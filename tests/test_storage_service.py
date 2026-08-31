"""Unit tests for StorageService and modern Flet storage paths."""

import asyncio
import os
from services.storage_service import (
    StorageService,
    get_cache_dir,
    get_storage_dir,
    get_temp_dir,
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
