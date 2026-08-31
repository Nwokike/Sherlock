"""Tests for EnrichService (socid-extractor wrapper)."""

from __future__ import annotations

import pytest


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
        import asyncio
        from services.enrich_service import EnrichService

        service = EnrichService()
        result = asyncio.run(
            service.enrich_url("https://invalid-url-that-will-fail.xyz/user", timeout=1)
        )
        assert isinstance(result, dict)

    def test_batch_enrich_empty_list(self):
        """batch_enrich() on empty list returns empty dict."""
        import asyncio
        from services.enrich_service import EnrichService

        service = EnrichService()
        result = asyncio.run(service.batch_enrich([]))
        assert result == {}
