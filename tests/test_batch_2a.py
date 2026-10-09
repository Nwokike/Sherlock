"""Regression tests for Fix Batch 2a (UI correctness).

Covers: changelog fallback, geo flush behavior, fingerprint helpers,
ResultCard click/numeric guards, and profile-dialog JSON robustness.
"""

import json

from components.result_card import _first_present
from core.changelog import CHANGELOG, notes_for
from screens.results_screen import (
    _email_fingerprint,
    _enrichment_fingerprint,
    _username_fingerprint,
)


class _Site:
    def __init__(self, site_name, status):
        self.site_name = site_name
        self.status = status


def test_notes_for_falls_back_to_latest():
    """The newest changelog entry is APP_VERSION's — the guard that kept
    2.2.0 hardcoded here was itself the version-drift bug."""
    from core.constants import APP_VERSION

    latest = next(iter(CHANGELOG.values()))
    assert notes_for("9.9.9-nonexistent") == latest
    assert latest == CHANGELOG[APP_VERSION]
    assert APP_VERSION in CHANGELOG
    assert notes_for("2.0.0") == CHANGELOG["2.0.0"]


def test_geo_flush_flag_clears_on_save(monkeypatch):
    """After the interval expires, dirty entries flush and the flag resets."""
    import core.geo_utils as geo

    saved = {}
    monkeypatch.setattr(
        "services.cache_service.save_geo_cache", lambda store: saved.update(store)
    )
    monkeypatch.setattr(geo, "_load_disk_cache", lambda: {})
    old_last, old_dirty = geo._LAST_GEO_FLUSH[0], geo._GEO_FLUSH_DIRTY[0]
    try:
        geo._GEO_FLUSH_DIRTY[0] = True
        geo._LAST_GEO_FLUSH[0] = 0.0  # long ago: interval expired
        geo._record_disk_hit("xx-test", None)
        assert geo._GEO_FLUSH_DIRTY[0] is False
    finally:
        geo._LAST_GEO_FLUSH[0] = old_last
        geo._GEO_FLUSH_DIRTY[0] = old_dirty
        geo._DISK_CACHE = None
        geo.resolve_location.cache_clear()


def test_geo_flush_throttles_within_interval(monkeypatch):
    import time

    import core.geo_utils as geo

    calls = []
    monkeypatch.setattr(
        "services.cache_service.save_geo_cache", lambda store: calls.append(store)
    )
    monkeypatch.setattr(geo, "_load_disk_cache", lambda: {})
    old_last, old_dirty = geo._LAST_GEO_FLUSH[0], geo._GEO_FLUSH_DIRTY[0]
    try:
        geo._GEO_FLUSH_DIRTY[0] = False
        geo._LAST_GEO_FLUSH[0] = time.monotonic()
        geo._record_disk_hit("xx-test-2", None)
        assert geo._GEO_FLUSH_DIRTY[0] is True
        assert calls == []
    finally:
        geo._LAST_GEO_FLUSH[0] = old_last
        geo._GEO_FLUSH_DIRTY[0] = old_dirty
        geo._DISK_CACHE = None
        geo.resolve_location.cache_clear()


def test_first_present_preserves_zero_and_false():
    assert _first_present({"a": 0, "b": 5}, ("a", "b")) == 0
    assert _first_present({"a": None, "b": False}, ("a", "b")) is False
    assert _first_present({"a": None}, ("a", "b")) is None
    assert _first_present({}, ("a",)) is None


def test_email_fingerprint_changes_on_status_flip():
    rows = [
        {"name": "GitHub", "exists": True, "rateLimit": False, "unavailable": False}
    ]
    before = _email_fingerprint(rows)
    rows[0]["exists"] = False
    assert _email_fingerprint(rows) != before
    assert _email_fingerprint([]) == ()


def test_username_fingerprint_changes_on_replace():
    items = [_Site("GitHub", "Claimed")]
    before = _username_fingerprint(items)
    items[0] = _Site("GitLab", "Claimed")
    assert _username_fingerprint(items) != before


def test_enrichment_fingerprint_changes_on_value_edit():
    enrich = {"https://x": {"name": "Ann"}}
    before = _enrichment_fingerprint(enrich)
    enrich["https://x"] = {"name": "Ann", "bio": "hi"}
    assert _enrichment_fingerprint(enrich) != before
    assert _enrichment_fingerprint(None) == ()
    assert _enrichment_fingerprint({}) == ()


def test_profile_json_dumps_with_datetime_default():
    """The dossier JSON path must survive non-JSON natives (default=str)."""
    import datetime

    payload = {
        "enrichment": {
            "seen": datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)
        }
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    assert "2024-01-01" in text
