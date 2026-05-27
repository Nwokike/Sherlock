"""Settings view — theme, about, credits."""

from __future__ import annotations

import logging
from typing import Callable

import flet as ft

from core import tokens
from core.constants import APP_NAME, APP_VERSION
from core.state import state
from core.theme import AppColors
from core.styles import setting_tile, section_header

logger = logging.getLogger(__name__)


def build_settings_view(
    page: ft.Page,
    storage,
) -> ft.View:
    theme_icon = ft.Ref[ft.Icon]()

    async def _toggle_theme(e):
        is_dark = page.theme_mode == ft.ThemeMode.DARK or (
            page.theme_mode == ft.ThemeMode.SYSTEM
            and page.platform_brightness == ft.Brightness.DARK
        )
        new_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        page.theme_mode = new_mode
        state.theme_mode = new_mode

        if storage:
            from core.constants import STORAGE_THEME
            await storage.set(
                STORAGE_THEME,
                "light" if new_mode == ft.ThemeMode.LIGHT else "dark",
            )

        if theme_icon.current:
            theme_icon.current.name = (
                ft.Icons.LIGHT_MODE_ROUNDED if is_dark else ft.Icons.DARK_MODE_ROUNDED
            )
        page.update()

    def _get_theme_label() -> str:
        is_dark = page.theme_mode == ft.ThemeMode.DARK or (
            page.theme_mode == ft.ThemeMode.SYSTEM
            and page.platform_brightness == ft.Brightness.DARK
        )
        return "Dark Mode" if not is_dark else "Light Mode"

    def _get_theme_subtitle() -> str:
        is_dark = page.theme_mode == ft.ThemeMode.DARK or (
            page.theme_mode == ft.ThemeMode.SYSTEM
            and page.platform_brightness == ft.Brightness.DARK
        )
        return "Switch to light theme" if is_dark else "Switch to dark theme"

    is_dark = page.theme_mode == ft.ThemeMode.DARK or (
        page.theme_mode == ft.ThemeMode.SYSTEM
        and page.platform_brightness == ft.Brightness.DARK
    )

    appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK_ROUNDED,
            on_click=lambda e: _go_back(),
        ),
        title=ft.Text("Settings", size=tokens.FONT_LG, weight=ft.FontWeight.W_600),
        center_title=False,
        bgcolor=ft.Colors.TRANSPARENT,
    )

    def _go_back():
        from views.home_view import build_home_view
        view = build_home_view(
            page=page,
            on_navigate=lambda r: page.go(r),
            storage=storage,
            ad_service=None,
            on_search=lambda u: None,
        )
        page.views.pop()
        page.views.append(view)
        page.go("/home")

    content = ft.ListView(
        controls=[
            ft.Container(height=tokens.SPACE_SM),
            section_header("PREFERENCES"),
            setting_tile(
                icon=ft.Icons.DARK_MODE_ROUNDED if not is_dark else ft.Icons.LIGHT_MODE_ROUNDED,
                title=_get_theme_label(),
                subtitle=_get_theme_subtitle(),
                on_click=lambda e: page.run_task(_toggle_theme),
            ),
            ft.Divider(height=1, color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
            ft.Container(height=tokens.SPACE_XL),
            section_header("ABOUT"),
            setting_tile(
                icon=ft.Icons.INFO_OUTLINE_ROUNDED,
                title=f"{APP_NAME} v{APP_VERSION}",
                subtitle=f"ng.kiri.sherlock",
            ),
            setting_tile(
                icon=ft.Icons.CODE_ROUNDED,
                title="Built with Flet 0.85",
                subtitle="Python → Flutter → Android",
            ),
            setting_tile(
                icon=ft.Icons.SHIELD_OUTLINED,
                title="Privacy First",
                subtitle="All searches run directly from your device",
            ),
            ft.Divider(height=1, color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
            ft.Container(height=tokens.SPACE_XXL),
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Powered by Sherlock Project",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            "sherlock-project/sherlock",
                            size=tokens.FONT_XS,
                            color=ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE),
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            "© 2026 Kiri. All rights reserved.",
                            size=tokens.FONT_XXS,
                            color=ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE),
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=tokens.SPACE_XXL,
            ),
        ],
        spacing=0,
        expand=True,
    )

    view = ft.View(
        route="/settings",
        controls=[content],
        appbar=appbar,
        padding=0,
        spacing=0,
    )

    return view
