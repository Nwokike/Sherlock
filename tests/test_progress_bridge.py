"""Tests for the scan-worker → main-loop progress bridge.

Regression: the bridge used page.run_task from the sherlock worker
thread; flet evaluates `session.connection.loop` there (no running
loop), raises after creating the callback coroutine, and the tick is
silently lost ("coroutine '_apply_progress' was never awaited").
"""

import asyncio
import threading

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
        before = state.progress_version

        def worker():
            controller._progress_from_thread(object())

        threading.Thread(target=worker, daemon=True).start()

        for _ in range(150):  # up to ~3s for the cross-thread hop
            if state.progress_version != before:
                break
            await asyncio.sleep(0.02)

        assert state.progress_version == before + 1

    asyncio.run(scenario())


def test_progress_without_captured_loop_is_dropped_safely():
    controller = AppController(_StrictPage())
    controller._main_loop = None
    controller._progress_from_thread(object())  # must not raise
