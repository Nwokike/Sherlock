"""Email OSINT service — wraps holehe-v2 with progress & cancellation.

holehe-v2 checks whether an email address is registered on 181 websites
by probing signup/login endpoints. Each platform exposes a validator:

    async def validate_<name>(email: str) -> holehe_v2.Result

We deliberately do NOT use v2's `run_all()`: it provides no progress
callback, no cancellation and no timeout enforcement (only 1 of 181
validators honours the global timeout; 18 impersonate-path modules have
no timeout at all). Instead we drive every validator as its own task
under a semaphore on a dedicated worker thread with a private event
loop — the same architecture the username engine uses — and classify
`Result.status` plus v2's honest error messages into the four buckets
the UI renders (found / not found / rate-limited / unavailable).
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

from core.tasks import spawn

logger = logging.getLogger(__name__)

_HOLEHE_AVAILABLE = False
_holehe_modules: dict[str, Callable] | None = None

try:
    from holehe_v2.core.helpers import set_global_timeout

    _HOLEHE_AVAILABLE = True
except ImportError:
    pass


def _load_validators_pkg() -> dict:
    """Zipimport-safe validator discovery — REPLACES upstream load_validators().

    Upstream globs `Path(__file__).parent.parent / "modules"` — on Android the
    package lives inside sitepackages.zip, where Path.glob finds NOTHING and
    the scan runs "0/0" instantly (the exact trap that used to kill the
    grapheme progress bar). Normal package imports go through zipimport,
    which works both in a desktop directory and inside the Android zip.
    """
    import importlib
    import inspect
    import pkgutil

    import holehe_v2.core.shim  # noqa: F401, RUF100 — result alias must exist first
    import holehe_v2.modules as pkg

    validators: dict = {}
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"holehe_v2.modules.{info.name}")
        except Exception as exc:
            # Per-module failures are tolerated (upstream does the same) but
            # always visible — owner rule: no swallowed errors.
            logger.warning("[loader] Failed to load %s: %s", info.name, exc)
            continue
        for name, fn in inspect.getmembers(module, inspect.iscoroutinefunction):
            if name.startswith("validate_"):
                validators[name[len("validate_") :]] = fn
    return validators


# ── TLS fingerprint selection ─────────────────────────────────────────
# v2's impersonate-path modules (github, canva, figma, patreon, quora,
# tumblr, walmart, ...) bind impersonate_request_async at module load.
# We wrap the helper BEFORE the first load_validators() so every bound
# reference is wrapped too. The wrapper picks the fingerprint per scan via
# a ContextVar (module-global _FINGERPRINT raced across concurrent scans;
# validators bind the wrapped fn at import, so per-scan rebinding can't work).
# Modules that pass an explicit fingerprint keep theirs.
_SCAN_FINGERPRINT: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "sherlock_email_fingerprint", default=None
)
# Legacy alias (kept for back-compat; the wrapper no longer reads it).
_FINGERPRINT: str | None = None

if _HOLEHE_AVAILABLE:
    try:
        import holehe_v2.core.impersonate as _imp

        if not getattr(_imp, "_sherlock_wrapped", False):
            _orig_impersonate = _imp.impersonate_request_async

            async def _impersonate_wrapped(url, method="GET", *args, **kwargs):
                # Fingerprint default preserved: explicit arg wins, else the
                # per-scan ContextVar, else upstream's chrome120. Everything
                # else passes through untouched for forward-compat with new
                # upstream params (proxy/timeout/cookies/...).
                kwargs["impersonate"] = (
                    kwargs.get("impersonate") or _SCAN_FINGERPRINT.get() or "chrome120"
                )
                return await _orig_impersonate(url, method, *args, **kwargs)

            _imp.impersonate_request_async = _impersonate_wrapped
            _imp._sherlock_wrapped = True
    except Exception:  # pragma: no cover — fingerprint is best-effort
        pass


# holehe-v2 Result.message strings, grouped by what actually happened:
# a site block (we were stopped — retryable later) vs an unchecked
# platform (dead endpoint / rotted parse / timeout). Rate-limit patterns
# win; ANY unmatched error honestly lands in "unavailable" — the platform
# could not be checked, which is a different fact than being blocked.
# (403/429 use word boundaries so "HTTP Error: 404" never matches.)
_RATE_LIMITED_RE = re.compile(
    r"\b(?:403|429)\b"
    r"|rate.?limit|too many requests|rate exceeded|limit exceeded"
    r"|try again later|temporarily blocked|throttl"
    r"|waf|cloudflare|datadome|captcha"
    r"|forbidden|bot challenge"
    r"|ip (?:has been |may be )?flagged"
    r"|registration attempt has been blocked"
    r"|blocked by \w+ waf",
    re.IGNORECASE,
)

# Single backoff before one rate-limit retry (see _run_one). Short by
# design: scans are long, and the semaphore slot is held while waiting,
# so this also throttles how fast retries re-hit the site.
_RATE_RETRY_DELAY_SEC = 2.0


def _is_rate_limited(message: str | None) -> bool:
    """True when v2's error message says the site blocked us."""
    return bool(_RATE_LIMITED_RE.search(message or ""))


