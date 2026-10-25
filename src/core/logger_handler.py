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


# Prime psutil CPU monitoring at import time so first get_telemetry_snapshot reads real CPU
if _PSUTIL_AVAILABLE and psutil is not None:
    try:
        psutil.cpu_percent(interval=None)
    except Exception:
        pass

in_memory_log_handler = MemoryLogHandler()

# Target noisy transport/framework libraries when muted so real service errors
# remain visible in the in-app terminal and console.
_QUIET_WHEN_MUTED: tuple[tuple[str, int], ...] = (
    ("httpcore", logging.WARNING),
    ("httpx", logging.WARNING),
    ("flet", logging.WARNING),
    ("flet_ads", logging.WARNING),
)


def set_engine_logs(verbose: bool) -> None:
    """Mute or restore verbose engine log noise.

    When verbose=True, sets loggers to DEBUG. When False, keeps transport
    libraries quiet so our terminal shows real activity and errors.
    """
    for name, quiet_level in _QUIET_WHEN_MUTED:
        logging.getLogger(name).setLevel(logging.DEBUG if verbose else quiet_level)


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
        if bat is not None and getattr(bat, "percent", None) is not None:
            plug_icon = "⚡" if getattr(bat, "power_plugged", False) else "🔋"
            parts.append(f"BAT: {bat.percent:.0f}% {plug_icon}")
    except Exception:
        pass

    return " | ".join(parts) if parts else "Telemetry: unavailable"
