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
    ERR_INVALID_EMAIL,
    MODE_EMAIL,
    MODE_USERNAME,
    MSG_OFFLINE,
    MSG_SEARCH_OFFLINE,
    STORAGE_EMAIL_METHOD_FILTER,
    STORAGE_EMAIL_TIMEOUT,
    STORAGE_EXCLUSIONS,
    STORAGE_HISTORY,
    STORAGE_NO_PASSWORD_RECOVERY,
    STORAGE_NSFW,
    STORAGE_RECURSIVE_SEARCH,
    STORAGE_SCAN_DEPTH,
    STORAGE_SEARCH_MODE,
    STORAGE_TIMEOUT,
    STORAGE_USE_CURL_CFFI,
)
from core.notify import show_snack
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
        "title": "Hunt Across 3,300+ Networks",
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
        "desc": "Export reports as PDF dossiers, XMind mind maps, CSV/JSON, or Text lists.",
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
    ("2", "Scan", "Sherlock checks 3,300+ platforms simultaneously"),
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
    # Informational — stay enabled with explicit styling (never disabled grey on grey)
    return ft.Chip(
        label=ft.Text(
            label,
            size=12,
            color=ft.Colors.ON_SURFACE,
            font_family="Outfit",
        ),
        leading=ft.Icon(icon, size=15, color=ft.Colors.ON_SURFACE_VARIANT),
        bgcolor=ft.Colors.TRANSPARENT,
        border_side=ft.BorderSide(
            1, ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE)
        ),
        show_checkmark=False,
        on_select=lambda e: None,
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
def HomeScreen(banner: Control | None = None) -> Control:
    """Compact search-first home dashboard (DDGS style)."""
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    search_query, set_search_query = ft.use_state("")
    theme_version, set_theme_version = ft.use_state(0)

    # Mode is driven by observable state so it persists across screens
    is_email_mode = state.search_mode == MODE_EMAIL

    from flet import context as flet_context

    def _get_page():
        try:
            return flet_context.page
        except Exception:
            return None

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

    def _cycle_scan_depth(e):
        depths = ["all", "1000", "500"]
        curr = state.scan_depth or "all"
        next_val = (
            depths[(depths.index(curr) + 1) % len(depths)] if curr in depths else "all"
        )
        state.scan_depth = next_val
        state.progress_version += 1

        async def _save():
            try:
                from services.storage_service import StorageService

                storage = StorageService(_get_page())
                await storage.set(STORAGE_SCAN_DEPTH, next_val)
                if controller.refresh_sites:
                    await controller.refresh_sites()
            except Exception:
                pass

        asyncio.create_task(_save())

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

    def _toggle_recursive_search(e):
        new_val = not getattr(state, "recursive_search", False)
        state.recursive_search = new_val
        state.progress_version += 1

        async def _save():
            try:
                from services.storage_service import StorageService

                storage = StorageService(_get_page())
                await storage.set(
                    STORAGE_RECURSIVE_SEARCH, "true" if new_val else "false"
                )
            except Exception:
                pass

        asyncio.create_task(_save())

    def _toggle_nsfw(e):
        new_val = not state.nsfw_enabled
        state.nsfw_enabled = new_val
        state.safe_search = not new_val
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

    def _cycle_email_method_filter(e):
        methods = ["all", "register", "login", "recovery"]
        curr = state.email_method_filter or "all"
        next_val = (
            methods[(methods.index(curr) + 1) % len(methods)]
            if curr in methods
            else "all"
        )
        state.email_method_filter = next_val
        state.progress_version += 1

        async def _save():
            try:
                from services.storage_service import StorageService

                storage = StorageService(_get_page())
                await storage.set(STORAGE_EMAIL_METHOD_FILTER, next_val)
            except Exception:
                pass

        asyncio.create_task(_save())

    def _cycle_email_timeout(e):
        timeouts = [5, 10, 15, 30]
        curr = state.email_timeout
        next_val = (
            timeouts[(timeouts.index(curr) + 1) % len(timeouts)]
            if curr in timeouts
            else 30
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

    def _toggle_use_curl_cffi(e):
        new_val = not getattr(state, "use_curl_cffi", True)
        state.use_curl_cffi = new_val
        state.progress_version += 1

        async def _save():
            try:
                from services.storage_service import StorageService

                storage = StorageService(_get_page())
                await storage.set(STORAGE_USE_CURL_CFFI, "true" if new_val else "false")
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

        # Offline gate on client submit
        if not state.is_online:
            page = _get_page()
            if page:
                show_snack(page, MSG_SEARCH_OFFLINE, bgcolor=AppColors.ERROR)
            return

        from services.email_service import validate_email

        if state.search_mode == MODE_EMAIL and not validate_email(query):
            page = _get_page()
            if page:
                show_snack(page, ERR_INVALID_EMAIL, bgcolor=AppColors.ERROR)
            return

        target_mode = state.search_mode

        async def _run():
            controller.show_results()
            if target_mode == MODE_EMAIL:
                await controller.start_email_search(query)
            else:
                await controller.start_search(query)

        asyncio.create_task(_run())

    def _on_input_change(e):
        value = e.control.value or ""
        set_search_query(value)

    def _maybe_switch_mode(value: str):
        """Auto-switch mode on paste: email -> Email mode, plain username -> Username mode."""
        from services.email_service import validate_email

        val = value.strip()
        if not val:
            return
        if state.search_mode == MODE_USERNAME and validate_email(val):
            _switch_mode(MODE_EMAIL)
        elif state.search_mode == MODE_EMAIL and "@" not in val:
            _switch_mode(MODE_USERNAME)

    def _on_paste(e):
        async def _paste():
            try:
                clipboard = ft.Clipboard()
                text = await clipboard.get()
                if text:
                    value = text.strip()
                    set_search_query(value)
                    _maybe_switch_mode(value)
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

        # 1. Try instant load from cache
        if controller.open_cached_result and controller.open_cached_result(query, mode):
            return

        # 2. Fallback to fresh scan if not in cache
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
        method_labels = {
            "all": "Method: All",
            "register": "Method: Register",
            "login": "Method: Login",
            "recovery": "Method: Recovery",
        }
        curr_method = getattr(state, "email_method_filter", "all")
        chips = [
            _category_chip(
                icon=ft.Icons.CATEGORY_ROUNDED,
                label=method_labels.get(curr_method, "Method: All"),
                color=AppColors.PRIMARY,
                is_active=curr_method != "all",
                on_click=_cycle_email_method_filter,
            ),
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
                icon=ft.Icons.SECURITY_ROUNDED,
                label="Stealth: Chrome 124"
                if getattr(state, "use_curl_cffi", True)
                else "Stealth: Standard",
                color=AppColors.PRIMARY_LIGHT
                if getattr(state, "use_curl_cffi", True)
                else AppColors.GREY,
                is_active=getattr(state, "use_curl_cffi", True),
                on_click=_toggle_use_curl_cffi,
            ),
        ]
    else:
        depth_labels = {
            "all": "Scope: All 3.3k",
            "1000": "Scope: Top 1k",
            "500": "Scope: Top 500",
        }
        curr_depth = getattr(state, "scan_depth", "all")
        chips = [
            _category_chip(
                icon=ft.Icons.TRAVEL_EXPLORE_ROUNDED,
                label=depth_labels.get(curr_depth, "Scope: All 3.3k"),
                color=AppColors.PRIMARY,
                is_active=curr_depth != "all",
                on_click=_cycle_scan_depth,
            ),
            _category_chip(
                icon=ft.Icons.TIMER_OUTLINED,
                label=f"{state.timeout}s Timeout",
                color=AppColors.PRIMARY,
                is_active=True,
                on_click=_cycle_timeout,
            ),
            _category_chip(
                icon=ft.Icons.SAVED_SEARCH_ROUNDED,
                label="Recursive: ON"
                if getattr(state, "recursive_search", False)
                else "Recursive: OFF",
                color=AppColors.PRIMARY_LIGHT
                if getattr(state, "recursive_search", False)
                else AppColors.GREY,
                is_active=getattr(state, "recursive_search", False),
                on_click=_toggle_recursive_search,
            ),
            _category_chip(
                icon=ft.Icons.BLOCK_ROUNDED,
                label="Adult Sites: ON" if state.nsfw_enabled else "Adult Sites: OFF",
                color=AppColors.PRIMARY if state.nsfw_enabled else AppColors.GREY,
                is_active=state.nsfw_enabled,
                on_click=_toggle_nsfw,
            ),
            _category_chip(
                icon=ft.Icons.SHIELD_ROUNDED,
                label="Disabled Sites: ON"
                if state.ignore_exclusions
                else "Disabled Sites: OFF",
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

    # ── Assemble ──

    header_controls: list[Control] = [
        # Compact header
        AppHeader(
            _get_page(),
            title=APP_NAME,
            on_settings=lambda e: (
                controller.show_settings() if controller.show_settings else None
            ),
        ),
    ]
    if banner:
        header_controls.append(banner)

    content = ft.Column(
        controls=[
            *header_controls,
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
            # ── Mode Switcher (Username / Email) — KTV Player pill style ──
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
                                ft.Icons.ALTERNATE_EMAIL_ROUNDED
                                if is_email_mode
                                else ft.Icons.HISTORY_ROUNDED,
                                size=16,
                                color=AppColors.PRIMARY,
                            ),
                            on_click=lambda _, entry=e: _on_history_click(entry),
                        )
                        for e in (
                            [
                                item
                                for item in (state.history or [])
                                if (
                                    item.get("mode")
                                    or (
                                        MODE_EMAIL
                                        if "@" in item.get("query", "")
                                        else MODE_USERNAME
                                    )
                                )
                                == state.search_mode
                            ][:5]
                        )
                    ],
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
            # Category / Quick Setting Chips — single horizontal track that
            # scrolls on narrow screens (never wraps to a second line).
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
