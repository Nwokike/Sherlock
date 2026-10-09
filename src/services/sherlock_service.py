"""Sherlock OSINT search engine — powered by Maigret across 5,200+ platforms."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_MAIGRET_AVAILABLE = False
try:
    import maigret
    from maigret.checking import maigret as maigret_search
    from maigret.errors import solution_of as _error_solution
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

    def _error_solution(_err_type: str) -> str:
        return ""


if _MAIGRET_AVAILABLE:

    class _SilentBar:
        """Drop-in replacement for alive_progress's alive_bar handle.

        maigret constructs an alive_bar unconditionally (checking.py calls
        it even with disable=True). alive_progress initializes its text
        engine at construction, and the grapheme package it depends on
        loads its data with a raw open() inside site-packages — which on
        Android is the sitepackages.zip FILE, so the path open() raises
        [Errno 20] Not a directory and every scan dies before starting.
        We never render the bar (we drive progress through our own notify
        bridge with no_progressbar=True), so a silent handle is
        behavior-identical on every platform and sidesteps the zip trap.
        """

        def __call__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def text(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> _SilentBar:
            return self

        def __exit__(self, *args: Any) -> bool:
            return False

    def _silent_alive_bar(*args: Any, **kwargs: Any) -> _SilentBar:
        return _SilentBar()

    # Guarded: a maigret build without checking.alive_bar must not kill
    # this module at import time.
    try:
        import maigret.checking as _checking

        if hasattr(_checking, "alive_bar"):
            _checking.alive_bar = _silent_alive_bar
        else:
            logger.warning(
                "maigret.checking.alive_bar missing — silent-bar patch skipped"
            )
    except Exception as exc:
        logger.warning("Silent-bar patch skipped: %s", exc)

    # P3-8 shared-DNS connector defaults: maigret builds a FRESH
    # TCPConnector per site check (checking.py), so the connector's
    # default ttl_dns_cache=10s dies between checks and the DNS prewarm
    # cache is never re-read by later connectors. Patch construction
    # defaults so every connector keeps resolutions for the whole scan.
    # aiohttp is only used by maigret in this process (email uses
    # httpx/curl_cffi), so the blast radius is the scan engine.
    try:
        import aiohttp as _aiohttp

        _orig_tcp_init = _aiohttp.TCPConnector.__init__

        def _tcp_init_with_scan_defaults(self, *args, **kwargs):
            kwargs.setdefault("ttl_dns_cache", 300)
            kwargs.setdefault("dns_cache_max_size", 10000)
            kwargs.setdefault("keepalive_timeout", 30)
            _orig_tcp_init(self, *args, **kwargs)

        _aiohttp.TCPConnector.__init__ = _tcp_init_with_scan_defaults
        logger.info("aiohttp connector defaults patched (ttl_dns_cache=300s)")
    except Exception as exc:
        logger.warning("Connector DNS-cache patch failed: %s", exc)


def _resolve_local_db(check_synced: bool = True) -> str:
    """Return a real filesystem path to the site database.

    Prefers user-synced or custom database. Otherwise falls back to the
    database bundled with maigret. On desktop the package lives in a real
    directory, but on mobile the Flet runtime imports it from inside
    sitepackages.zip — a zip *file*, not a folder — so naively joining
    dirname(__file__) yields a virtual path that open() rejects with
    [Errno 20] Not a directory. There we read the resource through the
    package loader and materialize a copy in the app CACHE dir (it is
    regenerable — the miss path re-extracts, so eviction is safe),
    re-extracting only when the bundled content changes.
    """
    import hashlib
    import os
    import pkgutil

    from services.storage_service import get_cache_dir, get_storage_dir

    synced_path = get_storage_dir() / "synced_data.json"
    if check_synced and synced_path.exists():
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
        raise FileNotFoundError("bundled resources/data.json not found in package")
    # NOTE: legacy "sherlock_project" fallback removed — installed dist is
    # maigret>=0.6.6 (pyproject.toml); a second wrong name only masks errors.

    cache = get_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    # One-time migration (Batch 12 tier fix): the materialized copy used to
    # live in durable storage/ — remove the legacy orphans so they don't
    # bloat backups forever.
    try:
        legacy = get_storage_dir() / "bundled_maigret_data.json"
        legacy.unlink(missing_ok=True)
        legacy.with_suffix(".json.sha256").unlink(missing_ok=True)
    except OSError:
        pass
    db_path = cache / "bundled_maigret_data.json"
    digest = hashlib.sha256(raw).hexdigest()
    hash_path = cache / "bundled_maigret_data.json.sha256"
    stored_hash = ""
    if hash_path.exists():
        try:
            stored_hash = hash_path.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    if not (db_path.exists() and stored_hash == digest):
        try:
            import tempfile

            fd, tmp_s = tempfile.mkstemp(
                dir=str(cache), prefix=".bundled_maigret_data.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(raw)
                os.replace(tmp_s, db_path)
                hash_path.write_text(digest, encoding="utf-8")
            finally:
                try:
                    os.unlink(tmp_s)
                except OSError:
                    pass
        except OSError as exc:
            logger.warning(
                "Bundled DB materialize failed, using in-memory fallback: %s", exc
            )
            import tempfile as _tf

            with _tf.NamedTemporaryFile(delete=False, suffix=".json") as fallback:
                fallback.write(raw)
            return fallback.name
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
    # Typed maigret CheckError + site protection metadata — drives the
    # WAF/bot-walled badges, the advice line, and keyword-hit chips.
    error_type: str | None = None
    error_hint: str = ""
    protection: list[str] = field(default_factory=list)
    badge: str = ""  # "bot" | "dead" | "rate" | "error" | ""
    keyword_hit: bool = False


# maigret CheckError.type values that mean "a bot wall stopped us" —
# exact vocabulary from maigret/errors.py (COMMON_ERRORS + ERRORS_TYPES).
_BOT_ERROR_TYPES = frozenset(
    {
        "Captcha",
        "Bot protection",
        "Access denied",
        "Request blocked",
        "Just a moment: bot redirect challenge",
        "Login required",
    }
)
_DEAD_ERROR_PREFIX = "Connecting failure"
_RATE_ERROR_TYPE = "Rate limited"
# Normalized substring fallback for error types outside maigret's exact
# vocabulary ("HTTP 429", "403 Forbidden", "Cloudflare challenge", ...).
# Checked AFTER the exact vocabulary above, so known types are unchanged.
_RATE_SUBSTRINGS = ("429", "rate", "too many")
_WAF_SUBSTRINGS = (
    "403",
    "cloudflare",
    "captcha",
    "waf",
    "forbidden",
    "incapsula",
    "datadome",
    "akamai",
    "perimeterx",
    "kasada",
    "bot",
    "challenge",
    "denied",
    "blocked",
)
# Generic failures on a site that carries protection tags are almost
# always the wall rather than the endpoint.
_GENERIC_ERROR_TYPES = frozenset({"Unknown", "", "HTTP", "Request failed", "Payload"})


def classify_error(error_type: str | None, protection: list[str] | None = None) -> str:
    """Map a CheckError type (+ site protection tags) → badge class.

    Returns one of "bot", "dead", "rate", "error", or "" (no error).
    """
    et = error_type or ""
    if not et:
        # No error on this result — site protection alone is not a badge
        # (a CLAIMED result on a walled site is a success, not a block).
        return ""
    if et == _RATE_ERROR_TYPE:
        return "rate"
    if et in _BOT_ERROR_TYPES:
        return "bot"
    if et == _DEAD_ERROR_PREFIX or et.startswith(_DEAD_ERROR_PREFIX + " "):
        return "dead"
    if et in _GENERIC_ERROR_TYPES and protection:
        return "bot"
    # Normalized substring fallback — catches "HTTP 429", "429 Too Many
    # Requests", "403 Forbidden", "Cloudflare challenge", "WAF blocked", etc.
    low = et.lower()
    if any(s in low for s in _RATE_SUBSTRINGS):
        return "rate"
    if any(s in low for s in _WAF_SUBSTRINGS):
        return "bot"
    if et:
        return "error"
    return ""


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
        cancel_event: threading.Event,
        progress: SearchProgress | None = None,
        on_progress: Callable[[SearchProgress], None] | None = None,
        sites_lookup: dict[str, Any] | None = None,
    ):
        self.total = total
        self.cancel_event = cancel_event
        self.progress = progress
        self.on_progress = on_progress
        # Site objects for protection metadata (bot-wall badges).
        self.sites_lookup = sites_lookup or {}
        self.last_update_time = time.monotonic()
        self.collector: list[SiteResult] = []
        self._enrich_requests = 0

    def start(
        self, username: str = "", id_type: str = "username", *args, **kwargs
    ) -> None:
        logger.debug("Maigret search started for %s (%s)", username, id_type)

    def update(self, result: Any, is_similar: bool = False, *args, **kwargs) -> None:
        if self.cancel_event.is_set():
            return

        status_obj = getattr(result, "status", None)
        status_name = (
            getattr(status_obj, "name", "UNKNOWN") if status_obj else "UNKNOWN"
        )

        url_user = getattr(result, "site_url_user", "") or ""
        site_name = getattr(result, "site_name", "Unknown")
        query_time = getattr(result, "query_time", None)
        context_str = getattr(result, "context", None)
        tags = getattr(result, "tags", []) or []
        ids_data = getattr(result, "ids_data", None)

        # Typed error classification: MaigretCheckResult.error carries a
        # CheckError (type = vocabulary like "Bot protection"/"Rate limited");
        # site.protection tags provide the fallback heuristic. Bot-class
        # failures render with the dedicated "WAF" status result_card
        # already styles; everything else stays "Error".
        err = getattr(result, "error", None)
        error_type = getattr(err, "type", None) if err is not None else None
        if error_type is not None and not isinstance(error_type, str):
            error_type = str(error_type)
        site_obj = self.sites_lookup.get(site_name)
        url_main = getattr(site_obj, "url_main", "") or ""
        protection = list(getattr(site_obj, "protection", []) or []) if site_obj else []
        kw_status = getattr(result, "keyword_match_status", None)
        keyword_hit = getattr(kw_status, "name", "") == "KEYWORD_FOUND"
        badge = classify_error(error_type, protection)

        status_str = (
            "Claimed"
            if status_name == "CLAIMED"
            else (
                "Available"
                if status_name == "AVAILABLE"
                # ILLEGAL = username not allowable for this site (checker
                # skipped), not a probed "available" — own status routed
                # to errors so counts stay honest.
                else (
                    "Skipped"
                    if status_name == "ILLEGAL"
                    else ("WAF" if badge == "bot" else "Error")
                )
            )
        )

        # MaigretCheckResult carries no http_status (it lives on maigret's
        # internal SiteResult dict, which is NOT passed to query_notify.update
        # — see maigret checking.py). Read best-effort so a future maigret that
        # attaches it is picked up without a fork.
        http_status = getattr(result, "http_status", "") or ""
        if not isinstance(http_status, str):
            http_status = str(http_status)

        sr = SiteResult(
            site_name=site_name,
            url_main=url_main,
            url_user=url_user,
            status=status_str,
            http_status=http_status,
            query_time=query_time,
            context=context_str,
            tags=tags,
            ids_data=ids_data,
            error_type=error_type,
            error_hint=_error_solution(error_type) if error_type else "",
            protection=protection,
            badge=badge,
            keyword_hit=keyword_hit,
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
                    except Exception as exc:
                        logger.debug("on_progress callback failed: %s", exc)

    def finish(self, message: str | None = None, *args, **kwargs) -> None:
        logger.debug("Maigret search finished: %s", message)
        if self._enrich_requests:
            # Deep-enrich visibility (owner rule): total mutation traffic
            # for this target, surfaced after every pass.
            logger.info(
                "Deep enrichment: %d mutation request(s)", self._enrich_requests
            )

    def warning(
        self, message: str = "", symbol: str = "-", advice: Any = None, *args, **kwargs
    ) -> None:
        logger.warning("Maigret warning: %s", message)

    def info(self, message: str = "", symbol: str = "*", *args, **kwargs) -> None:
        logger.info("Maigret info: %s", message)

    def success(self, message: str = "", symbol: str = "+", *args, **kwargs) -> None:
        logger.info("Maigret success: %s", message)

    def enrich(
        self,
        message: str = "",
        symbol: str = "*",
        verbose_only: bool = False,
        *args,
        **kwargs,
    ) -> None:
        self._enrich_requests += 1
        logger.debug("Maigret enrich: %s", message)

    def error(self, message: str = "", *args, **kwargs) -> None:
        logger.error("Maigret error: %s", message)


def parse_usernames(raw: str) -> list[str]:
    """Parse comma/space separated list of usernames and expand {?} wildcards."""
    items = [i.strip() for i in raw.split(",")] if "," in raw else raw.split()

    resolved = []
    checksymbols = ["_", "-", "."]
    for item in items:
        item = item.strip()
        if not item:
            continue
        if "{?}" in item:
            resolved.extend(item.replace("{?}", symb) for symb in checksymbols)
        else:
            resolved.append(item)

    seen = set()
    unique = []
    for item in resolved:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


# Recursive second-pass bounds — keep opt-in recursion mobile-friendly.
# Username-type secondaries scan the first N of the user's own scope;
# rare non-username types (vk_id, orcid, …) have a handful of sites each.
RECURSIVE_TARGET_CAP = 20
RECURSIVE_USERNAME_SITES = 500
# "All" depth sentinel for ranked_sites_dict(top=...).
SCAN_ALL = 9223372036854775807


def _mark_cancelled(prog: SearchProgress) -> None:
    prog.is_running = False
    prog.is_cancelled = True


def _maigret_kwargs(func: Any, **kwargs: Any) -> dict[str, Any]:
    """Drop kwargs the installed maigret() doesn't accept (version skew)."""
    import inspect as _inspect

    try:
        sig = _inspect.signature(func)
    except TypeError, ValueError:
        return kwargs
    params = sig.parameters
    if any(p.kind == _inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs  # 0.6.6 has **kwargs — pass through
    return {k: v for k, v in kwargs.items() if k in params}


def extract_holehe_usernames(email_rows: list | None, cap: int = 5) -> list[str]:
    """High-confidence usernames from holehe-v2 email results.

    github.login, duolingo/etzy usernames, gravatar usernames are
    platform-verified identities — prime cross-engine pivot candidates for
    a username scan. Returns deduped strings, most-confident first.
    """
    if not email_rows:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for r in email_rows:
        if isinstance(r, dict):
            get = r.get
        else:
            _r = r

            def get(k, d=None, _r=_r):
                return getattr(_r, k, d)

        if not get("exists"):
            continue
        others = get("others") or {}
        extra = (
            others.get("extra")
            if isinstance(others, dict) and isinstance(others.get("extra"), dict)
            else {}
        )
        cands = [
            extra.get("login"),
            extra.get("username"),
            extra.get("preferredUsername"),
        ]
        for c in cands:
            if isinstance(c, str) and c.strip():
                key = c.strip().lower()
                if key not in seen:
                    seen.add(key)
                    out.append(c.strip())
                    if len(out) >= cap:
                        return out
    return out


def _collect_recursive_targets(
    containers: dict[str, Any],
    db: Any,
    already: list[str],
    cap: int = RECURSIVE_TARGET_CAP,
) -> dict[str, str]:
    """Extract secondary scan targets ({id: id_type}) from primary passes.

    Mirrors maigret's own CLI recursion (extract_ids_from_results followed
    by adding every discovered id to the worklist) but with hard safety
    bounds: dedupe against everything already scanned and stop at `cap`.
    Values come from output_container — populated only when
    is_parsing_enabled (extract_info) is on.
    """
    from maigret.maigret import extract_ids_from_results

    seen = {a.lower() for a in already}
    discovered: dict[str, str] = {}
    for container in containers.values():
        if not container:
            continue
        try:
            found = extract_ids_from_results(container, db)
        except Exception as exc:
            logger.warning("Recursive ID extraction failed: %s", exc)
            continue
        for new_id, id_type in found.items():
            key = str(new_id).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            discovered[str(new_id)] = str(id_type)
            if len(discovered) >= cap:
                return discovered
    return discovered


def _run_maigret_worker_thread(
    targets: list[str],
    sites_to_scan: dict[str, Any],
    proxy: str | None,
    timeout: int,
    max_conns: int,
    dns_res: str,
    extract_info: bool,
    retry_count: int,
    cancel_event: threading.Event,
    on_progress_cb: Callable[[SearchProgress], None],
    db: Any | None = None,
    recursive: bool = False,
    deep_enrich: bool = False,
    keywords: list[str] | None = None,
    cookies_path: str | None = None,
    i2p_proxy: str | None = None,
    check_domains: bool = False,
    after_primary: Callable[[str, Any], None] | None = None,
) -> SearchProgress | None:
    """Run Maigret scan inside an isolated background OS thread with its own event loop.

    Keeping this off the main thread ensures 100% UI responsiveness for Flet.
    """
    worker_loop = asyncio.new_event_loop()
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        _old_loop = None
    else:
        _old_loop = asyncio.get_event_loop()
        if _old_loop is not None and _old_loop.is_closed():
            _old_loop = None
    asyncio.set_event_loop(worker_loop)

    last_prog: SearchProgress | None = None
    total_sites = len(sites_to_scan)

    async def _runner():
        nonlocal last_prog
        n_primary = len(targets)

        # Layer-6 DNS pre-warm on the worker loop (never the main Flet loop):
        # resolve the scan's domains ahead of the request flood so aiohttp's
        # per-connector lookups mostly hit the warm OS resolver cache.
        # Bounded and best-effort — can't block or fail the scan itself.
        try:
            from services.cache_service import prewarm_dns

            await prewarm_dns(
                [
                    (name, getattr(site, "url_main", "") or "")
                    for name, site in sites_to_scan.items()
                ]
            )
        except Exception as exc:
            logger.debug("DNS pre-warm skipped: %s", exc)

        # Per-target output containers, kept for the optional recursive
        # second pass (they carry ids_usernames/ids_links when parsing on).
        # Skipped entirely when the tail can't consume them.
        keep_containers = bool(recursive and extract_info)
        containers: dict[str, Any] = {}

        for tgt in targets:
            if cancel_event.is_set():
                break

            progress = SearchProgress(
                username=tgt,
                total_sites=total_sites,
                is_running=True,
            )
            on_progress_cb(progress)

            query_notify = _MaigretQueryNotify(
                total=total_sites,
                cancel_event=cancel_event,
                progress=progress,
                on_progress=on_progress_cb,
                sites_lookup=sites_to_scan,
            )

            output_container: dict[str, Any] = {}
            if keep_containers:
                containers[tgt] = output_container

            try:
                await maigret_search(
                    username=tgt,
                    site_dict=sites_to_scan,
                    logger=logger,
                    **_maigret_kwargs(
                        maigret_search,
                        query_notify=query_notify,
                        proxy=proxy,
                        timeout=timeout,
                        max_connections=max_conns,
                        no_progressbar=True,
                        dns_resolver=dns_res,
                        is_parsing_enabled=extract_info,
                        is_enrich_enabled=deep_enrich,
                        retries=retry_count,
                        output_container=output_container,
                        keywords=keywords,
                        cookies=cookies_path,
                        i2p_proxy=i2p_proxy,
                        check_domains=check_domains,
                    ),
                )
            except asyncio.CancelledError:
                progress.is_cancelled = True
                raise
            except Exception:
                # Mirror the recursive-tail policy: a failing PRIMARY must
                # not kill the remaining targets — log loudly, close out
                # this target, and continue the loop.
                logger.exception("Maigret search failed for %s", tgt)
                progress.is_running = False
            finally:
                progress.is_running = False

            on_progress_cb(progress)
            last_prog = progress
            if after_primary and not cancel_event.is_set():
                # Owner: history must register the moment the PRIMARY pass
                # finishes — the recursive tail may run much longer and the
                # final save (which upserts this entry) comes after it.
                try:
                    after_primary(tgt, progress)
                except Exception:
                    logger.exception("Primary-completion hook failed for %s", tgt)

        # ── Recursive second pass (state.recursive_search, opt-in) ────
        # Depth is capped at 2 BY CONSTRUCTION: ids discovered during these
        # secondary scans are never expanded again.
        if recursive and db is not None and containers and not cancel_event.is_set():
            discovered = _collect_recursive_targets(containers, db, targets)
            # Cross-engine pivot (Batch 10): usernames holehe verified on
            # email results feed maigret secondaries under the same opt-in
            # recursive flag. Read live state — no signature threading.
            try:
                from core.state import state as _app_state

                _email_rows = list(getattr(_app_state, "email_results", None) or [])
            except Exception:
                _email_rows = []
            if _email_rows:
                _have = {t.lower() for t in targets} | {k.lower() for k in discovered}
                for _u in extract_holehe_usernames(_email_rows):
                    if len(discovered) >= RECURSIVE_TARGET_CAP:
                        break
                    if _u.lower() not in _have:
                        _have.add(_u.lower())
                        discovered[_u] = "username"
            if discovered:
                logger.info(
                    "Recursive search: %d secondary target(s): %s",
                    len(discovered),
                    ", ".join(f"{k}({v})" for k, v in list(discovered.items())[:10]),
                )
            else:
                logger.info(
                    "Recursive search: primary pass done, no secondary targets found"
                )
            for new_id, id_type in discovered.items():
                if cancel_event.is_set():
                    break
                if id_type == "username":
                    # Rank-ordered slice of the user's own scope — bounded
                    # even when the primary scan is "All 5.2k".
                    sites2: dict[str, Any] = dict(
                        list(sites_to_scan.items())[:RECURSIVE_USERNAME_SITES]
                    )
                else:
                    try:
                        from core.state import state as app_state

                        sites2 = db.ranked_sites_dict(
                            top=SCAN_ALL,
                            disabled=app_state.ignore_exclusions,
                            excluded_tags=([] if app_state.nsfw_enabled else ["nsfw"]),
                            id_type=id_type,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Recursive scope failed for %s (%s): %s",
                            new_id,
                            id_type,
                            exc,
                        )
                        continue
                if not sites2:
                    continue

                # Same list object as state.search_targets (assigned by
                # reference in search()) — appending keeps the staleness
                # filter in main._apply_progress from dropping secondary ticks.
                # THREADING: worker thread appends while the main loop may
                # iterate state.search_targets; CPython makes append itself
                # atomic, but readers must iterate a snapshot, never live.
                targets.append(new_id)

                progress2 = SearchProgress(
                    username=new_id,
                    total_sites=len(sites2),
                    is_running=True,
                )
                on_progress_cb(progress2)
                notify2 = _MaigretQueryNotify(
                    total=len(sites2),
                    cancel_event=cancel_event,
                    progress=progress2,
                    on_progress=on_progress_cb,
                    sites_lookup=sites2,
                )
                container2: dict[str, Any] = {}
                if keep_containers:
                    containers[new_id] = container2
                try:
                    await maigret_search(
                        username=new_id,
                        site_dict=sites2,
                        logger=logger,
                        **_maigret_kwargs(
                            maigret_search,
                            query_notify=notify2,
                            proxy=proxy,
                            timeout=timeout,
                            max_connections=max_conns,
                            no_progressbar=True,
                            dns_resolver=dns_res,
                            is_parsing_enabled=extract_info,
                            is_enrich_enabled=deep_enrich,
                            retries=retry_count,
                            output_container=container2,
                            id_type=id_type,
                            keywords=keywords,
                            cookies=cookies_path,
                            i2p_proxy=i2p_proxy,
                            check_domains=check_domains,
                        ),
                    )
                except asyncio.CancelledError:
                    progress2.is_cancelled = True
                    raise
                except Exception:
                    # A failing secondary must not kill the whole scan —
                    # log it loudly and move to the next discovered id.
                    logger.exception(
                        "Recursive scan failed for %s (%s)", new_id, id_type
                    )
                finally:
                    progress2.is_running = False
                on_progress_cb(progress2)
                last_prog = progress2

        # Terminal-grade completion trail (owner diagnoses from device logs):
        # one line when the WHOLE pipeline (primary + recursive tail) ends.
        logger.info(
            "Scan worker finished: %d primary target(s), recursive=%s, %d total target(s)",
            n_primary,
            "on" if recursive else "off",
            len(targets),
        )
        return last_prog

    try:
        return worker_loop.run_until_complete(_runner())
    finally:
        pending = asyncio.all_tasks(worker_loop)
        for task in pending:
            task.cancel()
        if pending:
            with contextlib.suppress(Exception):
                worker_loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        worker_loop.close()
        try:
            asyncio.set_event_loop(_old_loop)
        except Exception:
            pass


class SherlockService:
    """Runs high-performance username OSINT searches powered by Maigret across 5,200+ sites."""

    def __init__(self):
        # Cooperative cancel only: the worker thread polls _thread_cancel
        # between targets. There is intentionally no asyncio.Event / task
        # handle — the scan runs in a threadpool thread that cannot be
        # interrupted mid-target; cancel takes effect at target boundaries
        # and suppresses further progress ticks.
        self._thread_cancel = threading.Event()
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
            state.scan_depth,
            tuple(state.unhealthy_sites or ()),
        )

        if not force and self._sites_dict and self._last_config == config:
            return self._total_sites

        try:
            logger.info("Loading Maigret site database...")

            if state.custom_manifest:
                path_arg = state.custom_manifest.strip()
                logger.info("Using custom manifest database: %s", path_arg)
            else:
                # Single source for synced/bundled resolution (the synced
                # check lives in _resolve_local_db — no second copy here).
                # use_local_db skips the synced copy (bundled wins when set).
                path_arg = _resolve_local_db(check_synced=not state.use_local_db)

            def _load_db():
                # Layer-1 cache: reuse the pickled database when the source
                # manifest is unchanged (hybrid mtime-then-SHA256 validation
                # in cache_service). Falls back to a full parse on any miss.
                # Defensive: try_load contractually returns None on miss, but
                # a corrupt-pickle raise must never kill the scan — parse instead.
                from services import cache_service

                try:
                    cached = cache_service.try_load_compiled_db(path_arg)
                except Exception as exc:
                    logger.warning(
                        "Compiled DB cache raised, falling back to parse: %s", exc
                    )
                    cached = None
                if cached is not None:
                    return cached
                db = MaigretDatabase().load_from_path(path_arg)
                cache_service.save_compiled_db(path_arg, db)
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
            # P3-6: drop sites the sampled DB-health panel flagged on the
            # last run (persisted by the controller, cleared by a healthy run).
            unhealthy = {n.lower() for n in (state.unhealthy_sites or [])}
            if unhealthy:
                removed = sum(1 for k in sites_dict if k.lower() in unhealthy)
                if removed:
                    sites_dict = {
                        k: v
                        for k, v in sites_dict.items()
                        if k.lower() not in unhealthy
                    }
                    logger.info("DB health: excluding %d flagged site(s)", removed)
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

            # Layer-5 cache: inverted tag -> names index so SitesScreen chip
            # filtering is an O(1) bucket lookup instead of an O(N) scan.
            # The on-disk copy is trusted only when its hash matches the
            # live DB (a manifest update can change tags under same names).
            try:
                from services import cache_service

                indices = cache_service.build_sites_indices(sites_dict)
                cached = cache_service.load_sites_indices(indices["db_hash"])
                if cached is not None:
                    state.sites_tag_index = cached["by_tag"]
                else:
                    cache_service.save_sites_indices(indices)
                    state.sites_tag_index = indices["by_tag"]
            except Exception as exc:
                logger.warning("Failed to build site tag index: %s", exc)
                state.sites_tag_index = None

            logger.info("Loaded %d Maigret sites", self._total_sites)
            return self._total_sites
        except Exception:
            logger.exception("Failed to load site database")
            return 0

    async def search(
        self,
        username: str,
        on_progress: Callable[[SearchProgress], None],
        timeout: int = 10,
        after_primary: Callable[[str, int, int], None] | None = None,
    ) -> SearchProgress:
        """Run Maigret search on an isolated worker thread with active settings filters.

        Returns the LAST target's SearchProgress only. Per-target truth is
        ``state.target_results`` ({target: SearchProgress}), populated on
        every progress tick via the recording wrapper below. Multi-target
        callers must read state.target_results, not the return value.

        `after_primary(target, found, total)` fires per finished primary
        target (first arg is the per-target id, not the raw query).
        """
        if not _MAIGRET_AVAILABLE:
            raise RuntimeError("Maigret search engine is not available")

        from core.state import state

        targets = parse_usernames(username)
        state.search_targets = targets
        state.target_results = {}
        if not targets:
            raise RuntimeError("No valid usernames specified for scanning")

        # Ensure sites database is loaded (load_sites() early-returns on
        # unchanged config, so this is cheap when nothing changed).
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

        self._thread_cancel.clear()

        proxy = getattr(state, "proxy_url", "") or None
        try:
            max_conns = int(getattr(state, "max_connections", 50))
        except TypeError, ValueError:
            max_conns = 50
        max_conns = max(1, min(max_conns, 200))
        try:
            timeout = int(timeout)
        except TypeError, ValueError:
            timeout = 10
        timeout = max(1, min(timeout, 120))
        dns_res = getattr(state, "dns_resolver", "threaded")
        # On Android / mobile platforms, always use ThreadedResolver (getaddrinfo via OS netd).
        # aiodns / c-ares requires /etc/resolv.conf which does not exist on Android,
        # causing [Could not contact DNS servers] for all major platforms.
        is_mobile = False
        try:
            from flet import context

            if context.page and hasattr(context.page, "platform"):
                is_mobile = context.page.platform.is_mobile()
        except Exception:
            pass
        if is_mobile or not dns_res:
            dns_res = "threaded"
        extract_info = getattr(state, "extract_info", True)
        try:
            retry_count = int(getattr(state, "retries", 0))
        except TypeError, ValueError:
            retry_count = 0
        retry_count = max(0, min(retry_count, 5))
        recursive = bool(getattr(state, "recursive_search", False))
        # P3-3/P3-7/P3-9 knobs (is_mobile computed above for DNS).
        deep_enrich = bool(getattr(state, "deep_enrich", False))
        raw_kw = (getattr(state, "search_keywords", "") or "").strip()
        keywords = [k.strip() for k in raw_kw.split(",") if k.strip()] or None
        cookies_path = (getattr(state, "cookies_path", "") or "").strip() or None
        i2p_proxy = (getattr(state, "i2p_proxy", "") or "").strip() or None
        # Domain checks use aiodns — dead on Android (/etc/resolv.conf).
        check_domains = bool(getattr(state, "check_domains", False)) and not is_mobile

        # Bridge the worker-thread primary-completion hook to the caller's
        # (target, found, total) signature — main saves history through it.
        # First arg is the per-target id, NOT the raw multi-target query.
        def _after_primary(tgt: str, prog: SearchProgress) -> None:
            if after_primary is not None:
                after_primary(tgt, len(prog.found), prog.total_sites)

        def _recording_progress(prog: SearchProgress) -> None:
            """Store per-target truth, then forward to the caller."""
            try:
                state.target_results[prog.username] = prog
            except Exception:
                pass
            on_progress(prog)

        # Execute on isolated background thread
        res = await asyncio.to_thread(
            _run_maigret_worker_thread,
            targets=targets,
            sites_to_scan=sites_to_scan,
            proxy=proxy,
            timeout=timeout,
            max_conns=max_conns,
            dns_res=dns_res,
            extract_info=extract_info,
            retry_count=retry_count,
            cancel_event=self._thread_cancel,
            on_progress_cb=_recording_progress,
            db=self._db,
            recursive=recursive,
            deep_enrich=deep_enrich,
            keywords=keywords,
            cookies_path=cookies_path,
            i2p_proxy=i2p_proxy,
            check_domains=check_domains,
            after_primary=_after_primary if after_primary else None,
        )

        for tgt in targets:
            if tgt not in state.target_results:
                state.target_results[tgt] = SearchProgress(
                    username=tgt,
                    total_sites=total_sites,
                    is_cancelled=True,
                )
            elif self._thread_cancel.is_set() and state.target_results[tgt].is_running:
                _mark_cancelled(state.target_results[tgt])

        # Last-target-only by contract; see docstring. Multi-target callers
        # must read state.target_results.
        return res or SearchProgress(
            username=targets[0] if targets else username.strip(),
            total_sites=total_sites,
        )

    async def run_db_health(
        self,
        sample_size: int = 25,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Sampled DB health (P3-6): probe N random enabled sites off-scan.

        Never auto-disables (auto_disable=False): results come back for the
        controller to surface (snackbar + terminal log) and persist as an
        exclusion hint consumed by load_sites().
        """
        if not _MAIGRET_AVAILABLE:
            return {"error": "maigret unavailable"}
        import random as _random

        from maigret.checking import self_check

        from core.state import state

        try:
            sample_size = int(sample_size)
        except TypeError, ValueError:
            sample_size = 25
        sample_size = max(1, min(sample_size, 200))
        cancel = cancel_event or self._thread_cancel

        if self._db is None:
            await self.load_sites()
        if self._db is None:
            return {"error": "site database unavailable"}
        if cancel.is_set():
            return {
                "error": "cancelled",
                "sample": 0,
                "ok": 0,
                "flagged": 0,
                "unhealthy": [],
                "details": [],
            }
        try:
            # MaigretDatabase.sites is a LIST (on-device crash this fixes:
            # "'list' object has no attribute 'values'").
            raw_sites = self._db.sites
            iterable = raw_sites.values() if hasattr(raw_sites, "values") else raw_sites
            candidates = [s for s in iterable if not getattr(s, "disabled", False)]
            if not candidates:
                return {"error": "no enabled sites to check"}
            sample = _random.sample(candidates, min(sample_size, len(candidates)))
            site_data = {s.name: s for s in sample}
            logger.info(
                "DB health: probing %d/%d sites...", len(site_data), len(candidates)
            )
            if cancel.is_set():
                return {
                    "error": "cancelled",
                    "sample": len(site_data),
                    "ok": 0,
                    "flagged": 0,
                    "unhealthy": [],
                    "details": [],
                }
            res = await self_check(
                self._db,
                site_data,
                logger,
                silent=True,
                max_connections=10,
                no_progressbar=True,
                dns_resolver="threaded",
                proxy=(getattr(state, "proxy_url", "") or "") or None,
            )
            results = res.get("results", []) if isinstance(res, dict) else []
            flagged = [r for r in results if r.get("issues")]
            summary = {
                "sample": len(site_data),
                "ok": len(site_data) - len(flagged),
                "flagged": len(flagged),
                "unhealthy": [r.get("site_name", "?") for r in flagged],
                "details": [
                    f"{r.get('site_name', '?')}: {'; '.join(r.get('issues') or [])}"
                    for r in flagged
                ],
            }
            logger.info(
                "DB health: %d/%d OK · %d flagged%s",
                summary["ok"],
                summary["sample"],
                summary["flagged"],
                (" — " + ", ".join(summary["unhealthy"][:8])) if flagged else "",
            )
            return summary
        except Exception as exc:
            # Visible failure path (owner rule) — the settings layer also
            # snackbars this, so it can never be a silently eaten task.
            logger.exception("DB health check failed")
            return {"error": f"DB health check failed: {exc}"}

    def cancel(self) -> None:
        """Signal cancel — cooperative, between-target boundary only.

        The scan runs in a threadpool thread that cannot be interrupted
        mid-target: in-flight site checks drain in the background while the
        worker stops ticking progress at the next target boundary.
        """
        self._thread_cancel.set()

        from core.state import state

        for tgt in state.target_results:
            prog = state.target_results[tgt]
            if prog.is_running:
                _mark_cancelled(prog)
