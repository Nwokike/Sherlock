"""Sherlock — main entry point."""

from __future__ import annotations

import json
import logging
import time

import flet as ft

from core.theme import AppTheme
from core.state import state
from core.constants import (
    STORAGE_THEME,
    STORAGE_HISTORY,
    STORAGE_NSFW,
    STORAGE_EXCLUSIONS,
    STORAGE_TIMEOUT,
    STORAGE_LOCAL_DB,
    STORAGE_SELECTED_SITES,
    STORAGE_ONBOARDING_DONE,
    STORAGE_MANIFEST,
)
from services.storage_service import StorageService
from services.ad_service import AdService
from services.sherlock_service import SherlockService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sherlock")


async def main(page: ft.Page):
    page.title = "Sherlock"
    page.favicon = "icon.png"

    page.fonts = {
        "Outfit": "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap"
    }

    page.theme = AppTheme.get_light_theme()
    page.dark_theme = AppTheme.get_dark_theme()
    page.theme.font_family = "Outfit"
    page.dark_theme.font_family = "Outfit"
    page.theme_mode = ft.ThemeMode.SYSTEM

    page.window.min_width = 360
    page.window.min_height = 600

    page.padding = 0
    page.spacing = 0

    def on_error(e):
        logger.error("Page error: %s", e.data)
        try:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(
                    "Something went wrong. Please try again.", color=ft.Colors.WHITE
                ),
                bgcolor=ft.Colors.BLACK,
            )
            page.snack_bar.open = True
            page.update()
        except Exception:
            pass

    page.on_error = on_error

    storage = StorageService(page)
    ad_service = AdService(page)
    sherlock_service = SherlockService()

    try:
        saved_theme = await storage.get(STORAGE_THEME)
        if saved_theme == "dark":
            page.theme_mode = ft.ThemeMode.DARK
        elif saved_theme == "system":
            page.theme_mode = ft.ThemeMode.SYSTEM
        else:
            page.theme_mode = ft.ThemeMode.LIGHT

        # Load advanced settings
        nsfw_raw = await storage.get(STORAGE_NSFW)
        if nsfw_raw is not None:
            state.nsfw_enabled = nsfw_raw == "true"
        else:
            state.nsfw_enabled = True

        excl_raw = await storage.get(STORAGE_EXCLUSIONS)
        if excl_raw is not None:
            state.ignore_exclusions = excl_raw == "true"
        else:
            state.ignore_exclusions = False

        timeout_raw = await storage.get(STORAGE_TIMEOUT)
        if timeout_raw:
            state.timeout = int(timeout_raw)

        local_db_raw = await storage.get(STORAGE_LOCAL_DB)
        if local_db_raw:
            state.use_local_db = local_db_raw == "true"

        selected_raw = await storage.get(STORAGE_SELECTED_SITES)
        if selected_raw:
            state.selected_sites = selected_raw.split(",")
        else:
            state.selected_sites = []

        manifest_raw = await storage.get(STORAGE_MANIFEST)
        state.custom_manifest = manifest_raw if manifest_raw else ""
    except Exception as e:
        logger.warning("Settings load failed: %s", e)

    page.run_task(ad_service.preload_interstitial)

    if sherlock_service.is_available:
        page.run_task(sherlock_service.load_sites)

    async def check_sherlock_updates():
        try:
            latest = await sherlock_service.check_updates()
            if latest:
                state.update_available_version = latest
                logger.info("New Sherlock version available: %s", latest)
        except Exception:
            pass

    page.run_task(check_sherlock_updates)

    async def on_disconnect(e=None):
        try:
            await storage.flush()
        except Exception:
            pass

    page.on_disconnect = on_disconnect

    current_search_task = None
    current_results_view = None

    async def navigate(route: str):
        page.route = route
        await route_change()

    def navigate_sync(route: str):
        page.run_task(navigate, route)

    def _build_nav_bar(active_route: str) -> ft.NavigationBar | None:
        routes = ["/home", "/history", "/settings"]
        if active_route not in routes:
            return None
        nav_bar = ft.NavigationBar(
            selected_index=routes.index(active_route) if active_route in routes else 0,
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.HOME_OUTLINED,
                    selected_icon=ft.Icons.HOME_ROUNDED,
                    label="Home",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.HISTORY_OUTLINED,
                    selected_icon=ft.Icons.HISTORY_ROUNDED,
                    label="History",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS_ROUNDED,
                    label="Settings",
                ),
            ],
            bgcolor=ft.Colors.SURFACE,
            indicator_color=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
            label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        )

        def on_nav_change(e):
            nonlocal current_search_task
            if current_search_task and not current_search_task.done():
                sherlock_service.cancel()
                current_search_task = None
            index = e.control.selected_index
            page.run_task(navigate, routes[index])

        nav_bar.on_change = on_nav_change
        return nav_bar

    async def _save_to_history(username: str, found: int, total: int):
        try:
            raw = await storage.get(STORAGE_HISTORY)
            entries = json.loads(raw) if raw else []
            entries.append(
                {
                    "username": username,
                    "found": found,
                    "total": total,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M"),
                }
            )
            entries = entries[-50:]
            await storage.set(STORAGE_HISTORY, json.dumps(entries))
        except Exception as e:
            logger.warning("Failed to save history: %s", e)

    async def start_search(username: str):
        nonlocal current_search_task, current_results_view

        if current_search_task and not current_search_task.done():
            sherlock_service.cancel()
            current_search_task = None

        await ad_service.show_interstitial()

        try:
            await sherlock_service.load_sites()
        except Exception:
            pass

        state.current_username = username
        state.is_searching = True

        current_results_view = None

        from views.results_view import build_results_view

        async def _cancel_search():
            nonlocal current_search_task
            if current_search_task and not current_search_task.done():
                sherlock_service.cancel()
                current_search_task = None
            state.is_searching = False
            await navigate("/home")

        async def _run_search():
            nonlocal current_results_view
            try:
                result = await sherlock_service.search(
                    username=username,
                    on_progress=lambda p: page.run_task(_refresh_view, p),
                    timeout=state.timeout,
                )
                state.is_searching = False

                await _save_to_history(
                    username,
                    len(result.found),
                    result.total_sites,
                )

                state.last_results = {
                    r.site_name: r
                    for r in result.found + result.not_found + result.errors
                }
                state.last_results_username = username

                await _refresh_view(result)

                # Check for high error rate (possible misconfigured proxy or network failure)
                if (
                    len(result.found) == 0
                    and len(result.errors) >= 5
                    and len(result.errors) >= 0.5 * result.total_sites
                ):
                    from core.theme import AppColors
                    from core import tokens

                    def _close_alert(evt):
                        page.pop_dialog()

                    title_text = "Connection Issue?"
                    icon = ft.Icons.WIFI_OFF_ROUNDED
                    icon_color = AppColors.ERROR
                    desc = (
                        "All or most of the checks failed with connection errors.\n\n"
                        "This usually happens when:\n"
                        "• Your device is not connected to the internet.\n"
                        "• Your network is blocking outgoing automated requests.\n"
                        "• A VPN or proxy is misconfigured.\n\n"
                        "Please check your network settings."
                    )

                    actions = [ft.TextButton("Dismiss", on_click=_close_alert)]

                    alert = ft.AlertDialog(
                        title=ft.Row(
                            controls=[
                                ft.Icon(icon, color=icon_color, size=24),
                                ft.Text(
                                    title_text,
                                    size=tokens.FONT_LG,
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ],
                            spacing=8,
                        ),
                        content=ft.Container(
                            content=ft.Column(
                                controls=[
                                    ft.Text(
                                        desc,
                                        size=tokens.FONT_SM,
                                        color=ft.Colors.ON_SURFACE,
                                    ),
                                ],
                                tight=True,
                            ),
                            width=320,
                        ),
                        actions=actions,
                        actions_alignment=ft.MainAxisAlignment.END,
                    )
                    page.show_dialog(alert)

                page.update()

            except Exception as e:
                logger.exception("Search failed: %s", e)
                state.is_searching = False
                state.search_error = str(e)
                await navigate("/home")

        async def _refresh_view(progress_data):
            nonlocal current_results_view
            page.views.clear()

            view = build_results_view(
                page=page,
                progress=progress_data,
                on_navigate=navigate_sync,
                on_restart=start_search_sync,
                on_cancel=lambda: page.run_task(_cancel_search),
            )
            current_results_view = view
            page.views.append(view)

            if progress_data and not progress_data.is_running:
                nb = _build_nav_bar("/history")
                if nb:
                    view.navigation_bar = nb

            page.update()

        current_search_task = page.run_task(_run_search)

        preview = type(
            "obj",
            (object,),
            {
                "username": username,
                "total_sites": 0,
                "checked_sites": 0,
                "found": [],
                "not_found": [],
                "errors": [],
                "is_running": True,
                "is_cancelled": False,
            },
        )()

        page.views.clear()
        view = build_results_view(
            page=page,
            progress=preview,
            on_navigate=navigate_sync,
            on_restart=start_search_sync,
            on_cancel=lambda: page.run_task(_cancel_search),
        )
        page.views.append(view)
        page.update()

    def start_search_sync(username: str):
        page.run_task(start_search, username)

    async def route_change(e=None):
        nonlocal current_search_task, current_results_view

        route = page.route
        logger.info("Route: %s", route)

        if current_search_task and current_search_task.done():
            current_search_task = None

        onboarding_done = await storage.get(STORAGE_ONBOARDING_DONE)
        if onboarding_done != "true" and route != "/onboarding":
            await navigate("/onboarding")
            return

        if route == "/results" and state.is_searching:
            return

        page.views.clear()

        if route == "/onboarding":
            from views.onboarding_view import build_onboarding_view

            view = build_onboarding_view(
                page=page,
                on_done=lambda: navigate_sync("/home"),
                storage=storage,
            )
            page.views.append(view)

        elif route == "/home" or route == "/":
            from views.home_view import build_home_view

            view = build_home_view(
                page=page,
                on_navigate=navigate_sync,
                storage=storage,
                on_search=start_search_sync,
            )
            page.views.append(view)

            if state.search_error:
                error_msg = state.search_error
                from core.theme import AppColors
                from core import tokens

                title_text = "Search Failed"
                alert_icon = ft.Icons.ERROR_OUTLINE_ROUNDED
                icon_color = AppColors.ERROR
                description_text = (
                    f"{error_msg}\n\n"
                    "Please check your internet connection or proxy settings."
                )

                def _close_error_alert(evt):
                    state.search_error = None
                    page.pop_dialog()

                actions = [
                    ft.TextButton(
                        "Dismiss",
                        on_click=_close_error_alert,
                    )
                ]

                error_dialog = ft.AlertDialog(
                    title=ft.Row(
                        controls=[
                            ft.Icon(
                                alert_icon,
                                color=icon_color,
                                size=24,
                            ),
                            ft.Text(
                                title_text,
                                size=tokens.FONT_LG,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=8,
                    ),
                    content=ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Text(
                                    description_text,
                                    size=tokens.FONT_SM,
                                    color=ft.Colors.ON_SURFACE,
                                ),
                            ],
                            tight=True,
                            spacing=6,
                        ),
                        width=320,
                    ),
                    actions=actions,
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                page.show_dialog(error_dialog)

        elif route == "/history":
            from views.history_view import build_history_view

            view = build_history_view(
                page=page,
                on_navigate=navigate_sync,
                on_search=start_search_sync,
                storage=storage,
            )
            page.views.append(view)

        elif route == "/settings":
            from views.settings_view import build_settings_view

            view = build_settings_view(
                page=page,
                sherlock_service=sherlock_service,
                storage=storage,
            )
            page.views.append(view)

        elif route == "/sites":
            from views.sites_view import build_sites_view

            view = build_sites_view(
                page=page,
                sherlock_service=sherlock_service,
                storage=storage,
                on_navigate=navigate_sync,
            )
            page.views.append(view)

        else:
            from views.home_view import build_home_view

            view = build_home_view(
                page=page,
                on_navigate=navigate_sync,
                storage=storage,
                on_search=start_search_sync,
            )
            page.views.append(view)

        if page.views:
            nb = _build_nav_bar(route)
            if nb:
                page.views[-1].navigation_bar = nb

        page.update()

    async def view_pop(e):
        nonlocal current_search_task
        if current_search_task and not current_search_task.done():
            sherlock_service.cancel()
            current_search_task = None
        page.views.pop()
        if page.views:
            top = page.views[-1]
            page.route = top.route
        page.update()

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    await navigate("/home")


if __name__ == "__main__":
    ft.run(main, assets_dir="src/assets")
