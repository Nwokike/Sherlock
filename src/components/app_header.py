"""AppHeader — single consistent header for every screen (MarkItDown / DDGS pattern).

Top-left:  App icon + optional title/subtitle (History / Settings / Home).
Top-right: Theme cycle (3 modes: dark→light→system) + settings gear + screen-specific actions.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

import flet as ft

from core import tokens
from core.constants import STORAGE_THEME
from core.theme import is_dark_mode

logger = logging.getLogger("AppHeader")


def _theme_icon(page: ft.Page | None) -> str:
    if page is None or page.theme_mode == ft.ThemeMode.DARK:
        return ft.Icons.DARK_MODE_ROUNDED
    if page.theme_mode == ft.ThemeMode.LIGHT:
        return ft.Icons.LIGHT_MODE_ROUNDED
    return ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED


def AppHeader(
    page: ft.Page | None,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    show_settings: bool = True,
    on_settings: Callable | None = None,
    extra_actions: list[ft.Control] | None = None,
) -> ft.Container:
    """Standard unified header component across Home, History, and Settings."""

    def _cycle_theme(e):
        if page is None:
            return
        if page.theme_mode == ft.ThemeMode.DARK:
            new_mode = ft.ThemeMode.LIGHT
            mode_str = "light"
        elif page.theme_mode == ft.ThemeMode.LIGHT:
            new_mode = ft.ThemeMode.SYSTEM
            mode_str = "system"
        else:
            new_mode = ft.ThemeMode.DARK
            mode_str = "dark"

        page.theme_mode = new_mode
        # Bump observable so AppShell chrome re-syncs greedily (Asase pattern)
        try:
            from core.state import state

            state.theme_mode = new_mode
            state.progress_version += 1
        except Exception:
            pass

        async def _persist():
            try:
                from services.storage_service import StorageService

                storage = StorageService(page)
                await storage.set(STORAGE_THEME, mode_str)
            except Exception as ex:
                logger.warning("Failed to persist cycled theme: %s", ex)

        asyncio.create_task(_persist())
        try:
            page.update()
        except Exception:
            pass

    # Left: icon + optional title column (KTV Player: use SVG everywhere, MarkItDown: tint white on dark)
    is_dark = is_dark_mode(page)
    left_controls: list[ft.Control] = [
        ft.Container(
            content=ft.Image(
                src="/icon.svg",
                width=32,
                height=32,
                color=ft.Colors.WHITE if is_dark else None,
                fit=ft.BoxFit.CONTAIN,
            ),
            width=32,
            height=32,
            alignment=ft.Alignment.CENTER,
        ),
    ]

    if title:
        title_controls: list[ft.Control] = [
            ft.Text(
                title,
                size=tokens.FONT_LG,
                weight=ft.FontWeight.BOLD,
                font_family="Outfit",
            ),
        ]
        if subtitle:
            title_controls.append(
                ft.Text(
                    subtitle,
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    font_family="Outfit",
                )
            )
        left_controls.append(
            ft.Column(
                controls=title_controls,
                spacing=tokens.SPACE_XXS,
                tight=True,
            )
        )

    # Right controls
    right_controls: list[ft.Control] = []
    if extra_actions:
        right_controls.extend(extra_actions)

    right_controls.append(
        ft.IconButton(
            icon=_theme_icon(page),
            icon_size=tokens.ICON_SM + 2,
            on_click=_cycle_theme,
            tooltip="Toggle theme (Light / Dark / System)",
        )
    )

    if show_settings:
        right_controls.append(
            ft.IconButton(
                icon=ft.Icons.SETTINGS_ROUNDED,
                icon_size=tokens.ICON_SM + 2,
                on_click=on_settings,
                tooltip="Settings",
            )
        )

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Row(
                    left_controls,
                    spacing=tokens.SPACE_SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    right_controls,
                    spacing=tokens.SPACE_XS,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_XL,
            top=tokens.SPACE_SM,
            right=tokens.SPACE_XL,
            bottom=tokens.SPACE_SM,
        ),
    )