EMAIL_FORMAT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass
class EmailResult:
    """Single email check result from one holehe-v2 validator."""

    name: str
    domain: str
    method: str = ""  # v2 has no method metadata; kept for snapshot compat
    exists: bool | None = None
    rate_limit: bool = False
    frequent_rate_limit: bool = False
    unavailable: bool = False
    email_recovery: str | None = None
    phone_number: str | None = None
    others: dict | None = None


@dataclass
class EmailSearchProgress:
    """Aggregate progress for an email search across all validators."""

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
    """Check if a string is a valid email address.

    holehe-v2 removed `is_email`; the local regex is the validator.
    """
    return bool(EMAIL_FORMAT.fullmatch(email))


def _domain_from(name: str, url: str | None) -> str:
    """Derive the platform domain from v2's Result.url.

    v2 sets url to the platform homepage (usable as domain — this is why
    email results still can't feed URL-based enrichment). Known buggy
    modules pass prose (walmart) or nothing; fall back to the validator
    name ("chess_com" → chess.com).
    """
    if url and str(url).startswith(("http://", "https://")):
        host = urlparse(str(url)).netloc.lower().split(":")[0]
        if "." in host:
            return host.removeprefix("www.")
    # Underscore names already encode the domain shape (chess_com →
    # chess.com, mail_ru → mail.ru); bare names get the .com default.
    dotted = name.replace("_", ".")
    return dotted if "_" in name else f"{dotted}.com"


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    if isinstance(value, str):
        return value or None
    # Numeric phones (int) and other scalars pass through — callers str() them.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def _phone_from(extra: dict) -> str | None:
    for key in ("phone", "phone_masked", "phone_number", "phoneNumber"):
        v = _first(extra.get(key))
        if v:
            return str(v)
    v = _first(extra.get("phone_numbers") or extra.get("phones"))
    return str(v) if v else None


def _recovery_from(extra: dict) -> str | None:
    for key in ("email", "recovery_email", "emailrecovery"):
        v = _first(extra.get(key))
        if v:
            return str(v)
    v = _first(extra.get("public_emails"))
    return str(v) if v else None


def _map_result(name: str, r) -> EmailResult:
    """Map a holehe-v2 Result onto our four-bucket dataclass."""
    domain = _domain_from(name, getattr(r, "url", None))
    others = {
        "message": getattr(r, "message", None),
        "url": getattr(r, "url", None),
        "extra": dict(getattr(r, "extra", None) or {}),
        "media": dict(getattr(r, "media", None) or {}),
    }

    if r.is_taken:
        return EmailResult(
            name=name,
            domain=domain,
            exists=True,
            email_recovery=_recovery_from(others["extra"]),
            phone_number=_phone_from(others["extra"]),
            others=others,
        )
    if r.is_available:
        return EmailResult(name=name, domain=domain, exists=False, others=others)

    # is_error — classify by v2's honest message.
    message = getattr(r, "message", "") or ""
    rate = _is_rate_limited(message)
    return EmailResult(
        name=name,
        domain=domain,
        exists=None,
        rate_limit=rate,
        unavailable=not rate,
        email_recovery=_recovery_from(others["extra"]),
        phone_number=_phone_from(others["extra"]),
        others=others,
    )


def _unavailable_result(name: str, message: str) -> EmailResult:
    """Bucket for a validator that raised or timed out."""
    return EmailResult(
        name=name,
        domain=_domain_from(name, None),
        exists=None,
        unavailable=True,
        # Same keys as _map_result so consumers can read others["extra"] /
        # others["message"] unconditionally; "error" kept for back-compat.
        others={
            "message": message,
            "url": None,
            "extra": {},
            "media": {},
            "error": message,
        },
    )


# Proxy env keys honoured by BOTH httpx (trust_env) and curl/libcurl
# (http_proxy/HTTPS_PROXY) — v2 validators build their own clients, so
# env injection is the only way to route them through state.proxy_url.
_PROXY_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def _install_proxy(proxy: str):
    """Set proxy env vars for the scan; return a restore callable.

    Process-global by necessity (validators build their own clients):
    concurrent scans and host env readers observe it during the window.
    Serialized by the is_running overlap guard — do not parallelize
    scans without a lock.
    """
    if not proxy:
        return lambda: None
    saved = {k: os.environ.get(k) for k in _PROXY_KEYS}
    for k in _PROXY_KEYS:
        os.environ[k] = proxy

    def _restore():
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    return _restore


