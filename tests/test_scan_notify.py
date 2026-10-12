"""Lifecycle tests for the flet-notifications integration (scan_notify).

Covers the shape the OS actually receives, without a notification
backend: one notification id per scan (re-show updates in place),
indeterminate -> determinate progress, completion with counts, cancel
clearing the bar, and the shutdown path. Also pins the design decision
that no manifest patch is required (show + foreground actions only).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from services.scan_notify import (
    CHANNEL_PROGRESS,
    CHANNEL_RESULT,
    FGS_TYPE,
    NOTIF_ID_DONE,
    NOTIF_ID_SCAN,
    ScanNotifier,
)


@pytest.fixture
def notifier():
    """A ScanNotifier with a stubbed backend, on a mock page."""
    page = MagicMock()
    n = ScanNotifier(page)
    n._service = MagicMock()  # skip construction/permissions
    # Posting paths gate on `is_usable()`, which needs both a service and a
    # granted permission — the legacy tests assume a healthy backend.
    n._ready = True
    return n


def _dispatched(page):
    """The (service_call, args, kwargs) the page actually received.

    The service call is a bound-method Mock; `_mock_name` carries the
    attribute name ("show"/"cancel"/"cancel_all") reliably — `__name__`
    on a Mock is itself a Mock and stringifies empty.
    """
    out = []
    for call in page.run_task.call_args_list:
        args, kwargs = call
        fn = args[0]
        name = getattr(fn, "_mock_name", None)
        if not isinstance(name, str):  # real coroutine function
            name = getattr(fn, "__name__", "?")
        out.append((name, args[1:], kwargs))
    return out


def test_scan_start_runs_the_foreground_service(notifier):
    """A running scan lives in a foreground service, not a plain show().

    The service is what keeps the engine alive when the user closes the app,
    and its notification is what the progress bar advances on.
    """
    notifier.scan_started("torvalds", is_email=False)
    (name, args, kwargs) = _dispatched(notifier.page)[0]
    assert name == "start_foreground_service"
    assert args[0] == NOTIF_ID_SCAN  # stable id -> update in place
    assert args[1] == "Scanning username"
    assert "torvalds" in args[2]
    assert kwargs["show_progress"] is True
    assert kwargs["indeterminate"] is True
    assert kwargs["channel_id"] == CHANNEL_PROGRESS
    assert kwargs["start_type"] == FGS_TYPE
    # a Cancel action is always offered while scanning
    assert [a.id for a in kwargs["actions"]] == ["cancel"]


def test_progress_tick_updates_same_notification_in_place(notifier):
    notifier.scan_started("torvalds", is_email=False)
    notifier.progress(2671, 5897)
    dispatched = _dispatched(notifier.page)
    assert dispatched[1][0] == "show"
    assert dispatched[1][1][0] == NOTIF_ID_SCAN  # same id, not a new one
    assert "45%" in dispatched[1][1][1]
    assert dispatched[1][2]["progress"] == 2671
    assert dispatched[1][2]["max_progress"] == 5897
    assert [a.id for a in dispatched[1][2]["actions"]] == ["cancel"]


def test_completion_swaps_to_a_separate_notification(notifier):
    """Completion stops the service, posts its own notification with the
    found count, offers View and Copy, and clears the progress bar."""
    notifier.scan_started("torvalds", is_email=False)
    notifier.progress(100, 100)
    notifier.scan_finished(14, 5897)
    dispatched = _dispatched(notifier.page)
    shows = [d for d in dispatched if d[0] == "show" and d[1][0] == NOTIF_ID_DONE]
    assert len(shows) == 1
    finish = shows[0]
    assert "14 accounts" in finish[1][1]
    assert finish[2]["channel_id"] == CHANNEL_RESULT
    # View opens results; Copy report takes the summary to the clipboard.
    assert [a.id for a in finish[2]["actions"]] == ["view", "copy"]
    # the service is stopped before the result is posted
    stops = [d for d in dispatched if d[0] == "stop_foreground_service"]
    assert stops and dispatched.index(stops[0]) < dispatched.index(finish)
    # and the progress bar is cleared
    cancels = [d for d in dispatched if d[0] == "cancel" and d[1] == (NOTIF_ID_SCAN,)]
    assert cancels


def test_cancel_clears_the_progress_bar(notifier):
    notifier.scan_started("torvalds", is_email=False)
    notifier.scan_cancelled()
    dispatched = _dispatched(notifier.page)
    cancel = dispatched[-1]
    assert cancel[0] == "cancel"
    assert cancel[1] == (NOTIF_ID_SCAN,)


def test_email_scan_wording(notifier):
    notifier.scan_started("bob@example.com", is_email=True)
    notifier.scan_finished(3, 181)
    dispatched = _dispatched(notifier.page)
    assert "Scanning email" in dispatched[0][1][1]
    done = next(d for d in dispatched if d[0] == "show" and d[1][0] == NOTIF_ID_DONE)
    assert "3 results" in done[1][1]


def test_zero_total_progress_does_not_divide_by_zero(notifier):
    notifier.scan_started("x", is_email=False)
    notifier.progress(0, 0)  # engine has not reported a denominator yet
    (_name, args, _kwargs) = _dispatched(notifier.page)[1]
    assert "0%" in args[1]
    assert args[1] != ""


def test_handlers_wire_cancel_and_view(notifier):
    """The notification buttons route to the app's own handlers."""
    fired = []
    notifier.set_handlers(
        on_cancel=lambda: fired.append("cancel"),
        on_view=lambda: fired.append("view"),
    )
    # simulate the OS delivering an action button press
    notifier._on_cancel()
    notifier._on_view()
    assert fired == ["cancel", "view"]


