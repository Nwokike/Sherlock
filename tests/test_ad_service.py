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
    ad_service = _mobile_service()
    _run(ad_service.preload_interstitial())
    stale = ad_service.interstitial
    # Simulate a spent/stale ad whose native show() always fails.
    stale.show = _fail  # type: ignore[method-assign]
    with caplog.at_level(logging.WARNING):
        shown = _run(ad_service.show_interstitial())
    assert shown is False
    assert any("show failed" in r.message for r in caplog.records)
    # Restocked exactly one replacement, and it is keep-alive registered.
    assert ad_service.interstitial is not None
    assert ad_service.interstitial is not stale
    assert ad_service.interstitial in ad_service.page.services


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
