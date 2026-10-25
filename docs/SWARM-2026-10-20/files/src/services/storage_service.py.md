# Audit — `src/services/storage_service.py` (367 lines)

Audited 2026-10-22. Ground truth: installed deps only — `flet 1.0.4`
(`.venv/Lib/site-packages/flet`), Python 3.14.7. Read-only audit; no file was modified.
All runtime claims below were reproduced with throwaway probes against the
installed venv (temp dirs only, outside the repo).

---

## 1) File role

`src/services/storage_service.py` is the app's **persistence layer**: a
singleton-per-directory string key/value store that persists UI settings and
scan state as a single JSON file (`storage.json`) in Flet's *data* storage tier.

Two halves:

* **A file-backed KV store** — `StorageService` (`:65-341`). Writes are debounced
  by 1.0s (`:17`) and land through an atomic `mkstemp` + `os.replace` sequence
  (`:194-219`) with a Windows WinError-5 backoff (`:204-213`).
* **Two module-level history codecs** — `load_history_entries` (`:344-358`) and
  `encode_history_entries` (`:361-367`), shared by `HomeScreen` and `AppController`
  to keep the oldest-first/newest-first reversal in one place.

Path resolution helpers: `get_storage_dir` (`:34-44`), `get_cache_dir` (`:47-53`),
`get_temp_dir` (`:56-62`). `get_cache_dir` is consumed by
`src/services/cache_service.py:51-53`; `get_temp_dir` has **zero callers** in `src/`.

Producers/consumers of the store:

| Role | Site |
|------|------|
| Primary owner | `src/main.py:511` → `StorageService(self.page)` |
| Secondary owners (same singleton) | `src/screens/home_screen.py:418,434,497,784`, `src/screens/history_screen.py:116,147,400`, `src/screens/settings_screen.py:327,694`, `src/components/app_header.py:146`, `src/screens/onboarding_screen.py:127` |
| Restore list | `src/main.py:635-849` (`_load_saved_state`) + `src/main.py:2223` (history) |

The class docstring (`:66-80`) is unusually honest about *why* it exists (the
old code made one instance per screen, each with its own debounce timer, which
raced `os.replace` on the same file). That intent is real; the implementation
only partly delivers it (see §4).

---

## 2) Storage API verification against installed flet 1.0.4

### 2.1 Every Flet API this file touches

| API used here | Exists in flet 1.0.4? | Evidence (`.venv/Lib/site-packages/flet/`) |
|---|---|---|
| **`page.client_storage`** (`:137`, `:236`) | **NO — DOES NOT EXIST** | `grep -rn "client_storage" .venv/Lib/site-packages/flet/` → **0 hits** (all file types). It is a Flet **0.x** API. |
| **`page.session_id`** (`:124`, `:126`) | **NO — not a `Page` attribute** | `grep -rn "session_id" flet/` → only `messaging/protocol.py:307,354` (a request dataclass), `messaging/session.py:72` (`self.__id`), `pubsub/pubsub_client.py`. No `Page.session_id`. |
| **`page.web`** (`:124`, `:126`) | **YES** | `flet/controls/page.py:516` → `web: bool = False` |
| `ft.Page` (type annotation `:82`, `:93`) | YES | `flet/controls/page.py` |
| `FLET_APP_STORAGE_DATA` / `_CACHE` / `_TEMP` (`:40`, `:49`, `:58`) | YES | documented in `flet/controls/services/storage_paths.py:27, 72, 188`. The full set of `FLET_APP_*` vars in 1.0.4 is `FLET_APP_CONSOLE`, `FLET_APP_HIDDEN`, `FLET_APP_STORAGE_CACHE`, `FLET_APP_STORAGE_DATA`, `FLET_APP_STORAGE_TEMP`, `FLET_APP_WEB`. |
| `flet.StoragePaths` | YES | `flet/controls/services/storage_paths.py:12` — but **all methods are `async`** and raise `FletUnsupportedPlatformException` on web (`:35-38, 59-62, 81-84, 99-102, 118-122, 137-140, 156-159, 172-175, 196-199, 218-221`) |
| `flet.SharedPreferences` | YES | `flet/controls/services/shared_preferences.py:13`; value types `str/int/float/bool/list[str]` (`:8`, validated `:39-46`); **all methods are `async`** (`set` `:18`, `get` `:49`, `contains_key` `:61`, `remove` `:73`, `get_keys` `:85`, `clear` `:97`) |
| `page.shared_preferences` / `page.storage_paths` accessor | **NO** | `grep "def shared_preferences\|def storage_paths"` over the package → 0 hits |
| `page.services` (list property) | YES | `flet/controls/base_page.py:823-832` — `services` getter/setter over `__root_view().services`. This is the correct mount point for a `SharedPreferences` instance (see `src/core/shared_services.py:57-58`, `src/main.py:492,501`). |

