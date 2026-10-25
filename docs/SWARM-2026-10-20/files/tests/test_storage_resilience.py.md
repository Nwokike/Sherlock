# Audit report — tests/test_storage_resilience.py (Sherlock V3)

**Target:** `tests/test_storage_resilience.py` (59 lines)
**Source under test:** `src/services/storage_service.py`
**Verdict:** 5/5 tests pass, but the file's regression value is real yet narrow; its most important test (`test_set_and_reload_roundtrip`, :22-31) is **blind**, and several storage failure modes have zero coverage.

---

## 1) File role

The file is the *only* dedicated resilience test for `StorageService`. Its docstring (`tests/test_storage_resilience.py:1`) scopes it to "Windows atomic-write resilience and instance sharing". It exercises the singleton-per-directory pattern, the synchronous `_write_snapshot` atomic-replace path, and the Windows `PermissionError`/`[WinError 5]` retry backoff. It does **not** exercise async `set`/`flush` interplay, corrupt-file recovery, `.bak` creation, invalid UTF-8, or concurrency.

Import wiring (for context): `pyproject.toml` sets `pythonpath = ["src"]`, so `from services.storage_service import StorageService` (`tests/test_storage_resilience.py:6`) resolves to `src/services/storage_service.py`.

---

## 2) What is actually asserted (verbatim)

Five tests, all passing:

**`test_singleton_shares_data_directory`** (:9-12)
```python
def test_singleton_shares_data_directory(tmp_path):
    a = StorageService(data_dir=tmp_path)
    b = StorageService(data_dir=tmp_path)
    assert a is b
```
Covers: singleton-per-directory identity (`storage_service.py:82-91`, `__new__`).

**`test_write_snapshot_persists`** (:15-19)
```python
def test_write_snapshot_persists(tmp_path):
    svc = StorageService(data_dir=tmp_path)
    ok = svc._write_snapshot({"k": "v"})
    assert ok is True
    assert svc._storage_file.exists()
```
Covers: `_write_snapshot` returns True and leaves `storage.json` present (`storage_service.py:183-223`).

**`test_set_and_reload_roundtrip`** (:22-31)
```python
def test_set_and_reload_roundtrip(tmp_path):
    async def _go():
        svc = StorageService(data_dir=tmp_path)
        await svc.set("alpha", "1")
        await svc.flush()
        # rebuild from disk
        svc2 = StorageService(data_dir=tmp_path)
        assert await svc2.get("alpha") == "1"

    asyncio.run(_go())
```
Covers (nominally): set → flush → reconstruct from disk → get. See section 3: it does **not** actually rebuild from disk.

**`test_write_snapshot_retries_on_permission_error`** (:34-48)
```python
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
```
Covers: `os.replace` PermissionError/WinError-5 retry backoff succeeding within `max_retries = 6` (`storage_service.py:204-213`).

**`test_write_snapshot_gives_up_after_max_retries`** (:51-59)
```python
def test_write_snapshot_gives_up_after_max_retries(tmp_path, monkeypatch):
    svc = StorageService(data_dir=tmp_path)

    def always_fail(src, dst):
        raise PermissionError("[WinError 5] Access is denied")

    monkeypatch.setattr("os.replace", always_fail)
    ok = svc._write_snapshot({"k": "v"})
    assert ok is False
```
Covers: `_write_snapshot` returns `False` when retries are exhausted (`storage_service.py:221-223`).

### Failure modes COVERED
- Windows `[WinError 5]` / `PermissionError` transient retry + backoff (`storage_service.py:204-213`) — tested via monkeypatch, which is what makes it runnable on Linux.
- Atomic replace via `os.replace` after temp-file write + `fsync` (`storage_service.py:203,208`) — exercised but not asserted beyond file existence.
- Singleton-per-directory sharing (`storage_service.py:82-91`).

### Failure modes MISSED (zero assertions)
- Corrupt JSON recovery and `.bak` creation (`storage_service.py:161-176`, `:23-31`).
- Invalid UTF-8 / `UnicodeDecodeError` path (`storage_service.py:157` outside the parse try → `:179` outer handler, no `.bak`).
- Concurrent `set()` landing during a write (orphaned dirty flag) — debounce path `_save_now` (`storage_service.py:229-231`).
- `flush()` holding a `threading.Lock` across an `await` (`storage_service.py:334-335`).
- Atomic-replace guarantees: temp-file cleanup, `fsync`, original preserved on failure (`storage_service.py:194-218`).
- Singleton never re-reads disk after first construction (`storage_service.py:82-97`).

