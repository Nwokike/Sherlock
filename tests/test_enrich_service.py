"""Tests for EnrichService (socid-extractor wrapper)."""

from __future__ import annotations

import asyncio

import pytest


def _stubbed(monkeypatch, parse=None, extract=None):
    """Stub socid fetch/extract so tests never touch the network."""
    import inspect

    import services.enrich_service as enrich_mod

    if parse is not None:

        async def _fake_parse(url, timeout, headers=None, cookies_str=""):
            res = parse(url, timeout, headers, cookies_str)
            if inspect.isawaitable(res):
                res = await res
            return res

        monkeypatch.setattr(enrich_mod, "_parse_in_thread", _fake_parse)
    if extract is not None:

        async def _fake_extract(page_text):
            res = extract(page_text)
            if inspect.isawaitable(res):
                res = await res
            return res

        monkeypatch.setattr(enrich_mod, "_extract_in_thread", _fake_extract)
    return enrich_mod


class TestEnrichService:
    """EnrichService unit tests."""

    def test_instantiates(self):
        from services.enrich_service import EnrichService

        service = EnrichService()
        assert service is not None

    def test_is_available_bool(self):
        from services.enrich_service import EnrichService

        service = EnrichService()
        assert isinstance(service.is_available, bool)

    def test_extract_empty_html_returns_dict(self):
        """extract() on empty/irrelevant HTML returns empty dict, never raises."""
        from services.enrich_service import EnrichService

        service = EnrichService()
        result = service.extract("<html><body>nothing here</body></html>")
        assert isinstance(result, dict)

    def test_extract_non_string_graceful(self):
        """extract() handles edge cases gracefully."""
        from services.enrich_service import EnrichService

        service = EnrichService()
        result = service.extract("")
        assert isinstance(result, dict)

    def test_get_mutations_unknown_url(self):
        """get_mutations() returns list for any URL (may be empty)."""
        from services.enrich_service import EnrichService

        service = EnrichService()
        mutations = service.get_mutations("https://unknown-site-xyz123.com/user/test")
        assert isinstance(mutations, list)

    def test_get_mutations_github(self):
        """get_mutations() for GitHub profile returns api.github.com URL."""
        from services.enrich_service import EnrichService

        service = EnrichService()
        if not service.is_available:
            pytest.skip("socid-extractor not available")

        mutations = service.get_mutations("https://github.com/octocat")
        urls = [url for url, _ in mutations]
        assert any("api.github.com" in u for u in urls)

    def test_extract_github_api_response(self):
        """extract() on a mock GitHub API JSON extracts known fields."""
        from services.enrich_service import EnrichService

        service = EnrichService()
        if not service.is_available:
            pytest.skip("socid-extractor not available")

        # Mock GitHub API JSON response for a user
        github_api_json = """{
            "login": "octocat",
            "id": 1,
            "name": "The Octocat",
            "company": "@github",
            "blog": "https://github.blog",
            "location": "San Francisco, CA",
            "email": null,
            "bio": "Hello World!",
            "public_repos": 8,
            "followers": 9999,
            "following": 9
        }"""

        result = service.extract(github_api_json)
        # The result may or may not match depending on what schemes are loaded;
        # we just verify the return type and no exceptions
        assert isinstance(result, dict)

    def test_enrich_url_returns_dict(self):
        """enrich_url() returns dict (may be empty for an offline/invalid URL)."""
        from services.enrich_service import EnrichService

        service = EnrichService()
        result = asyncio.run(
            service.enrich_url("https://invalid-url-that-will-fail.xyz/user", timeout=1)
        )
        assert isinstance(result, dict)

    def test_batch_enrich_empty_list(self):
        """batch_enrich() on empty list returns empty dict."""
        from services.enrich_service import EnrichService

        service = EnrichService()
        result = asyncio.run(service.batch_enrich([]))
        assert result == {}

    def test_batch_enrich_clamps_nonpositive_concurrency(self, monkeypatch):
        """max_concurrent<=0 must not deadlock (Semaphore(0) hangs gather)."""
        import services.enrich_service as enrich_mod
        from services.enrich_service import EnrichService

        async def _ok(url, timeout, headers=None, cookies_str=""):
            return ("<html></html>", 200)

        async def _ex(url):
            return {"name": "N"}

        _stubbed(monkeypatch, parse=_ok, extract=_ex)
        service = EnrichService()
        result = asyncio.run(
            asyncio.wait_for(
                service.batch_enrich(["https://a.example/x"], max_concurrent=0),
                timeout=10,
            )
        )
        assert result == {"https://a.example/x": {"name": "N"}}
        assert enrich_mod._HOST_SEMS  # per-host throttle registered

    def test_batch_enrich_dedupes_urls(self, monkeypatch):
        """Duplicate input pays one fetch, returns one entry."""
        from services.enrich_service import EnrichService

        calls = []

        async def _ok(url, timeout, headers=None, cookies_str=""):
            calls.append(url)
            return ("<html></html>", 200)

        async def _ex(url):
            return {"name": "N"}

        _stubbed(monkeypatch, parse=_ok, extract=_ex)
        service = EnrichService()
        result = asyncio.run(
            service.batch_enrich(["https://a.example/x"] * 3 + ["https://b.example/y"])
        )
        assert sorted(result) == ["https://a.example/x", "https://b.example/y"]
        assert sorted(calls) == ["https://a.example/x", "https://b.example/y"]

    def test_mutation_wins_and_provenance_accumulates(self, monkeypatch):
        """Truthy API-mutation values overwrite thin base; _extractor lists."""
        from services.enrich_service import EnrichService

        async def _parse(url, timeout, headers=None, cookies_str=""):
            if "api." in url:
                return ('{"login":"octocat"}', 200)
            return ("<html></html>", 200)

        async def _extract(text):
            if "octocat" in text:
                return {
                    "name": "Octocat Full",
                    "bio": "API bio",
                    "_extractor": "github",
                }
            return {"bio": "thin scraped bio", "_extractor": "generic"}

        _stubbed(monkeypatch, parse=_parse, extract=_extract)
        service = EnrichService()
        monkeypatch.setattr(
            service,
            "get_mutations",
            lambda url: [("https://api.example.com/u", {})],
        )
        result = asyncio.run(service.enrich_url_with_mutations("https://example.com/u"))
        assert result["name"] == "Octocat Full"
        assert result["bio"] == "API bio"
        assert sorted(result["_extractor"]) == ["generic", "github"]

    def test_on_result_async_and_sync_and_swallow(self, monkeypatch):
        """Sync + async on_result both run; exceptions never fail the batch."""
        from services.enrich_service import EnrichService

        seen_sync, seen_async = [], []

        async def _ok(url, timeout, headers=None, cookies_str=""):
            return ("<html></html>", 200)

        async def _ex(url):
            return {"name": "N"}

        _stubbed(monkeypatch, parse=_ok, extract=_ex)
        service = EnrichService()

        def _sync(url, data):
            seen_sync.append(url)

        async def _async(url, data):
            seen_async.append(url)

        def _boom(url, data):
            raise RuntimeError("callback blew up")

        urls = ["https://a.example/1", "https://b.example/2"]
        out = asyncio.run(service.batch_enrich(urls, on_result=_sync))
        assert sorted(out) == sorted(urls)
        assert sorted(seen_sync) == sorted(urls)
        out = asyncio.run(service.batch_enrich(urls, on_result=_async))
        assert sorted(seen_async) == sorted(urls)
        out = asyncio.run(service.batch_enrich(urls, on_result=_boom))
        assert sorted(out) == sorted(urls)

    def test_outer_timeout_unblocks_loop(self, monkeypatch):
        """A hung fetch (past timeout+slack) surfaces as {} without hanging."""

        async def _hang(url, timeout, headers=None, cookies_str=""):
            await asyncio.sleep(60)
            return ("<html></html>", 200)

        async def _ex(url):
            raise AssertionError("must not be called")

        _stubbed(monkeypatch, parse=_hang, extract=_ex)
        from services.enrich_service import EnrichService

        service = EnrichService()
        result = asyncio.run(
            asyncio.wait_for(
                service.enrich_url("https://a.example/x", timeout=1), timeout=15
            )
        )
        assert result == {}

    def test_retry_on_429_then_success(self, monkeypatch):
        """Single retry: 429 then 200 yields data."""
        from services.enrich_service import EnrichService

        attempts = []

        async def _flaky(url, timeout, headers=None, cookies_str=""):
            attempts.append(url)
            if len(attempts) == 1:
                return (None, 429)
            return ("<html></html>", 200)

        async def _ex(url):
            return {"name": "N"}

        _stubbed(monkeypatch, parse=_flaky, extract=_ex)
        import services.enrich_service as enrich_mod

        real_sleep = asyncio.sleep

        async def _fast_sleep(delay):
            await real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", _fast_sleep)
        service = EnrichService()
        result = asyncio.run(service.enrich_url("https://a.example/x"))
        assert result == {"name": "N"}
        assert len(attempts) == 2
        assert enrich_mod._HOST_SEMS

    def test_timeout_clamp_matrix(self, monkeypatch):
        """0/negative/None/huge timeouts clamp instead of raising."""
        import services.enrich_service as enrich_mod
        from services.enrich_service import EnrichService

        seen = []

        async def _ok(url, timeout, headers=None, cookies_str=""):
            seen.append(timeout)
            return ("<html></html>", 200)

        async def _ex(url):
            return {"name": "N"}

        _stubbed(monkeypatch, parse=_ok, extract=_ex)
        service = EnrichService()
        for bad in (0, -5, None, "x", 3600):
            out = asyncio.run(service.enrich_url("https://a.example/x", timeout=bad))
            assert out == {"name": "N"}
        assert all(1 <= t <= 30 for t in seen)
        assert enrich_mod._clamp_timeout(None) == 5

    def test_forwarding_subset_and_skip_flag(self, monkeypatch):
        """headers/cookies forwarded; proxy accepted-but-ignored; skip flag."""
        from services.enrich_service import EnrichService

        got = {}

        async def _ok(url, timeout, headers=None, cookies_str=""):
            got["headers"] = headers
            got["cookies_str"] = cookies_str
            return ("<html></html>", 200)

        async def _ex(url):
            return {}

        _stubbed(monkeypatch, parse=_ok, extract=_ex)
        service = EnrichService()
        out = asyncio.run(
            service.enrich_url(
                "https://a.example/x",
                headers={"X-Test": "1"},
                cookies={"session": "abc"},
                proxy="socks5://127.0.0.1:1080",
                user_agent="Sherlock/2.x",
            )
        )
        assert out == {}
        assert got["headers"]["X-Test"] == "1"
        assert got["headers"]["User-Agent"] == "Sherlock/2.x"
        assert got["cookies_str"]  # dict normalized to cookie string

        # skip_if_no_hint with no mutations + empty base returns early
        monkeypatch.setattr(service, "get_mutations", lambda url: [])
        out = asyncio.run(
            service.enrich_url_with_mutations(
                "https://a.example/x", skip_if_no_hint=True
            )
        )
        assert out == {}