### 2.2 What actually backs the "web storage path"

**Nothing.** The sibling claim is **CONFIRMED**:
`page.client_storage` does not exist in flet 1.0.4, so both web branches are
dead:

* `:136` `hasattr(self._page, "client_storage")` → always `False` → the
  `cs.get("sherlock_storage")` read never runs.
* `:235` the same guard → the `cs.set(...)` write never runs.

Runtime probe (duck-typed page with `web = True`):

```
is_web: True | has client_storage: False | data: {}
after set -> dirty: True | files: []          # nothing written, no error raised
```

The **only** browser-persistent primitive in flet 1.0.4 is
`flet.SharedPreferences` (`shared_preferences.py:13`), mounted via
`page.services.append(ft.SharedPreferences())` and driven with `await`
(`shared_preferences.py:18,49`). Its key constraints are only Android's three
forbidden base64 prefixes (`shared_preferences.py:24-26`); `"sherlock_storage"`
is unaffected.

`flet.StoragePaths` is the other half of the modern API, but it is **path
resolution only** and is explicitly unsupported on web — it cannot back a
browser KV store.

### 2.3 The `.flet/storage/data` fallback is a Flet 0.x concept

`get_storage_dir()`'s docstring (`:35-38`) claims *"Flet's sandbox
(.flet/storage/data)"*. Grep for `.flet/storage` / `".flet"` over the installed
flet package → **0 hits**. Flet 1.0.4 exposes the data dir through
`FLET_APP_STORAGE_DATA` (→ `get_application_support_directory()`, see
`storage_paths.py:71-73`), i.e. the platform app-support directory, **not** a
project-local `.flet/storage/data`. The fallback at `:43-44` is therefore a
hand-rolled path that only ever applies outside a Flet runtime (tests). The
comment is stale and will mislead the next reader.

### 2.4 Non-Flet API surface in this file (all fine)

`threading`, `tempfile`, `os.replace`, `json`, `pathlib` — standard library,
all used correctly except where noted in §4.

---

## 3) Confirmed known issues (cross-checked)

| # | Claim | Verdict |
|---|-------|---------|
| K1 | `:137`/`:236` use `page.client_storage`, which doesn't exist in flet 1.0.4 → web storage path silently dead | **CONFIRMED** — 0 hits in the package; the web path writes nothing and reports success. See §4 N2 for the *worse* consequence. |
| K2 | `:204-213` has a Windows WinError-5 backoff for atomic `os.replace` | **CONFIRMED present and functional** — covered by `tests/test_storage_resilience.py:34-59`. Two flaws in it: see §4 N12. |
| K3 | `:288-297` enforces str-only values | **CONFIRMED** — `TypeError` on non-str key/value, raised before the lock. No current caller violates it (every `storage.set(...)` in `src/` passes `str`; `state.email_domains: str` at `src/core/state.py:75`, `state.proxy_file: str`). See §5.13 for the missed opportunity. |
| K4 | `:193` `json.dumps(..., indent=2)` — sibling measured ~980KB payloads, "could drop indent" | **PARTIALLY REFUTED.** The 980KB is a *payload* problem, not an *indent* problem. Every stored value is a **pre-serialized JSON string** (`main.py:877`, `main.py:2202-2203`, `main.py:2237` all do `json.dumps(...)` first), so `indent=2` only indents the outer ~45-key dict. Measured on a synthetic snapshot: `indent=2` 43 052 B vs compact 43 039 B → **1.00x, i.e. <0.03% overhead**. The real defect is that the *entire* snapshot — including the large `sherlock_cached_results` blob — is re-serialized and rewritten on every `set()`. See §5.10. |
| K5 | Keys written but never restored by `main.py:_load_saved_state` | **CONFIRMED, exactly 6** (not 3): `STORAGE_HUDSON` (written `src/screens/home_screen.py:568`), `STORAGE_EMAIL_DOMAINS` (`src/screens/settings_screen.py:634`), `STORAGE_PHONE_CONCURRENCY` (`src/screens/home_screen.py:477`, `src/screens/settings_screen.py:1209`), `STORAGE_PROXY_FILE` (`src/screens/settings_screen.py:641`), `STORAGE_SHOW_ALL_RESULTS` (`src/screens/settings_screen.py:606`), `STORAGE_VERBOSE_OUTPUT` (`src/screens/settings_screen.py:610`). Repo-wide grep for `.get(STORAGE_*)` finds **no read** for any of the six → the user's choice is silently discarded on restart. `STORAGE_MAX_CONNECTIONS` **is** written (`src/screens/settings_screen.py:1265`, via `_slider_commit`) — an earlier regex pass missed it; it is read+written, not dead. |

