"""AppHeader — single consistent header for every screen (MarkItDown / DDGS pattern).

Top-left:  App icon + optional title/subtitle (History / Settings / Home).
Top-right: Version chip + theme cycle (3 modes) + settings gear + screen-specific actions.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import flet as ft

from core import tokens
from core.constants import APP_VERSION, STORAGE_THEME
from core.state import state as core_state
from core.tasks import spawn
from core.theme import AppColors, is_dark_mode

logger = logging.getLogger("AppHeader")

# Navigation hook for the tiny "Scanning…" pill. AppController.init() sets it
# so the header (shared by every screen) can open Results without each screen
# passing a callback — same pattern as main._AD_SERVICE_REF.
_SCAN_NAV: dict = {}


def set_scan_navigation(show_results: Callable | None) -> None:
    _SCAN_NAV["show_results"] = show_results


def _scan_pill(on_tap: Callable) -> ft.Control:
    """Tiny tappable chip — the ONLY in-app scan indicator.

    No progress, no spinner, no counters: the OS shade owns progress and the
    Cancel action. Tapping it opens the Results screen (proot-distro pattern).
    """
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.RADAR_ROUNDED,
                    size=tokens.ICON_XS,
                    color=AppColors.PRIMARY,
                ),
                ft.Text(
                    "Scanning…",
                    size=tokens.FONT_XS,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.PRIMARY,
                ),
                ft.Icon(
                    ft.Icons.ARROW_FORWARD_ROUNDED,
                    size=tokens.ICON_XS,
                    color=AppColors.PRIMARY,
                ),
            ],
            spacing=tokens.SPACE_XXS,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_SM, top=4, right=tokens.SPACE_SM, bottom=4
        ),
        border_radius=tokens.RADIUS_FULL,
        bgcolor=ft.Colors.with_opacity(tokens.OPACITY_LIGHT, ft.Colors.PRIMARY),
        ink=True,
        on_click=lambda e: on_tap(),
        tooltip="A scan is running — tap to view results",
    )



def _theme_icon(page: ft.Page | None) -> str:
    if page is None or page.theme_mode == ft.ThemeMode.DARK:
        return ft.Icons.DARK_MODE_ROUNDED
    if page.theme_mode == ft.ThemeMode.LIGHT:
        return ft.Icons.LIGHT_MODE_ROUNDED
    return ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED


def _build_version_chip(page: ft.Page | None) -> ft.Control:
    """KTV-style version chip: shows the current version normally, flips to
    an Update pill when a newer build is found. Always opens the update
    dialog (changelog when up to date)."""

    def _open_dialog(e=None):
        if page is not None:
            from components.update_dialog import show_update_dialog

            show_update_dialog(page)

    update_available = core_state.update_available
    if update_available:
        update_data = core_state.update_data or {}
        label = (
            update_data.get("version", "Update")
            if update_data.get("type") != "announcement"
            else "News"
        )
        content = ft.Row(
            controls=[
                ft.Text(
                    f"Update: {label} Available!"
                    if update_data.get("type") != "announcement"
                    else "News",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    color=AppColors.PRIMARY,
                    no_wrap=True,
                ),
                ft.Container(
                    width=6,
                    height=6,
                    border_radius=3,
                    bgcolor=AppColors.PRIMARY,
                ),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return ft.Container(
            content=content,
            padding=ft.Padding(10, 4, 10, 4),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
            border=ft.Border.all(1.5, AppColors.PRIMARY),
            ink=True,
            tooltip="New update available — tap to view",
            on_click=lambda e: _open_dialog(),
        )
    return ft.Container(
        content=ft.Text(
            f"v{APP_VERSION}",
            size=11,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.ON_SURFACE_VARIANT,
            no_wrap=True,
        ),
        padding=ft.Padding(10, 4, 10, 4),
        border_radius=10,
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE_VARIANT),
        ink=True,
        tooltip="What's New — version & changelog",
        on_click=lambda e: _open_dialog(),
    )


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

        # Pooled banner ads capture their glass colours when first built, so a
        # theme swap leaves stale light/dark glass on every banner until the
        # app restarts. clear_banner_pool's own docstring already promises this.
        try:
            from components.banner_ad import clear_banner_pool

            clear_banner_pool()
        except Exception:
            pass

        async def _persist():
            try:
                from services.storage_service import StorageService

                storage = StorageService.for_page(page)
                await storage.set(STORAGE_THEME, mode_str)
            except Exception as ex:
                logger.warning("Failed to persist cycled theme: %s", ex)

        spawn(_persist())
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

    right_controls.append(_build_version_chip(page))

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

    header_row = ft.Row(
        controls=[
            ft.Row(
                left_controls,
                spacing=tokens.SPACE_XS,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                right_controls,
                spacing=tokens.SPACE_XXS,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        # Owner: header must scroll horizontally when extra action
        # buttons make it overflow narrow screens (instead of clipping).
        scroll=ft.ScrollMode.AUTO,
    )

    # While a scan runs the shade owns progress; in-app shows only this pill.
    show_pill = bool(core_state.is_searching and core_state.search_progress)
    pill = None
    if show_pill:
        nav = _SCAN_NAV.get("show_results")
        if nav is not None:
            pill = _scan_pill(nav)

    if pill is not None:
        return ft.Container(
            content=ft.Column(controls=[pill, header_row], spacing=0, tight=True),
            padding=ft.Padding(
                left=tokens.SPACE_LG,
                top=tokens.SPACE_SM,
                right=tokens.SPACE_LG,
                bottom=tokens.SPACE_SM,
            ),
        )
    return ft.Container(
        content=header_row,
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            top=tokens.SPACE_SM,
            right=tokens.SPACE_LG,
            bottom=tokens.SPACE_SM,
        ),
    )
