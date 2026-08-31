"""HomeScreen — compact search-first dashboard (DDGS style).

Search bar above the fold, category chips, search tools, recent searches,
feature cards, how it works, and trust banner.
"""

from __future__ import annotations

import asyncio
import json
import logging

import flet as ft
from flet import Control

from components.banner_ad import build_banner_ad
from components.targets_card import TargetsCard
from core import tokens
from core.constants import (
    APP_NAME,
    APP_VERSION,
    MODE_EMAIL,
    MODE_USERNAME,
    MSG_OFFLINE,
    STORAGE_HISTORY,
    STORAGE_SEARCH_MODE,
    STORAGE_THEME,
)
from core.theme import (
    AppColors,
    AppStyles,
    adaptive_glass_bg,
    adaptive_glass_border,
    is_dark_mode,
)
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("HomeScreen")


# ── Feature cards data ─────────────────────────────────────────────────

_FEATURES_USERNAME = [
    {
        "icon": ft.Icons.PERSON_SEARCH_ROUNDED,
        "title": "Hunt Across 400+ Networks",
        "desc": "Scan GitHub, X, Instagram, TikTok, Reddit, Spotify, and more — simultaneously.",
        "color": AppColors.PRIMARY,
    },
    {
        "icon": ft.Icons.SPEED_ROUNDED,
        "title": "Ultra-Fast Offline Scans",
        "desc": "Scan from the local offline database — no site-list download first. A connection is still needed to reach each site.",
        "color": AppColors.PRIMARY_DARK,
    },
    {
        "icon": ft.Icons.DOWNLOAD_ROUNDED,
        "title": "Premium Data Exports",
        "desc": "Export reports as Excel, CSV, or Text lists — directly to your device.",
        "color": AppColors.PRIMARY_LIGHT,
    },
]

_FEATURES_EMAIL = [
    {
        "icon": ft.Icons.ALTERNATE_EMAIL_ROUNDED,
        "title": "Check 120+ Platforms",
        "desc": "Discover where an email is registered — social media, shopping, forums, CRM, and more.",
        "color": AppColors.PRIMARY,
    },
    {
        "icon": ft.Icons.SECURITY_ROUNDED,
        "title": "Recovery Data & Leaked Hints",
        "desc": "Uncover masked recovery emails, phone numbers, full names, and account creation dates.",
        "color": AppColors.PRIMARY_DARK,
    },
    {
        "icon": ft.Icons.CATEGORY_ROUNDED,
        "title": "23 Categories Covered",
        "desc": "Social media, mail providers, programming, music, shopping, forums, jobs, and more.",
        "color": AppColors.PRIMARY_LIGHT,
    },
]

_STEPS_USERNAME = [
    ("1", "Enter", "Type a username to hunt across social networks"),
    ("2", "Scan", "Sherlock checks 400+ platforms simultaneously"),
    ("3", "Done", "View results, export reports, or open profiles in browser"),
]

_STEPS_EMAIL = [
    ("1", "Enter", "Type an email address to investigate"),
    ("2", "Scan", "Checks 120+ platforms for registrations"),
    ("3", "Done", "View where the email is used, recovery hints, and more"),
]


# ── Compact components ─────────────────────────────────────────────────


@ft.memo
def _category_chip(
    icon: str,
    label: str,
    color: str,
    is_active: bool,
    on_click=None,
) -> ft.Container:
    """Compact filter-chip style category selector."""
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(
                    icon,
                    size=16,
                    color=color if is_active else ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    label,
                    size=12,
                    weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.W_400,
                    color=color if is_active else ft.Colors.ON_SURFACE,
                    font_family="Outfit",
                ),
            ],
            spacing=4,
            tight=True,
        ),
        padding=ft.Padding(12, 6, 12, 6),
        border_radius=20,
        border=ft.Border.all(
            1.5 if is_active else 1,
            color if is_active else ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
        ),
        bgcolor=ft.Colors.with_opacity(0.1, color)
        if is_active
        else ft.Colors.TRANSPARENT,
        on_click=on_click,
        animate=ft.Animation(tokens.ANIM_FAST, "easeOut"),
    )