---

## 4) NEW bugs (severity-ordered)

### N1 — HIGH · Lost write: the debounce timer clears `_dirty` for a change it never wrote
`src/services/storage_service.py:229-231`

```python
if self._write_snapshot(dict(self._data)):
    self._dirty = False
```

`_save_now()` snapshots `self._data` and, on success, unconditionally sets
`_dirty = False` — **without comparing against the snapshot** (contrast `flush()`
at `:339`, which correctly does `if ok and self._data == snapshot`). If a
`set()` lands (:298-301, which sets `_dirty = True`) while the timer thread is
inside `_write_snapshot`, the completing write resets `_dirty` back to `False`,
and `_fire_timer`'s post-check (:266-269) sees "clean" and does **not** re-arm
the timer → that value is never written to disk.

Reproduced:

```
dirty after concurrent set-during-write: False     # the set() value is orphaned
```

This is the exact class of bug the class docstring (:103-105) claims to have
fixed; it was only ever fixed for `flush()`.

**Fix:** reuse the `flush()` guard in `_save_now()` — capture the snapshot,
write it, then `if self._data == snapshot: self._dirty = False`.

### N2 — HIGH · Web mode is a total, silent no-op (two stacked breakages)
`src/services/storage_service.py:121-127`, `:134-151`, `:233-241`

1. `_is_web` becomes `True` whenever `page.web` is `True` (:123-127). The
   class then **never** loads from disk (:131-132 `if not self._is_web: self._load()`).
2. `_load_web()` (:134) is **never called from anywhere** — `grep -rn "_load_web"
   src/ tests/` returns only its own definition and its own `except` handler. Dead
   method; even if `client_storage` existed, the persisted blob would never be
   restored.
3. `_save_now_web()` (:233-241): the `hasattr(self._page, "client_storage")`
   guard is `False` → the write is skipped, **but** `:238` still executes
   `self._dirty = False`, i.e. the app records the value as "persisted".

Net effect in a browser build: every setting, the history, and the cached
results are discarded on reload, with **zero** error surfaced to the user or the
log. (Desktop is unaffected — `page.web` is `False` there.)

### N3 — HIGH · `close()` is never called → the trailing debounce window is lost on exit
`src/services/storage_service.py:271-282`

