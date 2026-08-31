"""SettingsScreen — search parameters, theme, and database updates.

@ft.component — reads/writes observable state via AppStateCtx.
Premium settings with grouped cards, modern switches, and clear hierarchy.
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft
from flet import Control

from components.app_header import AppHeader
from components.banner_ad import build_banner_ad
from components.section_header import SectionHeader
from core import tokens
from core.constants import (
    APP_NAME,
    APP_VERSION,
    STORAGE_EMAIL_TIMEOUT,
    STORAGE_EMAIL_CONCURRENCY,
    STORAGE_EMAIL_ONLY_FOUND,
    STORAGE_EMAIL_METHOD_FILTER,
    STORAGE_ENRICHMENT_MODE,
    STORAGE_EXCLUSIONS,
    STORAGE_LOCAL_DB,
    STORAGE_MANIFEST,
    STORAGE_NO_PASSWORD_RECOVERY,
    STORAGE_NSFW,
    STORAGE_PROXY_URL,
    STORAGE_THEME,
    STORAGE_TIMEOUT,
)
from core.theme import AppColors
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
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    from flet import context

    page = context.page

    async def _on_theme_change(val: str):
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
        await storage.flush()
        try:
            page.update()
        except Exception:
            pass

    def _create_theme_card(mode: str, label: str, icon: str):
        is_sel = (
            (mode == "dark" and page.theme_mode == ft.ThemeMode.DARK)
            or (mode == "light" and page.theme_mode == ft.ThemeMode.LIGHT)
            or (mode == "system" and page.theme_mode == ft.ThemeMode.SYSTEM)
        )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        icon,
                        color=AppColors.PRIMARY
                        if is_sel
                        else ft.Colors.ON_SURFACE_VARIANT,
                        size=tokens.ICON_SM + 2,
                    ),
                    ft.Text(
                        label,
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL,
                        color=AppColors.PRIMARY if is_sel else ft.Colors.ON_SURFACE,
                        font_family="Outfit",
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
            ),
            padding=ft.Padding(10, 10, 10, 10),
            border_radius=tokens.RADIUS_MD,
            border=(
                ft.Border.all(2, AppColors.PRIMARY)
                if is_sel
                else ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE))
            ),
            bgcolor=(
                ft.Colors.with_opacity(0.1, AppColors.PRIMARY)
                if is_sel
                else ft.Colors.SURFACE_CONTAINER_HIGHEST
            ),
            expand=True,
            ink=True,
            on_click=lambda e, m=mode: asyncio.create_task(_on_theme_change(m)),
            animate=ft.Animation(150, "easeOut"),
        )

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
        # refresh_sites is debounced via AppController — not per-keystroke.

    def _on_manifest_submit(e):
        val = e.control.value.strip() if e.control.value else ""
        state.custom_manifest = val
        asyncio.create_task(_persist(STORAGE_MANIFEST, val))
        if controller.refresh_sites:
            asyncio.create_task(controller.refresh_sites())

    def _on_timeout_change(val: str):
        state.timeout = int(val)
        asyncio.create_task(_persist(STORAGE_TIMEOUT, val))

    def _on_email_timeout_change(val: str):
        state.email_timeout = int(val)
        asyncio.create_task(_persist(STORAGE_EMAIL_TIMEOUT, val))

    def _on_email_concurrency_change(val: str):
        state.email_concurrency = max(5, min(30, int(val)))
        asyncio.create_task(_persist(STORAGE_EMAIL_CONCURRENCY, val))

    def _toggle_email_only_found(val: bool):
        state.email_only_found = val
        asyncio.create_task(
            _persist(STORAGE_EMAIL_ONLY_FOUND, "true" if val else "false")
        )

    def _on_email_method_filter_change(val: str):
        state.email_method_filter = val
        asyncio.create_task(_persist(STORAGE_EMAIL_METHOD_FILTER, val))

    def _on_proxy_change(val: str):
        state.proxy_url = val.strip()
        asyncio.create_task(_persist(STORAGE_PROXY_URL, val.strip()))

    def _on_enrichment_mode_change(val: str):
        state.enrichment_mode = val
        asyncio.create_task(_persist(STORAGE_ENRICHMENT_MODE, val))

    def _toggle_no_password_recovery(val: bool):
        state.no_password_recovery = val
        asyncio.create_task(
            _persist(STORAGE_NO_PASSWORD_RECOVERY, "true" if val else "false")
        )

    async def _persist(key: str, value: str):
        from flet import context
        from services.storage_service import StorageService

        storage = StorageService(context.page)
        await storage.set(key, value)

    # ─── Cards ──────────────────────────────────────────────────────────

    # Preferences
    preferences_card = _settings_card(
        [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Container(
                                    content=ft.Icon(
                                        ft.Icons.COLOR_LENS_ROUNDED,
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
                                    [
                                        ft.Text(
                                            "App Theme",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        ft.Text(
                                            "Choose between Light, Dark, or System",
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
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [
                                _create_theme_card(
                                    "light", "Light", ft.Icons.LIGHT_MODE_ROUNDED
                                ),
                                _create_theme_card(
                                    "dark", "Dark", ft.Icons.DARK_MODE_ROUNDED
                                ),
                                _create_theme_card(
                                    "system",
                                    "System",
                                    ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED,
                                ),
                            ],
                            spacing=tokens.SPACE_SM,
                        ),
                    ],
                    spacing=tokens.SPACE_MD,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD
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

    # Email Intelligence
    email_card = _settings_card(
        [
            _setting_row(
                ft.Icons.ALTERNATE_EMAIL_ROUNDED,
                "Email Request Timeout",
                "Max wait time per email check (holehe)",
                ft.Slider(
                    value=float(state.email_timeout),
                    min=5,
                    max=30,
                    divisions=5,
                    label=f"{state.email_timeout}s",
                    active_color=AppColors.PRIMARY,
                    on_change=lambda e: _on_email_timeout_change(
                        str(int(e.control.value))
                    ),
                ),
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.SPEED_ROUNDED,
                "Email Concurrency",
                "Parallel checks — higher is faster but rate-limits more",
                ft.Slider(
                    value=float(getattr(state, "email_concurrency", 15)),
                    min=5,
                    max=30,
                    divisions=5,
                    label=f"{getattr(state, 'email_concurrency', 15)}",
                    active_color=AppColors.PRIMARY,
                    on_change=lambda e: _on_email_concurrency_change(
                        str(int(e.control.value))
                    ),
                ),
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.FILTER_ALT_ROUNDED,
                "Show Found Only",
                "Hide not-found platforms in email results",
                ft.Switch(
                    value=getattr(state, "email_only_found", False),
                    on_change=lambda e: _toggle_email_only_found(e.control.value),
                    active_color=ft.Colors.PRIMARY,
                ),
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.PASSWORD_ROUNDED,
                "Skip Password Recovery",
                "Exclude password-recovery checks (faster, fewer hints)",
                ft.Switch(
                    value=state.no_password_recovery,
                    on_change=lambda e: _toggle_no_password_recovery(e.control.value),
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
                ft.Slider(
                    value=float(state.timeout),
                    min=5,
                    max=60,
                    divisions=11,
                    label=f"{state.timeout}s",
                    active_color=AppColors.PRIMARY,
                    on_change=lambda e: _on_timeout_change(str(int(e.control.value))),
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
                    on_submit=_on_manifest_submit,
                ),
                padding=ft.Padding(
                    left=tokens.SPACE_LG,
                    right=tokens.SPACE_LG,
                    bottom=tokens.SPACE_MD,
                ),
            ),
        ]
    )

    # About & Updates
    is_announcement = (
        state.update_available
        and state.update_data
        and state.update_data.get("type") == "announcement"
    )

    update_badge_controls: list[Control] = []
    if state.update_available and state.update_data:
        badge_color = AppColors.ACCENT if is_announcement else AppColors.PRIMARY
        badge_label = (
            "Announcement Available"
            if is_announcement
            else f"Update to v{state.update_data.get('version', '')} available"
        )
        badge_icon = (
            ft.Icons.CAMPAIGN_ROUNDED if is_announcement else ft.Icons.UPGRADE_ROUNDED
        )
        update_badge_controls.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(badge_icon, size=16, color=badge_color),
                        ft.Text(
                            badge_label,
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            color=badge_color,
                            font_family="Outfit",
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=6,
                ),
                padding=ft.Padding(14, 8, 14, 8),
                border_radius=tokens.RADIUS_MD,
                bgcolor=ft.Colors.with_opacity(0.12, badge_color),
                border=ft.Border.all(1.2, badge_color),
                ink=True,
                on_click=lambda e: controller.open_update_dialog(),
                margin=ft.Margin(0, tokens.SPACE_MD, 0, tokens.SPACE_XS),
            )
        )

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
                            "A UI for Sherlock & holehe.\nUsername & Email OSINT made easy.",
                            size=tokens.FONT_SM,
                            color=ft.Colors.with_opacity(
                                tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                            ),
                            text_align=ft.TextAlign.CENTER,
                        ),
                        *update_badge_controls,
                        ft.Container(height=tokens.SPACE_SM),
                        ft.TextButton(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.SYNC_ROUNDED,
                                        size=14,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                    ft.Text(
                                        "Check for updates",
                                        size=tokens.FONT_XS,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                ],
                                spacing=4,
                                alignment=ft.MainAxisAlignment.CENTER,
                                tight=True,
                            ),
                            on_click=lambda e: asyncio.create_task(
                                controller.check_for_updates()
                            ),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=0,
                ),
                padding=ft.Padding(
                    left=tokens.SPACE_LG,
                    right=tokens.SPACE_LG,
                    top=tokens.SPACE_XL,
                    bottom=tokens.SPACE_LG,
                ),
                alignment=ft.Alignment.CENTER,
            ),
        ]
    )

    # Extra cards: Network & Enrichment
    network_card = _settings_card(
        [
            ft.Container(
                content=ft.TextField(
                    value=state.proxy_url,
                    hint_text="socks5://127.0.0.1:1080 or http://proxy:8080 (empty = direct)",
                    label="Proxy URL",
                    prefix_icon=ft.Icons.LANGUAGE_ROUNDED,
                    border_radius=tokens.RADIUS_SM,
                    text_size=tokens.FONT_SM,
                    content_padding=tokens.SPACE_SM,
                    focused_border_color=ft.Colors.PRIMARY,
                    bgcolor=ft.Colors.SURFACE,
                    filled=True,
                    on_submit=lambda e: _on_proxy_change(e.control.value),
                    on_blur=lambda e: _on_proxy_change(e.control.value),
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD
                ),
            ),
        ]
    )
    enrichment_card = _settings_card(
        [
            _setting_row(
                ft.Icons.AUTO_AWESOME_ROUNDED,
                "Enrichment Mode",
                "Basic = fast (1 req/url) · Full = richer via API mutations",
                ft.Dropdown(
                    value=state.enrichment_mode,
                    options=[
                        ft.DropdownOption("basic", "Basic"),
                        ft.DropdownOption("full", "Full"),
                    ],
                    width=100,
                    text_size=tokens.FONT_SM,
                    border_radius=tokens.RADIUS_SM,
                    focused_border_color=ft.Colors.PRIMARY,
                    on_select=lambda e: _on_enrichment_mode_change(e.control.value),
                    content_padding=4,
                ),
            ),
        ]
    )

    content = ft.ListView(
        controls=[
            ft.Container(height=tokens.SPACE_SM),
            SectionHeader("PREFERENCES"),
            preferences_card,
            SectionHeader("SCAN PARAMETERS"),
            scan_card,
            build_banner_ad(),
            SectionHeader("EMAIL INTELLIGENCE"),
            email_card,
            SectionHeader("NETWORK & PROXY"),
            network_card,
            SectionHeader("ENRICHMENT"),
            enrichment_card,
            SectionHeader("CONNECTION & SPEED"),
            performance_card,
            SectionHeader("CUSTOM MANIFEST"),
            manifest_card,
            SectionHeader("ABOUT"),
            about_card,
            build_banner_ad(),
            ft.Container(height=tokens.SPACE_XXXL),
        ],
        spacing=0,
        expand=True,
    )

    return ft.Column(
        controls=[
            AppHeader(
                page,
                title="Settings",
                subtitle="Preferences & site database",
                show_settings=False,
            ),
            content,
        ],
        expand=True,
        spacing=0,
    )
