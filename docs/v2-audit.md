# Sherlock v2 Audit — `feature/v2-upgrade` (48ddd8e) vs `main` (92b506b, v1.4.0)

**Date:** 2026-08-31 · **Branch:** `feature/v2-upgrade` · **Base:** `main` @ `92b506b` (tag `v1.4.0`) · **Flet:** `0.85.0` pinned · **Dirty:** 14 modified + 3 untracked

> Full file reads were used as evidence. Verdicts use `PASS / WARN / FAIL` per file/area.

---

## TL;DR

The v2 prototype is **additive and feature-correct in shape** — dual-mode OSINT (username via `sherlock-project` 400+ + email via `holehe` 121 modules), enrichment (`socid-extractor`, 164 schemes), and update/announcement service are real work, not stubs. **The main risks are implementation quality, not feature scope**: duplicated screen logic, a 700-line `ProfileDetailDialog`, leaky email cancel, swallowed enrichment errors, unbounded `enrichments`, two sources of truth for mode, and a still-uncommitted storage migration + header extraction. Ruff is clean, 90+ tests exist, but live email streaming / history / storage tests are untracked and thin. No Flet breakage — but **migration to `0.86.5` is mandatory** to stay aligned with 6/8 Kiri apps (KTV `2.1.0`/18, DDGS, Asase, MarkItDown, spaninsight, collabshell).

---

## 1. What the agent actually built

### Committed (4 commits, `main..feature/v2-upgrade`, `+3386/-279`, 21 files):

| Commit | What shipped |
|---|---|
| `a9c5a6f` | `holehe` (121 modules, 15-concurrency semaphore, 200 ms throttled progress via captured loop, cancel, pw-recovery filter) + `socid-extractor` (164 schemes). Home pill toggle, auto-detect email, `ResultCard` enrichment lines, `EnrichService`, `AppController.start_email_search`, `AppState` email fields, `version 1.4.0→2.0.0`, `build_number 7→8`. |
| `7bd7bf7` | Onboarding bottom-pin, Email OSINT slide, `Outfit`, ruff E731. |
| `0bb2912` | `version.json` + `UpdateService` (httpx 4 s) + `UpdateDialog` (Play/APK/Desktop branches). Home pill, Settings banner, `check_for_updates`/`open_update_dialog`. |
| `48ddd8e` | Email typing auto-switch fix + `ProfileDetailDialog` (avatar/bio/metrics/UID/location/date/recovery/links/copy/launch). `ResultCard` `on_tap`. |

### Dirty polish (14 modified + 3 untracked, `+1173/-645`):

`StorageService` → `FLET_APP_STORAGE_DATA` + atomic write + `flush()`, `AppHeader` extraction (untracked `src/components/app_header.py` ~164 lines), `history_screen.py` mode badge + re-search rehydration, `email_service.py` live-streaming churn, `sherlock_service.py` bridge tweak, `home_screen.py` 563-line churn.

### Deps:

`pyproject.toml` `flet==0.85.0` **unchanged**, added `holehe>=1.61` + `socid-extractor>=0.1.1`, `uv.lock` +253 lines (transitive `beautifulsoup4`, `trio`, `cffi`, `tqdm`, `attrs`, `soupsieve`, `pycparser`, plus `pytest 9.1.1`). `requires-python >=3.13`, `stem==1.8.1` pinned.

---

## 2. File-by-file verdicts

### 2.1 Services

#### `src/services/email_service.py` — **WARN** (correct idea, leaky edges)

**What it does:** Wraps `holehe.core.import_submodules/get_functions/is_email`, `EmailResult`/`EmailSearchProgress`, `validate_email`, `threading.Event` cancel, `asyncio` concurrency (not `trio`), 15-semaphore, 200 ms throttled `on_progress` via `asyncio.Lock`.

**Passes:**
- Dynamic `import_submodules("holehe.modules")` + `get_functions(args=None)` is the right API; `skip_password_recovery` via `EMAIL_PW_RECOVERY_MODULES = {adobe, mail_ru, odnoklassniki, samsung}` matches holehe's `-NP` flag.
- `EMAIL_FORMAT` regex fallback when `holehe` absent is sane; `total_modules` fallback `121`.
- Throttling via `last_update_time` + `progress_lock` is sound.

**Fails / warns:**
- **Cancel is racy.** `_cancel_event` is checked only at `_run_module` entry. Once 121 tasks are created (`asyncio.create_task(_bounded(m)) for m in modules`), they all hold the `httpx.AsyncClient` and run to completion. `cancel()` sets `is_cancelled`/`is_running` on progress but does **not** `task.cancel()` the 121 tasks nor close the client early. Expect tail waste + UI lag on Cancel.
- **Forged errors hide reality.** `except Exception: local_out.append({..., rateLimit: True, exists: False})` turns every module crash into "rate limited". Real errors (DNS, 401, parsing) become indistinguishable from rate limits — the Rate Limited tab inflates.
- **Empty `local_out` fallback is wrong.** If a module returns no dict, code invents `exists=False`. Some holehe modules legitimately leave `out` empty on success — this flips Found→Not Found.
- **`get_functions(args=None)` caching bug.** `_holehe_modules` is a global cached after first call with `args=None`. `skip_password_recovery=True` filters in Python, but the comment says "`get_functions` expects args with `nopasswordrecovery`" — if future `holehe` changes to native filtering, cache will be wrong. Not failing today, but fragile.
- **Not on thread — don't need `threading.Event`.** `EmailService.search` is `async`, called via `await controller.start_email_search`. Using `threading.Event` to signal across `asyncio` tasks is unidiomatic — `asyncio.Event` would compose with `await`. Works, but mismatched primitive.
- **Dirty live-streaming churn incomplete.** `tests/test_email_live_streaming.py` (untracked) tests only dataclass accumulation, not cancellation or throttle — suggests the streaming polish isn't finished.

