"""Unit tests for StorageService and modern Flet storage paths."""

import asyncio
import json
import os

import pytest

from services.storage_service import (
    StorageService,
    encode_history_entries,
    get_cache_dir,
    get_storage_dir,
    get_temp_dir,
    load_history_entries,
)


def test_get_storage_dir_default(monkeypatch):
    monkeypatch.delenv("FLET_APP_STORAGE_DATA", raising=False)
    d = get_storage_dir()
    assert ".flet" in str(d)
    assert str(d).endswith(os.path.join("storage", "data"))


def test_get_storage_dir_custom_env(monkeypatch, tmp_path):
    custom_dir = str(tmp_path / "custom_storage")
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", custom_dir)
    d = get_storage_dir()
    assert str(d) == custom_dir


def test_get_storage_dir_relative_env(monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", "storage/data")
    d = get_storage_dir()
    assert ".flet" in str(d)
    assert str(d).endswith(os.path.join("storage", "data"))


def test_get_cache_and_temp_dirs(monkeypatch):
    monkeypatch.delenv("FLET_APP_STORAGE_CACHE", raising=False)
    monkeypatch.delenv("FLET_APP_STORAGE_TEMP", raising=False)
    c = get_cache_dir()
    t = get_temp_dir()
    assert str(c).endswith(os.path.join("storage", "cache"))
    assert str(t).endswith(os.path.join("storage", "temp"))


def test_storage_service_crud_atomic(tmp_path):
    storage = StorageService(data_dir=tmp_path)

    # Set value
    asyncio.run(storage.set("theme", "dark"))
    asyncio.run(storage.flush())

    storage_file = tmp_path / "storage.json"
    assert storage_file.exists()
    assert "dark" in storage_file.read_text(encoding="utf-8")

    # Read value
    val = asyncio.run(storage.get("theme"))
    assert val == "dark"

    # Delete value
    asyncio.run(storage.delete("theme"))
    asyncio.run(storage.flush())
    val_after = asyncio.run(storage.get("theme"))
    assert val_after is None

    # No leftover .tmp files
    assert not (tmp_path / "storage.tmp").exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_delete_absent_key_noop(tmp_path):
    """Deleting a missing key must not dirty the store or arm a write."""
    storage = StorageService(data_dir=tmp_path)

    async def _run():
        await storage.set("a", "1")
        await storage.flush()
        mtime = (tmp_path / "storage.json").stat().st_mtime
        assert storage._dirty is False
        handle_before = storage._pending_write_task
        await storage.delete("missing-key")
        assert storage._dirty is False
        # Absent-key delete must not re-arm the timer or touch the file.
        assert storage._pending_write_task is handle_before
        assert (tmp_path / "storage.json").stat().st_mtime == mtime

    asyncio.run(_run())


def test_clear_empty_noop_and_nonempty(tmp_path):
    storage = StorageService(data_dir=tmp_path)

    async def _run():
        await storage.clear()
        assert storage._dirty is False
        await storage.set("a", "1")
        await storage.set("b", "2")
        await storage.clear()
        assert await storage.get("a") is None
        await storage.flush()
        assert await storage.get("b") is None

    asyncio.run(_run())


def test_get_all_returns_copy(tmp_path):
    storage = StorageService(data_dir=tmp_path)

    async def _run():
        await storage.set("k", "v")
        snapshot = await storage.get_all()
        assert snapshot == {"k": "v"}
        snapshot["k"] = "mutated"
        snapshot["evil"] = "x"
        assert await storage.get("k") == "v"
        assert await storage.get("evil") is None

    asyncio.run(_run())


def test_set_rejects_non_string_immediately(tmp_path):
    """TypeError at set() time — not 1s later in the debounce task."""
    storage = StorageService(data_dir=tmp_path)

    async def _run():
        with pytest.raises(TypeError):
            await storage.set(123, "v")
        with pytest.raises(TypeError):
            await storage.set("k", 30)
        assert storage._dirty is False

    asyncio.run(_run())


def test_encode_trims_legacy_oversized(tmp_path):
    entries = [{"q": str(i)} for i in range(60)]
    out = json.loads(encode_history_entries(entries))
    assert len(out) == 50
    assert out[0] == {"q": "10"}
    out2 = json.loads(encode_history_entries(entries, {"q": "new"}))
    assert len(out2) == 50
    assert out2[-1] == {"q": "new"}


def test_load_filters_non_dicts():
    raw = json.dumps([{"query": "a"}, 42, "oops", None, {"query": "b"}])
    entries = load_history_entries(raw)
    assert entries == [{"query": "b"}, {"query": "a"}]
    assert load_history_entries(None) == []
    assert load_history_entries('{"not": "a list"}') == []


def test_rapid_set_flush_no_lost_write(tmp_path):
    """Concurrent set() during flush() must not strand a dirty write."""

    async def _run():
        storage = StorageService(data_dir=tmp_path)
        await asyncio.gather(*[storage.set(f"k{i}", str(i)) for i in range(20)])
        await storage.flush()
        for i in range(20):
            assert await storage.get(f"k{i}") == str(i)
        # Round-trips through a fresh loader.
        reloaded = StorageService(data_dir=tmp_path)
        for i in range(20):
            assert await reloaded.get(f"k{i}") == str(i)

    asyncio.run(_run())
