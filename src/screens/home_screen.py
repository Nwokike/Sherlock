"""HomeScreen — compact search-first dashboard (DDGS style).

Search bar above the fold, category chips, search tools, recent searches,
feature cards, how it works, and trust banner.
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft
from flet import Control

from components.app_header import AppHeader
from components.banner_ad import build_banner_ad
from components.targets_card import TargetsCard
from core import tokens
from core.constants import (
    APP_NAME,
    APP_VERSION,
    MODE_EMAIL,
    MODE_USERNAME,
    MSG_OFFLINE,
    STORAGE_EMAIL_TIMEOUT,
    STORAGE_EXCLUSIONS,
    STORAGE_HISTORY,
    STORAGE_LOCAL_DB,
    STORAGE_NO_PASSWORD_RECOVERY,
    STORAGE_NSFW,
    STORAGE_SEARCH_MODE,
    STORAGE_TIMEOUT,
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


def _category_chip(
    icon: str,
    label: str,
    color: str,
    is_active: bool,
    on_click=None,
) -> ft.Control:
    """Material 3 Chip — replaces hand-rolled Container pill."""
    if on_click is not None:
        return ft.Chip(
            label=ft.Text(
                label,
                size=12,
                weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.W_400,
                font_family="Outfit",
            ),
            leading=ft.Icon(
                icon,
                size=15,
                color=color if is_active else ft.Colors.ON_SURFACE_VARIANT,
            ),
            selected=is_active,
            selected_color=ft.Colors.with_opacity(0.14, color),
            bgcolor=ft.Colors.with_opacity(0.08, color)
            if is_active
            else ft.Colors.TRANSPARENT,
            show_checkmark=False,
            on_select=on_click,
        )
    return ft.Chip(
        label=ft.Text(label, size=12, font_family="Outfit"),
        leading=ft.Icon(icon, size=15, color=ft.Colors.ON_SURFACE_VARIANT),
        disabled_color=ft.Colors.ON_SURFACE_VARIANT,
    )


@ft.memo
def _history_row(
    query: str,
    found: int,
    total: int,
    timestamp: str,
    mode: str = MODE_USERNAME,
    on_click=None,
) -> ft.Container:
    """Compact recent search row with mode icon."""
    is_email = mode == MODE_EMAIL or "@" in query
    icon = (
        ft.Icons.ALTERNATE_EMAIL_ROUNDED if is_email else ft.Icons.PERSON_SEARCH_ROUNDED
    )
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(icon, size=16, color=AppColors.PRIMARY),
                ft.Text(
                    query,
                    size=12,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                    font_family="Outfit",
                    weight=ft.FontWeight.W_500,
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


# ── Main screen ───────────────────────────────────────────────────────


@ft.component
def HomeScreen() -> Control:
    """Compact search-first home dashboard (DDGS style)."""
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    search_query, set_search_query = ft.use_state("")
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

    # ── Quick Setting Toggles ──

    def _cycle_timeout(e):
        timeouts = [5, 10, 15, 30, 60]
        curr = state.timeout
        next_val = (
            timeouts[(timeouts.index(curr) + 1) % len(timeouts)]
            if curr in timeouts
            else 10
        )
        state.timeout = next_val
        state.progress_version += 1

        async def _save():
            try:
                from services.storage_service import StorageService

                storage = StorageService(_get_page())
                await storage.set(STORAGE_TIMEOUT, str(next_val))
            except Exception:
                pass

        asyncio.create_task(_save())

    def _cycle_email_timeout(e):
        timeouts = [5, 10, 15, 30]
        curr = state.email_timeout
        next_val = (
            timeouts[(timeouts.index(curr) + 1) % len(timeouts)]
            if curr in timeouts
            else 10
        )
        state.email_timeout = next_val
        state.progress_version += 1

        async def _save():
            try:
                from services.storage_service import StorageService

                storage = StorageService(_get_page())
                await storage.set(STORAGE_EMAIL_TIMEOUT, str(next_val))
            except Exception:
                pass

        asyncio.create_task(_save())

    def _toggle_local_db(e):
        new_val = not state.use_local_db
        state.use_local_db = new_val
        state.progress_version += 1

        async def _save():
            try:
                from services.storage_service import StorageService

                storage = StorageService(_get_page())
                await storage.set(STORAGE_LOCAL_DB, "true" if new_val else "false")
                if controller.refresh_sites:
                    await controller.refresh_sites()
            except Exception:
                pass

        asyncio.create_task(_save())

    def _toggle_nsfw(e):
        new_val = not state.nsfw_enabled
        state.nsfw_enabled = new_val
        state.progress_version += 1

        async def _save():
            try:
                from services.storage_service import StorageService

                storage = StorageService(_get_page())
                await storage.set(STORAGE_NSFW, "true" if new_val else "false")
                if controller.refresh_sites:
                    await controller.refresh_sites()
            except Exception:
                pass

        asyncio.create_task(_save())

    def _toggle_exclusions(e):
        new_val = not state.ignore_exclusions
        state.ignore_exclusions = new_val
        state.progress_version += 1

        async def _save():
            try:
                from services.storage_service import StorageService

                storage = StorageService(_get_page())
                await storage.set(STORAGE_EXCLUSIONS, "true" if new_val else "false")
                if controller.refresh_sites:
                    await controller.refresh_sites()
            except Exception:
                pass

        asyncio.create_task(_save())

    def _toggle_password_recovery(e):
        new_val = not state.no_password_recovery
        state.no_password_recovery = new_val
        state.progress_version += 1

        async def _save():
            try:
                from services.storage_service import StorageService

                storage = StorageService(_get_page())
                await storage.set(
                    STORAGE_NO_PASSWORD_RECOVERY, "true" if new_val else "false"
                )
            except Exception:
                pass

        asyncio.create_task(_save())

    # ── Search logic ──

    def _on_search(e=None):
        query = search_query.strip() if search_query else ""
        if not query:
            return

        try:
            asyncio.create_task(ft.HapticFeedback().medium_impact())
        except Exception:
            pass

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

    def _maybe_switch_to_email(value: str):
        """Only auto-switch when pasted value is a clear email, not on typing."""
        from services.email_service import validate_email

        if state.search_mode == MODE_USERNAME and validate_email(value.strip()):
            _switch_mode(MODE_EMAIL)

    def _on_paste(e):
        async def _paste():
            try:
                clipboard = ft.Clipboard()
                text = await clipboard.get()
                if text:
                    value = text.strip()
                    set_search_query(value)
                    _maybe_switch_to_email(value)
            except Exception:
                pass

        asyncio.create_task(_paste())

    def _on_history_click(entry: dict):
        query = entry.get("query") or entry.get("username") or ""
        mode = entry.get("mode") or (MODE_EMAIL if "@" in query else MODE_USERNAME)
        if not query:
            return
        if state.search_mode != mode:
            _switch_mode(mode)
        set_search_query(query)
        controller.show_results()

        async def _run_hist():
            if mode == MODE_EMAIL:
                await controller.start_email_search(query)
            else:
                await controller.start_search(query)

        asyncio.create_task(_run_hist())

    # ── Load history on mount ──
    def _load_history():
        async def _fetch():
            try:
                from services.storage_service import (
                    StorageService,
                    load_history_entries,
                )

                storage = StorageService(_get_page())
                raw = await storage.get(STORAGE_HISTORY)
                entries = load_history_entries(raw)
                if entries:
                    state.history.clear()
                    state.history.extend(entries)
            except Exception:
                pass

        asyncio.create_task(_fetch())

    ft.use_effect(_load_history, [])

    # ── Build UI ──

    is_dark = _is_dark()

    # Mode-aware category / quick settings chips
    if is_email_mode:
        chips = [
            _category_chip(
                icon=ft.Icons.TIMER_OUTLINED,
                label=f"{state.email_timeout}s Timeout",
                color=AppColors.PRIMARY,
                is_active=True,
                on_click=_cycle_email_timeout,
            ),
            _category_chip(
                icon=ft.Icons.LOCK_RESET_ROUNDED
                if not state.no_password_recovery
                else ft.Icons.LOCK_OUTLINE_ROUNDED,
                label="PW Recovery: ON"
                if not state.no_password_recovery
                else "PW Recovery: OFF",
                color=AppColors.PRIMARY
                if not state.no_password_recovery
                else AppColors.GREY,
                is_active=not state.no_password_recovery,
                on_click=_toggle_password_recovery,
            ),
            _category_chip(
                icon=ft.Icons.CATEGORY_ROUNDED,
                label="121 Platforms (23 Categories)",
                color=AppColors.PRIMARY_LIGHT,
                is_active=False,
                on_click=None,
            ),
        ]
    else:
        chips = [
            _category_chip(
                icon=ft.Icons.TIMER_OUTLINED,
                label=f"{state.timeout}s Timeout",
                color=AppColors.PRIMARY,
                is_active=True,
                on_click=_cycle_timeout,
            ),
            _category_chip(
                icon=ft.Icons.FLASH_ON_ROUNDED,
                label="Offline DB" if state.use_local_db else "Online DB",
                color=AppColors.PRIMARY_LIGHT if state.use_local_db else AppColors.GREY,
                is_active=state.use_local_db,
                on_click=_toggle_local_db,
            ),
            _category_chip(
                icon=ft.Icons.BLOCK_ROUNDED,
                label="NSFW: ON" if state.nsfw_enabled else "NSFW: OFF",
                color=AppColors.ERROR if state.nsfw_enabled else AppColors.GREY,
                is_active=state.nsfw_enabled,
                on_click=_toggle_nsfw,
            ),
            _category_chip(
                icon=ft.Icons.SHIELD_ROUNDED,
                label="Exclusions: Ignore"
                if state.ignore_exclusions
                else "Exclusions: Active",
                color=AppColors.WARNING if state.ignore_exclusions else AppColors.GREY,
                is_active=state.ignore_exclusions,
                on_click=_toggle_exclusions,
            ),
        ]

    # Recent searches — read observable state directly (reactive), so
    # the three most recent sit on top.
    recent_rows = []
    if state.history:
        for entry in list(state.history[:3]):
            q = entry.get("query") or entry.get("username", "")
            found = entry.get("found", 0)
            total = entry.get("total", 0)
            ts = entry.get("timestamp", "")
            m = entry.get("mode", MODE_USERNAME)
            recent_rows.append(
                _history_row(
                    query=q,
                    found=found,
                    total=total,
                    timestamp=ts,
                    mode=m,
                    on_click=lambda _, e=entry: _on_history_click(e),
                )
            )

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
            AppHeader(
                _get_page(),
                title=APP_NAME,
                extra_actions=[version_chip],
                on_settings=lambda e: (
                    controller.show_settings() if controller.show_settings else None
                ),
            ),
            # Offline — subtle inline banner (visible only when offline)
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.WIFI_OFF_ROUNDED,
                            size=14,
                            color=ft.Colors.ON_ERROR_CONTAINER,
                        ),
                        ft.Text(
                            MSG_OFFLINE,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_ERROR_CONTAINER,
                            expand=True,
                        ),
                    ],
                    spacing=6,
                ),
                padding=ft.Padding(tokens.SPACE_LG, 6, tokens.SPACE_LG, 6),
                bgcolor=ft.Colors.ERROR_CONTAINER,
                visible=not state.is_online,
            ),
            # ── Mode Switcher — Material 3 SegmentedButton (centered) ──
            ft.Container(
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                ),
                alignment=ft.Alignment.CENTER,
                content=ft.SegmentedButton(
                    segments=[
                        ft.Segment(
                            value=MODE_USERNAME,
                            label=ft.Text("Username", font_family="Outfit"),
                            icon=ft.Icons.PERSON_SEARCH_ROUNDED,
                        ),
                        ft.Segment(
                            value=MODE_EMAIL,
                            label=ft.Text("Email", font_family="Outfit"),
                            icon=ft.Icons.ALTERNATE_EMAIL_ROUNDED,
                        ),
                    ],
                    selected=[state.search_mode],
                    on_change=lambda e: _switch_mode(
                        e.control.selected[0] if e.control.selected else MODE_USERNAME
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
                        else "Enter username (tip: user{?}name → 3 variants)..."
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
                    controls=[
                        ft.ListTile(
                            title=ft.Text(
                                e.get("query", ""),
                                size=tokens.FONT_SM,
                                font_family="Outfit",
                            ),
                            leading=ft.Icon(
                                ft.Icons.HISTORY_ROUNDED,
                                size=16,
                                color=AppColors.PRIMARY,
                            ),
                            on_click=lambda _, entry=e: _on_history_click(entry),
                        )
                        for e in (list(state.history[:5]) if state.history else [])
                    ]
                    if state.history
                    else [],
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
            # Category / Quick Setting Chips (horizontal scroll, wrap on narrow)
            ft.Container(
                content=ft.Row(
                    chips,
                    wrap=True,
                    scroll=ft.ScrollMode.AUTO,
                    spacing=tokens.SPACE_SM,
                    alignment=ft.MainAxisAlignment.START,
                    run_spacing=tokens.SPACE_SM,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                ),
            ),
            # Search button
            ft.Container(
                content=ft.Row(
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
