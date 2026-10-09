"""Regression tests for Fix Batch 2b (engines + infra).

Covers: classify_error substring fallback + exact-vocab stability, ILLEGAL →
errors bucket, _unavailable_result unified keys, EMAIL_FORMAT TLD fix,
graph empty schema + non-string guards, storage close/corrupt behavior,
pickle integrity meta fields.
"""

from services.email_service import (
    EMAIL_FORMAT,
    EmailService,
    _unavailable_result,
    validate_email,
)
from services.graph_service import get_graph_analytics
from services.sherlock_service import classify_error


def test_classify_exact_vocabulary_unchanged():
    assert classify_error("Rate limited") == "rate"
    assert classify_error("Bot protection") == "bot"
    assert classify_error("Captcha") == "bot"
    assert classify_error("Connecting failure") == "dead"
    assert classify_error("Connecting failure extra") == "dead"
    assert classify_error("Unknown", ["tls_fingerprint"]) == "bot"
    assert classify_error(None) == ""
    assert classify_error("") == ""


def test_classify_substring_fallback():
    # Variants outside maigret's exact vocabulary
    assert classify_error("HTTP 429") == "rate"
    assert classify_error("429 Too Many Requests") == "rate"
    assert classify_error("Rate limit exceeded") == "rate"
    assert classify_error("403 Forbidden") == "bot"
    assert classify_error("Cloudflare challenge") == "bot"
    assert classify_error("WAF blocked") == "bot"
    assert classify_error("Some novel transport failure") == "error"


def test_unavailable_result_unified_keys():
    res = _unavailable_result("GitHub", "Connection timed out")
    assert res.others["message"] == "Connection timed out"
    assert res.others["url"] is None
    assert res.others["extra"] == {}
    assert res.others["media"] == {}
    assert res.others["error"] == "Connection timed out"


def test_email_format_rejects_pipe_tld():
    assert not EMAIL_FORMAT.fullmatch("a@b.c|")
    assert EMAIL_FORMAT.fullmatch("user@example.com")
    assert not EMAIL_FORMAT.fullmatch("not-an-email")
    assert validate_email("user@example.com")
    assert not validate_email("a@b.c|")


def test_graph_empty_schema_complete():
    analytics = get_graph_analytics(None)
    assert analytics["component_sizes"] == []
    assert analytics["top_canonical_nodes"] == []
    assert analytics["nodes"] == 0


def test_graph_non_string_phone_and_email_guarded():
    """int phone / list recovery must not raise during graph build."""
    from services.graph_service import build_identity_graph

    email_results = [
        {
            "name": "GitHub",
            "domain": "github.com",
            "exists": True,
            "emailrecovery": ["not-a-string"],
            "phoneNumber": 15551234567,
            "others": {},
        }
    ]
    graph = build_identity_graph(
        username="alice", found_accounts=[], email_results=email_results
    )
    assert graph is not None


def test_email_overlap_guard():
    svc = EmailService()
    assert svc._progress is None or not svc._progress.is_running


def test_pickle_meta_carries_payload_hash(tmp_path, monkeypatch):
    """save_compiled_db writes pkl_sha256/pkl_size; tampered payload misses."""
    import services.cache_service as cache
    from tests.test_batch_2b_helper_db import HelperDB

    monkeypatch.setattr(cache, "_cache_root", lambda: tmp_path)

    src = tmp_path / "sites.json"
    src.write_text('{"sites": []}')
    cache.save_compiled_db(str(src), HelperDB())

    import json

    meta = json.loads((tmp_path / "compiled_db.meta.json").read_text())
    assert "pkl_sha256" in meta
    assert "pkl_size" in meta

    # Tamper the payload → load must miss, not unpickle.
    pkl = tmp_path / "compiled_db.pkl"
    raw = bytearray(pkl.read_bytes())
    raw[-1] ^= 0xFF
    pkl.write_bytes(bytes(raw))
    assert cache.try_load_compiled_db(str(src)) is None


def test_storage_corrupt_backup(tmp_path):
    """Corrupt storage.json is backed up, not silently wiped."""
    import asyncio
    import json

    from services.storage_service import StorageService

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "storage.json").write_text("{not valid json!!!")

    svc = StorageService(page=None, data_dir=data_dir)
    assert svc._data == {}
    backups = list(data_dir.glob("storage.json.corrupt.*.bak"))
    assert len(backups) == 1
    assert "not valid json" in backups[0].read_text()

    async def _roundtrip():
        await svc.set("k", "v")
        await svc.flush()
        return await svc.get("k")

    assert asyncio.run(_roundtrip()) == "v"
    assert json.loads((data_dir / "storage.json").read_text()) == {"k": "v"}


def test_storage_close_flushes(tmp_path):
    import asyncio

    from services.storage_service import StorageService

    data_dir = tmp_path / "data2"
    svc = StorageService(page=None, data_dir=data_dir)

    async def _run():
        await svc.set("a", "1")
        await svc.close()
        return await svc.get("a")

    assert asyncio.run(_run()) == "1"
    assert svc._pending_write_task is None
