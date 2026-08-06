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


def _noop_sync() -> None:
    """No-op sync default."""


def _noop_lambda(_mode: str = "tv") -> None:
    """No-op lambda for open_search."""


@dataclass
class ControllerMethods:
    """Subset of AppController methods exposed to the component tree.

    Mutable (not frozen) so AppController can build it incrementally.
    AppShell further mutates it with view-local closures (show_results,
    go_home, back, etc.) during its render.
    """

    # AppController-populated (heavy, async)
    refresh_sites: Callable[[], Awaitable[None]] = _noop_async
    start_search: Callable[[str], Awaitable[None]] = _noop_search
    cancel_search: Callable[[], None] = _noop_sync

    # AppShell-populated (view-local, sync closures)
    show_results: Callable[[], None] = _noop_sync
    show_sites: Callable[[], None] = _noop_sync
    show_settings: Callable[[], None] = _noop_sync
    show_history: Callable[[], None] = _noop_sync
    go_home: Callable[[], None] = _noop_sync
    back: Callable[[], None] = _noop_sync
    toggle_theme: Callable[[], None] = _noop_sync
    open_search: Callable[[str], None] = _noop_lambda

    # Modal helpers (future-proofing)
    pop_modal: Callable[[str], Awaitable[None]] = _noop_async
    close_modal: Callable[[], Awaitable[None]] = _noop_async


ControllerMethodsCtx = ft.create_context(ControllerMethods())

__all__ = ["ControllerMethods", "ControllerMethodsCtx"]
