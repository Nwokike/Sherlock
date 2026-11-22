"""Wake lock keeps the screen on only while a scan is genuinely live.

The foreground service keeps the engine alive in the background; the wake
lock holds the display. It must drop when the app is backgrounded and only
re-arm on resume if a scan is still running.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import flet as ft

from core.constants import MODE_USERNAME
from core.state import state
from main import AppController
from services.sherlock_service import SearchProgress


class _FakeWakelock:
    def __init__(self):
        self.enabled = False
        self.calls: list = []
        self.raises = None

    async def enable(self):
        if self.raises:
            raise self.raises
        self.enabled = True
        self.calls.append("on")

    async def disable(self):
        if self.raises:
            raise self.raises
        self.enabled = False
        self.calls.append("off")

    async def is_enabled(self):
        return self.enabled


class _Event:
    def __init__(self, lifecycle_state):
        self.state = lifecycle_state


def _controller(wakelock):
    controller = AppController(MagicMock())
    controller.wakelock = wakelock
    controller.connectivity = None
    return controller


def _snapshot():
    return (
        state.is_searching,
        state.search_progress,
        state.current_username,
        state.search_mode,
    )


def _restore(snap):
    (
        state.is_searching,
        state.search_progress,
        state.current_username,
        state.search_mode,
    ) = snap


def test_wakelock_follows_scan_liveness_across_lifecycle():
    wl = _FakeWakelock()
    controller = _controller(wl)
    snap = _snapshot()
    try:
        state.is_searching = True
        state.search_progress = SearchProgress(
            username="alice", total_sites=10, is_running=True
        )
        state.current_username = "alice"
        state.search_mode = MODE_USERNAME

        asyncio.run(controller._on_lifecycle_change(_Event(ft.AppLifecycleState.RESUME)))
        assert wl.enabled, "a live scan must hold the screen awake"

        asyncio.run(controller._on_lifecycle_change(_Event(ft.AppLifecycleState.HIDE)))
        assert not wl.enabled, "backgrounding must drop the wake lock"

        asyncio.run(controller._on_lifecycle_change(_Event(ft.AppLifecycleState.RESUME)))
        assert wl.enabled, "a still-live scan re-arms on resume"

        # The scan ended: resume must not keep the screen on.
        state.is_searching = False
        state.search_progress = None
        asyncio.run(controller._on_lifecycle_change(_Event(ft.AppLifecycleState.RESUME)))
        assert not wl.enabled
        assert wl.calls[-1] == "off"
    finally:
        _restore(snap)


def test_wakelock_failures_are_swallowed():
    wl = _FakeWakelock()
    wl.raises = RuntimeError("no native service")
    controller = _controller(wl)
    asyncio.run(controller._set_wakelock(True))
    asyncio.run(controller._set_wakelock(False))
    assert wl.calls == []


def test_resume_does_not_hold_the_lock_for_a_stale_progress():
    """is_searching alone is not liveness; a stopped progress must not hold it."""
    wl = _FakeWakelock()
    controller = _controller(wl)
    snap = _snapshot()
    try:
        state.is_searching = True
        state.current_username = "alice"
        state.search_mode = MODE_USERNAME
        state.search_progress = SearchProgress(
            username="alice", total_sites=100, is_running=False
        )
        asyncio.run(controller._on_lifecycle_change(_Event(ft.AppLifecycleState.RESUME)))
        assert not wl.enabled, "a stale progress held the wake lock"
    finally:
        _restore(snap)
