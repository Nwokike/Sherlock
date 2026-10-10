"""SitesScreen — select/deselect which social networks get scanned.

@ft.component — reads observable state via AppStateCtx. Site names come
from the observable sites cache (populated by AppController after each
site-database load), so the screen renders the moment names are known
instead of instantiating its own (empty) SherlockService. Selection
changes persist through AppController (the single StorageService owner).
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft
from flet import Control

from components.banner_ad import pooled_banner_ad
from components.empty_state import EmptyState
from core import tokens
from core.constants import test_id
from core.tasks import spawn
from hooks.use_debounce import use_debounce
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("SitesScreen")

# Label-set for the "Popular Only" preset — matched case-insensitively
# against the loaded network labels. Names that are not present in the
# active database simply match nothing. ("x" is the current name; the legacy
# "twitter" entry was dropped to avoid double-counting one network.)
POPULAR_SITES = {
    "github",
    "instagram",
    "reddit",
    "youtube",
    "tiktok",
    "x",
    "steam",
    "pinterest",
    "facebook",
    "linkedin",
    "spotify",
    "twitch",
    "patreon",
    "medium",
}

# Static fallback while the live tag index is cold ( DB not loaded yet).
CATEGORY_TAGS = [
    ("all", "All Networks"),
    ("social", "Social"),
    ("coding", "Coding"),
    ("gaming", "Gaming"),
    ("forum", "Forums"),
    ("crypto", "Crypto"),
    ("dating", "Dating"),
    ("video", "Media"),
]

# Pinned first in the live chip row, in this order.
PINNED_TAGS = ["social", "coding", "gaming", "forum", "crypto", "dating", "video"]
PINNED_LABELS = {
    "social": "Social",
    "coding": "Coding",
    "gaming": "Gaming",
    "forum": "Forums",
    "crypto": "Crypto",
    "dating": "Dating",
    "video": "Media",
}

# Fixed row height so ListView virtualization can skip off-screen rows.
_ROW_HEIGHT = 56.0

# Banner density inside the network list (owner: every 10, same as results).
_BANNER_EVERY = 10
_BANNER_MAX = 15


@ft.component
def SitesSearchBar(initial: str, on_debounced):
    """Search field isolated so keystrokes don't rebuild the 5,200-row list.

    Raw input lives here; only the 200ms-stable value flows up to the
    parent, which is the sole dep of the filtered-names memo.
    """
    raw, set_raw = ft.use_state(initial)
    debounced = use_debounce(raw, 200)
    ft.use_effect(lambda: on_debounced(debounced), [debounced])
    return ft.Container(
        content=ft.TextField(
            key=test_id("sites-search-field"),
            value=raw,
            hint_text="Search networks...",
            prefix_icon=ft.Icons.SEARCH_ROUNDED,
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
            on_change=lambda e: set_raw(e.control.value),
            text_size=tokens.FONT_SM,
            content_padding=tokens.SPACE_SM,
            height=44,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_XL,
            right=tokens.SPACE_XL,
            top=tokens.SPACE_SM,
            bottom=tokens.SPACE_SM,
        ),
    )


@ft.component
def SitesScreen() -> Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    # Bumped after every site-database load — re-runs the init effect.
    _ = state.sites_version

    debounced_query, set_debounced_query = ft.use_state("")
    selected_tag, set_selected_tag = ft.use_state("all")
    checked_states, set_checked_states = ft.use_state({})
    # Double-fire guard: Checkbox.on_change fires, then the tap bubbles to
    # the row Container.on_click in the same frame — swallow the second.
    _row_from_checkbox = ft.use_ref(False)
    _persist_task = ft.use_ref(None)
    _pending_states = ft.use_ref(None)

    def _cleanup_persist():
        old = _persist_task.current
        if old is not None and not old.done():
            old.cancel()

    ft.use_effect(lambda: _cleanup_persist, [])

    def _init_states():
        """(Re)build checkbox states from the observed site name cache.

        Manual toggles are preserved across re-inits; only freshly
        added names get their initial value (checked unless the user
        has a custom selection that excludes them).
        """
        available = sorted(state.sites_cache or [], key=str.lower)
        if not available:
            return
        selected_lower = {s.lower() for s in (state.selected_sites or []) if s}
        current = dict(checked_states)
        new_states = {}
        for name in available:
            if name in current:
                new_states[name] = current[name]
            elif selected_lower:
                new_states[name] = name.lower() in selected_lower
            else:
                new_states[name] = True
        if new_states != current:
            set_checked_states(new_states)

    ft.use_effect(_init_states, [state.sites_version])

    def _get_stats() -> str:
        checked = sum(1 for v in checked_states.values() if v)
        total = len(checked_states)
        return f"{checked} of {total} selected"

    def _persist_debounced(new_states: dict):
        """Coalesce rapid toggles into one write per 300ms burst."""
        _pending_states.current = new_states
        old = _persist_task.current
        if old is not None and not old.done():
            old.cancel()

        async def _after():
            try:
                await asyncio.sleep(0.3)
                snap = _pending_states.current
                checked_list = sorted([n for n, c in snap.items() if c], key=str.lower)
                all_selected = bool(snap) and len(checked_list) == len(snap)
                await controller.save_selected_sites(
                    [] if all_selected else checked_list
                )
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("Site scope persist failed: %s", exc)

        _persist_task.current = spawn(_after(), name="sites-persist")

    def _persist(new_states: dict):
        """Persist the given checkbox state via the controller.

        An all-selected scope is stored as an empty list (= no custom
        filter, scan everything) — same semantics as pre-restructure.
        """
        _persist_debounced(new_states)

    def _apply(new_states: dict):
        set_checked_states(new_states)
        _persist(new_states)

    def _on_checkbox_change(name: str):
        _row_from_checkbox.current = True
        _toggle_row(name)

    def _on_row_click(name: str):
        if _row_from_checkbox.current:
            _row_from_checkbox.current = False
            return
        _toggle_row(name)

    def _toggle_row(name: str):
        new_states = dict(checked_states)
        new_states[name] = not new_states.get(name, False)
        _apply(new_states)

    def _select_all():
        _apply(dict.fromkeys(checked_states, True))

    def _select_none():
        _apply(dict.fromkeys(checked_states, False))

    def _select_popular():
        _apply({k: k.lower() in POPULAR_SITES for k in checked_states})

    def _scope_to_filter():
        """Set the scan scope to exactly the current category filter.

        Uses the O(1) inverted tag index (falls back to the per-site tags
        map) and the existing selected-sites persistence — the preset
        becomes the scan scope without any engine re-query. "All Networks"
        re-checks everything (= no custom scope).
        """
        if selected_tag == "all":
            new_states = dict.fromkeys(checked_states, True)
            msg = "Scope: all networks"
        else:
            tag_index = getattr(state, "sites_tag_index", None) or {}
            bucket = set(tag_index.get(selected_tag.lower(), []))
            if not bucket:
                bucket = {
                    name
                    for name, site_tags in (
                        getattr(state, "sites_tags_map", {}) or {}
                    ).items()
                    if selected_tag.lower() in [t.lower() for t in site_tags]
                }
            if not bucket:
                _notify_scope(f'No "{selected_tag}" sites in this database')
                return
            new_states = {k: k in bucket for k in checked_states}
            msg = f"Scope: {selected_tag} — {sum(new_states.values())} networks"
        _apply(new_states)
        _notify_scope(msg)

    def _notify_scope(message: str):
        try:
            from flet import context

            from core.notify import show_snack

            show_snack(context.page, message)
        except Exception as exc:
            logger.debug("scope snack skipped: %s", exc)

    # ── Memoized derived data (rebuilt only when deps change) ─────────────
    # Canonical name order: sites_cache is already stored sorted, so iterate
    # it directly instead of re-sorting 5,200 entries every render.
    canonical_names = ft.use_memo(
        lambda: sorted(state.sites_cache or [], key=str.lower),
        [state.sites_version],
    )
    # Lowered tag sets, hoisted out of the per-row loop (O(N·T) per frame).
    lowered_tags = ft.use_memo(
        lambda: {
            n: frozenset(str(t).lower() for t in (tags or []))
            for n, tags in ((getattr(state, "sites_tags_map", {}) or {}).items())
        },
        [state.sites_version],
    )
    tag_buckets = ft.use_memo(
        lambda: {
            str(k).lower(): frozenset(v or [])
            for k, v in ((getattr(state, "sites_tag_index", None) or {}).items())
        },
        [state.sites_version],
    )

    def _compute_filtered():
        q = debounced_query.strip().lower()
        bucket = (
            tag_buckets.get(selected_tag.lower()) if selected_tag != "all" else None
        )
        if selected_tag != "all" and bucket is None:
            bucket = frozenset(
                n for n, ts in lowered_tags.items() if selected_tag.lower() in ts
            )
        out = []
        for name in canonical_names:
            if bucket is not None and name not in bucket:
                continue
            if (
                q
                and q not in name.lower()
                and not any(q in t for t in lowered_tags.get(name, ()))
            ):
                continue
            out.append(name)
        return out

    # Deliberately NOT keyed on checked_states — toggles must not re-filter;
    # the checked lookup happens at row build via checked_states.get(name).
    filtered_names = ft.use_memo(
        _compute_filtered,
        [debounced_query, selected_tag, state.sites_version],
    )

    def _compute_chips():
        index = getattr(state, "sites_tag_index", None) or {}
        if not index:
            return CATEGORY_TAGS, []
        sizes = {str(k).lower(): len(v or []) for k, v in index.items()}

        def _is_country(k: str) -> bool:
            return len(k) == 2 and k.isalpha()

        cats = [("all", f"All Networks ({len(canonical_names)})")]
        cats += [
            (k, f"{PINNED_LABELS[k]} ({sizes.get(k, 0)})")
            for k in PINNED_TAGS
            if k in sizes
        ]
        rest = sorted(
            (
                k
                for k in sizes
                if k not in PINNED_TAGS and k != "all" and not _is_country(k)
            ),
            key=lambda k: sizes[k],
            reverse=True,
        )[:12]
        cats += [(k, f"{k.title()} ({sizes[k]})") for k in rest]
        countries = sorted(k for k in sizes if _is_country(k))
        return cats, countries

    live_cats, live_countries = ft.use_memo(_compute_chips, [state.sites_version])

    # Build filtered list
    items = []
    for name in filtered_names:
        is_checked = checked_states.get(name, False)
        items.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Checkbox(
                            value=is_checked,
                            on_change=lambda e, n=name: _on_checkbox_change(n),
                            fill_color={
                                ft.ControlState.HOVERED: ft.Colors.PRIMARY,
                                ft.ControlState.FOCUSED: ft.Colors.PRIMARY,
                                ft.ControlState.DEFAULT: ft.Colors.PRIMARY,
                            },
                        ),
                        ft.Text(
                            name,
                            size=tokens.FONT_MD,
                            weight=ft.FontWeight.W_500,
                        ),
                    ],
                    spacing=tokens.SPACE_MD,
                ),
                padding=ft.Padding(
                    left=tokens.SPACE_MD,
                    right=tokens.SPACE_XL,
                    top=tokens.SPACE_SM,
                    bottom=tokens.SPACE_SM,
                ),
                height=_ROW_HEIGHT,
                border=ft.Border.only(
                    bottom=ft.BorderSide(
                        width=0.5,
                        color=ft.Colors.with_opacity(
                            tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE
                        ),
                    )
                ),
                on_click=lambda e, n=name: _on_row_click(n),
            )
        )

    def _country_chip_label(code: str) -> str:
        """'gb' -> '🇬🇧 GB'; falls back to the bare code."""
        from core.geo_utils import get_country_by_tag

        geo = get_country_by_tag(code)
        flag = getattr(geo, "flag", "") if geo else ""
        upper = code.upper()
        return f"{flag} {upper}" if flag else upper

    # Category filter chips — live from the tag index (pinned first with
    # counts), plus a scrollable country row from 2-letter tags.
    def _chip_row(pairs):
        return ft.Row(
            controls=[
                ft.Chip(
                    label=ft.Text(label, size=11, font_family="Outfit"),
                    selected=selected_tag == tag_key,
                    show_checkmark=False,
                    on_select=lambda e, k=tag_key: set_selected_tag(k),
                )
                for tag_key, label in pairs
            ],
            scroll=ft.ScrollMode.HIDDEN,
            spacing=tokens.SPACE_XS,
        )

    chip_rows = [_chip_row(live_cats)]
    if live_countries:
        # Country chips carry their flag emoji alongside the code — the
        # codes alone ("GB", "RU") read as raw tags, not countries.
        chip_rows.append(
            _chip_row([(c, _country_chip_label(c)) for c in live_countries])
        )
    category_chips = ft.Container(
        content=ft.Column(chip_rows, spacing=0),
        padding=ft.Padding(
            left=tokens.SPACE_XL,
            right=tokens.SPACE_XL,
            top=tokens.SPACE_XS,
            bottom=tokens.SPACE_XS,
        ),
    )

    # Search bar — isolated component so keystrokes don't rebuild the list.
    search_bar = SitesSearchBar(initial="", on_debounced=set_debounced_query)

    # Bulk actions
    bulk_actions = ft.Container(
        content=ft.Row(
            controls=[
                ft.TextButton(
                    "Select All",
                    on_click=lambda e: _select_all(),
                    style=ft.ButtonStyle(color=ft.Colors.PRIMARY),
                ),
                ft.TextButton(
                    "Deselect All",
                    on_click=lambda e: _select_none(),
                    style=ft.ButtonStyle(color=ft.Colors.ON_SURFACE_VARIANT),
                ),
                ft.TextButton(
                    "Popular Only",
                    on_click=lambda e: _select_popular(),
                    style=ft.ButtonStyle(color=ft.Colors.PRIMARY),
                ),
                ft.TextButton(
                    "Scope to Filter"
                    if selected_tag != "all"
                    else "Scope: All Networks",
                    on_click=lambda e: _scope_to_filter(),
                    style=ft.ButtonStyle(color=ft.Colors.PRIMARY),
                    tooltip="Scan only the networks shown by the current category filter",
                ),
            ],
            alignment=ft.MainAxisAlignment.START,
            spacing=tokens.SPACE_XS,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_MD,
            right=tokens.SPACE_MD,
            top=0,
            bottom=tokens.SPACE_XS,
        ),
    )

    stats_text = _get_stats()
    # DB stats header: what the shipped database actually contains — helps
    # users judge scan breadth at a glance.
    db_total = getattr(state, "sites_total", 0) or 0
    n_tags = len(getattr(state, "sites_tag_index", None) or {})
    db_text = f" • DB: {db_total:,} sites, {n_tags} tags" if db_total else ""
    shown_text = (
        f" • {len(filtered_names)} shown"
        if filtered_names and len(filtered_names) != len(checked_states)
        else ""
    )
    stats_header = ft.Container(
        content=ft.Row(
            controls=[
                ft.Text(
                    stats_text + db_text + shown_text,
                    size=tokens.FONT_XS,
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                    ),
                    weight=ft.FontWeight.W_500,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        padding=ft.Padding(0, tokens.SPACE_XS, 0, tokens.SPACE_SM),
    )

    # The ListView IS the screen root and owns the only scroll. A Column here
    # would give it unbounded height (flet 1.0.4 ignores `expand` on column
    # children — no control sets `host_expanded`), the list would shrink-wrap
    # to all 5,200 rows, and a Column without `scroll=` never scrolls, so the
    # screen clipped and could not be scrolled at all. Header controls ride
    # inside the list instead.
    header_block = [search_bar, category_chips, bulk_actions, stats_header]

    if state.sites_version == 0 and not checked_states:
        return ft.ListView(
            controls=[
                *header_block,
                EmptyState(
                    title="Loading networks...",
                    message="Fetching the social network database.",
                    icon=ft.Icons.HUB_ROUNDED,
                ),
            ],
            spacing=0,
            expand=True,
        )
    if not canonical_names:
        return ft.ListView(
            controls=[
                *header_block,
                EmptyState(
                    title="No networks in database",
                    message="The site database loaded empty — check exclusions or reload.",
                    icon=ft.Icons.HUB_ROUNDED,
                ),
            ],
            spacing=0,
            expand=True,
        )
    if not items:
        filter_msg = (
            f'No networks match "{debounced_query}"'
            if debounced_query
            else f"No networks in category '{selected_tag}'"
        )
        return ft.ListView(
            controls=[
                *header_block,
                EmptyState(
                    title="No networks found",
                    message=filter_msg,
                    icon=ft.Icons.SEARCH_OFF_ROUNDED,
                ),
            ],
            spacing=0,
            expand=True,
        )

    # Banner every _BANNER_EVERY rows (cap _BANNER_MAX), drawn from the shared
    # pool so no render ever re-requests an ad. Slot keys are per-ad so each
    # position keeps its own instance.
    controls: list = list(header_block)
    placed = 0
    for i, row in enumerate(items):
        controls.append(row)
        placed += 1
        if placed >= _BANNER_EVERY:
            slot = i // _BANNER_EVERY
            if slot < _BANNER_MAX:
                controls.append(pooled_banner_ad(f"sites-list-{slot}"))
                placed = 0
            else:
                placed = _BANNER_EVERY - 1  # keep spacing, stop adding banners

    return ft.ListView(
        controls=controls,
        spacing=0,
        expand=True,
        build_controls_on_demand=True,
        item_extent=_ROW_HEIGHT,
        cache_extent=500,
    )
