# Dependency Audit: `msgpack` (1.2.3) — Sherlock-V3

Audit date: 2026-10-20 · Scope: installed `.venv/Lib/site-packages/msgpack` (only source of truth)
Question: could/should Sherlock-V3 use msgpack directly for cache/state persistence?
Method: source reads + runtime introspection in the project venv (Python 3.14.7) + benchmark on the
app's real persisted payload. **No application file was modified.**

## 1. Installed verification

| Item | Evidence | Value |
|---|---|---|
| Version | `msgpack/__init__.py:7-8` | `version = (1, 2, 3)`, `__version__ = "1.2.3"` |
| C extension | `.venv/.../msgpack/_cmsgpack.cp314-win_amd64.pyd` | present, 137,216 B, cp314/win_amd64 ABI |
| Pure-Python fallback | `msgpack/fallback.py` (34,269 B): `unpackb` `:83`, `Unpacker` `:141`, `Packer` `:624` | present |
| Shared ext types | `msgpack/ext.py:8` `ExtType`, `:21` `Timestamp` | used by **both** backends |
| Import switch | `msgpack/__init__.py:11-17` | `MSGPACK_PUREPYTHON` set → `.fallback`; else `try: ._cmsgpack` / `except ImportError: .fallback` |
| `packb` | `msgpack/__init__.py:30-36` | defined in `__init__` **only** (wraps `Packer().pack()`) → exists on both backends |
| `unpackb` | `__init__.py:15`/`:17` (C/fallback) + `fallback.py:83` | both backends |
| Aliases | `msgpack/__init__.py:52,55` | `loads = unpackb`, `dumps = packb` |

**Loaded backend — verified at runtime, not inferred:** `msgpack.Packer/Unpacker/unpackb.__module__`
all → `msgpack._cmsgpack`; `loads is unpackb` and `dumps is packb` → `True`. With
`MSGPACK_PUREPYTHON=1` the same interpreter reports `msgpack.fallback` for all three and
round-trips correctly — the fallback is live, not dead code. `packb`/`unpackb` are available today.

## 2. Who uses it in this venv

Transitive via flet — flet's Python↔Flutter wire protocol. Dependency chain: `uv.lock:133` (flet deps
include `{ name = "msgpack" }`), `uv.lock:267-270` (msgpack block); `flet-1.0.4.dist-info/METADATA:17`
→ `Requires-Dist: msgpack>=1.1.0` — **no platform marker**, so required on every platform incl. Android.

- Control encoder: `flet/messaging/protocol.py:6` import; `:206/:208/:210` `msgpack.ExtType(1/2/3)`
  for datetime/time/Duration; `:218-228` `decode_ext_from_msgpack` ext hook.
- Desktop/TCP: `flet/messaging/flet_socket_server.py:13` import; `:287` `unpackb(..., ext_hook=...)`; `:438` `packb(...)`.
- Dart VM bridge: `flet/messaging/flet_dart_bridge_server.py:33` import; `:129-130` `unpackb(...)`; `:229` `packb(...)`.
- WASM/pyodide: `flet/messaging/pyodide_connection.py:9` import; `:92` `unpackb(...)`; `:206` `packb(...)`.

**App never imports msgpack — confirmed.** `grep -rn "msgpack" src/ tests/` returns one hit and it
is a *changelog string*, not an import: `src/core/changelog.py:25` `"• Fix: msgpack-safe site
selection (list instead of set)"` — a V2.1.0 note about flet's transport, not app persistence.

## 3. Honest opportunity assessment

**The owner rule is satisfied:** msgpack is already installed *and already ships in the Android APK*
(flet requires it unconditionally), so using it adds **zero** dependencies and **zero** APK bytes.
That is genuinely green — but it is not the deciding factor.

**Measured on the app's real `storage.json`** (829,497 B on disk; `sherlock_cached_results` =
691,214 B of JSON text ≈ 790 KB escaped inside the `indent=2` file; other keys are noise —
`sherlock_cached_sites` 37,980 B, `sherlock_history` 802 B):
`json indent=2` 980,304 B / dump 29.27 ms / load 21.13 ms · `json compact` 632,470 B ·
**`msgpack` 493,432 B / pack 8.64 ms / unpack 18.25 ms** → 1.99× smaller, 3.4× faster pack.

**Why the 1.99× does not become a real win:**

