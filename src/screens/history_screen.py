"""HistoryScreen — past searches with clear-all and re-search actions.

@ft.component — reads observable state.history via AppStateCtx.
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft
from flet import Control

from components.app_header import AppHeader
from components.banner_ad import build_banner_ad
from components.empty_state import EmptyState
from core import tokens
from core.constants import MODE_EMAIL, MODE_USERNAME, STORAGE_HISTORY
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("HistoryScreen")


@ft.component
def HistoryScreen() -> Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    from flet import context

    page = context.page
    history = state.history if state.history else []

    def _on_clear_all():
        async def _clear():
            try:
                from services.storage_service import StorageService

                storage = StorageService(page)
                await storage.delete(STORAGE_HISTORY)
                await storage.flush()
            except Exception:
                pass
            state.history.clear()

        asyncio.create_task(_clear())

    def _on_re_search(entry: dict):
        query = entry.get("query") or entry.get("username", "")
        mode = entry.get("mode") or (MODE_EMAIL if "@" in query else MODE_USERNAME)
        if not query:
            return
        state.search_mode = mode
        controller.show_results()

        async def _search():
            if mode == MODE_EMAIL:
                await controller.start_email_search(query)
            else:
                await controller.start_search(query)

        asyncio.create_task(_search())

    if not history:
        body = EmptyState(
            title="No search history",
            message="Your search history will appear here.",
            icon=ft.Icons.HISTORY_ROUNDED,
        )
    else:
        items = []
        # state.history is newest-first — render it as-is so the most
        # recent search sits on top regardless of how this session was
        # started (fresh load vs in-app searches).
        for entry in history:
            query = entry.get("query") or entry.get("username", "")
            mode = entry.get("mode") or (MODE_EMAIL if "@" in query else MODE_USERNAME)
            found = entry.get("found", 0)
            total = entry.get("total", 0)
            ts = entry.get("timestamp", "")
            is_email = mode == MODE_EMAIL

            dismiss_bg = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.DELETE_ROUNDED, color=ft.Colors.WHITE),
                        ft.Text("Delete", color=ft.Colors.WHITE),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
                bgcolor=ft.Colors.ERROR,
                alignment=ft.Alignment.CENTER_RIGHT,
                padding=ft.Padding(0, 0, tokens.SPACE_XL, 0),
            )
            inner_tile = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Icon(
                                ft.Icons.ALTERNATE_EMAIL_ROUNDED
                                if is_email
                                else ft.Icons.PERSON_SEARCH_ROUNDED,
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
                                    query,
                                    size=tokens.FONT_LG,
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Row(
                                    controls=[
                                        ft.Text(
                                            f"{found}/{total} matches",
                                            size=tokens.FONT_SM,
                                            color=ft.Colors.with_opacity(
                                                tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
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
                                            "Email" if is_email else "Username",
                                            size=tokens.FONT_XS,
                                            color=ft.Colors.PRIMARY,
                                            weight=ft.FontWeight.W_500,
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
                            on_click=lambda e, ent=entry: _on_re_search(ent),
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
                ink=True,
                on_click=lambda e, ent=entry: _on_re_search(ent),
            )

            # Swipe-to-delete via Dismissible
            def _make_dismiss(ent=entry):
                def _on_dismiss(e):
                    try:
                        state.history.remove(ent)
                        import asyncio as _asyncio
                        from services.storage_service import StorageService
                        from flet import context

                        s = StorageService(context.page)
                        all_entries = list(reversed(state.history))
                        import json as _json

                        _asyncio.create_task(
                            s.set("sherlock_history", _json.dumps(all_entries))
                        )
                    except Exception:
                        pass

                return _on_dismiss

            tile = ft.Dismissible(
                content=inner_tile,
                background=dismiss_bg,
                dismiss_direction=ft.DismissDirection.END_TO_START,
                on_dismiss=_make_dismiss(),
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

    header_actions = []
    if history:
        header_actions.append(
            ft.IconButton(
                icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                tooltip="Clear History",
                icon_color=ft.Colors.ERROR,
                on_click=lambda e: _on_clear_all(),
            )
        )

    return ft.Column(
        controls=[
            AppHeader(
                page,
                title="History",
                subtitle="Recent searches & targets",
                on_settings=lambda e: (
                    controller.show_settings() if controller.show_settings else None
                ),
                extra_actions=header_actions,
            ),
            ft.Container(content=body, expand=True),
            build_banner_ad(),
        ],
        expand=True,
        spacing=0,
    )
