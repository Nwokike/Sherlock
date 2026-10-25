"""Phone OSINT service — wraps phonsint.

Drives phonsint's module validators directly. Preserves a Sherlock-style
contract (PhoneResult / PhoneSearchProgress) with real URLs, E.164 normalization,
and proper result bucketing.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from services.email_service import _is_rate_limited
from services.user_scanner_compat import (
    get_site_name_phone,
    load_phone_modules,
    run_phone_scan,
)

logger = logging.getLogger(__name__)


@dataclass
class PhoneResult:
    name: str = ""  # site name
    category: str = ""
    exists: bool | None = None  # True=Registered, False=Not Registered, None=error
    unavailable: bool = False
    rate_limit: bool = False
    url: str = ""
    url_main: str = ""
    url_user: str = ""
    domain: str = ""
    phone: str = ""
    extra: dict | None = None
    media: dict | None = None
    reason: str = ""
    raw: Any = None


@dataclass
class PhoneSearchProgress:
    phone: str = ""
    total_modules: int = 0
    checked_modules: int = 0
    found: list[PhoneResult] = field(default_factory=list)
    not_found: list[PhoneResult] = field(default_factory=list)
    rate_limited: list[PhoneResult] = field(default_factory=list)
    unavailable: list[PhoneResult] = field(default_factory=list)
    errors: list[PhoneResult] = field(default_factory=list)
    is_running: bool = False
    is_cancelled: bool = False


def _domain_from_url(url: str | None, fallback: str) -> str:
    if url and str(url).startswith(("http://", "https://")):
        host = urlparse(str(url)).netloc.lower().split(":")[0]
        if "." in host:
            return host.removeprefix("www.")
    return fallback.lower().replace("_", ".")


def _map_result(cat: str, site_name: str, r: Any, phone_info: Any) -> PhoneResult:
    from phonsint.core.result import Status

    url = getattr(r, "url", "") or ""
    domain = _domain_from_url(url, site_name)
    extra = dict(getattr(r, "extra", None) or {})
    media = dict(getattr(r, "media", None) or {})
    reason = ""
    try:
        reason = r.get_reason() if hasattr(r, "get_reason") else str(getattr(r, "reason", "") or "")
    except Exception:
        reason = str(getattr(r, "reason", "") or "")

    status = getattr(r, "status", None)
    if status == Status.TAKEN:
        exists = True
    elif status == Status.AVAILABLE:
        exists = False
    elif status == Status.SKIPPED:
        exists = None
    else:
        exists = None

    unavailable = (status == Status.ERROR) or (status == Status.SKIPPED)
    rate_limit = _is_rate_limited(reason)
    phone_e164 = getattr(r, "phone", None) or getattr(phone_info, "e164", "")

    return PhoneResult(
        name=site_name,
        category=cat,
        exists=exists,
        unavailable=unavailable and not rate_limit,
        rate_limit=rate_limit,
        url=url,
        url_main=url,
        url_user=url,
        domain=domain,
        phone=phone_e164,
        extra=extra,
        media=media,
        reason=reason,
        raw=r,
    )


class PhoneService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._cancel_token = threading.Event()
        self._thread_cancel = self._cancel_token
        self._worker_loop: asyncio.AbstractEventLoop | None = None
        self._generation: int = 0
        self._progress: PhoneSearchProgress | None = None
        self._modules: list[tuple[str, Any]] | None = None

    async def load_sites(self, force: bool = False) -> int:
        if self._modules is None or force:
            self._modules = await asyncio.to_thread(load_phone_modules)
        total = len(self._modules)
        from core.state import state as app_state

        app_state.sites_total = total
        app_state.sites_cache = sorted({get_site_name_phone(m) for _, m in self._modules})
        app_state.sites_tags_map = {get_site_name_phone(m): [cat] for cat, m in self._modules}
        app_state.sites_version += 1
        by_tag: dict[str, list[str]] = {}
        for cat, m in self._modules:
            by_tag.setdefault(cat, []).append(get_site_name_phone(m))
        app_state.sites_tag_index = by_tag
        return total

    @property
    def is_available(self) -> bool:
        try:
            import phonsint  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def total_modules(self) -> int:
        if self._modules is None:
            self._modules = load_phone_modules()
        return len(self._modules)

    async def search(
        self,
        phone: str,
        region: str | None = None,
        on_progress: Callable[[PhoneSearchProgress], None] | None = None,
        timeout: float = 15.0,
        concurrency: int = 15,
        allow_loud: bool = False,
        proxy: str = "",
        category_filter: str | None = None,
        module_filter: str | None = None,
    ) -> PhoneSearchProgress:
        from phonsint.core.parser import parse_phone_number

        # Parse number to inspect validity and normalise
        phone_info = parse_phone_number(phone, region)
        normalized_phone = phone_info.e164 if phone_info.is_valid else phone

        if self._modules is None:
            self._modules = await asyncio.to_thread(load_phone_modules)

        modules = list(self._modules)
        if category_filter:
            cats = {c.strip().lower() for c in category_filter.split(",") if c.strip()}
            modules = [m for m in modules if m[0].lower() in cats]
        if module_filter:
            mods = {m.strip().lower() for m in module_filter.split(",") if m.strip()}
            modules = [m for m in modules if m[1].__name__.split(".")[-1].lower() in mods]

        self._generation += 1
        cancel_token = threading.Event()
        self._cancel_token = cancel_token
        self._thread_cancel = cancel_token

        # Forward timeout and proxy to phonsint impersonate engine
        import phonsint.core.impersonate as p_imp

        old_timeout = getattr(p_imp, "_global_timeout", 15.0)
        old_proxy = getattr(p_imp, "_global_proxy", None)
        try:
            p_imp.set_global_timeout(float(timeout))
        except Exception:
            pass
        try:
            p_imp.set_global_proxy(proxy if proxy else None)
        except Exception:
            pass

        progress = PhoneSearchProgress(phone=normalized_phone, total_modules=len(modules), is_running=True)
        self._progress = progress

        last_update = [time.monotonic()]

        def _notify():
            if on_progress is not None:
                try:
                    on_progress(PhoneSearchProgress(
                        phone=progress.phone,
                        total_modules=progress.total_modules,
                        checked_modules=progress.checked_modules,
                        found=list(progress.found),
                        not_found=list(progress.not_found),
                        rate_limited=list(progress.rate_limited),
                        unavailable=list(progress.unavailable),
                        errors=list(progress.errors),
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
                _, cat, site_name, _, p_info = item
                res = PhoneResult(
                    name=site_name,
                    category=cat,
                    exists=None,
                    unavailable=True,
                    domain=_domain_from_url(None, site_name),
                    phone=getattr(p_info, "e164", normalized_phone),
                    reason="skipped (loud)",
                )
                progress.unavailable.append(res)
                progress.errors.append(res)
                progress.checked_modules += 1
            elif kind == "error":
                _, cat, site_name, exc, p_info = item
                res = PhoneResult(
                    name=site_name,
                    category=cat,
                    exists=None,
                    unavailable=True,
                    domain=_domain_from_url(None, site_name),
                    phone=getattr(p_info, "e164", normalized_phone),
                    reason=str(exc),
                )
                progress.unavailable.append(res)
                progress.errors.append(res)
                progress.checked_modules += 1
            elif kind == "result":
                _, cat, site_name, r, p_info = item
                res = _map_result(cat, site_name, r, p_info)
                if res.exists:
                    progress.found.append(res)
                elif res.rate_limit:
                    progress.rate_limited.append(res)
                    progress.errors.append(res)
                elif res.unavailable:
                    progress.unavailable.append(res)
                    progress.errors.append(res)
                else:
                    progress.not_found.append(res)
                progress.checked_modules += 1

            now = time.monotonic()
            if now - last_update[0] >= 0.25 or progress.checked_modules == progress.total_modules:
                last_update[0] = now
                _notify()

        try:
            await asyncio.to_thread(
                self._run_worker, phone, region, modules, timeout, concurrency, allow_loud, _on_result, cancel_token
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
                p_imp.set_global_timeout(old_timeout)
            except Exception:
                pass
            try:
                p_imp.set_global_proxy(old_proxy)
            except Exception:
                pass
            _notify()

        return progress

    def _run_worker(self, phone, region, modules, timeout, concurrency, allow_loud, on_result, cancel_token):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                run_phone_scan(
                    phone, region, modules, on_result, cancel_token,
                    timeout=timeout, concurrency=concurrency, allow_loud=allow_loud,
                )
            )
        except Exception:
            logger.exception("phone scan worker failed")
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

    def cancel(self) -> None:
        if self._cancel_token is not None:
            self._cancel_token.set()
        if self._thread_cancel is not None:
            self._thread_cancel.set()
        progress = self._progress
        if progress is not None:
            progress.is_cancelled = True
            progress.is_running = False
