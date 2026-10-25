# Audit — `src/services/cache_service.py` (732 lines)

Audited 2026-10-20. Ground truth: installed deps only — `flet 1.0.4`, `httpx 0.28.1`,
`user-scanner 1.5.2.3`, `phonsint 0.1.0`, `reportlab`, Python 3.14.7
(`.venv/Lib/site-packages`). Read-only audit; no file was modified.

---

## 1) File role

`src/services/cache_service.py` is a **pure-filesystem** cache service for Flet's `cache/`
storage tier. It contains **zero Flet API calls** — no `page.client_storage`, no
`page.shared_preferences`, no `StoragePaths`. Every path is resolved through
`src/services/cache_service.py:50-53` → `services.storage_service.get_cache_dir()`
→ env var `FLET_APP_STORAGE_CACHE` or `<project_root>/.flet/storage/cache`.

The file declares six layers (docstring `src/services/cache_service.py:1-24`):

| # | Layer | Lines | Actually called from prod code? |
|---|-------|-------|----------------------------------|
| 1 | `compiled_db.pkl` + `.meta.json` | 123-231 | **NO** — zero callers |
| 2 | `avatars/<sha256>.png` | 234-306 | **YES** (`result_card.py:515`, `profile_detail_dialog.py:557`, `report_service.py:794`, `main.py:1241`, `main.py:1624`) |
| 3 | `reports/<mode>_<query>_<fp>.<ext>` | 309-421 | **YES** (`app_shell.py:292/312/374/401`) — but always misses (§4 B4) |
| 4 | `geo_cache.json` | 424-463 | wired (`geo_utils.py:62/92`) but **inert** — `pycountry` is not installed (§4 B6) |
| 5 | `sites_indices.json` | 466-527 | **NO** — zero callers |
| 6 | `dns_cache.json` | 530-694 | **NO** — zero callers |

Public API actually exercised by the app: `ensure_cached_avatar`,
`schedule_avatar_download`, `load_cached_report`, `save_cached_report`,
`load_geo_cache`, `save_geo_cache`. Everything else is dead code
(verified by repo-wide grep excluding `.venv`).

Positives worth keeping: atomic `tmp + os.replace` writes
(`src/services/cache_service.py:68-97`), stream-hashed files (`:56-65`),
type-guard-heavy JSON parsing (`:437-453`, `:504-527`, `:540-576`), and
correct `isinstance`-first ordering that avoids the classic
`'list' object has no attribute 'get'` crash.

---

## 2) Storage / httpx API verification against installed flet 1.0.4

### 2.1 What flet 1.0.4 actually provides

Verified by grep over `.venv/Lib/site-packages/flet/`:

| API | Present? | Evidence |
|-----|----------|----------|
| `flet.StoragePaths` | **YES** | `flet/controls/services/storage_paths.py:12`; `get_application_cache_directory()` at `:20` |
| `FLET_APP_STORAGE_CACHE` / `_DATA` / `_TEMP` env vars | **YES** | documented in `flet/controls/services/storage_paths.py:27, 72, 188` → `storage_service.get_cache_dir()` is legitimate |
| `flet.SharedPreferences` | **YES** | `flet/controls/services/shared_preferences.py:13`; value types `str/int/float/bool/list[str]` (`:8`, validated `:39-46`) |
| `page.shared_preferences` / `page.storage_paths` property | **NOT FOUND** | grep for `def storage_paths|def client_storage|def shared_preferences` in the package → 0 hits |
| **`page.client_storage`** | **DOES NOT EXIST** | grep `client_storage` over the **entire** flet package (all file types) → **0 hits** |
| `LengthLimits` / key-or-value length caps | **ABSENT** | grep `LengthLimit` → 0 hits; the only `max_length` in flet 1.0.4 is `TextField.max_length` (`flet/controls/material/textfield.py:388`). The only documented storage key constraint is Android's three forbidden base64 key prefixes (`flet/controls/services/shared_preferences.py:24-26`) |
| `page.get_asset_url` | **NOT FOUND** | grep `get_asset_url` → 0 hits in flet 1.0.4 |

**Consequences for this file (and its dependency `storage_service.py`):**

