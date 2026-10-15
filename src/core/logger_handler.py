"""In-memory ring buffer logging handler and telemetry for diagnostic terminal.

Mirrors KTV-Player / DDGS / CollabShell MemoryLogHandler pattern.
"""

from __future__ import annotations

import collections
import logging
from typing import ClassVar

_PSUTIL_AVAILABLE = False
try:
    import psutil

    _PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None


class MemoryLogHandler(logging.Handler):
    """Ring buffer log handler capturing recent logs for in-app terminal display."""

    _logs: ClassVar[collections.deque[str]] = collections.deque(maxlen=500)

    def __init__(self, level: int = logging.DEBUG):
        super().__init__(level=level)
        formatter = logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._logs.append(msg)
        except Exception:
            self.handleError(record)

    @classmethod
    def get_logs(cls) -> list[str]:
        """Return a snapshot list of current in-memory log entries."""
        return list(cls._logs)

    @classmethod
    def clear_logs(cls) -> None:
        """Clear all in-memory log entries."""
        cls._logs.clear()


in_memory_log_handler = MemoryLogHandler()

# Engine noise, by logger, with the level it drops to when muted. A 5,200-site
# scan emits thousands of these and they bury everything else in both the
# console and the in-app terminal.
#
# `sherlock.engine` is the child logger handed to maigret — it reports every
# check through whatever logger it is given, and it used to be handed OUR
# module logger, so those records arrived as "services.sherlock_service" and
# muting `maigret` by name did nothing at all. Muted to ERROR rather than
# WARNING because its WARNINGs are per-site outcomes (403, bot wall, rate
# limit) repeated thousands of times — each one is already classified onto
# the result card as a badge, so nothing is lost by not logging it, while a
# WARNING level still drowned the terminal.
#
# `httpx` logs one INFO line per HTTP request, which is the email engine's
# entire traffic. Real transport problems come through at WARNING and up.
_QUIET_WHEN_MUTED: tuple[tuple[str, int], ...] = (
    ("sherlock.engine", logging.ERROR),
    ("httpx", logging.WARNING),
)

# Bare `logging.info(...)` calls land on the ROOT logger, so there is no name
# to quiet — `socid_extractor` does this once per detection
# (.venv/socid_extractor/main.py:80). A root-level filter is the only lever,
# and root filters apply exactly to records logged directly on root.
_BARE_LOGGING_SOURCES = ("socid_extractor",)


class _EngineNoiseFilter(logging.Filter):
    """Drop bare-root records emitted by engine dependencies when muted."""

    def __init__(self) -> None:
        super().__init__()
        self.muted = True

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.muted:
            return True
        pathname = getattr(record, "pathname", "") or ""
        return not any(source in pathname for source in _BARE_LOGGING_SOURCES)


_engine_noise_filter = _EngineNoiseFilter()


def set_engine_logs(verbose: bool) -> None:
    """Mute or restore the OSINT engine's own log noise.

    Off (the default) quiets the engine loggers and drops bare-root chatter
    from its dependencies, so the console and the in-app terminal show our
    own messages and real errors instead of per-site traffic. On restores
    everything to NOTSET, i.e. inherit the root level.
    """
    for name, quiet_level in _QUIET_WHEN_MUTED:
        logging.getLogger(name).setLevel(logging.NOTSET if verbose else quiet_level)
    _engine_noise_filter.muted = not verbose
    root = logging.getLogger()
    if _engine_noise_filter not in root.filters:
        # Logger filters apply to records logged directly on that logger,
        # which is what bare `logging.info(...)` produces.
        root.addFilter(_engine_noise_filter)


def get_telemetry_snapshot() -> str:
    """Return a compact system telemetry string (CPU, RAM, Net, Battery)."""
    if not _PSUTIL_AVAILABLE or psutil is None:
        return "Telemetry: psutil not loaded"

    parts = []
    try:
        cpu = psutil.cpu_percent(interval=None)
        parts.append(f"CPU: {cpu:.1f}%")
    except Exception:
        pass

    try:
        vm = psutil.virtual_memory()
        used_mb = vm.used / (1024 * 1024)
        parts.append(f"RAM: {used_mb:.0f}MB ({vm.percent}%)")
    except Exception:
        pass

    try:
        proc = psutil.Process()
        proc_mem = proc.memory_info().rss / (1024 * 1024)
        parts.append(f"App RSS: {proc_mem:.0f}MB")
    except Exception:
        pass

    try:
        bat = psutil.sensors_battery()
        if bat is not None:
            plug_icon = "⚡" if getattr(bat, "power_plugged", False) else "🔋"
            parts.append(f"BAT: {bat.percent:.0f}% {plug_icon}")
    except Exception:
        pass

    return " | ".join(parts) if parts else "Telemetry: unavailable"