@ft.memo
def _history_row(
    username: str,
    found: int,
    total: int,
    timestamp: str,
    on_click=None,
) -> ft.Container:
    """Compact recent search row."""
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.PERSON_SEARCH_ROUNDED, size=16, color=AppColors.PRIMARY
                ),
                ft.Text(
                    username,
                    size=12,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                    font_family="Outfit",
                ),
                ft.Text(
                    f"{found}/{total}",
                    size=10,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    font_family="Outfit",
                ),
                ft.Text(
                    timestamp,
                    size=10,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    font_family="Outfit",
                ),
                ft.Icon(
                    ft.Icons.ARROW_FORWARD_ROUNDED,
                    size=14,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(12, 8, 12, 8),
        border_radius=tokens.RADIUS_MD,
        bgcolor=adaptive_glass_bg(),
        border=ft.Border.all(1, adaptive_glass_border()),
        ink=True,
        on_click=on_click,
    )


@ft.memo
def _feature_card(
    icon: str,
    title: str,
    desc: str,
    color: str,
) -> ft.Container:
    """Feature highlight card row."""
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, size=20, color=color),
                    width=38,
                    height=38,
                    border_radius=10,
                    bgcolor=ft.Colors.with_opacity(0.1, color),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            title,
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            font_family="Outfit",
                            max_lines=1,
                            overflow="ellipsis",
                        ),
                        ft.Text(
                            desc,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=2,
                            overflow="ellipsis",
                            font_family="Outfit",
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_MD,
            vertical_alignment="center",
        ),
        padding=12,
        border_radius=12,
        bgcolor=adaptive_glass_bg(),
        border=ft.Border.all(1, adaptive_glass_border()),
        ink=True,
    )