---

## 3) Blind-spot analysis — the ":22-31" claim

**Claim to verify:** "`tests/test_storage_resilience.py:22-31` is blind for the same reason [the singleton never re-reads disk]."

**Verdict: CONFIRMED.** The test is blind — it does not validate disk persistence at all.

Evidence from source:
- `StorageService.__new__` (`storage_service.py:82-91`) returns the cached instance keyed by resolved data dir; a second `StorageService(data_dir=tmp_path)` is the **same object**.
- `__init__` (`storage_service.py:93-97`) returns early when `self._initialized` is already `True`, **skipping `_load()`** (`storage_service.py:129-132`), which is the only disk read.
- Therefore `svc2 is svc` and `svc2.get("alpha")` reads the **in-memory** `self._data`, not disk.

Empirical confirmation (ran against the real `.venv`, nothing written to disk):
```
svc2 is svc (singleton): True
get alpha WITHOUT flush (in-memory): 1
storage.json exists on disk: False
```
So `test_set_and_reload_roundtrip` passes even when `flush()` never writes `storage.json`. The comment `# rebuild from disk` (`tests/test_storage_resilience.py:27`) is misleading — nothing is rebuilt from disk. To make the test genuine, the singleton must be bypassed (clear `_INSTANCES`, force a reload, or assert on the raw `storage.json` bytes) before constructing `svc2`.

Related: `_save_now` (`storage_service.py:225-231`) clears `self._dirty = False` whenever `_write_snapshot` succeeds, even if a `set()` landed during the write (`storage_service.py:298-300` sets `_dirty = True` after the snapshot was taken at `:229`). `_fire_timer` then re-reads `_dirty` (`storage_service.py:266-268`), sees `False`, and does not re-arm → the late `set()` is orphaned/lost until the next `set()`. `flush()` handles this correctly (`storage_service.py:339-340`, clears dirty only if `self._data == snapshot`), but the debounce/`_save_now` path does not, and no test covers either.

Note on the context claim "`flush()` holds a threading.Lock across await" (`storage_service.py:334`): precisely, it is `_flush_lock` (a `threading.Lock`, `storage_service.py:105`) held across `await asyncio.to_thread(...)` (`storage_service.py:334-335`). `_lock` itself is released before the await. This is a liveness footgun (a non-reentrant `threading.Lock` held across a suspension point) but is not what makes the roundtrip test blind.

---

## 4) Proposed improvements (concrete sketches)

All sketches read-only w.r.t. the source; they are test additions plus, where noted, a one-line source observation.

### 4.1 Make the roundtrip test actually hit disk
Clear the singleton cache so `svc2` re-reads disk, or assert on raw file bytes.
```python
def test_set_and_reload_roundtrip(tmp_path):
    async def _go():
        svc = StorageService(data_dir=tmp_path)
        await svc.set("alpha", "1")
        await svc.flush()
        # force a fresh instance that re-reads disk
        StorageService._INSTANCES.clear()          # module-level cache
        svc2 = StorageService(data_dir=tmp_path)
        assert await svc2.get("alpha") == "1"
    asyncio.run(_go())
```
(Setting `_INSTANCES` requires importing it from `services.storage_service`.) Alternatively assert `json.loads((tmp_path/"storage.json").read_text())["alpha"] == "1"`.

### 4.2 Corrupt JSON recovery + `.bak` creation (MISSING)
`_backup_corrupt_file` (`storage_service.py:23-31`) renames a non-empty corrupt file to `<name>.corrupt.<ts>.bak`, and `_load` (`storage_service.py:161-176`) calls it on `JSONDecodeError`. No test writes corrupt JSON.
```python
def test_corrupt_json_is_backed_up_and_reset(tmp_path):
    (tmp_path / "storage.json").write_text("{not valid json", encoding="utf-8")
    svc = StorageService(data_dir=tmp_path)
    assert svc.get_all() == {}   # or async get equivalent
    baks = list(tmp_path.glob("storage.json.corrupt.*.bak"))
    assert len(baks) >= 1        # .bak evidence survives
```

