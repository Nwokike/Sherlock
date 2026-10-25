"""StorageService Windows atomic-write resilience and instance sharing."""


import asyncio

from services.storage_service import StorageService


def test_singleton_shares_data_directory(tmp_path):
    a = StorageService(data_dir=tmp_path)
    b = StorageService(data_dir=tmp_path)
    assert a is b


def test_write_snapshot_persists(tmp_path):
    svc = StorageService(data_dir=tmp_path)
    ok = svc._write_snapshot({"k": "v"})
    assert ok is True
    assert svc._storage_file.exists()


def test_set_and_reload_roundtrip(tmp_path):
    async def _go():
        svc = StorageService(data_dir=tmp_path)
        await svc.set("alpha", "1")
        await svc.flush()
        # rebuild from disk
        svc2 = StorageService(data_dir=tmp_path)
        assert await svc2.get("alpha") == "1"

    asyncio.run(_go())


def test_write_snapshot_retries_on_permission_error(tmp_path, monkeypatch):
    svc = StorageService(data_dir=tmp_path)
    calls = {"n": 0}
    real_replace = __import__("os").replace

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("[WinError 5] Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr("os.replace", flaky)
    ok = svc._write_snapshot({"k": "v"})
    assert ok is True
    assert calls["n"] >= 3


def test_write_snapshot_gives_up_after_max_retries(tmp_path, monkeypatch):
    svc = StorageService(data_dir=tmp_path)

    def always_fail(src, dst):
        raise PermissionError("[WinError 5] Access is denied")

    monkeypatch.setattr("os.replace", always_fail)
    ok = svc._write_snapshot({"k": "v"})
    assert ok is False