`close()`'s own docstring says *"call on app teardown so the trailing write
window is never lost on exit"*. **Nobody calls it**: `grep -rn "\.close()" src/
tests/` returns only `loop.close()` in `email_service.py:340,412`,
`sherlock_service.py:270`, `phone_service.py:234` and `ad_service.close()` at
`main.py:2428`. The app entry point is `ft.run(main, assets_dir=...)`
(`src/main.py:2452`) with no exit hook that flushes storage.

Therefore any `set()` issued within the last `_WRITE_DEBOUNCE_SEC = 1.0`s
(`:17`) before the window closes is **silently dropped** — e.g. toggling NSFW or
changing the theme and immediately closing the app. Note the window is 1s *plus*
the write time, and `_fire_timer` only re-arms if `_dirty` is still set
(:266-269), which N1 can also defeat.

**Fix:** call `await storage.close()` from an app-exit hook (`page.on_app_lifecycle_state_change` → `PagePlatformState.HIDDEN`/`EXIT`, or `atexit` for the non-async path), and/or shrink the debounce to ~250ms for small writes.

### N4 — MEDIUM-HIGH · Flush vs. debounce-timer ordering race (the file can regress to an older snapshot)
`src/services/storage_service.py:105`, `:229`, `:263`, `:334`

`_flush_lock` (:105) is taken **only** by `flush()` (:334). The debounce path
`_fire_timer` → `_save_now` → `_write_snapshot` (:263, :229) bypasses it
entirely. Both writes serialize on the global `_FILE_LOCK` (:190), so the file
is never torn — but their **order is arbitrary**. Sequence:

1. timer thread takes snapshot **S2** (newer) and writes it;
2. `flush()`'s in-flight snapshot **S1** (older) lands second → the file on disk
   now holds the older content;
3. the `self._data == snapshot` guard at `:339` only clears the dirty flag; it
   does **not** undo the stale write, and if `self._data` happens to equal S1 the
   flag is cleared too → nothing re-writes S2.

The class docstring (:78-79, :103-105) claims *"two concurrent flushes can't
write an older snapshot after a newer one"* — that guarantee holds only for
flush-vs-flush, not flush-vs-timer.

**Fix:** route both paths through one ordered writer (e.g. have `_fire_timer`
acquire `_flush_lock` too, or drop the timer's direct write and have the timer
call `flush()`).

### N5 — MEDIUM · `flush()` holds a blocking `threading.Lock` across an `await` → event-loop stall
`src/services/storage_service.py:334-335`

```python
with self._flush_lock:
    ok = await asyncio.to_thread(self._write_snapshot, snapshot)
```

`asyncio.to_thread` yields the event loop while `_flush_lock` is held. A second
coroutine calling `flush()` on the same loop then blocks the **event-loop
thread** inside `Lock.acquire()` (a blocking OS call — the loop cannot process
other tasks until it returns). With `os.fsync` + Windows AV scanning on the
write path, that is a UI freeze of hundreds of ms to seconds. The class
docstring (:74-77) explicitly reasons about "loop-bound" locks but then uses a
loop-agnostic lock in a way that blocks the loop.

**Fix:** use an `asyncio.Lock` created per running loop, or move the locking
*inside* the worker thread (`await asyncio.to_thread(self._write_snapshot_locked, snapshot)`).

### N6 — MEDIUM · Invalid UTF-8 is silently reset with **no backup** (the `.bak` path can't fire)
`src/services/storage_service.py:157`, `:172`, `:179-181`

The corrupt-file backup at `:172-176` is inside the inner `try` (`:161`), but
`self._storage_file.read_text(encoding="utf-8")` is at `:157` — **outside** it.
A file with non-UTF-8 bytes therefore raises `UnicodeDecodeError` at `:157`,
which is caught by the broad `except Exception` at `:179` → `self._data = {}`
and **no `.bak` file is created** → the user's data is overwritten by the next
write with zero forensics.

Reproduced:

```
StorageService._load failed: 'utf-8' codec can't decode byte 0xff in position 0
invalid-utf8 backup created: []   | data: {}
```

The `UnicodeDecodeError` name in the `:172` tuple is therefore **unreachable**.
(The tuple is also redundant: `json.JSONDecodeError` and `UnicodeDecodeError`
are both subclasses of `ValueError`, so `except ValueError` alone suffices.)

By contrast, a genuine JSON syntax error *does* get backed up (verified):
`storage.json.corrupt.<ts>.bak` is created and the original is renamed away.

**Fix:** move `read_text` inside the `try`, and narrow the tuple to
`except (json.JSONDecodeError, UnicodeDecodeError):`.

### N7 — MEDIUM · "Disk is always the source of truth on construction" is false — the singleton never re-reads
`src/services/storage_service.py:78-79`, `:94-97`, `:129-132`

The class docstring (:78-79) and the comment at :129-130 both assert that a file
changed by another process is picked up on construction. The singleton
(`__new__` :82-91) makes this impossible: `_load()` runs **once per directory
per process**, and every later `StorageService(...)` call takes the early-return
at `:94-97` — which refreshes `_page` but **not** `_data`.

Reproduced:

```
external writer sets storage.json -> {"x":"EXTERNAL"}
StorageService(same dir).get("x") -> "1"      # stale in-memory value
is same obj: True
```

This also makes the test suite blind: `tests/test_storage_resilience.py:22-31`
is commented `# rebuild from disk`, but `svc2` **is** `svc` — the "round-trip"
never touches the disk.

