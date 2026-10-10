"""ResultsScreen — live search results for both username and email OSINT.

@ft.component — reads observable state.progress_version to re-render on each tick.

In username mode: shows Found / Not Found / Errors tabs driven by sherlock-project.
In email mode:    shows Found / Not Found / Rate Limited tabs driven by holehe.

Both modes support: filter bar, stat cards, cancel, export.
"""

from __future__ import annotations

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
from core.tasks import spawn
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
    engine_total: int
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
        engine_total = progress.total_sites or 0
        total = engine_total or state.sites_total or 3300
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
        engine_total = 0
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
        engine_total=engine_total,
        has_progress=has_progress,
        is_cancelled=is_cancelled,
        is_running=is_running,
        username=username,
    )


def clamp_tab_index(tab_index: int, length: int) -> int:
    """Clamp a shared tab index into a valid range for a Tabs of `length` tabs.

    The tab index is shared across username mode (3 tabs) and email mode
    (4 tabs): switching modes while sitting on email tab 3 would otherwise pass
    ``selected_index=3`` to a ``length=3`` Tabs, and ``Tabs.before_update``
    raises ``IndexError`` (flet 1.0.1 does not clamp).
    """
    if length <= 0:
        return 0
    return max(0, min(int(tab_index), length - 1))


def _email_fingerprint(rows) -> tuple:
    """Cheap content fingerprint for email result dicts (memo dep)."""
    try:
        return tuple(
            (
                str(r.get("name", "")),
                bool(r.get("exists")),
                bool(r.get("rateLimit")),
                bool(r.get("unavailable")),
            )
            for r in (rows or [])
        )
    except Exception:
        return (len(rows or []),)


def _username_fingerprint(items) -> tuple:
    """Cheap content fingerprint for SiteResults (memo dep)."""
    try:
        return tuple(
            (
                str(getattr(r, "site_name", "")),
                str(getattr(r, "status", "")),
            )
            for r in (items or [])
        )
    except Exception:
        return (len(items or []),)


def _enrichment_fingerprint(enrichments) -> tuple:
    """Content fingerprint for the enrichments map (memo dep)."""
    try:
        if not enrichments:
            return ()
        return tuple(
            (str(k), str(sorted(v.keys())) if isinstance(v, dict) else str(v))
            for k, v in enrichments.items()
        )
    except Exception:
        return (len(enrichments or {}),)


# Banner spacing inside a results list: >10 results -> one banner every 10,
# <=10 -> one every 5. Keeps density sane on short lists and prevents a
# 5,200-hit list from becoming an ad wall. The per-list banner count is also
# capped, since a ListView this long can hit either cap first.
_BANNER_SPACING = 10
_BANNER_SPACING_SHORT = 5
_BANNER_SHORT_THRESHOLD = 10
_BANNER_MAX_PER_LIST = 8


def _banner_slots(count: int) -> list[int]:
    """0-based card indices after which a banner is placed (owner rule:
    every 10 results, or every 5 when the list is shorter than 10)."""
    if count <= 0:
        return []
    # <=10 (not just <) takes the tighter spacing so a 10-result list is not
    # an uncovered edge case.
    spacing = (
        _BANNER_SPACING_SHORT if count <= _BANNER_SHORT_THRESHOLD else _BANNER_SPACING
    )
    slots = list(range(spacing - 1, count - 1, spacing))
    if len(slots) > _BANNER_MAX_PER_LIST:
        step = len(slots) / _BANNER_MAX_PER_LIST
        slots = [slots[int(i * step)] for i in range(_BANNER_MAX_PER_LIST)]
    return slots


