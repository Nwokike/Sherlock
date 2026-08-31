"""Profile enrichment service — wraps socid-extractor.

socid-extractor extracts structured metadata (avatar, bio, display name,
location, follower count, cross-platform social links, etc.) from profile
page HTML across 164 supported site schemes.

This service provides two main capabilities:
1. extract(page_html) — parse pre-fetched HTML for profile metadata.
2. enrich_url(url) — fetch a URL and extract profile metadata from it.
3. get_mutations(url) — get alternative API URLs for richer data.

All operations are pure-Python and safe for Android/iOS builds.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

_SOCID_AVAILABLE = False
try:
    from socid_extractor import extract as _extract
    from socid_extractor import parse as _parse
    from socid_extractor import mutate_url as _mutate_url

    _SOCID_AVAILABLE = True
except ImportError:
    pass


class EnrichService:
    """Profile enrichment via socid-extractor."""

    @property
    def is_available(self) -> bool:
        return _SOCID_AVAILABLE

    def extract(self, page_html: str) -> dict:
        """Extract profile metadata from raw HTML/JSON page content.

        Returns a dict of extracted fields (uid, username, fullname, bio,
        image, location, follower_count, created_at, links, etc.) or an
        empty dict if no scheme matched.

        The returned dict includes '_extractor' with the scheme name.
        """
        if not _SOCID_AVAILABLE:
            return {}
        try:
            result = _extract(page_html)
            return result if result else {}
        except Exception as exc:
            logger.debug("socid-extractor extraction failed: %s", exc)
            return {}

    def get_mutations(self, url: str) -> list[tuple[str, dict]]:
        """Get alternative API endpoint URLs for a profile URL.

        Some sites expose richer data at API endpoints that differ from
        the public profile URL. This returns a list of (api_url, headers)
        tuples that can be fetched for deeper extraction.

        Example: github.com/user → api.github.com/users/user
        """
        if not _SOCID_AVAILABLE:
            return []
        try:
            return _mutate_url(url) or []
        except Exception as exc:
            logger.debug("URL mutation failed for %s: %s", url, exc)
            return []

    async def enrich_url(self, url: str, timeout: int = 5) -> dict:
        """Fetch a URL and extract profile metadata from the response.

        Uses socid-extractor's built-in parse() which makes an HTTP GET
        request with browser-like headers and then runs extract() on the
        response body.

        Returns extracted fields dict or empty dict on failure.
        """
        if not _SOCID_AVAILABLE:
            return {}

        try:
            page_text, status_code = await asyncio.to_thread(
                _parse, url, timeout=timeout
            )
            if status_code and 200 <= status_code < 400 and page_text:
                result = _extract(page_text)
                return result if result else {}
        except Exception as exc:
            logger.debug("Profile enrichment failed for %s: %s", url, exc)

        return {}

    async def enrich_url_with_mutations(self, url: str, timeout: int = 5) -> dict:
        """Fetch a URL and its API mutations, merging all extracted data.

        First tries the direct URL, then fetches any API endpoint
        mutations (e.g. GitHub API, Twitter GraphQL) for richer metadata.
        Merges results with mutation data taking precedence for fields
        that weren't found in the direct extraction.
        """
        if not _SOCID_AVAILABLE:
            return {}

        # Start with direct URL extraction
        result = await self.enrich_url(url, timeout=timeout)

        # Try mutations for richer data
        mutations = self.get_mutations(url)
        for api_url, headers in mutations:
            try:
                page_text, status_code = await asyncio.to_thread(
                    _parse, api_url, timeout=timeout, headers=headers
                )
                if status_code and 200 <= status_code < 400 and page_text:
                    mutation_result = _extract(page_text)
                    if mutation_result:
                        # Merge: keep existing non-empty values, add new ones
                        for key, value in mutation_result.items():
                            if key == "_extractor":
                                continue
                            if key not in result or not result.get(key):
                                result[key] = value
            except Exception as exc:
                logger.debug("Mutation enrichment failed for %s: %s", api_url, exc)

        return result

    async def batch_enrich(
        self,
        urls: list[str],
        timeout: int = 5,
        on_result: Callable[[str, dict], None] | None = None,
        max_concurrent: int = 5,
    ) -> dict[str, dict]:
        """Enrich multiple profile URLs concurrently.

        Returns {url: extracted_fields} for all URLs that yielded data.
        Optionally calls on_result(url, fields) as each completes.
        """
        if not _SOCID_AVAILABLE:
            return {}

        results: dict[str, dict] = {}
        sem = asyncio.Semaphore(max_concurrent)

        async def _enrich_one(url: str):
            async with sem:
                data = await self.enrich_url(url, timeout=timeout)
                if data:
                    results[url] = data
                    if on_result:
                        try:
                            on_result(url, data)
                        except Exception:
                            pass

        tasks = [asyncio.create_task(_enrich_one(u)) for u in urls]
        await asyncio.gather(*tasks, return_exceptions=True)
        return results
