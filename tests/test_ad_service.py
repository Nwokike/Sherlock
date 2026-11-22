"""AdService behavior tests — honest outcomes, no silent failures.

Desktop-platform gates are exercised with a fake non-mobile page; the
mobile-only paths are exercised with a fake mobile page (flet_ads is
installed, and constructing its service objects outside a real Flet
session is safe: Service.init() silently skips registration when no page
context is active). The goal is that every gate LOGS and returns a
truthful, actionable outcome instead of swallowing.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import flet_ads as fta

from services.ad_service import AdService


class _Platform:
    def __init__(self, mobile: bool):
        self._mobile = mobile

    def is_mobile(self) -> bool:
        return self._mobile


class _FakePage:
    def __init__(self, mobile: bool = False):
        self.platform = _Platform(mobile)
        self.services: list = []
        self.scheduled: list = []

    def run_task(self, coro_fn, *args, **kwargs):
        """Really run the coroutine (the show path is async end to end)."""
        task = asyncio.get_running_loop().create_task(coro_fn(*args, **kwargs))
        self.scheduled.append(task)
        return task


def _run(coro):
    return asyncio.run(coro)


def _desktop_service() -> AdService:
    return AdService(_FakePage(mobile=False))


def _mobile_service() -> AdService:
    return AdService(_FakePage(mobile=True))


def test_gather_consent_desktop_allows_ads_and_logs(caplog):
    ad_service = _desktop_service()
    with caplog.at_level(logging.INFO):
        _run(ad_service.gather_consent())
    assert ad_service._can_request_ads is True
    assert any("non-mobile" in r.message for r in caplog.records)


def test_show_privacy_options_without_manager_is_honest(caplog):
    ad_service = _desktop_service()
    with caplog.at_level(logging.WARNING):
        outcome = _run(ad_service.show_privacy_options())
    assert outcome == "no_manager"
    assert any("missing" in r.message for r in caplog.records)


def test_preload_interstitial_desktop_skips_with_log(caplog):
    ad_service = _desktop_service()
    with caplog.at_level(logging.INFO):
        _run(ad_service.preload_interstitial())
    assert ad_service.interstitial is None
    assert any("preload skipped" in r.message for r in caplog.records)


def test_show_interstitial_desktop_returns_false_with_log(caplog):
    ad_service = _desktop_service()
    with caplog.at_level(logging.INFO):
        shown = _run(ad_service.show_interstitial())
    assert shown is False
    assert any("interstitial skipped" in r.message.lower() for r in caplog.records)


def test_close_is_idempotent():
    ad_service = _desktop_service()
    _run(ad_service.close())
    assert ad_service._is_shutting_down is True
    _run(ad_service.close())  # must not raise


def test_desktop_banner_ad_is_zero_sized():
    from components.banner_ad import build_banner_ad

    ctrl = build_banner_ad(_FakePage(mobile=False))
    assert getattr(ctrl, "width", None) == 0
    assert getattr(ctrl, "height", None) == 0


# ── Mobile-path regression tests (keep-alive is the 7c4aa43 bug class) ──


def test_mobile_preload_keeps_service_alive():
    ad_service = _mobile_service()
    _run(ad_service.preload_interstitial())
    assert ad_service.interstitial is not None
    assert ad_service.interstitial in ad_service.page.services


def test_mobile_show_with_stale_preloaded_ad_returns_false_and_restocks(caplog):
    """A LOADED ad whose native show() fails must release and restock.

    The ad has to be marked loaded first: calling show() on an unloaded
    instance is the silent native no-op this service now refuses to do.
    """
    ad_service = _mobile_service()
    _run(ad_service.preload_interstitial())
    stale = ad_service.interstitial
    ad_service._on_ad_loaded(ad_service._ad_generation)  # native onAdLoaded
    stale.show = _fail  # type: ignore[method-assign]

    async def run():
        shown = await ad_service.show_interstitial()
        # let the scheduled show task run to completion
        for task in list(ad_service.page.scheduled):
            await task
        return shown

    with caplog.at_level(logging.WARNING):
        shown = _run(run())
    assert shown is True  # the show was triggered; it then failed natively
    assert any("show failed" in r.message for r in caplog.records)
    # The spent ad is gone and exactly one replacement is keep-alive registered.
    assert stale not in ad_service.page.services
    assert ad_service.interstitial is not None
    assert ad_service.interstitial is not stale
    assert ad_service.interstitial in ad_service.page.services
    # A failed show is NOT an impression: the cooldown must not be burned.
    assert ad_service._last_interstitial_at is None


def test_mobile_show_without_preload_queues_fresh_instance(caplog):
    ad_service = _mobile_service()
    with caplog.at_level(logging.INFO):
        shown = _run(ad_service.show_interstitial())
    assert shown is True
    assert ad_service._shown_interstitial is not None
    assert ad_service._shown_interstitial in ad_service.page.services
    assert any("fresh interstitial queued" in r.message for r in caplog.records)


def test_handle_close_releases_shown_ad_keep_alive():
    ad_service = _mobile_service()
    _run(ad_service.show_interstitial())
    shown = ad_service._shown_interstitial
    _run(ad_service._handle_close(None))
    assert ad_service._shown_interstitial is None
    assert shown not in ad_service.page.services


async def _fail(*args, **kwargs):
    raise RuntimeError("stale ad")


# ── Privacy-options outcome branches (the dead Manage button bug class) ──


class _StubConsentManager:
    def __init__(self, status):
        self._status = status

    async def get_privacy_options_requirement_status(self):
        return self._status

    async def show_privacy_options_form(self):
        self.form_shown = True

    async def can_request_ads(self):
        return True


def test_privacy_options_not_required_returns_honest_outcome(caplog):
    ad_service = _desktop_service()
    ad_service._consent_manager = _StubConsentManager(
        fta.PrivacyOptionsRequirementStatus.NOT_REQUIRED
    )
    with caplog.at_level(logging.INFO):
        outcome = _run(ad_service.show_privacy_options())
    assert outcome == "not_required"
    assert any("not required" in r.message for r in caplog.records)


def test_privacy_options_required_shows_form(caplog):
    ad_service = _desktop_service()
    stub = _StubConsentManager(fta.PrivacyOptionsRequirementStatus.REQUIRED)
    ad_service._consent_manager = stub
    with caplog.at_level(logging.INFO):
        outcome = _run(ad_service.show_privacy_options())
    assert outcome == "form_shown"
    assert stub.form_shown is True


def test_privacy_options_status_probe_error_is_reported(caplog):
    ad_service = _desktop_service()

    class _Broken(_StubConsentManager):
        async def get_privacy_options_requirement_status(self):
            raise RuntimeError("bridge down")

    ad_service._consent_manager = _Broken(None)
    with caplog.at_level(logging.WARNING):
        outcome = _run(ad_service.show_privacy_options())
    assert outcome.startswith("error:")
    assert any("status check failed" in r.message for r in caplog.records)


# ── Owner revenue policy: one per hour, confirmed impressions only ───────


def test_cooldown_is_one_hour():
    assert AdService.INTERSTITIAL_MIN_INTERVAL_SEC == 3600.0


def test_queued_show_does_not_burn_the_cooldown():
    """Only a CONFIRMED impression stamps the window.

    show() returning is not proof an ad appeared (the Dart call is
    `_interstitialAd?.show()`), so stamping on the attempt would waste the
    hour on a native no-op.
    """
    svc = _mobile_service()
    _run(svc.show_interstitial())
    assert svc._last_interstitial_at is None
    # native confirms a real display
    svc._on_ad_confirmed(svc._ad_generation, "impression")
    assert svc._last_interstitial_at is not None


def test_impression_stamps_once_per_instance():
    svc = _mobile_service()
    _run(svc.show_interstitial())
    svc._on_ad_confirmed(svc._ad_generation, "open")
    first = svc._last_interstitial_at
    svc._on_ad_confirmed(svc._ad_generation, "impression")
    assert svc._last_interstitial_at == first


def test_concurrent_major_actions_share_one_interstitial():
    svc = _mobile_service()

    async def run():
        first = await svc.show_interstitial()
        second = await svc.show_interstitial()
        return first, second

    first, second = _run(run())
    assert first is True
    assert second is False, "a concurrent action must not queue a second ad"
    assert len(svc.page.services) == 1


def test_preload_never_creates_a_second_instance():
    """The Dart side keeps ONE static ad; a second Python instance would
    overwrite it and steal the first one's callbacks."""
    svc = _mobile_service()
    _run(svc.preload_interstitial())
    first = svc.interstitial
    _run(svc.preload_interstitial())
    assert svc.interstitial is first
    assert len(svc.page.services) == 1