def _build_result_list(
    items,
    empty_title: str,
    empty_msg: str,
    build_card,
    debounced_filter: str = "",
    banner_at=None,
) -> Control:
    """Shared list builder with virtualization for large result sets.

    Always renders the FULL result set — no capping, no "+N more" footers.
    Performance is handled by ListView virtualization (build_controls_on_demand,
    only visible cards are materialized) and the worker-thread engine isolation;
    hiding a user's results was never an acceptable trade-off.

    `banner_at(i)` returns a banner control for the i-th banner slot; banners
    come from a stable ref-backed pool so the 2Hz progress ticks never
    re-request them. On desktop/web the pool entries are zero-size containers.
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
    slots = _banner_slots(len(items))
    controls = []
    cursor = 0
    for ordinal, slot in enumerate(slots):
        controls.extend(build_card(r) for r in items[cursor : slot + 1])
        controls.append(banner_at(ordinal))
        cursor = slot + 1
    controls.extend(build_card(r) for r in items[cursor:])
    # ListView with build_controls_on_demand: cards materialize lazily as the
    # user scrolls, so even 5,200 entries stay smooth.
    return ft.ListView(
        controls=controls,
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

    active_progress = state.search_progress
    # Typed snapshot for username mode — never dereference the raw
    # progress object for username rendering (see _resolve_username_view_data).
    username_view = _resolve_username_view_data(state)
    # Single source of truth for "a scan is live": the PIPELINE flag, not
    # progress.is_running (which flips False per-target the moment maigret
    # returns — owner saw Results say 'finished' while the banner still
    # counted 504/509). Results and the ActiveScanBanner now agree.
    is_running = bool(state.is_searching)

    # When a scan is actively running, derive the display mode from the
    # progress object itself — not from state.search_mode, which the user
    # can flip via the Home screen chips without affecting the running scan.
    if is_running and active_progress is not None:
        is_email_mode = hasattr(active_progress, "checked_modules")
    else:
        is_email_mode = state.search_mode == MODE_EMAIL

    filter_query, set_filter_query = ft.use_state("")
    debounced_filter = use_debounce(filter_query, 250)
    tab_index, set_tab_index = ft.use_state(0)
    # Stable inactive-tab placeholders: creating fresh Containers on every
    # progress tick churned TabBarView child identity ~2x/sec and surfaced
    # as a RangeError storm in the page-error log. Refs keep them stable so
    # at most one child changes per tick.
    _email_ph = ft.use_ref(lambda: [ft.Container() for _ in range(4)])
    _username_ph = ft.use_ref(lambda: [ft.Container() for _ in range(3)])

    # Interleaved in-list banners come from the shared screen-level pool, so
    # the 2Hz progress ticks never re-request an ad (a fresh BannerAd per
    # tick would burn requests and flash the slot).
    def _banner_at(ordinal: int):
        from components.banner_ad import pooled_banner_ad

        return pooled_banner_ad(f"results-{ordinal}")

    def _open_url(url: str):
        async def _launch():
            from flet import context

            from core.notify import show_snack
            from core.shared_services import shared_url_launcher

            try:
                await shared_url_launcher().launch_url(url)
            except Exception as exc:
                logger.warning("Failed to launch URL %s: %s", url, exc)
                page = context.page
                if page:
                    show_snack(page, ERR_OPEN_URL, bgcolor=AppColors.ERROR)

        spawn(_launch())

    def _pivot_search(handle: str):
        """Re-run search with a discovered cross-platform handle."""
        handle = (handle or "").strip().lstrip("@")
        if not handle:
            return
        if "@" in handle:
            spawn(controller.start_email_search(handle))
        else:
            spawn(controller.start_search(handle))

    def _show_username_details(r):
        from flet import context

        page = context.page
        if not page:
            return
        with contextlib.suppress(Exception):
            from core.shared_services import shared_haptics

            spawn(shared_haptics(page).light_impact())
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
            on_pivot=_pivot_search,
        )

    def _show_email_details(r):
        from flet import context

        page = context.page
        if not page:
            return
        with contextlib.suppress(Exception):
            from core.shared_services import shared_haptics

            spawn(shared_haptics(page).light_impact())
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
            engine_total = active_progress.total_modules or 0
            total = engine_total or state.email_total_modules or 121
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
            engine_total = 0
            total = state.email_total_modules or len(all_email) or 121
            # Cached history has no live checked counter: report 0 so the
            # progress section shows the indeterminate state instead of a
            # fake 100% (checked == total masked partial/cancelled runs).
            checked = 0

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

        # Apply only-found filter (method filtering was removed together
        # with old holehe — holehe-v2 validators carry no method metadata).
        # Keep raw_* intact for stats_row; the tabs/lists use shown_* so the
        # stat cards report real totals even when only-found is on.
        only_found = getattr(state, "email_only_found", False)

        shown_not_found = [] if only_found else raw_not_found
        shown_rate_limited = [] if only_found else raw_rate_limited
        shown_unavailable = [] if only_found else raw_unavailable

        def _email_filter_key(r):
            parts = [r.get("name", "") or "", r.get("domain", "") or ""]
            if r.get("emailrecovery"):
                parts.append(str(r["emailrecovery"]))
            if r.get("phoneNumber"):
                parts.append(str(r["phoneNumber"]))
            if r.get("method"):
                parts.append(str(r["method"]))
            others = r.get("others")
            if isinstance(others, dict):
                extra = others.get("extra")
                if isinstance(extra, dict):
                    parts.extend(str(v) for v in extra.values() if v)
            return " ".join(parts)

        email_found_filtered = _filter_by_name(raw_found, _email_filter_key)
        email_not_found_filtered = _filter_by_name(shown_not_found, _email_filter_key)
        email_rate_limited_filtered = _filter_by_name(
            shown_rate_limited, _email_filter_key
        )
        email_unavailable_filtered = _filter_by_name(
            shown_unavailable, _email_filter_key
        )

        # Predictable alphabetical ordering (A-Z by platform name) across all tabs
        email_found_filtered.sort(key=lambda r: (r.get("name") or "").lower())
        email_not_found_filtered.sort(key=lambda r: (r.get("name") or "").lower())
        email_rate_limited_filtered.sort(key=lambda r: (r.get("name") or "").lower())
        email_unavailable_filtered.sort(key=lambda r: (r.get("name") or "").lower())

        # P1-1: active-tab card list memoized on membership — progress
        # ticks between membership changes skip the O(N) card-tree rebuild.
        # Exactly one use_memo per branch keeps the hook slot stable across
        # email↔username mode switches (identical prefix, same hook type).
        email_specs = [
            (
                email_found_filtered,
                "No registrations found",
                "No platforms matched this email address.",
            ),
            (
                email_not_found_filtered,
                "All found",
                "Every platform confirmed this email is registered.",
            ),
            (
                email_rate_limited_filtered,
                "No rate limits",
                "All checks completed without rate limiting.",
            ),
            (
                email_unavailable_filtered,
                "No unavailable platforms",
                "Every platform check is currently supported.",
            ),
        ]
        email_slot = ft.use_memo(
            lambda: _build_result_list(
                email_specs[min(tab_index, len(email_specs) - 1)][0],
                email_specs[min(tab_index, len(email_specs) - 1)][1],
                email_specs[min(tab_index, len(email_specs) - 1)][2],
                _make_email_card,
                debounced_filter,
                banner_at=_banner_at,
            ),
            [
                tab_index,
                debounced_filter,
                _email_fingerprint(raw_found),
                _email_fingerprint(shown_not_found),
                _email_fingerprint(shown_rate_limited),
                _email_fingerprint(shown_unavailable),
            ],
        )
        tabs = ft.Tabs(
            selected_index=tab_index,
            length=4,
            on_change=lambda e: set_tab_index(e.control.selected_index),
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
                            email_slot if tab_index == 0 else _email_ph.current[0],
                            email_slot if tab_index == 1 else _email_ph.current[1],
                            email_slot if tab_index == 2 else _email_ph.current[2],
                            email_slot if tab_index == 3 else _email_ph.current[3],
                        ],
                        expand=True,
                    ),
                ],
                expand=True,
                spacing=0,
            ),
            expand=True,
        )

        # Stat cards double as tab selectors; every card uses the same
        # neutral treatment so none reads as "the selected one" (the old
        # dim Not-Found looked permanently highlighted).
        def _goto_tab(idx):
            set_tab_index(idx)

        _neutral = ft.Colors.ON_SURFACE
        stats_row = ft.Row(
            controls=[
                StatCard(
                    "Found",
                    str(len(raw_found)),
                    AppColors.SUCCESS,
                    on_click=lambda e: _goto_tab(0),
                ),
                StatCard(
                    "Not Found",
                    str(len(raw_not_found)),
                    _neutral,
                    on_click=lambda e: _goto_tab(1),
                ),
                StatCard(
                    "Rate Ltd",
                    str(len(raw_rate_limited)),
                    AppColors.WARNING,
                    on_click=lambda e: _goto_tab(2),
                ),
                StatCard(
                    "Unavail",
                    str(len(raw_unavailable)),
                    AppColors.ERROR,
                    on_click=lambda e: _goto_tab(3),
                ),
            ],
            spacing=tokens.SPACE_SM,
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        )
        if active_progress and getattr(active_progress, "is_cancelled", False):
            progress_label = f"Cancelled — {checked}/{total} checked"
        elif checked == 0 and engine_total == 0:
            # Initializing phase — same rationale as the username branch.
            progress_label = "Initializing..."
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
                error_type=getattr(r, "error_type", None),
                error_hint=getattr(r, "error_hint", "") or "",
                protection=tuple(getattr(r, "protection", None) or ()),
                badge=getattr(r, "badge", "") or "",
                keyword_hit=bool(getattr(r, "keyword_hit", False)),
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

        # Predictable alphabetical ordering (A-Z by site name) across all tabs
        found_items.sort(key=lambda r: (getattr(r, "site_name", "") or "").lower())
        notfound_items.sort(key=lambda r: (getattr(r, "site_name", "") or "").lower())
        error_items.sort(key=lambda r: (getattr(r, "site_name", "") or "").lower())
        total = username_view.total
        checked = username_view.checked

        # P1-1: memoized active-tab card list (one use_memo per branch —
        # hook slot stays stable across email↔username mode switches).
        # Per-tab empty states mirror the email branch (email_specs).
        if debounced_filter:
            username_specs = [
                (found_items, "No matches", f'No results match "{debounced_filter}"'),
                (
                    notfound_items,
                    "No matches",
                    f'No results match "{debounced_filter}"',
                ),
                (
                    error_items,
                    "No matches",
                    f'No results match "{debounced_filter}"',
                ),
            ]
        else:
            username_specs = [
                (
                    found_items,
                    "No results yet",
                    "Results will appear as the scan progresses.",
                ),
                (
                    notfound_items,
                    "All claimed",
                    "Every checked site confirmed this username is taken.",
                ),
                (
                    error_items,
                    "No errors",
                    "All checks completed without errors.",
                ),
            ]
        username_slot = ft.use_memo(
            lambda: _build_result_list(
                username_specs[min(tab_index, len(username_specs) - 1)][0],
                username_specs[min(tab_index, len(username_specs) - 1)][1],
                username_specs[min(tab_index, len(username_specs) - 1)][2],
                _make_username_card,
                debounced_filter,
                banner_at=_banner_at,
            ),
            [
                tab_index,
                debounced_filter,
                _username_fingerprint(username_view.found),
                _username_fingerprint(username_view.not_found),
                _username_fingerprint(username_view.errors),
                _enrichment_fingerprint(state.enrichments),
            ],
        )

        # Username mode has 3 tabs (0-2) but tab_index is shared with email
        # mode (4 tabs, 0-3): clamp so switching from email tab 3 cannot raise
        # IndexError in Tabs.before_update.
        username_tab_index = clamp_tab_index(tab_index, 3)
        tabs = ft.Tabs(
            selected_index=username_tab_index,
            length=3,
            on_change=lambda e: set_tab_index(e.control.selected_index),
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
                            username_slot
                            if username_tab_index == 0
                            else _username_ph.current[0],
                            username_slot
                            if username_tab_index == 1
                            else _username_ph.current[1],
                            username_slot
                            if username_tab_index == 2
                            else _username_ph.current[2],
                        ],
                        expand=True,
                    ),
                ],
                expand=True,
                spacing=0,
            ),
            expand=True,
        )
        _neutral = ft.Colors.ON_SURFACE
        stats_row = ft.Row(
            controls=[
                StatCard(
                    "Found",
                    str(len(username_view.found)),
                    AppColors.SUCCESS,
                    on_click=lambda e: set_tab_index(0),
                ),
                StatCard(
                    "Not Found",
                    str(len(username_view.not_found)),
                    _neutral,
                    on_click=lambda e: set_tab_index(1),
                ),
                StatCard(
                    "Errors",
                    str(len(username_view.errors)),
                    AppColors.WARNING,
                    on_click=lambda e: set_tab_index(2),
                ),
                # Total is a summary, not a tab — stays a plain card.
                StatCard("Total", str(total), ft.Colors.PRIMARY),
            ],
            spacing=tokens.SPACE_SM,
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        )
        if username_view.is_cancelled:
            progress_label = f"Cancelled — {checked}/{total} checked"
        elif checked == 0 and username_view.engine_total == 0:
            # Initializing phase — mirrors the ActiveScanBanner: the engine
            # has not reported a single site yet, so a 0/N denominator is
            # meaningless; show the same "Initializing..." state the banner
            # shows instead of a frozen 0/total bar.
            progress_label = "Initializing..."
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
            border={
                ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                    side=ft.BorderSide(
                        width=1,
                        color=ft.Colors.with_opacity(
                            tokens.OPACITY_MEDIUM, ft.Colors.OUTLINE
                        ),
                    ),
                    border_radius=tokens.RADIUS_MD,
                ),
                ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                    side=ft.BorderSide(width=1, color=ft.Colors.PRIMARY),
                    border_radius=tokens.RADIUS_MD,
                ),
            },
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
        # Indeterminate (value=None) while the engine has reported nothing —
        # the same continuously-filling "Initializing" animation the
        # ActiveScanBanner shows. Once the first site completes (or the
        # engine publishes its real denominator), switch to a determinate
        # 0..1 fraction.
        engine_known_total = username_view.engine_total or (
            getattr(active_progress, "total_modules", 0) or 0
        )
        if checked == 0 and engine_known_total == 0:
            progress_val = None
        elif total > 0:
            progress_val = checked / total
        else:
            progress_val = None
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
            filter_box,
            tabs,
            build_banner_ad(),
        ],
        expand=True,
        spacing=0,
    )
