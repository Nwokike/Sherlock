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
                # Includes "WAF", "Unknown", or other errors
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


def parse_usernames(raw: str) -> list[str]:
    """Parse comma/space separated list of usernames and expand {?} wildcards."""
    # Split by comma first, then if there's no comma, split by whitespace
    if "," in raw:
        items = [i.strip() for i in raw.split(",")]
    else:
        items = raw.split()

    resolved = []
    checksymbols = ["_", "-", "."]
    for item in items:
        item = item.strip()
        if not item:
            continue
        if "{?}" in item:
            for symb in checksymbols:
                resolved.append(item.replace("{?}", symb))
        else:
            resolved.append(item)

    # Keep order but remove duplicates
    seen = set()
    unique = []
    for item in resolved:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


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

            if state.custom_manifest:
                path_arg = state.custom_manifest.strip()
                logger.info("Using custom manifest database: %s", path_arg)
            else:
                # Determine local database path
                synced_path = Path.home() / ".sherlock" / "synced_data.json"
                if synced_path.exists():
                    db_path = str(synced_path)
                    logger.info("Using synced database: %s", db_path)
                else:
                    db_path = os.path.join(
                        os.path.dirname(sherlock_project.__file__),
                        "resources",
                        "data.json",
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

    async def check_updates(self) -> str | None:
        """Checks for updates. Returns latest version tag if new release is available."""
        try:
            import httpx
            import sherlock_project

            current_ver = sherlock_project.__version__
            url = sherlock_project.forge_api_latest_release
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    latest_tag = data.get("tag_name", "")
                    if latest_tag.startswith("v"):
                        latest_ver = latest_tag[1:]
                    else:
                        latest_ver = latest_tag

                    if latest_ver != current_ver:
                        return latest_ver
            return None
        except Exception:
            return None

    async def search(
        self,
        username: str,
        on_progress: Callable[[SearchProgress], None],
        timeout: int = 30,
    ) -> SearchProgress:
        """Run a sherlock search loop over multi-usernames with current settings filters."""
        if not _SHERLOCK_AVAILABLE:
            raise RuntimeError("Sherlock not available")

        from core.state import state

        # Parse comma/space list of usernames & wildcards
        targets = parse_usernames(username)
        state.search_targets = targets
        state.target_results = {}
        if not targets:
            raise RuntimeError("No valid usernames specified for scanning")

        # Load fresh SitesInformation based on current manifest configuration
        import os
        from pathlib import Path
        import sherlock_project

        if state.custom_manifest:
            path_arg = state.custom_manifest.strip()
        else:
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

        from sherlock_project.sherlock import sherlock

        # Run sequential search loops for each username
        last_prog = None
        for i, tgt in enumerate(targets):
            if self._cancel_event.is_set():
                break

            state.active_username = tgt
            self._collector = []
            self._progress = SearchProgress(
                username=tgt,
                total_sites=total_sites,
                is_running=True,
            )
            state.target_results[tgt] = self._progress
            on_progress(self._progress)

            query_notify = _CollectorQueryNotify(
                self._collector,
                total_sites,
                self._cancel_event,
                progress=self._progress,
                on_progress=on_progress,
            )

            proxy_str = state.proxy_url.strip() if state.proxy_url.strip() else None

            def _run():
                try:
                    results = sherlock(
                        username=tgt,
                        site_data=site_data,
                        query_notify=query_notify,
                        tor=state.tor_enabled,
                        unique_tor=state.unique_tor_enabled,
                        dump_response=False,
                        proxy=proxy_str,
                        timeout=timeout,
                    )
                    return results
                except SystemExit as se:
                    logger.warning(
                        "Sherlock attempted process exit (SystemExit): %s", se
                    )
                    raise RuntimeError(
                        "Tor connection failed. Please ensure Orbot or Tor is running on port 9050."
                    ) from se
                except Exception as e:
                    logger.exception("Sherlock search failed: %s", e)
                    raise e

            try:
                await asyncio.to_thread(_run)
            finally:
                self._progress.is_running = False

            on_progress(self._progress)
            last_prog = self._progress

        # Handle remaining cancelled targets if any
        for tgt in targets:
            if tgt not in state.target_results:
                state.target_results[tgt] = SearchProgress(
                    username=tgt,
                    total_sites=total_sites,
                    is_cancelled=True,
                )
            elif self._cancel_event.is_set() and state.target_results[tgt].is_running:
                state.target_results[tgt].is_running = False
                state.target_results[tgt].is_cancelled = True

        return last_prog or self._progress

    def cancel(self):
        """Cancel a running search."""
        self._cancel_event.set()
        if self._progress:
            self._progress.is_cancelled = True
            self._progress.is_running = False
        from core.state import state

        for tgt in state.target_results:
            prog = state.target_results[tgt]
            if prog.is_running:
                prog.is_running = False
                prog.is_cancelled = True