def test_consent_rejection_still_serves_ads():
    """Owner rule: a user who rejects consent still gets ads."""
    svc = _mobile_service()
    svc._can_request_ads = False  # UMP said no

    async def run():
        return await svc.show_interstitial()

    assert _run(run()) is True
    assert svc.interstitial is not None


def test_no_op_show_releases_the_slot_for_the_next_action():
    """A show with no impression and no error is a native no-op; the slot
    must recover or every later action would be skipped forever."""
    svc = _mobile_service()
    svc.SHOW_CONFIRM_TIMEOUT_SEC = 0.01
    _run(svc.preload_interstitial())
    svc._on_ad_loaded(svc._ad_generation)  # native onAdLoaded

    async def _noop_show(*args, **kwargs):
        return None  # succeeds but never fires impression/open/error

    svc.interstitial.show = _noop_show

    async def run():
        await svc.show_interstitial()
        for task in list(svc.page.scheduled):
            await task

    _run(run())
    assert svc._show_in_flight is False
    assert svc._show_pending is False
    assert svc._last_interstitial_at is None
    # restocked, so the next major action can still earn
    assert svc.interstitial is not None


def test_error_from_a_spent_generation_cannot_release_the_current_ad():
    svc = _mobile_service()
    _run(svc.preload_interstitial())
    old_gen = svc._ad_generation
    old_ad = svc.interstitial
    svc._release_ad(old_ad)
    svc._restock()
    current = svc.interstitial
    assert current is not old_ad
    svc._on_ad_error(old_gen, None)  # late event from the spent instance
    assert svc.interstitial is current
    assert current in svc.page.services