def test_view_action_failure_is_contained(notifier):
    """A broken view handler must not raise back into the notification."""

    def _boom():
        raise RuntimeError("view handler exploded")

    notifier.set_handlers(on_view=_boom)
    notifier._fire_view()  # logs, does not raise


def test_shutdown_clears_everything(notifier):
    """shutdown() is sync on the teardown path, so it dispatches the async
    cancel_all through run_task rather than calling it directly — a direct
    call returns an un-awaited coroutine and the shade keeps the bar."""
    svc = MagicMock()
    notifier._service = svc
    notifier.shutdown()
    (name, _args, _kwargs) = _dispatched(notifier.page)[0]
    assert name == "cancel_all"
    svc.cancel_all.assert_not_called()


def test_service_missing_is_noop():
    """No flet-notifications installed: everything degrades to a no-op."""
    page = MagicMock()
    n = ScanNotifier(page)
    n._service = None
    n.scan_started("x", is_email=False)
    n.progress(1, 2)
    n.scan_finished(1, 2)
    n.scan_cancelled()
    n.shutdown()
    assert page.run_task.call_count == 0


def test_available_flag_matches_import():
    """The availability probe agrees with the package's importability."""
    import importlib.util

    expected = importlib.util.find_spec("flet_notifications") is not None
    n = ScanNotifier(MagicMock())
    assert n.available is expected


# ── the race that made the first notification of a session vanish ──────


def _deny(notifier):
    """Backend stub where notifications exist but the user declined.

    A plain fake, not a MagicMock of `LocalNotifications` — the real control
    is a dataclass whose methods need a mounted page.
    """
    from services.scan_notify import _FakeBackend

    svc = _FakeBackend(enabled=False, granted=False)
    notifier._service = svc
    return svc


def _grant(notifier):
    """Backend stub with the permission already granted."""
    from services.scan_notify import _FakeBackend

    svc = _FakeBackend(enabled=True, granted=True)
    notifier._service = svc
    return svc


def test_ensure_ready_constructs_and_posts(notifier):
    """ensure_ready awaited before a scan makes the first show possible.

    The regression: firing the init through `page.run_task` returns a Future
    immediately, so `_service` is still None when `scan_started()` runs on
    the next line and the first notification of the session is dropped.
    """
    page = MagicMock()
    page.services = []
    n = ScanNotifier(page)

    # make construction resolve to our stub
    import services.scan_notify as sn

    real = sn.LocalNotifications
    sn.LocalNotifications = lambda: _grant(n)
    try:
        assert asyncio.run(n.ensure_ready()) is True
        assert n._service is not None
        assert n.is_usable() is True
        # now the first post of the session lands
        n.scan_started("torvalds", is_email=False)
        dispatched = _dispatched(n.page)
        assert dispatched
        assert dispatched[0][0] == "start_foreground_service"
    finally:
        sn.LocalNotifications = real


