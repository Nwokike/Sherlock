"""Sherlock OSINT search engine — powered by Maigret across 3,300+ platforms."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_MAIGRET_AVAILABLE = False
try:
    import maigret
    from maigret.checking import maigret as maigret_search
    from maigret.notify import QueryNotifyPrint
    from maigret.result import MaigretCheckResult, MaigretCheckStatus
    from maigret.sites import MaigretDatabase, MaigretSite

    _MAIGRET_AVAILABLE = True
except ImportError as err:
    logger.warning("Maigret library not available: %s", err)
    maigret = None
    maigret_search = None
    MaigretDatabase = None
    MaigretSite = None
    MaigretCheckResult = None
    MaigretCheckStatus = None
    QueryNotifyPrint = object


def _resolve_local_db() -> str:
    """Return a real filesystem path to the site database.

    Prefers user-synced or custom database. Otherwise falls back to the
    database bundled with maigret. On desktop the package lives in a real
    directory, but on mobile the Flet runtime imports it from inside
    sitepackages.zip — a zip *file*, not a folder — so naively joining
    dirname(__file__) yields a virtual path that open() rejects with
    [Errno 20] Not a directory. There we read the resource through the
    package loader and materialize a copy in the app storage dir,
    re-extracting only when the bundled content changes.
    """
    import hashlib
    import os
    import pkgutil

    from services.storage_service import get_storage_dir

    synced_path = get_storage_dir() / "synced_data.json"
    if synced_path.exists():
        logger.info("Using synced database: %s", synced_path)
        return str(synced_path)

    if maigret is not None and hasattr(maigret, "__file__"):
        bundled = os.path.join(
            os.path.dirname(maigret.__file__), "resources", "data.json"
        )
        if os.path.isfile(bundled):
            logger.info("Using local package database: %s", bundled)
            return bundled

    raw = pkgutil.get_data("maigret", "resources/data.json")
    if raw is None:
        # Check fallback to sherlock if maigret raw is not present
        raw = pkgutil.get_data("sherlock_project", "resources/data.json")
    if raw is None:
        raise FileNotFoundError("bundled resources/data.json not found in package")

    storage = get_storage_dir()
    storage.mkdir(parents=True, exist_ok=True)
    db_path = storage / "bundled_maigret_data.json"
    digest = hashlib.sha256(raw).hexdigest()
    hash_path = storage / "bundled_maigret_data.json.sha256"
    stored_hash = ""
    if hash_path.exists():
        try:
            stored_hash = hash_path.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    if not (db_path.exists() and stored_hash == digest):
        db_path.write_bytes(raw)
        hash_path.write_text(digest, encoding="utf-8")
    logger.info("Using extracted package database: %s", db_path)
    return str(db_path)


@dataclass
class SiteResult:
    site_name: str
    url_main: str
    url_user: str
    status: str
    http_status: str
    query_time: float | None = None
    context: str | None = None
    tags: list[str] = field(default_factory=list)
    ids_data: dict | None = None


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


class _MaigretQueryNotify:
    """Custom Maigret query notify callback collecting results into reactive SearchProgress."""

    def __init__(
        self,
        total: int,
        cancel_event: asyncio.Event,
        progress: SearchProgress | None = None,
        on_progress: Callable[[SearchProgress], None] | None = None,
    ):
        self.total = total
        self.cancel_event = cancel_event
        self.progress = progress
        self.on_progress = on_progress
        self.last_update_time = time.monotonic()
        self.collector: list[SiteResult] = []

    def start(self, username: str, id_type: str = "username") -> None:
        logger.debug("Maigret search started for %s (%s)", username, id_type)

    def update(self, result: Any, is_similar: bool = False) -> None:
        if self.cancel_event.is_set():
            return

        status_obj = getattr(result, "status", None)
        status_name = (
            getattr(status_obj, "name", "UNKNOWN") if status_obj else "UNKNOWN"
        )
        status_str = (
            "Claimed"
            if status_name == "CLAIMED"
            else ("Available" if status_name in ("AVAILABLE", "ILLEGAL") else "Error")
        )

        url_user = getattr(result, "site_url_user", "") or ""
        url_main = ""
        site_name = getattr(result, "site_name", "Unknown")
        query_time = getattr(result, "query_time", None)
        context_str = getattr(result, "context", None)
        tags = getattr(result, "tags", []) or []
        ids_data = getattr(result, "ids_data", None)

        sr = SiteResult(
            site_name=site_name,
            url_main=url_main,
            url_user=url_user,
            status=status_str,
            http_status="",
            query_time=query_time,
            context=context_str,
            tags=tags,
            ids_data=ids_data,
        )
        self.collector.append(sr)

        if self.progress:
            self.progress.checked_sites += 1
            if status_str == "Claimed":
                self.progress.found.append(sr)
            elif status_str == "Available":
                self.progress.not_found.append(sr)
            else:
                self.progress.errors.append(sr)

            if self.on_progress:
                now = time.monotonic()
                # Smoothly update at most 4 times a second (250ms), or immediately on the final site
                if (now - self.last_update_time >= 0.25) or (
                    self.progress.checked_sites >= self.total
                ):
                    self.last_update_time = now
                    try:
                        self.on_progress(self.progress)
                    except Exception:
                        pass

    def finish(self, message: str | None = None) -> None:
        logger.debug("Maigret search finished: %s", message)

    def warning(self, message: str) -> None:
        logger.warning("Maigret warning: %s", message)

    def info(self, message: str) -> None:
        logger.info("Maigret info: %s", message)


def parse_usernames(raw: str) -> list[str]:
    """Parse comma/space separated list of usernames and expand {?} wildcards."""
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

    seen = set()
    unique = []
    for item in resolved:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


class SherlockService:
    """Runs high-performance username OSINT searches powered by Maigret across 3,300+ sites."""

    def __init__(self):
        self._cancel_event = asyncio.Event()
        self._search_task: asyncio.Task | None = None
        self._progress: SearchProgress | None = None
        self._db: Any | None = None
        self._sites_dict: dict[str, Any] = {}
        self._total_sites: int = 0
        self._last_config: tuple | None = None

    @property
    def is_available(self) -> bool:
        return _MAIGRET_AVAILABLE

    async def load_sites(self, force: bool = False) -> int:
        """Load site database. Returns total number of sites available."""
        if not _MAIGRET_AVAILABLE:
            return 0

        from core.state import state

        config = (
            state.custom_manifest.strip() if state.custom_manifest else "",
            state.use_local_db,
            state.ignore_exclusions,
            state.nsfw_enabled,
        )

        if not force and self._sites_dict and self._last_config == config:
            return self._total_sites

        try:
            logger.info("Loading Maigret site database...")
            from services.storage_service import get_storage_dir

            if state.custom_manifest:
                path_arg = state.custom_manifest.strip()
                logger.info("Using custom manifest database: %s", path_arg)
            elif state.use_local_db:
                path_arg = _resolve_local_db()
            else:
                synced_path = get_storage_dir() / "synced_data.json"
                if synced_path.exists():
                    path_arg = str(synced_path)
                    logger.info("Using synced database: %s", path_arg)
                else:
                    path_arg = _resolve_local_db()

            def _load_db():
                db = MaigretDatabase().load_from_path(path_arg)
                return db

            self._db = await asyncio.to_thread(_load_db)

            # Build sites dict according to NSFW & exclusion settings and scan depth
            excluded_tags = [] if state.nsfw_enabled else ["nsfw"]
            top_limit = (
                500
                if state.scan_depth == "500"
                else (1000 if state.scan_depth == "1000" else 9223372036854775807)
            )
            sites_dict = self._db.ranked_sites_dict(
                top=top_limit,
                disabled=state.ignore_exclusions,
                excluded_tags=excluded_tags,
                id_type="username",
            )
            self._sites_dict = sites_dict
            self._total_sites = len(sites_dict)
            self._last_config = config

            # Populate reactive state
            state.sites_total = self._total_sites
            state.sites_cache = sorted(sites_dict.keys(), key=str.lower)
            state.sites_tags_map = {
                k: list(getattr(v, "tags", [])) for k, v in sites_dict.items()
            }
            state.sites_version += 1

            logger.info("Loaded %d Maigret sites", self._total_sites)
            return self._total_sites
        except Exception as e:
            logger.error("Failed to load site database: %s", e)
            return 0

    async def search(
        self,
        username: str,
        on_progress: Callable[[SearchProgress], None],
        timeout: int = 30,
    ) -> SearchProgress:
        """Run Maigret search across multi-usernames with active settings filters."""
        if not _MAIGRET_AVAILABLE:
            raise RuntimeError("Maigret search engine is not available")

        from core.state import state

        targets = parse_usernames(username)
        state.search_targets = targets
        state.target_results = {}
        if not targets:
            raise RuntimeError("No valid usernames specified for scanning")

        # Ensure sites database is loaded
        if not self._sites_dict:
            await self.load_sites()

        sites_to_scan = dict(self._sites_dict)
        if state.selected_sites:
            selected_set = {s.lower() for s in state.selected_sites}
            sites_to_scan = {
                k: v for k, v in sites_to_scan.items() if k.lower() in selected_set
            }

        total_sites = len(sites_to_scan)
        if total_sites == 0:
            raise RuntimeError("No sites selected or available for scanning")

        self._cancel_event.clear()
        last_prog: SearchProgress | None = None

        proxy = getattr(state, "proxy_url", "") or None
        max_conns = 50  # Balanced high-throughput concurrency for mobile & desktop

        for tgt in targets:
            if self._cancel_event.is_set():
                break

            state.active_username = tgt
            self._progress = SearchProgress(
                username=tgt,
                total_sites=total_sites,
                is_running=True,
            )
            state.target_results[tgt] = self._progress
            on_progress(self._progress)

            query_notify = _MaigretQueryNotify(
                total=total_sites,
                cancel_event=self._cancel_event,
                progress=self._progress,
                on_progress=on_progress,
            )

            output_container: dict[str, Any] = {}

            try:
                # Execute native async Maigret search
                await maigret_search(
                    username=tgt,
                    site_dict=sites_to_scan,
                    logger=logger,
                    query_notify=query_notify,
                    proxy=proxy,
                    timeout=timeout,
                    max_connections=max_conns,
                    no_progressbar=True,
                    dns_resolver="async",
                    output_container=output_container,
                )
            except asyncio.CancelledError:
                logger.info("Search task cancelled for %s", tgt)
                self._progress.is_cancelled = True
                raise
            except Exception as exc:
                logger.exception("Maigret search encountered an error: %s", exc)
                raise
            finally:
                self._progress.is_running = False

            on_progress(self._progress)
            last_prog = self._progress

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

    def cancel(self) -> None:
        """Cancel a running search."""
        self._cancel_event.set()
        if self._search_task and not self._search_task.done():
            self._search_task.cancel()
        if self._progress:
            self._progress.is_cancelled = True
            self._progress.is_running = False

        from core.state import state

        for tgt in state.target_results:
            prog = state.target_results[tgt]
            if prog.is_running:
                prog.is_running = False
                prog.is_cancelled = True