**Fix:** either re-read under the lock on the early-return path (with a cheap mtime check to avoid the I/O), or correct the docstring and add a `reload()` API; fix the test to use a fresh process/dir.

### N8 — MEDIUM · Wrong-shaped JSON is silently coerced to `{}` — no backup, no log
`src/services/storage_service.py:162-171`

Only `json.JSONDecodeError` triggers the `.bak`. A syntactically valid but
structurally wrong file (e.g. a bare list, or a top-level `null`) falls into the
`if isinstance(parsed, dict) else {}` branch at `:169-170` → `self._data = {}`,
the file is left on disk, and the next write **overwrites it**. Same for a dict
whose values are not all `str` (`:164-168`): the offending entries are dropped
silently, with no log line.

Reproduced:

```
list JSON  -> data: {}   files: ['storage.json']   (no .bak, no log)
mixed types-> data: {'a': '1'}                    ('b':2, 'c':None dropped silently)
```

**Fix:** treat "unparseable" and "wrong shape" identically (back up + warn), and log the dropped keys.

### N9 — LOW-MEDIUM · No schema version; the module's own history codec is bypassed by its main consumer
`src/services/storage_service.py:344-358`, `:361-367`

There is no `__schema_version` key and no key allow-list. `_load` accepts any
`{str: str}` blob (:163-171), so a future format change silently degrades to
"no data".

Worse, `load_history_entries`/`encode_history_entries` are **not** used where the
history is actually written: `src/main.py:2223-2237` re-implements the codec
inline with `raw = await self.storage.get(STORAGE_HISTORY)` /
`entries = json.loads(raw) if raw else []` — **with no `try/except`**, so a
corrupt `sherlock_history` value raises `JSONDecodeError` inside the save path
and the newest scan is never recorded. That directly contradicts this file's
docstring at :347-348 (*"the reversed contract lives in one place"*). Current
users of the helpers: `src/screens/home_screen.py:781-786`,
`src/screens/history_screen.py:113-118` (load) and
`src/screens/history_screen.py:402` (encode).

### N10 — LOW · `_load_web` is entirely dead code
`src/services/storage_service.py:134-151` — defined, never called; its `except`
handler at :149-151 is unreachable too. (Root cause and consequence in N2.)

### N11 — LOW · The web-detection heuristic cannot work as documented
`src/services/storage_service.py:116-127`

* `getattr(page, "session_id", None)` (:124) is always `None` in flet 1.0.4 —
  `Page.session_id` does not exist (see §2.1). The `or` branch is dead.
* `hasattr(page, "web")` is **always True** for a real `Page`
  (`page.py:516`), so the fallback at `:126-127` (*"prefer client_storage"*)
  can only fire for duck-typed test doubles — where it selects a path that
  provably does not exist in the installed flet.
* The comment at :116-120 therefore describes an intent that no installed API
  can satisfy.

### N12 — LOW · The WinError-5 backoff retries the wrong errors and only covers `os.replace`
`src/services/storage_service.py:205-213`

* `except (PermissionError, OSError)` — `PermissionError` **is** an `OSError`
  subclass, so the tuple is redundant.
* Every `OSError` is retried, including non-transient ones (`ENOSPC`, `EDQUOT`,
  `EACCES` on a read-only dir) — wasting up to ~2.5s of backoff
  (`0.04·2^0 … 0.04·2^4` = 0.04+0.08+0.16+0.32+0.64 = 1.24s of sleeps, 6 attempts)
  before failing. Narrow it to `PermissionError` (WinError 5/32).
* The retry covers only `os.replace` (:208). The temp-file write at `:200-203`
  — the *more* AV-exposed path, since the temp file lives in the same
  directory — is not retried at all.

### N13 — LOW · The rename is not durably persisted (no directory fsync)
`src/services/storage_service.py:200-208`

The temp file's *data* is fsynced (:203) but the **directory entry** created by
`os.replace` is never flushed, so on POSIX a crash immediately after the write
can leave the file missing (Windows `MoveFileEx` gives no durability guarantee
either without `FlushFileBuffers` on the directory handle). Cheap to add on
POSIX (`fd = os.open(dir, os.O_RDONLY); os.fsync(fd); os.close(fd)`).

### N14 — LOW · Orphaned temp files are never reclaimed
`src/services/storage_service.py:194-219`

