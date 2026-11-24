"""The controller must actually drive the shade notifier and wake lock.

Unit tests of ScanNotifier alone do not prove main.py calls it; this drives
start_search/cancel/on_close with recording fakes and asserts the lifecycle.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from core.state import state
from main import AppController
from services.sherlock_service import SearchProgress


class _FakeNotifier:
    def __init__(self):
        self.calls: list = []

    async def mount(self):
        self.calls.append(("mount",))

    async def scan_started(self, target, *, is_email=False):
        self.calls.append(("start", target, is_email))

    async def progress(self, checked, total):
        self.calls.append(("progress", checked, total))

    async def scan_finished(self, found, total):
        self.calls.append(("finish", found, total))

    async def stop_service(self):
        self.calls.append(("stop",))

    async def shutdown(self):
        self.calls.append(("shutdown",))


class _FakeWakelock:
    def __init__(self):
        self.state = False
        self.calls: list = []

    async def enable(self):
        self.state = True
        self.calls.append("on")

    async def disable(self):
        self.state = False
        self.calls.append("off")


def _controller():
    c = AppController(MagicMock())
    c.scan_notify = _FakeNotifier()
    c.wakelock = _FakeWakelock()
    c.sherlock_service = MagicMock()
    c.sherlock_service.load_sites = AsyncMock()
    c.storage = MagicMock()
    c.storage.set = AsyncMock()
    c.storage.get = AsyncMock(return_value=None)
    c.ad_service = None
    c.enrich_service = None
    c._controller_methods = MagicMock()
    c._controller_methods.show_results = lambda: None
    return c


def _engine(**kwargs):
    async def run(**kw):
        return SearchProgress(
            username=kw.get("username", "alice"),
            total_sites=100,
            checked_sites=100,
            found=[],
            not_found=[],
            errors=[],
        )

    return run


def test_start_to_finish_arms_and_disarms():
    c = _controller()
    c.sherlock_service.search = _engine()
    snap = (
        state.is_searching,
        state.search_progress,
        state.current_username,
        state.search_targets,
        state.target_results,
        state.is_online,
        state.search_mode,
    )
    try:
        state.is_searching = False
        state.search_progress = None
        state.current_username = ""
        state.search_targets = []
        state.target_results = {}
        state.is_online = True
        state.search_mode = "username"

        asyncio.run(c.start_search("alice"))

        kinds = [k for k, *_ in c.scan_notify.calls]
        assert "start" in kinds, "scan_started was never called"
        assert "finish" in kinds, "scan_finished was never called"
        assert c.wakelock.calls[0] == "on" and c.wakelock.calls[-1] == "off", (
            f"wake lock lifecycle wrong: {c.wakelock.calls}"
        )
        assert c.wakelock.state is False
    finally:
        (
            state.is_searching,
            state.search_progress,
            state.current_username,
            state.search_targets,
            state.target_results,
            state.is_online,
            state.search_mode,
        ) = snap


def test_cancel_stops_the_shade_notification():
    c = _controller()
    c.sherlock_service.search = _engine()
    snap = (
        state.is_searching,
        state.search_progress,
        state.current_username,
        state.search_targets,
        state.target_results,
        state.is_online,
    )
    try:
        state.is_searching = False
        state.search_progress = None
        state.current_username = ""
        state.search_targets = []
        state.target_results = {}
        state.is_online = True

        async def run():
            await c.start_search("alice")
            c.cancel_search()

        asyncio.run(run())
        kinds = [k for k, *_ in c.scan_notify.calls]
        assert "stop" in kinds, "cancel did not stop the foreground service"
        assert c.wakelock.state is False
    finally:
        (
            state.is_searching,
            state.search_progress,
            state.current_username,
            state.search_targets,
            state.target_results,
            state.is_online,
        ) = snap


def test_progress_is_throttled_to_two_hz():
    c = _controller()
    c.scan_notify = MagicMock()
    c.scan_notify.progress = AsyncMock()
    c._last_notify_progress = 0.0

    async def _two_ticks():
        await c._notify_scan_progress(
            SearchProgress(username="alice", total_sites=100, checked_sites=1)
        )
        await c._notify_scan_progress(
            SearchProgress(username="alice", total_sites=100, checked_sites=2)
        )

    asyncio.run(_two_ticks())
    assert c.scan_notify.progress.call_count == 1, (
        "shade progress is not throttled — it would spam native calls"
    )
