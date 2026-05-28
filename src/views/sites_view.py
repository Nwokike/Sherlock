"""Sites selection view — select/deselect networks to scan."""

from __future__ import annotations

import logging
from typing import Callable

import flet as ft

from core import tokens
from core.state import state
from core.constants import STORAGE_SELECTED_SITES

logger = logging.getLogger(__name__)

# List of popular sites for the "Popular" filter
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


def build_sites_view(
    page: ft.Page,
    sherlock_service,
    storage,
    on_navigate: Callable,
) -> ft.View:
    search_field = ft.Ref[ft.TextField]()
    sites_list = ft.Ref[ft.ListView]()
    stats_text = ft.Ref[ft.Text]()

    # In-memory dictionary representing checkbox control refs or raw checked states
    checked_states: dict[str, bool] = {}

    # Initialize checked states from global state
    selected_set = {s.lower() for s in state.selected_sites}
    all_sites = sorted(list((sherlock_service._site_data or {}).keys()), key=str.lower)

    for sname in all_sites:
        if not selected_set:
            checked_states[sname] = True
        else:
            checked_states[sname] = sname.lower() in selected_set

    async def _save_selection():
        checked_list = [name for name, checked in checked_states.items() if checked]
        if len(checked_list) == len(all_sites):
            state.selected_sites = []
            await storage.delete(STORAGE_SELECTED_SITES)
        else:
            state.selected_sites = checked_list
            await storage.set(STORAGE_SELECTED_SITES, ",".join(checked_list))

    def _update_stats():
        checked_count = sum(1 for checked in checked_states.values() if checked)
        if stats_text.current:
            stats_text.current.value = f"{checked_count} of {len(all_sites)} selected"
        page.update()

    async def _on_checkbox_change(name: str, value: bool):
        checked_states[name] = value
        _update_stats()
        await _save_selection()

    async def _select_all(e):
        for name in checked_states:
            checked_states[name] = True
        _update_stats()
        _refresh_list()
        await _save_selection()

    async def _select_none(e):
        for name in checked_states:
            checked_states[name] = False
        _update_stats()
        _refresh_list()
        await _save_selection()

    async def _select_popular(e):
        for name in checked_states:
            checked_states[name] = name.lower() in POPULAR_SITES
        _update_stats()
        _refresh_list()
        await _save_selection()

    def _on_search(e):
        _refresh_list()

    def _refresh_list():
        if not sites_list.current:
            return

        query = (
            search_field.current.value.strip().lower() if search_field.current else ""
        )
        sites_list.current.controls.clear()

        for name in all_sites:
            info = sherlock_service._site_data[name]
            url_main = info.get("urlMain", "")
            is_nsfw = info.get("isNSFW", False)

            if query and query not in name.lower() and query not in url_main.lower():
                continue

            is_checked = checked_states[name]

            tile = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Checkbox(
                            value=is_checked,
                            on_change=lambda e, n=name: page.run_task(
                                _on_checkbox_change, n, e.control.value
                            ),
                            fill_color={
                                ft.ControlState.HOVERED: ft.Colors.PRIMARY,
                                ft.ControlState.FOCUSED: ft.Colors.PRIMARY,
                                ft.ControlState.DEFAULT: ft.Colors.PRIMARY,
                            },
                        ),
                        ft.Column(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Text(
                                            name,
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        ft.Container(
                                            content=ft.Text(
                                                "NSFW",
                                                size=8,
                                                weight=ft.FontWeight.W_700,
                                                color=ft.Colors.WHITE,
                                            ),
                                            bgcolor=ft.Colors.RED,
                                            padding=ft.Padding(4, 1, 4, 1),
                                            border_radius=tokens.RADIUS_XS,
                                            visible=is_nsfw,
                                        ),
                                    ],
                                    spacing=tokens.SPACE_SM,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                ft.Text(
                                    url_main,
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.with_opacity(
                                        0.5, ft.Colors.ON_SURFACE
                                    ),
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                padding=ft.Padding(
                    left=tokens.SPACE_SM,
                    right=tokens.SPACE_LG,
                    top=8,
                    bottom=8,
                ),
                border=ft.Border.only(
                    bottom=ft.BorderSide(
                        width=0.5,
                        color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                    )
                ),
                on_click=lambda e, n=name: _toggle_row(n),
            )
            sites_list.current.controls.append(tile)

        page.update()

    def _toggle_row(name: str):
        new_val = not checked_states[name]
        checked_states[name] = new_val
        _update_stats()
        _refresh_list()
        page.run_task(_save_selection)

    # Search Bar
    search_bar = ft.Container(
        content=ft.TextField(
            ref=search_field,
            hint_text="Search social networks...",
            prefix_icon=ft.Icons.SEARCH,
            border_radius=tokens.RADIUS_MD,
            border_width=1.5,
            border_color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
            focused_border_color=ft.Colors.PRIMARY,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            filled=True,
            on_change=_on_search,
            text_size=tokens.FONT_MD,
            content_padding=10,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_SM,
            bottom=tokens.SPACE_SM,
        ),
    )

    # Bulk Selection Buttons
    bulk_actions = ft.Container(
        content=ft.Row(
            controls=[
                ft.TextButton(
                    content=ft.Text(
                        "Select All", size=tokens.FONT_XS, weight=ft.FontWeight.BOLD
                    ),
                    on_click=lambda e: page.run_task(_select_all, e),
                    style=ft.ButtonStyle(color=ft.Colors.PRIMARY),
                ),
                ft.TextButton(
                    content=ft.Text(
                        "Deselect All", size=tokens.FONT_XS, weight=ft.FontWeight.BOLD
                    ),
                    on_click=lambda e: page.run_task(_select_none, e),
                    style=ft.ButtonStyle(color=ft.Colors.ON_SURFACE_VARIANT),
                ),
                ft.TextButton(
                    content=ft.Text(
                        "Only Popular", size=tokens.FONT_XS, weight=ft.FontWeight.BOLD
                    ),
                    on_click=lambda e: page.run_task(_select_popular, e),
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

    # Site Count Display
    stats_header = ft.Container(
        content=ft.Row(
            controls=[
                ft.Text(
                    ref=stats_text,
                    size=tokens.FONT_XS,
                    color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                    weight=ft.FontWeight.W_500,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        padding=ft.Padding(0, tokens.SPACE_XS, 0, tokens.SPACE_SM),
    )

    # Scrollable Site List
    scroller = ft.ListView(
        ref=sites_list,
        spacing=0,
        expand=True,
    )

    appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK_ROUNDED,
            on_click=lambda e: on_navigate("/home"),
        ),
        title=ft.Row(
            [
                ft.Image(src="logo.png", width=24, height=24, border_radius=4),
                ft.Text(
                    "Social Networks", size=tokens.FONT_LG, weight=ft.FontWeight.W_600
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        center_title=False,
        bgcolor=ft.Colors.TRANSPARENT,
    )

    # Render initial list
    _refresh_list()
    _update_stats()

    view = ft.View(
        route="/sites",
        controls=[
            ft.SafeArea(
                ft.Container(
                    content=ft.Column(
                        [
                            search_bar,
                            bulk_actions,
                            stats_header,
                            scroller,
                        ],
                        expand=True,
                        spacing=0,
                    ),
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment.TOP_LEFT,
                        end=ft.Alignment.BOTTOM_RIGHT,
                        colors=[
                            ft.Colors.SURFACE,
                            ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
                        ],
                    ),
                    expand=True,
                ),
                expand=True,
            )
        ],
        appbar=appbar,
        padding=0,
        spacing=0,
    )

    return view
