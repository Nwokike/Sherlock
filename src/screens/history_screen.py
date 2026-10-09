"""HistoryScreen — past searches with clear-all and re-search actions.

@ft.component — reads observable state.history via AppStateCtx.
"""

from __future__ import annotations

import datetime
import logging

import flet as ft
from flet import Control

from components.app_header import AppHeader
from components.banner_ad import build_banner_ad
from components.empty_state import EmptyState
from core import tokens
from core.constants import (
    MODE_EMAIL,
    MODE_USERNAME,
    STORAGE_HISTORY,
    test_id,
)
from core.notify import show_snack
from core.tasks import spawn
from core.theme import AppColors
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("HistoryScreen")

_TIMESTAMP_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")


def _relative_time(ts: object) -> str:
    """Render a stored history timestamp as '5m ago / 3h ago / 2d ago'.

    Parses what `_save_to_history` (main.py) writes ("%Y-%m-%d %H:%M")
    plus seconds/T-separator/ISO variants. Returns the raw string
    unchanged when parsing fails or the entry is >= 30 days old (the
    full date stays more informative than "45d ago").
    """
    if not isinstance(ts, str) or not ts.strip():
        return str(ts) if ts else ""
    raw = ts.strip()
    parsed: datetime.datetime | None = None
    for fmt in _TIMESTAMP_FORMATS:
        try:
            # Naive-local to match the writer (strftime has no tz).
            parsed = datetime.datetime.strptime(raw, fmt)  # noqa: DTZ007, RUF100
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.datetime.fromisoformat(raw)
        except ValueError:
            return raw
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    delta = datetime.datetime.now() - parsed  # noqa: DTZ005, RUF100
    secs = delta.total_seconds()
    if secs < 0:  # clock skew / future stamp — show stored value
        return raw if secs < -60 else "just now"
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    days = int(secs // 86400)
    if days < 30:
        return f"{days}d ago"
    return raw


@ft.component
def HistoryScreen(banner: Control | None = None) -> Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    from flet import context

    try:
        page = context.page
    except Exception:
        page = None
    locked = (
        bool(getattr(state, "biometric_lock", False)) and not state.history_unlocked
    )
    history = [] if locked else (state.history if state.history else [])

    async def _unlock_history():
        from services.biometric_service import AuthStatus, authenticate_detailed

        # History read is low-friction: no sensitive-transaction elevation.
        result = await authenticate_detailed(
            "Unlock your search history", sensitive=False
        )
        if result.ok:
            state.history_unlocked = True
            state.progress_version += 1
            if page:
                show_snack(page, "History unlocked", bgcolor=AppColors.SUCCESS)
        elif page:
            if result.status == AuthStatus.LOCKOUT:
                show_snack(page, result.message, bgcolor=AppColors.ERROR)
            elif result.status == AuthStatus.CANCELLED:
                show_snack(page, "Unlock cancelled", bgcolor=AppColors.WARNING)
            elif result.message:
                # ERROR / UNAVAILABLE carry the concrete reason (timeout,
                # device unsupported, platform code) — show it, not a
                # generic string that hides the cause.
                show_snack(page, result.message, bgcolor=AppColors.ERROR)
            else:
                show_snack(
                    page,
                    "Biometric unlock failed",
                    bgcolor=AppColors.ERROR,
                )

    def _infer_mode(entry: dict, query: str) -> str:
        if entry.get("mode"):
            return entry["mode"]
        from services.email_service import validate_email

        return MODE_EMAIL if validate_email(query.strip()) else MODE_USERNAME

    # Hydrate history on mount if empty
    def _hydrate():
        async def _fetch():
            # Don't load sensitive entries into memory while locked.
            if locked:
                return
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
                        state.progress_version += 1
                except Exception:
                    pass

        spawn(_fetch())

    ft.use_effect(_hydrate, [])

    def _cancel_prompt():
        """Stop a pending OS prompt when leaving History (tab switch/back)."""

        async def _stop():
            try:
                from services.biometric_service import stop_prompt

                await stop_prompt()
            except Exception:
                pass

        spawn(_stop())

    ft.use_effect(lambda: None, [], cleanup=lambda: _cancel_prompt())

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
                state.progress_version += 1
                show_snack(page, "Search history cleared", bgcolor=AppColors.SUCCESS)

            spawn(_clear())

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
        if not isinstance(entry, dict):
            return
        query = entry.get("query") or entry.get("username", "")
        mode = _infer_mode(entry, query)
        if not query:
            show_snack(page, "Invalid history entry", bgcolor=AppColors.WARNING)
            return
        if controller.open_cached_result and controller.open_cached_result(query, mode):
            return
        _on_re_search(entry)

    def _on_re_search(entry: dict):
        if not isinstance(entry, dict):
            return
        query = entry.get("query") or entry.get("username", "")
        mode = _infer_mode(entry, query)
        if not query:
            show_snack(page, "Invalid history entry", bgcolor=AppColors.WARNING)
            return
        state.search_mode = mode
        controller.show_results()

        async def _search():
            if mode == MODE_EMAIL:
                await controller.start_email_search(query)
            else:
                await controller.start_search(query)

        spawn(_search())

    if locked:
        body = ft.Container(
            key=test_id("history-unlock"),
            content=EmptyState(
                title="History locked",
                message="Biometric unlock is required to view past searches.",
                icon=ft.Icons.LOCK_ROUNDED,
                action_label="Unlock",
                on_action=lambda e: spawn(_unlock_history()),
            ),
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
            if not isinstance(entry, dict):
                continue
            query = entry.get("query") or entry.get("username", "")
            mode = _infer_mode(entry, query)
            try:
                found = int(entry.get("found", 0) or 0)
            except TypeError, ValueError:
                found = 0
            try:
                total = int(entry.get("total", 0) or 0)
            except TypeError, ValueError:
                total = 0
            ts = _relative_time(entry.get("timestamp", ""))
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
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
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
                        idx = list(state.history).index(ent)
                    except ValueError:
                        return
                    state.history.remove(ent)
                    state.progress_version += 1

                    async def _persist_delete():
                        try:
                            from services.storage_service import (
                                StorageService,
                                encode_history_entries,
                            )

                            s = StorageService(page)
                            remaining = list(reversed(state.history))
                            await s.set(
                                STORAGE_HISTORY, encode_history_entries(remaining)
                            )
                            await s.flush()
                        except Exception:
                            pass

                    spawn(_persist_delete())
                    if page:
                        show_snack(
                            page,
                            "Entry deleted",
                            action_label="Undo",
                            on_action=lambda e: _undo_delete(ent, idx),
                        )

                return _on_dismiss

            def _undo_delete(ent, idx):
                state.history.insert(min(idx, len(state.history)), ent)
                state.progress_version += 1

                async def _persist_undo():
                    try:
                        from services.storage_service import (
                            StorageService,
                            encode_history_entries,
                        )

                        s = StorageService(page)
                        await s.set(
                            STORAGE_HISTORY,
                            encode_history_entries(list(reversed(state.history))),
                        )
                        await s.flush()
                    except Exception:
                        pass

                spawn(_persist_undo())

            tile = ft.Dismissible(
                key=ft.Key(f"{entry.get('query', '')}-{entry.get('timestamp', '')}"),
                content=inner_tile,
                background=dismiss_bg,
                secondary_background=dismiss_bg,
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
                on_click=lambda e: spawn(_unlock_history()),
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
