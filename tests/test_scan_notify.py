"""Lifecycle tests for the flet-notifications integration (scan_notify).

Covers the shape the OS actually receives, without a notification
backend: one notification id per scan (re-show updates in place),
indeterminate -> determinate progress, completion with counts, cancel
clearing the bar, and the shutdown path. Also pins the design decision
that no manifest patch is required (show + foreground actions only).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.scan_notify import (
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


def test_scan_start_uses_indeterminate_progress(notifier):
    notifier.scan_started("torvalds", is_email=False)
    (name, args, kwargs) = _dispatched(notifier.page)[0]
    assert name == "show"
    assert args[0] == NOTIF_ID_SCAN  # stable id -> update in place
    assert args[1] == "Scanning username"
    assert "torvalds" in args[2]
    assert kwargs["show_progress"] is True
    assert kwargs["indeterminate"] is True
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
    """Completion posts its own notification and dismisses the progress bar."""
    notifier.scan_started("torvalds", is_email=False)
    notifier.progress(100, 100)
    notifier.scan_finished(14, 5897)
    dispatched = _dispatched(notifier.page)
    shows = [d for d in dispatched if d[0] == "show" and d[1][0] == NOTIF_ID_DONE]
    assert len(shows) == 1
    finish = shows[0]
    assert "14 accounts" in finish[1][1]
    assert [a.id for a in finish[2]["actions"]] == ["view"]
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
    """shutdown() is sync and on the teardown path, so it calls the
    backend directly rather than through page.run_task."""
    svc = MagicMock()
    notifier._service = svc
    notifier.shutdown()
    svc.cancel_all.assert_called_once()
    assert notifier.page.run_task.call_count == 0


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