The `finally` at :214-219 only removes the temp file of the *current* attempt.
If the process is killed between `mkstemp` (:194) and `os.replace` (:208), a
`.storage.json.<rand>.tmp` file is orphaned in the storage directory forever —
verified: a stale `.storage.json.abc.tmp` survives `_load()` untouched. No
startup sweep exists.

### N15 — LOW · The singleton key is not case/format-normalized
`src/services/storage_service.py:83-84`, `:110-113`

`__new__` keys the instance on `str(target_dir.resolve())` (:84) while `__init__`
stores the **unresolved** path (:111). Two spellings of the same directory
(UNC vs. mapped drive, `\\?\` prefix, 8.3 short name, different drive-letter
case) can produce two different keys → **two independent `_data` caches writing
the same file**, i.e. exactly the `WinError 5` race the class was written to
eliminate. Use `os.path.normcase(str(target_dir.resolve()))`.

### N16 — LOW · Security: a credential-bearing proxy URL and PII are persisted in cleartext
`src/services/storage_service.py:101`, `:193`, `:288-301`

`STORAGE_PROXY_URL` stores the raw proxy string (`src/screens/settings_screen.py:483`),
which may embed `http://user:pass@host:port`; `STORAGE_SEARCH_KEYWORDS` persists
the user's typed search terms (PII). Both land verbatim in `storage.json`.

Mitigating: the file is created by `tempfile.mkstemp` → mode `0600` on POSIX and
`os.replace` preserves that mode, so on Linux/macOS the final `storage.json` is
owner-readable only; on Windows it inherits the `%APPDATA%` ACL (user-only by
default). There is **no encryption and no OS keyring**. Nothing is ever logged
(see N17), so the exposure is at-rest only. Recommend: strip/separate
credentials from the URL before persisting, or put them in the platform
keyring, and surface a warning in the Settings UI.

### N17 — INFO (positive) · No storage content is ever logged
Verified across the file: the only log statements are `:29` (paths), `:150`,
`:180`, `:222`, `:241` (exception messages). `logger.warning("StorageService.
_write_snapshot failed: %s", e)` can carry a path but never a value. No key,
value, or payload is written to the log.

### N18 — INFO · PEP 758 parentheseless `except` — valid on 3.14, SyntaxError on ≤3.13
`src/services/storage_service.py:172` → `except json.JSONDecodeError, ValueError, UnicodeDecodeError:`

This **compiles** on the project's interpreter (verified: `py_compile` succeeds
on Python 3.14.7, and `pyproject.toml:6` declares `requires-python = ">=3.14"`),
because Python 3.14 adopted PEP 758. It is *not* a bug in this repo — `src/main.py:664,
702, 719` use the same style project-wide. It is, however, a hard floor on 3.14
that any linter/interpreter on ≤3.13 will reject, and the tuple is redundant
(see N6). Worth a project-wide note, not a per-file change.

### N19 — INFO · Dead members
* `_last_write` (:107, set at :231, :239, :341) — **written four times, never read**. Dead state.
* `get_all()` (:319-321) — **zero callers** in `src/` and `tests/`. Dead public API.
* `get_temp_dir()` (:56-62) — zero callers (`get_cache_dir` is used by `cache_service.py:51-53`).
* `_INSTANCES` (:19) is never pruned — one leaked instance per distinct directory for the process lifetime.

---

## 5) Improvements (ordered by value/effort)

1. **Replace the hallucinated web API with the real one.** Mount
   `ft.SharedPreferences()` on `page.services` (`base_page.py:823-832`; pattern
   already used at `src/core/shared_services.py:57-58`) and convert
   `_load_web`/`_save_now_web` to `async` using
   `await sp.get("sherlock_storage")` / `await sp.set("sherlock_storage", payload)`
   (`shared_preferences.py:18,49`). Keep the JSON file for desktop. Note
   `SharedPreferences` natively supports `int/float/bool/list[str]`
   (`shared_preferences.py:8`), so the app can stop str-encoding everything.
2. **Call `close()` on teardown** (N3) — e.g. `page.on_app_lifecycle_state_change`
   on `HIDDEN`/`EXIT`, plus an `atexit` fallback — and consider dropping the
   debounce to 250–400 ms, which also shrinks the N1/N3 exposure window.
3. **Fix the lost-dirty race** (N1) by giving `_save_now` the same
   `self._data == snapshot` guard that `flush()` already has (:339).
