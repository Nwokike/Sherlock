"""Unit tests for SherlockService with Maigret async OSINT engine."""

import asyncio
from unittest.mock import MagicMock

import pytest

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
        # maigret 0.6.6 ships ~5,200 enabled sites (was ~2,600 in 0.6.5)
        assert count > 4000
        assert state.sites_total == count
        assert len(state.sites_cache) == count

    asyncio.run(scenario())


@pytest.mark.live
def test_sherlock_service_search_execution():
    """Hits the real GitHub over the network — excluded in CI via -m "not live"."""
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


# ── Wave B: typed errors, badges, recursion (docs/dependency-study.md) ──


class TestErrorClassification:
    """classify_error maps maigret CheckError vocabulary → badge classes."""

    def test_bot_types(self):
        from services.sherlock_service import classify_error

        for et in (
            "Captcha",
            "Bot protection",
            "Access denied",
            "Request blocked",
            "Just a moment: bot redirect challenge",
            "Login required",
        ):
            assert classify_error(et) == "bot", et

    def test_dead_rate_error_classes(self):
        from services.sherlock_service import classify_error

        assert classify_error("Connecting failure") == "dead"
        assert classify_error("Connecting failure (DNS)") == "dead"
        assert classify_error("Rate limited") == "rate"
        assert classify_error("HTTP 500") == "error"

    def test_generic_failure_on_protected_site_is_bot(self):
        from services.sherlock_service import classify_error

        assert classify_error("Unknown", ["cf_js_challenge"]) == "bot"
        assert classify_error("Unknown", []) == "error"
        assert classify_error(None, ["tls_fingerprint"]) == ""


class TestNotifyBadgeBridge:
    """_MaigretQueryNotify bridges CheckError + protection → WAF/typed fields."""

    def test_bot_error_renders_waf_with_hint(self):
        from maigret.errors import CheckError
        from maigret.result import MaigretCheckResult, MaigretCheckStatus
        from maigret.sites import MaigretSite

        from services.sherlock_service import (
            SearchProgress,
            _MaigretQueryNotify,
        )

        site = MaigretSite(
            "GitHub",
            {
                "url_main": "https://github.com",
                "tags": ["coding"],
                "protection": ["tls_fingerprint"],
            },
        )

        async def scenario():
            progress = SearchProgress(username="u", total_sites=1)
            notify = _MaigretQueryNotify(
                total=1,
                cancel_event=asyncio.Event(),
                progress=progress,
                on_progress=None,
                sites_lookup={"GitHub": site},
            )
            result = MaigretCheckResult(
                "u",
                "GitHub",
                "https://github.com/u",
                MaigretCheckStatus.UNKNOWN,
                error=CheckError("Bot protection", "Cloudflare"),
            )
            notify.update(result)
            return progress

        progress = asyncio.run(scenario())
        assert len(progress.errors) == 1
        sr = progress.errors[0]
        # Bot-class failures light up the WAF status result_card styles
        assert sr.status == "WAF"
        assert sr.badge == "bot"
        assert sr.error_type == "Bot protection"
        assert sr.error_hint  # solution_of() advice text
        assert sr.protection == ["tls_fingerprint"]

    def test_keyword_found_flag(self):
        from maigret.result import (
            KeywordMatchStatus,
            MaigretCheckResult,
            MaigretCheckStatus,
        )

        from services.sherlock_service import (
            SearchProgress,
            _MaigretQueryNotify,
        )

        async def scenario():
            progress = SearchProgress(username="u", total_sites=1)
            notify = _MaigretQueryNotify(
                total=1,
                cancel_event=asyncio.Event(),
                progress=progress,
            )
            notify.update(
                MaigretCheckResult(
                    "u",
                    "Reddit",
                    "https://reddit.com/u",
                    MaigretCheckStatus.CLAIMED,
                    keyword_match_status=KeywordMatchStatus.KEYWORD_FOUND,
                )
            )
            return progress

        progress = asyncio.run(scenario())
        assert progress.found[0].keyword_hit is True


class TestRecursiveTargetExtraction:
    """_collect_recursive_targets: dedupe, typing, caps (depth-2 by design)."""

    @staticmethod
    def _stub_db():
        class StubDB:
            def extract_ids_from_url(self, url):
                return {"secondaryuser": "username"} if "github.com" in url else {}

        return StubDB()

    def test_extracts_typed_ids_and_url_ids(self):
        from services.sherlock_service import _collect_recursive_targets

        containers = {
            "alice": {
                "VK": {
                    "ids_usernames": {"vkuser": "vk_id"},
                    "ids_links": ["https://github.com/alice"],
                }
            },
            "bob": {"Reddit": {"ids_links": []}},
        }
        got = _collect_recursive_targets(
            containers, self._stub_db(), ["alice", "bob"], cap=20
        )
        assert got == {"vkuser": "vk_id", "secondaryuser": "username"}

    def test_dedupes_against_already_scanned(self):
        from services.sherlock_service import _collect_recursive_targets

        containers = {
            "alice": {"X": {"ids_usernames": {"alice": "username"}}},
        }
        got = _collect_recursive_targets(
            containers, self._stub_db(), ["Alice"], cap=20
        )
        assert got == {}

    def test_cap_bounds_secondary_targets(self):
        from services.sherlock_service import _collect_recursive_targets

        containers = {
            f"s{i}": {"X": {"ids_usernames": {f"u{i}": "username"}}}
            for i in range(30)
        }
        got = _collect_recursive_targets(containers, self._stub_db(), [], cap=5)
        assert len(got) == 5

    def test_empty_containers_yield_nothing(self):
        from services.sherlock_service import _collect_recursive_targets

        assert _collect_recursive_targets({}, self._stub_db(), []) == {}
        assert (
            _collect_recursive_targets({"a": {}}, self._stub_db(), ["a"]) == {}
        )
