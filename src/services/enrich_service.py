"""Profile enrichment service — wraps socid-extractor.

socid-extractor extracts structured metadata (avatar, bio, display name,
location, follower count, cross-platform social links, etc.) from profile
page HTML across 164 supported site schemes.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from urllib.parse import urlparse

import anyio

from core.tasks import spawn

logger = logging.getLogger(__name__)

_SOCID_AVAILABLE = False
try:
    from socid_extractor import extract as _extract
    from socid_extractor import mutate_url as _mutate_url
    from socid_extractor import parse as _parse

    _SOCID_AVAILABLE = True
except ImportError:
    pass

# Shared bound on parse-thread offload (P5-4): caps total worker threads
# across overlapping enrichment jobs no matter how many caller semaphores
# are in flight.
_PARSE_LIMITER = anyio.CapacityLimiter(12)

_TIMEOUT_MIN, _TIMEOUT_MAX = 1, 30
_OUTER_SLACK = 5  # seconds over the clamped timeout for the outer wait_for
_HOST_LIMIT = 2  # max concurrent fetches per host
_RETRYABLE = {429, 500, 502, 503, 504}

_HOST_SEMS: dict[str, asyncio.Semaphore] = {}


def _clamp_timeout(timeout: object, default: int = 5) -> int:
    try:
        t = int(timeout)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return default
    return max(_TIMEOUT_MIN, min(_TIMEOUT_MAX, t))


def _host_sem(url: str) -> asyncio.Semaphore:
    host = urlparse(url).netloc.lower() or "_default"
    sem = _HOST_SEMS.get(host)
    if sem is None:
        sem = asyncio.Semaphore(_HOST_LIMIT)
        _HOST_SEMS[host] = sem
    return sem


def _normalize_fetch_args(
    headers: dict | None, cookies: dict | str | None, user_agent: str | None
) -> tuple[dict | None, str]:
    """Normalize caller fetch args to the subset socid parse() accepts.

    parse(url, cookies_str='', timeout=3, headers={}) — there is no proxy
    param, so proxy is accepted at the public API for compat and ignored
    (logged at the call site).
    """
    h = dict(headers or {})
    if user_agent:
        h["User-Agent"] = user_agent
    c: str = ""
    if isinstance(cookies, dict):
        try:
            from socid_extractor.utils import join_cookies

            c = join_cookies(cookies)
        except Exception:
            c = ""
    elif isinstance(cookies, str):
        c = cookies
    return (h or None), c


async def _parse_in_thread(
    url: str,
    timeout: int,
    headers: dict | None = None,
    cookies_str: str = "",
):
    timeout = _clamp_timeout(timeout)
    async with _PARSE_LIMITER:
        kw: dict = {"timeout": timeout}
        if headers:
            kw["headers"] = dict(headers)  # copy; upstream has mutable default
        if cookies_str:
            kw["cookies_str"] = cookies_str
        return await asyncio.to_thread(_parse, url, **kw)


async def _extract_in_thread(page_text: str) -> dict:
    """BS4/regex extraction off the event loop (CPU-bound over 164 schemes)."""
    async with _PARSE_LIMITER:
        result = await asyncio.to_thread(_extract, page_text)
        return result if result else {}


def _merge_mutation(base: dict, overlay: dict) -> dict:
    """Merge an API-mutation result over the base page result.

    Truthy overlay values win (API endpoints are authoritative over scraped
    HTML); empty overlay values never clobber populated base values.
    `_extractor` provenance accumulates (str → list on conflict).
    """
    for key, value in overlay.items():
        if key == "_extractor":
            continue
        if value:
            base[key] = value
    ext = overlay.get("_extractor")
    if ext:
        prev = base.get("_extractor")
        if not prev:
            base["_extractor"] = ext
        elif isinstance(prev, list):
            for e in ext if isinstance(ext, list) else [ext]:
                if e not in prev:
                    prev.append(e)
        elif prev != ext:
            base["_extractor"] = (
                [prev, ext]
                if isinstance(ext, str)
                else [prev] + (ext if isinstance(ext, list) else [ext])
            )
    return base


async def _fetch_with_retry(
    url: str,
    timeout: int,
    headers: dict | None = None,
    cookies_str: str = "",
) -> tuple:
    """Fetch with per-host throttle + one retry on 429/5xx."""
    last_status = None
    for attempt in (1, 2):
        async with _host_sem(url):
            page_text, status_code = await _parse_in_thread(
                url, timeout, headers, cookies_str
            )
        if status_code in _RETRYABLE and attempt == 1:
            logger.debug("retry %s status=%s", url, status_code)
            await asyncio.sleep(1.0)
            last_status = status_code
            continue
        return page_text, status_code
    return None, last_status


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

    async def enrich_url(
        self,
        url: str,
        timeout: int = 5,
        *,
        headers: dict | None = None,
        cookies: dict | str | None = None,
        proxy: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        """Fetch a URL and extract profile metadata from the response."""
        if not _SOCID_AVAILABLE:
            return {}
        if proxy:
            logger.debug(
                "proxy ignored for %s: socid parse() has no proxies param", url
            )
        timeout = _clamp_timeout(timeout)
        req_headers, cookies_str = _normalize_fetch_args(headers, cookies, user_agent)

        try:
            page_text, status_code = await asyncio.wait_for(
                _fetch_with_retry(url, timeout, req_headers, cookies_str),
                timeout + _OUTER_SLACK,
            )
            if status_code and 200 <= status_code < 300 and page_text:
                result = await _extract_in_thread(page_text)
                if result:
                    return result
                # 2xx with empty extract: login-wall/challenge page, not a
                # fetch failure — distinct from the warning below.
                logger.debug(
                    "enrich empty extract, likely login-wall/challenge: %s status=%s len=%d",
                    url,
                    status_code,
                    len(page_text or ""),
                )
                return {}
        except TimeoutError:
            logger.warning("Profile enrichment timed out for %s", url)
        except Exception as exc:
            logger.warning("Profile enrichment failed for %s: %s", url, exc)

        return {}

    async def enrich_url_with_mutations(
        self,
        url: str,
        timeout: int = 5,
        *,
        headers: dict | None = None,
        cookies: dict | str | None = None,
        proxy: str | None = None,
        user_agent: str | None = None,
        skip_if_no_hint: bool = False,
        max_depth: int = 1,
    ) -> dict:
        """Fetch a URL and its API mutations, merging all extracted data."""
        if not _SOCID_AVAILABLE:
            return {}
        if proxy:
            logger.debug(
                "proxy ignored for %s: socid parse() has no proxies param", url
            )
        timeout = _clamp_timeout(timeout)
        req_headers, cookies_str = _normalize_fetch_args(headers, cookies, user_agent)

        result = await self.enrich_url(
            url,
            timeout=timeout,
            headers=req_headers,
            cookies=cookies_str,
            user_agent=user_agent,
        )

        mutations = self.get_mutations(url)
        if not mutations and not result and skip_if_no_hint:
            logger.debug("skip-if-no-hint: no mutations and empty base for %s", url)
            return {}
        visited = {url}
        for api_url, m_headers in mutations:
            try:
                merged = dict(req_headers or {})
                merged.update(m_headers or {})
                page_text, status_code = await asyncio.wait_for(
                    _fetch_with_retry(api_url, timeout, merged or None, cookies_str),
                    timeout + _OUTER_SLACK,
                )
                if status_code and 200 <= status_code < 300 and page_text:
                    mutation_result = await _extract_in_thread(page_text)
                    if mutation_result:
                        _merge_mutation(result, mutation_result)
                        visited.add(api_url)
                    else:
                        logger.debug(
                            "mutation empty extract, likely login-wall: %s status=%s",
                            api_url,
                            status_code,
                        )
            except TimeoutError:
                logger.warning("Mutation enrichment timed out for %s", api_url)
            except Exception as exc:
                logger.warning("Mutation enrichment failed for %s: %s", api_url, exc)

        # Second hop (Batch 10): follow URLs discovered in merged results
        # (orcid → OpenAlex → arXiv chains, api → html alternates), cap 3.
        if max_depth > 1 and isinstance(result, dict):
            hop_urls: list[str] = []
            for value in result.values():
                cands = value if isinstance(value, list) else [value]
                for cand in cands:
                    if (
                        isinstance(cand, str)
                        and cand.startswith("http")
                        and cand not in visited
                        and len(hop_urls) < 3
                    ):
                        visited.add(cand)
                        hop_urls.append(cand)
            for hop_url in hop_urls:
                try:
                    page_text, status_code = await asyncio.wait_for(
                        _fetch_with_retry(hop_url, timeout, req_headers, cookies_str),
                        timeout + _OUTER_SLACK,
                    )
                    if status_code and 200 <= status_code < 300 and page_text:
                        hop_result = await _extract_in_thread(page_text)
                        if hop_result:
                            _merge_mutation(result, hop_result)
                        else:
                            logger.debug(
                                "2nd-hop empty extract, likely login-wall: %s status=%s",
                                hop_url,
                                status_code,
                            )
                except Exception as exc:
                    logger.warning("2nd-hop enrichment failed for %s: %s", hop_url, exc)

        return result

    async def batch_enrich(
        self,
        urls: list[str],
        timeout: int = 5,
        on_result: Callable[[str, dict], object] | None = None,
        max_concurrent: int = 5,
        use_mutations: bool = False,
        *,
        headers: dict | None = None,
        cookies: dict | str | None = None,
        proxy: str | None = None,
        user_agent: str | None = None,
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

        if (
            max_concurrent is None
            or not isinstance(max_concurrent, int)
            or max_concurrent < 1
        ):
            logger.warning(
                "batch_enrich: clamping max_concurrent %r to 1", max_concurrent
            )
            max_concurrent = 1
        timeout = _clamp_timeout(timeout)
        if proxy:
            logger.debug("proxy ignored: socid parse() has no proxies param")

        # Dedupe preserving order — duplicate input previously paid N fetches.
        urls = list(dict.fromkeys(urls))

        results: dict[str, dict] = {}
        failed = 0
        failed_lock = asyncio.Lock()
        sem = asyncio.Semaphore(max_concurrent)

        enrich_fn = self.enrich_url_with_mutations if use_mutations else self.enrich_url

        async def _enrich_one(url: str):
            nonlocal failed
            async with sem:
                data = await enrich_fn(
                    url,
                    timeout=timeout,
                    headers=headers,
                    cookies=cookies,
                    user_agent=user_agent,
                )
                if data:
                    results[url] = data
                    if on_result:
                        try:
                            res = on_result(url, data)
                            if inspect.isawaitable(res):
                                await res
                        except Exception:
                            logger.debug(
                                "batch_enrich on_result failed for %s",
                                url,
                                exc_info=True,
                            )
                else:
                    async with failed_lock:
                        failed += 1

        tasks = [spawn(_enrich_one(u), name="enrich-one") for u in urls]
        await asyncio.gather(*tasks, return_exceptions=True)
        if failed:
            logger.warning("Enrichment: %d/%d URLs returned no data", failed, len(urls))
        return results