* `src/services/storage_service.py:137` and `:236` use `page.client_storage` behind
  `hasattr` guards. That API does not exist in flet 1.0.4, so in web mode the
  `StorageService` web path is **silently dead** (`_load_web` → exception → `{}`;
  `_save_now_web` → exception → swallowed). The `hasattr` guard turns a hard API
  error into silent data loss.
* Because `cache_service` reaches the cache dir through that same module
  (`src/services/cache_service.py:51`), a **web deployment** writes its "cache" to
  `<project_root>/.flet/storage/cache` — a *server-local, shared, never-OS-purged*
  directory. That contradicts this file's own docstring
  (`src/services/cache_service.py:4-9`: "regenerable, OS-purgeable on device") and
  means two web users share one `avatars/` + `reports/` namespace (the report PDFs
  contain the searched username and the found profile URLs).
* `src/services/cache_service.py` itself performs **no encoding** of its own and
  touches no key/value store, so the "client_storage is str-only / base64" concern
  does not apply to this file.

### 2.2 httpx 0.28.1 verification

* `AsyncClient.stream(...)` + `Response.aiter_bytes(chunk_size)` — API confirmed at
  `httpx/_models.py:982`; `aiter_bytes` yields **decoded** (gzip/brotli/zstd) bytes, so
  the in-loop size check at `src/services/cache_service.py:297` measures the
  *decompressed* size. **The "5 MB cap" claim is TRUE** — the `content-length`
  pre-check at `:290-293` is only a fast path; the authoritative check is `:297`.
  Minor: the check runs *after* `buf += chunk`, so peak memory is 5 MB + one
  64 KB chunk (`_AVATAR_CHUNK`, `:262`).
* Timeout is inherited from the shared client
  (`src/services/http_client.py:54`: connect 5 s / read 15 s / write 10 s / pool 5 s).
  For a *streaming* read the 15 s read timeout applies **per chunk**, so total
  download time is unbounded; only the byte cap bounds it. No wall-clock deadline
  is applied to the whole avatar fetch.
* `follow_redirects=True` (`src/services/http_client.py:68, 76`) → the avatar fetch
  follows up to httpx's default 20 redirects, and **no re-validation happens after a
  redirect** (§4 B1).

### 2.3 `ft.Image.src` and local filesystem paths

`flet/controls/core/image.py:36-44` documents `src` as *"A URL or local **asset file**
path"* (also base64 str or raw bytes). Flet resolves the assets directory via
`DEFAULT_ASSETS_DIR = "assets"` (`flet/app.py:33-36`, `__get_assets_dir_path` at
`flet/app.py:677-725`) — i.e. `<app>/assets`, **not** the cache directory. There is no
`page.get_asset_url` in 1.0.4.

`src/services/cache_service.py:253` and `:274` hand back an **absolute OS path** under
`.flet/storage/cache/avatars/`, which is outside the assets dir. The actual loader is
the Dart client, so this **cannot be verified from the installed Python package** — but
the documented contract does not cover it. See §4 B3.

---

## 3) Confirmed known issues (refuted / confirmed)

| Claim | Verdict |
|-------|---------|
| `:418` drops `sig` → the signature check at `app_shell.py:266-280` can never hit | **CONFIRMED.** `save_cached_report` calls `cached_report_path(mode, query, found, ext)` (`src/services/cache_service.py:418`) without `sig`, while `load_cached_report` calls it **with** `sig` (`:403`). `results_fingerprint` mixes `sig` into the hash (`:382-384`), so the two paths always differ. Affects **pdf, md and html** (`app_shell.py:292/312` and `:374/401`). The report cache is a **100 % miss**, and every export writes a new orphan file into `reports/`. See §4 B4. |
| `:211` uses pickle + sha256 sidecar | **CONFIRMED** (`:211` `pickle.dumps`, `:221` `pkl_sha256`, `:177-183` verification) — but the sidecar lives in the same directory (`:126-128`), so it is a *truncation/corruption* check, not a tamper check. See §4 B9. The whole layer has no caller (§4 B18). |
| Avatars stream via the shared httpx client (`src/services/http_client.py`) | **CONFIRMED** at `src/services/cache_service.py:278-282`. `get_client()` is used by exactly two callers: this file and `update_service.py:74` — both on the main Flet loop, so the cross-event-loop hazard of a module-global `AsyncClient` is currently latent, not live. |
| `sherlock_cached_results` ~790 KB, capped at 30 elsewhere, size unbounded | **REFUTED for this file.** The key is a **durable storage-tier** key (`src/core/constants.py:56`), written by `src/main.py:2203` and read at `src/main.py:835`; the 30-entry LRU is `src/core/state.py:173-179`. `cache_service.py` never reads or writes it and provides no size bound for it. The unbounded part is the *per-entry snapshot payload*, not this file's concern. |
| Web / `client_storage` is str-only (storage_service forces base64) | **NOT APPLICABLE to this file** — it does no client_storage work and no encoding. The real web-mode defect for this file is the shared server-side cache dir (§2.1). |
| flet `client_storage` limits / `LengthLimits` | **No such API in flet 1.0.4.** `client_storage` does not exist at all; `SharedPreferences` exists with typed values and Android key-prefix restrictions, but **no documented key/value length limit anywhere in the installed package**. |

