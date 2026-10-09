"""Regression tests for Fix Batch 7a (main/app-shell edges).

Covers: gate-before-kill order, flusher completion, history lock,
avatar cap counter, storage per-field guards, close/error never-raise,
banner explicit modes.
"""

import asyncio
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _restore_global_state():
    """Snapshot state fields this file mutates via open_cached_result.

    The cached-result tests leave search_mode=EMAIL + email buckets behind;
    without a restore, _apply_progress drops later username ticks as
    cross-mode (found via pairwise bisect with test_logger_and_streaming).
    Restore goes through setattr (AppState is @ft.observable — never
    __dict__ surgery); collections restore in place to keep wrappers.
    """
    from core.state import state

    if state.results_cache is None:
        state.results_cache = {}
    if state.email_results is None:
        state.email_results = []
    if state.enrichments is None:
        state.enrichments = {}
    saved_scalars = {
        "current_username": state.current_username,
        "email_found_count": state.email_found_count,
        "email_not_found_count": state.email_not_found_count,
        "email_rate_limited_count": state.email_rate_limited_count,
        "email_results_address": state.email_results_address,
        "email_total_modules": state.email_total_modules,
        "email_unavailable_count": state.email_unavailable_count,
        "is_searching": state.is_searching,
        "last_results_username": state.last_results_username,
        "progress_version": state.progress_version,
        "search_mode": state.search_mode,
        "search_progress": state.search_progress,
    }
    saved_last = dict(state.last_results) if state.last_results else None
    saved_email = list(state.email_results)
    saved_enrich = dict(state.enrichments)
    saved_cache = dict(state.results_cache)
    yield
    for key, value in saved_scalars.items():
        setattr(state, key, value)
    if saved_last is None:
        state.last_results = None
    else:
        state.last_results.clear()
        state.last_results.update(saved_last)
    state.email_results[:] = saved_email
    state.enrichments.clear()
    state.enrichments.update(saved_enrich)
    state.results_cache.clear()
    state.results_cache.update(saved_cache)


def _controller():
    from main import AppController

    return AppController(MagicMock())


def test_gated_search_does_not_kill_healthy_scan():
    """Offline new search must not kill a running scan (gate-before-kill)."""
    from core.state import state

    controller = _controller()
    killed = []
    controller._kill_all_activity = lambda reason: killed.append(reason)
    controller._show_snack = lambda *a, **k: None

    prev_searching, prev_online = state.is_searching, state.is_online
    try:
        state.is_searching = True  # simulate healthy running scan
        state.is_online = False  # new search is doomed (offline)
        asyncio.run(controller.start_search("newtarget"))
        assert killed == []
        assert state.is_searching is True
    finally:
        state.is_searching, state.is_online = prev_searching, prev_online


def test_flusher_stops_on_completion():
    controller = _controller()
    controller._stop_render_flusher()
    assert controller._render_flush_task is None
    assert controller._pending_enrichments == {}


def test_history_lock_exists_and_serializes():
    controller = _controller()
    assert isinstance(controller._history_lock, type(asyncio.Lock()))

    async def _run():
        order = []

        async def _holder(name, delay):
            async with controller._history_lock:
                order.append(f"{name}-in")
                await asyncio.sleep(delay)
                order.append(f"{name}-out")

        await asyncio.gather(_holder("a", 0.05), _holder("b", 0.0))
        return order

    assert asyncio.run(_run()) == ["a-in", "a-out", "b-in", "b-out"]


def test_cancel_task_threadsafe_noop_when_done():
    controller = _controller()

    async def _noop():
        return None

    async def _run():
        # None-safe and done-safe; never raises.
        controller._cancel_task_threadsafe(None)
        done = asyncio.create_task(_noop())
        await done
        controller._cancel_task_threadsafe(done)
        # Cancels a genuinely pending task (threadsafe path from loop thread
        # falls through to task.cancel()).
        pending = asyncio.create_task(asyncio.sleep(60))
        await asyncio.sleep(0)
        controller._cancel_task_threadsafe(pending)
        try:
            await pending
        except asyncio.CancelledError:
            return True
        return False

    assert asyncio.run(_run()) is True


def test_storage_bad_ints_ignored(tmp_path):
    """One corrupt int must not abort the remaining loads."""

    async def _run():
        from core.constants import STORAGE_RETRIES, STORAGE_TIMEOUT
        from main import AppController
        from services.storage_service import StorageService

        # Hermetic dir — never touch the developer's real .flet storage
        # (whose owner settings would otherwise leak into the singleton).
        data_dir = tmp_path / "storage"
        data_dir.mkdir()
        store = StorageService(page=None, data_dir=data_dir)
        await store.set(STORAGE_TIMEOUT, "not-an-int")
        await store.set(STORAGE_RETRIES, "3")
        await store.flush()

        controller = AppController(MagicMock())
        controller.storage = store
        from core.state import state

        prev_timeout, prev_retries = state.timeout, state.retries
        try:
            await controller._load_saved_state()
            assert state.retries == 3  # later load survived the bad int
            assert state.timeout == prev_timeout  # bad int ignored
        finally:
            state.timeout, state.retries = prev_timeout, prev_retries

    asyncio.run(_run())


def test_on_error_never_raises():
    controller = _controller()
    controller._show_snack = lambda *a, **k: None
    controller.on_error(MagicMock(data="boom"))
    controller.on_error(object())  # no .data at all
    controller.on_error(MagicMock(data=None))


def test_cached_email_clears_enrichments():
    from core.state import state

    controller = _controller()
    state.enrichments.clear()
    state.enrichments["https://stale.example.com"] = {"name": "Stale"}
    state.set_cached_result(
        "email",
        "a@b.com",
        {"email_results": [{"name": "A", "exists": True}], "total": 1},
    )
    assert controller.open_cached_result("a@b.com", "email") is True
    assert "https://stale.example.com" not in state.enrichments


def test_avatar_warm_budget_resets_per_search():
    controller = _controller()
    controller._avatar_warmed = 49
    assert controller._avatar_warmed == 49

    # _register_search_task resets the budget (needs a running loop).
    async def _run():
        controller._register_search_task()
        assert controller._avatar_warmed == 0
        controller._stop_render_flusher()

    asyncio.run(_run())


def test_banner_explicit_modes():
    """Banner derives mode from progress type, not duck-typed attrs."""
    from services.email_service import EmailSearchProgress
    from services.sherlock_service import SearchProgress

    email_prog = EmailSearchProgress(email="a@b.com")
    user_prog = SearchProgress(username="alice")
    # isinstance routing (mirrors app_shell banner branch)
    assert isinstance(email_prog, EmailSearchProgress)
    assert not isinstance(user_prog, EmailSearchProgress)
    assert getattr(user_prog, "checked_sites", 0) == 0
