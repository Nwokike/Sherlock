"""Scan shade-notification behavior (flet-notifications 1.1.x API).

Pins the reference-app pattern: a foreground service whose notification IS
the progress bar, a LOW/silent channel, a Cancel action, reused ids, and
stop-before-cancel teardown. Every native call is mocked — no device.
"""

from __future__ import annotations

import asyncio

import pytest

import services.scan_notify as sn


class _Platform:
    def __init__(self, mobile=True):
        self._mobile = mobile

    def is_mobile(self):
        return self._mobile


class _FakePage:
    def __init__(self, mobile=True):
        self.platform = _Platform(mobile)
        self.services: list = []
        self.tasks: list = []

    def run_task(self, coro_fn, *args, **kwargs):
        task = asyncio.get_running_loop().create_task(coro_fn(*args, **kwargs))
        self.tasks.append(task)
        return task


class _FakeNotifications:
    """Records the calls the real Notifications service would make."""

    permission_result = True
    permission_raises = None
    fgs_raises = None

    def __init__(self, android_default_icon=None):
        self.android_default_icon = android_default_icon
        self.on_tap = None
        self.on_action = None
        self.channels: list = []
        self.fgs_calls: list = []
        self.shown: list = []
        self.cancelled: list = []
        self.stopped = False
        self.cancelled_all = False
        self.settings_opened = False

    async def create_channel(self, channel):
        self.channels.append(channel)

    async def request_permissions(self, **kwargs):
        if _FakeNotifications.permission_raises is not None:
            raise _FakeNotifications.permission_raises
        return _FakeNotifications.permission_result

    async def are_notifications_enabled(self):
        return True

    async def start_foreground_service(self, id, **kwargs):  # noqa: A002
        if _FakeNotifications.fgs_raises is not None:
            raise _FakeNotifications.fgs_raises
        self.fgs_calls.append((id, kwargs))

    async def stop_foreground_service(self):
        self.stopped = True

    async def show(self, id, **kwargs):  # noqa: A002
        self.shown.append((id, kwargs))

    async def cancel(self, id, **kwargs):  # noqa: A002
        self.cancelled.append(id)

    async def cancel_all(self):
        self.cancelled_all = True

    async def open_settings(self):
        self.settings_opened = True


@pytest.fixture
def fake(monkeypatch):
    _FakeNotifications.permission_result = True
    _FakeNotifications.permission_raises = None
    _FakeNotifications.fgs_raises = None
    monkeypatch.setattr(sn, "Notifications", _FakeNotifications)
    monkeypatch.setattr(sn, "_HAS_NOTIFICATIONS", True)
    return _FakeNotifications


def _notifier(fake):
    page = _FakePage()
    return sn.ScanNotifier(page), page


def _run(coro):
    return asyncio.run(coro)


def test_mount_creates_service_and_channels(fake):
    notifier, page = _notifier(fake)
    assert _run(notifier.mount()) is True
    svc = notifier._service
    assert svc in page.services
    assert svc.android_default_icon == sn.NOTIFICATION_ICON
    ids = {c.id for c in svc.channels}
    assert ids == {sn.CHANNEL_SCAN, sn.CHANNEL_RESULT}
    scan = next(c for c in svc.channels if c.id == sn.CHANNEL_SCAN)
    assert scan.play_sound is False and scan.enable_vibration is False


def test_mount_is_idempotent(fake):
    notifier, _ = _notifier(fake)
    _run(notifier.mount())
    svc = notifier._service
    _run(notifier.mount())
    assert notifier._service is svc
    assert len(svc.channels) == 2


def test_permission_denial_is_not_fatal_and_offers_settings(fake):
    notifier, _ = _notifier(fake)
    _run(notifier.mount())
    denied = []
    notifier.set_handlers(on_permission_denied=lambda: denied.append(1))
    _FakeNotifications.permission_result = False
    assert _run(notifier.ensure_permission()) is False
    assert denied == [1]
    # The scan still runs: the foreground service keeps the engine alive even
    # if the shade row is hidden, and permission is only asked once.
    assert _run(notifier.scan_started("alice")) is True


def test_permission_timeout_does_not_latch(fake, monkeypatch):
    notifier, _ = _notifier(fake)
    _run(notifier.mount())
    monkeypatch.setattr(sn, "_PERMISSION_TIMEOUT_SEC", 0.01)

    async def _hang(**kwargs):
        await asyncio.sleep(3600)
        return False

    notifier._service.request_permissions = _hang
    assert _run(notifier.ensure_permission()) is False
    # not latched: a later scan still attempts the foreground service
    assert _run(notifier.scan_started("alice")) is True


