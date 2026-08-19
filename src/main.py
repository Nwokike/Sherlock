"""Sherlock — main entry point and AppController.

`AppController` owns the long-lived services (storage, ads, sherlock
search engine) and the AppState observable singleton. It also builds
the `ControllerMethods` dataclass that bridges the controller layer to
the React-style component tree (`AppShell` and its descendants).

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
    ERR_NETWORK,
    MSG_OFFLINE,
    MSG_ONLINE,
    MSG_SEARCH_OFFLINE,
    STORAGE_EXCLUSIONS,
    STORAGE_HISTORY,
    STORAGE_LOCAL_DB,
    STORAGE_MANIFEST,
    STORAGE_NSFW,
    STORAGE_ONBOARDING_DONE,
    STORAGE_SELECTED_SITES,
    STORAGE_THEME,
    STORAGE_TIMEOUT,
)
from core.state import state
from core.theme import AppTheme
from services.ad_service import AdService
from services.sherlock_service import SherlockService
from services.storage_service import StorageService
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
        self.connectivity: ft.Connectivity | None = None
        # Shared controller-methods instance the component tree reads via
        # use_context(ControllerMethodsCtx). AppShell mutates the view-
        # navigation closures in-place; we hand AppShell a reference so
        # our own methods (start_search, etc.) can invoke them too.
        self._controller_methods: ControllerMethods | None = None

    # --- Lifecycle ----------------------------------------------------

    async def init(self) -> None:
        """Configure the page, init services, load state, mount AppShell."""
        logger.info("Starting %s v%s", APP_NAME, APP_VERSION)

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

        # Load saved state
        await self._load_saved_state()

        # Preload interstitial
        self.page.run_task(self.ad_service.preload_interstitial)

        # Load sites if sherlock is available
        if self.sherlock_service.is_available:
            self.page.run_task(self.sherlock_service.load_sites)

        # Check for upstream Sherlock updates
        self.page.run_task(self._check_updates)

        # Mount the React-style component tree
        from app_shell import AppShell

        refresh_sites = (
            self.sherlock_service.load_sites
            if self.sherlock_service.is_available
            else (lambda: asyncio.sleep(0))
        )

        methods = ControllerMethods(
            refresh_sites=refresh_sites,
            start_search=self.start_search,
            cancel_search=self.cancel_search,
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

            manifest_raw = await self.storage.get(STORAGE_MANIFEST)
            state.custom_manifest = manifest_raw if manifest_raw else ""

            onboarding_done = await self.storage.get(STORAGE_ONBOARDING_DONE)
            if onboarding_done == "true":
                state.has_accepted_terms = True
                state.is_first_launch = False
        except Exception as e:
            logger.warning("Settings load failed: %s", e)

    async def _check_updates(self) -> None:
        try:
            if not self.sherlock_service:
                return
            latest = await self.sherlock_service.check_updates()
            if latest:
                state.update_available_version = latest
                logger.info("New Sherlock version available: %s", latest)
        except Exception:
            pass

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

        # Bridge the thread-shed progress callbacks to the event loop
        def _thread_progress(progress):
            self.page.run_task(self._apply_progress, progress)

        try:
            result = await self.sherlock_service.search(
                username=username,
                on_progress=_thread_progress,
                timeout=state.timeout,
            )
            state.is_searching = False
            state.last_results = {
                r.site_name: r
                for r in (result.found + result.not_found + result.errors)
            }
            state.last_results_username = username

            await self._save_to_history(username, len(result.found), result.total_sites)

            # Final progress apply
            await self._apply_progress(result)
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

    async def _apply_progress(self, progress) -> None:
        """Push a search-progress snapshot into observable state."""
        state.search_progress = progress
        state.progress_version += 1

    def cancel_search(self) -> None:
        """Cancel a running search (sync — called from UI)."""
        if self.sherlock_service:
            self.sherlock_service.cancel()

    async def _save_to_history(self, username: str, found: int, total: int) -> None:
        """Append a search entry to persistent history and observable state."""
        if not self.storage:
            return
        try:
            entry = {
                "username": username,
                "found": found,
                "total": total,
                "timestamp": time.strftime("%Y-%m-%d %H:%M"),
            }
            raw = await self.storage.get(STORAGE_HISTORY)
            entries = json.loads(raw) if raw else []
            entries.append(entry)
            entries = entries[-50:]
            await self.storage.set(STORAGE_HISTORY, json.dumps(entries))
            state.history.insert(0, entry)
            if len(state.history) > 50:
                state.history[:] = state.history[:50]
        except Exception as e:
            logger.warning("Failed to save history: %s", e)

    # --- Errors -------------------------------------------------------

    def _show_snack(self, message: str, duration: int = 4000) -> None:
        """Best-effort snackbar for user-facing messages."""
        try:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(message, color=ft.Colors.WHITE),
                bgcolor=ft.Colors.BLACK,
                duration=duration,
            )
            self.page.snack_bar.open = True
            self.page.update()
        except Exception:
            pass

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

    async def _on_lifecycle_change(
        self, e: ft.AppLifecycleStateChangeEvent
    ) -> None:
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
