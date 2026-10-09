"""Shared fixtures for component tests."""

import inspect
from collections import deque
from typing import Any

import flet as ft
import pytest


class FakeClientStorage:
    """Dict-backed stand-in for page.client_storage.

    Matches StorageService usage (sync get/set of a JSON string).
    Async variants are thin wrappers for forward-compat.
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        self._store[key] = value

    async def get_async(self, key: str) -> str | None:
        return self.get(key)

    async def set_async(self, key: str, value: str) -> None:
        self.set(key, value)


class FakePage:
    """Minimal stand-in for ft.Page for unit testing the controller branch.

    Only the methods AppController touches are implemented. Component
    render tests in later tasks extend this with `components_mode` toggling.
    """

    def __init__(
        self,
        route: str = "/",
        platform: ft.PagePlatform = ft.PagePlatform.WINDOWS,
        width: float = 1280.0,
        platform_brightness: ft.Brightness = ft.Brightness.LIGHT,
    ):
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
        self.on_app_lifecycle_state_change = None
        self.platform = platform
        self.platform_brightness = platform_brightness
        self.width = width
        self.client_storage = FakeClientStorage()
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

    async def run_task_and_wait(self, coro_or_fn, *args, **kwargs):
        """Awaitable variant for tests needing real execution.

        Logs the identical ("run_task", ...) tuple so existing
        logging-only assertions keep passing.
        """
        self._render_calls.append(("run_task", coro_or_fn, args, kwargs))
        if inspect.iscoroutinefunction(coro_or_fn):
            return await coro_or_fn(*args, **kwargs)
        result = coro_or_fn(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    @property
    def render_calls(self):
        return list(self._render_calls)

    @property
    def pushed_routes(self):
        return list(self._pushed_routes)

    @property
    def dialogs(self):
        return list(self._dialogs)

    @property
    def update_calls(self):
        return self._update_calls


@pytest.fixture
def fake_page():
    return FakePage()


@pytest.fixture(autouse=True)
def _reset_shared_http_client():
    """Fresh shared httpx client per test — its proxy-keyed cache would
    otherwise leak a (possibly monkeypatched-away) client across tests."""
    import services.http_client as http_client

    http_client._client = None
    http_client._client_proxy = None
    http_client._client_retries = None
    yield
    http_client._client = None
    http_client._client_proxy = None
    http_client._client_retries = None
