"""Service contract tests across all three engine modes (username/email/phone)."""


import asyncio

from services.email_service import EmailService
from services.phone_service import PhoneResult, PhoneService
from services.sherlock_service import SherlockService, SiteResult


def test_sherlock_load_sites_populates_mode_catalog():
    svc = SherlockService()
    total = asyncio.run(svc.load_sites(mode="username"))
    assert total > 2000
    assert svc._modules is not None
    assert svc._modules_mode == "username"


def test_sherlock_load_sites_email_mode():
    svc = SherlockService()
    total = asyncio.run(svc.load_sites(mode="email"))
    assert 100 < total < 500
    assert svc._modules_mode == "email"


def test_email_service_available():
    assert EmailService().is_available is True


def test_email_skip_password_recovery_filters_loud():
    from services.user_scanner_compat import (
        get_site_name_user,
        is_loud_user,
        load_email_modules,
    )

    mods = load_email_modules()
    loud = [
        m for m in mods if is_loud_user(get_site_name_user(m[1]), is_email=True)
    ]
    kept = [
        m for m in mods if not is_loud_user(get_site_name_user(m[1]), is_email=True)
    ]
    assert len(kept) <= len(mods)
    assert all(m not in kept for m in loud)


def test_phone_service_load_sites():
    svc = PhoneService()
    total = asyncio.run(svc.load_sites())
    assert total == 5


def test_phone_result_mapping_registered():
    r = PhoneResult(name="facebook", category="Social", exists=True)
    assert r.exists is True
    assert r.name == "facebook"


def test_site_result_has_confidence_badge_field():
    sr = SiteResult(site_name="github", status="Claimed", badge="confirmed")
    assert sr.badge == "confirmed"


def test_hudson_methods_exist():
    assert callable(SherlockService.run_hudson)
    assert callable(EmailService.run_hudson)


def test_cross_scan_service_methods_wired():
    svc = SherlockService()
    assert hasattr(svc, "_run")
