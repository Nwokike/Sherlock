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


def spawn(coro: Coroutine[Any, Any, Any], name: str = "bg-task") -> asyncio.Task:
    """Create a tracked background task; log failures instead of dropping them."""
    task = asyncio.create_task(coro, name=name)

    def _done(t: asyncio.Task) -> None:
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.warning("Background task %r failed: %s", name, exc)

    task.add_done_callback(_done)
    return task
