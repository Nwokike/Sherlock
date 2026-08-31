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
    STORAGE_CACHED_SITES,
    STORAGE_EMAIL_TIMEOUT,
    STORAGE_EMAIL_CONCURRENCY,
    STORAGE_EMAIL_ONLY_FOUND,
    STORAGE_EMAIL_METHOD_FILTER,
    STORAGE_ENRICHMENT_MODE,
    STORAGE_EXCLUSIONS,
    STORAGE_HISTORY,
    STORAGE_LOCAL_DB,
    STORAGE_MANIFEST,
    STORAGE_NO_PASSWORD_RECOVERY,
    STORAGE_NSFW,
    STORAGE_ONBOARDING_DONE,
    STORAGE_PROXY_URL,
    STORAGE_SEARCH_MODE,
    STORAGE_SELECTED_SITES,
    STORAGE_THEME,
    STORAGE_TIMEOUT,
)
from core.state import state
from core.theme import AppTheme
from components.update_dialog import show_update_dialog
from services.ad_service import AdService
from services.email_service import EmailService
from services.enrich_service import EnrichService
from services.sherlock_service import SherlockService
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

    # --- Lifecycle ----------------------------------------------------

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
                state.email_timeout = int(email_timeout_raw)

            conc_raw = await self.storage.get(STORAGE_EMAIL_CONCURRENCY)
            if conc_raw:
                state.email_concurrency = max(5, min(30, int(conc_raw)))
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
                state.enrichment_mode = enrich_mode_raw

            no_pw_raw = await self.storage.get(STORAGE_NO_PASSWORD_RECOVERY)
            if no_pw_raw is not None:
                state.no_password_recovery = no_pw_raw == "true"

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

        # Offline gate — don't launch a 400-site scan that can only
        # produce timeouts. History/settings still work offline.
        if not state.is_online:
            logger.info("Search blocked: device offline")
            self._show_snack(MSG_SEARCH_OFFLINE, duration=10000)
            return

        state.current_username = username
        state.is_searching = True
        state.search_error = None

        # Preload interstitial
        if self.ad_service:
            with contextlib.suppress(Exception):
                await self.ad_service.show_interstitial()

        # Make sure sites are loaded before searching
        try:
            await self.sherlock_service.load_sites()
        except Exception:
            pass

        # Bridge the thread-shed progress callbacks onto the main loop
        try:
            result = await self.sherlock_service.search(
                username=username,
                on_progress=self._progress_from_thread,
                timeout=state.timeout,
            )
            state.is_searching = False
            state.last_results = {
                r.site_name: r
                for r in (result.found + result.not_found + result.errors)
            }
            state.last_results_username = username

            await self._save_to_history(
                username, len(result.found), result.total_sites, mode=MODE_USERNAME
            )

            # Final progress apply
            await self._apply_progress(result)

            # Auto-enrich claimed profiles with socid-extractor
            if (
                self.enrich_service
                and self.enrich_service.is_available
                and result.found
            ):
                claimed_urls = [r.url_user for r in result.found if r.url_user]
                if claimed_urls:

                    def _on_enriched_profile(url: str, data: dict):
                        state.set_enrichment(url, data)
                        state.progress_version += 1
                        try:
                            self.page.update()
                        except Exception:
                            pass

                    async def _enrich_task():
                        use_mutations = getattr(state, "enrichment_mode", "basic") == "full"
                        await self.enrich_service.batch_enrich(
                            claimed_urls,
                            timeout=8 if use_mutations else 6,
                            on_result=_on_enriched_profile,
                            max_concurrent=3 if use_mutations else 4,
                            use_mutations=use_mutations,
                        )

                    self.page.run_task(_enrich_task)
        except Exception as e:
            logger.exception("Search failed")
            state.is_searching = False
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

    def _progress_from_thread(self, progress) -> None:
        """Bridge a scan-worker progress tick onto the main event loop.

        The sherlock scan runs in a worker thread; its callbacks must be
        scheduled onto the loop captured at init. page.run_task is NOT
        usable here: it evaluates `self.session.connection.loop` from the
        worker thread (no running loop there), raises, and drops the
        already-created coroutine — surfacing as
        "coroutine '_apply_progress' was never awaited" and silently
        killing live result ticking.
        """
        if not self._main_loop:
            logger.warning("No main loop captured; progress tick dropped")
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._apply_progress(progress), self._main_loop
            )
        except Exception as e:
            logger.warning("Progress dispatch failed: %s", e)

    async def _apply_progress(self, progress) -> None:
        """Push a search-progress snapshot into observable state."""
        state.search_progress = progress
        state.progress_version += 1

    def cancel_search(self) -> None:
        """Cancel a running search (sync — called from UI)."""
        if self.sherlock_service:
            self.sherlock_service.cancel()

    # --- Email Search -------------------------------------------------

    async def start_email_search(self, email: str) -> None:
        """Run a holehe email OSINT search with optional enrichment."""
        if not self.email_service or not self.email_service.is_available:
            self._show_snack("Email search is not available.")
            return

        # Offline gate
        if not state.is_online:
            logger.info("Email search blocked: device offline")
            self._show_snack(MSG_SEARCH_OFFLINE, duration=10000)
            return

        # Validate email
        from services.email_service import validate_email

        if not validate_email(email.strip()):
            self._show_snack(ERR_INVALID_EMAIL)
            return

        state.current_username = email.strip()
        state.is_searching = True
        state.search_error = None
        state.email_results.clear()

        # Preload interstitial
        if self.ad_service:
            with contextlib.suppress(Exception):
                await self.ad_service.show_interstitial()

        try:
            result = await self.email_service.search(
                email=email.strip(),
                on_progress=self._email_progress_callback,
                timeout=state.email_timeout,
                skip_password_recovery=state.no_password_recovery,
                concurrency=getattr(state, "email_concurrency", 15),
            )
            state.is_searching = False

            # Convert to result list for state
            all_results = []
            for r in result.found + result.not_found + result.rate_limited:
                all_results.append(
                    {
                        "name": r.name,
                        "domain": r.domain,
                        "method": r.method,
                        "exists": r.exists,
                        "rateLimit": r.rate_limit,
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

            # Final progress apply
            await self._apply_progress(result)
        except ValueError as ve:
            state.is_searching = False
            self._show_snack(str(ve))
        except Exception as e:
            logger.exception("Email search failed")
            state.is_searching = False
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

    def _email_progress_callback(self, progress) -> None:
        """Bridge email search progress to observable state."""
        if not self._main_loop:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._apply_progress(progress), self._main_loop
            )
        except Exception:
            pass

    def cancel_email_search(self) -> None:
        """Cancel a running email search (sync — called from UI)."""
        if self.email_service:
            self.email_service.cancel()

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

    async def _save_to_history(
        self, query: str, found: int, total: int, mode: str = MODE_USERNAME
    ) -> None:
        """Append a search entry to persistent history and observable state."""
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
