"""Platform-resilient key-value storage service matching modern Flet .flet storage standard."""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
import threading
import time
from pathlib import Path

import flet as ft

logger = logging.getLogger(__name__)

_WRITE_DEBOUNCE_SEC = 1.0
_FILE_LOCK = threading.Lock()
_INSTANCES: dict[str, StorageService] = {}
_INSTANCES_LOCK = threading.Lock()


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


class StorageService:
    """Singleton-per-directory KV store.

    One instance per storage dir is shared process-wide. This is deliberate:
    the old code constructed a new instance per screen, and each had its own
    debounce timer, so several debounced `os.replace` calls could race on the
    same `storage.json` — which is what produced
    `[WinError 5] Access is denied: .tmp -> storage.json` on Windows.

    All in-process synchronization uses a plain `threading.Lock` (never
    `asyncio.Lock`), so the class works identically across event loops — a
    loop-bound `asyncio.Lock` raises under a second loop, and a loop-bound
    `TimerHandle` silently stops scheduling writes once the first loop closes.
    Disk is always the source of truth on construction: if another process
    changed the file, we pick it up rather than serving stale in-memory data.
    """

    def __new__(cls, page: ft.Page | None = None, data_dir: Path | str | None = None) -> StorageService:
        target_dir = Path(data_dir) if data_dir else get_storage_dir()
        key = str(target_dir.resolve())
        with _INSTANCES_LOCK:
            inst = _INSTANCES.get(key)
            if inst is None:
                inst = super().__new__(cls)
                inst._initialized = False
                _INSTANCES[key] = inst
            return inst

    def __init__(self, page: ft.Page | None = None, data_dir: Path | str | None = None):
        if getattr(self, "_initialized", False):
            if page is not None:
                self._page = page
            return

        self._initialized = True
        self._page = page
        self._data: dict[str, str] = {}
        self._lock = threading.RLock()
        # Serializes flushes so two concurrent flushes can't write an older
        # snapshot after a newer one (which used to drop the newest keys).
        self._flush_lock = threading.Lock()
        self._dirty = False
        self._pending_timer: threading.Timer | None = None

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
        self._is_web = bool(page is not None and getattr(page, "web", False))

        # Disk is authoritative: re-read so a file changed by another process
        # (or deleted while we were idle) is never masked by our cache.
        if not self._is_web:
            self._load()

        def _on_process_exit():
            with self._lock:
                if self._pending_timer is not None:
                    self._pending_timer.cancel()
                    self._pending_timer = None
                if self._dirty:
                    self._save_now()

        atexit.register(_on_process_exit)

    def _load(self) -> None:
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            if self._storage_file.exists():
                try:
                    raw = self._storage_file.read_text(encoding="utf-8")
                    if not raw.strip():
                        self._data = {}
                    else:
                        parsed = json.loads(raw)
                        if isinstance(parsed, dict):
                            self._data = {
                                str(k): str(v)
                                for k, v in parsed.items()
                                if isinstance(k, str) and isinstance(v, str)
                            }
                        else:
                            _backup_corrupt_file(self._storage_file)
                            self._data = {}
                except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                    logger.warning("Corrupt storage parse failed: %s", exc)
                    _backup_corrupt_file(self._storage_file)
                    self._data = {}
            else:
                self._data = {}
        except Exception as e:
            logger.warning("StorageService._load failed: %s", e)
            self._data = {}

    def _write_snapshot(self, snapshot: dict[str, str]) -> bool:
        """Synchronous file replace of a caller-owned snapshot with Windows retry backoff.

        Protected by a file-level thread lock and retried on PermissionError / WinError 5.
        """
        import tempfile

        with _FILE_LOCK:
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
                    # Windows NTFS backoff retry on transient filter/antivirus locks (WinError 5)
                    max_retries = 6
                    for attempt in range(max_retries):
                        try:
                            os.replace(tmp_s, self._storage_file)
                            break
                        except (PermissionError, OSError):
                            if attempt == max_retries - 1:
                                raise
                            time.sleep(0.04 * (2**attempt))
                finally:
                    try:
                        if os.path.exists(tmp_s):
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
        # Snapshot then compare: a set() landing while _write_snapshot runs must
        # NOT be orphaned — only clear dirty when nothing changed underneath us
        # (same guard flush() uses; without it the trailing write is lost).
        with self._lock:
            snapshot = dict(self._data)
        if self._write_snapshot(snapshot):
            with self._lock:
                if self._data == snapshot:
                    self._dirty = False

    def _save_now_web(self) -> None:
        try:
            if self._page and hasattr(self._page, "client_storage"):
                cs = self._page.client_storage
                cs.set("sherlock_storage", json.dumps(self._data))
            self._dirty = False
        except Exception as e:
            logger.warning("StorageService._save_now_web failed: %s", e)

    def _schedule_write(self) -> None:
        """Debounce a flush on a plain threading.Timer.

        A Timer is loop-agnostic: the previous `loop.call_later` handle was
        bound to whichever loop happened to call `set()` first, so after that
        loop closed every later `set()` hit the stale-handle early-return and
        never scheduled another write.
        """
        with self._lock:
            if self._pending_timer is not None:
                return
            self._pending_timer = threading.Timer(
                _WRITE_DEBOUNCE_SEC, self._fire_timer
            )
            self._pending_timer.daemon = True
            self._pending_timer.start()

    def _fire_timer(self) -> None:
        with self._lock:
            self._pending_timer = None
        self._save_now()
        # A set() landing during the write re-arms here rather than stranding
        # a dirty write with no timer.
        with self._lock:
            dirty = self._dirty
        if dirty:
            self._schedule_write()

    async def close(self) -> None:
        """Cancel the debounce timer and flush — call on app teardown so the
        trailing write window is never lost on exit."""
        with self._lock:
            timer = self._pending_timer
            self._pending_timer = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass
        await self.flush()

    async def get(self, key: str) -> str | None:
        with self._lock:
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
        with self._lock:
            self._data[key] = value
            self._dirty = True
        self._schedule_write()

    async def delete(self, key: str) -> None:
        with self._lock:
            if key not in self._data:
                return
            del self._data[key]
            self._dirty = True
        self._schedule_write()

    async def clear(self) -> None:
        with self._lock:
            if not self._data:
                return
            self._data.clear()
            self._dirty = True
        self._schedule_write()

    async def flush(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            if self._is_web:
                self._save_now_web()
                return
            snapshot = dict(self._data)

        # Serialize flushes: without this, two concurrent flushes can land
        # out of order and the older snapshot wins, dropping the newest keys.
        with self._flush_lock:
            ok = await asyncio.to_thread(self._write_snapshot, snapshot)
            with self._lock:
                # Only clear dirty if nothing changed while we were writing;
                # otherwise a later flush picks up the newer snapshot.
                if ok and self._data == snapshot:
                    self._dirty = False


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
