"""Tests for persistent results cache, instant history loading, and scan re-attachment."""

import asyncio
from unittest.mock import MagicMock

import pytest

from components.active_scan_banner import ActiveScanBanner
from core.constants import MODE_EMAIL, MODE_USERNAME
from core.state import state
from main import AppController
from services.sherlock_service import SearchProgress


@pytest.fixture(autouse=True)
def _restore_global_state():
    """Snapshot every state field this file's paths touch around each test.

    Covers the test bodies plus everything open_cached_result() mutates
    (main.py: enrichments clear/update, email buckets, last_results,
    progress_version) so no field leaks into the next test under any
    file order. Restore goes through setattr (never __dict__ surgery):
    AppState is @ft.observable and __dict__ surgery wipes its wrapper
    internals. Collections restore in place to keep their wrappers.
    """
    if state.results_cache is None:
        state.results_cache = {}
    if state.enrichments is None:
        state.enrichments = {}
    if state.last_results is None:
        state.last_results = {}
    saved = {
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
    saved_results_cache = dict(state.results_cache)
    saved_enrichments = dict(state.enrichments)
    saved_last_results = dict(state.last_results)
    saved_email_results = list(state.email_results) if state.email_results else []
    yield
    for key, value in saved.items():
        setattr(state, key, value)
    state.results_cache.clear()
    state.results_cache.update(saved_results_cache)
    state.enrichments.clear()
    state.enrichments.update(saved_enrichments)
    state.last_results.clear()
    state.last_results.update(saved_last_results)
    if state.email_results is None:
        state.email_results = []
    state.email_results[:] = saved_email_results


def test_active_scan_banner_component():
    clicked = []
    banner = ActiveScanBanner(
        target_query="torvalds",
        search_mode=MODE_USERNAME,
        checked=450,
        total=5203,
        on_tap=lambda: clicked.append(1),
    )
    assert banner is not None
    assert banner.on_click is not None
    banner.on_click(None)
    assert clicked == [1]


def test_results_cache_lru_cap():
    state.results_cache.clear()
    for i in range(35):
        state.set_cached_result(
            MODE_USERNAME, f"user_{i}", {"query": f"user_{i}", "total": 100}
        )

    # Should be capped at 30 items
    assert len(state.results_cache) == 30
    # Oldest (user_0 .. user_4) should have been evicted
    assert state.get_cached_result(MODE_USERNAME, "user_0") is None
    assert state.get_cached_result(MODE_USERNAME, "user_34") is not None


def test_open_cached_username_result(fake_page):
    controller = AppController(fake_page)
    results_shown = []
    controller._controller_methods = MagicMock()
    controller._controller_methods.show_results = lambda: results_shown.append(1)

    state.results_cache.clear()
    state.set_cached_result(
        MODE_USERNAME,
        "alice",
        {
            "query": "alice",
            "mode": MODE_USERNAME,
            "total": 5203,
            "checked": 5203,
            "found": [
                {
                    "site_name": "GitHub",
                    "url_main": "https://github.com",
                    "url_user": "https://github.com/alice",
                    "status": "Claimed",
                    "http_status": "200",
                    "query_time": 0.45,
                    "tags": ["coding"],
                }
            ],
            "not_found": [],
            "errors": [],
            "enrichments": {"https://github.com/alice": {"name": "Alice Smith"}},
        },
    )

    success = controller.open_cached_result("alice", MODE_USERNAME)
    assert success is True
    assert state.search_mode == MODE_USERNAME
    assert state.current_username == "alice"
    assert state.last_results_username == "alice"
    assert "GitHub" in state.last_results
    assert len(state.search_progress.found) == 1
    assert state.search_progress.found[0].site_name == "GitHub"
    assert state.search_progress.is_running is False
    assert state.is_searching is False
    assert "https://github.com/alice" in state.enrichments
    assert results_shown == [1]


def test_open_cached_email_result(fake_page):
    controller = AppController(fake_page)
    results_shown = []
    controller._controller_methods = MagicMock()
    controller._controller_methods.show_results = lambda: results_shown.append(1)

    state.results_cache.clear()
    state.set_cached_result(
        MODE_EMAIL,
        "bob@example.com",
        {
            "query": "bob@example.com",
            "mode": MODE_EMAIL,
            "total": 121,
            "checked": 121,
            "email_results": [
                {
                    "name": "adobe",
                    "domain": "adobe.com",
                    "method": "password recovery",
                    "exists": True,
                    "emailrecovery": "b***@example.com",
                }
            ],
        },
    )

    success = controller.open_cached_result("bob@example.com", MODE_EMAIL)
    assert success is True
    assert state.search_mode == MODE_EMAIL
    assert state.current_username == "bob@example.com"
    assert state.email_results_address == "bob@example.com"
    assert len(state.email_results) == 1
    assert state.email_results[0]["name"] == "adobe"
    assert len(state.search_progress.found) == 1
    assert state.search_progress.is_running is False
    assert state.is_searching is False
    assert results_shown == [1]


def test_open_cached_result_non_existent(fake_page):
    controller = AppController(fake_page)
    state.results_cache.clear()
    assert controller.open_cached_result("non_existent_user", MODE_USERNAME) is False


def test_smart_reattach_to_ongoing_search(fake_page):
    controller = AppController(fake_page)
    controller._controller_methods = MagicMock()
    results_shown = []
    controller._controller_methods.show_results = lambda: results_shown.append(1)

    # Simulate ongoing search
    state.is_searching = True
    state.current_username = "alice"
    state.search_mode = MODE_USERNAME
    orig_progress = SearchProgress(username="alice", total_sites=5203, is_running=True)
    state.search_progress = orig_progress

    # Mock service so if search was actually executed, it would fail
    controller.sherlock_service = MagicMock()
    controller.sherlock_service.search = MagicMock()

    async def scenario():
        # Start search for exact same username
        await controller.start_search("alice")
        # Should not have called sherlock_service.search again
        assert controller.sherlock_service.search.call_count == 0
        # Progress object should be the exact same active instance
        assert state.search_progress is orig_progress
        assert state.is_searching is True
        assert results_shown == [1]

    asyncio.run(scenario())
