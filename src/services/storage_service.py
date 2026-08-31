"""Platform-resilient key-value storage service matching modern Flet .flet storage standard."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import flet as ft

logger = logging.getLogger(__name__)

_WRITE_DEBOUNCE_SEC = 1.0


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
        self._is_web = bool(getattr(page, "session_id", None)) if page else False

        if self._is_web:
            self._load_web()
        else:
            self._load()

    def _load_web(self) -> None:
        try:
            if self._page and hasattr(self._page, "client_storage"):
                cs = self._page.client_storage
                raw = cs.get("sherlock_storage")
                self._data = json.loads(raw) if raw else {}
        except Exception as e:
            logger.warning("StorageService._load_web failed: %s", e)
            self._data = {}

    def _load(self) -> None:
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            if self._storage_file.exists():
                raw = self._storage_file.read_text(encoding="utf-8")
                self._data = json.loads(raw) if raw else {}
            else:
                self._data = {}
        except Exception as e:
            logger.warning("StorageService._load failed: %s", e)
            self._data = {}

    def _save_now(self) -> None:
        if self._is_web:
            self._save_now_web()
            return
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            tmp_file = self._storage_file.with_suffix(".tmp")
            tmp_file.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_file.replace(self._storage_file)
            self._dirty = False
            self._last_write = time.monotonic()
        except Exception as e:
            logger.warning("StorageService._save_now failed: %s", e)

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
                lambda: loop.create_task(self._flush_task()),
            )
        except RuntimeError:
            self._save_now()

    async def _flush_task(self) -> None:
        try:
            await self.flush()
        finally:
            self._pending_write_task = None

    async def get(self, key: str) -> str | None:
        async with self._lock:
            return self._data.get(key)

    async def set(self, key: str, value: str) -> None:
        async with self._lock:
            self._data[key] = value
            self._dirty = True
        self._schedule_write()

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)
            self._dirty = True
        self._schedule_write()

    async def flush(self) -> None:
        async with self._lock:
            if self._dirty:
                self._save_now()