---

## 4) NEW bugs (severity-ordered)

### B1 — HIGH — SSRF / local-network fetch of untrusted avatar URLs
`src/services/cache_service.py:265-306`

The only gate on the target URL is `url.startswith("http")` (`:272`). The URL comes
from third-party profile pages (`data.get("image")/("avatar")/("photo")` at
`src/main.py:1231-1235` and `("others")["media"]["avatar"]` at `src/main.py:1629`).
A hostile or compromised target site can therefore make the app fetch
`http://169.254.169.254/latest/meta-data/`, `http://127.0.0.1:8080/`,
`http://10.0.0.1/` or `http://[::1]/` — from the **user's desktop machine** or from
the **shared server** in web mode — and the response body is written to disk
(`:304`).

Redirects make it worse: `follow_redirects=True`
(`src/services/http_client.py:68, 76`) means a public URL can 302 into the LAN, and
nothing re-validates after the redirect.

The engine already ships the guard and the app simply does not use it — verified
importable and functional in the installed package:
`user_scanner/core/pdf_generator.py:88` `is_safe_media_url` (returns `False` for
`http://127.0.0.1/x`, `True` for `http://example.com/x` — executed and confirmed) and
`is_safe_ip` at `user_scanner/core/pdf_generator.py:69`.
Repo-wide grep for `is_safe_media_url|is_safe_ip|ssrf` in `src/` → **0 hits**.

*Fix:* call `is_safe_media_url(url)` before the request, re-check the final
`resp.url` after redirects, and restrict the scheme to `https`.

### B2 — HIGH — a cached avatar can be a non-image, permanently poisoning the UI
`src/services/cache_service.py:280-304`, `:250-258`

The response body is written verbatim to `<sha256>.png` with **no `content-type`
check and no magic-byte check**. A `text/html` error page, a `text/plain` body or an
SVG lands in a `.png`. Then:

* `ensure_cached_avatar` (`:250-258`) sees a non-empty file and returns the local
  path **forever** — there is no validation, no TTL and no re-download. `ft.Image`
  fails to decode it and shows `error_content` (the icon fallback) permanently.
* The extension lies about the format: a JPEG/AVIF/WebP/SVG body is stored as `.png`.
* `src/services/report_service.py:794-800` feeds the same file to ReportLab
  `RLImage` → `UnsupportedImageError`; it is caught at
  `src/services/report_service.py:821`, so the PDF survives but the 30×30 thumbnail
  is silently lost on every dossier.

### B3 — HIGH/MED — the avatar cache may never render at all
`src/services/cache_service.py:253`, `:274`

Both functions return an **absolute OS path** under
`<cache>/avatars/`. flet 1.0.4 documents `Image.src` as a URL or a *local asset file
path*, and the assets dir is `<app>/assets` (`flet/app.py:33-36`, `:677-725`); there
is no `get_asset_url` in 1.0.4. The renderer is the Dart client, so this is not
verifiable from the installed Python package — but the whole point of Layer 2
depends on an undocumented behaviour. The ReportLab consumer
(`src/services/report_service.py:794-800`) *does* work, because ReportLab reads the
file directly — so the PDF shows avatars while the on-screen `ft.Image` may not.

*Mitigation:* `Image.src` accepts raw `bytes` (`flet/controls/core/image.py:36`), so
read the file and pass bytes, or write avatars under the assets dir.

