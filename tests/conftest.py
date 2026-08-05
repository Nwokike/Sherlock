"""Shared fixtures for component tests."""

from collections import deque
from typing import Any

import pytest


class FakePage:
    """Minimal stand-in for ft.Page for unit testing the controller branch.

    Only the methods AppController touches are implemented. Component
    render tests in later tasks extend this with `components_mode` toggling.
    """

    def __init__(self, route: str = "/"):
        self.title = ""
        self.padding: Any = 0
        self.spacing = 0
        self.fonts: dict[str, str] = {}
        self.theme = None
        self.dark_theme = None
        self.theme_mode = None
        self.route = route
        self.views: list[Any] = []
        self.on_error = None
        self.on_route_change = None
        self.on_view_pop = None
        self.on_disconnect = None
        self.on_close = None
        self._render_calls: deque = deque()
        self._update_calls: int = 0
        self._dialogs: deque = deque()
        self._pushed_routes: deque = deque()
        self.services: list[Any] = []
        self.file_picker = None
        self.window: Any = type("W", (), {"min_width": 0, "min_height": 0})()

    def render(self, component: Any, *args: Any, **kwargs: Any) -> None:
        self._render_calls.append((component, args, kwargs))

    def render_views(self, component: Any, *args: Any, **kwargs: Any) -> None:
        self._render_calls.append((component, args, kwargs))

    def update(self, *controls: Any) -> None:
        self._update_calls += 1

    def schedule_update(self) -> None:
        self._update_calls += 1

    def show_dialog(self, dialog: Any) -> None:
        self._dialogs.append(dialog)

    def pop_dialog(self) -> None:
        if self._dialogs:
            self._dialogs.pop()

    def push_route(self, route: str) -> None:
        self._pushed_routes.append(route)

    def pop_views_until(self, route: str, result: Any = None) -> None:
        while self.views and getattr(self.views[-1], "route", None) != route:
            self.views.pop()

    def run_task(self, coro_or_fn, *args, **kwargs):
        self._render_calls.append(("run_task", coro_or_fn, args, kwargs))

    @property
    def render_calls(self):
        return list(self._render_calls)

    @property
    def pushed_routes(self):
        return list(self._pushed_routes)


@pytest.fixture
def fake_page():
    return FakePage()
