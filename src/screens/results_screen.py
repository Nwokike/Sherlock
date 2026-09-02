"""ResultsScreen — live search results for both username and email OSINT.

@ft.component — reads observable state.progress_version to re-render on each tick.

In username mode: shows Found / Not Found / Errors tabs driven by sherlock-project.
In email mode:    shows Found / Not Found / Rate Limited tabs driven by holehe.

Both modes support: filter bar, stat cards, cancel, export.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import NamedTuple

import flet as ft
from flet import Control

from components.banner_ad import build_banner_ad
from components.profile_detail_dialog import show_profile_detail_dialog
from components.result_card import ResultCard
from components.stat_card import StatCard
from core import tokens
from core.constants import ERR_OPEN_URL, MODE_EMAIL
from core.theme import AppColors
from hooks.use_debounce import use_debounce
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("ResultsScreen")


class _UsernameViewData(NamedTuple):
    """Normalized snapshot for username-mode rendering.

    Shields the render path from cross-mode progress objects: a stale
    EmailSearchProgress must never be dereferenced as SearchProgress
    (total_sites/checked_sites/site_name AttributeErrors during render
    kill Flet's updates scheduler task, freezing the whole UI with no
    visible log — the v2.0.0 email→username hang).
    """

    found: list
    not_found: list
    errors: list
    total: int
    checked: int
    has_progress: bool
    is_cancelled: bool
    is_running: bool
    username: str


def _resolve_username_view_data(state) -> _UsernameViewData:
    """Read username-mode data without ever raising during render."""
    progress = state.search_progress
    has_progress = progress is not None and hasattr(progress, "total_sites")

    if has_progress:
        found = list(progress.found)
        not_found = list(progress.not_found)
        errors = list(progress.errors)
        total = progress.total_sites or state.sites_total or 3300
        checked = progress.checked_sites
        is_cancelled = bool(getattr(progress, "is_cancelled", False))
        is_running = bool(getattr(progress, "is_running", False))
        username = getattr(progress, "username", "") or state.current_username
    else:
        # Fall back to the last completed username scan (dict of
        # site_name → SiteResult), or an empty idle view.
        last = state.last_results or {}
        found = [r for r in last.values() if getattr(r, "status", "") == "Claimed"]
        not_found = [
            r
            for r in last.values()
            if getattr(r, "status", "") in ("Available", "Illegal")
        ]
        errors = [
            r
            for r in last.values()
            if getattr(r, "status", "") not in ("Claimed", "Available", "Illegal")
        ]
        total = state.sites_total or len(last) or 3300
        checked = len(last)
        is_cancelled = False
        is_running = False
        username = state.last_results_username or state.current_username

    return _UsernameViewData(
        found=found,
        not_found=not_found,
        errors=errors,
        total=total,
        checked=checked,
        has_progress=has_progress,
        is_cancelled=is_cancelled,
        is_running=is_running,
        username=username,
    )


def _build_result_list(
    items,
    empty_title: str,
    empty_msg: str,
    build_card,
    debounced_filter: str = "",
    live_cap: int = 0,
) -> Control:
    """Shared list builder with virtualization for large result sets.

    `live_cap` bounds how many cards get BUILT while a scan is running:
    every card is ~12-15 controls, and Flet re-renders + re-diffs this
    whole list on each ~2Hz progress tick, so an uncapped list of hundreds
    of cards saturated the main loop (the scan freeze). The overflow is
    shown as a footer; the full list renders when the scan completes.
    """
    if not items:
        from components.empty_state import EmptyState

        return EmptyState(
            title="No matches" if debounced_filter else empty_title,
            message=f'No results match "{debounced_filter}"'
            if debounced_filter
            else empty_msg,
            icon=ft.Icons.SEARCH_OFF_ROUNDED,
        )
    shown = items
    footer = None
    if live_cap and len(items) > live_cap:
        shown = items[:live_cap]
        footer = ft.Container(
            content=ft.Text(
                f"+ {len(items) - live_cap} more — scan in progress",
                size=12,
                italic=True,
                color=ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE),
                text_align=ft.TextAlign.CENTER,
            ),
            padding=ft.Padding(0, 10, 0, 14),
            alignment=ft.Alignment.CENTER,
        )
    shown_controls = [build_card(r) for r in shown]
    if footer:
        shown_controls.append(footer)
    # Use ListView with build_controls_on_demand for virtualization on large lists (400+).
    return ft.ListView(
        controls=shown_controls,
        spacing=0,
        expand=True,
        build_controls_on_demand=True,
    )


@ft.component
def ResultsScreen() -> Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    # Force re-render on each progress_version bump
    _ = state.progress_version

    is_email_mode = state.search_mode == MODE_EMAIL

    filter_query, set_filter_query = ft.use_state("")
    debounced_filter = use_debounce(filter_query, 250)

    active_progress = state.search_progress
    # Typed snapshot for username mode — never dereference the raw
    # progress object for username rendering (see _resolve_username_view_data).
    username_view = _resolve_username_view_data(state)
    is_running = (
        active_progress.is_running
        if (active_progress is not None and hasattr(active_progress, "is_running"))
        else False
    )

    def _open_url(url: str):
        async def _launch():
            from core.notify import show_snack
            from flet import context

            try:
                await ft.UrlLauncher().launch_url(url)
            except Exception as exc:
                logger.warning("Failed to launch URL %s: %s", url, exc)
                page = context.page
                if page:
                    show_snack(page, ERR_OPEN_URL, bgcolor=AppColors.ERROR)

        asyncio.create_task(_launch())

    def _show_username_details(r):
        from flet import context

        page = context.page
        if not page:
            return
        with contextlib.suppress(Exception):
            asyncio.create_task(ft.HapticFeedback().light_impact())
        with contextlib.suppress(Exception):
            page.pop_dialog()
        enrich = (
            state.enrichments.get(r.url_user or r.url_main or "", None)
            if state.enrichments
            else None
        )
        show_profile_detail_dialog(
            page=page,
            site_name=r.site_name,
            status=r.status,
            mode="username",
            target_query=state.current_username or state.last_results_username,
            url_user=r.url_user,
            url_main=r.url_main,
            query_time=r.query_time,
            enrichment=enrich,
        )

    def _show_email_details(r):
        from flet import context

        page = context.page
        if not page:
            return
        with contextlib.suppress(Exception):
            asyncio.create_task(ft.HapticFeedback().light_impact())
        with contextlib.suppress(Exception):
            page.pop_dialog()
        domain_url = f"https://{r.get('domain', '')}" if r.get("domain") else None
        show_profile_detail_dialog(
            page=page,
            site_name=r.get("name", "unknown"),
            status="Claimed"
            if r.get("exists")
            else ("Error" if r.get("rateLimit") else "Available"),
            mode="email",
            target_query=state.email_results_address
            or (active_progress.email if hasattr(active_progress, "email") else None),
            url_user=None,
            url_main=domain_url,
            email_recovery=r.get("emailrecovery"),
            phone_number=r.get("phoneNumber"),
            others=r.get("others"),
            method=r.get("method", ""),
            rate_limit=r.get("rateLimit", False),
            frequent_rate_limit=r.get("frequent_rate_limit", False),
        )

    def _filter_by_name(items, key_fn):
        q = debounced_filter.strip().lower()
        if not q:
            return items
        return [r for r in items if q in key_fn(r).lower()]

    # ── Build content based on mode ───────────────────────────────────
    if is_email_mode:
        if active_progress and hasattr(active_progress, "checked_modules"):

            def _to_dict(r):
                return {
                    "name": r.name,
                    "domain": r.domain,
                    "method": r.method,
                    "exists": r.exists,
                    "rateLimit": r.rate_limit,
                    "unavailable": r.unavailable,
                    "frequent_rate_limit": r.frequent_rate_limit,
                    "emailrecovery": r.email_recovery,
                    "phoneNumber": r.phone_number,
                    "others": r.others,
                }

            raw_found = [_to_dict(r) for r in active_progress.found]
            raw_not_found = [_to_dict(r) for r in active_progress.not_found]
            raw_rate_limited = [_to_dict(r) for r in active_progress.rate_limited]
            raw_unavailable = [_to_dict(r) for r in active_progress.unavailable]
            total = active_progress.total_modules or state.email_total_modules or 121
            checked = active_progress.checked_modules
        else:
            all_email = list(state.email_results) if state.email_results else []
            raw_found = [
                r for r in all_email if r.get("exists") and not r.get("rateLimit")
            ]
            raw_not_found = [
                r
                for r in all_email
                if not r.get("exists")
                and not r.get("rateLimit")
                and not r.get("unavailable")
            ]
            raw_rate_limited = [
                r for r in all_email if r.get("rateLimit") and not r.get("unavailable")
            ]
            raw_unavailable = [r for r in all_email if r.get("unavailable")]
            total = state.email_total_modules or len(all_email) or 121
            checked = total if all_email else 0

        def _make_email_card(r):
            if r.get("exists"):
                status = "Claimed"
            elif r.get("rateLimit"):
                status = "Error"
            elif r.get("unavailable"):
                status = "Unavailable"
            else:
                status = "Available"
            return ResultCard(
                site_name=r.get("name", "unknown"),
                status=status,
                url_user=None,
                url_main=f"https://{r.get('domain', '')}" if r.get("domain") else None,
                on_open=lambda url: _open_url(url),
                on_tap=lambda item=r: _show_email_details(item),
                email_recovery=r.get("emailrecovery"),
                phone_number=r.get("phoneNumber"),
                others=r.get("others"),
                method=r.get("method", ""),
                rate_limit=r.get("rateLimit", False),
                frequent_rate_limit=r.get("frequent_rate_limit", False),
            )

        # Apply method + only-found filters
        method_filter = getattr(state, "email_method_filter", "all")
        only_found = getattr(state, "email_only_found", False)

        def _apply_email_extras(items):
            out = items
            if method_filter != "all":
                out = [r for r in out if r.get("method", "") == method_filter]
            return out

        raw_found = _apply_email_extras(raw_found)
        raw_not_found = [] if only_found else _apply_email_extras(raw_not_found)
        raw_rate_limited = [] if only_found else _apply_email_extras(raw_rate_limited)
        raw_unavailable = [] if only_found else _apply_email_extras(raw_unavailable)

        email_found_filtered = _filter_by_name(
            raw_found, lambda r: f"{r.get('name', '')} {r.get('domain', '')}"
        )
        email_not_found_filtered = _filter_by_name(
            raw_not_found, lambda r: f"{r.get('name', '')} {r.get('domain', '')}"
        )
        email_rate_limited_filtered = _filter_by_name(
            raw_rate_limited, lambda r: f"{r.get('name', '')} {r.get('domain', '')}"
        )
        email_unavailable_filtered = _filter_by_name(
            raw_unavailable, lambda r: f"{r.get('name', '')} {r.get('domain', '')}"
        )

        tabs = ft.Tabs(
            selected_index=0,
            length=4,
            content=ft.Column(
                [
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label=f"Found ({len(email_found_filtered)})"),
                            ft.Tab(
                                label=f"Not Found ({len(email_not_found_filtered)})"
                            ),
                            ft.Tab(
                                label=f"Rate Limited ({len(email_rate_limited_filtered)})"
                            ),
                            ft.Tab(
                                label=f"Unavailable ({len(email_unavailable_filtered)})"
                            ),
                        ],
                        scrollable=False,
                        indicator_color=ft.Colors.PRIMARY,
                        label_color=ft.Colors.PRIMARY,
                        unselected_label_color=ft.Colors.with_opacity(
                            tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                        ),
                        label_padding=ft.Padding(
                            tokens.SPACE_LG,
                            tokens.SPACE_SM,
                            tokens.SPACE_LG,
                            tokens.SPACE_SM,
                        ),
                    ),
                    ft.TabBarView(
                        controls=[
                            _build_result_list(
                                email_found_filtered,
                                "No registrations found",
                                "No platforms matched this email address.",
                                _make_email_card,
                                debounced_filter,
                                live_cap=60 if is_running else 0,
                            ),
                            _build_result_list(
                                email_not_found_filtered,
                                "All found",
                                "Every platform confirmed this email is registered.",
                                _make_email_card,
                                debounced_filter,
                                live_cap=60 if is_running else 0,
                            ),
                            _build_result_list(
                                email_rate_limited_filtered,
                                "No rate limits",
                                "All checks completed without rate limiting.",
                                _make_email_card,
                                debounced_filter,
                                live_cap=60 if is_running else 0,
                            ),
                            _build_result_list(
                                email_unavailable_filtered,
                                "No unavailable platforms",
                                "Every platform check is currently supported.",
                                _make_email_card,
                                debounced_filter,
                                live_cap=60 if is_running else 0,
                            ),
                        ],
                        expand=True,
                    ),
                ],
                expand=True,
                spacing=0,
            ),
            expand=True,
        )
        stats_row = ft.Row(
            controls=[
                StatCard("Found", str(len(raw_found)), AppColors.SUCCESS),
                StatCard(
                    "Not Found",
                    str(len(raw_not_found)),
                    ft.Colors.with_opacity(tokens.OPACITY_DIM, ft.Colors.ON_SURFACE),
                ),
                StatCard("Rate Ltd", str(len(raw_rate_limited)), AppColors.WARNING),
                StatCard("Unavail", str(len(raw_unavailable)), AppColors.ERROR),
            ],
            spacing=tokens.SPACE_SM,
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        )
        if active_progress and getattr(active_progress, "is_cancelled", False):
            progress_label = f"Cancelled — {checked}/{total} checked"
        else:
            pct = int(checked / max(total, 1) * 100)
            progress_label = f"Checking {checked}/{total} platforms ({pct}%)..."

        def cancel_callback(e):
            controller.cancel_email_search()

    else:

        def _make_username_card(r):
            return ResultCard(
                site_name=getattr(r, "site_name", "unknown"),
                status=getattr(r, "status", "Claimed"),
                url_user=getattr(r, "url_user", None),
                url_main=getattr(r, "url_main", None),
                query_time=getattr(r, "query_time", None),
                on_open=lambda url: _open_url(url),
                on_tap=lambda item=r: _show_username_details(item),
                enrichment=state.enrichments.get(
                    getattr(r, "url_user", None) or getattr(r, "url_main", None) or "",
                    None,
                )
                if state.enrichments
                else None,
                tags=tuple(getattr(r, "tags", None) or ()),
            )

        def _username_filter_key(r):
            parts = [
                getattr(r, "site_name", "") or "",
                getattr(r, "url_user", "") or "",
                getattr(r, "url_main", "") or "",
            ]
            t_list = getattr(r, "tags", None)
            if t_list:
                parts.extend(t_list)
            u_key = getattr(r, "url_user", None) or getattr(r, "url_main", None) or ""
            enrich = state.enrichments.get(u_key) if state.enrichments else None
            if enrich and isinstance(enrich, dict):
                if enrich.get("name"):
                    parts.append(str(enrich["name"]))
                if enrich.get("fullname"):
                    parts.append(str(enrich["fullname"]))
            return " ".join(parts)

        found_items = _filter_by_name(username_view.found, _username_filter_key)
        notfound_items = _filter_by_name(username_view.not_found, _username_filter_key)
        error_items = _filter_by_name(username_view.errors, _username_filter_key)
        total = username_view.total
        checked = username_view.checked

        tabs = ft.Tabs(
            selected_index=0,
            length=3,
            content=ft.Column(
                [
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label=f"Found ({len(found_items)})"),
                            ft.Tab(label=f"Not Found ({len(notfound_items)})"),
                            ft.Tab(label=f"Errors ({len(error_items)})"),
                        ],
                        scrollable=False,
                        indicator_color=ft.Colors.PRIMARY,
                        label_color=ft.Colors.PRIMARY,
                        unselected_label_color=ft.Colors.with_opacity(
                            tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                        ),
                        label_padding=ft.Padding(
                            tokens.SPACE_LG,
                            tokens.SPACE_SM,
                            tokens.SPACE_LG,
                            tokens.SPACE_SM,
                        ),
                    ),
                    ft.TabBarView(
                        controls=[
                            _build_result_list(
                                found_items,
                                "No matches" if debounced_filter else "No results yet",
                                f'No results match "{debounced_filter}"'
                                if debounced_filter
                                else "Results will appear as the scan progresses.",
                                _make_username_card,
                                debounced_filter,
                                live_cap=60 if is_running else 0,
                            ),
                            _build_result_list(
                                notfound_items,
                                "No matches" if debounced_filter else "No results yet",
                                f'No results match "{debounced_filter}"'
                                if debounced_filter
                                else "Results will appear as the scan progresses.",
                                _make_username_card,
                                debounced_filter,
                                live_cap=60 if is_running else 0,
                            ),
                            _build_result_list(
                                error_items,
                                "No matches" if debounced_filter else "No results yet",
                                f'No results match "{debounced_filter}"'
                                if debounced_filter
                                else "Results will appear as the scan progresses.",
                                _make_username_card,
                                debounced_filter,
                                live_cap=60 if is_running else 0,
                            ),
                        ],
                        expand=True,
                    ),
                ],
                expand=True,
                spacing=0,
            ),
            expand=True,
        )
        stats_row = ft.Row(
            controls=[
                StatCard("Found", str(len(username_view.found)), AppColors.SUCCESS),
                StatCard(
                    "Not Found",
                    str(len(username_view.not_found)),
                    ft.Colors.with_opacity(tokens.OPACITY_DIM, ft.Colors.ON_SURFACE),
                ),
                StatCard("Errors", str(len(username_view.errors)), AppColors.WARNING),
                StatCard("Total", str(total), ft.Colors.PRIMARY),
            ],
            spacing=tokens.SPACE_SM,
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        )
        if username_view.is_cancelled:
            progress_label = f"Cancelled — {checked}/{total} checked"
        else:
            pct = int(checked / max(total, 1) * 100)
            progress_label = f"Checking {checked}/{total} sites ({pct}%)..."

        def cancel_callback(e):
            controller.cancel_search()

    stats_card = ft.Container(
        content=stats_row,
        padding=tokens.SPACE_MD,
        border_radius=tokens.RADIUS_LG,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(
            width=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        margin=ft.Margin(
            tokens.SPACE_XL, tokens.SPACE_MD, tokens.SPACE_XL, tokens.SPACE_SM
        ),
    )
    # Email method filter chips (only in email mode)
    method_filter_row = ft.Container(width=0, height=0)
    if is_email_mode:
        method_filter = getattr(state, "email_method_filter", "all")

        def _method_chip(value, label):
            return ft.Chip(
                label=ft.Text(label, size=11, font_family="Outfit"),
                selected=method_filter == value,
                show_checkmark=False,
                on_select=lambda e, v=value: _set_method_filter(v),
            )

        def _set_method_filter(v):
            state.email_method_filter = v
            state.progress_version += 1
            try:
                from services.storage_service import StorageService
                from flet import context
                import asyncio as _asyncio

                s = StorageService(context.page)
                _asyncio.create_task(s.set("sherlock_email_method_filter", v))
            except Exception:
                pass

        method_filter_row = ft.Container(
            content=ft.Row(
                controls=[
                    _method_chip("all", "All"),
                    _method_chip("register", "Register"),
                    _method_chip("login", "Login"),
                    _method_chip("password recovery", "Recovery"),
                ],
                spacing=tokens.SPACE_XS,
                wrap=True,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding(tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, 0),
        )
    filter_hint = (
        "Filter by platform, domain, or recovery hint..."
        if is_email_mode
        else "Filter by network, domain, tag, or name..."
    )
    filter_box = ft.Container(
        content=ft.TextField(
            value=filter_query,
            hint_text=filter_hint,
            prefix_icon=ft.Icons.FILTER_LIST_ROUNDED,
            border_radius=tokens.RADIUS_MD,
            border_width=1,
            border_color=ft.Colors.with_opacity(
                tokens.OPACITY_MEDIUM, ft.Colors.OUTLINE
            ),
            focused_border_color=ft.Colors.PRIMARY,
            bgcolor=ft.Colors.SURFACE,
            filled=True,
            on_change=lambda e: set_filter_query(e.control.value),
            text_size=tokens.FONT_SM,
            content_padding=tokens.SPACE_SM,
            height=44,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_XL,
            right=tokens.SPACE_XL,
            top=tokens.SPACE_XS,
            bottom=tokens.SPACE_SM,
        ),
    )
    progress_section = ft.Container(width=0, height=0)
    if is_running and active_progress:
        progress_val = (checked / max(total, 1)) if total > 0 else None
        progress_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.ProgressBar(
                        value=progress_val,
                        color=ft.Colors.PRIMARY,
                        bgcolor=ft.Colors.with_opacity(
                            tokens.OPACITY_LIGHT, ft.Colors.PRIMARY
                        ),
                        height=tokens.PROGRESS_BAR_HEIGHT,
                    ),
                    ft.Row(
                        controls=[
                            ft.Text(
                                progress_label,
                                size=tokens.FONT_SM,
                                color=ft.Colors.with_opacity(
                                    tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                                ),
                            ),
                            ft.Container(expand=True),
                            ft.TextButton(
                                content=ft.Text(
                                    "Cancel",
                                    size=tokens.FONT_SM,
                                    color=AppColors.ERROR,
                                    weight=ft.FontWeight.W_600,
                                ),
                                on_click=cancel_callback,
                            ),
                        ]
                    ),
                ],
                spacing=tokens.SPACE_XS,
            ),
            padding=ft.Padding(
                left=tokens.SPACE_XL,
                right=tokens.SPACE_XL,
                top=tokens.SPACE_SM,
                bottom=0,
            ),
        )

    return ft.Column(
        controls=[
            progress_section,
            stats_card,
            method_filter_row,
            filter_box,
            tabs,
            build_banner_ad(),
        ],
        expand=True,
        spacing=0,
    )
