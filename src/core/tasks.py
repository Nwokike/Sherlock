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


def spawn(coro: Coroutine[Any, Any, Any], name: str | None = None) -> asyncio.Task:
    """Create a tracked background task; log failures instead of dropping them.

    When no name is supplied, use the coroutine's qualified name so device
    logs identify the actual failing callback instead of saying only
    ``bg-task`` (which made ``Frozen controls`` impossible to trace).
    """
    task_name = (
        name
        or getattr(coro, "__qualname__", None)
        or getattr(getattr(coro, "cr_code", None), "co_name", None)
        or "bg-task"
    )
    task = asyncio.create_task(coro, name=task_name)

    def _done(t: asyncio.Task) -> None:
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.warning("Background task %r failed: %s", task_name, exc)

    task.add_done_callback(_done)
    return task
