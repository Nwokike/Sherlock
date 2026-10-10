"""Biometric app-lock via flet-local-auth (P1-4).

Optional History-tab gate. Every outcome is honest and visible: success,
user cancellation, unsupported device, and import failure are all logged;
the caller surfaces a snackbar either way (owner rule — no swallowing).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

_AUTH_AVAILABLE = False
try:
    import flet_local_auth as _fla

    _AUTH_AVAILABLE = True
except ImportError as exc:  # pragma: no cover — dep is pinned in pyproject
    _fla = None
    logger.warning("flet-local-auth not installed: %s", exc)

# Serializes concurrent prompts: a second tap while the OS dialog is open
# would raise AUTH_IN_PROGRESS and surface a spurious failure. Lazily
# created inside the running loop (asyncio.Lock binds on first use).
_AUTH_LOCK: asyncio.Lock | None = None

_AUTH_TIMEOUT_SEC = 60


class AuthStatus(Enum):
    SUCCESS = "success"
    CANCELLED = "cancelled"
    LOCKOUT = "lockout"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass
class AuthResult:
    ok: bool
    status: AuthStatus
    message: str = ""


_LOCKOUT_CODES = frozenset(
    {
        "TEMPORARY_LOCKOUT",
        "BIOMETRIC_LOCKOUT",
    }
)

_CANCEL_CODES = frozenset(
    {
        "USER_CANCELED",
        "SYSTEM_CANCELED",
        "USER_REQUESTED_FALLBACK",
        "AUTH_IN_PROGRESS",
    }
)


async def capability_label() -> str:
    """Human-readable auth capability for the Settings row subtitle."""
    if not _AUTH_AVAILABLE:
        return "unavailable"
    try:
        from flet import context

        if context.page is None:
            return "unknown"
        svc = _fla.LocalAuthentication()
        if not await svc.can_check_biometrics():
            return "device credentials"
        types = await svc.get_available_biometrics() or []
        names = [getattr(t, "value", str(t)) for t in types]
        return "/".join(names) if names else "device credentials"
    except Exception as exc:
        logger.debug("capability probe failed: %s", exc)
        return "unknown"


async def stop_prompt() -> None:
    """Cancel an in-flight OS prompt (call on tab-leave/navigation)."""
    if not _AUTH_AVAILABLE:
        return
    try:
        await _fla.LocalAuthentication().stop_authentication()
    except Exception as exc:
        logger.debug("stop_authentication failed: %s", exc)


async def authenticate_detailed(
    reason: str = "Unlock Sherlock",
    *,
    biometric_only: bool = False,
    sensitive: bool = True,
) -> AuthResult:
    """Run the platform prompt with a typed outcome.

    Owner rule: the lock defaults ON — so devices that cannot enforce it
    (no hardware / nothing enrolled / no lock-screen credentials) are
    granted access with an explicit log instead of being stranded
    outside History. Cancellations and failed attempts stay locked.

    Note: device PIN/pattern fallback is allowed (``biometric_only=False``)
    — good UX for users without enrolled biometrics, not a biometric-only
    guarantee.
    """
    reason = reason.strip() or "Unlock Sherlock"
    if not _AUTH_AVAILABLE:
        logger.warning("Biometric auth unavailable (flet-local-auth missing)")
        return AuthResult(False, AuthStatus.ERROR, "Biometric auth unavailable")
    global _AUTH_LOCK
    if _AUTH_LOCK is None:
        _AUTH_LOCK = asyncio.Lock()
    try:
        from flet import context

        page = context.page
        if page is None:
            logger.warning("Biometric auth requested with no active page")
            return AuthResult(False, AuthStatus.ERROR, "No active page")
        async with _AUTH_LOCK:
            svc = _fla.LocalAuthentication()
            try:
                supported = True
                if hasattr(svc, "is_device_supported"):
                    supported = await svc.is_device_supported()
                if not supported:
                    logger.info(
                        "Biometric auth: device unsupported — lock not enforceable, "
                        "access granted"
                    )
                    return AuthResult(
                        True, AuthStatus.UNAVAILABLE, "Device unsupported"
                    )
                try:
                    from core.state import state as _app_state

                    ok = bool(
                        await asyncio.wait_for(
                            svc.authenticate(
                                reason,
                                biometric_only=biometric_only
                                or bool(getattr(_app_state, "biometric_strict", False)),
                                sensitive_transaction=sensitive,
                                persist_across_backgrounding=True,
                                android_messages=_fla.AndroidAuthMessages(
                                    sign_in_title="Sherlock",
                                    sign_in_hint="Unlock history",
                                    cancel_button="Cancel",
                                ),
                                ios_messages=_fla.IOSAuthMessages(
                                    cancel_button="Cancel",
                                    localized_fallback_title="Enter passcode",
                                ),
                                # local_auth 3.x exposes no customizable
                                # Windows strings — the class takes no args.
                                windows_messages=_fla.WindowsAuthMessages(),
                            ),
                            60,
                        )
                    )
                except TimeoutError:
                    logger.warning("Biometric auth timed out after 60s")
                    return AuthResult(
                        False, AuthStatus.ERROR, "Authentication timed out"
                    )
                if ok:
                    logger.info("Biometric auth succeeded")
                    return AuthResult(True, AuthStatus.SUCCESS)
                logger.info("Biometric auth declined or cancelled by user")
                return AuthResult(False, AuthStatus.CANCELLED, "Cancelled")
            except _fla.LocalAuthException as exc:
                code = getattr(exc, "code", None)
                code_name = getattr(code, "name", str(code))
                if _is_unenforceable(code_name):
                    logger.info(
                        "Biometric lock not enforceable on this device (%s) — "
                        "access granted",
                        code_name,
                    )
                    return AuthResult(True, AuthStatus.UNAVAILABLE, code_name)
                if code_name in _LOCKOUT_CODES:
                    logger.warning("Biometric auth locked out: %s", code_name)
                    return AuthResult(
                        False,
                        AuthStatus.LOCKOUT,
                        "Too many attempts — try again later or use device PIN",
                    )
                if code_name in _CANCEL_CODES:
                    logger.info("Biometric auth cancelled: %s", code_name)
                    return AuthResult(False, AuthStatus.CANCELLED, code_name)
                logger.warning("Biometric auth error: %s", exc)
                return AuthResult(False, AuthStatus.ERROR, code_name)
    except RuntimeError as exc:
        # Outside a live flet app (unit-test harness) — same condition the
        # context.page guards use elsewhere.
        logger.info("Biometric auth skipped (no page context): %s", exc)
        return AuthResult(False, AuthStatus.ERROR, "No page context")
    except Exception as exc:
        logger.warning("Biometric auth unexpected failure: %s", exc)
        return AuthResult(False, AuthStatus.ERROR, "Unexpected failure")


async def authenticate(reason: str = "Unlock Sherlock") -> bool:
    """Run the platform biometric prompt. True only on verified success.

    Thin bool wrapper over :func:`authenticate_detailed` (kept for existing
    callers). See its docstring for the lock-defaults contract.
    """
    return (await authenticate_detailed(reason)).ok


def _is_unenforceable(code_name: str) -> bool:
    """Codes meaning the device simply cannot present a biometric prompt."""
    return code_name in (
        "NO_BIOMETRIC_HARDWARE",
        "NO_BIOMETRICS_ENROLLED",
        "NO_CREDENTIALS_SET",
    )
