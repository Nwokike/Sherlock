"""Compatibility glue between Sherlock-V3 (Flet) and the user-scanner / phonsint engines.

This is the boundary that adapts user-scanner / phonsint internals to the
SherlockService / EmailService / PhoneService facades:
- Tolerant module loading with import caching
- Async scan drivers streaming progress via callbacks (250-worker thread pool)
- Deterministic cancellation and task cleanup
- End-to-end cross-scan scoping (respects selected sites & categories)
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import io
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Shared 250-worker thread pool for sync engine module execution
# (mirrors upstream orchestrator.py:28 and email_orchestrator.py:200)
_shared_executor = ThreadPoolExecutor(max_workers=250, thread_name_prefix="us_worker")

# In-memory module catalog caches to eliminate repeat multi-second imports
_USER_MODULES_CACHE: dict[bool, list[tuple[str, Any]]] = {}
_EMAIL_MODULES_CACHE: dict[bool, list[tuple[str, Any]]] = {}
_PHONE_MODULES_CACHE: list[tuple[str, Any]] | None = None
_MODULES_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Tolerant module loading with caching
# ---------------------------------------------------------------------------


def load_user_modules(no_nsfw: bool = False) -> list[tuple[str, Any]]:
    """Return [(category, module), ...] for username scanning, cached by no_nsfw."""
    with _MODULES_LOCK:
        if no_nsfw in _USER_MODULES_CACHE:
            return list(_USER_MODULES_CACHE[no_nsfw])
        from user_scanner.core.helpers import load_categories

        categories = load_categories(is_email=False, no_nsfw=no_nsfw)
        res = [
            (cat_name.capitalize(), mod)
            for cat_name, cat_path in categories.items()
            for mod in _load_modules_tolerant(cat_path)
        ]
        _USER_MODULES_CACHE[no_nsfw] = res
        return list(res)


def load_email_modules(no_nsfw: bool = False) -> list[tuple[str, Any]]:
    """Return [(category, module), ...] for email scanning, cached by no_nsfw."""
    with _MODULES_LOCK:
        if no_nsfw in _EMAIL_MODULES_CACHE:
            return list(_EMAIL_MODULES_CACHE[no_nsfw])
        from user_scanner.core.helpers import load_categories

        categories = load_categories(is_email=True, no_nsfw=no_nsfw)
        res = [
            (cat_name.capitalize(), mod)
            for cat_name, cat_path in categories.items()
            for mod in _load_modules_tolerant(cat_path)
        ]
        _EMAIL_MODULES_CACHE[no_nsfw] = res
        return list(res)


def load_phone_modules() -> list[tuple[str, Any]]:
    """Return [(category, module), ...] for phone scanning, cached."""
    global _PHONE_MODULES_CACHE
    with _MODULES_LOCK:
        if _PHONE_MODULES_CACHE is not None:
            return list(_PHONE_MODULES_CACHE)
        from phonsint.core.helpers import load_categories

        categories = load_categories()
        res = [
            (cat_name.capitalize(), mod)
            for cat_name, cat_path in categories.items()
            for mod in _load_modules_tolerant(cat_path)
        ]
        _PHONE_MODULES_CACHE = res
        return list(res)


def _load_modules_tolerant(category_path: Path) -> list[Any]:
    """Per-file import with try/except — upstream aborts the whole category."""
    import importlib.util

    modules: list[Any] = []
    skipped: list[str] = []
    for file in sorted(category_path.glob("*.py")):
        if file.name.startswith("__"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(file.stem, str(file))
            if spec is None or spec.loader is None:
                skipped.append(file.stem)
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            modules.append(module)
        except Exception as exc:  # pragma: no cover - defensive
            skipped.append(f"{file.stem}: {exc}")
            logger.warning("skipped module %s: %s", file.stem, exc)
    if skipped:
        logger.info("tolerant loader skipped %d module(s) in %s", len(skipped), category_path)
    return modules


def get_site_name_user(module: Any) -> str:
    from user_scanner.core.helpers import get_site_name
    return get_site_name(module)


def is_loud_user(name: str, is_email: bool = False) -> bool:
    from user_scanner.core.helpers import is_loud
    return is_loud(name, is_email=is_email)


def get_site_name_phone(module: Any) -> str:
    from phonsint.core.helpers import get_site_name
    return get_site_name(module)


# ---------------------------------------------------------------------------
# Username scan driver (user-scanner user_scan modules)
# ---------------------------------------------------------------------------


async def run_username_scan(
    username: str,
    modules: list[tuple[str, Any]],
    on_result: Callable[[Any], None],
    cancel_event: threading.Event,
    timeout: int = 10,
    concurrency: int = 50,
    allow_loud: bool = False,
    no_nsfw: bool = False,
    selected: set[str] | None = None,
    proxy: str | None = None,
) -> None:
    """Drive user_scan modules; stream each Result to on_result."""
    try:
        from user_scanner.core.helpers import set_global_timeout, set_proxy_manager
        set_global_timeout(float(timeout))
        if proxy:
            set_proxy_manager(proxies=[proxy])
        else:
            set_proxy_manager(None, None)
    except Exception:
        logger.warning("proxy setup/reset failed", exc_info=True)

    from user_scanner.core.helpers import (
        get_site_name,
        is_loud,
    )

    filtered: list[tuple[str, Any]] = []
    for cat, mod in modules:
        name = get_site_name(mod)
        if selected is not None and name.lower() not in selected:
            # Emit skipped so caller's checked counter accurately reflects all modules
            on_result(("skipped", cat, name, None))
            continue
        if not allow_loud and is_loud(name, is_email=False):
            on_result(("skipped", cat, name, None))
            continue
        filtered.append((cat, mod))

    if not filtered:
        return

    sem = asyncio.Semaphore(max(1, min(250, concurrency)))
    tasks: list[asyncio.Task] = []
    for cat, mod in filtered:
        if cancel_event.is_set():
            break
        task = asyncio.create_task(
            _run_one_user(mod, username, cat, sem, timeout, cancel_event)
        )
        tasks.append(task)

    if not tasks:
        return

    try:
        for coro in asyncio.as_completed(tasks):
            if cancel_event.is_set():
                break
            try:
                item = await coro
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("username module failed: %s", exc)
                continue
            if item is not None:
                on_result(item)
    finally:
        if cancel_event.is_set():
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def _run_one_user(module, username, category, sem, timeout, cancel_event):
    from user_scanner.core.helpers import get_scan_func, get_site_name
    from user_scanner.core.result import Result as USResult

    if cancel_event.is_set():
        return None
    async with sem:
        if cancel_event.is_set():
            return None
        site_name = get_site_name(module)
        func = get_scan_func(module)
        if func is None:
            return ("error", category, site_name, Exception("no validate_ function"))
        try:
            module_timeout = (float(timeout) if timeout else 15.0) + 10.0
            if inspect.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(username), timeout=module_timeout)
            else:
                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(_shared_executor, func, username),
                    timeout=module_timeout,
                )
        except TimeoutError:
            result = USResult.error(f"Module timed out after {module_timeout}s")
        except Exception as exc:
            result = USResult.error(exc)
        if not isinstance(result, USResult):
            result = USResult.error("invalid result type")
        result = result.update(site_name=site_name, username=username, category=category, is_email=False)
        return ("result", category, site_name, result)


# ---------------------------------------------------------------------------
# Email scan driver (user-scanner email_scan modules)
# ---------------------------------------------------------------------------


async def run_email_scan(
    email: str,
    modules: list[tuple[str, Any]],
    on_result: Callable[[Any], None],
    cancel_event: threading.Event,
    timeout: int = 10,
    concurrency: int = 15,
    allow_loud: bool = False,
    proxy: str | None = None,
) -> None:
    try:
        from user_scanner.core.helpers import set_global_timeout, set_proxy_manager
        set_global_timeout(float(timeout))
        if proxy:
            set_proxy_manager(proxies=[proxy])
        else:
            set_proxy_manager(None, None)
    except Exception:
        logger.warning("proxy setup/reset failed", exc_info=True)

    from user_scanner.core.helpers import get_site_name, is_loud

    filtered: list[tuple[str, Any]] = []
    for cat, mod in modules:
        name = get_site_name(mod)
        if not allow_loud and is_loud(name, is_email=True):
            on_result(("skipped", cat, name, None))
            continue
        filtered.append((cat, mod))

    if not filtered:
        return

    sem = asyncio.Semaphore(max(1, min(250, concurrency)))
    tasks = [
        asyncio.create_task(_run_one_email(mod, email, cat, sem, timeout, cancel_event))
        for cat, mod in filtered
    ]

    try:
        for coro in asyncio.as_completed(tasks):
            if cancel_event.is_set():
                break
            try:
                item = await coro
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("email module failed: %s", exc)
                continue
            if item is not None:
                on_result(item)
    finally:
        if cancel_event.is_set():
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def _run_one_email(module, email, category, sem, timeout, cancel_event):
    from user_scanner.core.helpers import get_scan_func, get_site_name
    from user_scanner.core.result import Result as USResult

    if cancel_event.is_set():
        return None
    async with sem:
        if cancel_event.is_set():
            return None
        site_name = get_site_name(module)
        func = get_scan_func(module)
        if func is None:
            return ("error", category, site_name, Exception("no validate_ function"))
        try:
            module_timeout = (float(timeout) if timeout else 15.0) + 10.0
            if inspect.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(email), timeout=module_timeout)
            else:
                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(_shared_executor, func, email),
                    timeout=module_timeout,
                )
        except TimeoutError:
            result = USResult.error(f"Module timed out after {module_timeout}s")
        except Exception as exc:
            result = USResult.error(exc)
        if not isinstance(result, USResult):
            result = USResult.error("invalid result type")
        result = result.update(site_name=site_name, username=email, category=category, is_email=True)
        return ("result", category, site_name, result)


# ---------------------------------------------------------------------------
# Phone scan driver (phonsint modules)
# ---------------------------------------------------------------------------


async def run_phone_scan(
    phone: str,
    region: str | None,
    modules: list[tuple[str, Any]],
    on_result: Callable[[Any], None],
    cancel_event: threading.Event,
    timeout: float = 15.0,
    concurrency: int = 15,
    allow_loud: bool = False,
) -> Any:
    try:
        from phonsint.core.impersonate import set_global_timeout
        set_global_timeout(float(timeout))
    except Exception:
        pass

    from phonsint.core.helpers import (
        get_site_name,
        is_loud,
    )
    from phonsint.core.parser import parse_phone_number

    phone_info = parse_phone_number(phone, region)

    filtered: list[tuple[str, Any]] = []
    for cat, mod in modules:
        name = get_site_name(mod)
        if not allow_loud and is_loud(name):
            on_result(("skipped", cat, name, None, phone_info))
            continue
        filtered.append((cat, mod))

    if not filtered:
        return phone_info

    sem = asyncio.Semaphore(max(1, min(100, concurrency)))
    tasks = [
        asyncio.create_task(_run_one_phone(mod, phone_info, cat, sem, timeout, cancel_event))
        for cat, mod in filtered
    ]

    try:
        for coro in asyncio.as_completed(tasks):
            if cancel_event.is_set():
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
        if cancel_event.is_set():
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    return phone_info


async def _run_one_phone(module, phone_info, category, sem, timeout, cancel_event):
    from phonsint.core.helpers import get_scan_func, get_site_name
    from phonsint.core.result import Result as PResult

    if cancel_event.is_set():
        return None
    async with sem:
        if cancel_event.is_set():
            return None
        site_name = get_site_name(module)
        func = get_scan_func(module)
        if func is None:
            return ("error", category, site_name, Exception("no validate_ function"), phone_info)
        try:
            sig = inspect.signature(func)
            params = list(sig.parameters.values())
            arg = (
                phone_info
                if (len(params) == 1 and params[0].name in ("phone_info", "info"))
                else phone_info.e164
            )
            module_timeout = (float(timeout) if timeout else 15.0) + 5.0
            if inspect.iscoroutinefunction(func):
                raw = await asyncio.wait_for(func(arg), timeout=module_timeout)
            else:
                loop = asyncio.get_running_loop()
                raw = await asyncio.wait_for(
                    loop.run_in_executor(_shared_executor, func, arg),
                    timeout=module_timeout,
                )
            if isinstance(raw, PResult):
                result = raw
            else:
                result = PResult.error("Module returned invalid result type")
        except TimeoutError:
            result = PResult.error(f"Timed out after {(float(timeout) if timeout else 15.0) + 5.0}s")
        except Exception as exc:
            result = PResult.error(exc)
        result = result.update(site_name=site_name, phone=phone_info.e164, category=category)
        return ("result", category, site_name, result, phone_info)


# ---------------------------------------------------------------------------
# Cross-scan driver (user-scanner multi-depth pivots + confidence scoring)
# ---------------------------------------------------------------------------


async def run_cross_scan_async(
    initial_results: list[Any],
    all_user_modules: list[tuple[str, Any]],
    all_email_modules: list[tuple[str, Any]],
    cross_config: Any,
    on_result: Callable[[Any], None],
    cancel_event: threading.Event,
    timeout: int = 10,
    concurrency: int = 50,
    allow_loud: bool = False,
    no_nsfw: bool = False,
    selected: set[str] | None = None,
    proxy: str | None = None,
) -> list[Any]:
    """Execute multi-depth cross-scan rounds without blocking the event loop."""
    from user_scanner.core.confidence import Confidence
    from user_scanner.core.cross_scan import (
        _already_scanned,
        _already_swept,
        _apply_confidence,
        _email_targets,
        _followable,
        _fresh_emails,
        _fresh_pivots,
        _named_targets,
        _split_budget,
        _sweep_targets,
        _tag,
        _tag_emails,
    )
    from user_scanner.core.helpers import ScanConfig, find_category
    from user_scanner.core.pivots import rank_usernames

    # 1. Compute scope from cross_config.modules / categories (upstream cross_scan.py:187-207)
    scope_modules_filter = getattr(cross_config, "modules", None)
    scope_categories_filter = getattr(cross_config, "categories", None)

    scope_user_pairs: list[tuple[str, Any]] | None = None
    if scope_modules_filter:
        norm_mods = {str(m).lower().replace(".", "_") for m in scope_modules_filter}
        scope_user_pairs = [
            (cat, mod) for cat, mod in all_user_modules
            if mod.__name__.split(".")[-1].lower() in norm_mods
            or get_site_name_user(mod).lower() in norm_mods
        ]
    elif scope_categories_filter:
        norm_cats = {str(c).lower() for c in scope_categories_filter}
        scope_user_pairs = [
            (cat, mod) for cat, mod in all_user_modules
            if cat.lower() in norm_cats
        ]

    # Upstream _named_targets expects a list of module objects for its scope argument
    scope_for_named = [mod for _, mod in scope_user_pairs] if scope_user_pairs is not None else None

    depth = max(1, getattr(cross_config, "depth", 1))
    budget = max(0, getattr(cross_config, "sweep", 3))
    all_pivots: list[Any] = []
    cross_results: list[Any] = []
    swept: set[str] = _already_swept(initial_results)
    checked: set[tuple[str, str]] = set()
    scanned_emails: set[str] = _already_scanned(initial_results)
    email_ratings: dict[str, Confidence] = {}
    source: list[Any] = list(initial_results)

    scan_cfg = ScanConfig(
        allow_loud=allow_loud,
        no_nsfw=no_nsfw,
        show_all=True,
        verbose=False,
        timeout=float(timeout),
    )

    for round_number in range(1, depth + 1):
        if cancel_event.is_set():
            break

        pivots = _fresh_pivots(source, cross_config.links, swept, checked)
        ranked = _fresh_emails(source, cross_config.emails, scanned_emails)
        if not pivots and not ranked:
            break

        all_pivots.extend(pivots)
        sweepable = (
            0
            if scope_user_pairs is not None and not scope_user_pairs
            else len(rank_usernames(pivots))
        )
        for_usernames, for_emails = _split_budget(budget, sweepable, len(ranked))

        # Redirect stdout around upstream print statements to keep console clean
        buf_sweep = io.StringIO()
        with contextlib.redirect_stdout(buf_sweep):
            usernames = _sweep_targets(pivots, for_usernames)
        sweep_log = buf_sweep.getvalue().strip()
        if sweep_log:
            logger.info("[cross-scan sweep] %s", sweep_log)

        usable_email_modules = [m[1] for m in all_email_modules]
        if not allow_loud:
            usable_email_modules = [
                m
                for m in usable_email_modules
                if not is_loud_user(get_site_name_user(m), is_email=True)
            ]
        buf_email = io.StringIO()
        with contextlib.redirect_stdout(buf_email):
            to_scan = _email_targets(ranked, for_emails, usable_email_modules)
        email_log = buf_email.getvalue().strip()
        if email_log:
            logger.info("[cross-scan email] %s", email_log)

        budget -= len(usernames) + len(to_scan)
        swept.update(u.lower() for u in usernames)
        scanned_emails.update(entry.email for entry in to_scan)
        email_ratings.update({entry.email: entry.confidence for entry in to_scan})

        round_results: list[Any] = []

        # 1. Sweep usernames across scoped modules (or all modules if scope is None)
        sweep_user_modules = scope_user_pairs if scope_user_pairs is not None else all_user_modules
        for u in usernames:
            if cancel_event.is_set():
                break
            u_results: list[Any] = []

            def _sweep_collector(item, u_results=u_results):
                if item and item[0] == "result":
                    u_results.append(item[3])

            await run_username_scan(
                u,
                sweep_user_modules,
                _sweep_collector,
                cancel_event,
                timeout=timeout,
                concurrency=concurrency,
                allow_loud=allow_loud,
                no_nsfw=no_nsfw,
                selected=selected,
                proxy=proxy,
            )
            tagged = _tag(u_results, all_pivots, u)
            round_results.extend(tagged)
            for r in tagged:
                cat = getattr(r, "category", None) or "General"
                site = getattr(r, "site_name", None) or "Unknown"
                on_result(("result", cat, site, r))

        # 2. Check named platform links
        named = _named_targets(pivots, swept, checked, scan_cfg, scope_for_named)
        for u, mods in named.items():
            if cancel_event.is_set():
                break
            named_pairs = [(find_category(m) or "General", m) for m in mods]
            named_results: list[Any] = []

            def _named_collector(item, named_results=named_results):
                if item and item[0] == "result":
                    named_results.append(item[3])

            await run_username_scan(
                u,
                named_pairs,
                _named_collector,
                cancel_event,
                timeout=timeout,
                concurrency=concurrency,
                allow_loud=allow_loud,
                no_nsfw=no_nsfw,
                proxy=proxy,
            )
            tagged = _tag(named_results, all_pivots, u)
            round_results.extend(tagged)
            for r in tagged:
                cat = getattr(r, "category", None) or "General"
                site = getattr(r, "site_name", None) or "Unknown"
                on_result(("result", cat, site, r))

        # 3. Check discovered email targets
        for entry in to_scan:
            if cancel_event.is_set():
                break
            em_results: list[Any] = []

            def _em_collector(item, em_results=em_results):
                if item and item[0] == "result":
                    em_results.append(item[3])

            await run_email_scan(
                entry.email,
                all_email_modules,
                _em_collector,
                cancel_event,
                timeout=timeout,
                concurrency=concurrency,
                allow_loud=allow_loud,
                proxy=proxy,
            )
            tagged = _tag_emails(em_results, entry)
            round_results.extend(tagged)
            for r in tagged:
                cat = getattr(r, "category", None) or "Email"
                site = getattr(r, "site_name", None) or "Unknown"
                on_result(("result", cat, site, r))

        checked.update((p.site, p.username.lower()) for p in pivots if p.site)
        cross_results.extend(round_results)

        if round_number < depth:
            _apply_confidence(initial_results + cross_results, cross_results, all_pivots, email_ratings)
            source = _followable(round_results)

    _apply_confidence(initial_results + cross_results, cross_results, all_pivots, email_ratings)
    return cross_results
