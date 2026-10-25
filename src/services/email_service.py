"""Email OSINT service — wraps user-scanner (email_scan modules).

Drives user-scanner's email validators directly (not run_email_full_batch, which
is CLI-coupled). Preserves the original Sherlock contract (EmailResult /
EmailSearchProgress) so the UI and controller need no changes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Ensure httpx monkeypatch from email_orchestrator is loaded so all 220
# email modules inherit proxy and timeout configurations
try:
    import user_scanner.core.email_orchestrator  # noqa: F401
except Exception:
    pass

from services.user_scanner_compat import (
    load_email_modules,
    run_email_scan,
)

logger = logging.getLogger(__name__)

EMAIL_FORMAT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_RATE_LIMITED_RE = re.compile(
    r"\b(?:403|429|503)\b|rate.?limit|too many requests|throttl|cloudflare|captcha|forbidden|waf|blocked",
    re.IGNORECASE,
)


def validate_email(email: str) -> bool:
    # Prefer user-scanner's stricter validator when available.
    try:
        from user_scanner.core.helpers import is_valid_email
        return bool(is_valid_email(email))
    except Exception:
        return bool(EMAIL_FORMAT.fullmatch(email or ""))


@dataclass
class EmailResult:
    name: str = ""
    domain: str = ""
    method: str = ""
    exists: bool | None = None
    rate_limit: bool = False
    frequent_rate_limit: bool = False
    unavailable: bool = False
    email_recovery: str | None = None
    phone_number: str | None = None
    others: dict | None = None
    # The upstream engine Result this row was mapped from (set by the
    # mapper; None for rows rebuilt from cached snapshots). Lets
    # engine-native exporters see the exact upstream object.
    raw: Any = None


@dataclass
class EmailSearchProgress:
    email: str = ""
    total_modules: int = 0
    checked_modules: int = 0
    found: list[EmailResult] = field(default_factory=list)
    not_found: list[EmailResult] = field(default_factory=list)
    rate_limited: list[EmailResult] = field(default_factory=list)
    unavailable: list[EmailResult] = field(default_factory=list)
    is_running: bool = False
    is_cancelled: bool = False


def _is_rate_limited(message: str | None) -> bool:
    return bool(_RATE_LIMITED_RE.search(message or ""))


def _domain_from(name: str, url: str | None) -> str:
    if url and str(url).startswith(("http://", "https://")):
        from urllib.parse import urlparse
        host = urlparse(str(url)).netloc.lower().split(":")[0]
        if "." in host:
            return host.removeprefix("www.")
    return name.lower().replace("_", ".")


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    if isinstance(value, str):
        return value or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def _recovery_from(extra: dict) -> str | None:
    for key in ("email", "recovery_email", "emailrecovery"):
        v = _first(extra.get(key))
        if v:
            return str(v)
    v = _first(extra.get("public_emails"))
    return str(v) if v else None


def _phone_from(extra: dict) -> str | None:
    for key in ("phone", "phone_masked", "phone_number", "phoneNumber"):
        v = _first(extra.get(key))
        if v:
            return str(v)
    v = _first(extra.get("phone_numbers") or extra.get("phones"))
    return str(v) if v else None


def _map_result(name: str, r: Any) -> EmailResult:
    from user_scanner.core.result import Status

    domain = _domain_from(name, getattr(r, "url", None))

    def _safe(v):
        if isinstance(v, (str, int, float, bool, type(None))):
            return v
        if isinstance(v, (list, tuple)):
            return [_safe(x) for x in v]
        if isinstance(v, dict):
            return {str(k): _safe(val) for k, val in v.items()}
        return str(v)

    _extra = getattr(r, "extra", None) or {}
    _media = getattr(r, "media", None) or {}
    extra = {str(k): _safe(v) for k, v in (_extra.items() if isinstance(_extra, dict) else {}.items())}
    media = {str(k): _safe(v) for k, v in (_media.items() if isinstance(_media, dict) else {}.items())}
    others = {
        "message": _safe(getattr(r, "reason", None)),
        "url": _safe(getattr(r, "url", None)),
        "extra": extra,
        "media": media,
    }
    confidence = extra.get("confidence")
    if confidence:
        others["confidence"] = str(confidence).lower()
    pivot_source = extra.get("pivot_source")
    if pivot_source:
        others["pivot_source"] = str(pivot_source)

    status = getattr(r, "status", None)
    if status == Status.TAKEN:
        return EmailResult(
            name=name, domain=domain, exists=True,
            email_recovery=_recovery_from(extra),
            phone_number=_phone_from(extra),
            others=others,
            raw=r,
        )
    if status == Status.AVAILABLE:
        return EmailResult(name=name, domain=domain, exists=False, others=others, raw=r)

    message = getattr(r, "get_reason", lambda: "")() if hasattr(r, "get_reason") else str(getattr(r, "reason", "") or "")
    rate = _is_rate_limited(message)
    return EmailResult(
        name=name, domain=domain, exists=None,
        rate_limit=rate, unavailable=not rate,
        email_recovery=_recovery_from(extra),
        phone_number=_phone_from(extra),
        others=others,
        raw=r,
    )


class EmailService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._cancel_token = threading.Event()
        self._generation: int = 0
        self._progress: EmailSearchProgress | None = None
        self._modules: list[tuple[str, Any]] | None = None

    async def load_sites(self, mode: str = "email", force: bool = False) -> int:
        from core.state import state as app_state
        if self._modules is None or force:
            nsfw = not getattr(app_state, "nsfw_enabled", True)
            self._modules = await asyncio.to_thread(load_email_modules, no_nsfw=nsfw)
        total = len(self._modules)
        app_state.sites_total = total
        from services.user_scanner_compat import get_site_name_user
        app_state.sites_cache = sorted({get_site_name_user(m) for _, m in self._modules})
        app_state.sites_tags_map = {get_site_name_user(m): [cat] for cat, m in self._modules}
        app_state.sites_version += 1
        by_tag: dict[str, list[str]] = {}
        for cat, m in self._modules:
            by_tag.setdefault(cat, []).append(get_site_name_user(m))
        app_state.sites_tag_index = by_tag
        return total

    @property
    def is_available(self) -> bool:
        return True

    @property
    def total_modules(self) -> int:
        from core.state import state as app_state
        if self._modules is None:
            self._modules = load_email_modules(no_nsfw=not getattr(app_state, "nsfw_enabled", True))
        return len(self._modules)

    async def search(
        self,
        email: str,
        on_progress: Callable[[EmailSearchProgress], None] | None = None,
        timeout: int = 10,
        skip_password_recovery: bool = False,
        concurrency: int = 15,
        use_curl_cffi: bool = True,
        proxy: str = "",
        *,
        use_stealth_fingerprint: bool | None = None,
    ) -> EmailSearchProgress:
        if not validate_email(email):
            raise ValueError(f"Invalid email address: {email}")

        from core.state import state as app_state

        if self._modules is None:
            self._modules = await asyncio.to_thread(
                load_email_modules, no_nsfw=not getattr(app_state, "nsfw_enabled", True)
            )

        modules = list(self._modules)
        if skip_password_recovery:
            from services.user_scanner_compat import get_site_name_user, is_loud_user

            modules = [
                m
                for m in modules
                if not is_loud_user(get_site_name_user(m[1]), is_email=True)
            ]

        self._generation += 1
        cancel_token = threading.Event()
        self._cancel_token = cancel_token

        # Global timeout and proxy manager handling
        from user_scanner.core.helpers import (
            get_global_timeout,
            set_global_timeout,
            set_proxy_manager,
        )

        old_timeout = None
        try:
            old_timeout = get_global_timeout()
            set_global_timeout(float(timeout))
        except Exception:
            pass

        try:
            if proxy:
                set_proxy_manager(proxies=[proxy])
            else:
                set_proxy_manager(None, None)
        except Exception:
            pass

        progress = EmailSearchProgress(email=email, total_modules=len(modules), is_running=True)
        self._progress = progress

        last_update = [time.monotonic()]

        def _notify():
            if on_progress is not None:
                try:
                    on_progress(EmailSearchProgress(
                        email=progress.email,
                        total_modules=progress.total_modules,
                        checked_modules=progress.checked_modules,
                        found=list(progress.found),
                        not_found=list(progress.not_found),
                        rate_limited=list(progress.rate_limited),
                        unavailable=list(progress.unavailable),
                        is_running=progress.is_running,
                        is_cancelled=progress.is_cancelled,
                    ))
                except Exception:
                    logger.debug("on_progress failed", exc_info=True)

        def _on_result(item):
            if cancel_token.is_set():
                return
            if not item:
                return
            kind = item[0]
            if kind == "skipped":
                _, _cat, site_name, _ = item
                res = EmailResult(
                    name=site_name, domain=_domain_from(site_name, None), exists=None, unavailable=True,
                    others={"message": "skipped (loud)", "url": None, "extra": {}, "media": {}}
                )
                progress.unavailable.append(res)
                progress.checked_modules += 1
            elif kind == "error":
                _, _cat, site_name, exc = item
                res = EmailResult(
                    name=site_name, domain=_domain_from(site_name, None), exists=None, unavailable=True,
                    others={"message": str(exc), "url": None, "extra": {}, "media": {}}
                )
                progress.unavailable.append(res)
                progress.checked_modules += 1
            elif kind == "result":
                _, _cat, site_name, r = item
                res = _map_result(site_name, r)
                if res.rate_limit:
                    progress.rate_limited.append(res)
                elif res.unavailable:
                    progress.unavailable.append(res)
                elif res.exists:
                    progress.found.append(res)
                else:
                    progress.not_found.append(res)
                progress.checked_modules += 1

            now = time.monotonic()
            if now - last_update[0] >= 0.25 or progress.checked_modules == progress.total_modules:
                last_update[0] = now
                _notify()

        try:
            await asyncio.to_thread(
                self._run_worker, email, modules, timeout, concurrency, _on_result, progress, cancel_token
            )
        except asyncio.CancelledError:
            cancel_token.set()
            progress.is_cancelled = True
            raise
        finally:
            progress.is_running = False
            if cancel_token.is_set():
                progress.is_cancelled = True
            try:
                set_global_timeout(old_timeout)
            except Exception:
                pass
            try:
                set_proxy_manager(None, None)
            except Exception:
                pass
            _notify()

        return progress

    def _run_worker(self, email, modules, timeout, concurrency, on_result, progress, cancel_token):
        from core.state import state

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        raw_results: list[Any] = []

        def _collector(item):
            if item and item[0] == "result":
                raw_results.append(item[3])
            on_result(item)

        async def _run():
            await run_email_scan(
                email,
                modules,
                _collector,
                cancel_token,
                timeout=timeout,
                concurrency=concurrency,
                allow_loud=getattr(state, "allow_loud", False),
            )
            if getattr(state, "cross_scan_enabled", False) and not cancel_token.is_set():
                try:
                    from user_scanner.core.cross_scan import CrossScanConfig

                    from services.user_scanner_compat import (
                        load_user_modules,
                        run_cross_scan_async,
                    )

                    cross_cfg = CrossScanConfig(
                        links=getattr(state, "cross_links", "all") or "all",
                        emails=getattr(state, "cross_emails", "verified") or "verified",
                        depth=int(getattr(state, "cross_depth", 1) or 1),
                        sweep=int(getattr(state, "cross_sweep", 3) or 3),
                    )
                    user_mods = load_user_modules(
                        no_nsfw=not getattr(state, "nsfw_enabled", True)
                    )
                    await run_cross_scan_async(
                        initial_results=raw_results,
                        all_user_modules=user_mods,
                        all_email_modules=modules,
                        cross_config=cross_cfg,
                        on_result=_collector,
                        cancel_event=cancel_token,
                        timeout=timeout,
                        concurrency=concurrency,
                        allow_loud=getattr(state, "allow_loud", False),
                        no_nsfw=not getattr(state, "nsfw_enabled", True),
                        proxy=getattr(state, "proxy_url", "") or None,
                    )
                except Exception as exc:
                    logger.warning("email cross-scan pass failed: %s", exc)

        try:
            loop.run_until_complete(_run())
        except Exception:
            logger.exception("email scan worker failed")
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

    def run_hudson(self, target: str, is_email: bool = True) -> str:
        import contextlib
        import io
        import re

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

    def cancel(self) -> None:
        if self._cancel_token is not None:
            self._cancel_token.set()
        progress = self._progress
        if progress is not None:
            progress.is_cancelled = True
            progress.is_running = False
