"""use_debounce — custom hook for debouncing a value across renders.

Mirrors KTV's use_debounce exactly.

Usage inside a @ft.component:
    query, set_query = ft.use_state("")
    debounced_query = use_debounce(query, 250)
"""

import asyncio

import flet as ft


def use_debounce(value, delay_ms: int = 250):
    """Return the debounced version of value — updates only delay_ms
    after the last actual change."""
    debounced, set_debounced = ft.use_state(value)
    timer = ft.use_ref(None)

    def _cancel_and_schedule():
        old = timer.current
        if old is not None and not old.done():
            old.cancel()

        async def _after_delay():
            await asyncio.sleep(delay_ms / 1000.0)
            set_debounced(value)

        timer.current = asyncio.create_task(_after_delay())

    def _cleanup():
        old = timer.current
        if old is not None and not old.done():
            old.cancel()

    ft.use_effect(_cancel_and_schedule, [value], cleanup=_cleanup)

    return debounced
