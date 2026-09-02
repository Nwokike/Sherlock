"""Tests for persistent results cache, instant history loading, and scan re-attachment."""

import asyncio
from unittest.mock import MagicMock

from components.active_scan_banner import ActiveScanBanner
from core.constants import MODE_EMAIL, MODE_USERNAME
from core.state import state
from main import AppController
from services.sherlock_service import SearchProgress


def test_active_scan_banner_component():
    clicked = []
    banner = ActiveScanBanner(
        target_query="torvalds",
        search_mode=MODE_USERNAME,
        checked=450,
        total=3302,
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
            "total": 3302,
            "checked": 3302,
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
    orig_progress = SearchProgress(username="alice", total_sites=3302, is_running=True)
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