def test_scan_started_opens_foreground_service_with_progress_and_cancel(fake):
    notifier, _ = _notifier(fake)
    _run(notifier.mount())
    assert _run(notifier.scan_started("alice", is_email=False)) is True
    svc = notifier._service
    assert len(svc.fgs_calls) == 1
    call_id, kw = svc.fgs_calls[0]
    assert call_id == sn.NOTIF_ID_SCAN and call_id != 0
    assert kw["start_type"] is sn.AndroidServiceStartType.STICKY
    assert sn.AndroidForegroundServiceType.SPECIAL_USE in kw["service_types"]
    actions = kw["actions"]
    assert [a.id for a in actions] == [sn._ACTION_CANCEL]
    android = kw["options"].android
    assert android.channel == sn.CHANNEL_SCAN
    assert android.silent and android.only_alert_once and android.ongoing
    assert android.progress.indeterminate is True


def test_second_scan_does_not_reopen_the_service(fake):
    notifier, _ = _notifier(fake)
    _run(notifier.mount())
    _run(notifier.scan_started("alice"))
    _run(notifier.scan_started("bob"))
    assert len(notifier._service.fgs_calls) == 1


def test_progress_reuses_the_same_id(fake):
    notifier, _ = _notifier(fake)

    async def run():
        await notifier.mount()
        await notifier.scan_started("alice")
        notifier.progress(250, 5000)
        await asyncio.gather(*notifier.page.tasks)

    _run(run())
    svc = notifier._service
    shown = [c for c in svc.shown if c[0] == sn.NOTIF_ID_SCAN]
    assert shown, "progress must update the FGS notification in place"
    progress = shown[-1][1]["options"].android.progress
    assert progress.value == 5 and progress.max == 100
    assert progress.indeterminate is False


def test_finish_stops_service_then_posts_result(fake):
    notifier, _ = _notifier(fake)
    _run(notifier.mount())
    _run(notifier.scan_started("alice"))
    _run(notifier.scan_finished(12, 5000))
    svc = notifier._service
    assert svc.stopped is True
    assert sn.NOTIF_ID_SCAN in svc.cancelled
    done = [c for c in svc.shown if c[0] == sn.NOTIF_ID_DONE]
    assert done, "a finished scan must post a result row"
    assert done[-1][1]["options"].android.auto_cancel is True


def test_stop_service_stops_before_cancelling(fake):
    """The FGS owns the id; stopping first stops Android re-posting it."""
    notifier, _ = _notifier(fake)
    _run(notifier.mount())
    _run(notifier.scan_started("alice"))
    order: list = []
    notifier._service.stop_foreground_service = _record(order, "stop")
    notifier._service.cancel = _record(order, "cancel", ids=True)
    _run(notifier.stop_service())
    assert order[0] == "stop"
    assert notifier._fgs_running is False


def _record(order, tag, ids=False):
    async def _do(*args, **kwargs):
        order.append(tag)
        if ids:
            order.append(args[0] if args else kwargs.get("id"))

    return _do


def test_cancel_action_routes_to_controller(fake):
    notifier, _ = _notifier(fake)
    _run(notifier.mount())
    cancelled = []
    viewed = []
    notifier.set_handlers(
        on_cancel=lambda: cancelled.append(1), on_view=lambda: viewed.append(1)
    )

    async def run():
        await notifier._handle_action(_Event(action_id=sn._ACTION_CANCEL))
        await notifier._handle_tap(_Event(action_id=""))

    _run(run())
    assert cancelled == [1] and viewed == [1]


def test_fgs_failure_is_swallowed(fake):
    notifier, _ = _notifier(fake)
    _run(notifier.mount())
    _FakeNotifications.fgs_raises = RuntimeError("no native layer")
    assert _run(notifier.scan_started("alice")) is False
    assert notifier._fgs_running is False


def test_shutdown_clears_everything(fake):
    notifier, _ = _notifier(fake)
    _run(notifier.mount())
    _run(notifier.scan_started("alice"))
    _run(notifier.shutdown())
    svc = notifier._service
    assert svc.stopped and svc.cancelled_all
    assert notifier._fgs_running is False


class _Event:
    def __init__(self, action_id="", data=None):
        self.action_id = action_id
        self.data = data


def test_fresh_denial_does_not_start_the_foreground_service(fake):
    """A first-run denial must return False and leave the FGS down."""
    notifier, _ = _notifier(fake)
    _run(notifier.mount())
    _FakeNotifications.permission_result = False
    assert _run(notifier.scan_started("alice")) is False
    assert notifier._service.fgs_calls == []
    assert notifier._fgs_running is False
