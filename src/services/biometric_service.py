"""Biometric app-lock via flet-local-auth (P1-4).

Optional History-tab gate. Every outcome is honest and visible: success,
user cancellation, unsupported device, and import failure are all logged;
the caller surfaces a snackbar either way (owner rule — no swallowing).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_AUTH_AVAILABLE = False
try:
    import flet_local_auth as _fla

    _AUTH_AVAILABLE = True
except ImportError as exc:  # pragma: no cover — dep is pinned in pyproject
    _fla = None
    logger.warning("flet-local-auth not installed: %s", exc)


async def authenticate(reason: str = "Unlock Sherlock") -> bool:
    """Run the platform biometric prompt. True only on verified success."""
    if not _AUTH_AVAILABLE:
        logger.warning("Biometric auth unavailable (flet-local-auth missing)")
        return False
    try:
        from flet import context

        page = context.page
        if page is None:
            logger.warning("Biometric auth requested with no active page")
            return False
        svc = _fla.LocalAuthentication()
        try:
            supported = True
            if hasattr(svc, "is_device_supported"):
                supported = await svc.is_device_supported()
            if not supported:
                logger.info("Biometric auth: device unsupported")
                return False
            ok = bool(await svc.authenticate(reason))
            if ok:
                logger.info("Biometric auth succeeded")
            else:
                logger.info("Biometric auth declined or cancelled by user")
            return ok
        except _fla.LocalAuthException as exc:
            logger.warning("Biometric auth error: %s", exc)
            return False
    except RuntimeError as exc:
        # Outside a live flet app (unit-test harness) — same condition the
        # context.page guards use elsewhere.
        logger.info("Biometric auth skipped (no page context): %s", exc)
        return False
    except Exception as exc:
        logger.warning("Biometric auth unexpected failure: %s", exc)
        return False
