"""Context exposing AppController callbacks to the component tree.

AppShell is rendered via page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))
so AppController cannot pass callbacks into AppShell's constructor.
Instead, AppController builds a mutable ControllerMethods dataclass with
its actual methods, then AppShell injects view-local closures (show_results,
go_home, etc.) by mutating the same instance.  Components read callbacks
via use_context(ControllerMethodsCtx).

Defaults are no-ops so the shell renders safely even before the provider
is mounted (e.g. inside unit tests that instantiate AppShell directly).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import flet as ft


async def _noop_async() -> None:
    """No-op async default."""


async def _noop_search(_username: str) -> None:
    """No-op async default for start_search(username)."""


async def _noop_save_sites(_sites: list[str]) -> None:
    """No-op async default for save_selected_sites(sites)."""


def _noop_sync() -> None:
    """No-op sync default."""


def _noop_dialog(_dialog) -> None:
    """No-op open_sheet(dialog) default (use_dialog portal)."""


async def _noop_health() -> dict:
    """No-op run_db_health() default."""
    return {}


@dataclass
class ControllerMethods:
    """Subset of AppController methods exposed to the component tree.

    Mutable (not frozen) so AppController can build it incrementally.
    AppShell further mutates it with view-local closures (show_results,
    go_home, back, etc.) during its render.
    """

    # AppController-populated (heavy, async or cache)
    refresh_sites: Callable[[], Awaitable[None]] = _noop_async
    start_search: Callable[[str], Awaitable[None]] = _noop_search
    cancel_search: Callable[[], None] = _noop_sync
    start_email_search: Callable[[str], Awaitable[None]] = _noop_search
    cancel_email_search: Callable[[], None] = _noop_sync
    save_selected_sites: Callable[[list[str]], Awaitable[None]] = _noop_save_sites
    check_for_updates: Callable[[], Awaitable[None]] = _noop_async
    open_update_dialog: Callable[[], None] = _noop_sync
    set_onboarding_done: Callable[[], Awaitable[None]] = _noop_async
    open_cached_result: Callable[[str, str], bool] = lambda _q, _m: False

    # AppShell-populated (view-local, sync closures)
    show_results: Callable[[], None] = _noop_sync
    show_sites: Callable[[], None] = _noop_sync
    show_settings: Callable[[], None] = _noop_sync
    show_history: Callable[[], None] = _noop_sync
    go_home: Callable[[], None] = _noop_sync
    back: Callable[[], None] = _noop_sync
    # use_dialog portal — AppShell owns the single overlay dialog state
    # (identity-preserving across scan re-renders, flet 1.0 P1-2).
    open_sheet: Callable[[object], None] = _noop_dialog
    close_dialog: Callable[[], None] = _noop_sync
    run_db_health: Callable[[], Awaitable[dict]] = _noop_health
    # System/back-button handler injected by AppShell (owns view+tab state).
    handle_system_back: Callable[[], None] = _noop_sync


ControllerMethodsCtx = ft.create_context(ControllerMethods())

__all__ = ["ControllerMethods", "ControllerMethodsCtx"]
