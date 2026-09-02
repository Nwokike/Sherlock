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

from components.banner_ad import build_banner_ad
from components.empty_state import EmptyState
from core import tokens
from hooks.use_debounce import use_debounce
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("SitesScreen")

# Label-set for the "Popular Only" preset — matched case-insensitively
# against the loaded network labels. Names that are not present in the
# active database simply match nothing.
POPULAR_SITES = {
    "github",
    "instagram",
    "reddit",
    "youtube",
    "tiktok",
    "twitter",
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

# Tag categories from Maigret's database (75 tags)
CATEGORY_TAGS = [
    ("all", "All Networks"),
    ("social", "Social"),
    ("coding", "Coding"),
    ("gaming", "Gaming"),
    ("forum", "Forums"),
    ("crypto", "Crypto"),
    ("video", "Media"),
    ("us", "US 🇺🇸"),
    ("ng", "NG 🇳🇬"),
    ("ru", "RU 🇷🇺"),
    ("de", "DE 🇩🇪"),
    ("cn", "CN 🇨🇳"),
]


@ft.component
def SitesScreen() -> Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    # Bumped after every site-database load — re-runs the init effect.
    _ = state.sites_version

    search_query, set_search_query = ft.use_state("")
    debounced_query = use_debounce(search_query, 200)
    selected_tag, set_selected_tag = ft.use_state("all")
    checked_states, set_checked_states = ft.use_state({})

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

    def _persist(new_states: dict):
        """Persist the given checkbox state via the controller.

        An all-selected scope is stored as an empty list (= no custom
        filter, scan everything) — same semantics as pre-restructure.
        """
        checked_list = sorted(
            [name for name, checked in new_states.items() if checked],
            key=str.lower,
        )
        all_selected = bool(new_states) and len(checked_list) == len(new_states)
        asyncio.create_task(
            controller.save_selected_sites([] if all_selected else checked_list)
        )

    def _apply(new_states: dict):
        set_checked_states(new_states)
        _persist(new_states)

    def _toggle_row(name: str):
        new_states = dict(checked_states)
        new_states[name] = not new_states.get(name, False)
        _apply(new_states)

    def _select_all():
        _apply({k: True for k in checked_states})

    def _select_none():
        _apply({k: False for k in checked_states})

    def _select_popular():
        _apply({k: k.lower() in POPULAR_SITES for k in checked_states})

    # Build filtered list
    query = debounced_query.strip().lower()
    # O(1) inverted tag index (built by SherlockService after each DB load)
    # — falls back to the per-site tags map when the index isn't warm yet.
    tag_index = getattr(state, "sites_tag_index", None) or {}
    tags_map = getattr(state, "sites_tags_map", {}) or {}
    tag_bucket: set[str] | None = None
    if selected_tag != "all" and selected_tag.lower() in tag_index:
        tag_bucket = set(tag_index[selected_tag.lower()])
    items = []
    for name, is_checked in sorted(checked_states.items()):
        if query and query not in name.lower():
            continue
        if selected_tag != "all":
            if tag_bucket is not None:
                if name not in tag_bucket:
                    continue
            else:
                site_tags = [t.lower() for t in tags_map.get(name, [])]
                if selected_tag.lower() not in site_tags:
                    continue
        items.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Checkbox(
                            value=is_checked,
                            on_change=None,
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
                border=ft.Border.only(
                    bottom=ft.BorderSide(
                        width=0.5,
                        color=ft.Colors.with_opacity(
                            tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE
                        ),
                    )
                ),
                on_click=lambda e, n=name: _toggle_row(n),
            )
        )

    # Category filter chips
    category_chips = ft.Container(
        content=ft.Row(
            controls=[
                ft.Chip(
                    label=ft.Text(label, size=11, font_family="Outfit"),
                    selected=selected_tag == tag_key,
                    show_checkmark=False,
                    on_select=lambda e, k=tag_key: set_selected_tag(k),
                )
                for tag_key, label in CATEGORY_TAGS
            ],
            scroll=ft.ScrollMode.HIDDEN,
            spacing=tokens.SPACE_XS,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_XL,
            right=tokens.SPACE_XL,
            top=tokens.SPACE_XS,
            bottom=tokens.SPACE_XS,
        ),
    )

    # Search bar
    search_bar = ft.Container(
        content=ft.TextField(
            value=search_query,
            hint_text="Search networks...",
            prefix_icon=ft.Icons.SEARCH_ROUNDED,
            border_radius=tokens.RADIUS_MD,
            border_width=1,
            border_color=ft.Colors.with_opacity(
                tokens.OPACITY_MEDIUM, ft.Colors.OUTLINE
            ),
            focused_border_color=ft.Colors.PRIMARY,
            bgcolor=ft.Colors.SURFACE,
            filled=True,
            on_change=lambda e: set_search_query(e.control.value),
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
    stats_header = ft.Container(
        content=ft.Row(
            controls=[
                ft.Text(
                    stats_text,
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

    if not checked_states:
        body = ft.Container(
            content=EmptyState(
                title="Loading networks...",
                message="Fetching the social network database.",
                icon=ft.Icons.HUB_ROUNDED,
            ),
            expand=True,
        )
    elif not items:
        filter_msg = (
            f'No networks match "{debounced_query}"'
            if debounced_query
            else f"No networks in category '{selected_tag}'"
        )
        body = ft.Container(
            content=EmptyState(
                title="No networks found",
                message=filter_msg,
                icon=ft.Icons.SEARCH_OFF_ROUNDED,
            ),
            expand=True,
        )
    else:
        body = ft.ListView(
            controls=items,
            spacing=0,
            expand=True,
            build_controls_on_demand=True,
        )

    return ft.Column(
        controls=[
            search_bar,
            category_chips,
            bulk_actions,
            stats_header,
            body,
            build_banner_ad(),
        ],
        expand=True,
        spacing=0,
    )
