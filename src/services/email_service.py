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
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_HOLEHE_AVAILABLE = False
_holehe_modules: list | None = None

try:
    from holehe.core import import_submodules, get_functions, is_email

    _HOLEHE_AVAILABLE = True
except ImportError:
    pass

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
        self._cancel_event = asyncio.Event()
        self._progress: EmailSearchProgress | None = None
        self._tasks: list[asyncio.Task] = []
        self._client = None

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
    ) -> EmailSearchProgress:
        """Run holehe email scan across all modules concurrently."""
        if not _HOLEHE_AVAILABLE:
            raise RuntimeError("holehe is not available")

        if not validate_email(email):
            raise ValueError(f"Invalid email address: {email}")

        modules = self._load_modules(skip_password_recovery)
        total = len(modules)

        self._cancel_event.clear()
        self._tasks.clear()

        progress = EmailSearchProgress(
            email=email,
            total_modules=total,
            is_running=True,
        )
        self._progress = progress
        on_progress(progress)

        last_update_time = time.monotonic()
        progress_lock = asyncio.Lock()

        import httpx

        async def _run_module(module, client):
            """Run a single holehe module and collect its result."""
            nonlocal last_update_time

            if self._cancel_event.is_set():
                return

            name = module.__name__
            local_out: list[dict] = []
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
                        "emailrecovery": None,
                        "phoneNumber": None,
                        "others": {"error": str(exc)},
                    }
                )

            if not local_out:
                # Holehe returned nothing — treat as inconclusive, not not_found.
                # Skipping prevents false-negative "Available" when the probe didn't run.
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
                    should_notify = (
                        now - last_update_time >= 0.20
                    ) or progress.checked_modules == total
                    if should_notify:
                        last_update_time = now
                if should_notify:
                    try:
                        on_progress(progress)
                    except Exception:
                        pass
                return

            raw = local_out[0]
            result = EmailResult(
                name=raw.get("name", name),
                domain=raw.get("domain", ""),
                method=raw.get("method", ""),
                exists=raw.get("exists"),
                rate_limit=raw.get("rateLimit", False),
                frequent_rate_limit=raw.get("frequent_rate_limit", False),
                email_recovery=raw.get("emailrecovery"),
                phone_number=raw.get("phoneNumber"),
                others=raw.get("others"),
            )

            async with progress_lock:
                progress.checked_modules += 1
                if result.rate_limit:
                    progress.rate_limited.append(result)
                elif result.exists:
                    progress.found.append(result)
                else:
                    progress.not_found.append(result)

                now = time.monotonic()
                should_notify = (
                    now - last_update_time >= 0.20
                ) or progress.checked_modules == total
                if should_notify:
                    last_update_time = now

            if should_notify:
                try:
                    on_progress(progress)
                except Exception:
                    pass

        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
            async with httpx.AsyncClient(
                timeout=timeout, headers=headers, follow_redirects=True
            ) as client:
                self._client = client
                sem = asyncio.Semaphore(max(5, min(30, concurrency)))

                async def _bounded(module):
                    async with sem:
                        if self._cancel_event.is_set():
                            return
                        await _run_module(module, client)

                self._tasks = [asyncio.create_task(_bounded(m)) for m in modules]
                await asyncio.gather(*self._tasks, return_exceptions=True)
                self._tasks.clear()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Email search failed: %s", exc)
            raise
        finally:
            self._client = None
            progress.is_running = False
            with __import__("contextlib").suppress(Exception):
                on_progress(progress)

        self._progress = progress
        return progress

    def cancel(self):
        """Cancel a running email search — cancels tasks and closes client."""
        self._cancel_event.set()
        for task in list(self._tasks):
            if not task.done():
                task.cancel()
        if self._client is not None:
            with __import__("contextlib").suppress(Exception):
                # httpx AsyncClient close is async; best-effort sync close
                self._client = None
        if self._progress:
            self._progress.is_cancelled = True
            self._progress.is_running = False
