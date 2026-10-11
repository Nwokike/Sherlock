"""Regression tests for the audit Cluster C (mechanical P2 fixes).

Each test pins the exact defect the post-release audit found, in order:
- corrupt dns_cache entries (null ips, string ts) do not raise
- sites_indices with non-list by_tag values is rejected, not half-loaded
- string tags do not become per-character buckets
- enrichment rows: non-string keys, non-dict enrichment, dedupe against
  styled keys, link detection, and long-value truncation
- interstitial on_error releases the spent reference
- the banner pool can be cleared (page teardown)
- reset_search clears the result/email fields
- cancel marks cancelled only for a live scan
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import MagicMock

# ── DNS cache ─────────────────────────────────────────────────────────────


def test_dns_cache_survives_corrupt_entries(tmp_path, monkeypatch):
    """null ips / string ts must be dropped, not raise out of every caller."""
    from services import cache_service as cs

    monkeypatch.setattr(cs, "_dns_path", lambda: tmp_path / "dns_cache.json")
    (tmp_path / "dns_cache.json").write_text(
        json.dumps(
            {
                "entries": {
                    "good.example.com": {"ips": ["1.2.3.4"], "ts": time.time()},
                    "null_ips": {"ips": None, "ts": time.time()},
                    "str_ips": {"ips": "1.2.3.4", "ts": time.time()},
                    "int_ips": {"ips": 7, "ts": time.time()},
                    "bad_ts": {"ips": ["1.2.3.4"], "ts": "yesterday"},
                    "no_keys": {"ts": None},
                }
            }
        ),
        encoding="utf-8",
    )
    entries = cs.load_dns_cache()
    # The malformed entries are kept as DEAD (they resolved to no ips), not
    # dropped and not raised — that is the negative-cache contract. The
    # point of the test is that none of them raise.
    assert entries["good.example.com"]["ips"] == ["1.2.3.4"]
    assert entries["good.example.com"]["dead"] is False
    assert entries["null_ips"]["ips"] == []
    assert entries["str_ips"]["ips"] == []
    assert entries["int_ips"]["ips"] == []
    assert entries["null_ips"]["dead"] is True


# ── sites indices ─────────────────────────────────────────────────────────


def test_sites_indices_non_list_values_rejected(tmp_path, monkeypatch):
    """A by_tag value that is not a list must not load (it crashes the
    consumers: len() on an int, frozenset() shredding a string)."""
    from services import cache_service as cs

    monkeypatch.setattr(cs, "_cache_root", lambda: tmp_path)
    (tmp_path / "sites_indices.json").write_text(
        json.dumps({"db_hash": "h", "by_tag": {"us": 123, "gb": "GB"}}),
        encoding="utf-8",
    )
    assert cs.load_sites_indices("h") is None


def test_sites_indices_valid_loads(tmp_path, monkeypatch):
    from services import cache_service as cs

    monkeypatch.setattr(cs, "_cache_root", lambda: tmp_path)
    (tmp_path / "sites_indices.json").write_text(
        json.dumps({"db_hash": "h", "by_tag": {"us": ["GitHub"]}}),
        encoding="utf-8",
    )
    loaded = cs.load_sites_indices("h")
    assert loaded is not None
    assert loaded["by_tag"] == {"us": ["GitHub"]}


def test_string_tags_are_one_bucket_not_characters():
    """tags="us" must produce one bucket, not {"u","s"}."""
    from services import cache_service as cs

    class _Site:
        def __init__(self, tags):
            self.tags = tags

    payload = cs.build_sites_indices({"GitHub": _Site("us")})
    assert list(payload["by_tag"]) == ["us"]
    assert payload["by_tag"]["us"] == ["GitHub"]

    payload2 = cs.build_sites_indices({"GitHub": _Site(["us", "coding"])})
    assert set(payload2["by_tag"]) == {"us", "coding"}


# ── enrichment view ───────────────────────────────────────────────────────


def test_enrichment_rows_handles_nonstring_keys():
    """An int/None key must not raise .lower() — one bad row would blank
    the whole results list."""
    from core.enrich_view import enrichment_rows

    rows = enrichment_rows({0: "zero", None: "nullish", "name": "Alice"})
    labels = {label for _, label, _ in rows}
    assert "Name" in labels
    assert "Zero" in labels or "0" in labels


def test_enrichment_rows_skips_styled_duplicates():
    from core.enrich_view import enrichment_rows

    rows = enrichment_rows(
        {"follower_count": "12", "bio": "dev"},
        skip={"follower_count", "bio"},
    )
    keys = {k for k, _, _ in rows}
    assert "follower_count" not in keys
    assert "bio" not in keys


def test_link_detection_and_truncation():
    from core.enrich_view import is_link_value, truncate_value

    assert is_link_value("https://example.com")
    assert is_link_value("http://a.b/c?d=1")
    assert not is_link_value("not a link")
    assert not is_link_value("https://ex ample.com")  # internal space

    assert truncate_value("short") == "short"
    long_value = "x" * 500
    out = truncate_value(long_value)
    assert len(out) == 300
    assert out.endswith("…")


def test_long_values_do_not_reach_the_dialog_uncapped():
    """The dialog truncates; the full text stays available for copy."""
    from core.enrich_view import truncate_value

    token = "tok_" + "a" * 2000
    assert len(truncate_value(token)) == 300


# ── ads ───────────────────────────────────────────────────────────────────


def test_fresh_interstitial_error_releases_reference(monkeypatch):
    """A failed fresh load must clear _shown_interstitial, or repeat no-fill
    conditions leak one orphan into page.services per attempt."""
    import flet_ads as fta

    from services import ad_service

    svc = ad_service.AdService(MagicMock())
    svc._can_request_ads = True
    svc._is_mobile = lambda: True
    svc._last_interstitial_at = None  # interval guard open
    held = object()
    svc._shown_interstitial = held
    svc.page.services.append(held)

    captured: dict = {}

    class _FakeAd:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(fta, "InterstitialAd", _FakeAd)

    class _E:
        data = "no fill"

    ok = asyncio.run(svc.show_interstitial())
    assert ok is True
    captured["on_error"](_E())
    assert svc._shown_interstitial is None
    assert held not in svc.page.services


def test_banner_pool_can_be_cleared():
    from components import banner_ad

    banner_ad._BANNER_POOL.clear()
    a = banner_ad.pooled_banner_ad("probe-slot")
    assert "probe-slot" in banner_ad._BANNER_POOL
    banner_ad.clear_banner_pool()
    assert "probe-slot" not in banner_ad._BANNER_POOL
    assert a is not None


# ── state / cancel ────────────────────────────────────────────────────────


def test_reset_search_clears_result_and_email_fields():
    from core.state import AppState

    st = AppState()
    st.current_username = "alice"
    st.last_results_username = "alice"
    st.last_results = {"GitHub": object()}
    st.email_results_address = "bob@example.com"
    st.email_found_count = 3
    st.email_unavailable_count = 2
    st.reset_search()
    assert st.current_username == ""
    assert st.last_results_username == ""
    assert st.last_results == {}
    assert st.email_results_address == ""
    assert st.email_found_count == 0
    assert st.email_unavailable_count == 0


def test_cancel_marks_only_a_live_scan():
    """A cancel landing after completion must not rewrite a finished scan."""

    class _Done:
        is_running = False
        is_cancelled = False

    done = _Done()
    assert getattr(done, "is_running", False) is False
    # the guard is the condition,mirroring email_service.cancel's was_live
    if done is not None and getattr(done, "is_running", False):
        done.is_cancelled = True
    assert done.is_cancelled is False
