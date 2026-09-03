"""SettingsScreen — search parameters, theme, and database updates.

@ft.component — reads/writes observable state via AppStateCtx.
Premium settings with grouped cards, modern switches, and clear hierarchy.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import flet as ft
from flet import Control

from components.app_header import AppHeader
from components.banner_ad import build_banner_ad
from components.section_header import SectionHeader
from core import tokens
from core.logger_handler import get_telemetry_snapshot, in_memory_log_handler
from core.notify import show_snack
from core.constants import (
    APP_BUILD_NUMBER,
    APP_NAME,
    APP_VERSION,
    STORAGE_DNS_RESOLVER,
    STORAGE_EMAIL_CONCURRENCY,
    STORAGE_EMAIL_METHOD_FILTER,
    STORAGE_EMAIL_ONLY_FOUND,
    STORAGE_EMAIL_TIMEOUT,
    STORAGE_ENRICHMENT_MODE,
    STORAGE_EXCLUSIONS,
    STORAGE_EXTRACT_INFO,
    STORAGE_LOCAL_DB,
    STORAGE_MANIFEST,
    STORAGE_MAX_CONNECTIONS,
    STORAGE_NO_PASSWORD_RECOVERY,
    STORAGE_NSFW,
    STORAGE_PROXY_URL,
    STORAGE_RECURSIVE_SEARCH,
    STORAGE_RETRIES,
    STORAGE_SAFE_SEARCH,
    STORAGE_SCAN_DEPTH,
    STORAGE_THEME,
    STORAGE_TIMEOUT,
    STORAGE_USE_CURL_CFFI,
)
from core.theme import AppColors, is_dark_mode
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("SettingsScreen")


def _setting_row(
    icon: ft.IconData,
    title: str,
    subtitle: str,
    trailing: Control,
    stacked: bool = False,
) -> ft.Container:
    """Reusable settings row with icon + text + trailing control.

    On narrow screens (`stacked=True`) the trailing control moves to its
    own line below the description instead of competing for horizontal
    space — SegmentedButtons and Sliders otherwise squeeze the subtitle
    or overflow on phones. Wide layouts are unchanged.
    """
    icon_box = ft.Container(
        content=ft.Icon(
            icon,
            size=tokens.ICON_MD,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
        width=tokens.ICON_BACKDROP,
        height=tokens.ICON_BACKDROP,
        border_radius=tokens.ICON_BACKDROP_RADIUS,
        bgcolor=ft.Colors.with_opacity(tokens.OPACITY_LIGHT, ft.Colors.ON_SURFACE),
        alignment=ft.Alignment.CENTER,
    )
    text_col = ft.Column(
        controls=[
            ft.Text(
                title,
                size=tokens.FONT_MD,
                weight=ft.FontWeight.W_500,
            ),
            ft.Text(
                subtitle,
                size=tokens.FONT_XS,
                color=ft.Colors.with_opacity(tokens.OPACITY_DIM, ft.Colors.ON_SURFACE),
            ),
        ],
        spacing=tokens.SPACE_XXS,
        expand=True,
    )

    if stacked:
        # Sliders and SegmentedButtons stretch across the second line;
        # switches/buttons keep their natural size under the text indent.
        stretches = isinstance(trailing, (ft.Slider, ft.SegmentedButton))
        trailing_line = ft.Row(
            controls=[
                ft.Container(width=tokens.ICON_BACKDROP + tokens.SPACE_MD),
                (ft.Row(controls=[trailing], expand=True) if stretches else trailing),
            ],
            spacing=0,
        )
        content = ft.Column(
            controls=[
                ft.Row(
                    controls=[icon_box, text_col],
                    spacing=tokens.SPACE_MD,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                trailing_line,
            ],
            spacing=tokens.SPACE_XS,
        )
    else:
        content = ft.Row(
            controls=[icon_box, text_col, trailing],
            spacing=tokens.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    return ft.Container(
        content=content,
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
def SettingsScreen(banner: Control | None = None) -> Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    from flet import context

    try:
        page = context.page
    except Exception:
        page = None

    # Narrow screens stack each setting's control under its description —
    # one-line rows squeeze subtitles and overflow SegmentedButtons.
    narrow = bool(page and getattr(page, "width", None) and page.width < 600)
    is_mobile = bool(page and hasattr(page, "platform") and page.platform.is_mobile())

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
        curr_mode = (
            page.theme_mode
            if page and hasattr(page, "theme_mode")
            else state.theme_mode
        )
        is_sel = (
            (mode == "dark" and curr_mode == ft.ThemeMode.DARK)
            or (mode == "light" and curr_mode == ft.ThemeMode.LIGHT)
            or (
                mode == "system"
                and (curr_mode == ft.ThemeMode.SYSTEM or curr_mode is None)
            )
        )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        icon,
                        color=AppColors.PRIMARY
                        if is_sel
                        else ft.Colors.ON_SURFACE_VARIANT,
                        size=tokens.ICON_SM,
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
            padding=ft.Padding(8, 8, 8, 8),
            border_radius=tokens.RADIUS_SM,
            border=ft.Border.all(
                1.5 if is_sel else 1,
                AppColors.PRIMARY
                if is_sel
                else ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE),
            ),
            bgcolor=(
                ft.Colors.with_opacity(0.10, AppColors.PRIMARY)
                if is_sel
                else ft.Colors.TRANSPARENT
            ),
            expand=True,
            ink=True,
            on_click=lambda e, m=mode: asyncio.create_task(_on_theme_change(m)),
            animate=ft.Animation(tokens.ANIM_FAST, "easeOut"),
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
        cleaned = val.strip()
        if cleaned and not any(
            cleaned.lower().startswith(p)
            for p in ("http://", "https://", "socks5://", "socks5h://")
        ):
            show_snack(
                page,
                "Invalid proxy URL. Please use http://, https://, or socks5://",
                bgcolor=AppColors.WARNING,
            )
            return
        state.proxy_url = cleaned
        asyncio.create_task(_persist(STORAGE_PROXY_URL, cleaned))

    def _on_enrichment_mode_change(val: str):
        state.enrichment_mode = val
        asyncio.create_task(_persist(STORAGE_ENRICHMENT_MODE, val))

    def _toggle_no_password_recovery(val: bool):
        state.no_password_recovery = val
        asyncio.create_task(
            _persist(STORAGE_NO_PASSWORD_RECOVERY, "true" if val else "false")
        )

    def _on_scan_depth_change(val: str):
        state.scan_depth = val
        asyncio.create_task(_persist(STORAGE_SCAN_DEPTH, val))
        asyncio.create_task(controller.refresh_sites())

    def _toggle_recursive_search(val: bool):
        state.recursive_search = val
        asyncio.create_task(
            _persist(STORAGE_RECURSIVE_SEARCH, "true" if val else "false")
        )

    def _toggle_extract_info(val: bool):
        state.extract_info = val
        asyncio.create_task(_persist(STORAGE_EXTRACT_INFO, "true" if val else "false"))

    def _on_max_connections_change(val: str):
        state.max_connections = max(10, min(100, int(val)))
        asyncio.create_task(_persist(STORAGE_MAX_CONNECTIONS, val))

    def _on_retries_change(val: str):
        state.retries = int(val)
        asyncio.create_task(_persist(STORAGE_RETRIES, val))

    def _on_dns_resolver_change(val: str):
        state.dns_resolver = val
        asyncio.create_task(_persist(STORAGE_DNS_RESOLVER, val))

    def _toggle_use_curl_cffi(val: bool):
        state.use_curl_cffi = val
        asyncio.create_task(_persist(STORAGE_USE_CURL_CFFI, "true" if val else "false"))

    def _toggle_safe_search(val: bool):
        state.safe_search = val
        state.nsfw_enabled = not val
        asyncio.create_task(_persist(STORAGE_SAFE_SEARCH, "true" if val else "false"))
        asyncio.create_task(_persist(STORAGE_NSFW, "false" if val else "true"))
        if controller.refresh_sites:
            asyncio.create_task(controller.refresh_sites())

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

    # Scan Parameters (Maigret Engine)
    scan_controls = [
        _setting_row(
            ft.Icons.SAVED_SEARCH_ROUNDED,
            "Recursive OSINT Search",
            "Extract discovered usernames & IDs to automatically expand search",
            ft.Switch(
                value=getattr(state, "recursive_search", False),
                on_change=lambda e: _toggle_recursive_search(e.control.value),
                active_color=ft.Colors.PRIMARY,
            ),
            stacked=narrow,
        ),
        ft.Divider(
            height=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        _setting_row(
            ft.Icons.ACCOUNT_BOX_ROUNDED,
            "Profile Data Extraction",
            "Parse claimed profile HTML for names, bios, avatars, and locations",
            ft.Switch(
                value=getattr(state, "extract_info", True),
                on_change=lambda e: _toggle_extract_info(e.control.value),
                active_color=ft.Colors.PRIMARY,
            ),
            stacked=narrow,
        ),
        ft.Divider(
            height=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        _setting_row(
            ft.Icons.SHIELD_ROUNDED,
            "Include Disabled Sites",
            "Scan unstable or broken networks (may increase false positives)",
            ft.Switch(
                value=state.ignore_exclusions,
                on_change=lambda e: _toggle_exclusions(e.control.value),
                active_color=ft.Colors.PRIMARY,
            ),
            stacked=narrow,
        ),
        ft.Divider(
            height=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        _setting_row(
            ft.Icons.BLOCK_ROUNDED,
            "Include Adult Sites",
            "Include NSFW, dating, and adult networks in scans",
            ft.Switch(
                value=state.nsfw_enabled,
                on_change=lambda e: _toggle_nsfw(e.control.value),
                active_color=ft.Colors.PRIMARY,
            ),
            stacked=narrow,
        ),
        ft.Divider(
            height=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        _setting_row(
            ft.Icons.REPLAY_ROUNDED,
            "Request Retries",
            "Number of retries when a network request drops or times out",
            ft.SegmentedButton(
                segments=[
                    ft.Segment(value="0", label=ft.Text("0", size=10)),
                    ft.Segment(value="1", label=ft.Text("1", size=10)),
                    ft.Segment(value="2", label=ft.Text("2", size=10)),
                    ft.Segment(value="3", label=ft.Text("3", size=10)),
                ],
                selected=[str(getattr(state, "retries", 0))],
                on_change=lambda e: _on_retries_change(
                    e.control.selected[0] if e.control.selected else "0"
                ),
                show_selected_icon=False,
            ),
            stacked=narrow,
        ),
    ]
    if not is_mobile:
        scan_controls.extend(
            [
                ft.Divider(
                    height=1,
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE
                    ),
                ),
                _setting_row(
                    ft.Icons.DNS_ROUNDED,
                    "DNS Resolver Mode",
                    "Async (c-ares) for speed · System (Threaded) for network compat",
                    ft.SegmentedButton(
                        segments=[
                            ft.Segment(value="async", label=ft.Text("Async", size=10)),
                            ft.Segment(
                                value="threaded", label=ft.Text("System", size=10)
                            ),
                        ],
                        selected=[getattr(state, "dns_resolver", "threaded")],
                        on_change=lambda e: _on_dns_resolver_change(
                            e.control.selected[0] if e.control.selected else "threaded"
                        ),
                        show_selected_icon=False,
                    ),
                    stacked=narrow,
                ),
            ]
        )
    scan_card = _settings_card(scan_controls)

    # Email Intelligence (Holehe + curl-cffi)
    email_card = _settings_card(
        [
            _setting_row(
                ft.Icons.SECURITY_ROUNDED,
                "Stealth TLS (curl-cffi)",
                "Chrome 124 JA3/H2 fingerprint to bypass WAF 403 blocks",
                ft.Switch(
                    value=getattr(state, "use_curl_cffi", True),
                    on_change=lambda e: _toggle_use_curl_cffi(e.control.value),
                    active_color=ft.Colors.PRIMARY,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
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
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.SPEED_ROUNDED,
                "Email Concurrency",
                "Parallel checks — lower is stealthier, higher is faster",
                ft.Slider(
                    value=float(getattr(state, "email_concurrency", 12)),
                    min=4,
                    max=30,
                    divisions=13,
                    label=f"{getattr(state, 'email_concurrency', 12)}",
                    active_color=AppColors.PRIMARY,
                    on_change=lambda e: _on_email_concurrency_change(
                        str(int(e.control.value))
                    ),
                ),
                stacked=narrow,
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
                stacked=narrow,
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
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.CATEGORY_ROUNDED,
                "Detection Method Filter",
                "Filter email intelligence by platform detection vector",
                ft.SegmentedButton(
                    segments=[
                        ft.Segment(value="all", label=ft.Text("All", size=10)),
                        ft.Segment(
                            value="register", label=ft.Text("Register", size=10)
                        ),
                        ft.Segment(value="login", label=ft.Text("Login", size=10)),
                        ft.Segment(
                            value="password recovery",
                            label=ft.Text("Recovery", size=10),
                        ),
                    ],
                    selected=[state.email_method_filter or "all"],
                    on_change=lambda e: _on_email_method_filter_change(
                        e.control.selected[0] if e.control.selected else "all"
                    ),
                    show_selected_icon=False,
                ),
                stacked=narrow,
            ),
        ]
    )

    # Performance
    performance_card = _settings_card(
        [
            _setting_row(
                ft.Icons.TRAVEL_EXPLORE_ROUNDED,
                "Scan Scope & Depth",
                "Choose between full sweep or top Alexa-ranked networks",
                ft.SegmentedButton(
                    segments=[
                        ft.Segment(value="all", label=ft.Text("All 3.3k", size=10)),
                        ft.Segment(value="1000", label=ft.Text("Top 1k", size=10)),
                        ft.Segment(value="500", label=ft.Text("Top 500", size=10)),
                    ],
                    selected=[state.scan_depth or "all"],
                    on_change=lambda e: _on_scan_depth_change(
                        e.control.selected[0] if e.control.selected else "all"
                    ),
                    show_selected_icon=False,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.SPEED_ROUNDED,
                "Network Concurrency",
                "Max parallel requests during username scans (10 - 100)",
                ft.Slider(
                    value=float(getattr(state, "max_connections", 50)),
                    min=10,
                    max=100,
                    divisions=9,
                    label=f"{getattr(state, 'max_connections', 50)}",
                    active_color=AppColors.PRIMARY,
                    on_change=lambda e: _on_max_connections_change(
                        str(int(e.control.value))
                    ),
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.FLASH_ON_ROUNDED,
                "Bundled Database",
                "Use local bundled 3.3k database (faster startup)",
                ft.Switch(
                    value=state.use_local_db,
                    on_change=lambda e: _toggle_local_db(e.control.value),
                    active_color=ft.Colors.PRIMARY,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.TIMER_OUTLINED,
                "Request Timeout",
                "Maximum connection wait time per site (5s - 60s)",
                ft.Slider(
                    value=float(state.timeout),
                    min=5,
                    max=60,
                    divisions=11,
                    label=f"{state.timeout}s",
                    active_color=AppColors.PRIMARY,
                    on_change=lambda e: _on_timeout_change(str(int(e.control.value))),
                ),
                stacked=narrow,
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

    # Personalized Ads & Consent (mobile only — ad_service)
    privacy_card = ft.Container(width=0, height=0)
    if is_mobile:

        def _open_privacy_options(e):
            async def _do_open():
                from flet import context

                page = context.page
                if not page:
                    return
                ad_svc = getattr(page, "_ad_service", None)
                if ad_svc:
                    await ad_svc.show_privacy_options()
                else:
                    show_snack(
                        page,
                        "Ad consent is managed automatically by your region.",
                        bgcolor=AppColors.PRIMARY,
                    )

            asyncio.create_task(_do_open())

        privacy_card = _settings_card(
            [
                _setting_row(
                    ft.Icons.PRIVACY_TIP_ROUNDED,
                    "Personalized Ads & Consent",
                    "Manage ad preferences and GDPR consent settings",
                    ft.FilledTonalButton(
                        "Manage",
                        icon=ft.Icons.TUNE_ROUNDED,
                        on_click=_open_privacy_options,
                    ),
                    stacked=narrow,
                ),
            ]
        )

    # About & Updates
    def _open_version_dialog(e=None):
        from components.update_dialog import show_update_dialog

        show_update_dialog(page)

    about_card = _settings_card(
        [
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Image(
                            src="/icon.svg",
                            width=48,
                            height=48,
                            color=ft.Colors.WHITE if is_dark_mode(page) else None,
                        ),
                        ft.Container(height=tokens.SPACE_SM),
                        ft.Text(
                            APP_NAME,
                            size=tokens.FONT_LG,
                            weight=ft.FontWeight.W_700,
                            color=ft.Colors.ON_SURFACE,
                        ),
                        ft.Container(
                            content=ft.Text(
                                f"Version {APP_VERSION} (Build {APP_BUILD_NUMBER})",
                                size=tokens.FONT_SM,
                                color=ft.Colors.with_opacity(
                                    tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                                ),
                            ),
                            ink=True,
                            tooltip="Tap to view changelog",
                            on_click=_open_version_dialog,
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
                ft.SegmentedButton(
                    segments=[
                        ft.Segment(
                            value="basic",
                            label=ft.Text("Basic", size=10, font_family="Outfit"),
                        ),
                        ft.Segment(
                            value="full",
                            label=ft.Text("Full", size=10, font_family="Outfit"),
                        ),
                    ],
                    selected=[state.enrichment_mode or "full"],
                    on_change=lambda e: _on_enrichment_mode_change(
                        e.control.selected[0] if e.control.selected else "full"
                    ),
                    show_selected_icon=False,
                ),
                stacked=narrow,
            ),
        ]
    )

    def _open_terminal():
        with contextlib.suppress(Exception):
            page.pop_dialog()

        logs_list = in_memory_log_handler.get_logs()
        log_text = ft.Text(
            value="\n".join(logs_list)
            if logs_list
            else "No activity recorded yet.\nEngine, network, and UI logs will appear here.",
            size=tokens.FONT_XS,
            font_family="Courier New",
            color=AppColors.TERMINAL_GREEN,
            selectable=True,
        )

        async def _copy_logs(e):
            try:
                cb = ft.Clipboard()
                current_logs = "\n".join(in_memory_log_handler.get_logs())
                await cb.set(current_logs)
                show_snack(page, "Logs copied to clipboard", bgcolor=AppColors.SUCCESS)
            except Exception as exc:
                logger.warning("Failed to copy logs: %s", exc)

        telemetry_text = ft.Text(
            get_telemetry_snapshot(),
            size=11,
            font_family="Courier New",
            color=AppColors.PRIMARY,
            weight=ft.FontWeight.W_600,
            expand=True,
        )

        def _refresh_telemetry(e):
            telemetry_text.value = get_telemetry_snapshot()
            cur_logs = in_memory_log_handler.get_logs()
            if cur_logs:
                log_text.value = "\n".join(cur_logs)
            page.update()

        def _clear_logs(e):
            in_memory_log_handler.clear_logs()
            log_text.value = "Logs cleared.\nNew activity will appear here."
            page.update()

        def _dismiss(e):
            page.pop_dialog()

        terminal_dlg = ft.AlertDialog(
            modal=False,
            title=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.TERMINAL_ROUNDED,
                        color=AppColors.PRIMARY,
                        size=tokens.ICON_MD,
                    ),
                    ft.Text(
                        "Live Activity Terminal",
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.BOLD,
                        font_family="Outfit",
                        color=AppColors.PRIMARY,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH_ROUNDED,
                        tooltip="Refresh telemetry",
                        icon_size=18,
                        icon_color=AppColors.PRIMARY,
                        on_click=_refresh_telemetry,
                    ),
                ],
                spacing=tokens.SPACE_SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Container(
                            content=ft.Row(
                                [
                                    telemetry_text,
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            padding=ft.Padding(8, 4, 8, 4),
                            border_radius=tokens.RADIUS_SM,
                            bgcolor=ft.Colors.with_opacity(0.08, AppColors.PRIMARY),
                            margin=ft.Margin(0, 0, 0, tokens.SPACE_XS),
                        ),
                        ft.Text(
                            "Real-time engine execution, network status, and diagnostic logs.",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Container(height=tokens.SPACE_XS),
                        ft.Container(
                            content=ft.Column(
                                [log_text],
                                scroll=ft.ScrollMode.AUTO,
                            ),
                            bgcolor=AppColors.TERMINAL_BG,
                            border=ft.Border.all(
                                1,
                                ft.Colors.with_opacity(
                                    tokens.OPACITY_LIGHT, ft.Colors.WHITE
                                ),
                            ),
                            border_radius=tokens.RADIUS_SM,
                            padding=tokens.SPACE_MD,
                            expand=True,
                        ),
                    ],
                    spacing=0,
                ),
                width=tokens.DIALOG_WIDTH_LG,
                height=tokens.DIALOG_HEIGHT_LG,
            ),
            actions=[
                ft.TextButton(
                    "Copy Logs",
                    icon=ft.Icons.COPY_ROUNDED,
                    on_click=lambda e: asyncio.create_task(_copy_logs(e)),
                ),
                ft.TextButton(
                    "Clear",
                    icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                    on_click=_clear_logs,
                ),
                ft.TextButton("Close", on_click=_dismiss),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(terminal_dlg)

    log_count = len(in_memory_log_handler.get_logs())
    logs_card = _settings_card(
        [
            _setting_row(
                ft.Icons.TERMINAL_ROUNDED,
                "Live Activity Terminal",
                f"{log_count} entries recorded · Real-time engine diagnostics",
                ft.FilledButton(
                    "Open Terminal",
                    icon=ft.Icons.TERMINAL_ROUNDED,
                    on_click=lambda e: _open_terminal(),
                ),
                stacked=narrow,
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
            build_banner_ad(),
            SectionHeader("CONNECTION & SPEED"),
            performance_card,
            SectionHeader("CUSTOM MANIFEST"),
            manifest_card,
            build_banner_ad(),
            SectionHeader("TROUBLESHOOTING & LOGS"),
            logs_card,
            SectionHeader("PRIVACY"),
            privacy_card,
            SectionHeader("ABOUT"),
            about_card,
            ft.Container(height=tokens.SPACE_XXXL),
        ],
        spacing=0,
        expand=True,
    )

    header_controls: list[Control] = [
        AppHeader(
            page,
            title="Settings",
            subtitle="Preferences & site database",
            show_settings=False,
        ),
    ]
    if banner:
        header_controls.append(banner)

    return ft.Column(
        controls=[
            *header_controls,
            content,
        ],
        expand=True,
        spacing=0,
    )
