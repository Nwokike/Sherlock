"""Sherlock search engine — wraps sherlock_project with progress & cancellation."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_SHERLOCK_AVAILABLE = False
try:
    from sherlock_project.result import QueryResult, QueryStatus
    from sherlock_project.sites import SitesInformation
    from sherlock_project.notify import QueryNotify

    _SHERLOCK_AVAILABLE = True
except ImportError:
    QueryResult = None
    QueryStatus = None
    SitesInformation = None
    QueryNotify = None


@dataclass
class SiteResult:
    site_name: str
    url_main: str
    url_user: str
    status: str
    http_status: str
    query_time: Optional[float] = None
    context: Optional[str] = None


@dataclass
class SearchProgress:
    username: str
    total_sites: int = 0
    checked_sites: int = 0
    found: list[SiteResult] = field(default_factory=list)
    not_found: list[SiteResult] = field(default_factory=list)
    errors: list[SiteResult] = field(default_factory=list)
    is_running: bool = False
    is_cancelled: bool = False


class _CollectorQueryNotify(QueryNotify):
    """Custom QueryNotify that collects results into a thread-safe list."""

    def __init__(self, collector: list, total: int, cancel_event: threading.Event):
        super().__init__()
        self.collector = collector
        self.total = total
        self.cancel_event = cancel_event

    def start(self, message):
        pass

    def update(self, result: QueryResult):
        if self.cancel_event.is_set():
            return
        sr = SiteResult(
            site_name=result.site_name,
            url_main="",
            url_user=result.site_url_user,
            status=result.status.value,
            http_status="",
            query_time=result.query_time,
            context=result.context,
        )
        self.collector.append(sr)

    def finish(self, message=None):
        pass


class SherlockService:
    """Runs sherlock searches in background threads."""

    def __init__(self):
        self._cancel_event = threading.Event()
        self._search_thread: threading.Thread | None = None
        self._progress: SearchProgress | None = None
        self._site_data: dict | None = None
        self._collector: list = []
        self._total_sites = 0

    @property
    def is_available(self) -> bool:
        return _SHERLOCK_AVAILABLE

    async def load_sites(self) -> int:
        """Load site data. Returns number of sites loaded."""
        if not _SHERLOCK_AVAILABLE:
            return 0
        try:
            logger.info("Loading site data...")
            sites = await asyncio.to_thread(SitesInformation)
            site_data = {site.name: site.information for site in sites}
            self._site_data = site_data
            self._total_sites = len(site_data)
            logger.info("Loaded %d sites", self._total_sites)
            return self._total_sites
        except Exception as e:
            logger.error("Failed to load sites: %s", e)
            return 0

    async def search(
        self,
        username: str,
        on_progress: Callable[[SearchProgress], None],
        timeout: int = 30,
    ) -> SearchProgress:
        """Run a sherlock search for the given username."""
        if not _SHERLOCK_AVAILABLE or not self._site_data:
            raise RuntimeError("Sherlock not available or site data not loaded")

        self._cancel_event.clear()
        self._collector = []
        self._progress = SearchProgress(
            username=username,
            total_sites=self._total_sites,
            is_running=True,
        )
        on_progress(self._progress)

        from sherlock_project.sherlock import sherlock

        query_notify = _CollectorQueryNotify(
            self._collector, self._total_sites, self._cancel_event
        )

        def _run():
            try:
                results = sherlock(
                    username=username,
                    site_data=self._site_data,
                    query_notify=query_notify,
                    timeout=timeout,
                )
                return results
            except Exception as e:
                logger.exception("Sherlock search failed: %s", e)
                return {}

        results = await asyncio.to_thread(_run)

        processed = set()
        for sr in self._collector:
            if sr.site_name not in processed:
                processed.add(sr.site_name)
                if sr.status == "Claimed":
                    self._progress.found.append(sr)
                elif sr.status == "Available" or sr.status == "Illegal":
                    self._progress.not_found.append(sr)
                else:
                    self._progress.errors.append(sr)

        self._progress.checked_sites = len(processed)
        self._progress.is_running = False

        for _ in range(3):
            on_progress(self._progress)
            await asyncio.sleep(0.05)

        return self._progress

    def cancel(self):
        """Cancel a running search."""
        self._cancel_event.set()
        if self._progress:
            self._progress.is_cancelled = True
            self._progress.is_running = False
