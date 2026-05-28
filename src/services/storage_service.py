"""Platform-resilient key-value storage service."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import flet as ft

logger = logging.getLogger(__name__)

storage_env = os.getenv("FLET_APP_STORAGE_DATA")
if storage_env:
    _STORAGE_DIR = Path(storage_env)
else:
    _STORAGE_DIR = Path.home() / ".sherlock"

_STORAGE_FILE = _STORAGE_DIR / "storage.json"
_WRITE_DEBOUNCE_SEC = 1.0


class StorageService:
    def __init__(self, page: ft.Page):
        self._page = page
        self._data: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._dirty = False
        self._last_write: float = 0.0
        self._pending_write_task: asyncio.Task | None = None
        self._is_web = bool(getattr(page, "session_id", None))

        if self._is_web:
            self._load_web()
        else:
            self._load()

    def _load_web(self) -> None:
        try:
            cs = self._page.client_storage
            raw = cs.get("sherlock_storage")
            self._data = json.loads(raw) if raw else {}
        except Exception as e:
            logger.warning("StorageService._load_web failed: %s", e)
            self._data = {}

    def _load(self) -> None:
        _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        if _STORAGE_FILE.exists():
            try:
                self._data = json.loads(_STORAGE_FILE.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("StorageService._load failed: %s", e)
                self._data = {}
        else:
            self._data = {}

    def _save_now(self) -> None:
        if self._is_web:
            self._save_now_web()
            return
        try:
            _STORAGE_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._dirty = False
            self._last_write = time.monotonic()
        except Exception as e:
            logger.warning("StorageService._save_now failed: %s", e)

    def _save_now_web(self) -> None:
        try:
            cs = self._page.client_storage
            cs.set("sherlock_storage", json.dumps(self._data))
            self._dirty = False
            self._last_write = time.monotonic()
        except Exception as e:
            logger.warning("StorageService._save_now_web failed: %s", e)

    def _schedule_write(self) -> None:
        if self._pending_write_task:
            return
        self._pending_write_task = asyncio.get_event_loop().call_later(
            _WRITE_DEBOUNCE_SEC,
            lambda: asyncio.get_event_loop().create_task(self._flush_task()),
        )

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
