"""Phone OSINT service — wraps phonsint's module validators.

Ported from the owner's Sherlock-V3 (``services/phone_service.py`` +
``user_scanner_compat.run_phone_scan``), adapted to 2.3.0's contracts:

- Same result/progress shape as the email engine, so the results screen,
  exporters and notification pipeline reuse one module-mode branch.
- Never touches ``state.sites_*``: the maigret network catalog and the Sites
  screen stay exactly as they are. Phone's own catalog is 5 modules.
- Everything phonsint-specific is imported lazily so the app starts (and the
  test suite runs) without the engine loaded.

phonsint 0.1.0 is beta: 5 modules (Facebook, Instagram, Microsoft, Amazon,
Zoho). It queries pre-authentication discovery endpoints only — it never sends
an SMS — and returns masked emails, display names, avatars and Zoho datacenter
routing in ``Result.extra`` / ``Result.media``.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import inspect
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.tasks import spawn

logger = logging.getLogger(__name__)

# Shared pool for sync phonsint module functions (mirrors upstream's
# orchestrator). Async modules run on the worker's own loop.
_shared_executor = None

_MODULES_CACHE: list[tuple[str, Any]] | None = None
_MODULES_LOCK = threading.Lock()


def _executor():
    global _shared_executor
    if _shared_executor is None:
        from concurrent.futures import ThreadPoolExecutor

        _shared_executor = ThreadPoolExecutor(
            max_workers=32, thread_name_prefix="phon_worker"
        )
    return _shared_executor


@dataclass
class PhoneResult:
    """One platform's verdict for a phone number."""

    name: str = ""  # site name
    category: str = ""
    exists: bool | None = None  # True=registered, False=not, None=error/skipped
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


def validate_phone(phone: str, region: str | None = None) -> bool:
    """Engine-side validity check (phonenumbers). Never raises."""
    try:
        from phonsint.core.parser import parse_phone_number

        return bool(parse_phone_number((phone or "").strip(), region).is_valid)
    except Exception:
        return False


def normalize_phone(phone: str, region: str | None = None) -> str:
    """E.164 identity for the scan, or the raw input when unparseable."""
    try:
        from phonsint.core.parser import parse_phone_number

        info = parse_phone_number((phone or "").strip(), region)
        return info.e164 if info.is_valid else (phone or "").strip()
    except Exception:
        return (phone or "").strip()


def load_catalog() -> list[tuple[str, Any]]:
    """[(category, module), ...] built from phonsint's live catalog.

    Tolerant: one broken module file never aborts the category (upstream's
    loader would). Cached for the session.
    """
    global _MODULES_CACHE
    with _MODULES_LOCK:
        if _MODULES_CACHE is not None:
            return list(_MODULES_CACHE)
        try:
            from phonsint.core.helpers import load_categories
        except Exception:
            logger.warning("phonsint unavailable — phone catalog empty")
            _MODULES_CACHE = []
            return []
        entries: list[tuple[str, Any]] = []
        for cat_name, cat_path in load_categories().items():
            entries.extend(
                (cat_name.capitalize(), module)
                for module in _load_modules_tolerant(cat_path)
            )
        _MODULES_CACHE = entries
        return list(entries)


