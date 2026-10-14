"""Scan notifications — the OS is the progress UI for a running scan.

A 5,200-site scan takes minutes and the user spends most of that outside
the app, so progress lives in the notification shade rather than on a
screen they have left. There is no in-app progress banner and no settings
toggle: a scan is a foreground activity the system must be able to show,
not a preference to opt into.

Design notes
------------
- **Two channels, created once.** `scan_progress` is low-importance and
  silent so a running scan never dings, `scan_result` is default importance
  so a finished scan gets attention. Sound and vibration are immutable
  after creation (`.venv/flet_notifications/channels.py:13-16`), so they
  are set here and never revised.
- **A determinate bar that survives the app closing.** The scan runs in a
  foreground service (`start_foreground_service`) whose notification IS the
  progress bar; `stop_foreground_service()` clears it at the end. This is
  what keeps the engine alive when the user swipes the app away — the owner's
  "it keeps running in the background".
- **One notification id per scan, re-shown.** `show()` with the same id
  updates in place, which is how the bar advances.
- **Actions, not one button.** Cancel (with inline reply so the scan stops
  without opening the app) while running; View (tap-to-results) and Copy
  report on completion. Inline reply needs `NotificationActionInput`
  (`.venv/flet_notifications/actions.py:9-28`), and `foreground=True` so
  the action is delivered to the live app rather than needing the
  manifest receivers the patcher adds for `foreground=False`.
- **Permission is asked at the first scan, never on cold start.** Asking
  before the user has a reason is the classic notification-permission
  mistake, and on Android the dialog appears only once or twice before the
  OS hard-denies it permanently — after which `request_permissions()` can
  never succeed and the only route back is the OS settings page.
- **Hold the reference.** `Service.__post_init__` self-registers through
  `page._services.register_service()` (`.venv/flet/controls/services/
  service.py`); `ServiceRegistry.unregister_services` drops anything whose
  refcount falls to <=3, so the service is also appended to `page.services`
  for app lifetime.
- **Every failure is logged, never raised** into the scan path: a broken
  notification backend must not break OSINT.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_HAS_NOTIFICATIONS = True
try:
    from flet_notifications import (
        Importance,
        LocalNotifications,
        NotificationAction,
        NotificationActionInput,
        NotificationChannel,
    )
except ImportError:  # pragma: no cover — dep is pinned in pyproject
    _HAS_NOTIFICATIONS = False

# Stable notification ids — re-showing the same id updates in place.
NOTIF_ID_SCAN = 3401
NOTIF_ID_DONE = 3402

# Channel ids. A channel's sound/vibration are fixed at creation, so the
# running-scan and the finished-scan notifications cannot share one.
CHANNEL_PROGRESS = "scan_progress"
CHANNEL_RESULT = "scan_result"

# Android foreground-service type. `dataSync` covers network I/O for a
# user-initiated job without claiming a more privileged type.
FGS_TYPE = "dataSync"

# `start_type` is a DIFFERENT vocabulary from the service type above: Dart's
# _mapServiceStartType accepts only these three strings
# (.venv/flutter/flet_notifications/lib/src/notifications_service.dart
# :1254-1265) and silently falls back to startSticky for anything else.
# Passing FGS_TYPE here worked only by falling into that default.
FGS_START_TYPE = "startSticky"

# Stable payload on every post: what the notification says about itself when
# tapped. Any scan notification means "show the live results", so one route
# covers progress, completion and a cold-start tap alike.
PAYLOAD_ROUTE = "sherlock://results"

_ACTION_VIEW = "view"
_ACTION_CANCEL = "cancel"
_ACTION_COPY = "copy"


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
        self.service_calls: list[dict] = []
        self.cancelled: list[int] = []
        self.cancel_all_calls = 0
        self.channels: list[dict] = []
        self.settings_calls = 0
        self.on_tap = None
        self.on_action = None

    async def are_notifications_enabled(self) -> bool:
        return self.enabled

    async def request_permissions(self) -> bool:
        return self.granted

    async def create_notification_channel(self, channel) -> None:
        self.channels.append(
            {
                "id": getattr(channel, "id", None),
                "importance": getattr(
                    getattr(channel, "importance", None), "value", None
                ),
            }
        )

    async def show(self, *args, **kwargs) -> None:
        self.shown.append({"args": args, "kwargs": kwargs})

    async def start_foreground_service(self, *args, **kwargs) -> None:
        self.service_calls.append({"op": "start", "args": args, "kwargs": kwargs})

    async def stop_foreground_service(self) -> None:
        self.service_calls.append({"op": "stop"})

    async def cancel(self, id: int) -> None:
        self.cancelled.append(id)

    async def cancel_all(self) -> None:
        self.cancel_all_calls += 1

    async def open_app_notification_settings(self) -> None:
        self.settings_calls += 1


class ScanNotifier:
    """OS-notification progress surface for one app lifetime."""

    def __init__(self, page) -> None:
        self.page = page
        self._service: LocalNotifications | None = None
        self._started = False
        self._ready = False
        self._channels_made = False
        self._active_target = ""
        self._active_is_email = False
        self._on_cancel = None
        self._on_view = None
        self._on_copy = None
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

        Constructing the service, creating the channels and asking for
        POST_NOTIFICATIONS are all coroutines that must complete before the
        first post; firing them through `page.run_task` returns a Future
        immediately, so a `show()` on the next synchronous line would see no
        service and the first notification of the session would be dropped
        silently. The caller's `await` is what sequences them.

        Idempotent: safe to call before every scan. Cheap after the first
        call (one `are_notifications_enabled` probe).
        """
        if not _HAS_NOTIFICATIONS:
            return False
        if not self._started:
            await self._construct()
        if self._service is None:
            return False
        await self._ensure_channels()
        return await self._check_permission()

    async def _construct(self) -> None:
        """Build the service once and wire its handlers.

        An already-injected service wins — that is how tests drive the
        permission paths without a mounted page. `_started` is set only on
        SUCCESS: latching it before the build meant one transient failure
        disabled notifications for the whole session with no retry.
        """
        if self._started:
            return
        if self._service is not None:
            self._started = True
            return
        try:
            svc = LocalNotifications()

            async def _on_tap(e):
                # A tap opens the results view — the same action the View
                # button fires, so both paths share one code path.
                self._fire_view()

            svc.on_tap = _on_tap

            async def _on_action(e):
                action_id = getattr(e, "action_id", "") or ""
                if action_id == _ACTION_CANCEL and self._on_cancel:
                    self._on_cancel()
                elif action_id == _ACTION_COPY and self._on_copy:
                    self._on_copy()
                else:
                    self._fire_view()

            svc.on_action = _on_action

            async def _on_dismissed(e):
                # The user swiped the shade entry away. Nothing to retract
                # (the scan itself is untouched) but local state must not
                # pretend the bar is still showing.
                logger.debug(
                    "ScanNotifier: notification dismissed (id=%s)",
                    getattr(e, "id", "?"),
                )

            svc.on_dismissed = _on_dismissed

            if svc not in self.page.services:
                self.page.services.append(svc)
            self._service = svc
            self._started = True
            logger.info("ScanNotifier: ready")
        except Exception as exc:
            # A dead notification backend must never break a scan.
            logger.warning("ScanNotifier: init failed (%s)", exc)
            self._service = None

    async def _ensure_channels(self) -> None:
        """Create the two channels once per app lifetime.

        Same latch discipline as `_construct`: the flag is set only after
        both creates succeed, so a transient failure is retried instead of
        silently leaving the result channel missing for the session.
        """
        if self._channels_made or self._service is None:
            return
        try:
            # Low + silent: a scan that takes minutes must not ding on every
            # tick, and the bar is visible in the shade regardless.
            await self._service.create_notification_channel(
                NotificationChannel(
                    id=CHANNEL_PROGRESS,
                    name="Scan progress",
                    description="Live progress of a running username or email scan",
                    importance=Importance.LOW,
                    play_sound=False,
                    enable_vibration=False,
                    show_badge=False,
                )
            )
            # Default: a finished scan is the one worth pulling the shade down
            # for, so it keeps sound and badge.
            await self._service.create_notification_channel(
                NotificationChannel(
                    id=CHANNEL_RESULT,
                    name="Scan results",
                    description="The outcome of a finished scan",
                    importance=Importance.DEFAULT,
                    show_badge=True,
                )
            )
            self._channels_made = True
        except Exception as exc:
            logger.warning("ScanNotifier: channel setup failed (%s)", exc)

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
        self,
        *,
        on_cancel=None,
        on_view=None,
        on_copy=None,
        on_permission_denied=None,
    ) -> None:
        self._on_cancel = on_cancel
        self._on_view = on_view
        self._on_copy = on_copy
        self._on_permission_denied = on_permission_denied

    def scan_started(self, target: str, *, is_email: bool = False) -> None:
        """Post the indeterminate start and open the foreground service.

        The service is what keeps the engine alive when the app is closed or
        backgrounded; its notification is the same one the bar advances on,
        so there is exactly one live scan notification.
        """
        self._active_target = target
        self._active_is_email = is_email
        if not self.is_usable():
            return
        kind = "email" if is_email else "username"
        try:
            self.page.run_task(
                self._service.start_foreground_service,
                NOTIF_ID_SCAN,
                f"Scanning {kind}",
                f"{target} — preparing…",
                show_progress=True,
                indeterminate=True,
                channel_id=CHANNEL_PROGRESS,
                start_type=FGS_START_TYPE,
                foreground_service_types=[FGS_TYPE],
                payload=PAYLOAD_ROUTE,
                actions=[
                    NotificationAction(
                        id=_ACTION_CANCEL,
                        title="Cancel",
                        input=NotificationActionInput(
                            label="Reason (optional)",
                        ),
                    ),
                    # A running scan must be able to take the user back to
                    # it. Without this the only actions were Cancel and a
                    # body-tap whose delivery depends on the OS, so a user
                    # could not get from the shade into the live results.
                    NotificationAction(
                        id=_ACTION_VIEW,
                        title="View",
                        # Tapping View must not dismiss the bar it is
                        # navigating to — the default cancel_notification=True
                        # removed the live progress the user just asked for.
                        cancel_notification=False,
                    ),
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
                channel_id=CHANNEL_PROGRESS,
                payload=PAYLOAD_ROUTE,
                actions=[
                    NotificationAction(id=_ACTION_CANCEL, title="Cancel"),
                    # Re-show REPLACES the action list, so View must be here
                    # too or the first tick would strip it off the FGS
                    # notification posted by scan_started().
                    NotificationAction(
                        id=_ACTION_VIEW,
                        title="View",
                        # Tapping View must not dismiss the bar it is
                        # navigating to — the default cancel_notification=True
                        # removed the live progress the user just asked for.
                        cancel_notification=False,
                    ),
                ],
            )
        except Exception as exc:
            logger.warning("ScanNotifier: progress post failed: %s", exc)

    def scan_finished(self, found: int, total: int) -> None:
        """Stop the service, drop the progress bar, then post the result."""
        if not self.is_usable():
            return
        label = self._active_target or "target"
        noun = "results" if self._active_is_email else "accounts"
        suffix = f" ({total} checked)" if total else ""
        try:
            # Teardown first: the service notification and the last progress
            # tick share NOTIF_ID_SCAN, and posting the result before they are
            # gone races them against it.
            self.stop_service()
            self.page.run_task(
                self._service.show,
                NOTIF_ID_DONE,
                f"Scan finished — {found} {noun}",
                f"{label}{suffix}",
                channel_id=CHANNEL_RESULT,
                payload=PAYLOAD_ROUTE,
                actions=[
                    NotificationAction(
                        id=_ACTION_VIEW,
                        title="View",
                        # The scan is over, so dismissing on tap is fine.
                    ),
                    NotificationAction(id=_ACTION_COPY, title="Copy report"),
                ],
            )
        except Exception as exc:
            logger.warning("ScanNotifier: finish post failed: %s", exc)

    def scan_cancelled(self) -> None:
        """A scan ended without a result: stop the service, drop the bar.

        `cancel()` alone only removes the tray entry — the foreground
        service keeps running (Android can even re-post its ongoing
        notification), which is exactly the "something is still stuck"
        symptom after a cancel or a superseded scan.
        """
        self.stop_service()

    def stop_service(self) -> None:
        """Stop the foreground service and drop the progress bar.

        Idempotent, and the ONE call every exit path uses — complete, cancel,
        supersede, error, app close. Two halves are required:

        * `stop_foreground_service()` retracts the service; without it the
          process stays flagged foreground and Android can re-post the bar.
        * `cancel(NOTIF_ID_SCAN)` clears the tray entry; every progress tick
          re-posts with `show()` on that id, so the last one would otherwise
          persist as a normal notification frozen at its percentage — the
          exact "stuck at 99%" symptom claimed fixed.

        Stop comes first so the OS cannot re-post the service's own ongoing
        entry over the tray we just cleared.
        """
        if self._service is None:
            return
        try:
            self.page.run_task(self._service.stop_foreground_service)
            self.page.run_task(self._service.cancel, NOTIF_ID_SCAN)
        except Exception as exc:
            logger.warning("ScanNotifier: stop service failed: %s", exc)

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
        """Teardown on app close: stop the service, then clear the tray.

        Both are coroutines, so both go through `run_task` like every other
        dispatch here; calling them directly returns un-awaited coroutines
        and the shade keeps a live-looking bar. Order matters: stop first,
        otherwise the tray clear can race the service's own ongoing
        notification.
        """
        if self._service is None:
            return
        try:
            self.page.run_task(self._service.stop_foreground_service)
            self.page.run_task(self._service.cancel_all)
            self._ready = False
        except Exception as exc:
            logger.warning("ScanNotifier: shutdown failed: %s", exc)
