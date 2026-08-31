"""Unit tests for history mode persistence and auto-switching."""

import asyncio
import json
from core.constants import MODE_EMAIL, MODE_USERNAME, STORAGE_HISTORY
from state.app_state import state


class MockStorage:
    def __init__(self):
        self._data = {}

    async def get(self, key: str):
        return self._data.get(key)

    async def set(self, key: str, value: str):
        self._data[key] = value

    async def delete(self, key: str):
        self._data.pop(key, None)


def test_history_saves_and_persists_mode(fake_page):
    from main import AppController

    storage = MockStorage()
    controller = AppController(fake_page)
    controller.storage = storage

    state.history.clear()
    try:
        # Save username search
        asyncio.run(
            controller._save_to_history(
                "johndoe", found=12, total=368, mode=MODE_USERNAME
            )
        )
        assert len(state.history) == 1
        assert state.history[0]["mode"] == MODE_USERNAME
        assert state.history[0]["query"] == "johndoe"
        assert state.history[0]["username"] == "johndoe"

        # Save email search
        asyncio.run(
            controller._save_to_history(
                "jane@example.com", found=5, total=121, mode=MODE_EMAIL
            )
        )
        assert len(state.history) == 2
        assert state.history[0]["mode"] == MODE_EMAIL
        assert state.history[0]["query"] == "jane@example.com"
        assert state.history[1]["mode"] == MODE_USERNAME

        # Verify storage serialization
        raw = asyncio.run(storage.get(STORAGE_HISTORY))
        assert raw is not None
        entries = json.loads(raw)
        assert len(entries) == 2
        assert entries[0]["mode"] == MODE_USERNAME
        assert entries[1]["mode"] == MODE_EMAIL
    finally:
        state.history.clear()
