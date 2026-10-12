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
- **Hold the reference.** `Service.__post_init__` self-registers through
  `page._services.register_service()` (`.venv/.../flet/controls/services/
  service.py`); `ServiceRegistry.unregister_services` drops anything whose
  refcount falls to <=3, so the service is also appended to `page.services`
  for app lifetime.
- **Cancelled scans clear the notification** so a dead scan never leaves
  a live-looking bar in the shade.
- **Every failure is logged, never raised** into the scan path: a
  notification backend that refuses to start must not break OSINT.

`is_usable()` is the single gate the UI consults — false when the package
is missing, the service never came up, or the OS has notifications off for
this app. `ensure_ready()` is the only entry point callers use: it is a
coroutine, so the caller MUST await it, which is what makes the first
`show()` of a session possible (see the race note below).
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


class _FakeBackend:
    """Test double for the notification service.

    `LocalNotifications` is a dataclass control whose real methods need a
    mounted page, so a MagicMock of it is not usable — this records the calls
    the same way the real one does.
    """

    def __init__(self, *, enabled: bool, granted: bool) -> None:
        self.enabled = enabled
        self.granted = granted
        self.shown: list[dict] = []
        self.cancelled: list[int] = []
        self.cancel_all_calls = 0
        self.settings_calls = 0
        self.on_tap = None
        self.on_action = None

    async def are_notifications_enabled(self) -> bool:
        return self.enabled

    async def request_permissions(self) -> bool:
        return self.granted

    async def show(self, *args, **kwargs) -> None:
        self.shown.append({"args": args, "kwargs": kwargs})

    async def cancel(self, id: int) -> None:
        self.cancelled.append(id)

    async def cancel_all(self) -> None:
        self.cancel_all_calls += 1

    async def open_app_notification_settings(self) -> None:
        self.settings_calls += 1


class ScanNotifier:
    """OS-notification mirror of scan progress for one app lifetime."""

    def __init__(self, page) -> None:
        self.page = page
        self._service: LocalNotifications | None = None
        self._started = False
        self._ready = False
        self._active_target = ""
        self._active_is_email = False
        self._on_cancel = None
        self._on_view = None
        # Set by the controller so a denied permission can route the user
        # to the OS page without this class importing app-level UI.
        self._on_permission_denied = None
        # One warning per session; the OS dialog only appears once or twice
        # and then hard-denies, so nagging every scan would be noise.
        self._warned = False

    # ── lifecycle ──────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return _HAS_NOTIFICATIONS

    def is_usable(self) -> bool:
        """True when notifications can actually be posted right now.

        This is a *state* probe, not a coroutine, so it never touches the
        service and can be consulted from render code.
        """
        return self._service is not None and self._ready

    async def ensure_ready(self) -> bool:
        """Await this before the first `show()` of a session.

        Constructing the service and asking for POST_NOTIFICATIONS both
        need the page session to own the service first; both are coroutines
        here so the caller's `await` is what sequences them ahead of the
        first post. Firing them through `page.run_task` does NOT work —
        `run_task` schedules onto the loop and returns a Future at once, so
        a `show()` on the next synchronous line sees `_service is None` and
        the first notification of the session is silently dropped.

        Idempotent: safe to call before every scan. Cheap after the first
        call (one `are_notifications_enabled` probe).
        """
        if not _HAS_NOTIFICATIONS:
            return False
        from core.state import state

        if not getattr(state, "scan_notifications", False):
            return False
        if not self._started:
            await self._construct()
        if self._service is None:
            return False
        return await self._check_permission()

    async def _construct(self) -> None:
        """Build the service once and wire its handlers.

        An already-injected service wins — that is how tests drive the
        permission paths without a mounted page.
        """
        if self._started:
            return
        self._started = True
        if self._service is not None:
            return
        try:
            svc = LocalNotifications()

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
            if svc not in self.page.services:
                self.page.services.append(svc)
            self._service = svc
            logger.info("ScanNotifier: ready")
        except Exception as exc:
            # A dead notification backend must never break a scan.
            logger.warning("ScanNotifier: init failed (%s)", exc)
            self._service = None

    async def _check_permission(self) -> bool:
        """Make sure the OS will actually deliver what we post.

        Re-checked before every scan rather than latched at startup: a user
        who turns notifications on from Android settings later gets them on
        the next scan with no restart.
        """
        if self._service is None:
            return False
        try:
            if await self._service.are_notifications_enabled():
                self._ready = True
                return True
            if await self._service.request_permissions():
                self._ready = True
                return True
        except Exception as exc:
            logger.warning("ScanNotifier: permission check failed: %s", exc)
            self._ready = False
            return False
        # Declined. Android only shows the system dialog once or twice and
        # then hard-denies it, so re-requesting will never succeed — the
        # only path back is the OS settings page.
        self._ready = False
        self._warn_denied()
        return False

    def _warn_denied(self) -> None:
        """Surface the decline once per session, with a way to fix it."""
        if self._warned:
            return
        self._warned = True
        cb = self._on_permission_denied
        if cb is None:
            return
        try:
            cb()
        except Exception as exc:
            logger.warning("ScanNotifier: denied handler failed: %s", exc)

    async def open_settings(self) -> None:
        """Route the user to the OS notification settings for this app."""
        if self._service is None:
            return
        try:
            await self._service.open_app_notification_settings()
        except Exception as exc:
            logger.warning("ScanNotifier: open settings failed: %s", exc)

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

    def set_handlers(
        self, *, on_cancel=None, on_view=None, on_permission_denied=None
    ) -> None:
        self._on_cancel = on_cancel
        self._on_view = on_view
        self._on_permission_denied = on_permission_denied

    def scan_started(self, target: str, *, is_email: bool = False) -> None:
        self._active_target = target
        self._active_is_email = is_email
        if not self.is_usable():
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
        if not self.is_usable():
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
        if not self.is_usable():
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
        """Clear notifications on teardown.

        `cancel_all` is a coroutine, so it has to go through `run_task`
        like every other dispatch here; calling it directly returns an
        un-awaited coroutine and the shade keeps a live-looking bar.
        """
        if self._service is None:
            return
        try:
            self.page.run_task(self._service.cancel_all)
        except Exception as exc:
            logger.warning("ScanNotifier: shutdown cancel failed: %s", exc)
