"""Tests for SherlockService — parse_usernames, SearchProgress accumulation."""

from services.sherlock_service import SearchProgress, SiteResult, parse_usernames


class TestParseUsernames:
    def test_single_username(self):
        assert parse_usernames("john") == ["john"]

    def test_comma_separated(self):
        assert parse_usernames("john,jane") == ["john", "jane"]

    def test_space_separated(self):
        assert parse_usernames("john jane") == ["john", "jane"]

    def test_wildcard_expansion(self):
        result = parse_usernames("user{?}")
        assert "user_" in result
        assert "user-" in result
        assert "user." in result

    def test_comma_with_wildcard(self):
        result = parse_usernames("admin, user{?}")
        assert "admin" in result
        assert "user_" in result

    def test_dedup(self):
        result = parse_usernames("john john jane")
        assert result.count("john") == 1
        assert "jane" in result

    def test_empty_string(self):
        assert parse_usernames("") == []

    def test_whitespace_only(self):
        assert parse_usernames("   ") == []


class TestSearchProgress:
    def test_initial_state(self):
        sp = SearchProgress(username="test")
        assert sp.username == "test"
        assert sp.total_sites == 0
        assert sp.checked_sites == 0
        assert sp.found == []
        assert sp.not_found == []
        assert sp.errors == []
        assert sp.is_running is False
        assert sp.is_cancelled is False

    def test_accumulate_found(self):
        sp = SearchProgress(username="test", total_sites=10)
        sr = SiteResult(
            site_name="GitHub",
            url_main="github.com",
            url_user="github.com/test",
            status="Claimed",
            http_status="200",
        )
        sp.found.append(sr)
        sp.checked_sites += 1
        assert len(sp.found) == 1
        assert sp.checked_sites == 1

    def test_accumulate_not_found(self):
        sp = SearchProgress(username="test", total_sites=10)
        sr = SiteResult(
            site_name="FakeSite",
            url_main="fakesite.com",
            url_user="",
            status="Available",
            http_status="",
        )
        sp.not_found.append(sr)
        assert len(sp.not_found) == 1

    def test_accumulate_errors(self):
        sp = SearchProgress(username="test", total_sites=10)
        sr = SiteResult(
            site_name="Timeout",
            url_main="timeout.com",
            url_user="",
            status="Error",
            http_status="408",
        )
        sp.errors.append(sr)
        assert len(sp.errors) == 1


class TestSiteResult:
    def test_fields(self):
        sr = SiteResult(
            site_name="GitHub",
            url_main="https://github.com",
            url_user="https://github.com/test",
            status="Claimed",
            http_status="200",
            query_time=0.12,
        )
        assert sr.site_name == "GitHub"
        assert sr.status == "Claimed"
        assert sr.query_time == 0.12
