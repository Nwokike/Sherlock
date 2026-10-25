"""Mode-aware module catalog tests (username / email / phone switching)."""


import asyncio

from core.constants import MODE_EMAIL, MODE_USERNAME
from core.state import state
from services.email_service import EmailService
from services.phone_service import PhoneService
from services.sherlock_service import SherlockService


def test_load_catalog_username():
    total = asyncio.run(SherlockService().load_sites(mode=MODE_USERNAME))
    assert total == state.sites_total
    assert state.sites_cache
    assert state.sites_tag_index


def test_load_catalog_phone_swaps_names():
    asyncio.run(PhoneService().load_sites())
    names = {n.lower() for n in (state.sites_cache or [])}
    # phonsint exposes 5 modules; display names use get_site_name
    assert len(names) == 5


def test_load_catalog_email():
    asyncio.run(EmailService().load_sites(mode=MODE_EMAIL))
    assert 100 < state.sites_total < 500


def test_state_has_phone_mode_constant():
    from core.constants import MODE_PHONE as MP

    assert MP == "phone"


def test_selected_sites_default_empty():
    assert state.selected_sites == []