#### `src/services/enrich_service.py` — **WARN**

**Passes:** Correct `socid-extractor` wrapping (`extract`, `parse`, `mutate_url`), `_SOCID_AVAILABLE` guard, `asyncio.to_thread(_parse)` for blocking `parse`, `batch_enrich` semaphore 5, `on_result` fire-and-forget.

**Warns:**
- **Failures swallowed.** `except Exception: return {}` / `return []` with only `logger.debug`. Callers (`main.py` enrichment) do `if enrichments: state.enrichments.update(...)` — silent empty looks like "no data" when it's actually a timeout/parse crash. Should log at `warning` or surface count.
- **`_parse` timeout not bounded end-to-end.** `enrich_url_with_mutations` calls `enrich_url` (timeout=5) **then** loops over mutations each with `timeout=5` — worst-case 5 s + N×5 s. A profile with 3 mutations can block 20 s, run inside `main.py`'s post-scan `batch_enrich` with no cancel.
- **`batch_enrich` ignores per-URL mutation richness.** It calls `enrich_url` (plain `extract`) not `enrich_url_with_mutations` — so `api.github.com` richness is never used in the batch path. `main.py`'s email enrichment also builds synthetic `https://{domain}` URLs — `socid-extractor` has no scheme for bare domains, so enrichment hit rate for email Found will be near zero (correct for username URLs, wasted for email).
- **No LRU / unbounded growth.** `state.enrichments` is a plain `dict` that grows per-scan. After `N×50` history entries with enrichment, memory + notify cost grows. Needs bound (e.g. 200).

#### `src/services/update_service.py` — **WARN**

**Passes:** `httpx.AsyncClient(timeout=4.0)` to raw GitHub `UPDATE_CONFIG_URL`, `build_number` compare, `UpdateInfo.to_dict()`, platform branching correctly left to dialog.

