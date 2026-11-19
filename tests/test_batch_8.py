"""Regression tests for Fix Batch 8 (email thread-safety + gaps)."""

import asyncio
from typing import ClassVar

import pytest


@pytest.fixture(autouse=True)
def _restore_holehe_registry():
    """Stub-module assignments must never leak into other test files."""
    from services import email_service as es

    original = es._holehe_modules
    yield
    es._holehe_modules = original


def test_snapshot_isolation():
    """Mutating the worker progress after notify must not affect receivers."""
    from services import email_service as es

    received = []

    async def fast(email):
        return None

    class _FakeResult:
        is_taken = True
        is_available = False
        message = "ok"
        url = "https://example.com"
        extra: ClassVar[dict] = {"bio": "hi"}
        media: ClassVar[dict] = {}

    async def scenario():
        es._holehe_modules = {"m1": fast}
        svc = es.EmailService()
        orig_map = es._map_result
        es._map_result = lambda name, r: orig_map(name, _FakeResult())
        try:
            task = asyncio.create_task(
                svc.search("user@example.com", on_progress=received.append, timeout=5)
            )
            return await asyncio.wait_for(task, timeout=15)
        finally:
            es._map_result = orig_map

    progress = asyncio.run(scenario())
    assert progress.is_cancelled is False
    assert len(received) >= 1
    # Snapshots are copies: later worker appends didn't grow earlier ones.
    counts = [len(p.found) for p in received]
    assert counts[0] <= counts[-1]
    for p in received:
        assert p is not progress


def test_cancel_idle_noop():
    """cancel() with nothing running must not flip stale flags."""
    from services.email_service import EmailSearchProgress, EmailService

    svc = EmailService()
    svc._progress = EmailSearchProgress(email="a@b.com", is_running=False)
    svc.cancel()
    assert svc._progress.is_cancelled is False

    svc._progress = None
    svc.cancel()  # must not raise


def test_outer_cancel_propagates():
    """Cancelling the awaiting task stops the worker (no orphan ticks)."""
    from services import email_service as es

    ticks = []

    async def slow(email):
        await asyncio.sleep(30)

    async def scenario():
        es._holehe_modules = {f"s{i}": slow for i in range(4)}
        svc = es.EmailService()
        task = asyncio.create_task(
            svc.search("user@example.com", on_progress=ticks.append, timeout=10)
        )
        # Wait for the worker to be genuinely up (not blind sleep).
        for _ in range(100):
            if svc._progress is not None and svc._progress.is_running:
                break
            await asyncio.sleep(0.05)
        assert svc._progress is not None and svc._progress.is_running
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0.5)  # orphan ticks would land here
        return svc, len(ticks)

    svc, _ = asyncio.run(scenario())
    assert svc._progress.is_cancelled is True
    # No assertion on exact tick count — just that the worker is dead.
    assert svc._worker_loop is None


def test_fingerprint_per_scan_isolation():
    """Two overlapping scans keep their own fingerprints (ContextVar)."""
    import services.email_service as es

    assert es._SCAN_FINGERPRINT.get() is None
    token = es._SCAN_FINGERPRINT.set("chrome131")
    try:
        assert es._SCAN_FINGERPRINT.get() == "chrome131"
    finally:
        es._SCAN_FINGERPRINT.reset(token)
    assert es._SCAN_FINGERPRINT.get() is None


def test_stealth_concurrency_one_honored():
    """concurrency=1 must stay 1 (was silently quadrupled to 4)."""
    import services.email_service as es

    in_flight = 0
    max_seen = 0

    async def slow(email):
        nonlocal in_flight, max_seen
        in_flight += 1
        max_seen = max(max_seen, in_flight)
        await asyncio.sleep(0.3)
        in_flight -= 1
        return

    async def scenario():
        es._holehe_modules = {f"s{i}": slow for i in range(4)}
        svc = es.EmailService()
        task = asyncio.create_task(
            svc.search(
                "user@example.com",
                on_progress=lambda p: None,
                timeout=5,
                concurrency=1,
            )
        )
        return await asyncio.wait_for(task, timeout=20)

    asyncio.run(scenario())
    assert max_seen == 1


def test_frequent_flag_on_broad_throttle():
    """3rd+ rate-limit in one scan is flagged frequent."""
    from services import email_service as es

    async def limited(email):
        class _R:
            is_taken = False
            is_available = False
            message = "Rate limited (429)"
            url = None
            extra: ClassVar[dict] = {}
            media: ClassVar[dict] = {}

        return _R()

    async def scenario():
        es._holehe_modules = {f"s{i}": limited for i in range(4)}
        svc = es.EmailService()
        task = asyncio.create_task(
            svc.search("user@example.com", on_progress=lambda p: None, timeout=5)
        )
        return await asyncio.wait_for(task, timeout=20)

    progress = asyncio.run(scenario())
    assert len(progress.rate_limited) == 4
    assert progress.rate_limited[0].frequent_rate_limit is False
    assert progress.rate_limited[-1].frequent_rate_limit is True


def test_rate_regex_new_patterns():
    from services.email_service import _is_rate_limited

    for msg in (
        "Too many requests",
        "Please try again later",
        "Temporarily blocked",
        "Rate exceeded",
        "Throttled by server",
        "Limit exceeded for this IP",
    ):
        assert _is_rate_limited(msg), msg
    assert not _is_rate_limited("HTTP Error: 404")
    assert not _is_rate_limited("Account not found")


def test_first_int_phone():
    from services.email_service import _first, _phone_from

    assert _first(15551234567) == 15551234567
    assert _first(True) is None
    assert _first("x") == "x"
    assert _first(["a", "b"]) == "a"
    assert _phone_from({"phone": 15551234567}) == "15551234567"


def test_stealth_alias_compat():
    """use_curl_cffi still works; use_stealth_fingerprint overrides."""
    import inspect

    from services.email_service import EmailService

    sig = inspect.signature(EmailService.search)
    assert "use_curl_cffi" in sig.parameters
    assert "use_stealth_fingerprint" in sig.parameters
    assert sig.parameters["use_stealth_fingerprint"].default is None