1. **The storage API is `str`-only, so bytes must be base64'd.** `src/services/storage_service.py:288-297`
   raises `TypeError` for any non-`str` value. Base64 of 493,432 B = **657,910 B** — only **~5 %**
   better than the 691,214 B it replaces. The headline 2× evaporates.
2. **The web tier forces JSON anyway.** `src/services/storage_service.py:237` writes
   `cs.set("sherlock_storage", json.dumps(self._data))` into `page.client_storage` (strings only),
   so a second JSON code path must stay alive regardless.
3. **CPU saving is invisible on mobile:** ~20 ms on a 1.0 s-debounced write (`storage_service.py:17`),
   ~3 ms on startup read.
4. **Format divergence costs more than it saves.** The store is deliberately human-inspectable JSON
   with atomic tmp+`os.replace` writes (`storage_service.py:183-223`), a corrupt-file backup path
   (`:23-31`), and a WinError-5 retry loop (`:204-213`). A second format = a second corruption path,
   a second migration story, non-debuggable files — for ~130 KB and ~20 ms.
5. **Other cache tiers are not candidates.** `src/services/cache_service.py:211` `compiled_db.pkl` uses
   `pickle` (arbitrary Python objects — msgpack cannot replace it) with a sha256 integrity sidecar
   (`:221-226`); `geo_cache.json` / `sites_indices.json` / `dns_cache.json` (`cache_service.py:111-113`,
   `:437-501`, `:536-611`) are small dicts where human-readability for debugging is worth more than KB.
   History is capped at 50 entries (`src/services/storage_service.py:361-367`) and totals **802 B**.
6. **The real problem is volume, not format.** An unbounded `state.results_cache` is a *policy* problem
   (no eviction/TTL); re-encoding it more compactly still leaves it unbounded.

**Opportunity verdict: NO — do not adopt msgpack for persistence.** The only place it could pay (one
790 KB value) yields ~5 % after the mandatory base64, for a second format, a second corruption path
and lost debuggability. The right fix is **bounding/evicting** it, not re-encoding it.

## 4. Mobile packaging note (Android arm64-v8a / x86_64)

- **No Android wheel exists for msgpack 1.2.3.** The msgpack block in `uv.lock:267+` has **0** `android`
  matches; the only Android wheel in the entire lock is
  `curl_cffi-0.16.3-cp314-cp314-android_24_arm64_v8a.whl` (`uv.lock:116`). PyPI's file list for 1.2.3
  (90 wheels) likewise has **no** `android_*` tag → Android builds from sdist.
- **Runtime fallback is automatic.** `msgpack/__init__.py:16-17` catches `ImportError` → `.fallback`
  (verified functional). A missing/failed `.so` degrades to *slower*, never *broken*.
- **Build-time is the real risk.** msgpack's `setup.py` adds the extension only
  `if not PYPY and not os.environ.get("MSGPACK_PUREPYTHON")`, and `setup()` is **unguarded** — a failed
  C compile **aborts the install**; there is no automatic build-time fallback. An Android build must
  compile via NDK or set `MSGPACK_PUREPYTHON`.
- **This risk is inherited, not added.** flet hard-requires msgpack on every platform, so flet's Android
  packaging already solves it. Any decision here leaves that risk profile unchanged.

## 5. Verdict

**Do not use msgpack in Sherlock-V3. Leave it as a pure flet transitive dependency.**

- Verified working: v1.2.3, `_cmsgpack.cp314-win_amd64.pyd` loaded, pure-Python fallback present and
  live, `packb`/`unpackb`/`loads`/`dumps` all available. App does not import it and should not (only hit
  is the changelog string `src/core/changelog.py:25`).
- The "no extra dependencies" rule is *not* the blocker — msgpack is already installed and already
  packaged for Android. The blocker is **no meaningful benefit**: ~5 % after the forced base64, ~20 ms of
  CPU, in exchange for a second serialization format, a second corruption/migration path, non-debuggable files.
- **Alternative worth raising with the owner separately:** the 790 KB `sherlock_cached_results` is
  unbounded, not badly encoded. Two cheap fixes beat any format change — bound/TTL it at
  `src/main.py:2203` (write) / `src/main.py:835-842` (read), and/or drop `indent=2` at
  `src/services/storage_service.py:193`, which alone shrinks the file 980,304 B → 632,470 B (**−35 %**)
  with zero new dependencies, zero format divergence and zero migration risk.
- Android note for the record: no msgpack Android wheel; runtime auto-falls back to pure Python, but the
  *build* has no automatic fallback. This is flet's problem to solve and is unaffected by the decision.