def test_ensure_ready_no_show_when_denied(notifier):
    """A declined permission must suppress the notification, not crash."""
    _deny(notifier)

    assert asyncio.run(notifier.ensure_ready()) is False
    assert notifier.is_usable() is False
    notifier.scan_started("torvalds", is_email=False)
    # nothing posted: the scan still runs, just silently
    assert notifier.page.run_task.call_count == 0


def test_denial_warns_once_and_routes_to_settings(notifier):
    """Decline -> one warning carrying a Settings action -> OS page."""
    svc = _deny(notifier)
    seen = []
    notifier.set_handlers(on_permission_denied=lambda: seen.append(True))

    assert asyncio.run(notifier.ensure_ready()) is False
    assert asyncio.run(notifier.ensure_ready()) is False
    # warned once per session, not once per scan
    assert seen == [True]

    asyncio.run(notifier.open_settings())
    assert svc.settings_calls == 1


def test_permission_enabled_later_needs_no_restart(notifier):
    """Re-probed per scan, so enabling from OS settings takes effect now."""
    svc = _deny(notifier)
    assert asyncio.run(notifier.ensure_ready()) is False

    # user flips the switch in Android settings; next scan sees it
    svc.enabled = True
    assert asyncio.run(notifier.ensure_ready()) is True
    assert notifier.is_usable() is True


def test_no_package_is_a_clean_no_op(notifier):
    """With no notification backend, ensure_ready just says no.

    There is no user setting to consult any more — a scan posts because it
    is a foreground activity the system must show, not because of a
    preference.
    """
    notifier._service = None
    assert asyncio.run(notifier.ensure_ready()) is False
    assert notifier.page.run_task.call_count == 0


# ── channels and the foreground service ───────────────────────────────


async def _ready(n):
    """Bring a fresh notifier to the usable state."""
    import services.scan_notify as sn

    real = sn.LocalNotifications
    sn.LocalNotifications = lambda: _grant(n)
    try:
        await n.ensure_ready()
    finally:
        sn.LocalNotifications = real


def test_two_channels_are_created_once():
    """A silent low channel for progress, a default one for results.

    Sound and vibration are immutable after creation
    (.venv/flet_notifications/channels.py:13-16), so a running scan cannot
    share the finished-scan channel — it must not ding.
    """
    from services.scan_notify import _FakeBackend

    page = MagicMock()
    page.services = []
    n = ScanNotifier(page)
    n._service = _FakeBackend(enabled=True, granted=True)
    asyncio.run(_ready(n))

    ids = [c["id"] for c in n._service.channels]
    assert ids == [CHANNEL_PROGRESS, CHANNEL_RESULT]


def test_completion_stops_the_service_before_posting():
    """Stopping the FGS first avoids the bar and the result racing."""
    page = MagicMock()
    n = ScanNotifier(page)
    n._service = MagicMock()
    n._ready = True
    n.scan_finished(3, 10)
    ops = [d[0] for d in _dispatched(page)]
    assert "stop_foreground_service" in ops
    assert ops.index("stop_foreground_service") < ops.index("show")


def test_cancel_action_routes_to_the_scan_canceller():
    """The shade's Cancel button stops the scan without opening the app."""
    from services.scan_notify import _ACTION_CANCEL

    class _Event:
        action_id = _ACTION_CANCEL

    n = ScanNotifier(MagicMock())
    calls = []
    n.set_handlers(on_cancel=lambda: calls.append(True))
    handler = _installed_on_action(n)
    asyncio.run(handler(_Event()))
    assert calls == [True]


def _installed_on_action(notifier):
    """The on_action closure the notifier installed on its real service."""
    import services.scan_notify as sn

    captured = {}

    class _Svc:
        def __init__(self):
            self.on_action = None
            self.on_tap = None

    def _fake():
        s = _Svc()
        captured["svc"] = s
        return s

    notifier._started = False
    notifier._service = None
    real_ctor = sn.LocalNotifications
    sn.LocalNotifications = _fake
    try:
        asyncio.run(notifier._construct())
    finally:
        sn.LocalNotifications = real_ctor
    return captured["svc"].on_action
