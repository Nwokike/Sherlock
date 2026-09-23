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
from core.notify import show_snack
from core.theme import AppColors
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("HistoryScreen")


@ft.component
def HistoryScreen(banner: Control | None = None) -> Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    from flet import context

    try:
        page = context.page
    except Exception:
        page = None
    locked = bool(getattr(state, "biometric_lock", False)) and not state.history_unlocked
    history = [] if locked else (state.history if state.history else [])

    async def _unlock_history():
        from services.biometric_service import authenticate

        ok = await authenticate("Unlock your search history")
        if ok:
            state.history_unlocked = True
            state.progress_version += 1
            if page:
                show_snack(page, "History unlocked", bgcolor=AppColors.SUCCESS)
        elif page:
            show_snack(
                page,
                "Biometric unlock failed or was cancelled",
                bgcolor=AppColors.ERROR,
            )

    # Hydrate history on mount if empty
    def _hydrate():
        async def _fetch():
            if not state.history and page:
                try:
                    from services.storage_service import (
                        StorageService,
                        load_history_entries,
                    )

                    storage = StorageService(page)
                    raw = await storage.get(STORAGE_HISTORY)
                    entries = load_history_entries(raw)
                    if entries:
                        state.history.clear()
                        state.history.extend(entries)
                except Exception:
                    pass

        asyncio.create_task(_fetch())

    ft.use_effect(_hydrate, [])

    # Portal-managed clear-confirm dialog (flet 1.0 use_dialog, P1-2).
    pending_dialog, set_pending_dialog = ft.use_state(None)
    try:
        # use_dialog touches ft.context.page, which raises outside a live
        # flet app (unit-test harness). The hook is still invoked every
        # render so hook ordering stays stable; in-app there is no throw.
        ft.use_dialog(pending_dialog)
    except RuntimeError:
        pass

    def _on_clear_all():
        if not page:
            return

        def _confirm_clear(e):
            set_pending_dialog(None)

            async def _clear():
                try:
                    from services.storage_service import StorageService

                    storage = StorageService(page)
                    await storage.delete(STORAGE_HISTORY)
                    await storage.flush()
                except Exception:
                    pass
                state.history.clear()
                show_snack(page, "Search history cleared", bgcolor=AppColors.SUCCESS)

            asyncio.create_task(_clear())

        dlg = ft.AlertDialog(
            modal=False,
            title=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.DELETE_SWEEP_ROUNDED,
                        color=ft.Colors.ERROR,
                        size=tokens.ICON_MD,
                    ),
                    ft.Text(
                        "Clear Search History",
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.BOLD,
                        font_family="Outfit",
                    ),
                ],
                spacing=tokens.SPACE_SM,
            ),
            content=ft.Text(
                "Are you sure you want to clear all past searches? This action cannot be undone.",
                size=tokens.FONT_SM,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: set_pending_dialog(None)),
                ft.FilledButton(
                    "Clear All",
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.ERROR, color=ft.Colors.WHITE
                    ),
                    on_click=_confirm_clear,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        set_pending_dialog(dlg)

    def _on_open_history(entry: dict):
        query = entry.get("query") or entry.get("username", "")
        mode = entry.get("mode") or (MODE_EMAIL if "@" in query else MODE_USERNAME)
        if not query:
            return
        if controller.open_cached_result and controller.open_cached_result(query, mode):
            return
        _on_re_search(entry)

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

    if locked:
        body = EmptyState(
            title="History locked",
            message="Biometric unlock is required to view past searches.",
            icon=ft.Icons.LOCK_ROUNDED,
        )
    elif not history:
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
                        ft.Container(
                            content=ft.IconButton(
                                icon=ft.Icons.REFRESH_ROUNDED,
                                tooltip="Rescan network targets",
                                icon_size=18,
                                icon_color=AppColors.PRIMARY,
                                on_click=lambda e, ent=entry: _on_re_search(ent),
                            ),
                            width=36,
                            height=36,
                            border_radius=18,
                            bgcolor=ft.Colors.with_opacity(0.12, AppColors.PRIMARY),
                            alignment=ft.Alignment.CENTER,
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
                on_click=lambda e, ent=entry: _on_open_history(ent),
            )

            # Swipe-to-delete via Dismissible
            def _make_dismiss(ent=entry):
                def _on_dismiss(e):
                    try:
                        state.history.remove(ent)
                        import asyncio as _asyncio

                        from flet import context

                        from services.storage_service import StorageService

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
    if locked:
        header_actions.append(
            ft.FilledButton(
                "Unlock",
                icon=ft.Icons.LOCK_OPEN_ROUNDED,
                on_click=lambda e: asyncio.create_task(_unlock_history()),
            )
        )
    elif history:
        header_actions.append(
            ft.IconButton(
                icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                tooltip="Clear History",
                icon_color=ft.Colors.ERROR,
                on_click=lambda e: _on_clear_all(),
            )
        )

    header_controls: list[Control] = [
        AppHeader(
            page,
            title="History",
            subtitle="Recent searches & targets",
            on_settings=lambda e: (
                controller.show_settings() if controller.show_settings else None
            ),
            extra_actions=header_actions,
        ),
    ]
    if banner:
        header_controls.append(banner)

    return ft.Column(
        controls=[
            *header_controls,
            ft.Container(content=body, expand=True),
            build_banner_ad(),
        ],
        expand=True,
        spacing=0,
    )
