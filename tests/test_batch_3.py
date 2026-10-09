"""Regression tests for Fix Batch 3 (security + data-correctness).

Covers: Markdown cell escaping, https-only URL helper, update payload
strictness, cached-result enrichment clearing, email 4-bucket restore,
context round-trip, XMind duplicate-site keys.
"""

import asyncio

import pytest

from services.report_service import _https_url, _md_cell


@pytest.fixture(autouse=True)
def _restore_global_state():
    """Snapshot state fields this file mutates via open_cached_result.

    The cached-result tests leave search_mode=EMAIL + email buckets behind;
    without a restore, _apply_progress drops later username ticks as
    cross-mode (found via pairwise bisect with test_logger_and_streaming).
    Restore goes through setattr (AppState is @ft.observable — never
    __dict__ surgery); collections restore in place to keep wrappers.
    """
    from core.state import state

    if state.results_cache is None:
        state.results_cache = {}
    if state.email_results is None:
        state.email_results = []
    if state.enrichments is None:
        state.enrichments = {}
    saved_scalars = {
        "current_username": state.current_username,
        "email_found_count": state.email_found_count,
        "email_not_found_count": state.email_not_found_count,
        "email_rate_limited_count": state.email_rate_limited_count,
        "email_results_address": state.email_results_address,
        "email_total_modules": state.email_total_modules,
        "email_unavailable_count": state.email_unavailable_count,
        "is_searching": state.is_searching,
        "last_results_username": state.last_results_username,
        "progress_version": state.progress_version,
        "search_mode": state.search_mode,
        "search_progress": state.search_progress,
    }
    saved_last = dict(state.last_results) if state.last_results else None
    saved_email = list(state.email_results)
    saved_enrich = dict(state.enrichments)
    saved_cache = dict(state.results_cache)
    yield
    for key, value in saved_scalars.items():
        setattr(state, key, value)
    if saved_last is None:
        state.last_results = None
    else:
        state.last_results.clear()
        state.last_results.update(saved_last)
    state.email_results[:] = saved_email
    state.enrichments.clear()
    state.enrichments.update(saved_enrich)
    state.results_cache.clear()
    state.results_cache.update(saved_cache)


def test_md_cell_escapes_pipes_and_newlines():
    assert _md_cell("a|b") == "a\\|b"
    assert _md_cell("line1\nline2") == "line1 line2"
    assert _md_cell("a\r\nb\rc") == "a b c"
    assert _md_cell(None) == ""
    assert _md_cell(123) == "123"


def test_https_url_allows_http_s_only():
    assert _https_url("https://github.com/x") == "https://github.com/x"
    assert _https_url("http://example.com") == "http://example.com"
    assert _https_url("javascript:alert(1)") is None
    assert _https_url("data:text/html,<h1>x</h1>") is None
    assert _https_url("file:///etc/passwd") is None
    assert _https_url("vbscript:msgbox(1)") is None
    # Case / whitespace bypass attempts
    assert _https_url("  HTTPS://example.com  ") == "HTTPS://example.com"
    assert _https_url("  javascript:alert(1)") is None
    assert _https_url(None) is None
    assert _https_url(123) is None


def test_markdown_report_escapes_cells():
    from services.report_service import generate_markdown_report
    from services.sherlock_service import SiteResult

    evil = SiteResult(
        site_name="Evil|Site",
        url_user="https://example.com/a|b",
        url_main="",
        status="Claimed",
        http_status="200",
        query_time=0.1,
    )
    payload = generate_markdown_report("alice", [evil], [], [])
    assert payload is not None
    text = payload.decode("utf-8")
    assert "Evil\\|Site" in text
    assert "a\\|b" in text


def test_email_markdown_report_escapes_cells():
    from services.report_service import generate_email_markdown_report

    rows = [
        {
            "name": "Bad|Platform",
            "domain": "example.com",
            "exists": True,
            "rateLimit": False,
            "unavailable": False,
            "others": {"message": "hello|world\nnewline"},
        }
    ]
    payload = generate_email_markdown_report("a@b.com", rows)
    text = payload.decode("utf-8")
    assert "Bad\\|Platform" in text
    assert "hello\\|world newline" in text