4. **Serialize all writes through one path** (N4): have `_fire_timer` call
   `flush()` (or take `_flush_lock`) so timer and explicit flushes cannot
   reorder.
5. **Remove the blocking lock across `await`** (N5): move the lock acquisition
   inside the `asyncio.to_thread` worker, or use a per-loop `asyncio.Lock`.
6. **Make corrupt recovery uniform** (N6, N8): move `read_text` inside the
   parse `try`; back up + log on *any* structural failure (bad JSON, bad UTF-8,
   non-dict root, non-str values); simplify the exception tuple.
7. **Add `__schema_version`** (N9) written by the service and validated on
   load, and route `main.py:2223-2237` through this module's
   `load_history_entries`/`encode_history_entries` (the module already provides
   them; the consumer just doesn't use them).
8. **Prune dead keys** (K5): either add the missing restore paths in
   `main.py:_load_saved_state` for `STORAGE_HUDSON`, `STORAGE_EMAIL_DOMAINS`,
   `STORAGE_PHONE_CONCURRENCY`, `STORAGE_PROXY_FILE`, `STORAGE_SHOW_ALL_RESULTS`,
   `STORAGE_VERBOSE_OUTPUT` — or stop writing them. A key registry in the
   service would let it GC unknown keys on load.
9. **Split the blob** (K4): keep `sherlock_cached_results` (the ~1MB payload)
   in its own file (or in `get_cache_dir()`), so toggling a boolean setting
   doesn't rewrite it. Keep `indent=2` for the small settings file — it is
   cheap (measured <0.03%) and makes the file diffable/hand-editable; drop it
   only for the results blob.
10. **Add byte accounting + a size cap**: expose the per-key size (the service
    already has `get_all()`), log a warning past a threshold, and prune the
    oldest `sherlock_cached_results` entries.
11. **Sweep stale `.tmp` files** at startup (N14) and use
    `os.path.normcase` for the singleton key (N15).
12. **Narrow the backoff** to `PermissionError` only (N12) and add a directory
    fsync on POSIX (N13).
13. **Reconsider the str-only contract** (K3): keep the `TypeError` for
    non-serializable input, but allow `int|float|bool` (stored as a typed JSON
    envelope) to end the `str()`/`int()` round-trip at `home_screen.py:467,477`
    ↔ `main.py:663,701,718`.
14. **Credential hygiene** (N16): strip userinfo from the proxy URL before
    persisting, or move it to the platform keyring; add a Settings-UI warning
    that the proxy URL is stored on disk.
15. **Delete the dead members** (N19): `_last_write`, `get_all()`, or give
    `get_all()` a real consumer.

---

## 6) Verdict

**Not clean.** The file has good bones — singleton-per-directory, atomic
`mkstemp`+`os.replace`, debounce on a loop-agnostic `threading.Timer` instead
of a loop-bound `call_later`, type-guarded JSON parsing, a working Windows
backoff — but the **Flet layer is entirely wrong**: `page.client_storage` does
not exist in flet 1.0.4, and `page.session_id` does not exist either, so the
whole web branch (:121-127, :134-151, :233-241) is dead code that *silently
reports success*. The correct API (`ft.SharedPreferences`, async, mounted via
`page.services`) is unused anywhere in the app.

Desktop behaviour is **mostly correct but not lossless**: `storage.json` is
written atomically, reloaded correctly on a fresh process, and corrupt JSON is
backed up. But three concrete defects bite on every run:

* a write that lands during a debounce write is **orphaned** (N1);
* the **last second** of changes is lost on exit because `close()` is never
  called (N3);
* a flush and the debounce timer can **regress the file** to an older snapshot
  (N4).

Plus a class of silent-corruption bugs: invalid UTF-8 is reset with no backup
(N6), wrong-shaped JSON is discarded without a trace (N8), and the "disk is
authoritative" guarantee is false because the singleton never re-reads (N7).

Six settings are written and never restored (K5) — the user's choices vanish on
restart — and the module's own history codec is bypassed by its main consumer
(N9).

**Priority:** (1) swap `client_storage` → `SharedPreferences`; (2) fix N1/N3/N4
(lost writes); (3) make corrupt-recovery uniform (N6/N8); (4) wire the six
never-restored keys; (5) split the ~1MB results blob out of the settings file.

*Audit tool-call budget respected; no file in the repository was modified.*
