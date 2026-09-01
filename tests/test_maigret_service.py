"""Unit tests for SherlockService with Maigret async OSINT engine."""

import asyncio
from unittest.mock import MagicMock

from core.state import state
from services.sherlock_service import (
    SearchProgress,
    SherlockService,
    _MaigretQueryNotify,
    _resolve_local_db,
    parse_usernames,
)


def test_resolve_local_db():
    db_path = _resolve_local_db()
    assert db_path is not None
    assert "data.json" in db_path


def test_parse_usernames():
    assert parse_usernames("alice, bob") == ["alice", "bob"]
    assert parse_usernames("alice bob") == ["alice", "bob"]
    assert parse_usernames("user{?}") == ["user_", "user-", "user."]


def test_query_notify_accumulation():
    progress = SearchProgress(username="testuser", total_sites=3, is_running=True)
    cancel_event = asyncio.Event()
    ticks = []

    notify = _MaigretQueryNotify(
        total=3,
        cancel_event=cancel_event,
        progress=progress,
        on_progress=lambda p: ticks.append(p.checked_sites),
    )

    # Mock Claimed result
    claimed_res = MagicMock()
    claimed_res.site_name = "GitHub"
    claimed_res.site_url_user = "https://github.com/testuser"
    claimed_res.status.name = "CLAIMED"
    claimed_res.query_time = 0.42
    claimed_res.context = None
    claimed_res.tags = ["coding"]
    claimed_res.ids_data = None

    notify.update(claimed_res)
    assert progress.checked_sites == 1
    assert len(progress.found) == 1
    assert progress.found[0].site_name == "GitHub"
    assert progress.found[0].status == "Claimed"

    # Mock Available result
    avail_res = MagicMock()
    avail_res.site_name = "Reddit"
    avail_res.site_url_user = "https://reddit.com/user/testuser"
    avail_res.status.name = "AVAILABLE"
    avail_res.query_time = 0.2
    avail_res.context = None
    avail_res.tags = ["social"]
    avail_res.ids_data = None

    notify.update(avail_res)
    assert progress.checked_sites == 2
    assert len(progress.not_found) == 1

    # Mock Unknown error result
    err_res = MagicMock()
    err_res.site_name = "BlockedSite"
    err_res.site_url_user = "https://blockedsite.com/testuser"
    err_res.status.name = "UNKNOWN"
    err_res.query_time = None
    err_res.context = "WAF challenge"
    err_res.tags = []
    err_res.ids_data = None

    notify.update(err_res)
    assert progress.checked_sites == 3
    assert len(progress.errors) == 1
    assert progress.errors[0].status == "Error"


def test_sherlock_service_load_sites():
    async def scenario():
        state.nsfw_enabled = False
        state.ignore_exclusions = False
        svc = SherlockService()
        count = await svc.load_sites(force=True)
        assert count > 2000
        assert state.sites_total == count
        assert len(state.sites_cache) == count

    asyncio.run(scenario())


def test_sherlock_service_search_execution():
    async def scenario():
        svc = SherlockService()
        await svc.load_sites()

        state.selected_sites = ["GitHub"]
        progress_ticks = []

        def on_progress(p):
            progress_ticks.append(p.checked_sites)

        res = await svc.search("torvalds", on_progress=on_progress, timeout=10)
        assert res is not None
        assert res.username == "torvalds"
        assert res.checked_sites == 1
        assert len(res.found) >= 1
        assert res.found[0].site_name == "GitHub"
        assert res.found[0].status == "Claimed"

    asyncio.run(scenario())