def _load_modules_tolerant(category_path: Path) -> list[Any]:
    modules: list[Any] = []
    for file in sorted(category_path.glob("*.py")):
        if file.name.startswith("__"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(file.stem, str(file))
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            modules.append(module)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("skipped phone module %s: %s", file.stem, exc)
    return modules


def catalog_names() -> list[str]:
    """Site names from the live catalog (no hardcoded list)."""
    try:
        from phonsint.core.helpers import get_site_name

        return [get_site_name(m) for _, m in load_catalog()]
    except Exception:
        return []


def catalog_categories() -> list[str]:
    return sorted({cat for cat, _ in load_catalog()})


def supported_regions() -> list[str]:
    """Every ISO-3166 region phonenumbers supports (no hardcoded list)."""
    try:
        import phonenumbers

        return sorted(phonenumbers.SUPPORTED_REGIONS)
    except Exception:
        return []


def _domain_from_url(url: str | None, fallback: str) -> str:
    if url and str(url).startswith(("http://", "https://")):
        host = urlparse(str(url)).netloc.lower().split(":")[0]
        if "." in host:
            return host.removeprefix("www.")
    return fallback.lower().replace("_", ".")


def _is_rate_limited(message: str | None) -> bool:
    text = (message or "").lower()
    return any(
        token in text
        for token in ("429", "rate limit", "rate-limit", "too many requests", "throttl")
    )


def _map_result(cat: str, site_name: str, result: Any, phone_info: Any) -> PhoneResult:
    from phonsint.core.result import Status

    url = getattr(result, "url", "") or ""
    extra = dict(getattr(result, "extra", None) or {})
    media = dict(getattr(result, "media", None) or {})
    try:
        reason = (
            result.get_reason()
            if hasattr(result, "get_reason")
            else str(getattr(result, "reason", "") or "")
        )
    except Exception:
        reason = str(getattr(result, "reason", "") or "")

    status = getattr(result, "status", None)
    if status == Status.TAKEN:
        exists: bool | None = True
    elif status == Status.AVAILABLE:
        exists = False
    else:
        exists = None

    rate_limit = _is_rate_limited(reason)
    unavailable = (status == Status.ERROR or status == Status.SKIPPED) and not rate_limit
    phone_e164 = getattr(result, "phone", None) or getattr(phone_info, "e164", "")

    return PhoneResult(
        name=site_name,
        category=cat,
        exists=exists,
        unavailable=unavailable,
        rate_limit=rate_limit,
        url=url,
        url_main=url,
        url_user=url,
        domain=_domain_from_url(url, site_name),
        phone=phone_e164,
        extra=extra,
        media=media,
        reason=reason,
        raw=result,
    )


class PhoneService:
    """Runs phonsint scans on a private worker loop with streaming progress."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._cancel_token = threading.Event()
        self._worker_loop: asyncio.AbstractEventLoop | None = None
        self._progress: PhoneSearchProgress | None = None

    @property
    def is_available(self) -> bool:
        try:
            import phonsint  # noqa: F401

            return True
        except ImportError:
            return False

    @property
    def total_modules(self) -> int:
        return len(load_catalog())

    def cancel(self) -> None:
        self._cancel_token.set()
        progress = self._progress
        if progress is not None:
            progress.is_cancelled = True
            progress.is_running = False
        loop = self._worker_loop
        if loop is not None:
            with contextlib.suppress(Exception):
                loop.call_soon_threadsafe(
                    lambda: [t.cancel() for t in asyncio.all_tasks(loop)]
                )

    async def search(
        self,
        phone: str,
        region: str | None = None,
        on_progress: Callable[[PhoneSearchProgress], None] | None = None,
        timeout: float = 15.0,
        concurrency: int = 15,
        proxy: str = "",
        categories: list[str] | None = None,
        modules: list[str] | None = None,
    ) -> PhoneSearchProgress:
        from phonsint.core.parser import parse_phone_number

        phone_info = parse_phone_number((phone or "").strip(), region)
        identity = phone_info.e164 if phone_info.is_valid else (phone or "").strip()

        entries = list(await asyncio.to_thread(load_catalog))
        wanted_cats = {c.lower() for c in (categories or []) if c}
        wanted_mods = {m.lower() for m in (modules or []) if m}
        if wanted_cats:
            entries = [e for e in entries if e[0].lower() in wanted_cats]
        if wanted_mods:
            from phonsint.core.helpers import get_site_name

            entries = [e for e in entries if get_site_name(e[1]).lower() in wanted_mods]

        cancel_token = threading.Event()
        self._cancel_token = cancel_token

        import phonsint.core.impersonate as p_imp

        old_timeout = getattr(p_imp, "_global_timeout", 15.0)
        old_proxy = getattr(p_imp, "_global_proxy", None)
        with contextlib.suppress(Exception):
            p_imp.set_global_timeout(float(timeout))
        with contextlib.suppress(Exception):
            p_imp.set_global_proxy(proxy or None)

        progress = PhoneSearchProgress(
            phone=identity, total_modules=len(entries), is_running=True
        )
        self._progress = progress

        last_update = [time.monotonic()]

        def _notify() -> None:
            if on_progress is None:
                return
            try:
                on_progress(
                    PhoneSearchProgress(
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
                    )
                )
            except Exception:
                logger.debug("phone on_progress failed", exc_info=True)

        def _on_result(item) -> None:
            if cancel_token.is_set() or not item:
                return
            kind = item[0]
            if kind == "skipped":
                _, cat, site_name, _, p_info = item
                row = PhoneResult(
                    name=site_name,
                    category=cat,
                    unavailable=True,
                    domain=_domain_from_url(None, site_name),
                    phone=getattr(p_info, "e164", identity),
                    reason="skipped (loud)",
                )
                progress.unavailable.append(row)
                progress.errors.append(row)
            elif kind == "error":
                _, cat, site_name, exc, p_info = item
                row = PhoneResult(
                    name=site_name,
                    category=cat,
                    unavailable=True,
                    domain=_domain_from_url(None, site_name),
                    phone=getattr(p_info, "e164", identity),
                    reason=str(exc),
                )
                progress.unavailable.append(row)
                progress.errors.append(row)
            else:
                _, cat, site_name, result, p_info = item
                row = _map_result(cat, site_name, result, p_info)
                if row.exists:
                    progress.found.append(row)
                elif row.rate_limit:
                    progress.rate_limited.append(row)
                    progress.errors.append(row)
                elif row.unavailable:
                    progress.unavailable.append(row)
                    progress.errors.append(row)
                else:
                    progress.not_found.append(row)
            progress.checked_modules += 1
            now = time.monotonic()
            if (
                now - last_update[0] >= 0.25
                or progress.checked_modules == progress.total_modules
            ):
                last_update[0] = now
                _notify()

        try:
            await asyncio.to_thread(
                self._run_worker,
                phone,
                region,
                entries,
                timeout,
                concurrency,
                _on_result,
                cancel_token,
            )
        except asyncio.CancelledError:
            cancel_token.set()
            progress.is_cancelled = True
            raise
        finally:
            progress.is_running = False
            if cancel_token.is_set():
                progress.is_cancelled = True
            with contextlib.suppress(Exception):
                p_imp.set_global_timeout(old_timeout)
            with contextlib.suppress(Exception):
                p_imp.set_global_proxy(old_proxy)
            _notify()

        return progress

    def _run_worker(
        self,
        phone: str,
        region: str | None,
        modules: list[tuple[str, Any]],
        timeout: float,
        concurrency: int,
        on_result: Callable[[Any], None],
        cancel_token: threading.Event,
    ) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._worker_loop = loop
        try:
            loop.run_until_complete(
                self._scan_modules(
                    phone, region, modules, timeout, concurrency, on_result, cancel_token
                )
            )
        except Exception:
            logger.exception("phone scan worker failed")
        finally:
            # Only clear the slot if it still points at THIS worker: a newer
            # scan may already have installed its own loop (cancel must reach
            # the live one, not be erased by the previous worker's teardown).
            if self._worker_loop is loop:
                self._worker_loop = None
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                with contextlib.suppress(Exception):
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            loop.close()
            with contextlib.suppress(Exception):
                asyncio.set_event_loop(None)

    async def _scan_modules(
        self,
        phone: str,
        region: str | None,
        modules: list[tuple[str, Any]],
        timeout: float,
        concurrency: int,
        on_result: Callable[[Any], None],
        cancel_token: threading.Event,
    ) -> None:
        from phonsint.core.helpers import get_scan_func, get_site_name, is_loud
        from phonsint.core.parser import parse_phone_number

        phone_info = parse_phone_number(phone, region)

        # Silent-operation guard: never run an upstream "loud" module (one
        # that could alert the target). phonsint 0.1.0 has none, but the
        # dependency is unbounded, so the skip must not rely on that.
        runnable: list[tuple[str, Any]] = []
        for cat, module in modules:
            name = get_site_name(module)
            if is_loud(name):
                on_result(("skipped", cat, name, None, phone_info))
                continue
            runnable.append((cat, module))
        modules = runnable

        sem = asyncio.Semaphore(max(1, min(100, concurrency)))

        async def _one(cat: str, module: Any):
            if cancel_token.is_set():
                return None
            async with sem:
                if cancel_token.is_set():
                    return None
                site_name = get_site_name(module)
                func = get_scan_func(module)
                if func is None:
                    return (
                        "error",
                        cat,
                        site_name,
                        Exception("no validate_ function"),
                        phone_info,
                    )
                from phonsint.core.result import Result as PResult

                try:
                    params = list(inspect.signature(func).parameters.values())
                    arg = (
                        phone_info
                        if (
                            len(params) == 1
                            and params[0].name in ("phone_info", "info")
                        )
                        else phone_info.e164
                    )
                    module_timeout = (float(timeout) if timeout else 15.0) + 5.0
                    if inspect.iscoroutinefunction(func):
                        result = await asyncio.wait_for(
                            func(arg), timeout=module_timeout
                        )
                    else:
                        running = asyncio.get_running_loop()
                        result = await asyncio.wait_for(
                            running.run_in_executor(_executor(), func, arg),
                            timeout=module_timeout,
                        )
                except TimeoutError:
                    result = PResult.error(f"Timed out after {module_timeout}s")
                except Exception as exc:
                    result = PResult.error(exc)
                if not isinstance(result, PResult):
                    result = PResult.error("Module returned invalid result type")
                result = result.update(
                    site_name=site_name, phone=phone_info.e164, category=cat
                )
                return ("result", cat, site_name, result, phone_info)

        tasks = [
            spawn(_one(cat, module), "phone-module")
            for cat, module in modules
        ]
        try:
            for coro in asyncio.as_completed(tasks):
                if cancel_token.is_set():
                    break
                try:
                    item = await coro
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.warning("phone module failed: %s", exc)
                    continue
                if item is not None:
                    on_result(item)
        finally:
            if cancel_token.is_set():
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