### 4.3 Invalid UTF-8 → no crash, but NO `.bak` (MISSING / gap)
`read_text(encoding="utf-8")` at `storage_service.py:157` is **outside** the parse `try` (`storage_service.py:161-176`), so `UnicodeDecodeError` escapes to the outer `except` (`storage_service.py:179`) which resets `_data = {}` **without** calling `_backup_corrupt_file`. This is a genuine gap between intent (back up corrupt files) and behavior.
```python
def test_invalid_utf8_does_not_crash(tmp_path):
    (tmp_path / "storage.json").write_bytes(b"\xff\xfe{bad")
    svc = StorageService(data_dir=tmp_path)
    assert await svc.get_all() == {}
    # NOTE: current code creates NO .bak here — documents the source gap
```
If/when source is fixed to back up invalid-UTF-8 files, add a `.bak` assertion here.

### 4.4 Concurrent `set()` during `flush()`/`_write_snapshot` (MISSING)
The debounce path orphans a late `set()` (`storage_service.py:229-231` vs `298-300`); `flush()` is safer (`storage_service.py:339-340`). No concurrency test exists.
```python
def test_concurrent_set_during_flush_no_lost_update(tmp_path):
    svc = StorageService(data_dir=tmp_path)
    async def hammer():
        for i in range(50):
            await svc.set(f"k{i}", str(i))
    await asyncio.gather(hammer(), hammer(), svc.flush())
    # every key that was set should be retrievable; no silently-dropped writes
    all_data = await svc.get_all()
    assert all(v.isdigit() for v in all_data.values())
```

### 4.5 Atomic replace guarantees (MISSING)
`_write_snapshot` (`storage_service.py:183-223`) uses `mkstemp` + `fsync` + `os.replace` + temp cleanup. No test asserts the original is preserved on failure or that no `.tmp` lingers.
```python
def test_write_snapshot_keeps_original_on_replace_failure(tmp_path, monkeypatch):
    svc = StorageService(data_dir=tmp_path)
    await svc.set("existing", "1"); await svc.flush()
    original = (tmp_path / "storage.json").read_text()

    def boom(src, dst):
        raise OSError("simulated replace failure")
    monkeypatch.setattr("os.replace", boom)
    assert svc._write_snapshot({"k": "v"}) is False
    assert (tmp_path / "storage.json").read_text() == original   # untouched
    assert not list(tmp_path.glob(".storage.json.*.tmp"))        # no temp left behind
```

### 4.6 `flush()` threading.Lock across await (observation, low severity)
`storage_service.py:334-335` holds `_flush_lock` (`threading.Lock`) across `await asyncio.to_thread`. Consider an `asyncio.Lock` or releasing before the await to avoid cross-thread/suspension liveness issues. No test covers this; add only if source is changed.

---

## 5) Verdict

The claim "`tests/test_storage_resilience.py` is the only file with genuine regression value" is **partially true but overstated**.

- **True:** it is the only resilience test, and its WinError-5/`PermissionError` retry coverage (`tests/test_storage_resilience.py:34-59`, mapping to `storage_service.py:204-213`) is genuine regression value that would not run on Linux without the monkeypatch approach. Atomic-replace and singleton behavior are at least exercised.
- **Overstated:** `test_set_and_reload_roundtrip` (`tests/test_storage_resilience.py:22-31`) is **blind** — confirmed by `svc2 is svc` and an in-memory read with no `storage.json` on disk — so it does not assert disk persistence despite its name and comment. The file has **zero** coverage of corrupt-file recovery, `.bak` creation, invalid UTF-8, concurrent `set()` during write, and atomic-replace guarantees.

**Bottom line:** 5/5 passing does not mean resilience is verified. The file's regression value is narrow (Windows retry backoff + singleton). Treat it as a starting point, not proof of storage reliability. Recommended next step: add the section-4 tests (especially 4.1 disk-backed roundtrip, 4.2 corrupt-`.bak`, 4.3 invalid-UTF-8 behavior) before relying on this file for storage regressions. No files were modified during this audit.

**Citations:** `tests/test_storage_resilience.py:1,6,9-12,15-19,22-31,34-48,51-59`; `src/services/storage_service.py:17-20,23-31,65-80,82-91,93-97,100-108,121-132,153-181,157,161-176,172,175,179,183-223,194-218,203-213,225-231,229-231,243-269,266-268,288-301,298-300,323-341,334-335,339-340`.
