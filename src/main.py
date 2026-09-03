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
from typing import Any

import flet as ft

from core.constants import (
    APP_NAME,
    APP_VERSION,
    ERR_GENERIC,
    ERR_INVALID_EMAIL,
    ERR_NETWORK,
    MODE_EMAIL,
    MODE_USERNAME,
    MSG_OFFLINE,
    MSG_ONLINE,
    MSG_SEARCH_OFFLINE,
    STORAGE_CACHED_RESULTS,
    STORAGE_CACHED_SITES,
    STORAGE_DNS_RESOLVER,
    STORAGE_EMAIL_CONCURRENCY,
    STORAGE_EMAIL_METHOD_FILTER,
    STORAGE_EMAIL_ONLY_FOUND,
    STORAGE_EMAIL_TIMEOUT,
    STORAGE_ENRICHMENT_MODE,
    STORAGE_EXCLUSIONS,
    STORAGE_EXTRACT_INFO,
    STORAGE_HISTORY,
    STORAGE_LOCAL_DB,
    STORAGE_MANIFEST,
    STORAGE_MAX_CONNECTIONS,
    STORAGE_NO_PASSWORD_RECOVERY,
    STORAGE_NSFW,
    STORAGE_ONBOARDING_DONE,
    STORAGE_PROXY_URL,
    STORAGE_RECURSIVE_SEARCH,
    STORAGE_RETRIES,
    STORAGE_SAFE_SEARCH,
    STORAGE_SCAN_DEPTH,
    STORAGE_SEARCH_MODE,
    STORAGE_SELECTED_SITES,
    STORAGE_THEME,
    STORAGE_TIMEOUT,
    STORAGE_USE_CURL_CFFI,
)
from core.logger_handler import in_memory_log_handler
from core.state import state
from core.theme import AppTheme
from components.update_dialog import show_update_dialog
from services.ad_service import AdService
from services.email_service import EmailResult, EmailSearchProgress, EmailService
from services.enrich_service import EnrichService
from services.sherlock_service import SearchProgress, SherlockService, SiteResult
from services.storage_service import StorageService
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
        self.sherlock_service: SherlockService | None = None
        self.email_service: EmailService | None = None
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
        # Handle of the in-flight search task (the home-screen `_run`
        # task awaiting start_search/start_email_search) — cancelled
        # instantly when a new search supersedes it.
        self._search_task: asyncio.Task | None = None
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

        Note: the sherlock scan runs on a worker thread whose queued
        HTTP requests cannot be interrupted (sherlock-project submits all
        site checks upfront) — the drain continues in background, but the
        collector stops ticking the moment the cancel event is set, so
        no state or UI is affected.
        """
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None

        killed = []
        if self._enrich_worker_task and not self._enrich_worker_task.done():
            self._enrich_worker_task.cancel()
            killed.append("enrich-worker")
        self._enrich_queue = None
        if self._render_flush_task and not self._render_flush_task.done():
            self._render_flush_task.cancel()
            killed.append("render-flusher")
        self._render_flush_task = None
        if hasattr(self.sherlock_service, "cancel"):
            self.sherlock_service.cancel()
            killed.append("sherlock-engine")
        if hasattr(self.email_service, "cancel"):
            self.email_service.cancel()
            killed.append("email-engine")
        if (
            self._search_task
            and self._search_task is not current
            and not self._search_task.done()
        ):
            self._search_task.cancel()
            killed.append("search-task")
        state.is_searching = False
        logger.info("KILL %s → cancelled: %s", reason, ", ".join(killed) or "nothing")

    def _register_search_task(self) -> None:
        """Register the calling task as the active search (killable)."""
        self._search_task = asyncio.current_task()
        self._start_render_flusher()

    def _start_render_flusher(self) -> None:
        """Start the single render-budget flusher for this search cycle."""
        if self._render_flush_task and not self._render_flush_task.done():
            return
        self._render_dirty = False
        self._pending_enrichments = {}
        self._render_flush_task = asyncio.create_task(self._render_flusher())

    async def _render_flusher(self) -> None:
        """The ONLY progress_version bumper during a scan (~2Hz max).

        Every bump invalidates every use_context(AppStateCtx) component and
        re-renders + re-diffs + re-encodes the whole tree on the main loop —
        Flet 0.86.5 has zero internal batching (session.py __updates_scheduler
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

    async def init(self) -> None:
        """Configure the page, init services, load state, mount AppShell."""
        logger.info("Starting %s v%s", APP_NAME, APP_VERSION)
        self._main_loop = asyncio.get_running_loop()

        self.page.title = APP_NAME
        self.page.padding = 0
        self.page.spacing = 0
        self.page.fonts = {
            "Outfit": (
                "https://fonts.googleapis.com/css2?"
                "family=Outfit:wght@300;400;500;600;700&display=swap"
            )
        }
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
        self.page.run_task(self._init_connectivity)
        self.page.on_app_lifecycle_state_change = self._on_lifecycle_change

        # Init services
        self.storage = StorageService(self.page)
        self.ad_service = AdService(self.page)
        self.sherlock_service = SherlockService()
        self.email_service = EmailService()
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
            save_selected_sites=self.save_selected_sites,
            check_for_updates=self.check_for_updates,
            open_update_dialog=self.open_update_dialog,
            set_onboarding_done=self.set_onboarding_done,
            open_cached_result=self.open_cached_result,
        )
        self._controller_methods = methods
        self.page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))
        logger.info("AppShell mounted successfully")

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

            nsfw_raw = await self.storage.get(STORAGE_NSFW)
            if nsfw_raw is not None:
                state.nsfw_enabled = nsfw_raw == "true"
            else:
                state.nsfw_enabled = True

            excl_raw = await self.storage.get(STORAGE_EXCLUSIONS)
            if excl_raw is not None:
                state.ignore_exclusions = excl_raw == "true"
            else:
                state.ignore_exclusions = False

            timeout_raw = await self.storage.get(STORAGE_TIMEOUT)
            if timeout_raw:
                state.timeout = int(timeout_raw)

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
                        state.sites_total = len(names)
                        state.sites_version += 1
                except Exception:
                    logger.warning("Site cache unreadable; will repopulate on load")

            manifest_raw = await self.storage.get(STORAGE_MANIFEST)
            state.custom_manifest = manifest_raw if manifest_raw else ""

            # Email mode settings
            search_mode_raw = await self.storage.get(STORAGE_SEARCH_MODE)
            if search_mode_raw in (MODE_USERNAME, MODE_EMAIL):
                state.search_mode = search_mode_raw

            email_timeout_raw = await self.storage.get(STORAGE_EMAIL_TIMEOUT)
            if email_timeout_raw:
                val = int(email_timeout_raw)
                # Migration: old default 10 → new default 30
                if val == 10:
                    state.email_timeout = 30
                    await self.storage.set(STORAGE_EMAIL_TIMEOUT, "30")
                else:
                    state.email_timeout = val

            conc_raw = await self.storage.get(STORAGE_EMAIL_CONCURRENCY)
            if conc_raw:
                val = max(5, min(30, int(conc_raw)))
                # Migration: old default 15 → new default 5
                if val == 15:
                    state.email_concurrency = 5
                    await self.storage.set(STORAGE_EMAIL_CONCURRENCY, "5")
                else:
                    state.email_concurrency = val
            only_found_raw = await self.storage.get(STORAGE_EMAIL_ONLY_FOUND)
            if only_found_raw is not None:
                state.email_only_found = only_found_raw == "true"
            method_filter_raw = await self.storage.get(STORAGE_EMAIL_METHOD_FILTER)
            if method_filter_raw in ("all", "register", "login", "recovery"):
                state.email_method_filter = method_filter_raw
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

            rec_raw = await self.storage.get(STORAGE_RECURSIVE_SEARCH)
            if rec_raw is not None:
                state.recursive_search = rec_raw == "true"

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

            safe_raw = await self.storage.get(STORAGE_SAFE_SEARCH)
            if safe_raw is not None:
                state.safe_search = safe_raw == "true"

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

        # SMART RE-ATTACH: If already searching this exact username, attach to live progress
        if (
            state.is_searching
            and state.current_username.strip().lower() == target_clean.lower()
            and state.search_mode == MODE_USERNAME
        ):
            logger.info("Re-attaching to ongoing username search for %r", target_clean)
            if self._controller_methods and self._controller_methods.show_results:
                self._controller_methods.show_results()
            return

        # NEW SEARCH = PRIORITY: kill any prior activity instantly,
        # whether it is still running or just draining its tail.
        self._kill_all_activity(f"username-search[{target_clean}]")
        self._register_search_task()

        # Offline gate — don't launch a 400-site scan that can only
        # produce timeouts. History/settings still work offline.
        if not state.is_online:
            logger.info("Search blocked: device offline")
            self._show_snack(MSG_SEARCH_OFFLINE, duration=10000)
            return

        state.current_username = target_clean
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

        # Interstitial on every search — original v1.4.0 behavior
        if self.ad_service:
            with contextlib.suppress(Exception):
                await self.ad_service.show_interstitial()

        # Initialize streaming real-time enrichment queue & worker task
        self._enriched_seen.clear()
        self._enrich_queue = asyncio.Queue()
        if self.enrich_service and self.enrich_service.is_available:
            self._enrich_worker_task = asyncio.create_task(self._drain_enrich_queue())

        # Make sure sites are loaded before searching
        try:
            await self.sherlock_service.load_sites()
        except Exception as e:
            logger.warning("load_sites failed before scan: %s", e)

        # Bridge the thread-shed progress callbacks onto the main loop
        try:
            result = await self.sherlock_service.search(
                username=username,
                on_progress=self._progress_from_thread,
                timeout=state.timeout,
            )
            # If this scan was cancelled or superseded by another search, do not clobber state
            if (
                getattr(result, "is_cancelled", False)
                or state.current_username != username
                or state.search_mode != MODE_USERNAME
            ):
                logger.info(
                    "WATCHDOG: username search %r cancelled/superseded — ignoring results",
                    username,
                )
                state.is_searching = False
                username_progress.is_running = False
                state.progress_version += 1
                return

            state.is_searching = False
            state.last_results = {
                r.site_name: r
                for r in (result.found + result.not_found + result.errors)
            }
            state.last_results_username = username
            logger.info(
                "WATCHDOG: username search COMPLETE %r — %d/%d checked, %d found",
                username,
                result.checked_sites,
                result.total_sites,
                len(result.found),
            )

            await self._save_to_history(
                username, len(result.found), result.total_sites, mode=MODE_USERNAME
            )

            # Final progress apply (enqueues any remaining found URLs).
            # Explicit bump: the flusher only renders while is_searching,
            # and the final result object may be the live one (silent assign).
            await self._apply_progress(result)
            state.progress_version += 1
        except asyncio.CancelledError:
            logger.info("WATCHDOG: username search %r killed mid-flight", username)
            raise
        except Exception as e:
            if getattr(state, "current_username", None) == username:
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

    async def _drain_enrich_queue(self) -> None:
        """Stream profile enrichment in real-time as sites are found."""
        if not self.enrich_service or not self.enrich_service.is_available:
            return

        use_mutations = getattr(state, "enrichment_mode", "basic") == "full"
        concurrency = 3 if use_mutations else 4
        semaphore = asyncio.Semaphore(concurrency)
        pending_tasks: set[asyncio.Task] = set()

        async def _enrich_single(url: str) -> None:
            async with semaphore:
                try:
                    fn = (
                        self.enrich_service.enrich_url_with_mutations
                        if use_mutations
                        else self.enrich_service.enrich_url
                    )
                    data = await fn(url, timeout=8 if use_mutations else 6)
                    if data:
                        # Batch into the flusher — never bump per URL: every
                        # observable write re-renders the whole tree.
                        self._pending_enrichments[url] = data
                        self._render_dirty = True

                        # Warm the on-device avatar cache in the background once
                        # per found profile (never on the render path).
                        avatar_url = (
                            data.get("image") or data.get("avatar") or data.get("photo")
                        )
                        if (
                            avatar_url
                            and isinstance(avatar_url, str)
                            and avatar_url.startswith("http")
                        ):
                            from services.cache_service import (
                                schedule_avatar_download,
                            )

                            asyncio.create_task(schedule_avatar_download(avatar_url))
                except Exception as exc:
                    logger.warning("Streaming enrichment error for %s: %s", url, exc)

        while (
            state.is_searching
            or (self._enrich_queue and not self._enrich_queue.empty())
            or pending_tasks
        ):
            # Clean up completed tasks
            done = {t for t in pending_tasks if t.done()}
            pending_tasks.difference_update(done)

            if self._enrich_queue and not self._enrich_queue.empty():
                try:
                    url = self._enrich_queue.get_nowait()
                    t = asyncio.create_task(_enrich_single(url))
                    pending_tasks.add(t)
                except Exception:
                    pass
            else:
                await asyncio.sleep(0.1)

        # Final wait for in-flight tasks when scan completes
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

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
            self._main_loop.call_later(
                delay,
                lambda: asyncio.run_coroutine_threadsafe(_flush(), self._main_loop),
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
        the active search's target.
        """
        is_email_progress = hasattr(progress, "checked_modules")
        if is_email_progress and state.search_mode != MODE_EMAIL:
            logger.debug(
                "Dropping email progress tick while in %s mode", state.search_mode
            )
            return
        if not is_email_progress and state.search_mode != MODE_USERNAME:
            logger.debug(
                "Dropping username progress tick while in %s mode", state.search_mode
            )
            return
        if is_email_progress:
            if getattr(progress, "email", None) != state.current_username:
                logger.debug("Dropping stale email progress tick — superseded scan")
                return
        elif (
            state.search_targets
            and state.is_searching
            and getattr(progress, "username", None) not in state.search_targets
        ):
            logger.debug("Dropping stale username progress tick — superseded scan")
            return
        state.search_progress = progress

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

    def cancel_search(self) -> None:
        """Cancel a running search (sync — called from UI)."""
        logger.info("CANCEL requested by user (username mode)")
        self._kill_all_activity("user-cancel[username]")

    # --- Email Search -------------------------------------------------

    async def start_email_search(self, email: str) -> None:
        """Run a holehe email OSINT search with optional enrichment."""
        if not self.email_service or not self.email_service.is_available:
            self._show_snack("Email search is not available.")
            return

        email_clean = email.strip()
        if not email_clean:
            return

        # SMART RE-ATTACH: If already searching this exact email, attach to live progress
        if (
            state.is_searching
            and state.current_username.strip().lower() == email_clean.lower()
            and state.search_mode == MODE_EMAIL
        ):
            logger.info("Re-attaching to ongoing email search for %r", email_clean)
            if self._controller_methods and self._controller_methods.show_results:
                self._controller_methods.show_results()
            return

        # NEW SEARCH = PRIORITY: kill any prior activity instantly,
        # whether it is still running or just draining its tail.
        self._kill_all_activity(f"email-search[{email_clean}]")
        self._register_search_task()

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

        state.current_username = email_clean
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

        # Interstitial on every email search too — same v1.4.0 behavior
        if self.ad_service:
            with contextlib.suppress(Exception):
                await self.ad_service.show_interstitial()

        try:
            result = await self.email_service.search(
                email=email.strip(),
                on_progress=self._progress_from_thread,
                timeout=state.email_timeout,
                skip_password_recovery=state.no_password_recovery,
                concurrency=getattr(state, "email_concurrency", 15),
                method_filter=getattr(state, "email_method_filter", "all"),
                use_curl_cffi=getattr(state, "use_curl_cffi", True),
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
                state.is_searching = False
                email_progress.is_running = False
                state.progress_version += 1
                return

            state.is_searching = False
            logger.info(
                "WATCHDOG: email search COMPLETE %r — %d/%d checked, %d found",
                email,
                result.checked_modules,
                result.total_modules,
                len(result.found),
            )

            # Convert to result list for state
            all_results = []
            for r in (
                result.found
                + result.not_found
                + result.rate_limited
                + result.unavailable
            ):
                all_results.append(
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
                )
            state.email_results[:] = all_results
            state.email_results_address = email.strip()
            state.email_found_count = len(result.found)
            state.email_not_found_count = len(result.not_found)
            state.email_rate_limited_count = len(result.rate_limited)
            state.email_unavailable_count = len(result.unavailable)
            state.email_total_modules = result.total_modules

            # Email enrichment via socid-extractor is intentionally skipped:
            # holehe `r.domain` is a bare domain (e.g. "twitter.com"), not a
            # profile URL. Fetching https://{domain}/ would hit the homepage and
            # never match a socid scheme — wasted batch at 0% hit rate. Keep
            # enrichment only for username mode where we have real profile URLs.

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
        except asyncio.CancelledError:
            logger.info("WATCHDOG: email search %r killed mid-flight", email)
            raise
        except ValueError as ve:
            state.is_searching = False
            email_progress.is_running = False
            state.progress_version += 1
            logger.warning("Email search rejected: %s", ve)
            self._show_snack(str(ve))
        except Exception as e:
            logger.exception("Email search failed")
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

    def cancel_email_search(self) -> None:
        """Cancel a running email search (sync — called from UI)."""
        logger.info("CANCEL requested by user (email mode)")
        self._kill_all_activity("user-cancel[email]")

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

    def open_cached_result(self, query: str, mode: str) -> bool:
        """Open past results from cache instantly without re-scanning."""
        snapshot = state.get_cached_result(mode, query)
        if not snapshot:
            return False

        # Cancel any active scan if opening a different target
        if (
            state.is_searching
            and state.current_username.strip().lower() != query.strip().lower()
        ):
            self._kill_all_activity(f"open-cached-result[{query}]")

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
            if snapshot.get("enrichments"):
                state.enrichments.update(snapshot["enrichments"])
        else:
            all_email = snapshot.get("email_results", [])
            found_count = len(
                [r for r in all_email if r.get("exists") and not r.get("rateLimit")]
            )
            state.email_results[:] = all_email
            state.email_results_address = query.strip()
            state.current_username = query.strip()
            state.search_mode = MODE_EMAIL
            state.email_found_count = found_count
            state.email_total_modules = snapshot.get("total", len(all_email) or 121)
            state.search_progress = EmailSearchProgress(
                email=query.strip(),
                total_modules=state.email_total_modules,
                checked_modules=state.email_total_modules,
                found=[
                    EmailResult(
                        name=r.get("name", ""),
                        domain=r.get("domain", ""),
                        method=r.get("method", ""),
                        exists=r.get("exists"),
                        rate_limit=r.get("rateLimit", False),
                        frequent_rate_limit=r.get("frequent_rate_limit", False),
                        email_recovery=r.get("emailrecovery"),
                        phone_number=r.get("phoneNumber"),
                        others=r.get("others"),
                    )
                    for r in all_email
                    if r.get("exists") and not r.get("rateLimit")
                ],
                is_running=False,
            )

        state.is_searching = False
        state.progress_version += 1
        if self._controller_methods and self._controller_methods.show_results:
            self._controller_methods.show_results()
        return True

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
                            "tags": getattr(r, "tags", []),
                            "ids_data": getattr(r, "ids_data", None),
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
                        }
                        for r in getattr(prog, "errors", [])
                    ],
                    "enrichments": dict(state.enrichments or {}),
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
            raw = await self.storage.get(STORAGE_HISTORY)
            entries = json.loads(raw) if raw else []
            entries.append(entry)
            entries = entries[-50:]
            await self.storage.set(STORAGE_HISTORY, json.dumps(entries))
            # Observable mirror is newest-first (display order); the
            # stored list stays oldest-first. Loaders must reverse.
            state.history.insert(0, entry)
            if len(state.history) > 50:
                state.history[:] = state.history[:50]
        except Exception as e:
            logger.warning("Failed to save history: %s", e)

    # --- Updates & Announcements --------------------------------------

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
        logger.error("Page error: %s", e.data)
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
            types = getattr(e, "connectivity", None) or [e.data]
            state.is_online = ft.ConnectivityType.NONE not in types
        except Exception:
            return
        if was_online and not state.is_online:
            logger.warning("Connectivity lost")
            self._show_snack(MSG_OFFLINE, duration=10000)
        elif not was_online and state.is_online:
            logger.info("Connectivity restored")
            self._show_snack(MSG_ONLINE)

    async def _on_lifecycle_change(self, e: ft.AppLifecycleStateChangeEvent) -> None:
        """Re-probe on resume — the OS can drop the connection while we're
        backgrounded and the connectivity listener may not fire for it."""
        if e.state not in (ft.AppLifecycleState.RESUME, ft.AppLifecycleState.SHOW):
            return
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
                await controller.storage.flush()
        with contextlib.suppress(Exception):
            if controller.ad_service:
                await controller.ad_service.close()

    page.on_close = _on_close


if __name__ == "__main__":
    ft.run(main, assets_dir="src/assets")
