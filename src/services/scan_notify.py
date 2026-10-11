"""Scan notifications — OS-level progress for long scans.

Wraps flet-notifications (the owner's own package, cross-platform local
notifications over flutter_local_notifications). A 5,200-site scan takes
minutes and the user spends most of that outside the app, so progress
belongs in the notification shade, not only on a screen they've left.

Design notes
------------
- **No build-pipeline change.** Only `show()` + progress updates + actions
  are used. The `<receiver>` manifest entries the package's patcher adds
  are needed for scheduling and for actions that run with the app dead
  (`foreground=False`); every action here is `foreground=True`, which is
  delivered through `onDidReceiveNotificationResponse`. Verified against
  the package's Dart side rather than inferred from its README.
- **One notification id per scan, re-shown.** `show()` with the same id
  updates in place, which is how a determinate progress bar advances.
- **Hold the reference.** Flet drops unreferenced services after every
  event (same trap as ConsentManager) — the service is appended to
  page.services for app lifetime.
- **Cancelled scans clear the notification** so a dead scan never leaves
  a live-looking bar in the shade.
- **Every failure is logged, never raised** into the scan path: a
  notification backend that refuses to start must not break OSINT.

`are_enabled()` is the single gate the UI consults — false when the
package is missing, the platform has no shade, or the user turned it off.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_HAS_NOTIFICATIONS = True
try:
    from flet_notifications import LocalNotifications, NotificationAction
except ImportError:  # pragma: no cover — dep is pinned in pyproject
    _HAS_NOTIFICATIONS = False

# Stable notification ids — re-showing the same id updates in place.
NOTIF_ID_SCAN = 3401
NOTIF_ID_DONE = 3402

_ACTION_VIEW = "view"
_ACTION_CANCEL = "cancel"


class ScanNotifier:
    """OS-notification mirror of scan progress for one app lifetime."""

    def __init__(self, page) -> None:
        self.page = page
        self._service: LocalNotifications | None = None
        self._started = False
        self._active_target = ""
        self._active_is_email = False
        self._on_cancel = None
        self._on_view = None

    # ── lifecycle ──────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return _HAS_NOTIFICATIONS

    async def start(self) -> None:
        """Construct once (inside page context) and keep it alive."""
        if self._started or not _HAS_NOTIFICATIONS:
            return
        self._started = True
        try:
            from core.state import state

            if not getattr(state, "scan_notifications", False):
                logger.info("ScanNotifier: disabled by setting")
                return
            svc = LocalNotifications()
            if svc not in self.page.services:
                self.page.services.append(svc)

            async def _on_tap(e):
                # A tap opens the results view — the same action the View
                # button fires, so both paths share one code path.
                self._fire_view()

            svc.on_tap = _on_tap

            async def _on_action(e):
                if e.action_id == _ACTION_CANCEL and self._on_cancel:
                    self._on_cancel()
                else:
                    self._fire_view()

            svc.on_action = _on_action
            self._service = svc
            logger.info("ScanNotifier: ready")
        except Exception as exc:
            # A dead notification backend must never break a scan.
            logger.warning("ScanNotifier: init failed (%s)", exc)

    async def request_permission(self) -> bool:
        """Ask for POST_NOTIFICATIONS. Best-effort; never raises."""
        if self._service is None:
            return False
        try:
            return bool(await self._service.request_permissions())
        except Exception as exc:
            logger.warning("ScanNotifier: permission request failed: %s", exc)
            return False

    # ── scan mirror ───────────────────────────────────────────────────

    def set_handlers(self, *, on_cancel=None, on_view=None) -> None:
        self._on_cancel = on_cancel
        self._on_view = on_view

    def scan_started(self, target: str, *, is_email: bool = False) -> None:
        self._active_target = target
        self._active_is_email = is_email
        if self._service is None:
            return
        kind = "email" if is_email else "username"
        try:
            self.page.run_task(
                self._service.show,
                NOTIF_ID_SCAN,
                f"Scanning {kind}",
                f"{target} — preparing…",
                show_progress=True,
                indeterminate=True,
                actions=[
                    NotificationAction(id=_ACTION_CANCEL, title="Cancel"),
                ],
            )
        except Exception as exc:
            logger.warning("ScanNotifier: start post failed: %s", exc)

    def progress(self, checked: int, total: int) -> None:
        """Update the live progress notification (rate-limited by caller)."""
        if self._service is None:
            return
        label = self._active_target or "target"
        kind = "email" if self._active_is_email else "username"
        pct = int(checked / max(total, 1) * 100)
        try:
            self.page.run_task(
                self._service.show,
                NOTIF_ID_SCAN,
                f"Scanning {kind} — {pct}%",
                f"{label} · {checked}/{total}",
                show_progress=True,
                max_progress=total,
                progress=checked,
                actions=[
                    NotificationAction(id=_ACTION_CANCEL, title="Cancel"),
                ],
            )
        except Exception as exc:
            logger.warning("ScanNotifier: progress post failed: %s", exc)

    def scan_finished(self, found: int, total: int) -> None:
        """Swap the progress bar for a completion notification."""
        if self._service is None:
            return
        label = self._active_target or "target"
        noun = "results" if self._active_is_email else "accounts"
        suffix = f" ({total} checked)" if total else ""
        try:
            self.page.run_task(
                self._service.show,
                NOTIF_ID_DONE,
                f"Scan finished — {found} {noun}",
                f"{label}{suffix}",
                actions=[
                    NotificationAction(id=_ACTION_VIEW, title="View"),
                ],
            )
            self._dismiss_progress()
        except Exception as exc:
            logger.warning("ScanNotifier: finish post failed: %s", exc)

    def scan_cancelled(self) -> None:
        self._dismiss_progress()

    def _dismiss_progress(self) -> None:
        if self._service is None:
            return
        try:
            self.page.run_task(self._service.cancel, NOTIF_ID_SCAN)
        except Exception as exc:
            logger.warning("ScanNotifier: dismiss failed: %s", exc)

    def _fire_view(self) -> None:
        if self._on_view:
            try:
                self._on_view()
            except Exception as exc:
                logger.warning("ScanNotifier: view action failed: %s", exc)

    def shutdown(self) -> None:
        """Clear notifications on teardown."""
        if self._service is None:
            return
        try:
            self._service.cancel_all()
        except Exception:
            pass
