"""SitesScreen — select/deselect networks to scan.

@ft.component — reads observable state via AppStateCtx.
Modern checkbox list with search, bulk actions, and premium styling.
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft
from flet import Control

from core.styles import build_banner_ad
from core import tokens
from core.constants import STORAGE_SELECTED_SITES
from state.app_state import AppStateCtx

logger = logging.getLogger("SitesScreen")

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


@ft.component
def SitesScreen() -> Control:
    from flet import context

    state = ft.use_context(AppStateCtx)
    page = context.page

    search_query, set_search_query = ft.use_state("")
    checked_states, set_checked_states = ft.use_state({})

    def _init_states():
        from services.sherlock_service import SherlockService

        service = SherlockService()
        all_sites = sorted((service._site_data or {}).keys(), key=str.lower)
        selected_set = {s.lower() for s in state.selected_sites}
        initial = {}
        for sname in all_sites:
            if not selected_set:
                initial[sname] = True
            else:
                initial[sname] = sname.lower() in selected_set
        set_checked_states(initial)

    ft.use_effect(_init_states, [])

    def _get_stats():
        checked = sum(1 for v in checked_states.values() if v)
        total = len(checked_states)
        return f"{checked} of {total} selected"

    async def _save_selection():
        checked_list = [name for name, checked in checked_states.items() if checked]
        from flet import context
        from services.storage_service import StorageService

        storage = StorageService(context.page)
        if len(checked_list) == len(checked_states):
            state.selected_sites = []
            await storage.delete(STORAGE_SELECTED_SITES)
        else:
            state.selected_sites = checked_list
            await storage.set(STORAGE_SELECTED_SITES, ",".join(checked_list))

    def _toggle_row(name: str):
        new_states = dict(checked_states)
        new_states[name] = not new_states.get(name, False)
        set_checked_states(new_states)
        asyncio.create_task(_save_selection())

    def _select_all():
        set_checked_states({k: True for k in checked_states})
        asyncio.create_task(_save_selection())

    def _select_none():
        set_checked_states({k: False for k in checked_states})
        asyncio.create_task(_save_selection())

    def _select_popular():
        set_checked_states({k: k.lower() in POPULAR_SITES for k in checked_states})
        asyncio.create_task(_save_selection())

    # Build filtered list
    query = search_query.strip().lower()
    items = []
    for name, is_checked in sorted(checked_states.items()):
        if query and query not in name.lower():
            continue
        items.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Checkbox(
                            value=is_checked,
                            on_change=lambda e, n=name: _toggle_row(n),
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

    # Search bar
    search_bar = ft.Container(
        content=ft.TextField(
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

    return ft.Column(
        controls=[
            search_bar,
            bulk_actions,
            stats_header,
            ft.ListView(controls=items, spacing=0, expand=True),
            build_banner_ad(page),
        ],
        expand=True,
        spacing=0,
    )
