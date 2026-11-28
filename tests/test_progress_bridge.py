"""Tests for the scan-worker → main-loop progress bridge.

Regression: the bridge used page.run_task from the sherlock worker
thread; flet evaluates `session.connection.loop` there (no running
loop), raises after creating the callback coroutine, and the tick is
silently lost ("coroutine '_apply_progress' was never awaited").
"""

import asyncio
import threading
from types import SimpleNamespace

from core.constants import MODE_USERNAME
from core.state import state
from main import AppController


class _StrictPage:
    """Fails the test if the bridge touches the page in any way."""

    def __getattr__(self, name):
        raise AssertionError(f"bridge touched page.{name} (must use _main_loop)")


def test_progress_tick_reaches_main_loop():
    async def scenario():
        controller = AppController(_StrictPage())
        controller._main_loop = asyncio.get_running_loop()
        tick = SimpleNamespace(username="alice", is_running=True)
        saved = (
            state.search_mode,
            state.current_username,
            state.search_targets,
            state.search_progress,
        )
        changes: list[str | None] = []
        dispose = state.subscribe(lambda _sender, field: changes.append(field))

        def worker():
            controller._progress_from_thread(tick)

        try:
            state.search_mode = MODE_USERNAME
            state.current_username = "alice"
            state.search_targets = ["alice"]
            state.search_progress = None

            # The bridge marks dirty; the render-budget flusher owns the
            # observable publication (~500ms window), so start it and wait.
            controller._start_render_flusher()
            threading.Thread(target=worker, daemon=True).start()

            for _ in range(250):  # up to ~5s for the cross-thread hop + flush
                if state.search_progress is tick:
                    break
                await asyncio.sleep(0.02)

            assert state.search_progress is tick
            assert changes.count("search_progress") == 1
        finally:
            controller._stop_render_flusher()
            dispose()
            (
                state.search_mode,
                state.current_username,
                state.search_targets,
                state.search_progress,
            ) = saved

    asyncio.run(scenario())


def test_progress_without_captured_loop_is_dropped_safely():
    controller = AppController(_StrictPage())
    controller._main_loop = None
    controller._progress_from_thread(object())  # must not raise
