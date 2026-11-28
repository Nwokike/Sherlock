"""Regressions for the scan-lifecycle defects confirmed against flet 1.0.4.

The recursive-tail freeze and the superseded same-target cancel were both
reproduced on the shipped code; these tests must fail if either returns.
"""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from core.constants import MODE_USERNAME
from core.state import state
from main import AppController
from services.sherlock_service import (
    SearchProgress,
    _CancelHandle,
    _MaigretQueryNotify,
)


def _controller() -> AppController:
    c = AppController(MagicMock())
    c._controller_methods = MagicMock()
    c._controller_methods.show_results = lambda: None
    return c


def _snapshot():
    keys = (
        "search_targets",
        "target_results",
        "current_username",
        "search_mode",
        "is_searching",
        "search_progress",
        "last_results",
        "last_results_username",
    )
    return {k: getattr(state, k) for k in keys}, keys


def _restore(saved, keys):
    for k in keys:
        setattr(state, k, saved[k])


def test_recursive_secondary_stays_in_tick_scope():
    """`state.search_targets` is an observable COPY of the engine's list;
    secondaries must be published to the main loop, not appended only there.
    """
    saved, keys = _snapshot()
    c = _controller()
    loop = asyncio.new_event_loop()
    c._main_loop = loop
    try:
        state.search_targets = ["primary"]
        state.target_results = {}
        state.current_username = "primary"
        state.search_mode = MODE_USERNAME
        state.is_searching = True
        state.search_progress = None

        c._on_secondary_target("secondary")
        c._on_target_result(
            SearchProgress(username="secondary", total_sites=500, is_running=True)
        )
        loop.run_until_complete(asyncio.sleep(0.02))

        assert list(state.search_targets) == ["primary", "secondary"]
        assert "secondary" in state.target_results

        tick = SearchProgress(username="secondary", total_sites=500, is_running=True)
        loop.run_until_complete(c._apply_progress(tick))
        c._flush_pending_progress()
        assert state.search_progress is tick, "secondary tick was dropped — 99% freeze"
    finally:
        loop.close()
        c._main_loop = None
        _restore(saved, keys)


def test_superseded_same_target_cancel_cannot_clear_the_live_scan():
    """The CancelledError handler must use _owns_scan(), not target equality."""
    saved, keys = _snapshot()
    c = _controller()
    c.sherlock_service = MagicMock()
    c.sherlock_service.load_sites = AsyncMock()
    c.storage = MagicMock()
    c.storage.set = AsyncMock()
    stopped: list = []
    c._stop_render_flusher = lambda: stopped.append(1)

    async def engine(**kwargs):
        await asyncio.sleep(3600)  # cancellation propagates from to_thread

    c.sherlock_service.search = engine
    state.history = []
    state.target_results = {}
    state.is_searching = False
    state.search_progress = None
    state.is_online = True

    async def run():
        first = asyncio.create_task(c.start_search("alice"))
        await asyncio.sleep(0.05)
        # The retry button clears the flag optimistically (and a stale
        # progress object must not re-attach), exactly like the real UI.
        state.is_searching = False
        task_b = asyncio.create_task(c.start_search("alice"))
        await asyncio.sleep(0.05)
        try:
            await asyncio.wait_for(
                asyncio.gather(first, return_exceptions=True), timeout=2
            )
        except TimeoutError:
            pass
        assert state.is_searching is True, (
            "dying same-target scan cleared the live replacement's flag"
        )
        assert state.search_mode == MODE_USERNAME
        assert stopped == [], "dying scan stopped the live replacement's flusher"
        task_b.cancel()
        await asyncio.gather(task_b, return_exceptions=True)

    try:
        asyncio.run(run())
    finally:
        _restore(saved, keys)


def _maigret_result(site_name: str):
    return SimpleNamespace(
        site_name=site_name,
        site_url_user=f"https://example.com/{site_name}",
        status=SimpleNamespace(name="CLAIMED"),
        query_time=None,
        context=None,
        tags=[],
        ids_data=None,
        error=None,
        keyword_match_status=None,
    )


def test_retries_do_not_double_count_checked_sites():
    notify = _MaigretQueryNotify(
        total=3,
        cancel_event=threading.Event(),
        progress=SearchProgress(username="u", total_sites=3),
    )
    assert notify.progress is not None
    notify.update(_maigret_result("GitHub"))
    # maigret re-checks the same site after a failure: replace, don't recount
    notify.update(_maigret_result("GitHub"))
    assert notify.progress.checked_sites == 1
    assert len(notify.progress.found) == 1


def test_pretty_name_finds_the_real_site_object():
    site = MagicMock(url_main="https://picuki.com", protection=["bot"])
    notify = _MaigretQueryNotify(
        total=1,
        cancel_event=threading.Event(),
        progress=SearchProgress(username="u", total_sites=1),
        sites_lookup={"picuki": site},
    )
    notify.update(_maigret_result("Picuki [TikTok]"))
    # maigret's pretty_name must still resolve url_main + protection tags
    assert notify.progress.found[0].url_main == "https://picuki.com"
    assert notify.progress.found[0].protection == ["bot"]


def test_cancel_handle_is_generation_scoped():
    h = _CancelHandle()
    first_loop = object()
    h.loop = first_loop
    h.owner = first_loop
    second_loop = object()
    h.loop = second_loop
    h.owner = second_loop
    h.clear(first_loop)  # stale worker teardown
    assert h.loop is second_loop, "stale worker wiped the replacement's handle"
    h.clear(second_loop)
    assert h.loop is None
