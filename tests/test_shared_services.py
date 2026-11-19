"""Tests for core.shared_services — mount-once service reuse.

Rationale: every Service construction registers on the page (append + wire
update, no dedup), so per-click ``ft.HapticFeedback()`` etc. accumulate
duplicates over a long session. The shared getters must return the mounted
instance and mounting must be idempotent.
"""

from core.shared_services import (
    mount_shared_services,
    shared_clipboard,
    shared_haptics,
    shared_share,
    shared_url_launcher,
)
from tests.conftest import FakePage


def test_mount_registers_four_services():
    page = FakePage()
    mount_shared_services(page)
    assert len(page.services) == 4
    for attr in (
        "shared_haptics",
        "shared_clipboard",
        "shared_share",
        "shared_url_launcher",
    ):
        assert getattr(page, attr, None) is not None


def test_mount_is_idempotent():
    page = FakePage()
    mount_shared_services(page)
    mount_shared_services(page)
    assert len(page.services) == 4


def test_getters_return_mounted_instances():
    page = FakePage()
    mount_shared_services(page)
    assert shared_haptics(page) is page.shared_haptics
    assert shared_clipboard(page) is page.shared_clipboard
    assert shared_share(page) is page.shared_share
    assert shared_url_launcher(page) is page.shared_url_launcher


def test_repeated_calls_do_not_accumulate():
    """N getter calls must not register N new services (the leak being fixed)."""
    page = FakePage()
    mount_shared_services(page)
    for _ in range(10):
        shared_haptics(page)
        shared_clipboard(page)
        shared_share(page)
        shared_url_launcher(page)
    assert len(page.services) == 4


def test_fallback_constructs_without_page():
    """Outside a live app (tests, early init) getters still return instances."""
    assert shared_haptics(None).__class__.__name__ == "HapticFeedback"
    assert shared_clipboard(None).__class__.__name__ == "Clipboard"
    assert shared_share(None).__class__.__name__ == "Share"
    assert shared_url_launcher(None).__class__.__name__ == "UrlLauncher"
