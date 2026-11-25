"""Scan progress in the OS shade, via flet-notifications 1.1.x.

The shade — not the app — owns scan progress. A scan runs minutes; the user
spends most of that outside the app, so progress lives in a foreground
service's notification (which is also what keeps the engine alive when the
app is minimized), while the app itself shows only a tiny tappable
"Scanning…" pill that opens the Results screen.

Pattern verified against the owner's reference apps (CollabShell, Proot
Distro, animepahe-tv) and the installed 1.1.2 API:

- One ``Notifications`` service per page, constructed with its icon and
  ``on_tap``/``on_action`` wired at construction (background taps are
  queued natively and replayed on the next service init; Python never runs
  in the background isolate). Appended once to ``page.services`` so flet's
  refcount service GC keeps it alive.
- Foreground service with ``AndroidForegroundServiceType.SPECIAL_USE`` +
  ``AndroidServiceStartType.STICKY`` (manifest entries live in
  pyproject.toml). The FGS notification IS the progress bar: re-showing the
  same id updates it in place, and ``only_alert_once`` + a LOW/silent
  channel mean advancing progress never dings.
- A Cancel action with ``foreground=True`` brings the app forward and runs
  the controller's cancel, so the scan stops without the user opening the
  app. A View action on the finished notification routes to Results.
- ``stop_foreground_service()`` then ``cancel(id)`` on every exit path —
  the service owns the id, so stopping it first prevents Android from
  re-posting its ongoing entry over the tray clear.
- Permission is asked at the first scan (bounded, so a hung dialog can
  never stall the scan) and a denial only offers the OS settings route.

Every failure is logged, never raised into the scan path.
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft

logger = logging.getLogger(__name__)

_HAS_NOTIFICATIONS = True
try:
    from flet_notifications import (
        AndroidForegroundServiceType,
        AndroidImportance,
        AndroidOptions,
        AndroidProgress,
        AndroidServiceStartType,
        NotificationAction,
        NotificationChannel,
        NotificationOptions,
        Notifications,
    )
except ImportError:  # pragma: no cover — dep is pinned in pyproject
    _HAS_NOTIFICATIONS = False

# Bundled white-silhouette drawable (android_res/drawable-*/ic_stat_sherlock.png).
NOTIFICATION_ICON = "ic_stat_sherlock"

# The FGS notification id must be NONZERO (the plugin rejects 0).
NOTIF_ID_SCAN = 1
# A finished scan gets its own auto-cancelling row (the progress row is
# ongoing and would otherwise stay in the shade).
NOTIF_ID_DONE = 2

CHANNEL_SCAN = "sherlock_scan"
CHANNEL_RESULT = "sherlock_result"

# Route payload on every scan notification: "open the live results".
PAYLOAD_ROUTE = "sherlock://results"

_ACTION_CANCEL = "cancel"
_ACTION_VIEW = "view"

# Human-interaction bound on the permission dialog. Reference apps call it
# unbounded, but a first-run dialog the user ignores must not stall the scan
# start (the old 20s stall bug). A timeout here does NOT latch anything off.
_PERMISSION_TIMEOUT_SEC = 15.0

# Channel declarations (created once; Android fixes sound/vibration at
# creation, so a silent progress channel and an audible result channel must
# be separate).
_SCAN_CHANNEL = NotificationChannel(
    id=CHANNEL_SCAN,
    name="Scan progress",
    description="Live progress of a running username or email scan",
    importance=AndroidImportance.LOW,
    play_sound=False,
    enable_vibration=False,
    show_badge=False,
)
_RESULT_CHANNEL = NotificationChannel(
    id=CHANNEL_RESULT,
    name="Scan results",
    importance=AndroidImportance.DEFAULT,
    show_badge=True,
)


class ScanNotifier:
    """OS-notification progress surface for one app lifetime."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self._service: Notifications | None = None
        self._channels_made = False
        self._fgs_running = False
        # One native stop per started service: stop_service() is reached from
        # completion, cancel, supersede and app-close, sometimes twice.
        self._stop_done = False
        # Re-entrancy guard for an in-flight stop.
        self._stopping = False
        self._target = ""
        self._is_email = False
        self._on_cancel = None
        self._on_view = None
        self._on_permission_denied = None
        # The denial snackbar is offered once per denial, not on every scan.
        self._denial_notified = False
        # Coalescing progress poster: the UI never awaits the platform
        # channel, and at most one bridge call is in flight at a time.
        self._progress_pending: tuple[int, int] | None = None
        self._poster_task = None

    @property
    def available(self) -> bool:
        return self._service is not None

    def _is_android(self) -> bool:
        """Foreground services exist only on Android; desktop posts plain
        notifications instead (both reference apps guard the same way)."""
        try:
            return (
                not getattr(self.page, "web", False)
                and self.page.platform == ft.PagePlatform.ANDROID
            )
        except Exception:
            return False

    def set_handlers(
        self, *, on_cancel=None, on_view=None, on_permission_denied=None
    ) -> None:
        self._on_cancel = on_cancel
        self._on_view = on_view
        self._on_permission_denied = on_permission_denied

    # ── setup ───────────────────────────────────────────────────────────

    async def mount(self) -> bool:
        """Construct the service and create the channels (idempotent).

        Called once at app init so the first scan does not pay for it.
        """
        if not _HAS_NOTIFICATIONS:
            return False
        try:
            if self._service is None:
                svc = Notifications(android_default_icon=NOTIFICATION_ICON)
                svc.on_tap = self._handle_tap
                svc.on_action = self._handle_action
                self._service = svc
                if svc not in self.page.services:
                    self.page.services.append(svc)
                logger.info("ScanNotifier: service mounted")
            if not self._channels_made:
                await self._service.create_channel(_SCAN_CHANNEL)
                await self._service.create_channel(_RESULT_CHANNEL)
                self._channels_made = True
                logger.info("ScanNotifier: channels created")
            return True
        except Exception as exc:
            logger.warning("ScanNotifier: mount failed: %s", exc)
            return False

    async def ensure_permission(self) -> bool:
        """Ask POST_NOTIFICATIONS before each foreground-service start.

        Bounded so a dialog the user ignores can never stall the scan. A
        denial/timeout is NOT latched forever: the reference apps re-ask on
        every service start, and Android simply returns False without a dialog
        once the user has denied. The offer to open OS settings is shown once
        per denial, not on every scan.
        """
        if self._service is None:
            return False
        try:
            granted = await asyncio.wait_for(
                self._service.request_permissions(), timeout=_PERMISSION_TIMEOUT_SEC
            )
        except TimeoutError:
            logger.info(
                "ScanNotifier: permission dialog unanswered after %.0fs — "
                "scanning without notifications",
                _PERMISSION_TIMEOUT_SEC,
            )
            return False
        except Exception as exc:
            logger.warning("ScanNotifier: permission request failed: %s", exc)
            return False
        if granted:
            self._denial_notified = False
            return True
        logger.info("ScanNotifier: notifications denied — scans still run")
        if not self._denial_notified:
            self._denial_notified = True
            cb = self._on_permission_denied
            if cb is not None:
                try:
                    cb()
                except Exception as exc:
                    logger.warning("ScanNotifier: denied handler failed: %s", exc)
        return False

    # ── scan lifecycle ──────────────────────────────────────────────────

    async def scan_started(self, target: str, *, is_email: bool = False) -> bool:
        """Open the foreground service; its notification is the progress bar."""
        if self._service is None or not self._is_android():
            # Desktop/web have no foreground service; the scan still runs and
            # progress() below posts plain notifications on every platform.
            return False
        kind = "email" if is_email else "username"
        self._target = target
        self._is_email = is_email
        if self._fgs_running:
            return True  # one scan notification per app
        if not await self.ensure_permission():
            # Permission declined/unanswered: the scan still runs, the app
            # simply has no shade progress. Never blocks the scan.
            return False
        try:
            await self._service.start_foreground_service(
                NOTIF_ID_SCAN,
                title="Sherlock",
                body=f"Scanning {kind}: {target}",
                payload=PAYLOAD_ROUTE,
                start_type=AndroidServiceStartType.STICKY,
                service_types=[AndroidForegroundServiceType.SPECIAL_USE],
                actions=[
                    NotificationAction(
                        id=_ACTION_CANCEL, title="Cancel", foreground=True
                    )
                ],
                options=NotificationOptions(
                    android=AndroidOptions(
                        # The channel OBJECT, not its bare ID: a missing ID-only
                        # channel is auto-created loud ("Notifications",
                        # DEFAULT importance) when mount() hasn't finished.
                        channel=_SCAN_CHANNEL,
                        silent=True,
                        only_alert_once=True,
                        ongoing=True,
                        progress=AndroidProgress(value=0, max=100, indeterminate=True),
                    )
                ),
            )
            self._fgs_running = True
            self._stop_done = False
            return True
        except Exception as exc:
            logger.warning("ScanNotifier: foreground service failed: %s", exc)
            return False

    def progress(self, checked: int, total: int) -> None:
        """Queue a shade progress update. NEVER awaited by the UI.

        The render loop must not wait on a platform-channel round-trip: at
        2 Hz that serialises the UI behind the notification bridge (the
        reported "notification updates but the Results screen freezes" bug).
        One coalescing poster task drains the LATEST values, so a slow bridge
        never backs up and no call is made from a dead Flet session.
        """
        if self._service is None:
            return
        self._progress_pending = (checked, total)
        self._ensure_poster()

    def _ensure_poster(self) -> None:
        if self._poster_task is not None and not self._poster_task.done():
            return
        try:
            # Touch the session BEFORE creating the coroutine: run_task reads
            # the session after the coroutine exists, so a destroyed session
            # would leave an unawaited coroutine behind (CollabShell's rule).
            _ = self.page.session
            self._poster_task = self.page.run_task(self._poster_loop)
        except Exception as exc:
            logger.debug("ScanNotifier: progress poster not scheduled: %s", exc)

    async def _poster_loop(self) -> None:
        while True:
            pending = self._progress_pending
            if pending is None:
                # Yield once so a value queued by the UI loop at the same
                # moment lands before we decide the queue is empty.
                await asyncio.sleep(0)
                if self._progress_pending is None:
                    return
                continue
            self._progress_pending = None
            await self._post_once(*pending)

    async def _post_once(self, checked: int, total: int) -> None:
        # Clamp: AndroidProgress validates value <= max, so an overshoot tick
        # would raise and silently freeze the bar.
        pct = max(0, min(int(checked / max(total, 1) * 100), 100)) if total else 0
        try:
            await self._service.show(
                NOTIF_ID_SCAN,
                title="Sherlock",
                body=f"{checked}/{total} checked" if total else "Preparing…",
                payload=PAYLOAD_ROUTE,
                actions=[
                    NotificationAction(
                        id=_ACTION_CANCEL, title="Cancel", foreground=True
                    )
                ],
                options=NotificationOptions(
                    android=AndroidOptions(
                        channel=_SCAN_CHANNEL,
                        silent=True,
                        only_alert_once=True,
                        ongoing=True,
                        progress=AndroidProgress(
                            value=pct, max=100, indeterminate=not bool(total)
                        ),
                    )
                ),
            )
        except Exception as exc:
            logger.debug("ScanNotifier: progress post failed: %s", exc)

    async def scan_finished(self, found: int, total: int) -> None:
        """Stop the service, drop the progress row, post the result row."""
        if self._service is None:
            return
        noun = "results" if self._is_email else "accounts"
        suffix = f" · {total} checked" if total else ""
        await self.stop_service()
        try:
            await self._service.show(
                NOTIF_ID_DONE,
                title=f"Scan finished — {found} {noun}",
                body=f"{self._target}{suffix}",
                payload=PAYLOAD_ROUTE,
                actions=[
                    NotificationAction(id=_ACTION_VIEW, title="View", foreground=True)
                ],
                options=NotificationOptions(
                    android=AndroidOptions(
                        channel=_RESULT_CHANNEL, auto_cancel=True, ongoing=False
                    )
                ),
            )
        except Exception as exc:
            logger.warning("ScanNotifier: finish post failed: %s", exc)

    async def stop_service(self) -> None:
        """Stop the FGS and clear the progress row. One call for every exit.

        Stop first: the service owns NOTIF_ID_SCAN, so stopping before the
        cancel prevents Android from re-posting its ongoing entry. Guarded so
        completion/cancel/supersede/app-close cannot race two stops, and the
        running flag clears only after the stop attempt.
        """
        if self._stopping or self._service is None:
            return
        self._stopping = True
        try:
            if (self._fgs_running or self._is_android()) and not self._stop_done:
                try:
                    await self._service.stop_foreground_service()
                    logger.info("ScanNotifier: foreground service stopped")
                except Exception as exc:
                    # Loud on purpose: this is the "does the service actually
                    # close at 100%?" signal to check on a device.
                    logger.warning("ScanNotifier: stop service failed: %s", exc)
                self._stop_done = True
            self._fgs_running = False
            try:
                await self._service.cancel(NOTIF_ID_SCAN)
            except Exception as exc:
                logger.warning("ScanNotifier: cancel failed: %s", exc)
        finally:
            self._stopping = False

    async def shutdown(self) -> None:
        """Teardown on app close."""
        await self.stop_service()
        if self._service is not None:
            try:
                await self._service.cancel_all()
            except Exception as exc:
                logger.warning("ScanNotifier: cancel_all failed: %s", exc)

    async def open_settings(self) -> None:
        """Route the user to the OS notification settings for this app."""
        if self._service is None:
            return
        try:
            await self._service.open_settings()
        except Exception as exc:
            logger.warning("ScanNotifier: open settings failed: %s", exc)

    async def are_notifications_enabled(self) -> bool:
        """OS-level notification authorization, for the Settings row.

        True where the platform has no permission gate (desktop); a failure
        reads as "blocked" so the row still offers the settings route.
        """
        if self._service is None:
            return False
        try:
            return bool(await self._service.are_notifications_enabled())
        except Exception as exc:
            logger.debug("ScanNotifier: enabled check failed: %s", exc)
            return False

    # ── events ──────────────────────────────────────────────────────────

    async def _handle_tap(self, e) -> None:
        if self._on_view is not None:
            try:
                self._on_view()
            except Exception as exc:
                logger.warning("ScanNotifier: view handler failed: %s", exc)

    async def _handle_action(self, e) -> None:
        action_id = getattr(e, "action_id", "") or ""
        if action_id == _ACTION_CANCEL:
            if self._on_cancel is not None:
                try:
                    self._on_cancel()
                except Exception as exc:
                    logger.warning("ScanNotifier: cancel handler failed: %s", exc)
            return
        if action_id == _ACTION_VIEW:
            if self._on_view is not None:
                try:
                    self._on_view()
                except Exception as exc:
                    logger.warning("ScanNotifier: view handler failed: %s", exc)
            return
        logger.debug("ScanNotifier: ignoring unknown action %r", action_id)
