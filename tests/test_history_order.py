"""History ordering contract.

Storage (STORAGE_HISTORY) is oldest-first; the observable
state.history mirror is ALWAYS newest-first so both the Home "Recent"
rows and the History screen show the most recent search on top.
"""

import asyncio
import json

from core.constants import STORAGE_HISTORY
from core.state import state
from main import AppController


class _StubStorage:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value


def test_save_keeps_state_newest_first_and_storage_oldest_first(fake_page):
    controller = AppController(fake_page)
    controller.storage = _StubStorage()
    try:
        asyncio.run(controller._save_to_history("alice", 3, 10))
        asyncio.run(controller._save_to_history("bob", 5, 10))
        asyncio.run(controller._save_to_history("carol", 7, 10))

        # Observable state: newest first → Home Recent / History top row.
        assert [e["username"] for e in list(state.history)[:3]] == [
            "carol",
            "bob",
            "alice",
        ]

        # Stored JSON: full append order preserved (oldest first). A 2-save
        # probe cannot detect a writer that reverses; three can.
        stored = json.loads(controller.storage.data[STORAGE_HISTORY])
        assert [e["username"] for e in stored] == ["alice", "bob", "carol"]
    finally:
        state.history.clear()


def test_startup_load_normalizes_to_newest_first():
    """The Home loader reverses the stored oldest-first list."""
    entries_oldest_first = [
        {"username": "old", "found": 1, "total": 9, "timestamp": "t1"},
        {"username": "mid", "found": 2, "total": 9, "timestamp": "t2"},
        {"username": "new", "found": 3, "total": 9, "timestamp": "t3"},
    ]
    from services.storage_service import load_history_entries

    try:
        state.history.clear()
        # Exercise the REAL loader, not a local reversed() copy.
        loaded = load_history_entries(json.dumps(entries_oldest_first))
        state.history.extend(loaded)
        assert [e["username"] for e in state.history[:3]] == ["new", "mid", "old"]
    finally:
        state.history.clear()