def test_pdf_renders_evil_username():
    from services.report_service import generate_pdf_dossier
    from services.sherlock_service import SiteResult

    evil = SiteResult(
        site_name="x<y",
        url_user="https://example.com",
        url_main="",
        status="Claimed",
        http_status="200",
        query_time=0.1,
    )
    payload = generate_pdf_dossier("a&b<evil>", [evil], [], [])
    # Must not raise ParaParseError; None only when reportlab missing.
    assert payload is None or isinstance(payload, (bytes, bytearray))


def test_pdf_rejects_javascript_links():
    from services.report_service import _https_url

    assert _https_url("javascript:alert(document.domain)") is None


def test_update_strictness():
    from services.update_service import UpdateService

    service = UpdateService()
    base = {
        "build_number": 99999,
        "version": "9.9.9",
        "type": "update",
        "title": "Hi",
        "release_notes": "notes",
        "mandatory": "false",  # truthy string must NOT force mandatory
        "github_url": "javascript:alert(1)",
        "playstore_url": "http://insecure.example.com",
        "action_url": "data:text/html,x",
    }

    from unittest.mock import AsyncMock, MagicMock, patch

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = dict(base)
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=mock_resp)
    with patch("services.http_client.get_client", return_value=fake_client):
        result = asyncio.run(service.check_for_update())

    assert result is not None
    assert result["mandatory"] is False
    # Non-https URLs fall back to defaults / None
    assert result["github_url"].startswith("https://")
    assert result["playstore_url"].startswith("https://")
    assert result["action_url"] is None


def test_update_type_allowlist_and_truncate():
    from unittest.mock import AsyncMock, MagicMock, patch

    from services.update_service import UpdateService

    service = UpdateService()
    mock_data = {
        "build_number": 99999,
        "version": {"not": "a string"},
        "type": "evil-type",
        "title": ["list", "title"],
        "release_notes": "x" * 20000,
        "mandatory": True,
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_data
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=mock_resp)
    with patch("services.http_client.get_client", return_value=fake_client):
        result = asyncio.run(service.check_for_update())

    assert result is not None
    assert result["type"] == "update"
    assert result["version"] != "{'not': 'a string'}"
    assert len(result["release_notes"]) <= 10000
    assert result["mandatory"] is True


def test_cached_enrich_clear_and_email_buckets():
    """open_cached_result clears stale enrichments and restores all counts."""
    from unittest.mock import MagicMock

    from core.state import state
    from main import AppController

    controller = AppController(MagicMock())
    state.enrichments.clear()
    state.enrichments["https://stale.example.com"] = {"name": "Stale"}

    state.set_cached_result(
        "username",
        "bob",
        {
            "found": [],
            "not_found": [],
            "errors": [],
            "total": 10,
            "enrichments": {"https://fresh.example.com": {"name": "Fresh"}},
        },
    )
    assert controller.open_cached_result("bob", "username") is True
    assert "https://stale.example.com" not in state.enrichments
    assert state.enrichments["https://fresh.example.com"] == {"name": "Fresh"}

    state.set_cached_result(
        "email",
        "a@b.com",
        {
            "email_results": [
                {"name": "A", "exists": True},
                {"name": "B", "exists": False},
                {"name": "C", "rateLimit": True},
                {"name": "D", "unavailable": True},
            ],
            "total": 4,
        },
    )
    assert controller.open_cached_result("a@b.com", "email") is True
    assert state.email_found_count == 1
    assert state.email_not_found_count == 1
    assert state.email_rate_limited_count == 1
    assert state.email_unavailable_count == 1
    assert state.email_total_modules == 4


def test_xmind_dup_site_keys_distinct(tmp_path):
    """Duplicate site names must not collide in the XMind topic map."""
    from services.report_service import generate_xmind_case
    from services.sherlock_service import SiteResult

    dupes = [
        SiteResult(
            site_name="GitHub",
            url_user="https://github.com/alice",
            url_main="",
            status="Claimed",
            http_status="200",
        ),
        SiteResult(
            site_name="GitHub",
            url_user="https://github.com/alice2",
            url_main="",
            status="Claimed",
            http_status="200",
        ),
    ]
    out = tmp_path / "case.xmind"
    result = generate_xmind_case("alice", dupes, output_path=out)
    # None only when xmind missing; otherwise the zip must exist and both
    # account URLs must be embedded (no topic overwritten by key collision).
    if result is not None:
        data = out.read_bytes()
        assert data[:2] == b"PK"  # zip container magic
        assert b"github.com/alice" in data
        assert b"github.com/alice2" in data