**Warns:**
- **No cache / ETag.** Every launch hits raw GitHub. On flaky mobile, this is a 4 s cold start tax. DDGS/KTV use cached `version.json` fallback — should persist last `build_number` or ETag.
- **`mandatory` fetched but barely used.** `UpdateService` returns `mandatory` but `AppController.check_for_updates` only does `if mandatory: open_dialog()` — no "Later" suppression. `UpdateDialog` does `modal=is_mandatory` + hides "Later" — correct, but service never enforces "mandatory = block search".
- **`APP_BUILD_NUMBER` / `APP_VERSION` drift risk.** `core/constants.py` `APP_BUILD_NUMBER=8`, `pyproject.toml` `build_number=8`, `version.json` `build_number=8`, `core/constants.py` `APP_VERSION="2.0.0"` — four-way sync with no test (the new `test_storage_service.py` doesn't cover this).

#### `src/services/storage_service.py` — **WARN** (good migration, not finished)

**Passes:** `get_storage_dir()` reads `FLET_APP_STORAGE_DATA` with `Path.is_absolute()` guard + fallback `project_root/.flet/storage/data`, `get_cache_dir`/`get_temp_dir`, atomic `.tmp→replace`, `StorageService(page=None, data_dir=None)`, `flush()`, `asyncio.Lock`, 1 s debounced `call_later(_flush_task)`.

**Warns:**
- **Dual-path history ordering contract is implicit.** Storage `oldest-first` (`entries.append` + `entries[-50:]`) vs observable `newest-first` (`insert(0)` + `reversed(load)`) is documented in comments but not enforced by a shared helper — easy to regress (previous bug was exactly this). `history_screen.py` now does `await storage.flush()` on clear, but other callers (`_save_to_history`, chip toggles) rely on debounced `call_later` — a crash before 1 s loses the last write.
- **Web vs native split is incomplete.** `_is_web = bool(getattr(page, "session_id", None))` is a weak heuristic; Flet web uses `page.client_storage` but also sets `FLET_APP_STORAGE_DATA` in some runners — could double-write. `_load_web` reads single key `sherlock_storage` but `_save_now_web` writes `client_storage.set("sherlock_storage", json.dumps(_data))` — so web loses per-key granularity.
- **New test is solid but untracked.** `tests/test_storage_service.py` covers `get_storage_dir` env, CRUD atomic, no `.tmp` leftover — promotes to committed.
- **`.gitignore` already updated** `.flet/` + `storage/` — correct.

#### `src/services/sherlock_service.py` — **PASS** (best file in v2)

**Passes:** Keeps thread bridge via captured loop + `run_coroutine_threadsafe`, `_CollectorQueryNotify` 250 ms throttle, `load_sites` caching via `state.custom_manifest`/`use_local_db`/`ignore_exclusions`/`nsfw_enabled`, `parse_usernames` comma→space→`{?}` expansion, `SystemExit` guard, multi-target sequential loops. Dirty 29-line tweak preserves bridge.

**Nits:**
- `load_sites` duplicates path resolution (`get_storage_dir()/synced_data.json` vs `sherlock_project/resources/data.json`) between `load_sites` and `search` — same code pasted twice.
- `selected_sites` filter is case-insensitive lowercased set — correct — but `state.selected_sites = []` vs `None` inconsistency still exists in `core/state.py` (`__init__` sets `[]` but type is `list[str] | None`).

#### `src/services/ad_service.py` + `src/components/banner_ad.py` — **WARN** (income-critical, now behind Kiri)

**Passes:** `AdService(page)`, mobile gate `page.platform.is_mobile()`, `BannerAd(320×50)` + `InterstitialAd(on_close→preload)`, `build_banner_ad(page=None)` resolving `flet.context.page`, desktop fallback `Container(0,0)` — matches v1.

**Fails to align with Kiri:**
- **No `ConsentManager`.** KTV `d0fd668` / DDGS `76dbc24` require `fta.ConsentManager()` registered on `page.services` + `await gather_consent()` before `preload_interstitial`. Sherlock v2 still calls only `preload_interstitial` in `main.py` — will fail Play policy on TCF/UMP. `flet_ads 0.85.0` has no `ConsentManager` API (per memory), but migration to `0.86.5` makes it mandatory.
- **No `NativeAd`.** KTV added `NativeAdTemplateStyle/Type` + `get_native_ad()` + fallback `get_standard_banner_ad()` in `9014c06`. Sherlock still only has `BannerAd` — leaves revenue on table.
- **Two banner builders.** `AdService.get_banner_ad()` (plain container 320×50) vs `build_banner_ad()` (glass `SPONSORED` container) diverge — screens use the glass one; `AdService` is dead code except for `preload_interstitial`. Should unify (`build_banner_ad` delegates to `AdService.get_banner_ad()` like MarkItDown).
- **No singleton.** Kiri uses `get_ad_service(page)` singleton holding preloaded interstitial across screens — Sherlock constructs `AdService` per `AppController` instance (fine) but reinstalls `BannerAd` per screen (re-creates native view). Not a leak (0.85 has no `dispose()`), but wasteful.

---

### 2.2 Core & State

#### `src/core/state.py` — **WARN**

**Passes:** `@ft.observable AppState`, `collections` assigned in `__init__` (wrapping), `reset_search` clears `search_progress`, `email_results`, `enrichments`.

**Warns:**
- **`is_first_launch` + `has_accepted_terms` dual flags.** `AppShell._should_show_onboarding` checks `is_first_launch or not has_accepted_terms` — two bools for one concept. `set_onboarding_done` sets both. Could simplify to single `has_accepted_terms`.
- **`search_progress: object | None` untyped.** Loses `SearchProgress` vs `EmailSearchProgress` distinction — `results_screen.py` does `hasattr(active_progress, "checked_modules")` to branch. Should be union typed.
- **`enrichments: dict` unbounded**, already noted.
- **Email fields partially persisted.** `email_timeout` + `no_password_recovery` + `search_mode` are persisted, but `email_results` / `enrichments` / `update_available` are not — correct (transient) — but `is_online` defaults `True` until first probe — correct too.

#### `src/core/constants.py` — **PASS** (with drift risk)

`APP_VERSION="2.0.0"` + `APP_BUILD_NUMBER=8` + `UPDATE_CONFIG_URL` (raw GitHub) + `PLAY_STORE/GITHUB` URLs + storage keys + `MODE_*` + `EMAIL_PW_RECOVERY_MODULES` frozenset — all in one place. Drift risk only: `pyproject.toml` + `version.json` must stay in sync — no CI check.

---

### 2.3 App Controller & Shell

#### `src/main.py` — **WARN** (solid, one bad email enrichment path)

**Passes:** `AppController(page)` owns 6 services + `_main_loop` captured at `init`, `page.services.append(FilePicker)` + `Connectivity(on_change)`, `StorageService(page)` + `SherlockService` + `EmailService` + `EnrichService` + `UpdateService`, `_load_saved_state` 11 keys, `refresh_sites` closure, `page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))`, `_progress_from_thread` via `run_coroutine_threadsafe` (correct — previous bug used `page.run_task` off loop), `_apply_progress` bumps `progress_version`, `start_search` offline gate + `show_interstitial` + `batch_enrich(found URLs, on_result→page.update())`, `start_email_search` `validate_email` + offline gate + synthetic domain enrichment, `_save_to_history(query, found, total, mode)`, `check_for_updates` + `open_update_dialog`.

**Fails:**
- **Email enrichment builds fake URLs.** `found_urls = [f"https://{r.domain}" for r in result.found if r.domain]` — `holehe` `domain` is `twitter.com` etc., not a profile URL. `socid-extractor` will fetch the homepage and `extract` will find no scheme — 0% hit rate, wasted 5×5 s batch.
- **Email mode final apply is late.** `state.email_results[:] = all_results` happens **after** enrichment attempt, but `_email_progress_callback` already streams `_apply_progress(active_progress)` during scan — `results_screen.py` reads either `active_progress` or `state.email_results` depending on `is_running`. Works, but `progress_version` bump inside enrichment `if enrichments: state.enrichments.update(...); state.progress_version+=1` without `page.update()` may not re-render until next tick.
- **Duplicate history contract.** `_save_to_history` `entries.append` + `entries[-50:]` + `state.history.insert(0, entry)` — correct — but `HomeScreen._load_history` does `state.history.extend(reversed(entries))` on mount, re-adding after `AppController` already populated — double-add on first launch if both run before `reversed` dedupe.

#### `src/app_shell.py` — **PASS** (clean reuse)

NavigationBar reuse (`if isinstance(current_nav, NavigationBar): selected_index=active_tab else: create`) is a genuine improvement over v1's recreate. `_sync_chrome` via `use_effect([active_tab, active_view, has_accepted_terms])` + `page.views[0].appbar/navigation_bar` mutation is correct. Export `xlsx/csv/txt` via `FilePicker.save_file` + `pandas` + `csv` preserved.

**Nits:** `appbar` branch for `results` builds `Copy URLs` that reads `app_state.search_progress.found` — in email mode `search_progress` is `EmailSearchProgress` with `found: list[EmailResult]` whose `url_user` is always `None` — copy will be empty in email mode. Minor.

#### `src/state/controller_ctx.py` — **PASS**

`ControllerMethods` mutable dataclass + `ControllerMethodsCtx = ft.create_context(ControllerMethods())` — textbook. New fields `start_email_search`/`cancel_email_search`/`check_for_updates`/`open_update_dialog` follow same `refresh_sites` pattern. No-ops safe for tests.

---

### 2.4 Components

#### `src/components/result_card.py` — **WARN** (14 params, two modes jammed, but renders correctly)

399 lines, `ResultCard(site_name, status, url_user, url_main, query_time, on_open, on_tap, email_recovery, phone_number, others, method, rate_limit, frequent_rate_limit, enrichment)` — polymorphic tile.

**Passes:** `status→icon/color/chip` mapping, `avatar_url = image|avatar|photo`, bio/location/followers/following, `method` badge (`register`/`password recovery`/other), `rate_limit & frequent_rate_limit` notice, `_handle_click` prefers `on_tap` else `on_open(url_user)` — correct for `ProfileDetailDialog`.

**Warns:**
- **God props.** 14 params; `enrichment` + `others` + `email_recovery` + `phone_number` + `method` should be a single `details: EmailResult | Enrichment | SiteResult` dataclass.
- **Avatar `Image(src=avatar_url)` with no `on_error` fallback beyond `error_content`.** Correct, but `avatar_url` can be a relative path from `socid-extractor` — `Image` will 404. Should guard `avatar_url.startswith("http")`.
- **`display_title = f"{site_name} · {enrichment.name or fullname}"` mixes platform name with display name — can produce `GitHub · The Octocat` — okay but noisy.

#### `src/components/profile_detail_dialog.py` — **FAIL** (700+ lines, duplicated, needs split)

**Passes:** Dual dossier works — email branch shows domain/method badge/recovery/phone/others/date, username branch shows avatar/bio/metrics/UID/location/joined/links, copy via `ft.Clipboard`, open via `ft.UrlLauncher`, status chips.

**Fails:**
- **God file (734 lines dirty).** 370-line `if is_email:` + 360-line username branch duplicated: `_detail_row` defined twice, chip calculation duplicated, header row duplicated, `async _copy_text` / `_dismiss` shared but `platform_url` vs `profile_url` vs `avatar_url` split. Must extract `EmailDossier(...)` + `UsernameDossier(...)` + shared `DossierRow`.
- **No tests.** `test_update_service.py` smokes dialog creation with `MockPage`, but `profile_detail_dialog.py` has zero tests — 700 lines with `asyncio.create_task(_copy_text)` and `page.pop_dialog()` deserve at least one `MockPage` assertion.
- **Fire-and-forget launchers.** `on_click=lambda e: asyncio.create_task(_launch_platform_url())` — if `page.pop_dialog()` happens first, the `context.page` inside `_launch` may be stale. Works today because `page` is closed over, but pattern is fragile.

#### `src/components/update_dialog.py` — **PASS** (with caveat)

Platform-aware (`page.platform == ANDROID → Play+APK else GitHub`), announcement vs update branches, `mandatory` hides "Later", `asyncio.create_task(_launch(url))`. **Caveat:** `page.platform` enum comparison is `== ft.PagePlatform.ANDROID` — on web `page.platform` can be `LINUX` or `UNKNOWN` — desktop branch will show GitHub button correctly, but `is_android` should also handle `page.platform.is_mobile()` to catch Android via `Context`.

#### `src/components/app_header.py` — **PASS** (promote this)

Untracked ~164 lines, unified header with theme cycle (dark→light→system + persist) + settings gear + `extra_actions`. Used by Home/History/Settings — correct dedupe. Clean `ft.Container(Row(left=[icon+title], right=[extra+theme+settings]))`. **Needs `git add` + keep.**

#### `src/components/banner_ad.py` — **PASS** (see ad warn above)

`build_banner_ad(page=None)` resolves `flet.context.page`, mobile gate, `BannerAd(320×50)` + glass `SPONSORED` wrapper, zero-size fallback — correct for 0.85. Unify with `AdService` on migration.

---

### 2.5 Screens

#### `src/screens/home_screen.py` — **WARN** (600+ lines, two sources of truth for mode, auto-switch fixed but still fragile)

1098 lines → 563-line dirty churn.

**Passes:** Pill toggle `MODE_USERNAME/MODE_EMAIL` via `state.search_mode` + `StorageService.set(STORAGE_SEARCH_MODE)`, `_FEATURES_USERNAME/_FEATURES_EMAIL` + `_STEPS_*` split, `TargetsCard` hidden in email mode, version pill (`Update` vs `News` vs `v2.0.0`), `Recent` 3 rows reactive via `state.history`, offline banner `visible=not state.is_online`, quick chips (`Timeout`/`Offline DB`/`NSFW`/`Exclusions` / `Email Timeout`/`PW Recovery`).

**Warns:**
- **Auto-switch heuristic.** `if "@" in value and "." in value.split("@")[-1] and len(tld)>=2: _switch_mode(MODE_EMAIL)` — fixes the reported "email typing auto-switch revert" bug (`48ddd8e`) by only switching on full paste, but typing `user@example.co` will still auto-flip from username to email mid-typing. Should trigger only on paste/submit, not `on_change`.
- **Chip `on_click` creates new StorageService per click.** Each toggle does `storage = StorageService(_get_page()); await storage.set(...)` — re-reads `FLET_APP_STORAGE_DATA` path per toggle. Not a bug, but wasteful vs holding `controller.storage`.
- **`Recent` `on_click=lambda _, e=entry: _on_history_click(e)` captures `entry` via default arg — correct (avoids late-binding bug) — good.

#### `src/screens/results_screen.py` — **WARN** (massive duplication, live streaming wired but brittle)

551→+441 lines.

**Passes:** `is_email_mode = state.search_mode == MODE_EMAIL`, `_filter_username_items` + `_filter_email_items` with `use_debounce(250)`, `_build_username_result_list` / `_build_email_result_list` with `EmptyState`, dual `Tabs` (Found/NotFound/Errors vs Found/NotFound/RateLimited), `_open_url` via `ft.UrlLauncher`, `_show_username_details/_show_email_details` → `ProfileDetailDialog`, `progress_section` + `stats_row` + `filter_box` + `tabs` + `build_banner_ad()`. Live streaming reads `active_progress.found/not_found/rate_limited` while `is_running`, falls back to `state.email_results` after.

**Warns:**
- **Huge duplication.** Email branch converts `EmailResult` → `dict` (`name/domain/exists/rateLimit/...`) then `ResultCard` re-branches on `rateLimit/frequent_rate_limit/method`. That's the same data round-trip twice. `progress→dict→ResultCard` + username `SiteResult→ResultCard` could share `_build_result_list(items, filter_fn, card_fn)` with a thin adapter.
- **`Column(spacing=0, scroll=AUTO, expand=True)` with 400 rows.** Virtualization debt unchanged — should be `ListView(build_controls_on_demand=True)`. `_build_*_result_list` returns `Column` that will jank on first paint.
- **`checked/total` source flips.** While running, `total = active_progress.total_modules or state.email_total_modules or 121`; after, `total = state.email_total_modules or len(all_email) or 121`. If scan cancelled early, `checked` is `active_progress.checked_modules` but `total` stays 121 — progress label `Checking 40/121 (33%)` persists after Cancel — misleading.

#### `src/screens/history_screen.py` — **PASS** (dirty polish is correct)

Mode badge (`ALTERNATE_EMAIL_ROUNDED` vs `PERSON_SEARCH_ROUNDED`), `mode = entry.get("mode") or (MODE_EMAIL if "@" in query else MODE_USERNAME)` fallback is fragile but correct for pre-v2 history without `mode`. Re-search rehydrates `state.search_mode` + `start_email_search` vs `start_search`. `tiles ink=True` + `on_click`, clear-all via `AppHeader`, `ListView`, `build_banner_ad()`.

**Nits:** `await storage.flush()` only on clear — other writes stay debounced. `@` fallback should be removed after one migration pass writes `mode` everywhere.

#### `src/screens/settings_screen.py` — **WARN** (correct cards, one desktop bug shape, missing flush on some paths)

**Passes:** Grouped cards `preferences_card`/`scan_card`/`email_card`/`performance_card`/`manifest_card`/`about_card`, `AppHeader`, `SectionHeader`, theme 3-cards, `Switch` + `Dropdown` + `TextField`, `update_badge` (`Announcement` vs `Update vX`), `Check for updates` via `controller.check_for_updates`.

**Warns:**
- **`DropdownOption` API drift.** `ft.DropdownOption("5","5s")` uses positional constructor — Flet 0.85 expects `ft.dropdown.Option` — `DropdownOption` is an alias that was renamed in 0.86 — migration must audit. Same for `on_select` vs `on_change` (0.85 uses `on_change`, dirty file uses `on_select` — which is 0.86). Dirty file is already half-migrated — will break on 0.85 and is ready for 0.86.
- **Manifest `TextField` re-creates on every render.** No `use_state` for manifest value — typing lags as `state.custom_manifest` triggers `refresh_sites` task per keystroke. Should debounce.
- **`_persist` helper uses `context.page`** but `page` is already closed over — fine, but `StorageService(context.page)` per persist re-creates path resolution — same as Home.

#### `src/screens/onboarding_screen.py` — **PASS**

3 slides (400+ Networks / Email OSINT / Exports), swipe `GestureDetector(on_horizontal_drag_end)`, dot indicators (`Animated width 24→8`), bottom-pinned `Column(expand=True) + Container(dots+button)`, `gradient` — correct. Dirty only formats.

---

### 2.6 Performance, Security, Packaging, UX, Tests

#### Performance — **WARN**

- **Concurrency 15 + throttle 200 ms** (email) vs **250 ms** (username) is appropriate — sibling `progress_version` style. `enrich_service` batch runs **post-scan** (main.py `_enrich_task` via `page.run_task`) — progressive (`on_result→page.update()`) — not blocking UI. Dirty "auto-enrich during search" would double the concurrent fetch load — keep sequential post-scan.
- **Missing virtualization** is the largest perf debt — 400-row `Column` in `results_screen.py` will drop frames on low-end Android. KTV uses `ListView(build_controls_on_demand=True)` — adopt.
- **`use_debounce` 250 ms** correctly on filter, `use_memo` on `_category_chip/_history_row/_feature_card` — good.

#### Security — **PASS**

- `holehe` checks 121 login/register/recovery endpoints — user supplies email, only probing public endpoints — not a credential dump. `EMAIL_PW_RECOVERY_MODULES` opt-out reduces sensitive recovery hints — good default.
- `httpx` with browser `User-Agent` + `follow_redirects=True` — okay, but `enrich_service` fetches arbitrary profile URLs — no SSRF guard. `socid-extractor` fetch is bounded by `timeout=5` + 5-concurrency — acceptable for on-device.

#### Packaging / Deps — **WARN**

- **`uv.lock` +253 lines** for `holehe` + `socid-extractor` ( `trio`, `beautifulsoup4`, `cffi`, `pycparser`) is expected — but CI must handle `stem==1.8.1` `PIP_FIND_LINKS` precompile (existing `.github/workflows` packaging job does — verify after migration).
- **No `.env`** anywhere — correct (runtime storage only).
- **Signing missing.** `pyproject.toml` lacks `[tool.flet.android.signing] key_store="../../../../kiri_keystore.jks"` alias `upload` — every other `ng.kiri` app (KTV, Asase, MarkItDown, DDGS, spaninsight, collabshell) shares it. Must add on migration or Play upload fails.
- **`[tool.flet.app] startup_message`** uses 0.85 schema — siblings use `[tool.flet.app.boot_screen] startup_message` (0.86).
- **`requires-python >=3.13`** vs KTV `>=3.14`, Asase/MarkItDown `>=3.12` — Sherlock's pin is tightest; keep but document.

#### UX / Brand — **PASS**

- Gold `PRIMARY #A68E59` / `PRIMARY_LIGHT #CD995F` / `PRIMARY_DARK #8A7347` + `ACCENT #0EA5E9` dark `DARK_BG_1 #0F1114` / `LIGHT_BG #FAFAFA` — consistent vs `main` and siblings' gold. `Outfit` font, glass `adaptive_glass_bg/border`, `AppStyles.brand_gradient` — DDGS-aligned.
- Ads `USE_TEST_IDS=False` — correct, but AdMob `0 active, 0 enabled` (from memory) is the real reason ads don't show — not code.
- `onboarding` slide 2 now "Email OSINT Made Easy" — correct v2 messaging.

#### Tests — **WARN**

- Committed 90 tests (commit history 61→79→88→90, `test_email_service.py` 105, `test_enrich_service.py` 105, `test_update_service.py` 213, `test_components.py` +58). Ruff clean.
- **Untracked** `test_email_live_streaming.py` (40 lines — only dataclass accumulation + `service.cancel()`), `test_history_mode_persistence.py` (mock `MockStorage` + `AppController._save_to_history` round-trip), `test_storage_service.py` (env path + CRUD atomic + no `.tmp` leftover) — all **should be committed** — they cover the exact dirty areas.
- **Gaps:** no cancel streaming test, no rate-limit tab test, no enrichment failure test, no offline gate test, no `ProfileDetailDialog` smoke test (only `UpdateDialog` has one).
- Evidence: `uv run ruff check .` → `All checks passed!` on dirty branch.

---

## 3. Kiri alignment debt (must fix for Play + parity)

| Area | Sherlock v2 (`0.85.0`) | Kiri canonical (`>=0.86.5`) | Action |
|---|---|---|---|
| `flet` | `flet==0.85.0`, `flet-ads==0.85.0` | `flet>=0.86.5`, `flet-ads>=0.86.5` (KTV 2.1.0/18, DDGS) | Bump `pyproject.toml` + `uv sync --upgrade` |
| `Icon` | `ft.Icon(name=)` may exist | `ft.Icon(icon=)` (KTV `780f36e`) | grep `Icon(name=` → `Icon(icon=` |
| `ImageFit` | `ft.ImageFit` | `ft.BoxFit` | grep `ImageFit` → `BoxFit` |
| `BannerAd` guard | `init` mobile check (works today) | `before_update` guard (DDGS `037b425` #6726) | Keep `build_banner_ad` 0-size fallback; no `BaseAd.init` monkey-patch needed (Sherlock has none — DDGS removed theirs) |
| `ConsentManager` | absent | `fta.ConsentManager()` on `page.services` + `gather_consent()` (KTV `d0fd668`) | Add `AdService.gather_consent()` + `page.services` registration + `await` before `preload_interstitial` |
| `NativeAd` | absent | `NativeAdTemplateStyle/Type` + fallback `get_standard_banner_ad()` (KTV `9014c06`) | Add `NATIVE_ID` + `get_native_ad()` (optional, revenue) |
| Signing | absent | `key_store="../../../../kiri_keystore.jks"` alias `upload` | Add `[tool.flet.android.signing]` |
| `boot_screen` | `[tool.flet.app] startup_message` | `[tool.flet.app.boot_screen] startup_message` | Migrate key |
| `Dropdown` | `DropdownOption` + `on_select` (mixed) | `ft.dropdown.Option` + `on_change`/`on_select` per version | Normalize on `0.86.5` API |
| `SnackBar` | `SnackBar` via `page.show_dialog(SnackBar)` | still `show_dialog` / `show_snack_bar` — verify `core/notify.py` | Probe `flet` 0.86.5 `SnackBar` path |
| `FilePicker` | `page.services.append(FilePicker)` | same | keep |
| `AdService` singleton | per-`AppController` | `get_ad_service(page)` (spaninsight/MarkItDown) | Optional singleton wrapper |

---

## 4. Remediation plan (no scope loss)

### Phase 0 — Stabilize (1 day, read-only verified)

- [ ] `git branch backup/v2-prototype-2026-08-31` from `feature/v2-upgrade` HEAD.
- [ ] Decide dirty → commit vs stash; commit `WIP: storage/history/header live-streaming polish` so diff is `main..HEAD` clean.
- [ ] Verify `uv run ruff check .` + `uv run pytest -q` green on both `main` and `feature/v2-upgrade` (flag if not).

### Phase 1 — Critical fixes on `feature/v2-upgrade` (Flet `0.85.0`, before migration)

- [ ] **Email cancel:** Cancel tasks + close `AsyncClient` — track `tasks` list + `asyncio.gather(..., return_exceptions=True)` + `for t in tasks: t.cancel()` on `cancel()`; or replace `threading.Event` with `asyncio.Event` polled between modules.
- [ ] **Email error handling:** Don't forge `rateLimit=True` on exception — surface as `others={"error": str(exc)}` + `rate_limit=False` so UI shows Errors vs Rate Limited correctly.
- [ ] **Email empty `out` fallback:** Don't invent `exists=False` when `local_out` empty — treat as inconclusive / skip.
- [ ] **Email enrichment fake URLs:** Remove `https://{domain}` enrichment in `main.py:start_email_search` (or gate behind `socid_extractor` scheme check). Keep enrichment only for username mode (real `url_user`).
- [ ] **`enrich_service` swallowing:** Promote `logger.debug` → `logger.warning` for `enrich_url` fail, add count; make `batch_enrich` use `enrich_url_with_mutations` or document why not.
- [ ] **Bound `enrichments`:** Cap `state.enrichments` (LRU 200) or clear on `reset_search` is enough — already cleared — add cap to avoid long-session growth.
- [ ] **`profile_detail_dialog.py` split:** Extract `EmailDossier` + `UsernameDossier` + shared `DossierRow` — keep 700 lines but two 250-line helpers + shared row.
- [ ] **`result_card.py` props:** Introduce `ResultViewModel` (`site_name/status/url_user/display_name/recovery/phone/method/enrichment`) — single prop vs 14.
- [ ] **`results_screen.py` dedupe:** Extract `_build_result_list(items, filter_fn, card_fn)` + single `progress_label(stats)` helper; keep dual tab sets (Found/NotFound/Errors vs Found/NotFound/RateLimited) but share list builder.
- [ ] **Virtualization:** Replace `Column(spacing=0, scroll=AUTO, expand=True)` with `ListView(build_controls_on_demand=True)` for both username and email tabs.
- [ ] **`home_screen.py` auto-switch:** Only auto-switch on paste/submit (`value` validated as email), not on every `on_change` keystroke.
- [ ] **`app_header.py` promotion:** `git add src/components/app_header.py` + migrate Home/History/Settings to it (already done dirty — commit).
- [ ] **`storage_service.py` promotion:** Commit `get_storage_dir`/`get_cache_dir`/`get_temp_dir` + atomic write + `flush()` + `tests/test_storage_service.py` + `.gitignore .flet/`.
- [ ] **History contract helper:** Extract `load_history_entries(raw) -> newest_first` so `HomeScreen._load_history` + `AppController._save_to_history` share one `reversed` codepath.
- [ ] **Tests promotion + gaps:** `git add tests/test_storage_service.py tests/test_history_mode_persistence.py tests/test_email_live_streaming.py` + expand live streaming test to cancel + throttle + `ProfileDetailDialog` smoke.

### Phase 2 — Flet `0.85.0` → `0.86.5` migration (follow KTV `9014c06` + DDGS `037b425`)

- [ ] `pyproject.toml` `flet==0.85.0 → flet>=0.86.5`, `flet-ads==0.85.0 → >=0.86.5`, `uv sync --upgrade` (+ bump `build_number 8→9`, keep `version 2.0.0`).
- [ ] `core/constants.py` `APP_BUILD_NUMBER 8→9`, `version.json` `build_number 8→9` — four-way sync.
- [ ] `ft.Icon(name=) → ft.Icon(icon=)` (grep), `ft.ImageFit → ft.BoxFit`.
- [ ] `BannerAd` desktop guard stays `build_banner_ad(0-size)` — no monkey-patch.
- [ ] `AdService` + `banner_ad.py` alignment: add `fta.ConsentManager()` + `gather_consent()` + `show_privacy_options()`, register on `page.services`, call before `preload_interstitial` in `main.py`; add `NATIVE_ID` + `get_native_ad(template_type)` + fallback (optional).
- [ ] `[tool.flet.android.signing]` + `[tool.flet.app.boot_screen]` migration.
- [ ] `Dropdown` API audit (`Option` + `on_select` vs `on_change`) — normalize to 0.86.5.
- [ ] Verify desktop run + `ruff` + `pytest -q` (+ BannerAd 0-size fallback not crashing — DDGS #6726 regression).

### Phase 3 — Polish & release

- [ ] Theme `CardTheme`/`NavigationBarTheme`/`PageTransitionsTheme` from KTV if missing — keep gold `PRIMARY #A68E59`.
- [ ] `banner_ad.py` delegates to `AdService` (MarkItDown pattern), bottom-pinned banner with glass border (siblings).
- [ ] Update `README.md` Flet version + screenshots — keep `AdMob 0 active` note (code correct, console approval needed).
- [ ] Merge `feature/v2-upgrade → main` (PR), tag `v2.0.0`, `v1.4.0` anchor stays. `CHANGELOG` if present. CI `fpm`/desktop packaging re-verified (stem precompile).

---

## 5. What to keep vs throw away

| Keep | Throw away / redo |
|---|---|
| Dual-mode OSINT, 121 modules, pw-recovery filter | Forged `rateLimit` errors, fake `https://{domain}` enrichment |
| `EmailService` semaphore 15 + throttle 200 ms pattern | `threading.Event` cancel → replace with `asyncio.Event` + task cancel |
| `socid-extractor` on username `url_user` (avatar/bio/followers) | Swallowed extraction errors — log them |
| `UpdateService` + `UpdateDialog` + `version.json` | None — promote as-is, add ETag later |
| `StorageService` `.flet/storage/data` + atomic write + `flush()` | `session_id` web heuristic as sole gate — keep fallback |
| `AppHeader` extraction | None — promote |
| `AppShell` NavigationBar reuse | None |
| History `oldest→newest` reversed + mode badge | `@` fallback once `mode` is ubiquitous |

---

## 6. Risks

- **holehe flakiness / timeout:** 15 semaphore + 10 s default is right; keep `skip_password_recovery` reducing noise; per-module `httpx.Timeout` already via `AsyncClient(timeout=state.email_timeout)`.
- **Desktop ad crash regression:** DDGS `BaseAd.init → before_update` fix must stay — Sherlock has no monkey-patch to remove, but 0-size fallback must remain.
- **Storage data loss:** Keep fallback read from `storage/data/storage.json` → write to `FLET_APP_STORAGE_DATA`, atomic replace prevents corruption.
- **Tests give false confidence:** Current email/enrich tests are smoke — don't trust them for cancel or enrichment semantics until Phase 1 gaps filled.

---

## 7. Files to read (complete)

`src/services/email_service.py`, `enrich_service.py`, `update_service.py`, `storage_service.py`, `sherlock_service.py`, `ad_service.py`, `src/components/app_header.py`, `banner_ad.py`, `result_card.py`, `profile_detail_dialog.py` (734), `update_dialog.py`, `src/core/state.py`, `constants.py`, `theme.py`, `notify.py`, `src/main.py`, `src/app_shell.py`, `src/state/controller_ctx.py`, `src/screens/home_screen.py` (1098), `results_screen.py` (551→+441), `history_screen.py` (221), `settings_screen.py` (638), `onboarding_screen.py` (236), `src/hooks/use_debounce.py`, `pyproject.toml`, `uv.lock` (+253), `version.json`, `.gitignore`, `tests/test_email_service.py`, `test_enrich_service.py`, `test_update_service.py`, `test_email_live_streaming.py` (untracked), `test_history_mode_persistence.py` (untracked), `test_storage_service.py` (untracked).

---

## 8. Next action

Approve Phase 0/1 scoping or ask to shrink/expand. No code changes until you confirm. Audit doc is at `docs/v2-audit.md` — gitignored `.zcode/plans` was intentionally avoided.
