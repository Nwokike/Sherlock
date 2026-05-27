"""Sherlock — main entry point."""

from __future__ import annotations

import asyncio
import json
import logging
import time

import flet as ft

from core.theme import AppTheme
from core.state import state
from core.constants import STORAGE_THEME, STORAGE_HISTORY
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
    page.favicon = "logo.png"

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
        elif saved_theme == "light":
            page.theme_mode = ft.ThemeMode.LIGHT
        else:
            page.theme_mode = ft.ThemeMode.SYSTEM
    except Exception as e:
        logger.warning("Theme load failed: %s", e)

    page.run_task(ad_service.preload_interstitial)

    if sherlock_service.is_available:
        page.run_task(sherlock_service.load_sites)

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
            entries.append({
                "username": username,
                "found": found,
                "total": total,
                "timestamp": time.strftime("%Y-%m-%d %H:%M"),
            })
            entries = entries[-50:]
            await storage.set(STORAGE_HISTORY, json.dumps(entries))
        except Exception as e:
            logger.warning("Failed to save history: %s", e)

    async def start_search(username: str):
        nonlocal current_search_task, current_results_view

        if current_search_task and not current_search_task.done():
            sherlock_service.cancel()
            current_search_task = None

        try:
            await sherlock_service.load_sites()
        except Exception:
            pass

        state.current_username = username
        state.is_searching = True

        current_results_view = None

        from views.results_view import build_results_view

        progress = type('obj', (object,), {
            'username': username,
            'total_sites': 0,
            'checked_sites': 0,
            'found': [],
            'not_found': [],
            'errors': [],
            'is_running': True,
            'is_cancelled': False,
        })()

        async def _run_search():
            nonlocal current_results_view
            try:
                result = await sherlock_service.search(
                    username=username,
                    on_progress=lambda p: page.run_task(_refresh_view, p),
                )
                state.is_searching = False

                await _save_to_history(
                    username,
                    len(result.found),
                    result.total_sites,
                )

                state.last_results = {
                    r.site_name: r for r in result.found + result.not_found + result.errors
                }
                state.last_results_username = username

                await _refresh_view(result)
                page.update()

            except Exception as e:
                logger.exception("Search failed: %s", e)
                state.is_searching = False
                page.update()

        async def _refresh_view(progress_data):
            nonlocal current_results_view
            page.views.clear()

            view = build_results_view(
                page=page,
                progress=progress_data,
                on_navigate=navigate,
                on_restart=start_search,
                ad_service=ad_service,
            )
            current_results_view = view
            page.views.append(view)

            if progress_data and not progress_data.is_running:
                nb = _build_nav_bar("/history")
                if nb:
                    view.navigation_bar = nb

            page.update()

        current_search_task = page.run_task(_run_search)

        preview = type('obj', (object,), {
            'username': username,
            'total_sites': 0,
            'checked_sites': 0,
            'found': [],
            'not_found': [],
            'errors': [],
            'is_running': True,
            'is_cancelled': False,
        })()

        page.views.clear()
        view = build_results_view(
            page=page,
            progress=preview,
            on_navigate=navigate,
            on_restart=start_search,
            ad_service=ad_service,
        )
        page.views.append(view)
        page.update()

    async def route_change(e=None):
        nonlocal current_search_task, current_results_view

        route = page.route
        logger.info("Route: %s", route)

        if current_search_task and current_search_task.done():
            current_search_task = None

        if route == "/results" and state.is_searching:
            return

        page.views.clear()

        if route == "/home" or route == "/":
            from views.home_view import build_home_view

            view = build_home_view(
                page=page,
                on_navigate=navigate,
                storage=storage,
                ad_service=ad_service,
                on_search=start_search,
            )
            page.views.append(view)

        elif route == "/history":
            from views.history_view import build_history_view

            view = build_history_view(
                page=page,
                on_navigate=navigate,
                on_search=start_search,
                storage=storage,
            )
            page.views.append(view)

        elif route == "/settings":
            from views.settings_view import build_settings_view

            view = build_settings_view(
                page=page,
                storage=storage,
            )
            page.views.append(view)

        else:
            from views.home_view import build_home_view

            view = build_home_view(
                page=page,
                on_navigate=navigate,
                storage=storage,
                ad_service=ad_service,
                on_search=start_search,
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