### B4 — MED/HIGH — report cache never hits and leaks files
`src/services/cache_service.py:411-421` (vs `:398-408`)

Confirmed in §3. Two concrete consequences: (a) every export re-renders the full
ReportLab dossier — the app's most expensive operation is never cached; (b) every
export writes a *new* file into `reports/` whose name is never read again
(`reports/` grows without bound — see B10).

### B5 — MED — the geo cache freezes permanently at 4096 entries
`src/services/cache_service.py:456-463` and `:453`

`trimmed = dict(list(lookup.items())[:_GEO_MAX_ENTRIES])` keeps the **oldest** 4096
entries in insertion order. `src/core/geo_utils.py:78-82` appends new keys at the
**end** of the same dict, so once the cap is reached every newly resolved location is
dropped on save and the on-disk cache stops learning forever. The trim comment at
`:451` ("a usable prefix survives oversize writes") describes the intent but not the
effect. Same first-N truncation on load (`:453`).

*Fix:* keep the most recent (`items[-4096:]`) or evict oldest-by-insertion.

### B6 — MED — the geo version guard can never fire
`src/services/cache_service.py:430-434`, `:446`

`getattr(pycountry, "__version__", "unknown")` — but **pycountry is not installed**
(verified: `No module named 'pycountry'`; and it is not in
`pyproject.toml:7-12` dependencies). So the version is permanently `"unknown"`, the
check `data.get(_GEO_MIN_TS_KEY) != version` (`:446`) compares `"unknown"` to
`"unknown"` and always passes, and the documented invalidation ("pycountry data
changes between versions can silently change fuzzy matches", `:442-444`) never
happens. (Independently, pycountry historically exposes no `__version__` attribute —
`importlib.metadata.version("pycountry")` is the correct source.)

Net effect: Layer 4 is inert, because `src/core/geo_utils.py:14-21` gates on
`_PYCOUNTRY_AVAILABLE`.

### B7 — MED — `_engine_version()` fallback returns a constant `"unknown"`
`src/services/cache_service.py:330-342`

The fallback reads `version.json` next to the engine package and looks up the key
`"current_version"` (`:339`). The installed `user_scanner/version.json` contains
`{"version": "1.5.2.3", "version_type": "pypi"}` — there is **no `current_version`
key**, so the fallback would always yield `"user-scanner:unknown"`. The primary path
works today (`importlib.metadata.version("user-scanner")` → `1.5.2.3`, verified), so
this is latent: if the distribution name ever changes, pickle invalidation silently
degrades to a constant that never changes. Secondary defect: the loop at `:324-329`
returns the **first** success, so if `user-scanner` were absent but `phonsint` present,
the "engine version" would become phonsint's version.

### B8 — MED — the documented integrity guarantee is a no-op in the fast path
`src/services/cache_service.py:159-167`

When `mtime` **and** `size` match, `hash_matches = True` and the stored source hash
is never compared. The docstring (`:134-138`) promises the hash pass "still
detect[s] replaced-but-equal-mtime manifests" — it does not. A manifest replaced with
identical size and a restored mtime (`tar`, `rsync -t`, `touch -r`) silently reuses
the stale catalog. The stored `hash` (`:219`) is otherwise unused.

### B9 — MED — the sha256 "tamper" check protects nothing; `pickle.loads` is RCE
`src/services/cache_service.py:174-187`

The pickle's sha256 and size live in a **sibling file in the same directory**
(`:126-128`, `:215-228`). Anyone able to replace the `.pkl` can replace the `.meta`.
The comment at `:185-186` ("a tampered artifact fails the hash check before reaching
this line") is therefore **wrong**; the check only catches truncation/bit-rot. Since
`pickle.loads` (`:187`) executes arbitrary opcodes, a writable cache dir equals code
execution — which matters because in web mode that dir is a shared server directory
(§2.1). If this layer is ever wired up, use a non-executable format (JSON/msgpack)
or move the key/HMAC out of the same directory.

### B10 — MED — no eviction anywhere; every file-backed layer grows without bound
`src/services/cache_service.py:240`, `:395`, `:461`, `:501`

* `avatars/` — one file per distinct URL, never evicted, no TTL, no size budget.
* `reports/` — one file per (mode, query, fingerprint); because of B4 every export
  adds another orphan.
* `geo_cache.json` / `sites_indices.json` / `dns_cache.json` — bounded by entry
  count only, never by bytes.
* `clear_all_caches` (`:697-732`) exists to wipe them but is **never called** from
  `src/` or `tests/`.

The module docstring (`:8-9`) promises "cheap to rebuild after an OS purge" but
nothing enforces a budget; on desktop the OS may never purge it.

### B11 — MED — avatar cache never refreshes and never negative-caches
`src/services/cache_service.py:274-276`

Only *existence* is checked. A changed profile picture at the same URL is never
re-fetched (the cache is frozen forever), and a 404/500 avatar is re-requested on
every scan — up to 50 spawns per scan (`src/main.py:1230`, `src/main.py:1632`).
Failures are logged at INFO (`:286-288`) and never recorded, so the failure path is
re-executed indefinitely.

### B12 — MED — Windows write failures are not retried
`src/services/cache_service.py:88`

`os.replace(tmp_s, path)` has no `PermissionError` backoff. The sibling module
explicitly added one for exactly this failure mode — a 6-attempt exponential backoff
at `src/services/storage_service.py:204-213` ("Windows NTFS backoff retry on transient
filter/antivirus locks (WinError 5)"). `cache_service` writes with the same
`os.replace` pattern but without the retry, so on Windows an AV/filter lock turns
into a silently failed avatar/report/geo write (only a WARNING from `:95-97`).

### B13 — LOW/MED — `ext` is not sanitized in the report cache path
`src/services/cache_service.py:387-395`

`mode` and `query` go through `_safe_name_component` (`:312-315`), but `ext` is
interpolated raw into the filename. Today only `"pdf"`, `"md"`, `"html"` are passed
(`src/app_shell.py:292`, `:374`), so there is no live traversal — but the asymmetry
is a latent path-traversal if a caller ever passes a user-controlled extension.
(Also: `_safe_name_component` truncates to 48 chars, so `a.b@x.com` and
`a_b@x.com` collapse to the same prefix; the fingerprint disambiguates the file, so
there is no collision in practice.)

### B14 — LOW/MED — weak scheme test, and `ensure_cached_avatar` can return non-`str`
`src/services/cache_service.py:250`, `:251`, `:272`

`url.startswith("http")` also accepts `httpx://…` and any `http<anything>` scheme.
In `ensure_cached_avatar` the order is `not url` → `not isinstance(url, str)` →
`url.startswith(...)`, so a non-empty **bytes** value falls through the
`isinstance` branch and is returned as-is — violating the `-> str` annotation and
handing raw bytes to `ft.Image(src=...)` (which flet would interpret as image bytes).

### B15 — LOW — `_backup_corrupt` is dead code; corruption is never surfaced
`src/services/cache_service.py:100-108` (definition only — grep finds exactly one
hit, the `def`)

`_read_json` (`:116-120`) swallows every exception and returns `None`, so a corrupt
`geo_cache.json` / `sites_indices.json` / `dns_cache.json` is silently treated as
"no cache" and then silently overwritten on the next save. The forensics helper the
author wrote for exactly this case is never wired in. The sibling module does it
correctly (`src/services/storage_service.py:23-31` called at `:175`).

### B16 — LOW — the DNS layer is dead code and would race if it were wired
`src/services/cache_service.py:530-694`

`prewarm_dns`, `flush_dns_cache`, `is_domain_dead`, `get_dns_record` have **no
callers** outside this file. If wired: `_dns_store` (`:532`) is a process-global
mutated by the scan worker thread while `flush_dns_cache` (`:606`) does
`json.dumps(_dns_store)` on the event loop → `RuntimeError: dictionary changed size
during iteration`. `flush_dns_cache` has **no try/except** (`:601-610`), unlike every
other writer in this file, so that race would propagate to the caller.

### B17 — LOW — the sites-indices layer is dead code and mishandles dict-shaped sites
`src/services/cache_service.py:466-527`

`build_sites_indices` / `save_sites_indices` / `load_sites_indices` have no callers.
`build_sites_indices` reads `getattr(site, "tags", None)` (`:483`) — for a
**dict-shaped** site entry (a custom manifest) this yields `None` → zero tags,
while the very next lines special-case a *string* `tags` value (`:484-485`). The
dict case is the obvious gap. `load_sites_indices` also returns the whole file
(`:527`) with no size bound.

### B18 — LOW — the compiled-DB layer is dead code
`src/services/cache_service.py:123-231`

`try_load_compiled_db` / `save_compiled_db` have exactly one occurrence each in the
whole repo (their own `def` lines) — no caller. The stated goal ("skip module import
+ category scan on startup", `:11-13`) is not wired.

### B19 — LOW — `prewarm_dns` would overload the shared default executor
`src/services/cache_service.py:670-692`

`loop.getaddrinfo` runs on the event loop's **default** `ThreadPoolExecutor`
(`min(32, cpu+4)` threads). With `max_hosts=300` (`:627`) that is 300 blocking
`getaddrinfo` calls saturating the same executor the app uses for
`asyncio.to_thread(...)` elsewhere (`src/main.py:1119`, `src/main.py:1575`,
`src/app_shell.py:441`, `src/services/user_scanner_compat.py:203`).

### B20 — LOW — `_cache_root()` re-resolves the project root on every call
`src/services/cache_service.py:50-53`

`get_cache_dir()` → `Path(__file__).resolve()` (a filesystem syscall) on *every*
call, and `ensure_cached_avatar` is invoked per result card on the render path
(`src/components/result_card.py:515`). Cheap individually, but it is pure overhead
on the hot render path.

### B21 — LOW — DNS write/read semantics disagree
`src/services/cache_service.py:564` vs `:591-597`

`set_dns_record(domain, [], dead=False)` writes `dead=False` with empty `ips`, but
the reader computes `is_dead = bool(rec.get("dead", False)) or not ips` (`:564`) and
reinterprets it as dead. Latent (dead layer), but the two sides disagree.

### B22 — INFO — `clear_all_caches` overstates the removal count
`src/services/cache_service.py:697-732`

`shutil.rmtree` on a symlink-to-directory raises `OSError` (swallowed at `:718`)
without incrementing `removed`, so the returned count can overstate. `removed` is
also incremented for children whose `unlink` silently failed. Minor, and the function
is never called.

### B23 — INFO — no cross-process lock on the cache writers
`src/services/cache_service.py:68-97`

The atomic-write discipline correctly prevents interleaving *within* a process
(unique `mkstemp` name, same-directory `os.replace`). Across processes (two `flet
run` sessions, or a dev run and a packaged app sharing `FLET_APP_STORAGE_CACHE`),
the `.pkl` and its `.meta` can come from different writers → sha mismatch → a
permanent 100 % cache miss (safe, but silent).

### B24 — INFO — write results are inconsistently handled
`src/services/cache_service.py:456-463` (`save_geo_cache`), `:500-501`
(`save_sites_indices`) ignore the boolean returned by `_write_json_atomic`; only
`flush_dns_cache` (`:606-610`) checks it. `save_cached_report` downgrades the
failure to `logger.debug` (`:420-421`) even though `_write_atomic` already logs a
WARNING (`:96`). A failed geo/indices write is therefore invisible at WARNING level.

### B25 — INFO — no size cap when reading JSON caches
`src/services/cache_service.py:116-120`

`geo_cache.json`, `sites_indices.json` and `dns_cache.json` are read fully into
memory with no bound; a runaway or hostile file is a memory spike.

### B26 — INFO — no parent-directory fsync
`src/services/cache_service.py:86-88`

The file contents are fsynced (`:87`) but the containing directory is not, so on
POSIX a power loss can lose the rename. Consistent with
`src/services/storage_service.py:203`, so not a regression.

---

## 5) Improvements (ordered)

1. **Fix the `sig` drop** — `src/services/cache_service.py:418` must forward `sig`
   to `cached_report_path`. One line; it restores the app's most expensive
   optimisation and stops the `reports/` leak. Add a regression test asserting
   `save_cached_report(..., sig="a")` then `load_cached_report(..., sig="a")` hits.
2. **Add the SSRF guard to the avatar fetch** — reuse
   `user_scanner.core.pdf_generator.is_safe_media_url` (already installed and
   importable) before the request, re-validate `resp.url` after redirects, and
   restrict the scheme to `https`.
3. **Validate avatar content** — check `content-type` starts with `image/`, verify
   magic bytes, and store the real extension (or a `.bin` + sniffed type) instead of
   always `.png`. Reject non-images before `_write_atomic` (`:304`).
4. **Serve avatars in a way flet 1.0.4 actually supports** — pass `src=bytes`
   (`flet/controls/core/image.py:36`) instead of an absolute path, or publish the
   avatar dir as the app's assets dir.
5. **Add eviction and byte budgets** — an LRU over `avatars/` and `reports/` with a
   total size cap (e.g. 100 MB) and a TTL for avatars; call `clear_all_caches`
   opportunistically at startup when the cache exceeds its budget. This also fixes
   B10 and the "avatar never refreshes" half of B11 (add an mtime-based TTL).
6. **Fix the geo cache** — keep the most recent 4096 entries
   (`items[-_GEO_MAX_ENTRIES:]`), source the version from
   `importlib.metadata.version("pycountry")`, and either add `pycountry` to
   `pyproject.toml:7-12` or delete Layer 4 outright.
7. **Fix `_engine_version`** — read the `version` key (not `current_version`), try
   `user-scanner` before `phonsint`, and never silently return a constant.
8. **Delete or wire the dead layers** — `compiled_db` (123-231), `sites_indices`
   (466-527) and `dns_cache` (530-694) are ~260 lines with zero callers. Either
   wire them or delete them; if the DNS layer is wired, add a lock around
   `_dns_store` and a `try/except` in `flush_dns_cache`.
9. **Move blocking I/O off the UI loop** — the report save
   (`src/app_shell.py:312` → `src/services/cache_service.py:419`) writes a whole
   PDF synchronously on the Flet event loop; wrap it in `asyncio.to_thread`. Same
   for `flush_dns_cache` and `save_geo_cache` (`:460-463`).
10. **Add the Windows replace backoff** — copy the retry loop from
    `src/services/storage_service.py:204-213` into `_write_atomic` (`:88`).
11. **Wire `_backup_corrupt` into `_read_json`** so corrupt caches are preserved and
    logged instead of being silently overwritten (`:100-108`, `:116-120`).
12. **Sanitise `ext`** in `cached_report_path` (`:392-395`) and add a dict branch for
    `site["tags"]` in `build_sites_indices` (`:483-488`).
13. **Cache the resolved cache root** in a module-level variable (`:50-53`) to remove
    the per-card `Path.resolve()` syscall.
14. **Bound JSON reads** (`:118`) with a size check before `json.loads`.

---

## 6) Verdict

Structurally this is a careful file — atomic writes with fsync, streaming hashes,
defensive type checks on every JSON path, TTLs, and a comment block that explains
intent. But measured against the installed dependencies, its headline features are
either broken or dead:

* **The report cache can never hit** (`:418` drops `sig`) — the app's most expensive
  operation is re-rendered on every export, and every export leaks a file into
  `reports/`. (Known issue **confirmed**.)
* **The avatar cache is unsafe and possibly invisible** — no SSRF guard on a
  user-influenced URL (`:265-306`), no content-type/magic-byte validation (`:304`),
  and a local absolute path that flet 1.0.4 does not document as a valid
  `Image.src` (`:253`).
* **3 of 6 layers have zero callers** (`compiled_db`, `sites_indices`, `dns_cache`),
  and a 4th (`geo_cache`) is inert because `pycountry` is not installed and the
  version guard is a no-op. Roughly 260 of 732 lines are dead.
* **The `sherlock_cached_results` 790 KB problem is not in this file** — it is the
  durable storage tier (`src/core/constants.py:56`, `src/core/state.py:173-179`).
* The `page.client_storage` API used by `src/services/storage_service.py:137/236`
  **does not exist in flet 1.0.4** (0 hits in the entire package), and flet 1.0.4
  ships **no** `LengthLimits` and **no** documented key/value size cap for
  `SharedPreferences` — only Android's three forbidden key prefixes.

Top three fixes, in order: (1) forward `sig` at `:418`; (2) add
`is_safe_media_url` + content-type validation to `schedule_avatar_download`;
(3) delete or wire the three dead layers so the file stops advertising capabilities
the app does not use.
