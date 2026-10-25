# Audit — `src/core/constants.py`

**File:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/core/constants.py` (106 lines)
**Audited against (installed deps = truth):** `flet 1.0.4` (`.venv/Lib/site-packages/flet`), `flet-ads 1.0.4` (`.venv/Lib/site-packages/flet_ads` + `flutter/flet_ads/lib/src/*.dart`), `user_scanner 1.5.2.3`, `phonsint 0.1.0`, `uv.lock`, `pyproject.toml`, `version.json`, GitHub API (`gh`) for the remote repo names. CPython 3.14.
**Scope:** this file only. Call sites in `src/` are cited as evidence for a finding about a constant; defects in those other files are not audited here.
**Method:** repo-wide grep census of every constant (name + value + definition + read + write), cross-check of `main.py:_load_saved_state`, `ruff check` on the file, `ast.parse` on the file, and live checks against the installed `flet`/`flet-ads` sources and the GitHub API.

---

## 1) File role

The app-wide leaf of the configuration pyramid: 66 module-level constants + 1 helper function, in six blocks.

| Block | Lines | Members | Role |
|---|---|---|---|
| UI-automation hook | `:5-13` | `USE_TEST_IDS`, `test_id()` | Env-gated (`SHERLOCK_TEST_IDS=1`) `key=` attributes for black-box test drivers. |
| Identity | `:16-18` | `APP_NAME`, `APP_VERSION`, `APP_BUILD_NUMBER` | Versioning; mirrored in `pyproject.toml:3,19` and `version.json`. |
| Catalog fallback | `:20-22` | `SITES_TOTAL_FALLBACK` | Display denominator used before the module catalog lands (`app_shell.py:303,393`; `report_service.py:197,391,677,705`). |
| Distribution URLs | `:24-29` | `UPDATE_CONFIG_URL`, `PLAY_STORE_URL`, `GITHUB_RELEASES_URL` | Update-check source + Play Store / release deep links. |
| Storage keys | `:31-78` | 47 `STORAGE_*` keys | Every `StorageService` key in the app. |
| Search modes | `:80-83` | `MODE_USERNAME`, `MODE_EMAIL`, `MODE_PHONE` | The mode vocabulary persisted under `STORAGE_SEARCH_MODE`. |
| AdMob units | `:85-86` | `AD_BANNER_UNIT_ID` | The **only** ad unit id in this file (the interstitial units live in `ad_service.py:53-54`). |
| Errors | `:88-92` | `ERR_NETWORK`, `ERR_GENERIC`, `ERR_OPEN_URL`, `ERR_INVALID_EMAIL` | Snackbar strings. |
| Connectivity | `:94-101` | `MSG_OFFLINE`, `MSG_ONLINE`, `MSG_SEARCH_OFFLINE` | Connectivity snackbars. |
| Trailing comment | `:103-105` | — | Section header with no constants under it (see B9). |

The file is **API-clean**: it imports only `os` (`:3`) and touches no third-party API at all. Every value is a literal or an `os.environ.get` comparison. `ruff check src/core/constants.py` → *All checks passed*; `ast.parse` → OK. The defects below are all **semantic/contract** defects, not name errors.

---

## 2) Constant census (used / dead)

**66 constants + 1 function. 1 constant is completely dead; 6 storage keys are persisted but never read back.** All 66 names are unique and all 61 string-valued constants have **distinct values** (verified programmatically) — no collisions, no shadowing.

### 2.1 Dead / write-only constants

| Constant | Line | Usage outside this file | Verdict |
|---|---|---|---|
| `STORAGE_BULK_MODE` | `:75` | **0** | **DEAD.** Repo-wide scan of `src/` + `tests/`: the only hit is its own definition. Its state field `state.bulk_mode` (`state.py:77`) is also never assigned or read anywhere. |
| `STORAGE_SHOW_ALL_RESULTS` | `:66` | import `settings_screen.py:59`, write `settings_screen.py:606` | **WRITE-ONLY.** Never read back → see B3. |
| `STORAGE_VERBOSE_OUTPUT` | `:67` | import `settings_screen.py:63`, write `settings_screen.py:610` | **WRITE-ONLY.** → B3. |
| `STORAGE_EMAIL_DOMAINS` | `:73` | import `settings_screen.py:37`, write `settings_screen.py:634` | **WRITE-ONLY.** → B3. |
| `STORAGE_HUDSON` | `:74` | import `home_screen.py:32`, write `home_screen.py:568` | **WRITE-ONLY.** → B3. |
| `STORAGE_PROXY_FILE` | `:76` | import `settings_screen.py:52`, write `settings_screen.py:641` | **WRITE-ONLY.** → B3. |
| `STORAGE_PHONE_CONCURRENCY` | `:77` | import `settings_screen.py:51` + `home_screen.py:35`, writes `settings_screen.py:1209`, `home_screen.py:477` | **WRITE-ONLY AND INEFFECTIVE** → B3 + B4b. |

### 2.2 Live constants (usage counts = references in `src/` + `tests/`, excluding this file)

| Constant | Line | Uses | Notes |
|---|---|---|---|
| `MODE_EMAIL` | `:82` | 55 | Live. |
| `MODE_PHONE` | `:83` | 41 | Live in code, but **not restorable** → B4. |
| `MODE_USERNAME` | `:81` | 37 | Live. |
| `APP_VERSION` | `:17` | 15 | Matches `pyproject.toml:3` and `version.json` `"version"`. |
| `STORAGE_HISTORY` | `:32` | 10 | The only key with multiple writers (`main.py:2237`, `history_screen.py:402`) and a deleter (`history_screen.py:148`). Read lazily, not in `_load_saved_state`. |
| `SITES_TOTAL_FALLBACK` | `:22` | 9 | Arithmetic in the comment checks out (2521+220+5 = 2746). |
| `STORAGE_USE_CURL_CFFI` | `:64` | 7 | **NOT a dead toggle** — see §2.4. |
| `STORAGE_ALLOW_LOUD` | `:65` | 7 | Live for username/email scans; hardcoded `False` for phone → §2.4. |
| `STORAGE_EMAIL_TIMEOUT` | `:43` | 8 | Live + migrated (`main.py:697-712`). |
| `APP_NAME` | `:16` | 8 | Live. |
| `APP_BUILD_NUMBER` | `:18` | 6 | Matches `pyproject.toml:19` / `version.json` `build_number`; used as the update baseline (`update_service.py:86`). |
| `PLAY_STORE_URL` | `:28` | 6 | `ng.kiri.sherlock` matches `pyproject.toml:35` `bundle_id`. ✅ |
| `STORAGE_CACHED_RESULTS` | `:56` | 4 | Live but heavy → B5. |
| `AD_BANNER_UNIT_ID` | `:86` | 4 | Live; single-platform → B6. |
| `UPDATE_CONFIG_URL` | `:25-27` | 3 | **404 → B1.** |
| `GITHUB_RELEASES_URL` | `:29` | 5 | **404 → B2.** |
| `USE_TEST_IDS` + `test_id()` | `:8, :11-13` | 4 | Live: `home_screen.py:1210,1311`, `sites_screen.py:156`. Name-collides with `AdService.USE_TEST_IDS` → B7. |
| `ERR_NETWORK` `:89` / `ERR_GENERIC` `:90` / `ERR_OPEN_URL` `:91` / `ERR_INVALID_EMAIL` `:92` | 4 / 5 / 8 / 5 | | Live. |
| `MSG_OFFLINE` `:95` / `MSG_ONLINE` `:98` / `MSG_SEARCH_OFFLINE` `:99` | 5 / 3 / 7 | | Live. |
| 30 further `STORAGE_*` keys | `:32-78` | 3–8 each | Live and restored by `main.py:_load_saved_state`. |

### 2.3 Storage-key read/write matrix (the important table)

47 keys defined. **40 are read somewhere; 7 are never read by anything.**

| Key | Line | Written | Read | Restored by `main.py:_load_saved_state`? |
|---|---|---|---|---|
| `STORAGE_HISTORY` | `:32` | ✓ | ✓ (lazy) | n/a (on-demand) |
| `STORAGE_CACHED_RESULTS` | `:56` | ✓ | ✓ | ✅ `:835` |
| `STORAGE_CACHED_SITES` | `:34` | ✓ | ✓ | ✅ `:679` |
| `STORAGE_DB_UNHEALTHY` | `:54` | ✓ | ✓ | ✅ |
| `STORAGE_SHOW_ALL_RESULTS` | `:66` | ✓ | ✗ | ❌ |
| `STORAGE_VERBOSE_OUTPUT` | `:67` | ✓ | ✗ | ❌ |
| `STORAGE_EMAIL_DOMAINS` | `:73` | ✓ | ✗ | ❌ |
| `STORAGE_HUDSON` | `:74` | ✓ | ✗ | ❌ |
| `STORAGE_BULK_MODE` | `:75` | ✗ | ✗ | ❌ |
| `STORAGE_PROXY_FILE` | `:76` | ✓ | ✗ | ❌ |
| `STORAGE_PHONE_CONCURRENCY` | `:77` | ✓ | ✗ | ❌ |

(All other 36 keys: written ✓ / read ✓ / restored ✓.)

### 2.4 Refutation of the "dead toggle" hypothesis

`STORAGE_USE_CURL_CFFI` (`:64`) is **live**, not dead. Chain verified end-to-end: persisted/edited in `home_screen.py:535-537` and `settings_screen.py:681-682` → restored at `main.py:807-809` → forwarded to the engine at `main.py:1087` and `main.py:1536` → `email_service.py:207` → `email_service.py:251` (`use_stealth_fingerprint = use_curl_cffi`). The stealth-fingerprint behaviour is therefore *coupled to* the curl-cffi toggle — the constant name is accurate.

`STORAGE_ALLOW_LOUD` (`:65`) is live for username scans (`sherlock_service.py:208,240`) and email scans (`email_service.py:364,393`), but the **phone** path hardcodes `allow_loud=False` (`main.py:1777`), so the toggle has no effect in phone mode.

---

## 3) Storage-key correctness

### 3.1 The flet `SharedPreferences` forbidden-prefix rule does not apply to this app — and would be satisfied anyway

`flet/controls/services/shared_preferences.py:22-27` documents three Android-reserved prefixes that cannot be written:

```
VGhpcyBpcyB0aGUgcHJlZml4IGZvciBhIGxpc3Qu
VGhpcyBpcyB0aGUgcHJlZml4IGZvciBCaWdJbnRlZ2Vy
VGhpcyBpcyB0aGUgcHJlZml4IGZvciBEb3VibGUu
```

**The app never uses `SharedPreferences`.** `main.py:511` constructs `StorageService(self.page)`, which is file-backed: `storage_service.py:115` → `<storage_dir>/storage.json` under `.flet/storage/data/`, with `client_storage` used only for web sessions (`storage_service.py:121-125`). A repo-wide grep for `SharedPreferences` / `shared_preferences` across `src/` and `tests/` returns **zero hits**. So the prefix rule is currently moot.

**Nevertheless, all 47 keys are compliant by construction**: every key begins with `sherlock_`, and none begins with `VGhpcyBpcyB0aGUgcHJlZml4IGZvci`. A future migration to `SharedPreferences` would not need a single key rename. No finding — recorded for the record.

### 3.2 Key hygiene — clean

* **No duplicates.** All 66 constant names are unique; all string values are unique (programmatic check).
* **No literal drift.** No raw `"sherlock_*"` string literal appears anywhere outside this file (repo-wide grep) — every key is referenced through its constant, so a typo cannot silently fork a key.
* **No near-miss spellings.** A scan of every `STORAGE_*`/`MODE_*`/`AD_*`/`ERR_*`/`MSG_*`/`APP_*`/`UPDATE_*`/`PLAY_*`/`GITHUB_*`/`SITES_*`/`USE_*` identifier used across `src/` found **no** identifier that is used but not defined here (the single hit, `GITHUB_WEB`, is `ft.MarkdownExtensionSet.GITHUB_WEB` at `update_dialog.py:184,208` — a flet enum, not a constant).
* **Type discipline.** `StorageService.set` (`storage_service.py:288-297`) raises `TypeError` for a non-`str` key or value. Every key here is a `str` and every write path passes a `str` (`_persist` at `settings_screen.py:688-698` passes `str`; `json.dumps` results are `str`). Consistent today — but note the portability trap: flet's `SharedPreferences.set` accepts `str|int|float|bool|list[str]` (`shared_preferences.py:39-47`) while `StorageService` accepts `str` only. This file's constants give no type contract, so a future `int` write would crash the file backend and work on the flet backend.
* **Flat namespace.** All 47 keys share one flat namespace with no screen/module qualifier. `STORAGE_CROSS_LINKS` / `STORAGE_CROSS_EMAILS` / `STORAGE_CROSS_DEPTH` / `STORAGE_CROSS_SWEEP` share a prefix but are distinct scalars — no collision. Visually-confusable pairs that do **not** collide but invite a copy/paste slip: `STORAGE_TIMEOUT` (`:37`) vs `STORAGE_EMAIL_TIMEOUT` (`:43`); `STORAGE_SCAN_DEPTH` (`:55`) vs `STORAGE_CROSS_DEPTH` (`:71`); `STORAGE_EMAIL_CONCURRENCY` (`:44`) vs `STORAGE_PHONE_CONCURRENCY` (`:77`).

### 3.3 The restore contract is where the file breaks

`main.py:_load_saved_state` (`:635-848`) is the **only** startup-restore path, and it restores **39 of the 47** keys. The 8 it skips are exactly the 7 in §2.3 plus `STORAGE_HISTORY` (which is restored lazily on demand by `history_screen.py:117` / `home_screen.py:785` / `main.py:2223`). Six of the skipped keys have a live UI toggle, a live `state` field, and a live write — the user changes the setting, the app writes it to disk, the app tells the user it saved, and the next launch silently discards it.

This is a **contract failure of the constants file**, not just of `main.py`: the file declares 47 keys as the app's persistence vocabulary but carries no marker of which are "restore on boot" vs "read on demand" vs "dead". Nothing in `constants.py` tells a reader that `STORAGE_SHOW_ALL_RESULTS` will be written and never read.

---

## 4) Ad-unit correctness

### 4.1 What is here

Only **one** ad unit id lives in this file:

```
constants.py:86   AD_BANNER_UNIT_ID = "ca-app-pub-5679949845754640/5131365762"
```

The interstitial units are **not** here — they are class attributes of `AdService` (`ad_service.py:53-54`):

```
INTERSTITIAL_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/1033173712"
INTERSTITIAL_ID_ANDROID_PROD  = "ca-app-pub-5679949845754640/2758003779"
```

So the app has **two** homes for AdMob unit ids, and `constants.py` — the file whose docstring literally says "Application-wide constants" — holds only half of them. `banner_ad.py:4-5` even documents the split ("Production unit ID lives in core/constants.py (AD_BANNER_UNIT_ID)"), i.e. the split is intentional today but leaves the banner id with no companion test id and no iOS id.

### 4.2 Verification of the banner id

| Check | Result |
|---|---|
| Is it a **Google test** id left in a production path? | **No.** Publisher `5679949845754640` is the production publisher; Google's test publisher is `3940256099942544`. ✅ |
| Does the publisher match this app's AdMob application id? | **Yes.** `pyproject.toml:43` → `com.google.android.gms.ads.APPLICATION_ID = "ca-app-pub-5679949845754640~1261089274"` — same publisher/app (`~` app-id form vs `/` ad-unit form). Not a copy-paste from another account. ✅ |
| Is the id consistent with the repo's own reference doc? | **Yes.** `docs/reference/dep-flet-ads.md:227` records exactly `ca-app-pub-5679949845754640/5131365762` as "Banner Production ID (Android)". (Minor: that doc cites `constants.py:71` — the constant now lives at `:86`; `:71` is `STORAGE_CROSS_DEPTH`. Stale line ref.) |
| Is any **test** id reachable in production? | No for the banner (no test id exists for it). The only test id in the app is `ad_service.py:53`, gated by the hardcoded `USE_TEST_IDS = False` (`ad_service.py:51`). ✅ |
| Is it **Android-only**? | **Yes.** The id is documented as the *Android* banner production id. `banner_ad.py:88` gates only on `page.platform.is_mobile()` — Android **and** iOS — and passes this single id to `fta.BannerAd` (`banner_ad.py:97`). AdMob ad units are per-platform, so an iOS build requests an Android unit → never fills, silently, with no error surfaced to the user. |

**Severity qualifier:** the project ships Android-only — `pyproject.toml` has `[tool.flet.android]` (`:34-52`) and **no** `[tool.flet.ios]`, and `PLAY_STORE_URL` (`:28`) points at Google Play. So the iOS banner gap is **latent, not live**. It becomes a live zero-revenue bug the moment an iOS build is configured, and the same defect was already confirmed by the sibling flet-ads audit for the interstitial (its N7). The banner repeats it.

### 4.3 Two traps worth recording

1. **The banner has no test-unit escape hatch.** `AdService` has `USE_TEST_IDS` (`ad_service.py:51`) so a diagnostic build can prove the pipeline end-to-end. The banner has nothing equivalent — the diagnostic recipe in `banner_ad.py:17-21` ("if this banner ever appears empty on mobile, open Settings → Troubleshooting") cannot distinguish "wrong unit id" from "no fill". Google publishes banner test ids: Android `ca-app-pub-3940256099942544/9214589741`, iOS `ca-app-pub-3940256099942544/2435281174` (`docs/reference/dep-flet-ads.md:219`).
2. **flet-ads' own Dart fallback for a banner is an *interstitial* id.** `flutter/flet_ads/lib/src/banner.dart:23-27`:
   ```dart
   final testAdUnitId = isIOSMobile()
       ? 'ca-app-pub-3940256099942544/4411468910'   // iOS *interstitial* test id
       : 'ca-app-pub-3940256099942544/1033173712';  // Android *interstitial* test id
   BannerAd bannerAd = BannerAd(adUnitId: widget.control.getString("unit_id", testAdUnitId)!, ...
   ```
   The app always passes `unit_id=AD_BANNER_UNIT_ID`, so the fallback is never reached — but `AD_BANNER_UNIT_ID` must never be allowed to become empty/`None`, or the Dart default silently substitutes an interstitial unit into a banner slot.

---

## 5) Bugs (severity-ordered)

### B1 — HIGH — `UPDATE_CONFIG_URL` points at a repository that does not exist (`:25-27`)

```
"https://raw.githubusercontent.com/Nwokike/Sherlock-V2/main/version.json"
```

Verified live: `gh api repos/Nwokike/Sherlock-V2` → **`404 Not Found`**. The real repository is **`Nwokike/Sherlock`** (default branch `main`) — `gh api repos/Nwokike/Sherlock` → OK. `Nwokike/Sherlock-V3` also 404s (this working copy is a local workspace, not a published repo).

Consequence: `UpdateService.__init__` (`update_service.py:64`) defaults `config_url` to this constant → the update check **always fails** → no update banner is ever shown, and the release notes in `version.json` are unreachable in-app.

The repo's own canonical metadata already has the right URL — `version.json:8`:
```
"github_url": "https://github.com/Nwokike/Sherlock/releases/latest"
```

**Fix:** `UPDATE_CONFIG_URL = "https://raw.githubusercontent.com/Nwokike/Sherlock/main/version.json"`.

### B2 — HIGH — `GITHUB_RELEASES_URL` points at the same non-existent repository (`:29`)

```
"https://github.com/Nwokike/Sherlock-V2/releases/latest"
```

Same 404. This is the fallback link the update dialog opens (`update_dialog.py:86,90,99`) and the value `update_service.py:103` falls back to when the remote payload omits `github_url`. Since B1 makes the remote payload unreachable, **this 404 link is what users actually see** in the update dialog.

**Fix:** `GITHUB_RELEASES_URL = "https://github.com/Nwokike/Sherlock/releases/latest"` (exactly what `version.json:8` already says).

> B1 and B2 share one root cause: the URLs were written for the pre-rename `Sherlock-V2` layout and never updated. They are the only two GitHub URLs in the entire app source (repo-wide grep for `github.com` / `raw.githubusercontent` in `*.py`).

### B3 — MEDIUM-HIGH — Six persisted settings are silently discarded on every app restart (`:66, :67, :73, :74, :76, :77`)

| Constant | Line | `state` field | Written at | Restored? |
|---|---|---|---|---|
| `STORAGE_SHOW_ALL_RESULTS` | `:66` | `state.show_all_results` (`state.py:68`) | `settings_screen.py:605-606` | ❌ |
| `STORAGE_VERBOSE_OUTPUT` | `:67` | `state.verbose_output` (`state.py:69`) | `settings_screen.py:609-610` | ❌ |
| `STORAGE_EMAIL_DOMAINS` | `:73` | `state.email_domains` (`state.py:75`) | `settings_screen.py:633-634` | ❌ |
| `STORAGE_HUDSON` | `:74` | `state.hudson_enabled` (`state.py:76`) | `home_screen.py:567-568` | ❌ |
| `STORAGE_PROXY_FILE` | `:76` | `state.proxy_file` (`state.py:78`) | `settings_screen.py:640-641` | ❌ |
| `STORAGE_PHONE_CONCURRENCY` | `:77` | `state.phone_concurrency` (`state.py:79`) | `settings_screen.py:1209`, `home_screen.py:475-477` | ❌ |

Each has a live UI control, a live `state` field, and a live write path (`_persist` → `storage.set` + `flush`, `settings_screen.py:688-698`). None is read by `main.py:_load_saved_state` (`:635-848`) — or anywhere else. On the next launch the field falls back to its `state.py` default while the toggle still renders in its "on" position, so the UI actively misreports the persisted state.

Worst offenders:
* `STORAGE_PROXY_FILE` — a proxy file path silently disappears, so scans run **unproxied** while the user believes their proxy is active.
* `STORAGE_EMAIL_DOMAINS` — the user's email-domain filter disappears; scans broaden without warning.
* `STORAGE_PHONE_CONCURRENCY` — additionally **has no effect at all** (see B4b), so it is both unrestored *and* inert.

**Fix:** add restore blocks in `main.py:_load_saved_state` for the six keys; and mark restore-ability in this file (see §6 improvement I2).

### B4 — MEDIUM — The mode vocabulary is persisted but not round-tripped (`:83`, `:42`)

`MODE_PHONE` (`:83`) is a first-class mode — 41 references — and `home_screen.py:419` persists it:

```python
await storage.set(STORAGE_SEARCH_MODE, new_mode)
```

but `main.py:694-696` restores only:

```python
search_mode_raw = await self.storage.get(STORAGE_SEARCH_MODE)
if search_mode_raw in (MODE_USERNAME, MODE_EMAIL):
    state.search_mode = search_mode_raw
```

→ a phone-mode user is returned to username mode on every relaunch, and the phone catalog (`phone_service.load_sites()`) is never loaded at boot.

**Root cause is in this file's shape, not only in `main.py`:** the three modes are three separate scalars with no shared "valid set", so the restore filter had to re-type the list by hand and drifted. **Fix:** define the vocabulary once — e.g. `SEARCH_MODES = (MODE_USERNAME, MODE_EMAIL, MODE_PHONE)` at `:80-83` — and have both the persist and the restore paths iterate it.

### B4b — MEDIUM — `STORAGE_PHONE_CONCURRENCY` is persisted but never consulted by the scan it names (`:77`)

`state.phone_concurrency` is written by two screens (`settings_screen.py:637`, `home_screen.py:475`) and read by **nothing**. The phone scan uses the **email** concurrency instead:

```python
# main.py:1776
concurrency=getattr(state, "email_concurrency", 15),
```

So the phone-concurrency slider is decorative. Combined with B3 (never restored), `STORAGE_PHONE_CONCURRENCY` is doubly dead: persisted, never restored, never read. `STORAGE_EMAIL_CONCURRENCY` (`:44`) is the value that actually reaches the phone path.

### B5 — MEDIUM — `STORAGE_CACHED_RESULTS` is an unbounded, main-thread-parsed blob (`:56`)

* **Write:** `main.py:2202-2204` writes the *entire* `json.dumps(state.results_cache)` after **every** search completion — a full rewrite, not a delta.
* **Cap:** `state.set_cached_result` (`state.py:173-179`) caps the **entry count** at 30 ("LRU cap of 30 queries"). Each entry is a full scan snapshot (per-site payloads for up to ~2,700 sites). The count cap does **not** bound the byte size; the observed ~790KB blob is one snapshot in practice, not a ceiling.
* **Read:** `main.py:835-842` `json.loads` the blob **on the UI thread** inside `_load_saved_state`, i.e. on the event loop *before* the first frame, on every launch.

There is no size guard on either side. The 30-entry policy lives in `state.py`, ~1,000 lines away from the key that names it, so a reader of `constants.py` cannot tell that this key holds a capped cache rather than a scalar.

**Fix:** add a sibling constant next to the key — `STORAGE_CACHED_RESULTS_MAX_ENTRIES = 30` — and cap the serialized byte length before writing; consider moving the parse off the startup path.

### B6 — MEDIUM — `AD_BANNER_UNIT_ID` is an Android unit used on every mobile platform (`:86`)

`ca-app-pub-5679949845754640/5131365762` is the **Android** production banner id (`docs/reference/dep-flet-ads.md:227`). `banner_ad.py:88` gates only on `page.platform.is_mobile()` — Android **and** iOS — and hands this single unit to `fta.BannerAd` (`banner_ad.py:97`). AdMob ad units are per-platform, so an iOS build requests an Android unit → the request never fills → **silent** zero revenue (no exception, no `on_error`).

This is the same defect the sibling flet-ads audit recorded as N7 for the interstitial (`ad_service.py:76-80`), repeated for the banner, with the same "the constant names say ANDROID but are used for iOS" shape.

**Mitigating (and important):** the project is Android-only — `pyproject.toml` has `[tool.flet.android]` (`:34-52`) and no `[tool.flet.ios]`; `PLAY_STORE_URL` (`:28`) targets Google Play. Impact today is nil; the defect is **latent**.

**Fix:** add `AD_BANNER_UNIT_ID_IOS` next to `:86` and select by `page.platform` in `banner_ad.py`; also add `AD_BANNER_UNIT_ID_TEST` (Android `ca-app-pub-3940256099942544/9214589741`, iOS `.../2435281174`) so the banner has the same diagnostic escape hatch `AdService.USE_TEST_IDS` gives the interstitial.

### B7 — LOW-MEDIUM — Two unrelated switches share the name `USE_TEST_IDS` (`:8`, vs `ad_service.py:51`)

* `core.constants.USE_TEST_IDS` (`:8`) is **env-driven** (`SHERLOCK_TEST_IDS=1`) and only controls `key=` attributes on controls (`:11-13`).
* `AdService.USE_TEST_IDS` (`ad_service.py:51`) is a **hardcoded class attribute** (`False`) that swaps the interstitial unit for Google's test unit.

Setting `SHERLOCK_TEST_IDS=1` does **not** put the app in test-ad mode, and the two are indistinguishable by name at the call site. If anyone ever writes `from core.constants import USE_TEST_IDS` inside `AdService`, the class attribute shadows it and the import is silently ignored.

**Fix:** rename one (e.g. `AD_USE_TEST_IDS`) or make `AdService` read the same env var.

### B8 — LOW — `STORAGE_BULK_MODE` is entirely dead (`:75`)

Zero references outside its own definition; `state.bulk_mode` (`state.py:77`) is never assigned or read. Either wire it (persist + restore + a UI toggle) or delete both the constant and the state field. Today it is a key that can never exist on disk.

### B9 — LOW — A section header with nothing under it (`:103-105`)

```python
# ── Email OSINT constants ─────────────────────────────────────────────
# Validator names skipped by the "No Password Recovery" setting are
# derived at scan time from user-scanner's loud-module list.
```
The file ends at `:106`. The header promises constants; none follow, and the behaviour it describes lives in `services/user_scanner_compat.py` (`is_loud`, `allow_loud` at `:156, :236, :321, :451`). Either delete the block or move the note to the module that implements it — a reader currently greps this file for "email OSINT constants" and finds none.

### B10 — LOW — The `noqa: S105` note at `:48` is correct but self-defeating in wording

The directive is **necessary and working**: `ruff check src/core/constants.py` passes clean with `RUF` selected (`pyproject.toml:89`), and `RUF100` (unused-noqa) is in that set — so an unnecessary directive would itself be flagged. Ruff's S105 fires because the *variable name* contains "password".

But the note says "storage-KEY name, not a secret", which reads as if it is justifying the *value*; the trigger is the *variable name*. **Reword** to name the variable: `# noqa: S105 — variable name contains "password"; the value is a storage key`.

### B11 — LOW — `SITES_TOTAL_FALLBACK` is a hardcoded snapshot of a live upstream catalog (`:20-22`)

The comment's arithmetic is correct (2,521 + 220 + 5 = 2,746 ✅). But the constant is used as a *display denominator* via `total_sites or SITES_TOTAL_FALLBACK` (`app_shell.py:303,393`; `report_service.py:197,391,677,705`) — so the app can print "X / 2746" where 2746 is frozen in time while the upstream catalog grows. Add a "last verified <date>" to the comment, or derive it from the loaded catalog when available.

---

## 6) Verdict

**API correctness: clean.** This file imports only `os` and touches no third-party API. `ruff check` passes, `ast.parse` passes, all 66 constant names are unique, all string values are unique, no identifier is used anywhere in `src/` without being defined here, and no raw `"sherlock_*"` literal escapes this file. There is **no hallucinated API, no typo, and no near-miss spelling** in the file.

**The file's real problem is that it is a passive list with no contract.** Every defect above is the same shape: the constant declares a fact, and some *other* file is supposed to honour that fact, but nothing ties the two together — so the honouring quietly drifted:

* the two distribution URLs (`:26, :29`) point at a repository that **does not exist** (`gh api` → 404), so the entire update subsystem is dead in-app;
* 6 of the 47 storage keys are written and never read, so six user settings are silently lost on every relaunch and one (`STORAGE_PHONE_CONCURRENCY`, `:77`) is additionally inert because the phone scan reads the email concurrency (`main.py:1776`);
* `MODE_PHONE` (`:83`) can be persisted but is never restored (`main.py:695`);
* `AD_BANNER_UNIT_ID` (`:86`) is Android-only but used for all mobile platforms — latent today (Android-only build), live the moment iOS is configured.

**Storage-key correctness: verified clean on every axis the audit asked about.** The app does not use flet `SharedPreferences` at all (file-backed `StorageService` instead), so the three Android-reserved prefixes (`shared_preferences.py:22-27`) do not apply — and all 47 keys would satisfy them anyway (`sherlock_` prefix). No key collisions, no literal drift, no undefined references.

**Ad-unit correctness: the banner id is a legitimate production Android unit for the right AdMob app, with no test id in any production path — but it has no iOS counterpart, no test-unit escape hatch, and it is separated from the interstitial units that live in `ad_service.py:53-54`.**

**Concrete improvements (in priority order):**

1. **Fix the two URLs** (`:26`, `:29`) → `Nwokike/Sherlock` (verified live). *Unblocks the whole update subsystem.*
2. **Restore the six orphaned settings** in `main.py:_load_saved_state`, and **wire `state.phone_concurrency` into the phone scan** (`main.py:1776` currently reads `state.email_concurrency`).
3. **Introduce a shared mode vocabulary** — `SEARCH_MODES = (MODE_USERNAME, MODE_EMAIL, MODE_PHONE)` at `:80-83` — and use it in both the persist and the restore path so `MODE_PHONE` round-trips.
4. **Annotate the storage block** so the file states the contract instead of leaving it implicit: mark each key's lifecycle — `RESTORE_ON_BOOT` vs `READ_ON_DEMAND` vs `UNUSED`. A one-line comment per key (or three sub-sections) removes an entire class of "written but never read" drift. Right now nothing in the file says `STORAGE_SHOW_ALL_RESULTS` will never be read.
5. **Move both ad unit families into this file** — `AD_BANNER_UNIT_ID` (`:86`) plus `AD_BANNER_UNIT_ID_IOS`, `AD_BANNER_UNIT_ID_TEST`, and the interstitial prod/test ids currently in `ad_service.py:53-54` — so there is one place to look, one place to bump, and one place to add the banner's missing test escape hatch.
6. **Bound `STORAGE_CACHED_RESULTS`** (`:56`) by bytes, not just by entry count, and co-locate the `30` cap with the key (`STORAGE_CACHED_RESULTS_MAX_ENTRIES = 30`).
7. **Delete `STORAGE_BULK_MODE`** (`:75`) and `state.bulk_mode`, or implement the feature.
8. **Rename one of the two `USE_TEST_IDS`** (`:8` vs `ad_service.py:51`), and reword the `noqa: S105` note at `:48`.
9. **Delete the empty section header** at `:103-105`, and add a "last verified" date to the `SITES_TOTAL_FALLBACK` comment at `:20-22`.

**Risk rating:** HIGH for B1+B2 (the update subsystem is fully dead — a shipping-blocker for a versioned Play Store app), MEDIUM-HIGH for B3 (six user settings silently lost per launch, one of them a proxy path), MEDIUM for B4/B4b/B5/B6, LOW for B7-B11.
