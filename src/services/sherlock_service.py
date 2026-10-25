"""Username OSINT service — wraps user-scanner (user_scan modules).

Drives user-scanner's module validators directly (not run_user_full, which
is CLI-coupled: rich Progress + print() + blocking asyncio.run()). Mirrors
the original Sherlock service contract (SiteResult / SearchProgress) so the
UI and controller need no changes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.state import state
from services.user_scanner_compat import (
    load_email_modules,
    load_user_modules,
    run_cross_scan_async,
    run_username_scan,
)

logger = logging.getLogger(__name__)


@dataclass
class SiteResult:
    site_name: str = ""
    url_main: str = ""
    url_user: str = ""
    status: str = "Available"
    http_status: str = ""
    query_time: float | None = None
    context: str | None = None
    tags: list[str] = field(default_factory=list)
    ids_data: dict | None = None
    error_type: str | None = None
    error_hint: str = ""
    protection: list[str] = field(default_factory=list)
    badge: str = ""
    keyword_hit: bool = False
    # The upstream engine Result this row was mapped from (set by the
    # mapper; None for rows rebuilt from cached snapshots). Lets
    # engine-native exporters see the exact upstream object.
    raw: Any = None


@dataclass
class SearchProgress:
    username: str = ""
    total_sites: int = 0
    checked_sites: int = 0
    found: list[SiteResult] = field(default_factory=list)
    not_found: list[SiteResult] = field(default_factory=list)
    errors: list[SiteResult] = field(default_factory=list)
    skipped: list[SiteResult] = field(default_factory=list)
    is_running: bool = False
    is_cancelled: bool = False


def parse_usernames(raw: str) -> list[str]:
    items = [i.strip() for i in (raw or "").split(",")] if "," in (raw or "") else (raw or "").split()
    resolved = []
    for item in items:
        item = item.strip()
        if item:
            resolved.append(item)
    seen: set[str] = set()
    unique: list[str] = []
    for item in resolved:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


_RATE_LIMITED_RE = re.compile(
    r"\b(?:403|429|503)\b|rate.?limit|too many requests|throttl|cloudflare|captcha|forbidden|waf|blocked",
    re.IGNORECASE,
)


def _badge_for(reason: str | None, status: str) -> str:
    if status == "Skipped":
        return ""
    low = (reason or "").lower()
    if any(s in low for s in ("cloudflare", "captcha", "datadome", "waf", "bot")):
        return "bot"
    if _RATE_LIMITED_RE.search(low):
        if "403" in low or "forbidden" in low or "blocked" in low or "waf" in low:
            return "bot"
        return "rate"
    if "timeout" in low or "connection" in low or "dns" in low:
        return "dead"
    if status == "Error":
        return "error"
    return ""


class SherlockService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._cancel_token = threading.Event()
        self._generation: int = 0
        self._modules: list[tuple[str, Any]] | None = None

    @property
    def is_available(self) -> bool:
        return True

    async def load_sites(self, force: bool = False, mode: str = "username") -> int:
        from user_scanner.core.helpers import set_global_timeout
        try:
            set_global_timeout(float(getattr(state, "timeout", 10) or 10))
        except Exception:
            pass
        if self._modules is not None and not force and getattr(self, "_modules_mode", None) == mode:
            total = len(self._modules)
        else:
            nsfw = not getattr(state, "nsfw_enabled", True)
            if mode == "email":
                from services.user_scanner_compat import load_email_modules
                self._modules = await asyncio.to_thread(load_email_modules, no_nsfw=nsfw)
            else:
                self._modules = await asyncio.to_thread(load_user_modules, no_nsfw=nsfw)
            self._modules_mode = mode
            total = len(self._modules)
        state.sites_total = total
        from services.user_scanner_compat import get_site_name_user
        names = [get_site_name_user(m) for _, m in self._modules]
        state.sites_cache = sorted(set(names))
        state.sites_tags_map = {get_site_name_user(m): [cat] for cat, m in self._modules}
        state.sites_version += 1
        # inverted tag index
        by_tag: dict[str, list[str]] = {}
        for cat, m in self._modules:
            by_tag.setdefault(cat, []).append(m.__name__.split(".")[-1])
        state.sites_tag_index = by_tag
        logger.info("user-scanner: loaded %d modules", total)
        return total

    async def search(
        self,
        username: str,
        on_progress: Callable[[SearchProgress], None] | None = None,
        timeout: int = 10,
        after_primary: Callable[[str, int, int], None] | None = None,
    ) -> SearchProgress:
        from core.state import state as app_state

        targets = parse_usernames(username)
        app_state.search_targets = targets
        app_state.target_results = {}
        if not targets:
            raise RuntimeError("No valid usernames specified for scanning")

        await self.load_sites()

        all_modules = self._modules or load_user_modules(no_nsfw=not getattr(app_state, "nsfw_enabled", True))
        selected = {s.lower() for s in (app_state.selected_sites or [])} if app_state.selected_sites else None

        self._generation += 1
        cancel_token = threading.Event()
        self._cancel_token = cancel_token

        last_prog: SearchProgress | None = None

        try:
            last_prog = await asyncio.to_thread(
                self._run_worker, targets, all_modules, selected, timeout, on_progress, after_primary, app_state, cancel_token
            )
        except asyncio.CancelledError:
            logger.info("username scan cancelled")
            cancel_token.set()

        for tgt in targets:
            prog = app_state.target_results.get(tgt)
            if prog is None:
                app_state.target_results[tgt] = SearchProgress(username=tgt, total_sites=len(all_modules), is_cancelled=cancel_token.is_set())
            elif cancel_token.is_set():
                prog.is_running = False
                prog.is_cancelled = True

        if last_prog is not None:
            if cancel_token.is_set():
                last_prog.is_cancelled = True
                last_prog.is_running = False
            return last_prog
        return SearchProgress(
            username=targets[0] if targets else username,
            total_sites=len(all_modules),
            is_cancelled=cancel_token.is_set(),
        )

    def cancel(self) -> None:
        if self._cancel_token is not None:
            self._cancel_token.set()

    async def _run(self, targets, all_modules, selected, timeout, on_progress, after_primary, app_state, cancel_token):
        total = len(all_modules)
        last_prog = None

        def _notify(prog: SearchProgress) -> None:
            if on_progress:
                try:
                    on_progress(
                        SearchProgress(
                            username=prog.username,
                            total_sites=prog.total_sites,
                            checked_sites=prog.checked_sites,
                            found=list(prog.found),
                            not_found=list(prog.not_found),
                            errors=list(prog.errors),
                            skipped=list(prog.skipped),
                            is_running=prog.is_running,
                            is_cancelled=prog.is_cancelled,
                        )
                    )
                except Exception:
                    logger.debug("on_progress notification failed", exc_info=True)

        for tgt in targets:
            if cancel_token.is_set():
                break
            progress = SearchProgress(username=tgt, total_sites=total, is_running=True)
            _notify(progress)
            app_state.target_results[tgt] = progress

            raw_results: list[Any] = []

            def _on_result(item, progress=progress, raw_results=raw_results):
                if cancel_token.is_set():
                    return
                if not item:
                    return
                kind = item[0]
                if kind == "result":
                    _, cat, _site_name, r = item
                    raw_results.append(r)
                    sr = _map_username_result(r, cat)
                    progress.checked_sites += 1
                    if sr.status == "Claimed":
                        progress.found.append(sr)
                    elif sr.status == "Available":
                        progress.not_found.append(sr)
                    elif sr.status == "Skipped":
                        progress.skipped.append(sr)
                    else:
                        progress.errors.append(sr)
                    _notify(progress)
                elif kind in ("skipped", "error"):
                    progress.checked_sites += 1
                    _notify(progress)

            try:
                await run_username_scan(
                    tgt, all_modules, _on_result, cancel_token,
                    timeout=timeout, concurrency=getattr(app_state, "max_connections", 50) or 50,
                    allow_loud=getattr(app_state, "allow_loud", False),
                    no_nsfw=not getattr(app_state, "nsfw_enabled", True),
                    selected=selected,
                    proxy=getattr(app_state, "proxy_url", "") or None,
                )

                if after_primary and not cancel_token.is_set():
                    try:
                        after_primary(tgt, len(progress.found), progress.total_sites)
                    except Exception:
                        logger.exception("primary-completion hook failed for %s", tgt)

                # Cross-scan secondary pivot rounds
                if getattr(app_state, "cross_scan_enabled", False) and not cancel_token.is_set():
                    try:
                        from user_scanner.core.cross_scan import CrossScanConfig
                        selected_cats = getattr(app_state, "selected_categories", None)
                        cross_cfg = CrossScanConfig(
                            links=getattr(app_state, "cross_links", "all") or "all",
                            emails=getattr(app_state, "cross_emails", "verified") or "verified",
                            depth=int(getattr(app_state, "cross_depth", 1) or 1),
                            sweep=int(getattr(app_state, "cross_sweep", 3) or 3),
                            modules=list(app_state.selected_sites) if app_state.selected_sites else None,
                            categories=list(selected_cats) if selected_cats else None,
                        )
                        email_mods = load_email_modules(no_nsfw=not getattr(app_state, "nsfw_enabled", True))
                        await run_cross_scan_async(
                            initial_results=raw_results,
                            all_user_modules=all_modules,
                            all_email_modules=email_mods,
                            cross_config=cross_cfg,
                            on_result=_on_result,
                            cancel_event=cancel_token,
                            timeout=timeout,
                            concurrency=getattr(app_state, "max_connections", 50) or 50,
                            allow_loud=getattr(app_state, "allow_loud", False),
                            no_nsfw=not getattr(app_state, "nsfw_enabled", True),
                            selected=selected,
                            proxy=getattr(app_state, "proxy_url", "") or None,
                        )
                        # Re-map confidence badge for found results after cross-scan computes confidence
                        for sr in progress.found:
                            if sr.raw is not None:
                                conf = (getattr(sr.raw, "extra", None) or {}).get("confidence")
                                if conf:
                                    sr.badge = str(conf).lower()
                    except Exception as exc:
                        logger.warning("cross-scan pass failed: %s", exc)
            except Exception as exc:
                logger.warning("username scan failed for %s: %s", tgt, exc)
            finally:
                progress.is_running = False
                if cancel_token.is_set():
                    progress.is_cancelled = True

            _notify(progress)
            last_prog = progress
        return last_prog

    def _run_worker(self, targets, all_modules, selected, timeout, on_progress, after_primary, app_state, cancel_token):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._run(targets, all_modules, selected, timeout, on_progress, after_primary, app_state, cancel_token)
            )
        except Exception:
            logger.exception("username scan worker failed")
            return None
        finally:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for t in pending:
                t.cancel()
            if pending:
                with contextlib.suppress(Exception):
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass

    def run_hudson(self, target: str, is_email: bool = False) -> str:
        """Run Hudson Rock breach-intel check; capture printed output."""
        import io

        from user_scanner.core import hudson

        try:
            hudson.update_hudson_preference(False)
        except Exception:
            pass

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                hudson.run_hudson_scan(target, is_email=is_email)
        except Exception as exc:
            logger.warning("hudson scan failed: %s", exc)
            return f"Hudson check failed: {exc}"
        raw = buf.getvalue().strip()
        clean = re.sub(r"\x1b\[[0-9;]*m", "", raw).strip()
        return clean or "Hudson Rock check complete: no findings."

    async def run_db_health(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"error": "user-scanner: no site DB"}


def _map_username_result(r: Any, category: str) -> SiteResult:
    from user_scanner.core.result import Status

    # Robust mapping via the engine Status enum (TAKEN/AVAILABLE/SKIPPED/ERROR).
    status_str = "Claimed"
    status = getattr(r, "status", None)
    try:
        if status == Status.TAKEN:
            status_str = "Claimed"
        elif status == Status.AVAILABLE:
            status_str = "Available"
        elif status == Status.SKIPPED:
            status_str = "Skipped"
        elif status == Status.ERROR:
            status_str = "WAF" if _badge_for(str(r.get_reason() if hasattr(r, "get_reason") else ""), "Error") == "bot" else "Error"
    except Exception:
        pass

    reason = ""
    try:
        reason = r.get_reason() if hasattr(r, "get_reason") else str(r.reason)
    except Exception:
        reason = str(getattr(r, "reason", "") or "")

    extra = getattr(r, "extra", None) or {}
    media = getattr(r, "media", None) or {}
    # JSON-safe: coerce non-primitive values (exceptions, objects) to str
    def _safe(v):
        if isinstance(v, (str, int, float, bool, type(None))):
            return v
        if isinstance(v, (list, tuple)):
            return [_safe(x) for x in v]
        if isinstance(v, dict):
            return {str(k): _safe(val) for k, val in v.items()}
        return str(v)
    extra = {str(k): _safe(v) for k, v in (extra.items() if isinstance(extra, dict) else {}.items())}
    media = {str(k): _safe(v) for k, v in (media.items() if isinstance(media, dict) else {}.items())}
    ids_data = {"extra": extra, "media": media} if (extra or media) else None
    badge = _badge_for(reason, status_str)
    confidence = extra.get("confidence")
    if status_str == "Claimed" and confidence:
        badge = str(confidence).lower()

    pivot_source = extra.get("pivot_source")
    tags = [category]
    if pivot_source:
        tags.append(f"pivot:{pivot_source}")

    return SiteResult(
        site_name=getattr(r, "site_name", "") or "",
        url_main="",
        url_user=getattr(r, "url", "") or "",
        status=status_str,
        http_status="",
        query_time=None,
        context=pivot_source,
        tags=tags,
        ids_data=ids_data,
        error_type=reason if status_str in ("Error", "WAF") else None,
        error_hint="",
        protection=[],
        badge=badge,
        keyword_hit=False,
        raw=r,
    )