def test_hung_load_does_not_wedge_future_interstitials():
    """A native request that fires neither on_load nor on_error must not
    block every later major action for the session (persistent income loss)."""
    svc = _mobile_service()
    svc.LOAD_CONFIRM_TIMEOUT_SEC = 0.01

    async def run():
        first = await svc.show_interstitial()  # queued, never loads
        for task in list(svc.page.scheduled):
            await task
        recovered = svc._show_pending is False
        second = await svc.show_interstitial()
        return first, recovered, second

    first, recovered, second = _run(run())
    assert first is True
    assert recovered, "hung load left the slot wedged"
    assert second is True, "a later major action could not earn"
    assert svc.interstitial is not None


def test_ad_service_ref_is_shared_from_a_normal_import():
    """The ref must live in a normally-imported module.

    When the app entry runs as `__main__`, `from main import ...` re-imports a
    SECOND module object, so a dict kept in the entry module is invisible and
    the export/history/graph interstitials silently never fire.
    """
    from services import ad_service as mod

    sentinel = object()
    mod.AD_SERVICE_REF["service"] = sentinel
    try:
        assert mod.AD_SERVICE_REF["service"] is sentinel
        # the same module object is what callers get
        import services.ad_service as again

        assert again.AD_SERVICE_REF is mod.AD_SERVICE_REF
    finally:
        mod.AD_SERVICE_REF.pop("service", None)
