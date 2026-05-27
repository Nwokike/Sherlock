"""History view — past searches."""

from __future__ import annotations

import json
import logging
from typing import Callable

import flet as ft

from core import tokens
from core.constants import LBL_NO_HISTORY, LBL_HISTORY
from core.state import state

logger = logging.getLogger(__name__)


def build_history_view(
    page: ft.Page,
    on_navigate: Callable,
    on_search: Callable,
    storage,
) -> ft.View:
    history_list = ft.Ref[ft.Column]()
    empty_state = ft.Ref[ft.Container]()

    async def _clear_all(e):
        await storage.delete("sherlock_history")
        history_list.current.controls.clear()
        empty_state.current.visible = True
        page.update()

    async def _load_history():
        try:
            raw = await storage.get("sherlock_history")
            if not raw:
                return
            entries = json.loads(raw)
            history_list.current.controls.clear()
            for entry in reversed(entries):
                username = entry.get("username", "")
                found = entry.get("found", 0)
                total = entry.get("total", 0)
                ts = entry.get("timestamp", "")

                tile = ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.PERSON_SEARCH_OUTLINED,
                                size=tokens.ICON_LG,
                                color=ft.Colors.PRIMARY,
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(
                                        username,
                                        size=tokens.FONT_LG,
                                        weight=ft.FontWeight.W_500,
                                    ),
                                    ft.Row(
                                        controls=[
                                            ft.Text(
                                                f"{found}/{total} found",
                                                size=tokens.FONT_SM,
                                                color=ft.Colors.with_opacity(
                                                    0.5, ft.Colors.ON_SURFACE
                                                ),
                                            ),
                                            ft.Text(
                                                "·",
                                                size=tokens.FONT_SM,
                                                color=ft.Colors.with_opacity(
                                                    0.3, ft.Colors.ON_SURFACE
                                                ),
                                            ),
                                            ft.Text(
                                                ts,
                                                size=tokens.FONT_XS,
                                                color=ft.Colors.with_opacity(
                                                    0.4, ft.Colors.ON_SURFACE
                                                ),
                                            ),
                                        ],
                                        spacing=4,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.REFRESH_ROUNDED,
                                tooltip="Search again",
                                on_click=lambda e, u=username: on_search(u),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(
                        left=tokens.SPACE_LG, right=tokens.SPACE_LG,
                        top=12, bottom=12,
                    ),
                    border=ft.border.only(
                        bottom=ft.BorderSide(
                            0.5, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
                        )
                    ),
                )
                history_list.current.controls.append(tile)

            if entries:
                empty_state.current.visible = False
            page.update()
        except Exception:
            pass

    appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK_ROUNDED,
            on_click=lambda e: on_navigate("/home"),
        ),
        title=ft.Text(LBL_HISTORY, size=tokens.FONT_LG, weight=ft.FontWeight.W_600),
        center_title=False,
        bgcolor=ft.Colors.TRANSPARENT,
        actions=[
            ft.IconButton(
                icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                tooltip="Clear all",
                on_click=lambda e: page.run_task(_clear_all, e),
            ),
        ],
    )

    empty = ft.Container(
        ref=empty_state,
        content=ft.Column(
            controls=[
                ft.Container(height=60),
                ft.Icon(
                    ft.Icons.HISTORY_ROUNDED,
                    size=64,
                    color=ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE),
                ),
                ft.Container(height=tokens.SPACE_LG),
                ft.Text(
                    LBL_NO_HISTORY,
                    size=tokens.FONT_LG,
                    color=ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE),
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Search for a username to get started",
                    size=tokens.FONT_SM,
                    color=ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE),
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        expand=True,
    )

    list_view = ft.Column(ref=history_list, spacing=0, expand=True)

    view = ft.View(
        route="/history",
        controls=[list_view, empty],
        appbar=appbar,
        padding=0,
        spacing=0,
    )

    page.run_task(_load_history)

    return view
