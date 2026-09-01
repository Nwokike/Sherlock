"""In-memory ring buffer logging handler for in-app diagnostic terminal.

Mirrors KTV-Player / DDGS / CollabShell MemoryLogHandler pattern.
"""

from __future__ import annotations

import collections
import logging
from typing import ClassVar


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
