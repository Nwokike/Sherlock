"""Tracked background tasks — fire-and-forget without losing exceptions.

Every bare ``asyncio.create_task()`` leaks failures silently (the coroutine's
exception is never retrieved) and trips RUF006. ``spawn()`` attaches a
done-callback that logs failures, so background work stays observable.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


_ACTIVE_TASKS: set[asyncio.Task] = set()


def cancel_all() -> None:
    """Cancel all registered active background tasks."""
    for t in list(_ACTIVE_TASKS):
        if not t.done():
            t.cancel()
    _ACTIVE_TASKS.clear()


def spawn(coro: Coroutine[Any, Any, Any], name: str = "bg-task") -> asyncio.Task:
    """Create a tracked background task; log failures instead of dropping them."""
    task = asyncio.create_task(coro, name=name)
    _ACTIVE_TASKS.add(task)

    def _done(t: asyncio.Task) -> None:
        _ACTIVE_TASKS.discard(t)
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.warning("Background task %r failed: %s", name, exc)

    task.add_done_callback(_done)
    return task


def spawn_replace(
    old_task: asyncio.Task | None,
    coro: Coroutine[Any, Any, Any],
    name: str = "bg-task",
) -> asyncio.Task:
    """Cancel old_task if still active, then spawn coro."""
    if old_task is not None and not old_task.done():
        old_task.cancel()
    return spawn(coro, name=name)
