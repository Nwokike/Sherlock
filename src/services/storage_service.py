"""Platform-resilient key-value storage service matching modern Flet .flet storage standard."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import flet as ft

from core.tasks import spawn

logger = logging.getLogger(__name__)

_WRITE_DEBOUNCE_SEC = 1.0


def _backup_corrupt_file(path: Path) -> None:
    """Rename a corrupt file aside for forensics (parse errors only)."""
    try:
        if path.is_file() and path.stat().st_size > 0:
            bak = path.with_name(f"{path.name}.corrupt.{int(time.time())}.bak")
            os.replace(path, bak)
            logger.warning("Corrupt storage backed up: %s -> %s", path, bak)
    except OSError:
        pass


def get_storage_dir() -> Path:
    """Resolve durable storage directory — Flet's sandbox (.flet/storage/data) or env var.

    FLET_APP_STORAGE_DATA points at .flet/storage/data during `flet run`
    and at the device sandbox on mobile. Fallback is project_root/.flet/storage/data.
    """
    storage_env = os.getenv("FLET_APP_STORAGE_DATA")
    if storage_env and Path(storage_env).is_absolute():
        return Path(storage_env)
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / ".flet" / "storage" / "data"


def get_cache_dir() -> Path:
    """Resolve regenerable cache directory — FLET_APP_STORAGE_CACHE or .flet/storage/cache."""
    cache_env = os.getenv("FLET_APP_STORAGE_CACHE")
    if cache_env and Path(cache_env).is_absolute():
        return Path(cache_env)
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / ".flet" / "storage" / "cache"


def get_temp_dir() -> Path:
    """Resolve temporary scratch directory — FLET_APP_STORAGE_TEMP or .flet/storage/temp."""
    temp_env = os.getenv("FLET_APP_STORAGE_TEMP")
    if temp_env and Path(temp_env).is_absolute():
        return Path(temp_env)
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / ".flet" / "storage" / "temp"


class StorageService:
    def __init__(self, page: ft.Page | None = None, data_dir: Path | str | None = None):
        self._page = page
        self._data: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._dirty = False
        self._last_write: float = 0.0
        self._pending_write_task: asyncio.Task | None = None

        if data_dir:
            self._storage_dir = Path(data_dir)
        else:
            self._storage_dir = get_storage_dir()

        self._storage_file = self._storage_dir / "storage.json"
        # Web detection: an explicit page without file-system semantics uses
        # client_storage. page=None (tests/headless) is always file-backed —
        # it has no client_storage. When a page exists but carries neither
        # detection attribute, prefer client_storage (private) over the
        # server file (shared/ephemeral).
        if page is None:
            self._is_web = False
        else:
            self._is_web = bool(
                getattr(page, "session_id", None) or getattr(page, "web", False)
            )
            if not hasattr(page, "session_id") and not hasattr(page, "web"):
                self._is_web = True

        if self._is_web:
            self._load_web()
        else:
            self._load()

    def _load_web(self) -> None:
        try:
            if self._page and hasattr(self._page, "client_storage"):
                cs = self._page.client_storage
                raw = cs.get("sherlock_storage")
                parsed = json.loads(raw) if raw else {}
                self._data = (
                    {
                        k: v
                        for k, v in parsed.items()
                        if isinstance(k, str) and isinstance(v, str)
                    }
                    if isinstance(parsed, dict)
                    else {}
                )
        except Exception as e:
            logger.warning("StorageService._load_web failed: %s", e)
            self._data = {}

    def _load(self) -> None:
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            if self._storage_file.exists():
                raw = self._storage_file.read_text(encoding="utf-8")
                if not raw.strip():
                    self._data = {}
                else:
                    try:
                        parsed = json.loads(raw)
                        self._data = (
                            {
                                k: v
                                for k, v in parsed.items()
                                if isinstance(k, str) and isinstance(v, str)
                            }
                            if isinstance(parsed, dict)
                            else {}
                        )
                    except json.JSONDecodeError, ValueError, UnicodeDecodeError:
                        # Parse error (not missing file): back the corrupt
                        # file up before resetting, so evidence survives.
                        _backup_corrupt_file(self._storage_file)
                        self._data = {}
            else:
                self._data = {}
        except Exception as e:
            logger.warning("StorageService._load failed: %s", e)
            self._data = {}

    def _write_snapshot(self, snapshot: dict[str, str]) -> bool:
        """Synchronous file replace of a caller-owned snapshot.

        No lock, no flag mutation — call via to_thread from flush().
        Returns success so the caller keeps retry semantics.
        """
        import tempfile

        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            data = json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8")
            fd, tmp_s = tempfile.mkstemp(
                dir=str(self._storage_dir),
                prefix=f".{self._storage_file.name}.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_s, self._storage_file)
            finally:
                try:
                    os.unlink(tmp_s)
                except OSError:
                    pass
            return True
        except Exception as e:
            logger.warning("StorageService._write_snapshot failed: %s", e)
            return False

    def _save_now(self) -> None:
        if self._is_web:
            self._save_now_web()
            return
        if self._write_snapshot(dict(self._data)):
            self._dirty = False
            self._last_write = time.monotonic()

    def _save_now_web(self) -> None:
        try:
            if self._page and hasattr(self._page, "client_storage"):
                cs = self._page.client_storage
                cs.set("sherlock_storage", json.dumps(self._data))
            self._dirty = False
            self._last_write = time.monotonic()
        except Exception as e:
            logger.warning("StorageService._save_now_web failed: %s", e)

    def _schedule_write(self) -> None:
        if self._pending_write_task:
            return
        try:
            loop = asyncio.get_running_loop()
            self._pending_write_task = loop.call_later(
                _WRITE_DEBOUNCE_SEC,
                lambda: spawn(self._flush_task(), name="storage-flush"),
            )
        except RuntimeError:
            self._save_now()

    async def _flush_task(self) -> None:
        # Clear the handle BEFORE flushing: a set() landing during flush()
        # re-arms via _schedule_write instead of hitting the early-return
        # and stranding a dirty write with no timer.
        self._pending_write_task = None
        try:
            await self.flush()
        finally:
            if self._dirty and self._pending_write_task is None:
                self._schedule_write()

    async def close(self) -> None:
        """Cancel the debounce timer and flush — call on app teardown so the
        trailing write window is never lost on exit."""
        task = self._pending_write_task
        self._pending_write_task = None
        if task is not None:
            try:
                task.cancel()
            except Exception:
                pass
        await self.flush()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            return self._data.get(key)

    async def set(self, key: str, value: str) -> None:
        if not isinstance(key, str):
            raise TypeError(
                f"StorageService.set key must be str, got {type(key).__name__}"
            )
        if not isinstance(value, str):
            raise TypeError(
                f"StorageService.set value for {key!r} must be str, "
                f"got {type(value).__name__}"
            )
        async with self._lock:
            self._data[key] = value
            self._dirty = True
        self._schedule_write()

    async def delete(self, key: str) -> None:
        async with self._lock:
            if key not in self._data:
                return
            del self._data[key]
            self._dirty = True
        self._schedule_write()

    async def clear(self) -> None:
        async with self._lock:
            if not self._data:
                return
            self._data.clear()
            self._dirty = True
        self._schedule_write()

    async def get_all(self) -> dict[str, str]:
        async with self._lock:
            return dict(self._data)

    async def flush(self) -> None:
        async with self._lock:
            if not self._dirty:
                return
            if self._is_web:
                self._save_now_web()  # fast client_storage, keep under lock
                return
            snapshot = dict(self._data)
        # Write outside the lock so gets/sets never stall on fsync.
        ok = await asyncio.to_thread(self._write_snapshot, snapshot)
        async with self._lock:
            if ok and self._data == snapshot:
                self._dirty = False
            # else: concurrent mutation during write — stay dirty; the
            # _flush_task re-arm persists it on the next pass.
            self._last_write = time.monotonic()


def load_history_entries(raw: str | None) -> list[dict]:
    """Decode stored history (oldest-first) → newest-first for display.

    Shared by HomeScreen and AppController so the reversed contract lives
    in one place. Returns empty list on bad/missing JSON.
    """
    if not raw:
        return []
    try:
        entries = json.loads(raw)
        if not isinstance(entries, list):
            return []
        return [e for e in reversed(entries) if isinstance(e, dict)]
    except Exception:
        return []


def encode_history_entries(entries: list[dict], new_entry: dict | None = None) -> str:
    """Encode history as oldest-first JSON for storage. Keeps last 50."""
    out = list(entries)
    if new_entry is not None:
        out.append(new_entry)
    out = out[-50:]
    return json.dumps(out)
