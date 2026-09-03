"""Email OSINT service — wraps holehe with progress & cancellation.

holehe checks whether an email address is registered on 121+ websites
by probing signup, login, and password-recovery endpoints. Each module
is a standalone async function with the signature:

    async def <name>(email: str, client: httpx.AsyncClient, out: list) -> None

This service loads all modules dynamically, runs them concurrently using
asyncio (not trio — trio isn't needed when we drive the client ourselves),
and provides throttled progress callbacks compatible with the main-thread
bridge pattern used by SherlockService.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_HOLEHE_AVAILABLE = False
_holehe_modules: list | None = None
_CURL_CFFI_AVAILABLE = False

try:
    from holehe.core import import_submodules, get_functions, is_email

    _HOLEHE_AVAILABLE = True
except ImportError:
    pass

try:
    from curl_cffi.requests import AsyncSession as CurlAsyncSession

    _CURL_CFFI_AVAILABLE = True
except ImportError:
    CurlAsyncSession = None


def _patch_holehe_user_agents():
    """Patch holehe's internal user agent dictionary with modern browser strings

    to prevent ancient Chrome 24-41 bot detection and WAF challenge blocks.
    """
    try:
        import holehe.localuseragent as lua

        lua.ua["browsers"]["chrome"] = [
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
                " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0"
                " Safari/537.36"
            ),
            (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML,"
                " like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        ]
        lua.ua["browsers"]["firefox"] = [
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0)"
                " Gecko/20100101 Firefox/125.0"
            ),
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0)"
                " Gecko/20100101 Firefox/125.0"
            ),
        ]
    except Exception:
        pass


if _CURL_CFFI_AVAILABLE and CurlAsyncSession is not None:

    class StealthHoleheSession(CurlAsyncSession):
        """curl-cffi AsyncSession with Chrome 124 TLS & JA3 impersonation

        and httpx kwarg compatibility (follow_redirects -> allow_redirects).
        """

        def request(self, method, url, **kwargs):
            if "follow_redirects" in kwargs:
                kwargs["allow_redirects"] = kwargs.pop("follow_redirects")
            return super().request(method, url, **kwargs)

    # Record every response status into the running module's log. holehe
    # collapses all module failures into rateLimit=True, but the HTTP
    # statuses tell the real story (403/429 = the site blocked us;
    # 404/5xx = holehe's endpoint is dead; 2xx = site alive but holehe's
    # parsing rotted). The log is a contextvar so concurrent modules on
    # the shared client never mix their request histories.
    _orig_request = StealthHoleheSession.request

    async def _recording_request(self, method, url, **kwargs):
        response = await _orig_request(self, method, url, **kwargs)
        log = _module_statuses.get()
        if log is not None:
            log.append(getattr(response, "status_code", -1))
        return response

    StealthHoleheSession.request = _recording_request
else:
    StealthHoleheSession = None

# Per-module HTTP status log (set in _run_module around each module call).
_module_statuses: contextvars.ContextVar[list[int] | None] = contextvars.ContextVar(
    "module_statuses", default=None
)


def _genuine_rate_limit(statuses: list[int]) -> bool:
    """True only when the site itself blocked us (403/429).

    holehe marks ANY module failure as rateLimit — dead endpoints (404/5xx)
    and pages whose 2021-era parsing no longer matches 2026 markup all get
    the same flag. Only an explicit block status deserves that label.
    """
    return any(s in (403, 429) for s in statuses)


EMAIL_FORMAT = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")


@dataclass
class EmailResult:
    """Single email check result from one holehe module."""

    name: str
    domain: str
    method: str = ""
    exists: bool | None = None
    rate_limit: bool = False
    frequent_rate_limit: bool = False
    unavailable: bool = False
    email_recovery: str | None = None
    phone_number: str | None = None
    others: dict | None = None


@dataclass
class EmailSearchProgress:
    """Aggregate progress for an email search across all modules."""

    email: str
    total_modules: int = 0
    checked_modules: int = 0
    found: list[EmailResult] = field(default_factory=list)
    not_found: list[EmailResult] = field(default_factory=list)
    rate_limited: list[EmailResult] = field(default_factory=list)
    unavailable: list[EmailResult] = field(default_factory=list)
    is_running: bool = False
    is_cancelled: bool = False


def validate_email(email: str) -> bool:
    """Check if a string is a valid email address."""
    if _HOLEHE_AVAILABLE:
        return is_email(email)
    return bool(EMAIL_FORMAT.fullmatch(email))


class EmailService:
    """Runs holehe email OSINT scans with progress and cancellation."""

    def __init__(self):
        self._thread_cancel = threading.Event()
        self._progress: EmailSearchProgress | None = None
        self._tasks: list[asyncio.Task] = []
        self._client = None
        self._worker_loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_available(self) -> bool:
        return _HOLEHE_AVAILABLE

    def _load_modules(self, skip_password_recovery: bool = False) -> list:
        """Load all holehe check modules. Cached after first call."""
        global _holehe_modules
        if _holehe_modules is None:
            modules = import_submodules("holehe.modules")
            _holehe_modules = get_functions(modules, args=None)

        if skip_password_recovery:
            from core.constants import EMAIL_PW_RECOVERY_MODULES

            return [
                fn
                for fn in _holehe_modules
                if fn.__name__ not in EMAIL_PW_RECOVERY_MODULES
            ]
        return list(_holehe_modules)

    @property
    def total_modules(self) -> int:
        """Return total number of available email check modules."""
        if not _HOLEHE_AVAILABLE:
            return 0
        try:
            return len(self._load_modules())
        except Exception:
            return 121  # fallback

    async def search(
        self,
        email: str,
        on_progress: Callable[[EmailSearchProgress], None],
        timeout: int = 10,
        skip_password_recovery: bool = False,
        concurrency: int = 15,
        method_filter: str = "all",
        use_curl_cffi: bool = True,
    ) -> EmailSearchProgress:
        """Run holehe email scan on an isolated worker thread (stealth TLS).

        The scan — all 121 modules and their HTML/JSON parsing — executes on
        a dedicated OS thread with its own event loop, exactly like the
        username engine. Holehe parsing is CPU-bound Python; running it on
        the main Flet loop starved the socket server and froze the UI
        (dead cancel button, dead back button).
        """
        if not _HOLEHE_AVAILABLE:
            raise RuntimeError("holehe is not available")

        if not validate_email(email):
            raise ValueError(f"Invalid email address: {email}")

        _patch_holehe_user_agents()

        modules = self._load_modules(skip_password_recovery)

        self._thread_cancel.clear()
        self._tasks.clear()

        return await asyncio.to_thread(
            self._scan_in_worker,
            email,
            modules,
            timeout,
            concurrency,
            method_filter,
            use_curl_cffi,
            on_progress,
        )

    def _scan_in_worker(
        self,
        email: str,
        modules: list,
        timeout: int,
        concurrency: int,
        method_filter: str,
        use_curl_cffi: bool,
        on_progress: Callable[[EmailSearchProgress], None],
    ) -> EmailSearchProgress:
        """Run the whole holehe scan on this worker thread's private loop."""
        import httpx

        worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(worker_loop)
        self._worker_loop = worker_loop

        total = len(modules)
        progress = EmailSearchProgress(
            email=email, total_modules=total, is_running=True
        )
        self._progress = progress
        try:
            on_progress(progress)
        except Exception:
            pass

        last_update_time = time.monotonic()
        progress_lock = asyncio.Lock()

        def _notify() -> None:
            """Throttled worker→bridge tick (bridge coalesces again at ~2Hz)."""
            try:
                on_progress(progress)
            except Exception:
                pass

        async def _run_module(module, client):
            """Run a single holehe module and collect its result."""
            nonlocal last_update_time

            if self._thread_cancel.is_set():
                return

            name = module.__name__
            local_out: list[dict] = []
            statuses: list[int] = []
            _module_statuses.set(statuses)
            try:
                await module(email, client, local_out)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Module %s failed: %s", name, exc)
                local_out.append(
                    {
                        "name": name,
                        "domain": f"{name}.com",
                        "rateLimit": False,
                        "exists": None,
                        "unavailable": True,
                        "emailrecovery": None,
                        "phoneNumber": None,
                        "others": {"error": str(exc)},
                    }
                )
            finally:
                _module_statuses.set(None)

            if not local_out:
                # Holehe returned nothing — treat as inconclusive, not not_found.
                logger.warning("Module %s returned empty result — skipping", name)
                async with progress_lock:
                    progress.checked_modules += 1
                    result = EmailResult(
                        name=name,
                        domain=f"{name}.com",
                        exists=None,
                        rate_limit=False,
                        others={"error": "empty response"},
                    )
                    progress.not_found.append(result)
                    now = time.monotonic()
                    if (
                        now - last_update_time >= 0.25
                        or progress.checked_modules == total
                    ):
                        last_update_time = now
                        _notify()
                return

            raw = local_out[0]
            result = EmailResult(
                name=raw.get("name", name),
                domain=raw.get("domain", ""),
                method=raw.get("method", ""),
                exists=raw.get("exists"),
                rate_limit=raw.get("rateLimit", False),
                frequent_rate_limit=raw.get("frequent_rate_limit", False),
                unavailable=raw.get("unavailable", False),
                email_recovery=raw.get("emailrecovery"),
                phone_number=raw.get("phoneNumber"),
                others=raw.get("others"),
            )

            # Reclassify holehe's blanket rateLimit flag: only a real site
            # block (403/429) stays "rate limited". Dead endpoints (404/5xx)
            # and rotted parsing on live pages move to "unavailable" — the
            # platform can't be checked, which is a different fact than
            # being blocked.
            if result.rate_limit and statuses and not _genuine_rate_limit(statuses):
                result.rate_limit = False
                result.unavailable = True
                result.frequent_rate_limit = False

            # Apply method filtering if active
            if method_filter and method_filter != "all":
                m_curr = (result.method or "").lower()
                m_target = method_filter.lower()
                # Accept exact match or recovery alias
                if not (
                    m_curr == m_target
                    or (m_target == "recovery" and "recovery" in m_curr)
                ):
                    async with progress_lock:
                        progress.checked_modules += 1
                        now = time.monotonic()
                        if (
                            now - last_update_time >= 0.25
                            or progress.checked_modules == total
                        ):
                            last_update_time = now
                            _notify()
                    return

            async with progress_lock:
                progress.checked_modules += 1
                if result.rate_limit:
                    progress.rate_limited.append(result)
                elif result.unavailable:
                    progress.unavailable.append(result)
                elif result.exists:
                    progress.found.append(result)
                else:
                    progress.not_found.append(result)

                now = time.monotonic()
                if now - last_update_time >= 0.25 or progress.checked_modules == total:
                    last_update_time = now
                    _notify()

        async def _runner() -> EmailSearchProgress:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Windows"',
            }

            if (
                use_curl_cffi
                and _CURL_CFFI_AVAILABLE
                and StealthHoleheSession is not None
            ):
                client_ctx = StealthHoleheSession(
                    impersonate="chrome124",
                    timeout=timeout,
                    headers=headers,
                    allow_redirects=True,
                )
            else:
                client_ctx = httpx.AsyncClient(
                    timeout=timeout, headers=headers, follow_redirects=True
                )

            async with client_ctx as client:
                self._client = client
                sem = asyncio.Semaphore(max(4, min(30, concurrency)))

                async def _bounded(module):
                    async with sem:
                        if self._thread_cancel.is_set():
                            return
                        await _run_module(module, client)

                self._tasks = [asyncio.create_task(_bounded(m)) for m in modules]
                await asyncio.gather(*self._tasks, return_exceptions=True)
                self._tasks.clear()
            return progress

        try:
            return worker_loop.run_until_complete(_runner())
        except Exception as exc:
            logger.exception("Email search worker failed: %s", exc)
            raise
        finally:
            progress.is_running = False
            pending = [t for t in self._tasks if not t.done()]
            for t in pending:
                t.cancel()
            if pending:
                worker_loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            self._tasks.clear()
            self._client = None
            self._worker_loop = None
            with contextlib.suppress(Exception):
                asyncio.set_event_loop(None)
            worker_loop.close()
            try:
                on_progress(progress)
            except Exception:
                pass

    def cancel(self):
        """Cancel a running email search — instant from any thread.

        Sets the cooperative flag (modules stop at the next boundary) and,
        when the worker loop is alive, cancels in-flight module tasks on it
        so awaited requests abort immediately.
        """
        self._thread_cancel.set()
        loop = self._worker_loop
        tasks = list(self._tasks)
        if loop is not None and loop.is_running():

            def _cancel_all():
                for task in tasks:
                    if not task.done():
                        task.cancel()

            try:
                loop.call_soon_threadsafe(_cancel_all)
            except RuntimeError:
                pass  # worker already tearing down
        if self._progress:
            self._progress.is_cancelled = True
            self._progress.is_running = False
        if self._progress:
            self._progress.is_cancelled = True
            self._progress.is_running = False