class EmailService:
    """Runs holehe-v2 email OSINT scans with progress and cancellation."""

    def __init__(self):
        self._thread_cancel = threading.Event()
        self._progress: EmailSearchProgress | None = None
        self._tasks: list[asyncio.Task] = []
        self._worker_loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_available(self) -> bool:
        return _HOLEHE_AVAILABLE

    def _load_modules(self, skip_password_recovery: bool = False) -> dict:
        """Load all holehe-v2 validators. Cached after first call."""
        global _holehe_modules
        if _holehe_modules is None:
            loaded = _load_validators_pkg()
            if not loaded:
                # Loud failure: an empty registry means an instant "0/0"
                # fake scan (the Android zip-path bug we just fixed).
                logger.error(
                    "holehe-v2: 0 validators loaded — email scans would be "
                    "empty. Package layout: %s",
                    __import__("holehe_v2").__file__,
                )
                raise RuntimeError("holehe-v2 validator discovery returned 0 modules")
            logger.info("holehe-v2: %d validators loaded", len(loaded))
            _holehe_modules = loaded

        if skip_password_recovery:
            from core.constants import EMAIL_PW_RECOVERY_MODULES

            return {
                name: fn
                for name, fn in _holehe_modules.items()
                if name not in EMAIL_PW_RECOVERY_MODULES
            }
        return dict(_holehe_modules)

    @property
    def total_modules(self) -> int:
        """Return total number of available email check validators."""
        if not _HOLEHE_AVAILABLE:
            return 0
        try:
            return len(self._load_modules())
        except Exception as exc:
            # No hardcoded fallback: a stale constant (was 181) drifts with
            # every holehe release; 0 forces callers onto live counts.
            logger.warning("total_modules: discovery failed: %s", exc)
            return 0

    async def search(
        self,
        email: str,
        on_progress: Callable[[EmailSearchProgress], None],
        timeout: int = 10,
        skip_password_recovery: bool = False,
        concurrency: int = 15,
        use_curl_cffi: bool = True,
        proxy: str = "",
        *,
        use_stealth_fingerprint: bool | None = None,
    ) -> EmailSearchProgress:
        """Run a holehe-v2 email scan on an isolated worker thread.

        The scan — all 181 validators and their HTML/JSON parsing —
        executes on a dedicated OS thread with its own event loop, exactly
        like the username engine. Validator parsing is CPU-bound Python;
        running it on the main Flet loop starved the socket server and
        froze the UI (dead cancel button, dead back button).

        `use_stealth_fingerprint` (alias `use_curl_cffi`) selects the TLS
        fingerprint for v2's impersonate-path modules (modern chrome131 vs
        upstream chrome120). `proxy` is injected via HTTP(S)_PROXY env vars
        for the scan only — v2's validators build their own clients, so
        this is the only hook.
        """
        if use_stealth_fingerprint is None:
            use_stealth_fingerprint = use_curl_cffi

        if not _HOLEHE_AVAILABLE:
            raise RuntimeError("holehe-v2 is not available")

        if not validate_email(email):
            raise ValueError(f"Invalid email address: {email}")

        fingerprint = None
        if use_stealth_fingerprint:
            # P2-3 rotation: Android devices present as Chrome Android
            # (chrome131_android); desktops as chrome131.
            fingerprint = "chrome131"
            try:
                from flet import context as _flet_context

                if (
                    _flet_context.page
                    and hasattr(_flet_context.page, "platform")
                    and _flet_context.page.platform.is_mobile()
                ):
                    fingerprint = "chrome131_android"
            except Exception:
                pass
        # Only gravatar honours this, but it's free; every other timeout
        # is enforced below with asyncio.wait_for.
        set_global_timeout(float(timeout))

        modules = self._load_modules(skip_password_recovery)

        if self._progress is not None and self._progress.is_running:
            raise RuntimeError(
                "Email search already running — cancel before starting a new one"
            )
        self._thread_cancel.clear()
        self._tasks.clear()

        try:
            return await asyncio.to_thread(
                self._scan_in_worker,
                email,
                modules,
                timeout,
                concurrency,
                proxy,
                on_progress,
                fingerprint,
            )
        except asyncio.CancelledError:
            # Outer cancellation (Flet side): stop the worker too, or it
            # keeps running and ticking progress on a dead UI.
            self.cancel()
            raise

    def _scan_in_worker(
        self,
        email: str,
        modules: dict[str, Callable],
        timeout: int,
        concurrency: int,
        proxy: str,
        on_progress: Callable[[EmailSearchProgress], None],
        fingerprint: str | None = None,
    ) -> EmailSearchProgress:
        """Run the whole holehe-v2 scan on this worker thread's private loop."""
        token = _SCAN_FINGERPRINT.set(fingerprint)
        worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(worker_loop)
        self._worker_loop = worker_loop

        total = len(modules)
        progress = EmailSearchProgress(
            email=email, total_modules=total, is_running=True
        )
        self._progress = progress

        def _snapshot() -> EmailSearchProgress:
            """Copy lists so the UI thread never sees a mutating object."""
            return EmailSearchProgress(
                email=progress.email,
                total_modules=progress.total_modules,
                checked_modules=progress.checked_modules,
                found=list(progress.found),
                not_found=list(progress.not_found),
                rate_limited=list(progress.rate_limited),
                unavailable=list(progress.unavailable),
                is_running=progress.is_running,
                is_cancelled=progress.is_cancelled,
            )

        try:
            on_progress(_snapshot())
        except Exception:
            pass

        last_update_time = time.monotonic()
        progress_lock = asyncio.Lock()

        def _notify() -> None:
            """Throttled worker→bridge tick (bridge coalesces again at ~2Hz)."""
            try:
                on_progress(_snapshot())
            except Exception:
                pass

        async def _run_one(name: str, fn: Callable) -> None:
            """Run a single validator and bucket its Result.

            One rate-limited response gets a single backoff retry (the site
            answered, so a short wait often clears it); the retry is
            skipped when the scan was cancelled during the wait.
            """
            nonlocal last_update_time

            async def _attempt():
                if self._thread_cancel.is_set():
                    return None
                try:
                    # wait_for is mandatory: only 1/181 validators honour
                    # the global timeout and 18 impersonate-path modules
                    # have none.
                    r = await asyncio.wait_for(fn(email), timeout)
                except TimeoutError:
                    return _unavailable_result(name, "Connection timed out")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("Validator %s failed: %s", name, exc)
                    return _unavailable_result(name, str(exc))
                return _map_result(name, r)

            result = None
            try:
                result = await _attempt()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # _map_result junk guard lives inside _attempt; this covers
                # anything the mapping raised before it was folded in.
                logger.warning("Validator %s failed: %s", name, exc)
                result = _unavailable_result(name, str(exc))
            if (
                result is not None
                and result.rate_limit
                and not self._thread_cancel.is_set()
            ):
                await asyncio.sleep(_RATE_RETRY_DELAY_SEC)
                if self._thread_cancel.is_set():
                    return
                retried = await _attempt()
                if retried is not None:
                    result = retried
            if result is None:
                return

            async with progress_lock:
                progress.checked_modules += 1
                if result.rate_limit:
                    # "Frequent" = this scan is being broadly throttled (2+
                    # rate-limits already seen), not just one strict module.
                    if len(progress.rate_limited) >= 2:
                        result.frequent_rate_limit = True
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
            restore_proxy = _install_proxy(proxy)
            try:
                # Floor is 1, not 4: an explicit concurrency=1 (stealth)
                # must be honored, not silently quadrupled.
                sem = asyncio.Semaphore(max(1, min(30, concurrency)))

                async def _bounded(name: str, fn: Callable):
                    async with sem:
                        if self._thread_cancel.is_set():
                            return
                        await _run_one(name, fn)

                self._tasks = [
                    spawn(_bounded(name, fn), name=f"holehe-{name}")
                    for name, fn in modules.items()
                ]
                await asyncio.gather(*self._tasks, return_exceptions=True)
                self._tasks.clear()
            finally:
                restore_proxy()
            return progress

        try:
            return worker_loop.run_until_complete(_runner())
        except Exception:
            logger.exception("Email search worker failed")
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
            self._worker_loop = None
            _SCAN_FINGERPRINT.reset(token)
            with contextlib.suppress(Exception):
                asyncio.set_event_loop(None)
            worker_loop.close()
            try:
                on_progress(_snapshot())
            except Exception:
                pass

    def cancel(self):
        """Cancel a running email search — instant from any thread.

        Sets the cooperative flag (validators stop at the next boundary)
        and, when the worker loop is alive, cancels in-flight tasks on it
        so awaited requests abort immediately.
        """
        self._thread_cancel.set()
        # Snapshot liveness BEFORE the blocking wakeup below: waking the
        # worker loop can release the GIL, letting the worker finish its
        # teardown (is_running=False) before we evaluate the mark — a
        # cancel that lands on a live scan must still mark it cancelled.
        progress = self._progress
        was_live = progress is not None and progress.is_running
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
        # Only mark a LIVE scan: flipping a completed/stale progress to
        # cancelled rewrites history after the fact.
        if was_live:
            progress.is_cancelled = True
            progress.is_running = False
