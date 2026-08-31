"""Profile enrichment service — wraps socid-extractor.

socid-extractor extracts structured metadata (avatar, bio, display name,
location, follower count, cross-platform social links, etc.) from profile
page HTML across 164 supported site schemes.
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
        """Extract profile metadata from raw HTML/JSON page content."""
        if not _SOCID_AVAILABLE:
            return {}
        try:
            result = _extract(page_html)
            return result if result else {}
        except Exception as exc:
            logger.warning("socid-extractor extraction failed: %s", exc)
            return {}

    def get_mutations(self, url: str) -> list[tuple[str, dict]]:
        """Get alternative API endpoint URLs for a profile URL."""
        if not _SOCID_AVAILABLE:
            return []
        try:
            return _mutate_url(url) or []
        except Exception as exc:
            logger.warning("URL mutation failed for %s: %s", url, exc)
            return []

    async def enrich_url(self, url: str, timeout: int = 5) -> dict:
        """Fetch a URL and extract profile metadata from the response."""
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
            logger.warning("Profile enrichment failed for %s: %s", url, exc)

        return {}

    async def enrich_url_with_mutations(self, url: str, timeout: int = 5) -> dict:
        """Fetch a URL and its API mutations, merging all extracted data."""
        if not _SOCID_AVAILABLE:
            return {}

        result = await self.enrich_url(url, timeout=timeout)

        mutations = self.get_mutations(url)
        for api_url, headers in mutations:
            try:
                page_text, status_code = await asyncio.to_thread(
                    _parse, api_url, timeout=timeout, headers=headers
                )
                if status_code and 200 <= status_code < 400 and page_text:
                    mutation_result = _extract(page_text)
                    if mutation_result:
                        for key, value in mutation_result.items():
                            if key == "_extractor":
                                continue
                            if key not in result or not result.get(key):
                                result[key] = value
            except Exception as exc:
                logger.warning("Mutation enrichment failed for %s: %s", api_url, exc)

        return result

    async def batch_enrich(
        self,
        urls: list[str],
        timeout: int = 5,
        on_result: Callable[[str, dict], None] | None = None,
        max_concurrent: int = 5,
        use_mutations: bool = False,
    ) -> dict[str, dict]:
        """Enrich multiple profile URLs concurrently.

        When ``use_mutations`` is True, each URL is enriched via
        ``enrich_url_with_mutations`` (richer data from API endpoints,
        e.g. github.com/user → api.github.com/users/user). Off by
        default to keep the common post-scan batch fast.
        """
        if not _SOCID_AVAILABLE:
            return {}

        if not urls:
            return {}

        results: dict[str, dict] = {}
        failed = 0
        sem = asyncio.Semaphore(max_concurrent)

        enrich_fn = self.enrich_url_with_mutations if use_mutations else self.enrich_url

        async def _enrich_one(url: str):
            nonlocal failed
            async with sem:
                data = await enrich_fn(url, timeout=timeout)
                if data:
                    results[url] = data
                    if on_result:
                        try:
                            on_result(url, data)
                        except Exception:
                            pass
                else:
                    failed += 1

        tasks = [asyncio.create_task(_enrich_one(u)) for u in urls]
        await asyncio.gather(*tasks, return_exceptions=True)
        if failed:
            logger.warning("Enrichment: %d/%d URLs returned no data", failed, len(urls))
        return results
