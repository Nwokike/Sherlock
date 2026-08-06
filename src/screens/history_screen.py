"""HistoryScreen — past searches with clear-all and re-search actions.

@ft.component — reads observable state.history via AppStateCtx.
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft
from flet import Control

from core.styles import build_banner_ad
from components.empty_state import EmptyState
from core import tokens
from core.constants import STORAGE_HISTORY
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("HistoryScreen")


@ft.component
def HistoryScreen() -> Control:
    from flet import context

    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = context.page
    history = state.history if state.history else []

    def _on_clear_all():
        async def _clear():
            try:
                from services.storage_service import StorageService
                from flet import context

                storage = StorageService(context.page)
                await storage.delete(STORAGE_HISTORY)
            except Exception:
                pass
            state.history.clear()

        asyncio.create_task(_clear())

    def _on_re_search(username: str):
        async def _search():
            controller.show_results()
            await controller.start_search(username)

        asyncio.create_task(_search())

    if not history:
        body = EmptyState(
            title="No search history",
            message="Your search history will appear here.",
            icon=ft.Icons.HISTORY_ROUNDED,
        )
    else:
        items = []
        for entry in reversed(history):
            username = entry.get("username", "")
            found = entry.get("found", 0)
            total = entry.get("total", 0)
            ts = entry.get("timestamp", "")

            tile = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Icon(
                                ft.Icons.PERSON_SEARCH_ROUNDED,
                                size=tokens.ICON_MD,
                                color=ft.Colors.PRIMARY,
                            ),
                            width=40,
                            height=40,
                            border_radius=20,
                            bgcolor=ft.Colors.with_opacity(
                                tokens.OPACITY_LIGHT, ft.Colors.PRIMARY
                            ),
                            alignment=ft.Alignment.CENTER,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    username,
                                    size=tokens.FONT_LG,
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Row(
                                    controls=[
                                        ft.Text(
                                            f"{found}/{total} matches",
                                            size=tokens.FONT_SM,
                                            color=ft.Colors.with_opacity(
                                                tokens.OPACITY_DIM,
                                                ft.Colors.ON_SURFACE,
                                            ),
                                        ),
                                        ft.Text(
                                            "·",
                                            size=tokens.FONT_SM,
                                            color=ft.Colors.with_opacity(
                                                tokens.OPACITY_MUTED,
                                                ft.Colors.ON_SURFACE,
                                            ),
                                        ),
                                        ft.Text(
                                            ts,
                                            size=tokens.FONT_XS,
                                            color=ft.Colors.with_opacity(
                                                tokens.OPACITY_MUTED,
                                                ft.Colors.ON_SURFACE,
                                            ),
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XS,
                                ),
                            ],
                            spacing=tokens.SPACE_XXS,
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.REFRESH_ROUNDED,
                            tooltip="Search again",
                            icon_color=ft.Colors.PRIMARY,
                            on_click=lambda e, u=username: _on_re_search(u),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(
                    left=tokens.SPACE_LG,
                    right=tokens.SPACE_LG,
                    top=tokens.SPACE_MD,
                    bottom=tokens.SPACE_MD,
                ),
                border_radius=tokens.RADIUS_LG,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                border=ft.Border.all(
                    width=1,
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE
                    ),
                ),
                margin=ft.Margin(0, 0, 0, tokens.SPACE_SM),
            )
            items.append(tile)

        body = ft.ListView(
            controls=items,
            spacing=0,
            expand=True,
            padding=ft.Padding(
                tokens.SPACE_XL, tokens.SPACE_MD, tokens.SPACE_XL, tokens.SPACE_MD
            ),
        )

    return ft.Column(
        controls=[
            ft.Container(content=body, expand=True),
            build_banner_ad(page),
        ],
        expand=True,
        spacing=0,
    )
