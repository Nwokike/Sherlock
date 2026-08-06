"""SettingsScreen — search parameters, theme, and database updates.

@ft.component — reads/writes observable state via AppStateCtx.
Premium settings with grouped cards, modern switches, and clear hierarchy.
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft
from flet import Control

from core.styles import build_banner_ad
from components.section_header import SectionHeader
from core import tokens
from core.constants import (
    APP_NAME,
    APP_VERSION,
    STORAGE_EXCLUSIONS,
    STORAGE_LOCAL_DB,
    STORAGE_MANIFEST,
    STORAGE_NSFW,
    STORAGE_THEME,
    STORAGE_TIMEOUT,
)
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("SettingsScreen")


def _setting_row(
    icon: ft.IconData,
    title: str,
    subtitle: str,
    trailing: Control,
) -> ft.Container:
    """Reusable settings row with icon + text + trailing control."""
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(
                        icon,
                        size=tokens.ICON_MD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    width=tokens.ICON_BACKDROP,
                    height=tokens.ICON_BACKDROP,
                    border_radius=tokens.ICON_BACKDROP_RADIUS,
                    bgcolor=ft.Colors.with_opacity(
                        tokens.OPACITY_LIGHT, ft.Colors.ON_SURFACE
                    ),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            title,
                            size=tokens.FONT_MD,
                            weight=ft.FontWeight.W_500,
                        ),
                        ft.Text(
                            subtitle,
                            size=tokens.FONT_XS,
                            color=ft.Colors.with_opacity(
                                tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                            ),
                        ),
                    ],
                    spacing=tokens.SPACE_XXS,
                    expand=True,
                ),
                trailing,
            ],
            spacing=tokens.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_MD,
        ),
    )


def _settings_card(controls: list[Control]) -> ft.Container:
    """Grouped settings card with Material 3 surface."""
    return ft.Container(
        content=ft.Column(controls=controls, spacing=0),
        margin=ft.Margin(tokens.SPACE_XL, 0, tokens.SPACE_XL, tokens.SPACE_SM),
        border_radius=tokens.RADIUS_LG,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(
            width=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )


@ft.component
def SettingsScreen() -> Control:
    from flet import context

    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = context.page

    async def _on_theme_change(val: str):
        from flet import context

        page = context.page
        if val == "system":
            new_mode = ft.ThemeMode.SYSTEM
        elif val == "light":
            new_mode = ft.ThemeMode.LIGHT
        else:
            new_mode = ft.ThemeMode.DARK
        page.theme_mode = new_mode
        state.theme_mode = new_mode
        from services.storage_service import StorageService

        storage = StorageService(page)
        await storage.set(STORAGE_THEME, val)

    def _toggle_nsfw(val: bool):
        state.nsfw_enabled = val
        asyncio.create_task(_persist(STORAGE_NSFW, "true" if val else "false"))
        if controller.refresh_sites:
            asyncio.create_task(controller.refresh_sites())

    def _toggle_exclusions(val: bool):
        state.ignore_exclusions = val
        asyncio.create_task(_persist(STORAGE_EXCLUSIONS, "true" if val else "false"))
        if controller.refresh_sites:
            asyncio.create_task(controller.refresh_sites())

    def _toggle_local_db(val: bool):
        state.use_local_db = val
        asyncio.create_task(_persist(STORAGE_LOCAL_DB, "true" if val else "false"))
        if controller.refresh_sites:
            asyncio.create_task(controller.refresh_sites())

    def _on_manifest_change(val: str):
        state.custom_manifest = val
        asyncio.create_task(_persist(STORAGE_MANIFEST, val))
        if controller.refresh_sites:
            asyncio.create_task(controller.refresh_sites())

    def _on_timeout_change(val: str):
        state.timeout = int(val)
        asyncio.create_task(_persist(STORAGE_TIMEOUT, val))

    async def _persist(key: str, value: str):
        from flet import context
        from services.storage_service import StorageService

        storage = StorageService(context.page)
        await storage.set(key, value)

    # ─── Cards ──────────────────────────────────────────────────────────

    # Preferences
    preferences_card = _settings_card(
        [
            _setting_row(
                ft.Icons.COLOR_LENS_ROUNDED,
                "App Theme",
                "Choose between System, Light, or Dark",
                ft.Dropdown(
                    value=(
                        state.theme_mode.value.capitalize()
                        if isinstance(state.theme_mode, ft.ThemeMode)
                        else "System"
                    ),
                    options=[
                        ft.DropdownOption("System", "System"),
                        ft.DropdownOption("Light", "Light"),
                        ft.DropdownOption("Dark", "Dark"),
                    ],
                    width=110,
                    height=44,
                    text_size=tokens.FONT_SM,
                    border_radius=tokens.RADIUS_SM,
                    focused_border_color=ft.Colors.PRIMARY,
                    on_select=lambda e: asyncio.create_task(
                        _on_theme_change(e.control.value)
                    ),
                    content_padding=4,
                ),
            ),
        ]
    )

    # Scan Parameters
    scan_card = _settings_card(
        [
            _setting_row(
                ft.Icons.BLOCK_ROUNDED,
                "Include NSFW Sites",
                "Include adult/NSFW networks in scans",
                ft.Switch(
                    value=state.nsfw_enabled,
                    on_change=lambda e: _toggle_nsfw(e.control.value),
                    active_color=ft.Colors.PRIMARY,
                ),
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.SHIELD_ROUNDED,
                "Ignore Exclusions",
                "Scans exclusions list (may increase false positives)",
                ft.Switch(
                    value=state.ignore_exclusions,
                    on_change=lambda e: _toggle_exclusions(e.control.value),
                    active_color=ft.Colors.PRIMARY,
                ),
            ),
        ]
    )

    # Performance
    performance_card = _settings_card(
        [
            _setting_row(
                ft.Icons.FLASH_ON_ROUNDED,
                "Fast Offline Scan",
                "Load local network list instantly without internet",
                ft.Switch(
                    value=state.use_local_db,
                    on_change=lambda e: _toggle_local_db(e.control.value),
                    active_color=ft.Colors.PRIMARY,
                ),
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.TIMER_OUTLINED,
                "Request Timeout",
                "Maximum connection wait time per site",
                ft.Dropdown(
                    value=str(state.timeout),
                    options=[
                        ft.DropdownOption("5", "5s"),
                        ft.DropdownOption("10", "10s"),
                        ft.DropdownOption("15", "15s"),
                        ft.DropdownOption("30", "30s"),
                        ft.DropdownOption("60", "60s"),
                    ],
                    width=80,
                    height=44,
                    text_size=tokens.FONT_SM,
                    border_radius=tokens.RADIUS_SM,
                    focused_border_color=ft.Colors.PRIMARY,
                    on_select=lambda e: _on_timeout_change(e.control.value),
                    content_padding=4,
                ),
            ),
        ]
    )

    # Custom Manifest
    manifest_card = _settings_card(
        [
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Icon(
                                ft.Icons.FOLDER_OPEN_ROUNDED,
                                size=tokens.ICON_MD,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            width=36,
                            height=36,
                            border_radius=18,
                            bgcolor=ft.Colors.with_opacity(
                                tokens.OPACITY_LIGHT, ft.Colors.ON_SURFACE
                            ),
                            alignment=ft.Alignment.CENTER,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "Custom Manifest",
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                ),
                                ft.Text(
                                    "JSON URL or local path",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.with_opacity(
                                        tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                                    ),
                                ),
                            ],
                            spacing=tokens.SPACE_XXS,
                            expand=True,
                        ),
                    ],
                    spacing=tokens.SPACE_MD,
                ),
                padding=ft.Padding(
                    left=tokens.SPACE_LG,
                    right=tokens.SPACE_LG,
                    top=tokens.SPACE_MD,
                    bottom=tokens.SPACE_SM,
                ),
            ),
            ft.Container(
                content=ft.TextField(
                    value=state.custom_manifest,
                    hint_text="https://raw.githubusercontent.com/.../data.json",
                    border_radius=tokens.RADIUS_SM,
                    text_size=tokens.FONT_SM,
                    content_padding=tokens.SPACE_SM,
                    focused_border_color=ft.Colors.PRIMARY,
                    bgcolor=ft.Colors.SURFACE,
                    filled=True,
                    border_width=1,
                    border_color=ft.Colors.with_opacity(
                        tokens.OPACITY_MEDIUM, ft.Colors.OUTLINE
                    ),
                    on_change=lambda e: _on_manifest_change(e.control.value),
                ),
                padding=ft.Padding(
                    left=tokens.SPACE_LG,
                    right=tokens.SPACE_LG,
                    bottom=tokens.SPACE_MD,
                ),
            ),
        ]
    )

    # About
    about_card = _settings_card(
        [
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Image(
                            src="icon.png",
                            width=48,
                            height=48,
                            border_radius=tokens.RADIUS_MD,
                        ),
                        ft.Container(height=tokens.SPACE_SM),
                        ft.Text(
                            APP_NAME,
                            size=tokens.FONT_LG,
                            weight=ft.FontWeight.W_700,
                            color=ft.Colors.ON_SURFACE,
                        ),
                        ft.Text(
                            f"Version {APP_VERSION}",
                            size=tokens.FONT_SM,
                            color=ft.Colors.with_opacity(
                                tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                            ),
                        ),
                        ft.Container(height=tokens.SPACE_XS),
                        ft.Text(
                            "A user-friendly UI for the\nopen-source Sherlock Project.",
                            size=tokens.FONT_SM,
                            color=ft.Colors.with_opacity(
                                tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                            ),
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=0,
                ),
                padding=ft.Padding(
                    left=tokens.SPACE_LG,
                    right=tokens.SPACE_LG,
                    top=tokens.SPACE_XL,
                    bottom=tokens.SPACE_XL,
                ),
                alignment=ft.Alignment.CENTER,
            ),
        ]
    )

    content = ft.ListView(
        controls=[
            ft.Container(height=tokens.SPACE_SM),
            SectionHeader("PREFERENCES"),
            preferences_card,
            build_banner_ad(page),
            SectionHeader("SCAN PARAMETERS"),
            scan_card,
            build_banner_ad(page),
            SectionHeader("CONNECTION & SPEED"),
            performance_card,
            build_banner_ad(page),
            SectionHeader("CUSTOM MANIFEST"),
            manifest_card,
            build_banner_ad(page),
            SectionHeader("ABOUT"),
            about_card,
            ft.Container(height=tokens.SPACE_XXXL),
        ],
        spacing=0,
        expand=True,
    )

    return ft.Column(
        controls=[content],
        expand=True,
        spacing=0,
    )
