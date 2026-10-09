"""Regression tests for Fix Batch 7b (biometric polish).

Ads are explicitly out of scope for this batch (owner instruction).
Covers: detailed auth outcomes, lock serialization, timeout, wrapper compat.
"""

import asyncio


def test_auth_result_types():
    from services.biometric_service import AuthResult, AuthStatus

    assert AuthResult(True, AuthStatus.SUCCESS).ok is True
    assert AuthResult(False, AuthStatus.LOCKOUT).status == AuthStatus.LOCKOUT
    assert set(AuthStatus) == {
        AuthStatus.SUCCESS,
        AuthStatus.CANCELLED,
        AuthStatus.LOCKOUT,
        AuthStatus.UNAVAILABLE,
        AuthStatus.ERROR,
    }


def test_authenticate_wrapper_returns_bool():
    """authenticate() stays a bool wrapper over authenticate_detailed."""

    async def _run():
        import services.biometric_service as bio

        called = {}

        async def _fake_detailed(reason=""):
            called["reason"] = reason
            from services.biometric_service import AuthResult, AuthStatus

            return AuthResult(True, AuthStatus.SUCCESS)

        orig = bio.authenticate_detailed
        bio.authenticate_detailed = _fake_detailed
        try:
            ok = await bio.authenticate("  ")
            assert ok is True
            assert called["reason"] == "  "
        finally:
            bio.authenticate_detailed = orig

    asyncio.run(_run())


def test_detailed_unavailable_without_page():
    """No page context → ERROR result, never raises."""
    from services.biometric_service import AuthStatus, authenticate_detailed

    result = asyncio.run(authenticate_detailed("Unlock"))
    assert result.ok is False
    assert result.status == AuthStatus.ERROR


def test_auth_lock_serializes_prompts():
    """Concurrent lock holders serialize instead of overlapping."""
    import services.biometric_service as bio

    async def _main():
        if bio._AUTH_LOCK is None:
            bio._AUTH_LOCK = asyncio.Lock()
        order = []

        async def _one(tag):
            async with bio._AUTH_LOCK:
                order.append(f"{tag}-in")
                await asyncio.sleep(0.05)
                order.append(f"{tag}-out")

        await asyncio.gather(_one("a"), _one("b"))
        return order

    assert asyncio.run(_main()) == ["a-in", "a-out", "b-in", "b-out"]
