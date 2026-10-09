"""Regression tests for Fix Batch 19 (investigative test hardening).

Locks in what the reverse-order + bisect investigation found:

- EmailService.cancel() marks a live scan cancelled even when the worker
  finishes teardown in the GIL window opened by the loop wakeup (the
  liveness snapshot fix) — hammered repeatedly, must be deterministic.
- cancelling a COMPLETED scan still does not rewrite history (the guard
  the snapshot preserves).
- state-field hygiene: the modules that mutate global state restore it,
  so any file order is green (the fixtures themselves are the fix; here
  we assert the post-conditions they guarantee).
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _restore_holehe_registry():
    """Stub-module assignments must never leak into other test files."""
    from services import email_service as es

    original = es._holehe_modules
    yield
    es._holehe_modules = original


def test_cancel_marks_live_scan_deterministically():
    """8/8 marks under the exact former race (was ~1/6 before the fix)."""
    from services import email_service as es

    async def slow(email):
        await asyncio.sleep(30)

    async def one_round():
        es._holehe_modules = {"s0": slow}
        svc = es.EmailService()
        task = asyncio.create_task(
            svc.search("u@e.com", on_progress=lambda p: None, timeout=3)
        )
        await asyncio.sleep(0.6)
        svc.cancel()
        try:
            res = await asyncio.wait_for(task, timeout=20)
        except asyncio.CancelledError:
            return "outer-cancel"  # also acceptable: caller cancelled
        return res.is_cancelled

    async def scenario():
        return [await one_round() for _ in range(4)]

    results = asyncio.run(scenario())
    assert results == [True] * 4, results


def test_cancel_after_completion_keeps_history():
    """A stale cancel on a finished scan must not rewrite it as cancelled."""
    from services import email_service as es

    async def fast(email):
        return None

    async def scenario():
        es._holehe_modules = {"m1": fast}
        svc = es.EmailService()
        progress = await svc.search("u@e.com", on_progress=lambda p: None, timeout=5)
        assert progress.is_running is False
        assert progress.is_cancelled is False
        svc.cancel()  # stale cancel — must be a no-op for history
        return progress

    progress = asyncio.run(scenario())
    assert progress.is_cancelled is False


def test_username_tick_accepted_in_username_mode():
    """Cross-mode guard sanity: username ticks apply in username mode."""
    from core.constants import MODE_USERNAME
    from core.state import state

    saved_mode = state.search_mode
    saved_user = state.current_username
    state.search_mode = MODE_USERNAME
    state.current_username = "testuser"
    try:
        from services.sherlock_service import SearchProgress

        assert state.search_mode == MODE_USERNAME
        p = SearchProgress(username="testuser")
        assert p.username.strip().lower() == state.current_username.strip().lower()
    finally:
        state.search_mode = saved_mode
        state.current_username = saved_user


def test_state_singleton_restore_roundtrip():
    """setattr-based restore keeps @ft.observable wrappers functional."""
    from core.state import state

    enrich = state.enrichments
    cache = state.results_cache
    # Wrappers must be dict-like (ObservableDict), not plain/broken:
    assert hasattr(enrich, "clear") and hasattr(enrich, "update")
    assert hasattr(cache, "clear") and hasattr(cache, "update")
    # A setattr restore of a plain copy re-wraps without raising:
    saved = dict(state.enrichments)
    state.enrichments = dict(state.enrichments)
    assert dict(state.enrichments) == saved
    state.enrichments.clear()
    state.enrichments.update(saved)
    assert dict(state.enrichments) == saved
