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
    """Custom QueryNotify that collects results into a thread-safe list and updates progress."""

    def __init__(
        self,
        collector: list,
        total: int,
        cancel_event: threading.Event,
        progress: SearchProgress = None,
        on_progress: Callable = None,
    ):
        super().__init__()
        self.collector = collector
        self.total = total
        self.cancel_event = cancel_event
        self.progress = progress
        self.on_progress = on_progress
        import time

        self.last_update_time = time.monotonic()

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

        if self.progress:
            self.progress.checked_sites += 1
            if sr.status == "Claimed":
                self.progress.found.append(sr)
            elif sr.status == "Available" or sr.status == "Illegal":
                self.progress.not_found.append(sr)
            else:
                self.progress.errors.append(sr)

            if self.on_progress:
                import time

                now = time.monotonic()
                # Smoothly update at most 4 times a second (250ms), but always update on the final site
                if (now - self.last_update_time >= 0.25) or (
                    self.progress.checked_sites == self.total
                ):
                    self.last_update_time = now
                    try:
                        self.on_progress(self.progress)
                    except Exception:
                        pass

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
            import os
            from pathlib import Path
            import sherlock_project
            from core.state import state

            # Determine local database path
            synced_path = Path.home() / ".sherlock" / "synced_data.json"
            if synced_path.exists():
                db_path = str(synced_path)
                logger.info("Using synced database: %s", db_path)
            else:
                db_path = os.path.join(
                    os.path.dirname(sherlock_project.__file__), "resources", "data.json"
                )
                logger.info("Using local package database: %s", db_path)

            path_arg = db_path if state.use_local_db else None
            sites = await asyncio.to_thread(
                SitesInformation,
                data_file_path=path_arg,
                honor_exclusions=not state.ignore_exclusions,
            )

            if not state.nsfw_enabled:
                sites.remove_nsfw_sites()

            site_data = {site.name: site.information for site in sites}
            self._site_data = site_data
            self._total_sites = len(site_data)
            logger.info("Loaded %d sites", self._total_sites)
            return self._total_sites
        except Exception as e:
            logger.error("Failed to load sites: %s", e)
            return 0

    async def sync_database(self) -> bool:
        """Download latest data.json from GitHub and save to local storage."""
        try:
            import json
            import httpx
            from pathlib import Path

            logger.info("Syncing database from GitHub...")
            url = "https://raw.githubusercontent.com/sherlock-project/sherlock/master/sherlock_project/resources/data.json"
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    # Validate JSON
                    if isinstance(data, dict) and len(data) > 0:
                        save_dir = Path.home() / ".sherlock"
                        save_dir.mkdir(parents=True, exist_ok=True)
                        save_path = save_dir / "synced_data.json"
                        save_path.write_text(
                            json.dumps(data, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        logger.info("Database synced successfully to %s", save_path)
                        # Reload sites so memory reflects the update
                        await self.load_sites()
                        return True
            return False
        except Exception as e:
            logger.error("Failed to sync database: %s", e)
            return False

    async def search(
        self,
        username: str,
        on_progress: Callable[[SearchProgress], None],
        timeout: int = 30,
    ) -> SearchProgress:
        """Run a sherlock search for the given username with current settings filters."""
        if not _SHERLOCK_AVAILABLE:
            raise RuntimeError("Sherlock not available")

        # Load fresh SitesInformation based on current settings
        import os
        from pathlib import Path
        import sherlock_project
        from core.state import state

        synced_path = Path.home() / ".sherlock" / "synced_data.json"
        if synced_path.exists():
            db_path = str(synced_path)
        else:
            db_path = os.path.join(
                os.path.dirname(sherlock_project.__file__), "resources", "data.json"
            )

        path_arg = db_path if state.use_local_db else None

        try:
            sites = await asyncio.to_thread(
                SitesInformation,
                data_file_path=path_arg,
                honor_exclusions=not state.ignore_exclusions,
            )
            if not state.nsfw_enabled:
                sites.remove_nsfw_sites()
        except Exception as e:
            logger.error("Failed to load sites for search: %s", e)
            sites = None

        # Filter custom selected sites if any
        selected = state.selected_sites
        if selected and sites:
            selected_lower = {s.lower() for s in selected}
            site_data = {}
            for site in sites:
                if site.name.lower() in selected_lower:
                    site_data[site.name] = site.information
        elif sites:
            site_data = {site.name: site.information for site in sites}
        else:
            site_data = self._site_data or {}

        total_sites = len(site_data)
        if total_sites == 0:
            raise RuntimeError("No sites selected or available for scanning")

        self._cancel_event.clear()
        self._collector = []
        self._progress = SearchProgress(
            username=username,
            total_sites=total_sites,
            is_running=True,
        )
        on_progress(self._progress)

        from sherlock_project.sherlock import sherlock

        query_notify = _CollectorQueryNotify(
            self._collector,
            total_sites,
            self._cancel_event,
            progress=self._progress,
            on_progress=on_progress,
        )

        def _run():
            try:
                results = sherlock(
                    username=username,
                    site_data=site_data,
                    query_notify=query_notify,
                    timeout=timeout,
                )
                return results
            except Exception as e:
                logger.exception("Sherlock search failed: %s", e)

        await asyncio.to_thread(_run)

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
