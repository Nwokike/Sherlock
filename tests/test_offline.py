"""Tests for offline/connectivity handling.

Covers the search gate (no 400-site scan while offline), the
hard-failure surfacing, and the ft.Connectivity handler logic that
drives state.is_online.
"""

import asyncio
import types

import flet as ft
import pytest

from core.constants import ERR_NETWORK, MSG_OFFLINE, MSG_SEARCH_OFFLINE
from core.state import state
from main import AppController


class _StubSherlockService:
    """Minimal stand-in that records calls and can be made to fail."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.search_calls = 0

    async def load_sites(self):
        return 100

    async def search(self, username, on_progress=None, timeout=30):
        self.search_calls += 1
        if self.fail:
            raise RuntimeError("connection failed: DNS lookup timed out")
        return None


class _FakeConnectivity:
    """Stand-in for ft.Connectivity with a scripted probe result."""

    def __init__(self, result):
        self._result = result
        self.probe_calls = 0

    async def get_connectivity(self):
        self.probe_calls += 1
        return self._result


@pytest.fixture
def controller(fake_page):
    c = AppController(fake_page)
    yield c
    # Restore singleton fields touched by these tests
    state.is_online = True
    state.is_searching = False
    state.search_error = None
    state.current_username = ""


class TestSearchGate:
    def test_offline_search_blocked(self, controller):
        """Offline, start_search must not launch the scan at all."""
        stub = _StubSherlockService()
        controller.sherlock_service = stub
        state.is_online = False

        asyncio.run(controller.start_search("testuser"))

        assert stub.search_calls == 0
        assert state.is_searching is False
        assert state.current_username == ""
        assert controller.page.snack_bar is not None

    def test_offline_gate_message(self, controller):
        controller.sherlock_service = _StubSherlockService()
        state.is_online = False

        asyncio.run(controller.start_search("testuser"))

        assert controller.page.snack_bar.content.value == MSG_SEARCH_OFFLINE

    def test_online_search_failure_shows_network_error(self, controller):
        """A hard failure online must be surfaced, not silently empty."""
        controller.sherlock_service = _StubSherlockService(fail=True)
        state.is_online = True

        asyncio.run(controller.start_search("testuser"))

        assert state.search_error is not None
        assert state.is_searching is False
        assert controller.page.snack_bar.content.value == ERR_NETWORK


class TestConnectivityHandlers:
    @staticmethod
    def _event(connectivity):
        return types.SimpleNamespace(connectivity=connectivity)

    def test_change_to_offline(self, controller):
        state.is_online = True
        controller._on_connectivity_change(
            self._event([ft.ConnectivityType.NONE])
        )
        assert state.is_online is False
        assert controller.page.snack_bar is not None
        assert controller.page.snack_bar.content.value == MSG_OFFLINE

    def test_change_to_online(self, controller):
        state.is_online = False
        controller._on_connectivity_change(
            self._event([ft.ConnectivityType.WIFI])
        )
        assert state.is_online is True
        assert controller.page.snack_bar is not None

    def test_change_event_fallback_to_data(self, controller):
        """Defensive path: event without a `connectivity` attribute
        falls back to the raw e.data single type."""
        state.is_online = True
        event = types.SimpleNamespace(data=ft.ConnectivityType.NONE)
        controller._on_connectivity_change(event)
        assert state.is_online is False

    def test_init_connectivity_offline(self, controller):
        controller.connectivity = _FakeConnectivity([ft.ConnectivityType.NONE])
        asyncio.run(controller._init_connectivity())
        assert state.is_online is False

    def test_init_connectivity_online(self, controller):
        controller.connectivity = _FakeConnectivity([ft.ConnectivityType.WIFI])
        asyncio.run(controller._init_connectivity())
        assert state.is_online is True

    def test_init_connectivity_probe_error_keeps_online(self, controller):
        """A failed initial probe must not lock the app out (default
        stays online so the listener can correct it)."""

        class _Broken:
            async def get_connectivity(self):
                raise RuntimeError("no backend")

        controller.connectivity = _Broken()
        state.is_online = True
        asyncio.run(controller._init_connectivity())
        assert state.is_online is True
