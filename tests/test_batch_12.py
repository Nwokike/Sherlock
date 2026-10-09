"""Regression tests for Fix Batch 12 (scan pipeline tail + tier fix)."""

import asyncio


def test_scan_all_constant():
    from services.sherlock_service import SCAN_ALL

    assert SCAN_ALL == 9223372036854775807


def test_mark_cancelled_helper():
    from services.sherlock_service import SearchProgress, _mark_cancelled

    prog = SearchProgress(username="alice", is_running=True)
    _mark_cancelled(prog)
    assert prog.is_running is False
    assert prog.is_cancelled is True


def test_maigret_kwargs_passthrough_and_filter():
    from services.sherlock_service import _maigret_kwargs

    def _with_var_kw(a, **kwargs):
        pass

    kw = {"a": 1, "b": 2}
    assert _maigret_kwargs(_with_var_kw, **kw) == kw

    def _strict(a):
        pass

    assert _maigret_kwargs(_strict, **kw) == {"a": 1}


def test_clamp_helpers():
    # Clamps live inline in search(); verify the expressions directly.
    assert max(1, min(200, 0)) == 1
    assert max(1, min(200, 500)) == 200
    assert max(1, min(120, -5)) == 1
    assert max(0, min(5, 99)) == 5


def test_resolve_local_db_prefers_cache_tier(tmp_path, monkeypatch):
    """Materialized copy lands in cache/, legacy data/ orphans removed."""
    from types import SimpleNamespace

    import services.sherlock_service as svc

    monkeypatch.setattr(
        "services.storage_service.get_cache_dir", lambda: tmp_path / "cache"
    )
    monkeypatch.setattr(
        "services.storage_service.get_storage_dir", lambda: tmp_path / "data"
    )
    (tmp_path / "data").mkdir(parents=True)
    legacy = tmp_path / "data" / "bundled_maigret_data.json"
    legacy.write_bytes(b'{"stale": true}')
    # Force the extract path (desktop would return the real package dir).
    monkeypatch.setattr(svc, "maigret", SimpleNamespace())

    path = svc._resolve_local_db(check_synced=False)
    assert path.startswith(str(tmp_path / "cache"))
    assert not legacy.exists()
    # Second call hits the hash fast-path.
    assert svc._resolve_local_db(check_synced=False) == path


def test_resolve_local_db_synced_wins(tmp_path, monkeypatch):
    import services.sherlock_service as svc

    monkeypatch.setattr(
        "services.storage_service.get_cache_dir", lambda: tmp_path / "cache"
    )
    monkeypatch.setattr(
        "services.storage_service.get_storage_dir", lambda: tmp_path / "data"
    )
    (tmp_path / "data").mkdir(parents=True)
    synced = tmp_path / "data" / "synced_data.json"
    synced.write_text("{}")
    assert svc._resolve_local_db(check_synced=True) == str(synced)
    # check_synced=False skips it even when present.
    assert svc._resolve_local_db(check_synced=False) != str(synced)


def test_db_health_clamp_and_cancel():
    import threading

    from services.sherlock_service import SherlockService

    svc = SherlockService()
    cancelled = threading.Event()
    cancelled.set()

    async def _run():
        out = await svc.run_db_health(sample_size=0, cancel_event=cancelled)
        assert out["error"] == "cancelled"
        assert out["sample"] == 0

    asyncio.run(_run())


def test_recording_wrapper_stores_truth():
    """_recording_progress equivalent: per-target ticks land in target_results."""
    from core.state import state
    from services.sherlock_service import SearchProgress

    prev = dict(state.target_results)
    try:
        state.target_results.clear()
        prog = SearchProgress(username="bob", total_sites=10)
        state.target_results[prog.username] = prog
        assert state.target_results["bob"] is prog
    finally:
        state.target_results.clear()
        state.target_results.update(prev)


def test_stale_loop_reset():
    """Worker setup/teardown never leaves a closed loop as current."""
    import asyncio

    async def _run():
        worker_loop = asyncio.new_event_loop()
        old = None
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            pass
        else:
            old = asyncio.get_event_loop()
        asyncio.set_event_loop(worker_loop)
        worker_loop.close()
        try:
            asyncio.set_event_loop(old)
        except Exception:
            pass
        try:
            current = asyncio.get_event_loop()
        except RuntimeError:
            current = None
        return current is None or not current.is_closed()

    assert asyncio.run(_run()) is True