@ft.memo
def _step_row(number: str, title: str, desc: str) -> ft.Row:
    """Numbered step row."""
    return ft.Row(
        controls=[
            ft.Container(
                content=ft.Text(
                    number,
                    size=tokens.FONT_SM,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.WHITE,
                    text_align=ft.TextAlign.CENTER,
                    font_family="Outfit",
                ),
                width=26,
                height=26,
                border_radius=13,
                bgcolor=AppColors.PRIMARY,
                alignment=ft.Alignment.CENTER,
            ),
            ft.Column(
                controls=[
                    ft.Text(
                        title,
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_600,
                        font_family="Outfit",
                    ),
                    ft.Text(
                        desc,
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        font_family="Outfit",
                    ),
                ],
                spacing=tokens.SPACE_XXS,
                expand=True,
            ),
        ],
        spacing=tokens.SPACE_MD,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _make_compact_dropdown(label, icon, value, options, on_change, width=140):
    return ft.Column(
        [
            ft.Row(
                [
                    ft.Icon(icon, size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(
                        label,
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        font_family="Outfit",
                        weight=ft.FontWeight.W_500,
                    ),
                ],
                spacing=4,
                tight=True,
            ),
            ft.Dropdown(
                value=value,
                options=options,
                on_select=on_change,
                filled=True,
                text_size=tokens.FONT_XS,
                content_padding=ft.Padding(left=10, top=4, right=10, bottom=4),
                border_radius=tokens.RADIUS_MD,
                width=width,
                height=36,
            ),
        ],
        spacing=2,
        tight=True,
    )


# ── Main screen ───────────────────────────────────────────────────────


@ft.component
def HomeScreen() -> Control:
    """Compact search-first home dashboard (DDGS style)."""
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    search_query, set_search_query = ft.use_state("")
    active_chip, set_active_chip = ft.use_state("all")
    tools_expanded, set_tools_expanded = ft.use_state(False)
    theme_version, set_theme_version = ft.use_state(0)

    # Mode is driven by observable state so it persists across screens
    is_email_mode = state.search_mode == MODE_EMAIL

    from flet import context as flet_context

    def _get_page():
        return flet_context.page

    def _is_dark():
        return is_dark_mode(_get_page())

    # ── Mode switcher ──

    def _switch_mode(new_mode: str):
        state.search_mode = new_mode

        async def _save():
            try:
                from services.storage_service import StorageService

                storage = StorageService(_get_page())
                await storage.set(STORAGE_SEARCH_MODE, new_mode)
            except Exception:
                pass

        asyncio.create_task(_save())

    # ── Search logic ──

    def _on_search(e=None):
        query = search_query.strip() if search_query else ""
        if not query:
            return

        async def _run():
            controller.show_results()
            if state.search_mode == MODE_EMAIL:
                await controller.start_email_search(query)
            else:
                await controller.start_search(query)

        asyncio.create_task(_run())

    def _on_input_change(e):
        value = e.control.value or ""
        set_search_query(value)
        # Auto-switch to email mode only if full email is pasted while in username mode
        if (
            state.search_mode == MODE_USERNAME
            and "@" in value
            and "." in value.split("@")[-1]
            and len(value.split("@")[-1].split(".")[-1]) >= 2
        ):
            _switch_mode(MODE_EMAIL)

    def _on_paste(e):
        async def _paste():
            try:
                clipboard = ft.Clipboard()
                text = await clipboard.get()
                if text:
                    set_search_query(text.strip())
            except Exception:
                pass

        asyncio.create_task(_paste())

    def _on_history_click(username: str):
        set_search_query(username)
        _on_search()

    # ── Theme toggle ──

    def _toggle_theme(e):
        page = _get_page()
        if page.theme_mode == ft.ThemeMode.DARK:
            new_mode = ft.ThemeMode.LIGHT
            theme_val = "light"
        elif page.theme_mode == ft.ThemeMode.LIGHT:
            new_mode = ft.ThemeMode.SYSTEM
            theme_val = "system"
        else:
            new_mode = ft.ThemeMode.DARK
            theme_val = "dark"
        page.theme_mode = new_mode
        state.theme_mode = new_mode
        set_theme_version(theme_version + 1)

        # Persist theme preference
        async def _save():
            try:
                from services.storage_service import StorageService

                storage = StorageService(page)
                await storage.set(STORAGE_THEME, theme_val)
            except Exception:
                pass

        asyncio.create_task(_save())

    def _get_theme_icon():
        page = _get_page()
        if page.theme_mode == ft.ThemeMode.DARK:
            return ft.Icons.DARK_MODE_ROUNDED
        elif page.theme_mode == ft.ThemeMode.LIGHT:
            return ft.Icons.LIGHT_MODE_ROUNDED
        return ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED

    # ── Load history on mount ──
    def _load_history():
        async def _fetch():
            try:
                from services.storage_service import StorageService

                storage = StorageService(_get_page())
                raw = await storage.get(STORAGE_HISTORY)
                if raw:
                    entries = json.loads(raw)
                    # Contract: storage is oldest-first; observable
                    # state.history is ALWAYS newest-first (display order).
                    state.history.clear()
                    state.history.extend(reversed(entries))
            except Exception:
                pass

        asyncio.create_task(_fetch())

    ft.use_effect(_load_history, [])

    # ── Build UI ──

    is_dark = _is_dark()

    # Category chips — real Sherlock settings
    chips = [
        _category_chip(
            icon=ft.Icons.PUBLIC_ROUNDED,
            label=f"{state.timeout}s Timeout",
            color=AppColors.PRIMARY,
            is_active=active_chip == "timeout",
            on_click=lambda e: set_active_chip("timeout"),
        ),
        _category_chip(
            icon=ft.Icons.FLASH_ON_ROUNDED,
            label="Offline DB" if state.use_local_db else "Online Only",
            color=AppColors.PRIMARY_LIGHT if state.use_local_db else AppColors.GREY,
            is_active=active_chip == "offline",
            on_click=lambda e: set_active_chip("offline"),
        ),
        _category_chip(
            icon=ft.Icons.BLOCK_ROUNDED,
            label="NSFW" if state.nsfw_enabled else "No NSFW",
            color=AppColors.ERROR if state.nsfw_enabled else AppColors.GREY,
            is_active=active_chip == "nsfw",
            on_click=lambda e: set_active_chip("nsfw"),
        ),
        _category_chip(
            icon=ft.Icons.SHIELD_ROUNDED,
            label="Exclusions" if state.ignore_exclusions else "No Exclusions",
            color=AppColors.WARNING if state.ignore_exclusions else AppColors.GREY,
            is_active=active_chip == "exclusions",
            on_click=lambda e: set_active_chip("exclusions"),
        ),
    ]

    # Recent searches — read observable state directly (reactive), so
    # the three most recent sit on top.
    recent_rows = []
    if state.history:
        for entry in list(state.history[:3]):
            username = entry.get("username", "")
            found = entry.get("found", 0)
            total = entry.get("total", 0)
            ts = entry.get("timestamp", "")
            recent_rows.append(
                _history_row(
                    username=username,
                    found=found,
                    total=total,
                    timestamp=ts,
                    on_click=lambda _, u=username: _on_history_click(u),
                )
            )

    # Search tools
    tools_controls = [
        _make_compact_dropdown(
            "Timeout",
            ft.Icons.TIMER_OUTLINED,
            f"{state.timeout}s",
            [
                ft.DropdownOption("5", "5s"),
                ft.DropdownOption("10", "10s"),
                ft.DropdownOption("15", "15s"),
                ft.DropdownOption("30", "30s"),
                ft.DropdownOption("60", "60s"),
            ],
            lambda e: None,
            width=90,
        ),
        _make_compact_dropdown(
            "Offline DB",
            ft.Icons.FLASH_ON_ROUNDED,
            "On" if state.use_local_db else "Off",
            [
                ft.DropdownOption("On", "On"),
                ft.DropdownOption("Off", "Off"),
            ],
            lambda e: None,
            width=80,
        ),
    ]

    # ── Version / Update Chip ──
    is_announcement = (
        state.update_available
        and state.update_data
        and state.update_data.get("type") == "announcement"
    )
    if state.update_available:
        badge_color = AppColors.ACCENT if is_announcement else AppColors.PRIMARY
        badge_text = "News" if is_announcement else "Update"
        badge_icon = (
            ft.Icons.CAMPAIGN_ROUNDED if is_announcement else ft.Icons.UPGRADE_ROUNDED
        )
        version_chip = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(badge_icon, size=13, color=badge_color),
                    ft.Text(
                        badge_text,
                        size=11,
                        weight=ft.FontWeight.W_700,
                        color=badge_color,
                        font_family="Outfit",
                    ),
                    ft.Container(
                        width=6,
                        height=6,
                        border_radius=3,
                        bgcolor=badge_color,
                    ),
                ],
                spacing=4,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding(7, 3, 7, 3),
            border_radius=tokens.RADIUS_SM,
            bgcolor=ft.Colors.with_opacity(0.12, badge_color),
            border=ft.Border.all(1.2, badge_color),
            ink=True,
            tooltip="New update available — tap to view",
            on_click=lambda e: controller.open_update_dialog(),
        )
    else:
        version_chip = ft.Container(
            content=ft.Text(
                f"v{APP_VERSION}",
                size=11,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.with_opacity(tokens.OPACITY_DIM, ft.Colors.ON_SURFACE),
                font_family="Outfit",
            ),
            padding=ft.Padding(6, 2, 6, 2),
            border_radius=tokens.RADIUS_SM,
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE),
            ),
        )

    # ── Assemble ──

    content = ft.Column(
        controls=[
            # Compact header
            ft.Container(
                content=ft.Row(
                    [
                        ft.Row(
                            [
                                ft.Image(
                                    src="icon.png",
                                    width=28,
                                    height=28,
                                    color=AppColors.PRIMARY,
                                ),
                                ft.Text(
                                    APP_NAME,
                                    size=tokens.FONT_LG,
                                    weight=ft.FontWeight.BOLD,
                                    font_family="Outfit",
                                ),
                                version_chip,
                            ],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            tight=True,
                        ),
                        ft.Row(
                            [
                                ft.IconButton(
                                    icon=_get_theme_icon(),
                                    icon_size=20,
                                    on_click=_toggle_theme,
                                    tooltip="Toggle Theme",
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.SETTINGS_ROUNDED,
                                    icon_size=20,
                                    on_click=lambda e: controller.show_settings(),
                                    tooltip="Settings",
                                ),
                            ],
                            spacing=0,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                ),
            ),
            # Offline banner — reactively bound to state.is_online
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.WIFI_OFF_ROUNDED,
                            color=ft.Colors.ON_ERROR_CONTAINER,
                            size=tokens.ICON_SM,
                        ),
                        ft.Text(
                            MSG_OFFLINE,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_ERROR_CONTAINER,
                            expand=True,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM
                ),
                bgcolor=ft.Colors.ERROR_CONTAINER,
                visible=not state.is_online,
            ),
            # ── Mode Switcher (Username / Email) ──
            ft.Container(
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                ),
                content=ft.Container(
                    padding=ft.Padding(4, 4, 4, 4),
                    border_radius=12,
                    bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
                    border=ft.Border.all(
                        1, ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE)
                    ),
                    content=ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.PERSON_SEARCH_ROUNDED,
                                            size=16,
                                            color=ft.Colors.WHITE
                                            if not is_email_mode
                                            else ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                        ft.Text(
                                            "Username",
                                            size=12,
                                            weight=ft.FontWeight.BOLD,
                                            color=ft.Colors.WHITE
                                            if not is_email_mode
                                            else ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                    spacing=6,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                                bgcolor=AppColors.PRIMARY
                                if not is_email_mode
                                else ft.Colors.TRANSPARENT,
                                border_radius=8,
                                padding=ft.Padding(12, 6, 12, 6),
                                ink=True,
                                expand=True,
                                alignment=ft.Alignment.CENTER,
                                on_click=lambda e: _switch_mode(MODE_USERNAME),
                            ),
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.ALTERNATE_EMAIL_ROUNDED,
                                            size=16,
                                            color=ft.Colors.WHITE
                                            if is_email_mode
                                            else ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                        ft.Text(
                                            "Email",
                                            size=12,
                                            weight=ft.FontWeight.BOLD,
                                            color=ft.Colors.WHITE
                                            if is_email_mode
                                            else ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                    spacing=6,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                                bgcolor=AppColors.PRIMARY
                                if is_email_mode
                                else ft.Colors.TRANSPARENT,
                                border_radius=8,
                                padding=ft.Padding(12, 6, 12, 6),
                                ink=True,
                                expand=True,
                                alignment=ft.Alignment.CENTER,
                                on_click=lambda e: _switch_mode(MODE_EMAIL),
                            ),
                        ],
                        spacing=4,
                    ),
                ),
            ),
            # Search field — modern SearchBar
            ft.Container(
                alignment=ft.Alignment.CENTER,
                content=ft.SearchBar(
                    value=search_query,
                    bar_hint_text=(
                        "Enter email to check 120+ platforms..."
                        if is_email_mode
                        else "Enter username to hunt across 400+ networks..."
                    ),
                    bar_leading=ft.Icon(
                        ft.Icons.ALTERNATE_EMAIL_ROUNDED
                        if is_email_mode
                        else ft.Icons.SEARCH_ROUNDED,
                        color=AppColors.PRIMARY,
                    ),
                    bar_trailing=[
                        ft.IconButton(
                            icon=ft.Icons.PASTE_ROUNDED,
                            icon_size=18,
                            icon_color=AppColors.PRIMARY,
                            tooltip="Paste from clipboard",
                            on_click=_on_paste,
                        ),
                    ],
                    bar_bgcolor=(
                        AppColors.DARK_SURFACE if is_dark else AppColors.LIGHT_SURFACE
                    ),
                    bar_border_side=ft.BorderSide(
                        1,
                        ft.Colors.with_opacity(
                            0.12,
                            AppColors.DARK_TEXT if is_dark else AppColors.LIGHT_TEXT,
                        ),
                    ),
                    bar_shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                    bar_text_style=ft.TextStyle(
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.W_500,
                    ),
                    bar_hint_text_style=ft.TextStyle(
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.W_400,
                        color=ft.Colors.with_opacity(
                            0.4,
                            AppColors.DARK_TEXT if is_dark else AppColors.LIGHT_TEXT,
                        ),
                    ),
                    full_screen=True,
                    on_submit=lambda e: _on_search(),
                    on_change=_on_input_change,
                    autofocus=False,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                ),
            ),
            # ── Targets card — live network-scope summary (username mode only) ──
            ft.Container(
                content=TargetsCard(
                    selected_count=len(state.selected_sites)
                    if state.selected_sites
                    else 0,
                    total_count=state.sites_total,
                    on_open=lambda e: controller.show_sites(),
                    page=_get_page(),
                ),
                visible=not is_email_mode,
            ),
            # Category chips (horizontal scroll — username mode only)
            ft.Container(
                content=ft.Row(
                    chips,
                    wrap=False,
                    scroll=ft.ScrollMode.AUTO,
                    spacing=tokens.SPACE_SM,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                ),
                visible=not is_email_mode,
            ),
            # Tools toggle + search button
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Container(
                                    content=ft.Row(
                                        [
                                            ft.Icon(
                                                ft.Icons.TUNE_ROUNDED,
                                                size=16,
                                                color=AppColors.PRIMARY,
                                            ),
                                            ft.Text(
                                                "Search Tools",
                                                size=tokens.FONT_XS,
                                                weight=ft.FontWeight.W_600,
                                                color=AppColors.PRIMARY,
                                                font_family="Outfit",
                                            ),
                                            ft.Icon(
                                                ft.Icons.EXPAND_MORE_ROUNDED
                                                if not tools_expanded
                                                else ft.Icons.EXPAND_LESS_ROUNDED,
                                                size=16,
                                                color=AppColors.PRIMARY,
                                            ),
                                        ],
                                        spacing=4,
                                        alignment=ft.MainAxisAlignment.CENTER,
                                        tight=True,
                                    ),
                                    on_click=lambda e: set_tools_expanded(
                                        not tools_expanded
                                    ),
                                    padding=ft.Padding(12, 6, 12, 6),
                                    border_radius=tokens.RADIUS_FULL,
                                    border=ft.Border.all(
                                        1,
                                        ft.Colors.with_opacity(0.2, AppColors.PRIMARY),
                                    ),
                                    bgcolor=ft.Colors.with_opacity(
                                        0.06, AppColors.PRIMARY
                                    ),
                                    animate=ft.Animation(
                                        tokens.ANIM_FAST,
                                        "easeOut",
                                    ),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        # Tools panel
                        ft.Container(
                            content=ft.Row(
                                controls=tools_controls,
                                wrap=True,
                                spacing=tokens.SPACE_MD,
                                run_spacing=tokens.SPACE_SM,
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                            padding=ft.Padding(8, 10, 8, 10),
                            border_radius=tokens.RADIUS_MD,
                            bgcolor=ft.Colors.with_opacity(0.04, AppColors.PRIMARY),
                            border=ft.Border.all(
                                1, ft.Colors.with_opacity(0.08, AppColors.PRIMARY)
                            ),
                            visible=tools_expanded,
                            animate=ft.Animation(
                                tokens.ANIM_FAST,
                                "easeOut",
                            ),
                        ),
                        # Search button
                        ft.Row(
                            [
                                ft.FilledButton(
                                    content=ft.Row(
                                        [
                                            ft.Icon(
                                                ft.Icons.ALTERNATE_EMAIL_ROUNDED
                                                if is_email_mode
                                                else ft.Icons.SEARCH_ROUNDED,
                                                size=tokens.ICON_MD,
                                                color=ft.Colors.WHITE,
                                            ),
                                            ft.Text(
                                                "Search Emails"
                                                if is_email_mode
                                                else "Search Networks",
                                                size=tokens.FONT_MD,
                                                weight=ft.FontWeight.W_600,
                                                color=ft.Colors.WHITE,
                                                font_family="Outfit",
                                            ),
                                        ],
                                        spacing=8,
                                        tight=True,
                                    ),
                                    on_click=lambda _: _on_search(),
                                    style=ft.ButtonStyle(
                                        shape=ft.RoundedRectangleBorder(
                                            radius=tokens.RADIUS_FULL,
                                        ),
                                        bgcolor=AppColors.PRIMARY,
                                        padding=ft.Padding(32, 14, 32, 14),
                                    ),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM
                ),
            ),
            # Recent searches
            *(
                [
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text(
                                            "Recent",
                                            size=tokens.FONT_SM,
                                            weight=ft.FontWeight.W_600,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                            font_family="Outfit",
                                        ),
                                        ft.Container(expand=True),
                                        ft.Container(
                                            content=ft.Icon(
                                                ft.Icons.ARROW_FORWARD_ROUNDED,
                                                size=tokens.ICON_SM,
                                                color=ft.Colors.ON_SURFACE_VARIANT,
                                            ),
                                            padding=6,
                                            border_radius=tokens.RADIUS_SM,
                                            ink=True,
                                            tooltip="View all history",
                                            on_click=lambda _: (
                                                controller.show_history()
                                            ),
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                *recent_rows,
                            ],
                            spacing=tokens.SPACE_SM,
                        ),
                        padding=ft.Padding(
                            tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_SM
                        ),
                    )
                ]
                if recent_rows
                else []
            ),
            # Banner ad (after recent searches) — DDGS placement
            build_banner_ad(),
            # What Sherlock Can Do / Email Intelligence
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "What Sherlock Can Do"
                            if not is_email_mode
                            else "Email Intelligence",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            font_family="Outfit",
                        ),
                        ft.Container(height=tokens.SPACE_SM),
                        *[
                            ft.Container(
                                content=_feature_card(
                                    f["icon"], f["title"], f["desc"], f["color"]
                                ),
                                margin=ft.Margin(0, 0, 0, tokens.SPACE_SM),
                            )
                            for f in (
                                _FEATURES_EMAIL if is_email_mode else _FEATURES_USERNAME
                            )
                        ],
                    ],
                    spacing=0,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG
                ),
            ),
            # Banner ad (after features) — DDGS placement
            build_banner_ad(),
            # How It Works
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "How It Works",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            font_family="Outfit",
                        ),
                        ft.Container(height=tokens.SPACE_SM),
                        *[
                            _step_row(n, t, d)
                            for n, t, d in (
                                _STEPS_EMAIL if is_email_mode else _STEPS_USERNAME
                            )
                        ],
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG
                ),
            ),
            # Trust banner
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.SHIELD_ROUNDED,
                            size=20,
                            color=AppColors.PRIMARY,
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    "100% Privacy-First",
                                    size=tokens.FONT_SM,
                                    weight=ft.FontWeight.W_600,
                                    font_family="Outfit",
                                ),
                                ft.Text(
                                    "Your searches are never tracked or stored. "
                                    "Results come directly from public profiles.",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    font_family="Outfit",
                                    style=ft.TextStyle(height=1.3),
                                ),
                            ],
                            spacing=tokens.SPACE_XXS,
                            expand=True,
                        ),
                    ],
                    spacing=tokens.SPACE_MD,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD
                ),
                margin=ft.Margin(tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG),
                border_radius=tokens.RADIUS_LG,
                bgcolor=ft.Colors.with_opacity(0.06, AppColors.PRIMARY),
                border=ft.Border.all(
                    1, ft.Colors.with_opacity(0.15, AppColors.PRIMARY)
                ),
            ),
            ft.Container(height=80),  # Bottom nav bar spacing
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    return ft.Container(
        content=ft.Column(
            [content],
            expand=True,
            spacing=0,
        ),
        gradient=AppStyles.brand_gradient(_get_page())
        if hasattr(AppStyles, "brand_gradient")
        else None,
        expand=True,
    )
