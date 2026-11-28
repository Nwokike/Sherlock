"""The controller must actually drive the shade notifier and wake lock.

Unit tests of ScanNotifier alone do not prove main.py calls it; this drives
start_search/cancel/on_close with recording fakes and asserts the lifecycle.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock

from core.constants import MODE_USERNAME
from core.state import state
from main import AppController
from services.sherlock_service import SearchProgress


class _FakeNotifier:
    def __init__(self):
        self.calls: list = []

    async def mount(self):
        self.calls.append(("mount",))

    async def scan_started(self, target, *, kind="username"):
        self.calls.append(("start", target, kind))

    def progress(self, checked, total):
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


def test_progress_flusher_publishes_one_latest_snapshot():
    """One 0.5 s flush feeds BOTH surfaces from the same latest snapshot.

    This is the animepahe pattern: cache many worker ticks, publish once.
    """
    c = _controller()
    c.scan_notify = MagicMock()
    c.scan_notify.progress = MagicMock()
    first = SearchProgress(username="alice", total_sites=100, checked_sites=1)
    latest = SearchProgress(username="alice", total_sites=100, checked_sites=2)

    c._pending_progress = first
    c._pending_progress = latest
    c._render_dirty = True
    c._flush_pending_progress()

    assert c.scan_notify.progress.call_count == 1, (
        "one flush must queue exactly one shade update"
    )
    c.scan_notify.progress.assert_called_once_with(2, 100)
    assert state.search_progress is latest
    assert c._pending_progress is None
    # The bridge must never be awaited from the UI path (freeze risk):
    # the progress bridge is a plain sync call that only queues work.
    assert not inspect.iscoroutinefunction(c._notify_scan_progress)


class _RecordingNotifier:
    def __init__(self):
        self.calls: list[tuple[int, int]] = []

    def progress(self, checked: int, total: int) -> None:
        self.calls.append((checked, total))

    async def stop_service(self) -> None:
        pass


def test_live_flusher_publishes_latest_snapshot_to_both_surfaces():
    """Run the REAL 0.5 s loop, not just the helper.

    Two ticks inside one window must produce one UI publication and one
    shade update, both from the second tick. Removing the flush call from
    _render_flusher must fail this test.
    """
    c = _controller()
    notifier = _RecordingNotifier()
    c.scan_notify = notifier
    c._enrich_queue = None
    saved = (
        state.search_mode,
        state.current_username,
        state.search_targets,
        state.search_progress,
        state.is_searching,
    )
    try:
        state.search_mode = MODE_USERNAME
        state.current_username = "alice"
        state.search_targets = ["alice"]
        state.search_progress = None
        state.is_searching = True
        changes: list[str | None] = []
        dispose = state.subscribe(lambda _sender, field: changes.append(field))

        async def scenario():
            c._start_render_flusher()
            await c._apply_progress(
                SearchProgress(username="alice", total_sites=100, checked_sites=1)
            )
            await c._apply_progress(
                SearchProgress(username="alice", total_sites=100, checked_sites=2)
            )
            await asyncio.sleep(0.65)
            # Assert BEFORE stop: _stop_render_flusher also flushes the tail,
            # so checking only after it would let a broken live loop pass.
            assert state.search_progress is not None
            assert state.search_progress.checked_sites == 2
            assert notifier.calls == [(2, 100)]
            task = c._render_flush_task
            c._stop_render_flusher()
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)

        asyncio.run(scenario())
        assert state.search_progress is not None
        assert state.search_progress.checked_sites == 2
        assert notifier.calls == [(2, 100)]
        assert changes.count("search_progress") == 1
        assert changes.count("progress_version") == 0, (
            "fresh snapshots must not trigger a second full-tree render"
        )
    finally:
        dispose()
        (
            state.search_mode,
            state.current_username,
            state.search_targets,
            state.search_progress,
            state.is_searching,
        ) = saved


def test_kill_discards_pending_tick_before_the_next_flusher():
    """A queued tick from a killed scan must never be published by the next
    scan's flusher. Removing the _kill_all_activity buffer reset must fail."""
    c = _controller()
    notifier = _RecordingNotifier()
    c.scan_notify = notifier
    c._enrich_queue = None
    saved = (
        state.search_mode,
        state.current_username,
        state.search_targets,
        state.search_progress,
        state.is_searching,
    )
    try:
        state.search_mode = MODE_USERNAME
        state.current_username = "alice"
        state.search_targets = ["alice"]
        state.search_progress = None
        state.is_searching = True

        async def scenario():
            c._start_render_flusher()
            tick = SearchProgress(
                username="alice", total_sites=100, checked_sites=1
            )
            await c._apply_progress(tick)
            assert c._pending_progress is tick
            old_task = c._render_flush_task
            c._kill_all_activity("test-supersede")
            if old_task is not None:
                await asyncio.gather(old_task, return_exceptions=True)
            assert c._pending_progress is None

            c._start_render_flusher()
            await asyncio.sleep(0.65)
            task = c._render_flush_task
            c._stop_render_flusher()
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)

        asyncio.run(scenario())
        assert state.search_progress is None
        assert notifier.calls == []
    finally:
        (
            state.search_mode,
            state.current_username,
            state.search_targets,
            state.search_progress,
            state.is_searching,
        ) = saved
