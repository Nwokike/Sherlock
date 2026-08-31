"""ResultsScreen — live search results for both username and email OSINT.

@ft.component — reads observable state.progress_version to re-render on each tick.

In username mode: shows Found / Not Found / Errors tabs driven by sherlock-project.
In email mode:    shows Found / Not Found / Rate Limited tabs driven by holehe.

Both modes support: filter bar, stat cards, cancel, export.
Email mode additionally shows: recovery email/phone hints, method badge, others data.
"""

from __future__ import annotations

import asyncio
import logging

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


@ft.component
def ResultsScreen() -> Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    # Force re-render on each progress_version bump
    _ = state.progress_version

    is_email_mode = state.search_mode == MODE_EMAIL

    filter_query, set_filter_query = ft.use_state("")
    debounced_filter = use_debounce(filter_query, 250)

    # ── Get active progress ────────────────────────────────────────────
    active_progress = state.search_progress
    is_running = active_progress.is_running if active_progress else False

    # ── URL opener ────────────────────────────────────────────────────
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

    # ── Detail Dialog Openers ─────────────────────────────────────────
    def _show_username_details(r):
        from flet import context

        page = context.page
        if not page:
            return
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

    # ── Username mode ─────────────────────────────────────────────────
    def _filter_username_items(items):
        q = debounced_filter.strip().lower()
        if not q:
            return items
        return [r for r in items if q in r.site_name.lower()]

    def _build_username_result_list(items):
        if not items:
            from components.empty_state import EmptyState

            return EmptyState(
                title="No matches" if debounced_filter else "No results yet",
                message=(
                    f'No results match "{debounced_filter}"'
                    if debounced_filter
                    else "Results will appear as the scan progresses."
                ),
                icon=ft.Icons.SEARCH_OFF_ROUNDED,
            )
        return ft.Column(
            controls=[
                ResultCard(
                    site_name=r.site_name,
                    status=r.status,
                    url_user=r.url_user,
                    url_main=r.url_main,
                    query_time=r.query_time,
                    on_open=lambda url: _open_url(url),
                    on_tap=lambda item=r: _show_username_details(item),
                    enrichment=state.enrichments.get(
                        r.url_user or r.url_main or "", None
                    )
                    if state.enrichments
                    else None,
                )
                for r in items
            ],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    # ── Email mode ────────────────────────────────────────────────────
    def _filter_email_items(items):
        q = debounced_filter.strip().lower()
        if not q:
            return items
        return [
            r
            for r in items
            if q in r.get("name", "").lower() or q in r.get("domain", "").lower()
        ]

    def _build_email_result_list(items, tab_type: str):
        """Build email result list. tab_type: 'found' | 'not_found' | 'rate_limited'"""
        if not items:
            from components.empty_state import EmptyState

            empty_msgs = {
                "found": (
                    "No registrations found",
                    "No platforms matched this email address.",
                ),
                "not_found": (
                    "All found",
                    "Every platform confirmed this email is registered.",
                ),
                "rate_limited": (
                    "No rate limits",
                    "All checks completed without rate limiting.",
                ),
            }
            title, msg = empty_msgs.get(
                tab_type, ("No results", "Results will appear as scan progresses.")
            )
            if debounced_filter:
                title = "No matches"
                msg = f'No results match "{debounced_filter}"'
            return EmptyState(
                title=title,
                message=msg,
                icon=ft.Icons.SEARCH_OFF_ROUNDED,
            )

        return ft.Column(
            controls=[
                ResultCard(
                    site_name=r.get("name", "unknown"),
                    status="Claimed"
                    if r.get("exists")
                    else ("Error" if r.get("rateLimit") else "Available"),
                    url_user=None,
                    url_main=f"https://{r.get('domain', '')}"
                    if r.get("domain")
                    else None,
                    on_open=lambda url: _open_url(url),
                    on_tap=lambda item=r: _show_email_details(item),
                    email_recovery=r.get("emailrecovery"),
                    phone_number=r.get("phoneNumber"),
                    others=r.get("others"),
                    method=r.get("method", ""),
                    rate_limit=r.get("rateLimit", False),
                    frequent_rate_limit=r.get("frequent_rate_limit", False),
                )
                for r in items
            ],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    # ── Build content based on mode ───────────────────────────────────
    if is_email_mode:
        # Live Email streaming: if active_progress has data, read directly from it!
        if active_progress and hasattr(active_progress, "checked_modules"):
            raw_found = [
                {
                    "name": r.name,
                    "domain": r.domain,
                    "method": r.method,
                    "exists": r.exists,
                    "rateLimit": r.rate_limit,
                    "frequent_rate_limit": r.frequent_rate_limit,
                    "emailrecovery": r.email_recovery,
                    "phoneNumber": r.phone_number,
                    "others": r.others,
                }
                for r in active_progress.found
            ]
            raw_not_found = [
                {
                    "name": r.name,
                    "domain": r.domain,
                    "method": r.method,
                    "exists": r.exists,
                    "rateLimit": r.rate_limit,
                    "frequent_rate_limit": r.frequent_rate_limit,
                    "emailrecovery": r.email_recovery,
                    "phoneNumber": r.phone_number,
                    "others": r.others,
                }
                for r in active_progress.not_found
            ]
            raw_rate_limited = [
                {
                    "name": r.name,
                    "domain": r.domain,
                    "method": r.method,
                    "exists": r.exists,
                    "rateLimit": r.rate_limit,
                    "frequent_rate_limit": r.frequent_rate_limit,
                    "emailrecovery": r.email_recovery,
                    "phoneNumber": r.phone_number,
                    "others": r.others,
                }
                for r in active_progress.rate_limited
            ]
            total = active_progress.total_modules or state.email_total_modules or 121
            checked = active_progress.checked_modules
        else:
            all_email = list(state.email_results) if state.email_results else []
            raw_found = [
                r for r in all_email if r.get("exists") and not r.get("rateLimit")
            ]
            raw_not_found = [
                r for r in all_email if not r.get("exists") and not r.get("rateLimit")
            ]
            raw_rate_limited = [r for r in all_email if r.get("rateLimit")]
            total = state.email_total_modules or len(all_email) or 121
            checked = total if all_email else 0

        email_found_filtered = _filter_email_items(raw_found)
        email_not_found_filtered = _filter_email_items(raw_not_found)
        email_rate_limited_filtered = _filter_email_items(raw_rate_limited)

        tabs = ft.Tabs(
            selected_index=0,
            length=3,
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
                            _build_email_result_list(email_found_filtered, "found"),
                            _build_email_result_list(
                                email_not_found_filtered, "not_found"
                            ),
                            _build_email_result_list(
                                email_rate_limited_filtered, "rate_limited"
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
                StatCard("Total", str(total), ft.Colors.PRIMARY),
            ],
            spacing=tokens.SPACE_SM,
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        )

        pct = int(checked / max(total, 1) * 100)
        progress_label = f"Checking {checked}/{total} platforms ({pct}%)..."

        def cancel_callback(e):
            controller.cancel_email_search()

    else:
        # Username results from search_progress
        found_items = (
            _filter_username_items(active_progress.found) if active_progress else []
        )
        notfound_items = (
            _filter_username_items(active_progress.not_found) if active_progress else []
        )
        error_items = (
            _filter_username_items(active_progress.errors) if active_progress else []
        )
        total = (
            active_progress.total_sites if active_progress else state.sites_total or 400
        )
        checked = (
            active_progress.checked_sites
            if active_progress
            else (total if state.last_results else 0)
        )

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
                            _build_username_result_list(found_items),
                            _build_username_result_list(notfound_items),
                            _build_username_result_list(error_items),
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
                StatCard(
                    "Found",
                    str(len(found_items) if active_progress else 0),
                    AppColors.SUCCESS,
                ),
                StatCard(
                    "Not Found",
                    str(len(notfound_items) if active_progress else 0),
                    ft.Colors.with_opacity(tokens.OPACITY_DIM, ft.Colors.ON_SURFACE),
                ),
                StatCard(
                    "Errors",
                    str(len(error_items) if active_progress else 0),
                    AppColors.WARNING,
                ),
                StatCard("Total", str(total), ft.Colors.PRIMARY),
            ],
            spacing=tokens.SPACE_SM,
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        )

        pct = int(checked / max(total, 1) * 100)
        progress_label = f"Checking {checked}/{total} sites ({pct}%)..."

        def cancel_callback(e):
            controller.cancel_search()

    # ── Shared UI components ──────────────────────────────────────────
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

    filter_hint = (
        "Filter results by platform name..."
        if is_email_mode
        else "Filter results by site name..."
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

    # Progress bar + cancel
    progress_section = ft.Container(width=0, height=0)
    if is_running and active_progress:
        progress_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.ProgressBar(
                        value=None,
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
                        ],
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
            filter_box,
            tabs,
            build_banner_ad(),
        ],
        expand=True,
        spacing=0,
    )
