"""Sherlock — main entry point and AppController.

`AppController` owns the long-lived services (storage, ads, sherlock
search engine, email OSINT, profile enrichment) and the AppState
observable singleton. It also builds the `ControllerMethods` dataclass
that bridges the controller layer to the React-style component tree
(`AppShell` and its descendants).

View navigation is handled inside `AppShell` via `use_state` + injected
controller methods. `start_search` / `_apply_progress` only mutate the
observable state; the UI re-renders automatically.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import flet as ft

from components.update_dialog import show_update_dialog
from core.constants import (
    APP_NAME,
    APP_VERSION,
    ERR_GENERIC,
    ERR_INVALID_EMAIL,
    ERR_NETWORK,
    MODE_EMAIL,
    MODE_PHONE,
    MODE_USERNAME,
    MSG_OFFLINE,
    MSG_ONLINE,
    MSG_SEARCH_OFFLINE,
    STORAGE_CACHED_RESULTS,
    STORAGE_CACHED_SITES,
    STORAGE_CHECK_DOMAINS,
    STORAGE_COOKIES_PATH,
    STORAGE_DB_UNHEALTHY,
    STORAGE_DEEP_ENRICH,
    STORAGE_DNS_RESOLVER,
    STORAGE_EMAIL_CONCURRENCY,
    STORAGE_EMAIL_ONLY_FOUND,
    STORAGE_EMAIL_TIMEOUT,
    STORAGE_ENRICHMENT_MODE,
    STORAGE_EXCLUSIONS,
    STORAGE_EXTRACT_INFO,
    STORAGE_HISTORY,
    STORAGE_I2P_PROXY,
    STORAGE_LOCAL_DB,
    STORAGE_LOG_ENGINE_LOGS,
    STORAGE_MANIFEST,
    STORAGE_MAX_CONNECTIONS,
    STORAGE_NO_PASSWORD_RECOVERY,
    STORAGE_ONBOARDING_DONE,
    STORAGE_PERMUTE,
    STORAGE_PHONE_CATEGORIES,
    STORAGE_PHONE_CONCURRENCY,
    STORAGE_PHONE_MODULES,
    STORAGE_PHONE_REGION,
    STORAGE_PROXY_URL,
    STORAGE_RECURSIVE_SEARCH,
    STORAGE_RETRIES,
    STORAGE_SCAN_DEPTH,
    STORAGE_SEARCH_KEYWORDS,
    STORAGE_SEARCH_MODE,
    STORAGE_SELECTED_SITES,
    STORAGE_THEME,
    STORAGE_TIMEOUT,
    STORAGE_USE_CURL_CFFI,
)
from core.logger_handler import in_memory_log_handler, set_engine_logs
from core.shared_services import mount_shared_services
from core.state import state
from core.tasks import spawn
from core.theme import AppTheme
from services.ad_service import AdService
from services.email_service import EmailResult, EmailSearchProgress, EmailService
from services.enrich_service import EnrichService
from services.phone_service import PhoneResult, PhoneSearchProgress, PhoneService
from services.scan_notify import ScanNotifier
from services.sherlock_service import SearchProgress, SherlockService, SiteResult
from services.storage_service import (
    StorageService,
    decode_stored_history,
    encode_history_entries,
)
from services.update_service import UpdateService
from state.controller_ctx import (
    ControllerMethods,
    ControllerMethodsCtx,
)

logger = logging.getLogger("sherlock")


class AppController:
    """Top-level controller owning services and reactive state."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.storage: StorageService | None = None
        self.ad_service: AdService | None = None
        # OS-shade scan progress (foreground service + progress bar + Cancel)
        # and the wake lock that keeps the screen on while a scan runs.
        self.scan_notify: ScanNotifier = ScanNotifier(page)
        self.wakelock: ft.Wakelock | None = None
        self.sherlock_service: SherlockService | None = None
        self.email_service: EmailService | None = None
        self.phone_service: PhoneService | None = None
        self.enrich_service: EnrichService | None = None
        self.update_service: UpdateService | None = None
        self.connectivity: ft.Connectivity | None = None
        # Main-thread event loop, captured in init(). Worker threads
        # (the sherlock scan thread) bridge progress callbacks onto it
        # via asyncio.run_coroutine_threadsafe — page.run_task cannot be
        # used off the main loop (it resolves session.connection.loop in
        # a context with no running loop and drops the coroutine).
        self._main_loop: asyncio.AbstractEventLoop | None = None
        # Shared controller-methods instance the component tree reads via
        # use_context(ControllerMethodsCtx). AppShell mutates the view-
        # navigation closures in-place; we hand AppShell a reference so
        # our own methods (start_search, etc.) can invoke them too.
        self._controller_methods: ControllerMethods | None = None
        # Streaming real-time enrichment queue & task
        self._enrich_queue: asyncio.Queue[str] | None = None
        self._enriched_seen: set[str] = set()
        self._enrich_worker_task: asyncio.Task | None = None
        # Enrichment generation: bumped on every kill/new search. The old
        # drain worker captures its generation at entry and self-quiesces
        # (skips writes) once a newer generation exists — orphaned
        # _enrich_single/avatar tasks can never contaminate the next scan.
        self._enrich_gen: int = 0
        # Per-scan avatar warm budget (reset in _register_search_task).
        self._avatar_warmed: int = 0
        # Handle of the in-flight search task (the home-screen `_run`
        # task awaiting start_search/start_email_search) — cancelled
        # instantly when a new search supersedes it.
        self._search_task: asyncio.Task | None = None
        # Serializes history read-modify-write (primary-done bridge vs
        # final save) so concurrent upserts can't interleave and lose one.
        self._history_lock = asyncio.Lock()
        # Coalesced progress bridge throttling
        self._last_progress_emit: float = 0.0
        self._pending_progress: Any | None = None
        self._progress_emit_scheduled: bool = False
        # Single render-budget flusher: ALL scan-time observable mutations
        # (progress ticks + enrichment batches) funnel through one task that
        # bumps progress_version at most ~2x/sec. Every bump re-renders the
        # whole tree on the main loop (Flet has no internal batching), so
        # per-URL enrichment bumps and 5Hz ticks were saturating the loop —
        # the scan freeze. Completions/cancellations bump directly.
        self._render_dirty: bool = False
        self._pending_enrichments: dict[str, dict] = {}
        self._render_flush_task: asyncio.Task | None = None

    # --- Lifecycle ----------------------------------------------------

    def _kill_all_activity(self, reason: str) -> None:
        """Instantly kill every running search activity.

        Called whenever a new search starts: the new search is the
        priority, so both engines, their in-flight tasks and the
        enrichment worker die regardless of `state.is_searching` (which
        can lie — a task hung mid-await leaves it stale-True, a finished
        scan leaves it False while background work drains). Cancelling
        the task also means the old search's results/history tail can
        never run and clobber the new search's state.

        Note: `sherlock_service.cancel()` reaches into the worker's own
        event loop and cancels the running maigret task, which aborts the
        site checks in flight — maigret's executor cancels its queue workers
        and each worker cancels its live request
        (.venv/maigret/executors.py:60-69, 99-110). An earlier comment here
        claimed those requests "cannot be interrupted"; that was wrong, and
        it was why a cancelled username scan kept running to completion.
        """
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None

        killed = []
        self._enrich_gen += 1
        if self._enrich_worker_task and not self._enrich_worker_task.done():
            self._cancel_task_threadsafe(self._enrich_worker_task)
            killed.append("enrich-worker")
        self._enrich_queue = None
        if self._render_flush_task and not self._render_flush_task.done():
            self._cancel_task_threadsafe(self._render_flush_task)
            killed.append("render-flusher")
        self._render_flush_task = None
        # A cancelled scan's queued tick must never be applied by the next
        # scan's flusher (especially email/phone, whose snapshots are new
        # objects rather than the same mutable username progress instance).
        self._pending_progress = None
        self._render_dirty = False
        if hasattr(self.sherlock_service, "cancel"):
            self.sherlock_service.cancel()
            killed.append("sherlock-engine")
        if hasattr(self.email_service, "cancel"):
            self.email_service.cancel()
            killed.append("email-engine")
        if hasattr(self.phone_service, "cancel"):
            self.phone_service.cancel()
            killed.append("phone-engine")
        if (
            self._search_task
            and self._search_task is not current
            and not self._search_task.done()
        ):
            self._cancel_task_threadsafe(self._search_task)
            killed.append("search-task")
        state.is_searching = False
        # Drain the dead scan's target scope too. `_apply_progress` admits a
        # username tick whose target is in `state.search_targets`, and the
        # replacement does not rebind that list until its engine starts — so
        # without this, a dying scan's secondary/cached ticks stay admissible
        # during the interstitial + site-load window. REBIND, never clear:
        # the dead worker holds this same list object and appends recursive
        # secondaries to it, so an in-place clear would be undone by the next
        # append and the tick would re-enter scope. The next `search()` binds
        # the fresh list.
        state.search_targets = []
        # The old scan's shade entry and wake lock die with its engine. The
        # replacement re-opens both in its own start path. Loop-safe: cancel
        # and supersede can arrive from a sync context (tests, UI handlers).
        self._spawn_bg(self.scan_notify.stop_service(), "scan-notify-stop")
        self._spawn_bg(self._set_wakelock(False), "wakelock-off")
        logger.info("KILL %s → cancelled: %s", reason, ", ".join(killed) or "nothing")

    def _spawn_bg(self, coro, name: str = "bg-task"):
        """Spawn when a loop is running; otherwise close the coro and skip.

        Cancelling/superseding can happen from synchronous UI callbacks where
        no loop is current — a bare create_task would leak the coroutine and
        trip the warning-escalation filter.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                coro.close()
            except Exception:
                pass
            logger.debug("No running loop; skipped %s", name)
            return None
        return spawn(coro, name=name)

    def _live_username_progress(self) -> bool:
        """True when a username scan is genuinely mid-flight.

        Authoritative source is the progress object, not `is_searching`:
        the flag is set optimistically by the Results retry button and
        cleared by cancel/kill, so on its own it can disagree with reality
        in both directions.
        """
        prog = state.search_progress
        if prog is None or hasattr(prog, "checked_modules"):
            return False  # email progress or nothing at all
        return bool(getattr(prog, "is_running", False))

    def _owns_scan(self) -> bool:
        """True while the CALLING task is still the registered search task.

        Target equality alone is not ownership: the retry button and a
        history re-search can start a scan for the SAME target, and a dying
        scan that only compares names would then clear the live
        replacement's flags and stop its shared render flusher.
        `_search_task` is set by every start, so a superseded scan fails
        this test however its result arrives.

        Outside a running loop (direct calls from teardown/tests) there is no
        calling task to compare, and the caller's own target guard decides.
        """
        try:
            current = asyncio.current_task()
        except RuntimeError:
            return True
        return self._search_task is None or self._search_task is current

    def _abandon_search(self, target: str, progress_obj) -> None:
        """Clear this search's state after a cancellation before the engine
        started (the window between setting the flags and the engine `try`).

        Guarded on ownership so a superseded scan cannot clear the live
        replacement's flags, exactly like the exception handlers below.
        """
        try:
            if not self._owns_scan():
                return
            if (state.current_username or "").strip().lower() != target.strip().lower():
                return
            state.is_searching = False
            state.search_error = None
            if progress_obj is not None:
                progress_obj.is_running = False
            state.progress_version += 1
            self._stop_render_flusher()
        except Exception as exc:  # never mask the cancellation
            logger.warning("abandon_search cleanup failed: %s", exc)

    def _live_email_progress(self) -> bool:
        """Email counterpart of :meth:`_live_username_progress`."""
        prog = state.search_progress
        if (
            prog is None
            or not hasattr(prog, "checked_modules")
            or hasattr(prog, "phone")
        ):
            return False  # username/phone progress or nothing at all
        return bool(getattr(prog, "is_running", False))

    def _live_phone_progress(self) -> bool:
        """Phone counterpart of :meth:`_live_username_progress`."""
        prog = state.search_progress
        if prog is None or not hasattr(prog, "phone"):
            return False
        return bool(getattr(prog, "is_running", False))

    def _register_search_task(self) -> None:
        """Register the calling task as the active search (killable)."""
        self._search_task = asyncio.current_task()
        self._avatar_warmed = 0
        self._start_render_flusher()

    def _start_render_flusher(self) -> None:
        """Start the single render-budget flusher for this search cycle."""
        if self._render_flush_task and not self._render_flush_task.done():
            return
        self._render_dirty = False
        self._pending_progress = None
        self._pending_enrichments = {}
        self._render_flush_task = spawn(self._render_flusher())

    def _flush_pending_progress(self) -> None:
        """Publish ONE latest snapshot to BOTH surfaces (animepahe pattern).

        The UI observable and the shade queue are fed from the same snapshot,
        in the same 0.5 s window. Email/phone progress objects are fresh
        snapshots, so assigning them outside this window caused a full
        observable re-render per tick IN ADDITION TO the flusher's render.
        """
        progress, self._pending_progress = self._pending_progress, None
        if progress is not None:
            state.search_progress = progress
            self._notify_scan_progress(progress)

    def _stop_render_flusher(self) -> None:
        """Stop the flusher on normal completion (no kill follows).

        Flushes any residual pending progress and enrichments first so the
        tail batch is never lost, then cancels the idle 0.5s wake loop —
        otherwise it spins for the app lifetime.
        """
        self._flush_pending_progress()
        pending, self._pending_enrichments = self._pending_enrichments, {}
        if pending:
            try:
                state.enrichments.update(pending)
            except Exception:
                pass
        task, self._render_flush_task = self._render_flush_task, None
        if task and not task.done():
            task.cancel()

    async def _render_flusher(self) -> None:
        """The ONLY progress_version bumper during a scan (~2Hz max).

        Every bump invalidates every use_context(AppStateCtx) component and
        re-renders + re-diffs + re-encodes the whole tree on the main loop —
        Installed flet 1.0.4 coalesces updates per wake (session.py __updates_scheduler
        drains per wake, MessagePack encode inline). Funneling all scan-time
        mutations through this one window keeps the loop free for socket
        receive and click dispatch.
        """
        try:
            while True:
                await asyncio.sleep(0.5)
                if not self._render_dirty:
                    continue
                self._render_dirty = False
                self._flush_pending_progress()
                if self._pending_enrichments:
                    batch = self._pending_enrichments
                    self._pending_enrichments = {}
                    state.enrichments.update(batch)
                    # Mirror set_enrichment's LRU cap after the batch write.
                    from core.state import _ENRICHMENT_CAP

                    while len(state.enrichments) > _ENRICHMENT_CAP:
                        oldest = next(iter(state.enrichments))
                        del state.enrichments[oldest]
                # Dirty alone means render — the enrichment tail after a
                # scan completes also lands here (is_searching already False).
                state.progress_version += 1
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            # A raise here used to end the loop for good: every later
            # `_render_dirty = True` set a flag nothing read, so the UI froze
            # mid-scan with no error and no recovery. Keep the bump going.
            logger.warning("Render flusher iteration failed: %s", exc, exc_info=True)
            self._render_dirty = True
            try:
                while True:
                    await asyncio.sleep(0.5)
                    if self._render_dirty:
                        self._render_dirty = False
                        self._flush_pending_progress()
                        state.progress_version += 1
            except asyncio.CancelledError:
                pass

    async def init(self) -> None:
        """Configure the page, init services, load state, mount AppShell."""
        logger.info("Starting %s v%s", APP_NAME, APP_VERSION)
        self._main_loop = asyncio.get_running_loop()

        self.page.title = APP_NAME
        self.page.padding = 0
        self.page.spacing = 0
        # Bundled variable font (src/assets/fonts/Outfit-Variable.ttf) —
        # offline first paint, no Google-Fonts fetch on launch.
        self.page.fonts = {"Outfit": "fonts/Outfit-Variable.ttf"}
        self.page.theme = AppTheme.get_light_theme()
        self.page.dark_theme = AppTheme.get_dark_theme()
        self.page.theme.font_family = "Outfit"
        self.page.dark_theme.font_family = "Outfit"
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        self.page.window.min_width = 360
        self.page.window.min_height = 600

        # Register FilePicker singleton. FilePicker extends Service;
        # self-registers through page._services (see Flet
        # .venv/controls/services/file_picker.py + service.py:11-19).
        # Constructing it inline per-call loses the registration on Android.
        file_picker = ft.FilePicker()
        self.page.services.append(file_picker)
        self.page.file_picker = file_picker

        # Connectivity service — native listener for device network state.
        # Drives state.is_online (offline banner, transition toasts, and
        # the search gate). page.on_disconnect is NOT a substitute: it is
        # the Flet web-client session event, not internet availability.
        self.connectivity = ft.Connectivity()
        self.connectivity.on_change = self._on_connectivity_change
        self.page.services.append(self.connectivity)

        # Shared transient services (haptics/clipboard/share/url-launcher):
        # mount one of each so per-click helpers reuse instead of registering
        # a new service on every tap.
        mount_shared_services(self.page)

        # Wake lock: keeps the display awake while a scan runs, so the user
        # can leave the app mid-scan (the foreground service keeps the engine
        # alive; this keeps the screen on).
        self.wakelock = ft.Wakelock()
        if self.wakelock not in self.page.services:
            self.page.services.append(self.wakelock)

        # Scan progress in the shade: mount the notification service and
        # channels up front so the first scan does not pay for it.
        self.scan_notify.set_handlers(
            on_cancel=self._cancel_active_scan,
            on_view=self._show_results_from_notification,
            on_permission_denied=self._notify_permission_denied,
        )
        # The shared AppHeader pill uses this to open Results.
        from components.app_header import set_scan_navigation

        set_scan_navigation(self._show_results_from_notification)
        # Mount first, then clear a stale row: a fresh process has no live
        # Python scan, so any FGS row left by the PREVIOUS process is stale
        # (it survived via the sticky service but nothing can advance it).
        self.page.run_task(self._mount_notifications)

        self.page.run_task(self._init_connectivity)
        self.page.on_app_lifecycle_state_change = self._on_lifecycle_change

        # Init services
        self.storage = StorageService.for_page(self.page)
        self.ad_service = AdService(self.page)
        from services.ad_service import AD_SERVICE_REF

        AD_SERVICE_REF["service"] = self.ad_service
        self.sherlock_service = SherlockService()
        self.email_service = EmailService()
        self.phone_service = PhoneService()
        self.enrich_service = EnrichService()
        self.update_service = UpdateService()

        # Load saved state
        await self._load_saved_state()

        # Gather UMP consent then preload interstitial (Play policy)
        async def _consent_and_preload():
            await self.ad_service.gather_consent()
            await self.ad_service.preload_interstitial()

        self.page.run_task(_consent_and_preload)

        # Load sites if sherlock is available
        if self.sherlock_service.is_available:
            self.page.run_task(self._load_and_cache_sites)

        # Check for remote updates / announcements in background
        self.page.run_task(self.check_for_updates)

        # Mount the React-style component tree
        from app_shell import AppShell

        refresh_sites = (
            self._load_and_cache_sites
            if self.sherlock_service.is_available
            else (lambda: asyncio.sleep(0))
        )

        methods = ControllerMethods(
            refresh_sites=refresh_sites,
            start_search=self.start_search,
            cancel_search=self.cancel_search,
            start_email_search=self.start_email_search,
            cancel_email_search=self.cancel_email_search,
            start_phone_search=self.start_phone_search,
            cancel_phone_search=self.cancel_phone_search,
            save_selected_sites=self.save_selected_sites,
            check_for_updates=self.check_for_updates,
            open_update_dialog=self.open_update_dialog,
            set_onboarding_done=self.set_onboarding_done,
            notifications_enabled=self.notifications_enabled,
            open_notification_settings=self.open_notification_settings,
            show_privacy_options=self.show_privacy_options,
            open_cached_result=self.open_cached_result,
            run_db_health=self.run_db_health,
        )
        self._controller_methods = methods

        def _on_system_back(_e=None):
            # Owner: Android/system back must never tear down the
            # single-view shell — it maps to in-app navigation instead.
            try:
                views_left = len(self.page.views)
            except Exception:
                views_left = -1
            logger.info(
                "System back pressed (root views=%d) → in-app navigation",
                views_left,
            )
            methods.handle_system_back()
            try:
                if not self.page.views:
                    # flet removed the only view anyway — unexpected for
                    # this shell; log loudly so device behavior is
                    # diagnosable from the terminal.
                    logger.error(
                        "System back removed the ROOT view — single-view "
                        "shell violated (flet behavior change?)"
                    )
            except Exception:
                pass

        self.page.on_view_pop = _on_system_back
        self.page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))
        logger.info("AppShell mounted successfully")
        # After render: the root view now exists, so guard its back.
        self._guard_root_view_pop()

    def _guard_root_view_pop(self) -> None:
        """Intercept Android back on the shell view instead of letting it pop.

        A single-view app has nowhere to pop TO: flet's Dart system-back
        handler bails out when the top view is the only one, so the
        framework finishes the activity and the app closes from any screen.

        `View.can_pop=False` + `on_confirm_pop` is the supported will-pop
        hook: back fires the handler, we route it to in-app navigation, and
        `confirm_pop(False)` keeps the view on the stack. No second view, so
        there is also nothing to accidentally reveal underneath.
        """
        try:
            views = self.page.views
            if not views:
                return
            root = views[-1]
            if getattr(root, "can_pop", True) is False:
                return  # already guarded (init re-entered)
            root.can_pop = False
            root.on_confirm_pop = self._on_root_confirm_pop
            self.page.update()
            logger.info("Root view back-guard installed")
        except Exception as exc:
            logger.warning("Could not install the back-guard: %s", exc)

    async def _on_root_confirm_pop(self, e) -> None:
        """Back was pressed on the shell: navigate in, never exit."""
        try:
            if self._controller_methods is not None and hasattr(
                self._controller_methods, "handle_system_back"
            ):
                self._controller_methods.handle_system_back()
        except Exception as exc:
            logger.warning("Back navigation failed: %s", exc)
        finally:
            # Keep the view: the app stays alive whatever navigation did.
            try:
                await e.control.confirm_pop(False)
            except Exception as exc:
                logger.warning("confirm_pop(False) failed: %s", exc)

    async def _load_saved_state(self) -> None:
        """Load saved settings from storage into observable state."""
        if not self.storage:
            return
        try:
            saved_theme = await self.storage.get(STORAGE_THEME)
            if saved_theme == "dark":
                self.page.theme_mode = ft.ThemeMode.DARK
            elif saved_theme == "system":
                self.page.theme_mode = ft.ThemeMode.SYSTEM
            else:
                self.page.theme_mode = ft.ThemeMode.LIGHT

            excl_raw = await self.storage.get(STORAGE_EXCLUSIONS)
            if excl_raw is not None:
                state.ignore_exclusions = excl_raw == "true"
            else:
                state.ignore_exclusions = False

            timeout_raw = await self.storage.get(STORAGE_TIMEOUT)
            if timeout_raw:
                try:
                    state.timeout = int(timeout_raw)
                except TypeError, ValueError:
                    logger.warning("Ignoring corrupt stored timeout: %r", timeout_raw)

            local_db_raw = await self.storage.get(STORAGE_LOCAL_DB)
            if local_db_raw:
                state.use_local_db = local_db_raw == "true"

            selected_raw = await self.storage.get(STORAGE_SELECTED_SITES)
            if selected_raw:
                state.selected_sites = selected_raw.split(",")
            else:
                state.selected_sites = []

            # Warm site-name cache — lets the Sites screen and the Home
            # targets card show real names before the first load lands.
            cache_raw = await self.storage.get(STORAGE_CACHED_SITES)
            if cache_raw:
                try:
                    names = json.loads(cache_raw)
                    if isinstance(names, list) and names:
                        state.sites_cache = sorted(names, key=str.lower)
                        # Deliberately NOT setting state.sites_total here: this
                        # list is a warm hint from storage and can be stale (an
                        # older database), which made the Home scope card show
                        # the previous DB's count (e.g. 5.2k vs 10,310). The
                        # count comes from load_sites(); before that the label
                        # reads the installed database metadata.
                        state.sites_version += 1
                except Exception:
                    logger.warning("Site cache unreadable; will repopulate on load")

            manifest_raw = await self.storage.get(STORAGE_MANIFEST)
            state.custom_manifest = manifest_raw if manifest_raw else ""

            # Email mode settings
            search_mode_raw = await self.storage.get(STORAGE_SEARCH_MODE)
            if search_mode_raw in (MODE_USERNAME, MODE_EMAIL, MODE_PHONE):
                state.search_mode = search_mode_raw

            email_timeout_raw = await self.storage.get(STORAGE_EMAIL_TIMEOUT)
            if email_timeout_raw:
                try:
                    val = int(email_timeout_raw)
                except TypeError, ValueError:
                    logger.warning(
                        "Ignoring corrupt stored email timeout: %r", email_timeout_raw
                    )
                    val = None
                if val is not None:
                    # Migration: old default 10 → new default 30
                    if val == 10:
                        state.email_timeout = 30
                        await self.storage.set(STORAGE_EMAIL_TIMEOUT, "30")
                    else:
                        state.email_timeout = val

            conc_raw = await self.storage.get(STORAGE_EMAIL_CONCURRENCY)
            if conc_raw:
                try:
                    val = max(5, min(30, int(conc_raw)))
                except TypeError, ValueError:
                    logger.warning("Ignoring corrupt stored concurrency: %r", conc_raw)
                    val = None
                if val is not None:
                    # Migration: old default 15 → new default 5
                    if val == 15:
                        state.email_concurrency = 5
                        await self.storage.set(STORAGE_EMAIL_CONCURRENCY, "5")
                    else:
                        state.email_concurrency = val
            only_found_raw = await self.storage.get(STORAGE_EMAIL_ONLY_FOUND)
            if only_found_raw is not None:
                state.email_only_found = only_found_raw == "true"

            phone_conc_raw = await self.storage.get(STORAGE_PHONE_CONCURRENCY)
            if phone_conc_raw:
                try:
                    state.phone_concurrency = max(5, min(30, int(phone_conc_raw)))
                except TypeError, ValueError:
                    logger.warning(
                        "Ignoring corrupt stored phone concurrency: %r",
                        phone_conc_raw,
                    )
            region_raw = await self.storage.get(STORAGE_PHONE_REGION)
            if region_raw:
                state.phone_region = str(region_raw).strip().upper()
            if state.phone_region:
                try:
                    import phonenumbers

                    # No hardcoded region list: validate against the library.
                    if state.phone_region not in phonenumbers.SUPPORTED_REGIONS:
                        state.phone_region = ""
                except Exception:
                    state.phone_region = ""
            phone_cats_raw = await self.storage.get(STORAGE_PHONE_CATEGORIES)
            if phone_cats_raw:
                try:
                    loaded = json.loads(phone_cats_raw)
                    if isinstance(loaded, list):
                        state.phone_categories[:] = [
                            str(c) for c in loaded if c
                        ]
                except Exception:
                    logger.warning("Phone categories unreadable; using all")
            phone_mods_raw = await self.storage.get(STORAGE_PHONE_MODULES)
            if phone_mods_raw:
                try:
                    loaded = json.loads(phone_mods_raw)
                    if isinstance(loaded, list):
                        state.phone_modules[:] = [str(m) for m in loaded if m]
                except Exception:
                    logger.warning("Phone modules unreadable; using all")
            proxy_raw = await self.storage.get(STORAGE_PROXY_URL)
            if proxy_raw:
                state.proxy_url = proxy_raw
            enrich_mode_raw = await self.storage.get(STORAGE_ENRICHMENT_MODE)
            if enrich_mode_raw in ("basic", "full"):
                # Migration: old default basic → new default full
                if enrich_mode_raw == "basic":
                    state.enrichment_mode = "full"
                    await self.storage.set(STORAGE_ENRICHMENT_MODE, "full")
                else:
                    state.enrichment_mode = enrich_mode_raw

            no_pw_raw = await self.storage.get(STORAGE_NO_PASSWORD_RECOVERY)
            if no_pw_raw is not None:
                state.no_password_recovery = no_pw_raw == "true"

            scan_depth_raw = await self.storage.get(STORAGE_SCAN_DEPTH)
            if scan_depth_raw in ("all", "1000", "500"):
                state.scan_depth = scan_depth_raw

            kw_raw = await self.storage.get(STORAGE_SEARCH_KEYWORDS)
            if kw_raw is not None:
                state.search_keywords = kw_raw
            deep_raw = await self.storage.get(STORAGE_DEEP_ENRICH)
            if deep_raw is not None:
                state.deep_enrich = deep_raw == "true"
            unhealthy_raw = await self.storage.get(STORAGE_DB_UNHEALTHY)
            if unhealthy_raw:
                try:
                    loaded_flags = json.loads(unhealthy_raw)
                    if isinstance(loaded_flags, list):
                        state.unhealthy_sites = [str(n) for n in loaded_flags]
                except Exception:
                    logger.warning("DB health flags unreadable; ignoring")
            cookies_raw = await self.storage.get(STORAGE_COOKIES_PATH)
            if cookies_raw:
                state.cookies_path = cookies_raw
            i2p_raw = await self.storage.get(STORAGE_I2P_PROXY)
            if i2p_raw:
                state.i2p_proxy = i2p_raw
            cd_raw = await self.storage.get(STORAGE_CHECK_DOMAINS)
            if cd_raw is not None:
                state.check_domains = cd_raw == "true"
            rec_raw = await self.storage.get(STORAGE_RECURSIVE_SEARCH)
            if rec_raw is not None:
                state.recursive_search = rec_raw == "true"

            perm_raw = await self.storage.get(STORAGE_PERMUTE)
            if perm_raw is not None:
                state.permute_enabled = perm_raw == "true"

            log_engine = await self.storage.get(STORAGE_LOG_ENGINE_LOGS)
            if log_engine is not None:
                state.log_engine_logs = log_engine == "true"
            # Applies the stored choice (or the muted default) to the engine
            # before any scan can emit anything.
            set_engine_logs(state.log_engine_logs)

            ext_raw = await self.storage.get(STORAGE_EXTRACT_INFO)
            if ext_raw is not None:
                state.extract_info = ext_raw == "true"

            max_conn_raw = await self.storage.get(STORAGE_MAX_CONNECTIONS)
            if max_conn_raw and max_conn_raw.isdigit():
                state.max_connections = int(max_conn_raw)

            retries_raw = await self.storage.get(STORAGE_RETRIES)
            if retries_raw and retries_raw.isdigit():
                state.retries = int(retries_raw)

            dns_res_raw = await self.storage.get(STORAGE_DNS_RESOLVER)
            if dns_res_raw in ("async", "threaded"):
                state.dns_resolver = dns_res_raw

            curl_raw = await self.storage.get(STORAGE_USE_CURL_CFFI)
            if curl_raw is not None:
                state.use_curl_cffi = curl_raw == "true"

            cached_res_raw = await self.storage.get(STORAGE_CACHED_RESULTS)
            if cached_res_raw:
                try:
                    res_map = json.loads(cached_res_raw)
                    if isinstance(res_map, dict):
                        state.results_cache.update(res_map)
                except Exception:
                    logger.warning("Failed to deserialize cached results from storage")

            onboarding_done = await self.storage.get(STORAGE_ONBOARDING_DONE)
            if onboarding_done == "true":
                state.has_accepted_terms = True
                state.is_first_launch = False
        except Exception as e:
            logger.warning("Settings load failed: %s", e)

    async def _load_and_cache_sites(self) -> None:
        """Load the site database, publish to state, and warm the cache.

        Wraps `SherlockService.load_sites` so the controller (not the
        service) owns persistence. Call sites:
        - app startup (page.run_task)
        - `refresh_sites` (used by Settings after manifest/DB changes)
        """
        if not self.sherlock_service:
            return
        count = await self.sherlock_service.load_sites()
        if not count or not state.sites_cache:
            return
        try:
            await self.storage.set(STORAGE_CACHED_SITES, json.dumps(state.sites_cache))
        except Exception as e:
            logger.warning("Failed to cache site names: %s", e)

    # --- Search -------------------------------------------------------

    async def start_search(self, username: str) -> None:
        """Run a sherlock search. The UI layer (AppShell/HomeScreen) is
        responsible for calling `controller.show_results()` separately
        to switch to the results view — that keeps view navigation in
        the AppShell layer where it belongs.
        """
        if not self.sherlock_service:
            return

        target_clean = username.strip()
        if not target_clean:
            return

        # SMART RE-ATTACH: attach only to a scan that is genuinely live.
        # The progress object must exist and still be running — otherwise a
        # stuck is_searching (the retry button sets it optimistically) or a
        # just-killed scan whose worker thread has not stopped ticking yet
        # would swallow every later search into a no-op re-attach, leaving
        # the app permanently "searching" with no scan behind it.
        if (
            state.is_searching
            and self._live_username_progress()
            and state.current_username.strip().lower() == target_clean.lower()
            and state.search_mode == MODE_USERNAME
        ):
            logger.info("Re-attaching to ongoing username search for %r", target_clean)
            if self._controller_methods and self._controller_methods.show_results:
                self._controller_methods.show_results()
            return

        # NEW SEARCH = PRIORITY: kill any prior activity instantly,
        # whether it is still running or just draining its tail.
        # NOTE: the kill runs AFTER the offline gate — a doomed new search
        # (offline/empty) must never kill a healthy running scan.

        # Offline gate — don't launch a 400-site scan that can only
        # produce timeouts. History/settings still work offline.
        if not state.is_online:
            logger.info("Search blocked: device offline")
            self._show_snack(MSG_SEARCH_OFFLINE, duration=10000)
            return

        self._kill_all_activity(f"username-search[{target_clean}]")
        self._register_search_task()

        state.current_username = target_clean
        # Own the mode as documented (history_screen/_on_re_search: "start_*
        # owns it after its own gates"). Without this, a start whose mode
        # disagrees with the running engine (hydrated default, a chip set
        # elsewhere) made _apply_progress's cross-mode guard drop EVERY tick
        # of a perfectly live scan — the Results screen froze.
        state.search_mode = MODE_USERNAME
        state.is_searching = True
        state.search_error = None
        # Reset to a fresh USERNAME-typed progress immediately: the UI
        # switches to ResultsScreen before the first scan tick, and a
        # stale EmailSearchProgress here crashes username-mode render.
        username_progress = SearchProgress(username=target_clean, is_running=True)
        state.search_progress = username_progress
        state.progress_version += 1
        logger.info(
            "WATCHDOG: username search START %r (total_sites pending)",
            target_clean,
        )
        # Shade progress (foreground service) + keep the screen awake: the
        # scan must survive the user leaving the app.
        await self.scan_notify.scan_started(target_clean, kind="username")
        await self._set_wakelock(True)
        # Interstitial on every search — original v1.4.0 behavior
        if self.ad_service:
            try:
                await self.ad_service.show_interstitial()
            except asyncio.CancelledError:
                # A supersede landing in this window must not leave the
                # flags set with no engine behind them (the stuck-flag
                # wedge). Clear, then let it propagate.
                self._abandon_search(target_clean, username_progress)
                raise
            except Exception as exc:
                logger.warning("Interstitial show failed: %s", exc)

        # Initialize streaming real-time enrichment queue & worker task
        self._enriched_seen.clear()
        self._enrich_queue = asyncio.Queue()
        if self.enrich_service and self.enrich_service.is_available:
            try:
                self._enrich_worker_task = spawn(self._drain_enrich_queue())
            except asyncio.CancelledError:
                self._abandon_search(target_clean, username_progress)
                raise
            except Exception as exc:
                logger.warning("Enrich worker start failed: %s", exc)

        # Make sure sites are loaded before searching
        try:
            await self.sherlock_service.load_sites()
        except asyncio.CancelledError:
            self._abandon_search(target_clean, username_progress)
            raise
        except Exception as e:
            logger.warning("load_sites failed before scan: %s", e)

        # Permute: separator variants join the target list (engine parses
        # the comma-joined string; per-target truth lands in
        # state.target_results and is merged into last_results below).
        scan_query = target_clean
        if state.permute_enabled:
            from core.permute import permute_username

            variants = permute_username(target_clean)
            if variants:
                scan_query = ",".join([target_clean, *variants])
                logger.info(
                    "Permute: +%d handle variant(s) joined the scan",
                    len(variants),
                )

        # Bridge the thread-shed progress callbacks onto the main loop
        try:
            result = await self.sherlock_service.search(
                username=scan_query,
                on_progress=self._progress_from_thread,
                timeout=state.timeout,
                after_primary=self._on_username_primary_done,
                on_secondary_target=self._on_secondary_target,
                on_target_result=self._on_target_result,
            )
            # If this scan was cancelled or superseded by another search, do not clobber state
            if (
                getattr(result, "is_cancelled", False)
                or state.current_username != target_clean
                or state.search_mode != MODE_USERNAME
            ):
                logger.info(
                    "WATCHDOG: username search %r cancelled/superseded — ignoring results",
                    target_clean,
                )
                # Only the scan that still OWNS the slot may touch it. A
                # superseded scan reaches here after its replacement started,
                # and `is_cancelled` alone cannot tell the two apart: the kill
                # path marks every live progress cancelled, supersede included.
                # The replacement owns the flags and the shared render
                # flusher — a dying scan must not clear or stop either.
                if self._owns_scan():
                    state.is_searching = False
                    username_progress.is_running = False
                    state.progress_version += 1
                    self._stop_render_flusher()
                return

            state.is_searching = False
            merged_results: dict = {}

            def _merge_result(r) -> None:
                existing = merged_results.get(r.site_name)
                # Prefer the CLAIMED row when two handles hit the same site.
                if existing is None or (
                    r.status == "Claimed" and existing.status != "Claimed"
                ):
                    merged_results[r.site_name] = r

            for prog in list((state.target_results or {}).values()):
                for r in prog.found + prog.not_found + prog.errors:
                    _merge_result(r)
            for r in result.found + result.not_found + result.errors:
                _merge_result(r)
            state.last_results = merged_results
            state.last_results_username = target_clean
            # Aggregate across targets: for a recursive/permuted scan `result`
            # is only the LAST secondary, so its counters describe one handle,
            # not the scan. Found is deduped by site (a claimed row wins).
            progs = list((state.target_results or {}).values())
            if len(progs) > 1:
                checked_total = sum(
                    min(
                        getattr(p, "checked_sites", 0) or 0,
                        getattr(p, "total_sites", 0) or 0,
                    )
                    for p in progs
                )
                sites_total = sum(getattr(p, "total_sites", 0) or 0 for p in progs)
            else:
                checked_total = result.checked_sites
                sites_total = result.total_sites
            found_count = sum(
                1 for r in merged_results.values() if r.status == "Claimed"
            )
            logger.info(
                "WATCHDOG: username search COMPLETE %r — %d/%d checked, %d found",
                target_clean,
                checked_total,
                sites_total,
                found_count,
            )

            await self._save_to_history(
                target_clean, found_count, sites_total, mode=MODE_USERNAME
            )

            # Final progress apply (enqueues any remaining found URLs).
            # Explicit bump: completion must render even though is_searching
            # is now False, and the result object may be the live one (silent
            # assign).
            await self._apply_progress(result)
            state.progress_version += 1
            self._stop_render_flusher()
            self._last_scan_summary = (
                "username",
                target_clean,
                found_count,
            )
            # Shade: stop the FGS and post the result row; drop the wake lock.
            await self.scan_notify.scan_finished(
                found_count, sites_total or result.total_sites
            )
            await self._set_wakelock(False)
        except asyncio.CancelledError:
            # BaseException in 3.8+ — `except Exception` does NOT catch
            # this. Without clearing the flag here, a cancelled scan left
            # is_searching stuck True and the Search button disabled
            # forever ("the scan is not starting").
            logger.info("WATCHDOG: username search %r killed mid-flight", target_clean)
            # Ownership, not just target equality: a cancel-then-retry of the
            # SAME handle leaves a dying scan whose target still matches, and
            # clearing unconditionally would flip the LIVE replacement's
            # is_searching and stop its flusher (the stuck-search wedge).
            if (
                self._owns_scan()
                and getattr(state, "current_username", None) == target_clean
                and state.search_mode == MODE_USERNAME
            ):
                state.is_searching = False
                username_progress.is_running = False
                state.search_error = None
                state.progress_version += 1
                self._stop_render_flusher()
                await self.scan_notify.stop_service()
                await self._set_wakelock(False)
            raise
        except Exception as e:
            if (
                self._owns_scan()
                and getattr(state, "current_username", None) == target_clean
                and state.search_mode == MODE_USERNAME
            ):
                logger.exception("Search failed")
                state.is_searching = False
                username_progress.is_running = False
                state.progress_version += 1
                state.search_error = str(e)
                # Surface the failure — without this a hard crash renders as
                # silently empty results. Keyword heuristic mirrors DDGS.
                msg = (
                    ERR_NETWORK
                    if any(
                        kw in str(e).lower()
                        for kw in (
                            "dns",
                            "connect",
                            "network",
                            "offline",
                            "unreachable",
                            "timeout",
                            "timed out",
                        )
                    )
                    else ERR_GENERIC
                )
                self._show_snack(msg, duration=10000)
                self._stop_render_flusher()
                await self.scan_notify.stop_service()
                await self._set_wakelock(False)

    async def _drain_enrich_queue(self) -> None:
        """Stream profile enrichment in real-time as sites are found."""
        if not self.enrich_service or not self.enrich_service.is_available:
            return

        gen = self._enrich_gen
        use_mutations = getattr(state, "enrichment_mode", "basic") == "full"
        concurrency = 3 if use_mutations else 4
        semaphore = asyncio.Semaphore(concurrency)
        pending_tasks: set[asyncio.Task] = set()

        async def _enrich_single(url: str) -> None:
            async with semaphore:
                if gen != self._enrich_gen:
                    return
                try:
                    fn = (
                        self.enrich_service.enrich_url_with_mutations
                        if use_mutations
                        else self.enrich_service.enrich_url
                    )
                    # Forward stored cookies (auth-gated schemes) + UA so
                    # enrichment performs instead of failing logged-out.
                    cookies_path = (state.cookies_path or "").strip() or None
                    cookies_str = ""
                    if cookies_path:
                        try:
                            cookies_str = (
                                Path(cookies_path).read_text(encoding="utf-8")
                                if Path(cookies_path).is_file()
                                else ""
                            )
                        except OSError:
                            cookies_str = ""
                    data = await fn(
                        url,
                        timeout=8 if use_mutations else 6,
                        cookies=cookies_str or None,
                        user_agent="Sherlock/2.x",
                    )
                    if data and gen == self._enrich_gen:
                        # Batch into the flusher — never bump per URL: every
                        # observable write re-renders the whole tree.
                        self._pending_enrichments[url] = data
                        self._render_dirty = True

                        # Warm the on-device avatar cache in the background once
                        # per found profile (never on the render path). Bounded
                        # like the email path — unbounded spawns stall the loop.
                        if self._avatar_warmed < 50:
                            avatar_url = (
                                data.get("image")
                                or data.get("avatar")
                                or data.get("photo")
                            )
                            if (
                                avatar_url
                                and isinstance(avatar_url, str)
                                and avatar_url.startswith("http")
                            ):
                                from services.cache_service import (
                                    schedule_avatar_download,
                                )

                                spawn(schedule_avatar_download(avatar_url))
                                self._avatar_warmed += 1
                except Exception as exc:
                    logger.warning("Streaming enrichment error for %s: %s", url, exc)

        while (
            state.is_searching
            or (self._enrich_queue and not self._enrich_queue.empty())
            or pending_tasks
        ):
            if gen != self._enrich_gen:
                # Superseded by a newer search — stop draining; children
                # self-quiesce via the generation check above.
                for t in pending_tasks:
                    t.cancel()
                return
            # Clean up completed tasks
            done = {t for t in pending_tasks if t.done()}
            pending_tasks.difference_update(done)

            if self._enrich_queue and not self._enrich_queue.empty():
                try:
                    url = self._enrich_queue.get_nowait()
                    t = spawn(_enrich_single(url))
                    pending_tasks.add(t)
                except Exception:
                    pass
            else:
                await asyncio.sleep(0.1)

        # Final wait for in-flight tasks when scan completes
        if pending_tasks and gen == self._enrich_gen:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

    def _record_target_result(self, progress) -> None:
        """MAIN LOOP: store per-target truth marshalled from the scan worker.

        `state.target_results` is an observable; writing it on the worker
        thread schedules UI updates off-loop. Every tick is recorded here
        (uncoalesced) so no target of a multi-target/recursive scan is lost.
        """
        try:
            state.target_results[progress.username] = progress
        except Exception as exc:
            logger.warning("Per-target record failed: %s", exc)

    def _append_search_target(self, name: str) -> None:
        """MAIN LOOP: widen the tick-admission scope with a recursive secondary.

        The engine appends secondaries to its OWN plain list; the observable
        `state.search_targets` holds a copy made at assignment, so without
        this the scope filter in `_apply_progress` drops every secondary tick
        and the recursive tail freezes at the primary's 100%.
        """
        targets = state.search_targets
        if targets is None:
            state.search_targets = [name]
            return
        if name not in targets:
            targets.append(name)

    def _on_secondary_target(self, name: str) -> None:
        """WORKER THREAD: hand a newly discovered secondary to the main loop."""
        loop = self._main_loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._append_search_target, name)
        except RuntimeError:
            pass  # main loop already tearing down

    def _on_target_result(self, progress) -> None:
        """WORKER THREAD: hand per-target truth to the main loop, uncoalesced."""
        loop = self._main_loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._record_target_result, progress)
        except RuntimeError:
            pass

    def _progress_from_thread(self, progress) -> None:
        """Bridge a scan-worker progress tick onto the main event loop.

        Coalesces rapid worker updates (500ms window — ~2Hz UI budget) and
        marks the render flusher dirty instead of bumping progress_version
        directly: one pipeline, one bump window, main loop stays free.
        """
        if not self._main_loop:
            logger.warning("No main loop captured; progress tick dropped")
            return
        self._pending_progress = progress
        if self._progress_emit_scheduled:
            return

        now = time.monotonic()
        delay = max(0.0, 0.50 - (now - self._last_progress_emit))
        self._progress_emit_scheduled = True

        async def _flush():
            self._progress_emit_scheduled = False
            self._last_progress_emit = time.monotonic()
            snap = self._pending_progress
            self._pending_progress = None
            if snap is not None:
                await self._apply_progress(snap)
                self._render_dirty = True

        if delay > 0.001:
            # call_later is NOT thread-safe — this bridge runs on the worker
            # thread, so schedule through call_soon_threadsafe.
            self._main_loop.call_soon_threadsafe(
                lambda: self._main_loop.call_later(
                    delay,
                    lambda: asyncio.run_coroutine_threadsafe(_flush(), self._main_loop),
                )
            )
        else:
            try:
                asyncio.run_coroutine_threadsafe(_flush(), self._main_loop)
            except Exception as e:
                logger.warning("Progress dispatch failed: %s", e)

    async def _apply_progress(self, progress) -> None:
        """Push a search-progress snapshot into observable state.

        NOTE: does NOT bump progress_version — during a scan the render
        flusher owns that (single ~2Hz window). Assigning the live progress
        object is silent (same identity), so this only updates data; the
        next flusher tick renders it. Completion paths bump explicitly.

        Ticks from killed/superseded scans are dropped: a dying scan's
        late callbacks (e.g. its finally-block tick) must never clobber
        the current search's progress slot. Cross-mode ticks are always
        dropped; same-mode ticks are dropped when their target is not
        the active search's target, or when the scan that produced them has
        already been cancelled.
        """
        if getattr(progress, "is_cancelled", False):
            # The user stopped this scan. A bare cancel leaves the target
            # matching, so the scope check below would admit the cancel
            # path's own trailing tick and repaint a scan the UI has already
            # reported as stopped.
            logger.debug("Dropping tick from a cancelled scan")
            return
        is_phone_progress = hasattr(progress, "phone") and not hasattr(progress, "email")
        is_email_progress = hasattr(progress, "checked_modules") and not is_phone_progress
        if is_phone_progress and state.search_mode != MODE_PHONE:
            logger.debug(
                "Dropping phone progress tick while in %s mode", state.search_mode
            )
            return
        if is_email_progress and state.search_mode != MODE_EMAIL:
            logger.debug(
                "Dropping email progress tick while in %s mode", state.search_mode
            )
            return
        if not is_email_progress and not is_phone_progress and state.search_mode != MODE_USERNAME:
            logger.debug(
                "Dropping username progress tick while in %s mode", state.search_mode
            )
            return
        if is_phone_progress:
            if getattr(progress, "phone", None) != state.current_username:
                logger.debug("Dropping stale phone progress tick — superseded scan")
                return
        elif is_email_progress:
            if getattr(progress, "email", None) != state.current_username:
                logger.debug("Dropping stale email progress tick — superseded scan")
                return
        else:
            # Scope of a legitimate tick = the active query PLUS every
            # target the engine is scanning right now.
            #
            # The engine APPENDS recursive secondaries to state.search_targets
            # (sherlock_service, `targets.append` — whose own comment says it
            # exists precisely so this filter admits them) and `parse_usernames`
            # puts permute variants there too. The old check compared ONLY
            # against current_username and fired first, so it dropped every
            # secondary tick and the final apply — which carries `last_prog`,
            # the last secondary. The primary rendered, the recursive tail
            # froze, and `is_searching` stayed True for the whole tail (up to
            # 20 targets x 500 sites). That is the "stuck at 98/99%" stall.
            probe = (getattr(progress, "username", None) or "").strip().lower()
            primary = (state.current_username or "").strip().lower()
            # primary unset => cached reattach writes progress directly:
            # nothing to supersede against, so admit.
            if primary and probe != primary:
                # Snapshot: the worker thread appends secondaries to this
                # same list object; never iterate it live.
                scope = {
                    str(t).strip().lower() for t in list(state.search_targets or [])
                }
                if probe not in scope:
                    logger.debug(
                        "Dropping stale username progress tick — superseded scan"
                    )
                    return
        # Publish only from the single 0.5 s flusher. Assigning a fresh
        # email/phone snapshot here would re-render the observable tree once
        # here and again when the flusher bumps progress_version.
        self._pending_progress = progress
        self._render_dirty = True

        # Stream newly discovered found URLs into the enrichment queue
        if (
            self.enrich_service
            and self.enrich_service.is_available
            and self._enrich_queue is not None
            and getattr(progress, "found", None)
        ):
            for r in list(progress.found):
                url = getattr(r, "url_user", None) or getattr(r, "url_main", None)
                if url and url not in self._enriched_seen:
                    self._enriched_seen.add(url)
                    self._enrich_queue.put_nowait(url)

    def _notify_scan_progress(self, progress) -> None:
        """Queue the same snapshot the UI flusher just published.

        Both engines are handled here (networks vs validator platforms) so the
        shade and the Results bar always agree. The flusher is the throttle;
        this NEVER awaits the notification bridge — ScanNotifier coalesces the
        latest values onto its own task, so a slow platform channel cannot
        stall the UI loop.
        """
        checked = getattr(progress, "checked_sites", None)
        if checked is None:
            checked = getattr(progress, "checked_modules", 0) or 0
        total = getattr(progress, "total_sites", None)
        if not total:
            total = getattr(progress, "total_modules", 0) or 0
        try:
            self.scan_notify.progress(checked, total)
        except Exception as exc:  # never let a shade post break a scan tick
            logger.debug("ScanNotifier: progress bridge failed: %s", exc)

    def _cancel_task_threadsafe(self, task: asyncio.Task | None) -> None:
        """Cancel a task from any thread (sync UI callbacks may run off-loop)."""
        if task is None or task.done():
            return
        try:
            loop = self._main_loop
            if loop is not None and asyncio.get_running_loop() is not loop:
                loop.call_soon_threadsafe(task.cancel)
                return
        except RuntimeError:
            pass
        try:
            task.cancel()
        except Exception:
            pass

    def _cancel_active_scan(self) -> None:
        """Cancel whichever engine is running (shade Cancel action).

        The notification carries no mode of its own; derive it from the live
        progress object, falling back to the selected mode. This is what makes
        Cancel in the shade stop an email or phone scan too (it used to always
        cancel the username engine).
        """
        prog = state.search_progress
        if hasattr(prog, "phone"):
            self.cancel_phone_search()
        elif hasattr(prog, "checked_modules"):
            self.cancel_email_search()
        elif state.search_mode == MODE_PHONE:
            self.cancel_phone_search()
        elif state.search_mode == MODE_EMAIL:
            self.cancel_email_search()
        else:
            self.cancel_search()

    def cancel_search(self) -> None:
        """Cancel a running search (sync — called from UI)."""
        logger.info("CANCEL requested by user (username mode)")
        self._kill_all_activity("user-cancel[username]")
        prog = state.search_progress
        if prog is not None and getattr(prog, "is_running", False):
            # Only mark a LIVE scan: a cancel landing after completion
            # rewrote a finished result as cancelled.
            prog.is_running = False
            prog.is_cancelled = True
        state.progress_version += 1
        try:
            self.page.update()
        except Exception:
            pass

    # --- Email Search -------------------------------------------------

    async def start_email_search(self, email: str) -> None:
        """Run a holehe email OSINT search with optional enrichment."""
        if not self.email_service or not self.email_service.is_available:
            self._show_snack("Email search is not available.")
            return

        email_clean = email.strip()
        if not email_clean:
            return

        # SMART RE-ATTACH: live progress only (see the username gate — a
        # stuck is_searching must not swallow the search).
        if (
            state.is_searching
            and self._live_email_progress()
            and state.current_username.strip().lower() == email_clean.lower()
            and state.search_mode == MODE_EMAIL
        ):
            logger.info("Re-attaching to ongoing email search for %r", email_clean)
            if self._controller_methods and self._controller_methods.show_results:
                self._controller_methods.show_results()
            return

        # NOTE: the kill runs AFTER the gates — a doomed new search
        # (offline/invalid) must never kill a healthy running scan.
        # Offline gate
        if not state.is_online:
            logger.info("Email search blocked: device offline")
            self._show_snack(MSG_SEARCH_OFFLINE, duration=10000)
            return

        # Validate email
        from services.email_service import validate_email

        if not validate_email(email_clean):
            self._show_snack(ERR_INVALID_EMAIL)
            return

        self._kill_all_activity(f"email-search[{email_clean}]")
        self._register_search_task()

        state.current_username = email_clean
        # Same contract as the username path: the start owns the mode, so the
        # cross-mode guard can't drop a live email scan's ticks.
        state.search_mode = MODE_EMAIL
        state.is_searching = True
        state.search_error = None
        state.email_results.clear()
        # Reset to a fresh EMAIL-typed progress immediately: the UI
        # switches to ResultsScreen before the first scan tick, and a
        # stale SearchProgress here crashes email-mode render.
        email_progress = EmailSearchProgress(email=email_clean, is_running=True)
        state.search_progress = email_progress
        state.progress_version += 1
        logger.info("WATCHDOG: email search START %r", email_clean)
        await self.scan_notify.scan_started(email_clean, kind="email")
        await self._set_wakelock(True)

        # Interstitial on every email search too — same v1.4.0 behavior
        if self.ad_service:
            try:
                await self.ad_service.show_interstitial()
            except asyncio.CancelledError:
                # Mirrors the username path (:862): a supersede landing in
                # this window must not leave the flags set with no engine
                # behind them. Without this, a cancel caught here fell
                # through to `except Exception` — which does NOT catch
                # BaseException — leaving is_searching stuck True.
                self._abandon_search(email_clean, email_progress)
                raise
            except Exception as exc:
                logger.warning("Interstitial show failed: %s", exc)

        try:
            result = await self.email_service.search(
                email=email.strip(),
                on_progress=self._progress_from_thread,
                timeout=state.email_timeout,
                skip_password_recovery=state.no_password_recovery,
                concurrency=getattr(state, "email_concurrency", 12),
                use_curl_cffi=getattr(state, "use_curl_cffi", True),
                proxy=getattr(state, "proxy_url", "") or "",
            )
            # If this scan was cancelled or superseded by another search, do not clobber state
            if (
                getattr(result, "is_cancelled", False)
                or state.current_username != email.strip()
                or state.search_mode != MODE_EMAIL
            ):
                logger.info(
                    "WATCHDOG: email search %r cancelled/superseded — ignoring results",
                    email,
                )
                # Same rule as the username path: only the scan that still
                # OWNS the slot may touch it, because a superseded scan
                # reaches here after its replacement owns the flags and the
                # shared render flusher.
                if self._owns_scan():
                    state.is_searching = False
                    email_progress.is_running = False
                    state.progress_version += 1
                    self._stop_render_flusher()
                return

            state.is_searching = False
            logger.info(
                "WATCHDOG: email search COMPLETE %r — %d/%d checked, %d found",
                email,
                result.checked_modules,
                result.total_modules,
                len(result.found),
            )
            self._last_scan_summary = ("email", email_clean, len(result.found))
            await self.scan_notify.scan_finished(
                len(result.found),
                result.total_modules or result.checked_modules,
            )
            await self._set_wakelock(False)

            # Convert to result list for state
            all_results = [
                {
                    "name": r.name,
                    "domain": r.domain,
                    "method": r.method,
                    "exists": r.exists,
                    "rateLimit": r.rate_limit,
                    "unavailable": r.unavailable,
                    "frequent_rate_limit": r.frequent_rate_limit,
                    "emailrecovery": r.email_recovery,
                    "phoneNumber": r.phone_number,
                    "others": r.others,
                }
                for r in (
                    result.found
                    + result.not_found
                    + result.rate_limited
                    + result.unavailable
                )
            ]
            state.email_results[:] = all_results
            state.email_results_address = email.strip()
            state.email_found_count = len(result.found)
            state.email_not_found_count = len(result.not_found)
            state.email_rate_limited_count = len(result.rate_limited)
            state.email_unavailable_count = len(result.unavailable)
            state.email_total_modules = result.total_modules

            # URL-based socid enrichment is intentionally skipped for email
            # results: v2's Result.url is the platform homepage, not a
            # profile URL — fetching it would never match a socid scheme
            # (0% hit rate). Rich profile data instead arrives IN-BAND via
            # Result.extra/media, mapped into EmailResult.others and
            # rendered from there. Keep URL-based enrichment for username
            # mode where we have real profile URLs.

            # P2-2: warm the avatar cache for v2 media producers (gravatar,
            # github, etsy, duolingo) so email cards get persistent
            # on-device images. Bounded + fire-and-forget by design.
            from services.cache_service import schedule_avatar_download

            warmed = 0
            for rrow in all_results:
                if not rrow.get("exists"):
                    continue
                media = (rrow.get("others") or {}).get("media") or {}
                avatar = media.get("avatar")
                if isinstance(avatar, str) and avatar.startswith("http"):
                    spawn(schedule_avatar_download(avatar))
                    warmed += 1
                if warmed >= 50:
                    break
            if warmed:
                logger.info("Warmed %d email avatar cache slot(s)", warmed)

            await self._save_to_history(
                email.strip(),
                len(result.found),
                result.total_modules,
                mode=MODE_EMAIL,
            )

            # Final progress apply — explicit bump: the flusher only renders
            # while is_searching, and result may be the live progress object
            # (silent assign).
            await self._apply_progress(result)
            state.progress_version += 1
            self._stop_render_flusher()
        except asyncio.CancelledError:
            # Supersede guard (same as the username path): only clear the
            # flags if THIS search still owns the slot. A superseded task's
            # cancellation is delivered late, and clearing unconditionally
            # would flip the LIVE replacement's is_searching to False and
            # stop its render flusher, stranding it with a dead UI.
            logger.info("WATCHDOG: email search %r killed mid-flight", email)
            if (
                self._owns_scan()
                and state.current_username.strip().lower() == email_clean.lower()
                and state.search_mode == MODE_EMAIL
            ):
                state.is_searching = False
                email_progress.is_running = False
                state.search_error = None
                state.progress_version += 1
                self._stop_render_flusher()
                await self.scan_notify.stop_service()
                await self._set_wakelock(False)
            raise
        except ValueError as ve:
            if (
                self._owns_scan()
                and state.current_username.strip().lower() == email_clean.lower()
                and state.search_mode == MODE_EMAIL
            ):
                state.is_searching = False
                email_progress.is_running = False
                state.progress_version += 1
                self._stop_render_flusher()
            logger.warning("Email search rejected: %s", ve)
            self._show_snack(str(ve))
        except Exception as e:
            logger.exception("Email search failed")
            if (
                self._owns_scan()
                and state.current_username.strip().lower() == email_clean.lower()
                and state.search_mode == MODE_EMAIL
            ):
                state.is_searching = False
                email_progress.is_running = False
                state.progress_version += 1
                state.search_error = str(e)
                msg = (
                    ERR_NETWORK
                    if any(
                        kw in str(e).lower()
                        for kw in (
                            "dns",
                            "connect",
                            "network",
                            "offline",
                            "unreachable",
                            "timeout",
                            "timed out",
                        )
                    )
                    else ERR_GENERIC
                )
                self._show_snack(msg, duration=10000)
                self._stop_render_flusher()
                await self.scan_notify.stop_service()
                await self._set_wakelock(False)

    def cancel_email_search(self) -> None:
        """Cancel a running email search (sync — called from UI)."""
        logger.info("CANCEL requested by user (email mode)")
        self._kill_all_activity("user-cancel[email]")
        prog = state.search_progress
        if prog is not None and getattr(prog, "is_running", False):
            prog.is_running = False
            prog.is_cancelled = True
        state.progress_version += 1
        try:
            self.page.update()
        except Exception:
            pass

    async def start_phone_search(self, phone: str) -> None:
        """Run a phonsint phone OSINT search (beta)."""
        from services.phone_service import normalize_phone, validate_phone

        if not self.phone_service or not self.phone_service.is_available:
            self._show_snack("Phone search is not available.")
            return

        phone_clean = phone.strip()
        if not phone_clean:
            return

        region = (state.phone_region or "").strip().upper() or None
        identity = normalize_phone(phone_clean, region)

        # The engine validates; do it here too so a typo never launches a
        # pointless scan or flips the app into a dead progress state.
        if not validate_phone(phone_clean, region):
            self._show_snack(
                "Enter a valid phone number (include the country code).",
                duration=8000,
            )
            return

        if not state.is_online:
            logger.info("Phone search blocked: device offline")
            self._show_snack(MSG_SEARCH_OFFLINE, duration=10000)
            return

        # SMART RE-ATTACH: only to a genuinely live phone scan.
        if (
            state.is_searching
            and self._live_phone_progress()
            and state.current_username.strip().lower() == identity.lower()
            and state.search_mode == MODE_PHONE
        ):
            logger.info("Re-attaching to ongoing phone search for %r", identity)
            if self._controller_methods and self._controller_methods.show_results:
                self._controller_methods.show_results()
            return


        self._kill_all_activity(f"phone-search[{phone_clean}]")
        self._register_search_task()

        state.current_username = identity
        state.search_mode = MODE_PHONE
        state.is_searching = True
        state.search_error = None
        state.phone_results.clear()
        state.phone_results_number = phone_clean
        phone_progress = PhoneSearchProgress(phone=identity, is_running=True)
        state.search_progress = phone_progress
        state.progress_version += 1
        logger.info("WATCHDOG: phone search START %r", identity)

        await self.scan_notify.scan_started(identity, kind="phone")
        await self._set_wakelock(True)

        if self.ad_service:
            try:
                await self.ad_service.show_interstitial()
            except asyncio.CancelledError:
                self._abandon_search(identity, phone_progress)
                raise
            except Exception as exc:
                logger.warning("Interstitial show failed: %s", exc)

        try:
            result = await self.phone_service.search(
                phone=phone_clean,
                region=region,
                on_progress=self._progress_from_thread,
                timeout=state.timeout,
                concurrency=getattr(state, "phone_concurrency", 15) or 15,
                proxy=state.proxy_url or "",
                categories=list(state.phone_categories or []),
                modules=list(state.phone_modules or []),
            )

            if (
                getattr(result, "is_cancelled", False)
                or state.current_username != identity
                or state.search_mode != MODE_PHONE
            ):
                logger.info(
                    "WATCHDOG: phone search %r cancelled/superseded — ignoring results",
                    identity,
                )
                if self._owns_scan():
                    state.is_searching = False
                    phone_progress.is_running = False
                    state.progress_version += 1
                    self._stop_render_flusher()
                return

            state.is_searching = False
            logger.info(
                "WATCHDOG: phone search COMPLETE %r — %d/%d checked, %d found",
                identity,
                result.checked_modules,
                result.total_modules,
                len(result.found),
            )
            self._last_scan_summary = ("phone", phone_clean, len(result.found))
            await self.scan_notify.scan_finished(
                len(result.found), result.total_modules or result.checked_modules
            )
            await self._set_wakelock(False)

            rows = [
                {
                    "name": r.name,
                    "domain": getattr(r, "domain", "") or r.name.lower(),
                    "method": "",
                    "exists": r.exists,
                    "rateLimit": r.rate_limit,
                    "unavailable": r.unavailable,
                    "frequent_rate_limit": False,
                    "emailrecovery": (r.extra or {}).get("email") if r.extra else None,
                    "phoneNumber": getattr(r, "phone", None) or phone_clean,
                    "others": {
                        "extra": r.extra,
                        "media": r.media,
                        "url": getattr(r, "url_user", None)
                        or getattr(r, "url_main", None)
                        or r.url,
                        "message": r.reason,
                        "category": r.category,
                    },
                }
                for r in (result.found + result.not_found + result.errors)
            ]
            state.phone_results[:] = rows
            state.phone_results_number = phone_clean
            state.phone_found_count = len(result.found)
            state.phone_not_found_count = len(result.not_found)
            state.phone_rate_limited_count = len(result.rate_limited)
            state.phone_unavailable_count = len(result.unavailable)
            state.phone_total_modules = result.total_modules

            await self._save_to_history(
                phone_clean, len(result.found), result.total_modules, mode=MODE_PHONE
            )

            await self._apply_progress(result)
            state.progress_version += 1
            self._stop_render_flusher()
        except asyncio.CancelledError:
            logger.info("WATCHDOG: phone search %r killed mid-flight", identity)
            if (
                self._owns_scan()
                and state.current_username == identity
                and state.search_mode == MODE_PHONE
            ):
                state.is_searching = False
                phone_progress.is_running = False
                state.search_error = None
                state.progress_version += 1
                self._stop_render_flusher()
                await self.scan_notify.stop_service()
                await self._set_wakelock(False)
            raise
        except Exception as exc:
            if (
                self._owns_scan()
                and state.current_username == identity
                and state.search_mode == MODE_PHONE
            ):
                logger.exception("Phone search failed")
                state.is_searching = False
                phone_progress.is_running = False
                state.progress_version += 1
                state.search_error = str(exc)
                self._show_snack(ERR_NETWORK, duration=10000)
                self._stop_render_flusher()
                await self.scan_notify.stop_service()
                await self._set_wakelock(False)

    def cancel_phone_search(self) -> None:
        """Cancel a running phone search (sync — called from UI)."""
        logger.info("CANCEL requested by user (phone mode)")
        self._kill_all_activity("user-cancel[phone]")
        prog = state.search_progress
        if prog is not None and getattr(prog, "is_running", False):
            prog.is_running = False
            prog.is_cancelled = True
        state.progress_version += 1
        try:
            self.page.update()
        except Exception:
            pass

    async def save_selected_sites(self, sites: list[str]) -> None:
        """Persist the network-selection scope and update observable state.

        An empty list means "no custom scope" — scan every available
        network (same semantics the pre-restructure rewrite used).
        """
        state.selected_sites = list(sites) if sites else []
        if not self.storage:
            return
        try:
            if sites:
                await self.storage.set(STORAGE_SELECTED_SITES, ",".join(sites))
            else:
                await self.storage.delete(STORAGE_SELECTED_SITES)
        except Exception as e:
            logger.warning("Failed to persist site selection: %s", e)

    async def set_onboarding_done(self) -> None:
        """Mark onboarding complete in state and immediately flush to storage."""
        state.has_accepted_terms = True
        state.is_first_launch = False
        if self.storage:
            try:
                await self.storage.set(STORAGE_ONBOARDING_DONE, "true")
                await self.storage.flush()
                logger.info("Onboarding state successfully persisted")
            except Exception as e:
                logger.warning("Failed to persist onboarding state: %s", e)

    async def notifications_enabled(self) -> bool:
        """OS notification authorization for the Settings row."""
        return await self.scan_notify.are_notifications_enabled()

    async def open_notification_settings(self) -> None:
        """Public route for the Settings → Notifications row."""
        await self._open_notification_settings()

    async def show_privacy_options(self) -> str:
        """Open the UMP privacy-options form; returns what happened."""
        if not self.ad_service:
            return "no_manager"
        try:
            return await self.ad_service.show_privacy_options()
        except Exception as exc:
            logger.warning("Privacy options failed: %s", exc)
            return f"error:{exc}"

    def open_cached_result(self, query: str, mode: str) -> bool:
        """Open past results from cache instantly without re-scanning."""
        snapshot = state.get_cached_result(mode, query)
        if not snapshot:
            return False

        query_norm = query.strip().lower()
        current_norm = (state.current_username or "").strip().lower()
        # Same-target live scan: re-attach, do NOT clobber with a stale
        # snapshot (mirrors the start_search smart re-attach). Liveness and
        # mode are both required — is_searching alone can be stuck True
        # (that is the 99%-hang bug), and re-attaching across modes for an
        # identical string would open the wrong engine's results.
        live = (
            self._live_username_progress()
            if mode == MODE_USERNAME
            else (
                self._live_phone_progress()
                if mode == MODE_PHONE
                else self._live_email_progress()
            )
        ) and state.search_mode == mode
        if state.is_searching and live and current_norm == query_norm:
            if self._controller_methods and self._controller_methods.show_results:
                self._controller_methods.show_results()
            return True
        # Cancel any active scan if opening a different target
        if state.is_searching:
            self._kill_all_activity(f"open-cached-result[{query}]")

        # Major action: a full past result set is delivered instantly.
        from services.ad_service import fire_major_action_interstitial

        fire_major_action_interstitial()

        if mode == MODE_USERNAME:
            found_objs = [
                SiteResult(
                    site_name=r.get("site_name", "?"),
                    url_main=r.get("url_main", ""),
                    url_user=r.get("url_user", ""),
                    status=r.get("status", "Claimed"),
                    http_status=r.get("http_status", ""),
                    query_time=r.get("query_time"),
                    context=r.get("context"),
                    tags=r.get("tags", []),
                    ids_data=r.get("ids_data"),
                    error_type=r.get("error_type"),
                    error_hint=r.get("error_hint", ""),
                    protection=r.get("protection", []),
                    badge=r.get("badge", ""),
                    keyword_hit=r.get("keyword_hit", False),
                )
                for r in snapshot.get("found", [])
            ]
            notfound_objs = [
                SiteResult(
                    site_name=r.get("site_name", "?"),
                    url_main=r.get("url_main", ""),
                    url_user=r.get("url_user", ""),
                    status=r.get("status", "Available"),
                    http_status="",
                    error_type=r.get("error_type"),
                    error_hint=r.get("error_hint", ""),
                    protection=r.get("protection", []),
                    badge=r.get("badge", ""),
                    keyword_hit=r.get("keyword_hit", False),
                )
                for r in snapshot.get("not_found", [])
            ]
            error_objs = [
                SiteResult(
                    site_name=r.get("site_name", "?"),
                    url_main=r.get("url_main", ""),
                    url_user=r.get("url_user", ""),
                    status=r.get("status", "Error"),
                    http_status="",
                    context=r.get("context"),
                    error_type=r.get("error_type"),
                    error_hint=r.get("error_hint", ""),
                    protection=r.get("protection", []),
                    badge=r.get("badge", ""),
                    keyword_hit=r.get("keyword_hit", False),
                )
                for r in snapshot.get("errors", [])
            ]
            total = snapshot.get("total") or len(found_objs) + len(notfound_objs) + len(
                error_objs
            )
            progress = SearchProgress(
                username=query.strip(),
                total_sites=total,
                checked_sites=total,
                found=found_objs,
                not_found=notfound_objs,
                errors=error_objs,
                is_running=False,
            )
            state.current_username = query.strip()
            state.last_results_username = query.strip()
            state.last_results = {
                r.site_name: r for r in (found_objs + notfound_objs + error_objs)
            }
            state.search_mode = MODE_USERNAME
            state.search_progress = progress
            # Clear-first: update() alone would leak the previous target's
            # enrichments (stale avatars) into this cached result.
            state.enrichments.clear()
            if snapshot.get("enrichments"):
                state.enrichments.update(snapshot["enrichments"])
        elif mode == MODE_PHONE:
            all_phone = snapshot.get("phone_results", []) or []
            found_dicts = [
                r for r in all_phone if r.get("exists") and not r.get("rateLimit")
            ]
            not_found_dicts = [
                r
                for r in all_phone
                if not r.get("exists")
                and not r.get("rateLimit")
                and not r.get("unavailable")
            ]
            rate_limited_dicts = [
                r for r in all_phone if r.get("rateLimit") and not r.get("unavailable")
            ]
            unavailable_dicts = [r for r in all_phone if r.get("unavailable")]
            state.phone_results[:] = all_phone
            state.phone_results_number = query.strip()
            state.current_username = query.strip()
            state.search_mode = MODE_PHONE
            state.phone_found_count = len(found_dicts)
            state.phone_not_found_count = len(not_found_dicts)
            state.phone_rate_limited_count = len(rate_limited_dicts)
            state.phone_unavailable_count = len(unavailable_dicts)
            state.phone_total_modules = snapshot.get("total") or len(all_phone)
            state.enrichments.clear()
            self._enrich_gen += 1
            self._enriched_seen.clear()

            def _to_phone_result(r):
                others = r.get("others")
                others = others if isinstance(others, dict) else {}
                return PhoneResult(
                    name=r.get("name", ""),
                    category=others.get("category", ""),
                    exists=r.get("exists"),
                    rate_limit=r.get("rateLimit", False),
                    unavailable=r.get("unavailable", False),
                    url=others.get("url", "") or "",
                    url_main=others.get("url", "") or "",
                    url_user=others.get("url", "") or "",
                    domain=r.get("domain", ""),
                    phone=r.get("phoneNumber", "") or "",
                    extra=others.get("extra"),
                    media=others.get("media"),
                    reason=others.get("message", ""),
                )

            state.search_progress = PhoneSearchProgress(
                phone=query.strip(),
                total_modules=state.phone_total_modules,
                checked_modules=state.phone_total_modules,
                found=[_to_phone_result(r) for r in found_dicts],
                not_found=[_to_phone_result(r) for r in not_found_dicts],
                rate_limited=[_to_phone_result(r) for r in rate_limited_dicts],
                unavailable=[_to_phone_result(r) for r in unavailable_dicts],
                errors=[
                    _to_phone_result(r)
                    for r in rate_limited_dicts + unavailable_dicts
                ],
                is_running=False,
            )
        else:
            all_email = snapshot.get("email_results", []) or []
            found_dicts = [
                r for r in all_email if r.get("exists") and not r.get("rateLimit")
            ]
            not_found_dicts = [
                r
                for r in all_email
                if not r.get("exists")
                and not r.get("rateLimit")
                and not r.get("unavailable")
            ]
            rate_limited_dicts = [
                r for r in all_email if r.get("rateLimit") and not r.get("unavailable")
            ]
            unavailable_dicts = [r for r in all_email if r.get("unavailable")]
            state.email_results[:] = all_email
            state.email_results_address = query.strip()
            state.current_username = query.strip()
            state.search_mode = MODE_EMAIL
            state.email_found_count = len(found_dicts)
            state.email_not_found_count = len(not_found_dicts)
            state.email_rate_limited_count = len(rate_limited_dicts)
            state.email_unavailable_count = len(unavailable_dicts)
            state.email_total_modules = snapshot.get("total") or len(all_email)
            # Username enrichments are URL-keyed profile data — meaningless
            # for email rows. Clear so stale avatars can't leak in, and bump
            # the generation so any draining worker self-quiesces.
            state.enrichments.clear()
            self._enrich_gen += 1
            self._enriched_seen.clear()

            def _to_email_result(r):
                return EmailResult(
                    name=r.get("name", ""),
                    domain=r.get("domain", ""),
                    method=r.get("method", ""),
                    exists=r.get("exists"),
                    rate_limit=r.get("rateLimit", False),
                    frequent_rate_limit=r.get("frequent_rate_limit", False),
                    unavailable=r.get("unavailable", False),
                    email_recovery=r.get("emailrecovery"),
                    phone_number=r.get("phoneNumber"),
                    others=r.get("others"),
                )

            state.search_progress = EmailSearchProgress(
                email=query.strip(),
                total_modules=state.email_total_modules,
                checked_modules=state.email_total_modules,
                found=[_to_email_result(r) for r in found_dicts],
                not_found=[_to_email_result(r) for r in not_found_dicts],
                rate_limited=[_to_email_result(r) for r in rate_limited_dicts],
                unavailable=[_to_email_result(r) for r in unavailable_dicts],
                is_running=False,
            )

        state.is_searching = False
        state.progress_version += 1
        if self._controller_methods and self._controller_methods.show_results:
            self._controller_methods.show_results()
        return True

    def _on_username_primary_done(self, query: str, found: int, total: int) -> None:
        """Bridge from the scan worker thread: save history the moment the
        PRIMARY pass completes — the recursive tail can run much longer and
        the final (upserting) save only happens after it. Owner report:
        Recent must populate as soon as the user sees the scan 'finish'."""
        loop = self._main_loop
        if loop is None or not loop.is_running():
            logger.warning("Primary-done history bridge skipped (no main loop)")
            return

        def _schedule():
            spawn(self._save_to_history(query, found, total, mode=MODE_USERNAME))

        try:
            loop.call_soon_threadsafe(_schedule)
        except RuntimeError:
            logger.warning("Primary-done history bridge failed (loop closing)")

    async def _save_to_history(
        self, query: str, found: int, total: int, mode: str = MODE_USERNAME
    ) -> None:
        """Append a search entry to persistent history, snapshot results, and observable state."""
        # 1. Capture full results snapshot for instant history viewing
        try:
            if mode == MODE_USERNAME:
                prog = state.search_progress
                snapshot = {
                    "query": query,
                    "mode": mode,
                    "total": total,
                    "checked": total,
                    "found": [
                        {
                            "site_name": getattr(r, "site_name", "?"),
                            "url_main": getattr(r, "url_main", ""),
                            "url_user": getattr(r, "url_user", ""),
                            "status": getattr(r, "status", "Claimed"),
                            "http_status": getattr(r, "http_status", ""),
                            "query_time": getattr(r, "query_time", None),
                            "context": getattr(r, "context", None),
                            "tags": getattr(r, "tags", []),
                            "ids_data": getattr(r, "ids_data", None),
                            "error_type": getattr(r, "error_type", None),
                            "error_hint": getattr(r, "error_hint", ""),
                            "protection": getattr(r, "protection", []),
                            "badge": getattr(r, "badge", ""),
                            "keyword_hit": getattr(r, "keyword_hit", False),
                        }
                        for r in getattr(prog, "found", [])
                    ],
                    "not_found": [
                        {
                            "site_name": getattr(r, "site_name", "?"),
                            "url_main": getattr(r, "url_main", ""),
                            "url_user": getattr(r, "url_user", None)
                            or getattr(r, "url_main", ""),
                            "status": getattr(r, "status", "Available"),
                            "error_type": getattr(r, "error_type", None),
                            "error_hint": getattr(r, "error_hint", ""),
                            "protection": getattr(r, "protection", []),
                            "badge": getattr(r, "badge", ""),
                            "keyword_hit": getattr(r, "keyword_hit", False),
                        }
                        for r in getattr(prog, "not_found", [])
                    ],
                    "errors": [
                        {
                            "site_name": getattr(r, "site_name", "?"),
                            "url_main": getattr(r, "url_main", ""),
                            "url_user": getattr(r, "url_user", None)
                            or getattr(r, "url_main", ""),
                            "status": getattr(r, "status", "Error"),
                            "context": getattr(r, "context", None),
                            "error_type": getattr(r, "error_type", None),
                            "error_hint": getattr(r, "error_hint", ""),
                            "protection": getattr(r, "protection", []),
                            "badge": getattr(r, "badge", ""),
                            "keyword_hit": getattr(r, "keyword_hit", False),
                        }
                        for r in getattr(prog, "errors", [])
                    ],
                    "enrichments": dict(state.enrichments or {}),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M"),
                }
            elif mode == MODE_PHONE:
                snapshot = {
                    "query": query,
                    "mode": mode,
                    "total": total,
                    "checked": total,
                    "phone_results": list(state.phone_results or []),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M"),
                }
            else:
                snapshot = {
                    "query": query,
                    "mode": mode,
                    "total": total,
                    "checked": total,
                    "email_results": list(state.email_results or []),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M"),
                }
            state.set_cached_result(mode, query, snapshot)
            if self.storage:
                await self.storage.set(
                    STORAGE_CACHED_RESULTS, json.dumps(state.results_cache)
                )
        except Exception as snap_exc:
            logger.warning("Failed to snapshot search results: %s", snap_exc)

        # 2. Append to history metadata list
        if not self.storage:
            return
        try:
            entry = {
                "query": query,
                "username": query,  # backward compatibility
                "mode": mode,
                "found": found,
                "total": total,
                "timestamp": time.strftime("%Y-%m-%d %H:%M"),
            }
            # The whole read-modify-write runs under the history lock so the
            # primary-done bridge and the final save can't interleave.
            async with self._history_lock:
                # Work in the STORED order (oldest-first). load_history_entries
                # reverses for DISPLAY and must never be used in a writer —
                # that asymmetry is how swipe-delete flipped the order.
                entries = decode_stored_history(await self.storage.get(STORAGE_HISTORY))
                # Upsert across ALL entries: a stale primary-done save from a
                # killed scan can land after a newer save of the same handle,
                # so checking only entries[-1] allowed duplicates.
                match = next(
                    (
                        i
                        for i, e in enumerate(entries)
                        if e.get("query") == entry["query"]
                        and e.get("mode") == entry["mode"]
                    ),
                    None,
                )
                if match is None:
                    entries.append(entry)
                else:
                    entries[match] = entry
                await self.storage.set(STORAGE_HISTORY, encode_history_entries(entries))
            # Observable mirror is newest-first (display order); the
            # stored list stays oldest-first. Loaders must reverse.
            if (
                state.history
                and state.history[0].get("query") == entry["query"]
                and state.history[0].get("mode") == entry["mode"]
            ):
                state.history[0] = entry
            else:
                state.history.insert(0, entry)
                # "New history while you were elsewhere" indicator for the
                # nav badge. Counted, not flagged, so consecutive scans
                # stack — but only for a row that was actually INSERTED.
                # A username scan saves twice (primary-done bridge + the
                # final upsert), and the second save replaces the head row
                # the first one created; incrementing there read the badge
                # as 2 for one scan.
                state.history_unseen = (state.history_unseen or 0) + 1
            if len(state.history) > 50:
                state.history[:] = state.history[:50]
        except Exception as e:
            logger.warning("Failed to save history: %s", e)

    # --- Updates & Announcements --------------------------------------

    async def run_db_health(self) -> dict:
        """Sampled DB-health check (P3-6): probe, persist flags, refresh.

        Flags replace (not accumulate): a fully healthy run clears the
        exclusion list. Results are shown, never silent.
        """
        if not self.sherlock_service:
            return {"error": "engine unavailable"}
        summary = await self.sherlock_service.run_db_health(sample_size=25)
        if summary.get("error"):
            self._show_snack(f"DB health failed: {summary['error']}", duration=10000)
            return summary
        state.unhealthy_sites = list(summary.get("unhealthy") or [])
        if self.storage:
            try:
                await self.storage.set(
                    STORAGE_DB_UNHEALTHY, json.dumps(state.unhealthy_sites)
                )
            except Exception as exc:
                logger.warning("Failed to persist DB health flags: %s", exc)
        if self._controller_methods and self._controller_methods.refresh_sites:
            await self._controller_methods.refresh_sites()
        label = f"DB health: {summary['ok']}/{summary['sample']} OK"
        if summary.get("flagged"):
            label += f" · {summary['flagged']} flagged (excluded from scans)"
        self._show_snack(label, duration=8000)
        return summary

    def open_update_dialog(self) -> None:
        """Open update or announcement dialog using data loaded from version.json."""
        if state.update_available and state.update_data:
            show_update_dialog(self.page, state.update_data)

    async def check_for_updates(self, notify_if_latest: bool = False) -> None:
        """Query version.json on GitHub for updates/announcements."""
        if not self.update_service:
            return
        update_info = await self.update_service.check_for_update()
        if update_info:
            state.update_available = True
            state.update_data = update_info
            state.progress_version += 1
            if update_info.get("mandatory"):
                self.open_update_dialog()
            try:
                self.page.update()
            except Exception:
                pass
        elif notify_if_latest:
            self._show_snack(f"Sherlock v{APP_VERSION} is up to date!")

    # --- Errors -------------------------------------------------------

    def _show_snack(self, message: str, duration: int = 4000) -> None:
        """Best-effort snackbar for user-facing messages."""
        from core.notify import show_snack

        show_snack(self.page, message, duration=duration)

    def on_error(self, e) -> None:
        """Page-level error handler. Best-effort snackbar."""
        logger.error("Page error: %s", getattr(e, "data", e))
        self._show_snack(ERR_GENERIC)

    # --- Connectivity -------------------------------------------------

    async def _init_connectivity(self) -> None:
        """Initial network probe. Until it lands, is_online stays at its
        default (True) so the app opens online."""
        if not self.connectivity:
            return
        try:
            result = await self.connectivity.get_connectivity()
            state.is_online = ft.ConnectivityType.NONE not in result
        except Exception:
            pass

    def _on_connectivity_change(self, e) -> None:
        """Native listener callback for device connectivity changes."""
        was_online = state.is_online
        try:
            types = getattr(e, "connectivity", None) or [getattr(e, "data", None)]
            types = [t for t in types if t is not None]
            if not types:
                return
            state.is_online = ft.ConnectivityType.NONE not in types
        except Exception:
            return
        if was_online and not state.is_online:
            logger.warning("Connectivity lost")
            self._show_snack(MSG_OFFLINE, duration=10000)
        elif not was_online and state.is_online:
            logger.info("Connectivity restored")
            self._show_snack(MSG_ONLINE)

    def _scan_in_progress(self) -> bool:
        """True while any engine is genuinely mid-flight."""
        return bool(
            state.is_searching
            and (
                self._live_username_progress()
                or self._live_email_progress()
                or self._live_phone_progress()
            )
        )

    async def _mount_notifications(self) -> None:
        """Mount the service, then clear any row left by a previous process."""
        await self.scan_notify.mount()
        await self._clear_stale_notification()

    async def _clear_stale_notification(self) -> None:
        """Clear a foreground-service row left by a previous process.

        The sticky FGS can outlive a killed Python process; with no live scan
        behind it, that row would sit in the shade claiming progress forever.
        """
        if state.is_searching:
            return
        try:
            await self.scan_notify.stop_service()
        except Exception as exc:
            logger.debug("Stale notification cleanup failed: %s", exc)

    async def _set_wakelock(self, on: bool) -> None:
        """Keep the screen awake while a scan runs (ft.Wakelock)."""
        wl = self.wakelock
        if wl is None:
            return
        try:
            if on:
                await wl.enable()
            else:
                await wl.disable()
        except Exception as exc:
            logger.debug("Wakelock set(%s) failed: %s", on, exc)

    def _show_results_from_notification(self) -> None:
        """Notification tap / View action: open Results, restoring the scan.

        Works in three states:
        - a scan is live: just navigate (the live progress is already there);
        - the app was backgrounded: navigate immediately;
        - the process was restarted (cold tap): hydrate the newest cached
          snapshot first, then navigate once AppShell has wired its nav.
        Never mutates widgets directly — AppShell owns the view switch.
        """
        if not state.is_searching:
            self._spawn_bg(self._hydrate_last_results(), "notify-hydrate-last")
        self._spawn_bg(self._retry_show_results(), "notify-show-results")

    async def _hydrate_last_results(self) -> None:
        """Cold start only: load the newest cached snapshot into Results."""
        if state.is_searching or state.last_results or self.storage is None:
            return
        try:
            entries = decode_stored_history(await self.storage.get(STORAGE_HISTORY))
        except Exception as exc:
            logger.debug("History read for notification restore failed: %s", exc)
            return
        if not entries:
            return
        last = entries[-1]
        query = str(last.get("query") or "")
        mode = str(last.get("mode") or MODE_USERNAME)
        if query:
            try:
                self.open_cached_result(query, mode)
            except Exception as exc:
                logger.debug("Cached-result restore failed: %s", exc)

    async def _retry_show_results(self) -> None:
        """Navigate once AppShell has injected its real `show_results`.

        A notification tap that launches the app can be replayed before the
        component tree mounts; the ControllerMethods default is a no-op.
        """
        from state.controller_ctx import _noop_sync

        for _ in range(20):
            methods = self._controller_methods
            if methods is not None and methods.show_results is not _noop_sync:
                try:
                    methods.show_results()
                except Exception as exc:
                    logger.warning("show_results failed: %s", exc)
                return
            await asyncio.sleep(0.25)
        logger.info("Notification: Results navigation skipped (no shell)")

    def _notify_permission_denied(self) -> None:
        """A denial must not look like a crash; offer the OS settings route."""
        from core.notify import show_snack
        from core.theme import AppColors

        show_snack(
            self.page,
            "Notifications are off — scans still run, progress stays in the app",
            bgcolor=AppColors.WARNING,
            duration=6000,
            action_label="Settings",
            on_action=lambda _e: spawn(self._open_notification_settings()),
        )

    async def _open_notification_settings(self) -> None:
        try:
            await self.scan_notify.open_settings()
        except Exception as exc:
            logger.warning("open notification settings failed: %s", exc)

    async def _on_lifecycle_change(self, e: ft.AppLifecycleStateChangeEvent) -> None:
        """Re-probe on resume; keep the wake lock in step with a live scan.

        The foreground service keeps the engine alive in the background; the
        wake lock only needs to hold the screen while a scan is running, so
        it is dropped the moment the app is backgrounded and re-armed on
        resume only if a scan is still live.
        """
        if e.state in (ft.AppLifecycleState.RESUME, ft.AppLifecycleState.SHOW):
            await self._set_wakelock(self._scan_in_progress())
        else:
            await self._set_wakelock(False)
        if e.state not in (ft.AppLifecycleState.RESUME, ft.AppLifecycleState.SHOW):
            return
        # "Your scan finished while you were away" — an in-app snackbar on
        # resume, so a scan that completed in the background is not missed.
        summary = getattr(self, "_last_scan_summary", None)
        if summary:
            self._last_scan_summary = None
            mode, target, found = summary
            noun = {
                "username": "accounts",
                "email": "results",
                "phone": "matches",
            }.get(mode, "results")
            try:
                from core.notify import show_snack

                show_snack(
                    self.page,
                    f"Scan finished — {found} {noun} for {target}",
                    duration=8000,
                    action_label="View",
                    # Same safe restore path as a notification tap: hydrate
                    # after a cold start, navigate once the shell is wired.
                    # (The old freeze was the UI loop awaiting the notification
                    # bridge, not this handler — flet dispatches arity-aware.)
                    on_action=lambda _e: self._show_results_from_notification(),
                )
            except Exception as exc:
                logger.warning("Resume snack failed: %s", exc)
        if not self.connectivity:
            return
        try:
            result = await self.connectivity.get_connectivity()
            state.is_online = ft.ConnectivityType.NONE not in result
        except Exception as exc:
            logger.warning("Connectivity probe failed: %s", exc)


async def main(page: ft.Page) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    root_logger = logging.getLogger()
    if in_memory_log_handler not in root_logger.handlers:
        root_logger.addHandler(in_memory_log_handler)
    # Quiet the engine's per-check chatter from the very first log line —
    # impossible to read the console or the in-app terminal otherwise.
    # The Settings troubleshooting toggle and stored preference can lift it.
    set_engine_logs(state.log_engine_logs)

    controller = AppController(page)
    await controller.init()

    page.on_error = controller.on_error

    async def _on_disconnect(e=None):
        with contextlib.suppress(Exception):
            if controller.storage:
                await controller.storage.flush()

    page.on_disconnect = _on_disconnect

    async def _on_close(e=None):
        with contextlib.suppress(Exception):
            if controller.storage:
                # close() cancels the debounce timer then flushes, so the
                # trailing 1s write window is never lost on exit.
                await controller.storage.close()
        with contextlib.suppress(Exception):
            # Do NOT cancel the scan notification on close. The sticky FGS
            # keeps the native service (and its notification) alive so a tap
            # reopens the app on Results — CollabShell/proot behaviour. Only a
            # finished/idle app tears the row down.
            if controller.scan_notify and not controller._scan_in_progress():
                await controller.scan_notify.stop_service()
        with contextlib.suppress(Exception):
            await controller._set_wakelock(False)
        with contextlib.suppress(Exception):
            if controller.ad_service:
                await controller.ad_service.close()
        # Pooled httpx client — logs its own failures at WARNING
        # (no suppression inside close_client).
        from services.http_client import close_client

        with contextlib.suppress(Exception):
            await close_client()

    page.on_close = _on_close


if __name__ == "__main__":
    # Resolve against THIS file's directory, not the working directory.
    # `ft.run` joins a relative assets_dir onto the CWD
    # (.venv/flet/app.py:__get_assets_dir_path, relative_to_cwd=True), and the
    # `flet run` CLI joins `--assets` onto the script dir and then exports it as
    # FLET_ASSETS_DIR (.venv/flet_cli/commands/run.py:resolve_assets_dir) — so a
    # literal "src/assets" here becomes <root>/src/src/assets under the CLI and
    # warns "assets_dir does not exist". Deriving it from __file__ means the
    # same value works whether launched directly, through the CLI, or built.
    _here = Path(__file__).resolve().parent
    ft.run(main, assets_dir=str(_here / "assets"))
