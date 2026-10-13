"""HistoryScreen — past searches with clear-all and re-search actions.

@ft.component — reads observable state.history via AppStateCtx.
"""

from __future__ import annotations

import logging

import flet as ft
from flet import Control

from components.app_header import AppHeader
from components.banner_ad import pooled_banner_ad
from components.empty_state import EmptyState
from core import tokens
from core.constants import MODE_EMAIL, MODE_USERNAME, STORAGE_HISTORY
from core.notify import show_snack
from core.tasks import spawn
from core.theme import AppColors
from services.storage_service import encode_history_entries
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("HistoryScreen")


def _relative_time(raw) -> str:
    """Humanise a stored write timestamp.

    The writer emits `"%Y-%m-%d %H:%M"` (minute precision) — seconds/T/ISO
    variants and a raw fallback are accepted so older or hand-written entries
    still render. Never raises: an unparseable value comes back unchanged.
    """
    if not isinstance(raw, str) or not raw:
        return ""
    import datetime as _dt

    # The writer emits naive-local (`time.strftime`, no tz), so comparisons
    # must stay naive-local; making them aware would silently shift every value.
    parsed = None
    for fmt in (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
    ):
        try:
            parsed = _dt.datetime.strptime(  # noqa: DTZ007 — naive-local
                raw.strip()[:19], fmt
            )
            break
        except ValueError:
            continue
    if parsed is None:
        return raw

    delta = _dt.datetime.now() - parsed  # noqa: DTZ005 — naive-local
    seconds = int(delta.total_seconds())
    if seconds < 0:
        # Clock skew on the device: prefer the timestamp over a lie.
        return raw
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    # Older than a month is history proper — the full date is more useful.
    return raw


def _infer_mode(entry, query: str) -> str:
    """Which engine a stored entry belongs to.

    Trusts a stored `mode`; only falls back to the email validator for
    legacy entries that predate the field. `"@" in query` is not enough —
    it classifies `a@b` and `foo@bar` as email when they are not.
    """
    mode = entry.get("mode") if isinstance(entry, dict) else None
    if mode in (MODE_EMAIL, MODE_USERNAME):
        return mode
    from services.email_service import validate_email

    return MODE_EMAIL if validate_email((query or "").strip()) else MODE_USERNAME


@ft.component
def HistoryScreen(banner: Control | None = None) -> Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    from flet import context

    try:
        page = context.page
    except Exception:
        page = None
    history = state.history if state.history else []

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

        spawn(_fetch(), "history-hydrate")

    ft.use_effect(_hydrate, [])

    def _clear_unseen():
        # Opening History consumes the badge (the entries are now visible).
        if getattr(state, "history_unseen", 0):
            state.history_unseen = 0

    ft.use_effect(_clear_unseen, [])

    def _on_clear_all():
        if not page:
            return

        def _confirm_clear(e):
            page.pop_dialog()

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

            spawn(_clear(), "history-clear")

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
                ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
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
        page.show_dialog(dlg)

    def _on_open_history(entry: dict):
        query = entry.get("query") or entry.get("username", "")
        mode = _infer_mode(entry, query)
        if not query:
            return
        if controller.open_cached_result and controller.open_cached_result(query, mode):
            return
        _on_re_search(entry)

    def _on_re_search(entry: dict):
        query = entry.get("query") or entry.get("username", "")
        mode = _infer_mode(entry, query)
        if not query:
            return
        # search_mode is deliberately NOT set here: start_*_search owns it
        # after its own gates, so a retry that gets blocked (offline/busy)
        # cannot strand a live scan of the other mode with its ticks dropped
        # by the cross-mode guard in _apply_progress.
        controller.show_results()

        async def _search():
            if mode == MODE_EMAIL:
                await controller.start_email_search(query)
            else:
                await controller.start_search(query)

        spawn(_search(), "history-research")

    def _offer_undo(idx: int, entry):
        """Offer to put a just-swiped entry back where it came from.

        The removal is not persisted until the snackbar expires or the user
        keeps it gone, so an accidental swipe is one tap from fixed.
        """
        if not isinstance(entry, dict):
            return

        def _undo(_e):
            if entry in list(state.history):
                return
            at = idx if 0 <= idx <= len(state.history) else len(state.history)
            state.history.insert(at, entry)
            state.progress_version += 1

        show_snack(
            page,
            "Search removed",
            bgcolor=AppColors.SUCCESS,
            action_label="Undo",
            on_action=_undo,
        )

    items: list[Control] = []
    if not history:
        items.append(
            EmptyState(
                title="No search history",
                message="Your search history will appear here.",
                icon=ft.Icons.HISTORY_ROUNDED,
            )
        )
    else:
        # state.history is newest-first — render it as-is so the most
        # recent search sits on top regardless of how this session was
        # started (fresh load vs in-app searches).
        for entry in history:
            query = entry.get("query") or entry.get("username", "")
            mode = _infer_mode(entry, query)
            found = entry.get("found", 0)
            total = entry.get("total", 0)
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
                            from services.storage_service import StorageService

                            s = StorageService(page)
                            await s.set(
                                STORAGE_HISTORY, encode_history_entries(state.history)
                            )
                            await s.flush()
                        except Exception:
                            logger.warning(
                                "History delete persist failed", exc_info=True
                            )

                    spawn(_persist_delete(), "history-delete-persist")
                    _offer_undo(idx, ent)

                return _on_dismiss

            # ValueKey (not base Key): base Key has `_type=None` and is not in
            # flet's KeyValue union, so Flutter gets no key kind. Identity
            # carries found/total because `query-timestamp` alone collides at
            # the writer's minute precision — two scans of the same handle
            # inside one minute would otherwise reconcile to the same tile.
            tile = ft.Dismissible(
                key=ft.ValueKey(f"{query}|{entry.get('mode')}|{ts}|{found}/{total}"),
                content=inner_tile,
                background=dismiss_bg,
                dismiss_direction=ft.DismissDirection.END_TO_START,
                on_dismiss=_make_dismiss(),
            )
            items.append(tile)

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

    # The ListView is the root, not a Column child. `expand` is honoured only
    # when the DIRECT parent is a Column/Row/View/Page (.venv flet
    # controls/control.py:33; only column.py:86, row.py:102 and view.py:163
    # set host_expanded), so the previous shape — ListView inside a Container
    # inside a Column — left the list unbounded and un-scrollable, clipping
    # any history taller than one viewport. Header items ride inside the
    # The ListView owns the only scroll (a Column root gives it unbounded
    # height) and the header rides inside the list. Padding must therefore
    # go on the ROWS, not the list root: a root padding would inset
    # `AppHeader` on top of its own, which is why History's header looked
    # narrower/hardcoded next to Settings and Home (whose roots carry no
    # padding and whose header keeps only its own).
    return ft.ListView(
        controls=[
            *header_controls,
            ft.Column(controls=items, spacing=0, expand=True),
            pooled_banner_ad("history-1"),
        ],
        spacing=0,
        expand=True,
        padding=ft.Padding(0, 0, 0, tokens.SPACE_LG),
    )
