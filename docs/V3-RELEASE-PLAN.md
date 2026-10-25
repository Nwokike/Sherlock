# Sherlock V3 — Complete Work Breakdown to Final Publication

Source: full swarm (34 dep audits + 48 file audits + 9 test audits), read in full.
Every item cites its swarm report. No MVP scoping — this is 100% of the work.
Work in milestone order; each milestone ends with the suite green and ruff clean.

---

## M1 — Purge dead weight & realign exports (owner rule: exports = engine exports)

**Deletions**
1. Enrichment subsystem (~350 lines): `src/services/enrich_service.py`; `main.py` import/:87, attrs/:120,:134-144,:162, spawn/:965-975, `_drain_enrich_queue`/:1181-1277, enqueue/:1408-1419, flusher blocks/:412-417,:438-449, clears/:1991,:2016,:2068, snapshot/:2184; `core/state.py` enrichments + `set_enrichment`; `results_screen.py` :387-390,:725-731,:749-753,:178-195,:818; `app_shell.py` :301,:391; `settings_screen.py` Enrichment card :1527-1551 + handler; `core/constants.py` STORAGE_ENRICHMENT_MODE. **KEEP** `core/enrich_view.py:36-144` (native extra path) — delete only `enrichment_summary` :147-149.
2. `report_service.py` dead 647 lines: reportlab/jinja2 import blocks :20-47, `_human_date_filter`/`_jinja_env` :50-63, identity/date keys :66-87, `_https_url` :108-116, HTML template+generator :249-402, email HTML :455-562, PDF :565-863, PDF-only imports. Rewrite docstring.
3. Export tiles: delete PDF tile `app_shell.py:519-526` + branch :290-311; delete HTML tile :551-558 + branch :368-408 (keep MD); delete email-HTML branch :74-84; drop "HTML" from email note :509-517.
4. `geo_utils.py` → replace with dependency-free `flag_for_alpha2()`; delete `resolve_location`, pycountry import, disk-cache layer; delete `cache_service.py:424-463` geo cache; fix consumers `result_card.py:20,333-336,564-572`, `profile_detail_dialog.py:15,780-781`, `sites_screen.py:487-492`; remove `pyproject.toml:57-58` pycountry cleanup rules.
5. `scan_notify.py` dead code: `_FakeBackend` :107-159, `request_permission` :444-452, `_dismiss_progress` :619-625, `available` :187-189, `PAYLOAD_ROUTE` :100; remove pyproject A002 ignore; fix :74 false comment.
6. Dead fields/keys: `state.is_loading`, `active_username`, `total_sites_checked`, `found_count`, `not_found_count`, `error_count`, `bulk_mode`; `STORAGE_BULK_MODE`; dead methods `reset_search` (or wire) + `set_enrichment`; `constants.py:103-105` empty header.
7. Dead cache layers in `cache_service.py`: compiled_db :123-231, sites_indices :466-527, dns_cache :530-694 (~260 lines); `_backup_corrupt` wire-or-delete; dead storage members `_last_write`, `get_all()`, `get_temp_dir()`.
8. Dead theme/tokens: theme.py `get_bg/get_surface/get_surface_2/get_border/get_text/get_text_dim/grey_dim/section_card/glass_card`, PADDING_*/RADIUS_SMALL/LARGE; tokens.py 28 unused tokens (see M3 tokens item); `_extractor`/`"photo"` in enrich_view; `get_scan_func_user`/`get_scan_func_phone` in compat; dead `no_nsfw` param :124; sherlock `:304-308` malformed conditionals, `_cancel_handle`, unreachable `:164` elif, `run_db_health` stub decide; `home_screen` `_run_hudson` :577-591, `hasattr(AppStyles,"brand_gradient")` :1490-1492, `user{?}name` placeholder :1156; `main.py:491-493` dead FilePicker attr; `update_service.action_url` decide; storage `get_temp_dir`; `notify` dead action branch decide.

**Export realignment (engine-first)**
9. Add `raw: Any = None` to `SiteResult` + `EmailResult`; set in both mappers (prerequisite for engine exports).
10. CSV tile → `user_scanner.core.formatter.into_csv(results)` (inherits `_neutralize_csv_cell` guard); JSON tile → `formatter.into_json(results)` replacing inline `app_shell.py:327-366`; keep TXT (add header line using `username`); keep MD slimmed (delete enrichment block :218-234, empty Time column, fix double-escape :230-234, "Platforms checked" metric, `<`/`>` escaping in `_md_cell`).
11. Fix `cache_service.py:418` sig drop (report cache 100% miss); stale pre-removal dossier cache invalidated.
12. `app_shell.py:421-424` add `file_type=CUSTOM` if filters wanted; drop redundant desktop rewrite :437-441; distinct export-failure messages (NEW-2).

**Config/manifest truth**
13. `constants.py:26,:29` URLs → `Nwokike/Sherlock` (404 verified otherwise); project description V2→V3.

---

## M2 — Scan engine correctness (the heart of the wrap)

**user_scanner_compat.py**
1. Cross-scan scope end-to-end: add `scope` computation (upstream `_scope` mirror), pass to `_named_targets` :492, sweep scoped set :475-485, add `selected` param, populate `CrossScanConfig.modules/categories` in both callers (fixes ~7,500-request sweeps).
2. 250-worker executor (module-level or `loop.set_default_executor`) replacing 8-thread default (:203,:282).
3. Cancel properly: keep task list; `t.cancel()` + `gather(return_exceptions=True)`; await as_completed coroutines; deterministic loop close.
4. Proxy reset: always call `set_proxy_manager`; `set_proxy_manager(None, None)` when empty; log instead of `pass`.
5. Emit `("skipped", ...)` for filtered/selected-out modules so progress reaches 100% (N-5); callers accept "error" too.
6. Cache module loads (restore lru semantics; ~2.2s → ~0s repeats); stop double-loading via upstream `find_module` (N-3).
7. `redirect_stdout` around upstream cross-scan prints :448,:457; route text to logger.
8. `set_global_timeout` inside adapter (N-4); unify the three tuple protocols into one event shape; heartbeat/on_start tick.

**sherlock_service.py**
9. Per-generation cancel token (kill K4 cross-generation race); propagate `is_cancelled=True` on returned progress (revive main.py watchdogs).
10. Catalog load off event loop + cache by `(mode, no_nsfw)`; guard first `on_progress` :178; remap confidence after cross-scan (N5); SKIPPED bucket + `is_visible(ScanConfig)` for show_all; stop publishing live-mutating progress (snapshot); namespace `state.target_results` writes per generation; adopt email rate regex for `_badge_for`.

**email_service.py**
11. Install `email_orchestrator` monkeypatch (or local re-impl) at scan start — 180/220 modules currently bypass proxy+timeout (C5).
12. `_domain_from` fix (no fabricated `.com`, lowercase, empty fallback).
13. Real cancel (worker loop + `_tasks` populated) or delete dead machinery; per-scan `threading.Event` (N4); drop global env proxy mutation or lock+refcount (N5); save/restore `set_global_timeout` (N6); surface worker exceptions (N7); SKIPPED ≠ unavailable; split rate-limit vs WAF buckets; populate/delete `method`+`frequent_rate_limit`.

**phone_service.py**
14. Add `rate_limited`/`unavailable` to `PhoneSearchProgress`; populate in `_on_result`; accept `("error",...)` tuples; route exists-first.
15. `PhoneResult` identity: `phone` (E.164), `domain` (host from url), `url_main`/`url_user` — fixes share crash, dedup, `"https://Social"`; use real URL on cards.
16. Plumbing: forward `region` (new state field + setting; reject/parse in service; `is_valid` warning), forward `proxy` via `phonsint.core.impersonate.set_global_proxy` (restore in finally), `set_global_timeout` same pattern, `phone_concurrency` instead of email_concurrency (main.py:1776), `allow_loud=state.allow_loud` or delete dead loud branch.
17. Shared rate regex (email's), snapshot final tick, clear `_progress`, real `is_available`, drop `*args/**kwargs` ctor, namespace phone catalog.

**main.py (engine wiring)**
18. Phone call site: region/concurrency/allow_loud/proxy from state (I-8).
19. Hudson: non-interactive (set `auto_hudson_preference(False)` once or call API directly), ANSI strip, structured results, no process-global `redirect_stdout`, distinguish declined/none/found.
20. Failure paths use `_owns_scan()` not target equality (N-8); per-scan Events (no `clear()` race); done-callbacks on `run_coroutine_threadsafe` futures (N-6).
21. Email-domains: batch write (`state.email_results[:] = rows`), counters describe union, surface cap "5 of N", validate scopes at commit (H4).
22. Result cache: per-key writes or off-loop dumps + shallow copy + restore through LRU cap (N-4/N-5/B-9).
23. `_load_saved_state`: table-driven; restore 6 missing keys + MODE_PHONE + `state.theme_mode`; per-key try/except; clamp restores.
24. Wire `on_platform_brightness_change` → bump rebuild lever; `state.theme_mode` single source.

---

## M3 — UI surface correctness (screen by screen)

**app_shell.py**: History badge live in isinstance branch (NEW-1); `on_dismiss` on export sheet (NEW-3); pass `banner=` to screens instead of Column wrapper (NEW-4, revives dead param); back/go_home distinct semantics (NEW-5); replace 4 swallowed chrome exceptions with logger.exception (NEW-6); `_share_urls` defensive + row-URL helper (NEW-8); empty-badge when 0 (NEW-9); export mode from progress object (NEW-16); parenthesize `username` expr (NEW-17); route interstitial via ControllerMethods (NEW-18); split `_build_appbar` into per-view builders; delete redundant progress touch (NEW-10); drop double close_dialog (NEW-14); phone-mode sheet wording (NEW-15).

**home_screen.py**: fix suggestion-filter precedence (B1); phone branch in `_run_hist` (B2); inert chips — wire (scan_depth→module cap, recursive→engine gate, ignore_exclusions→loader, phone_concurrency, allow_loud) or delete (B3/B4); bulk file: comma-join + per-segment validation + web message (B5); double-submit guard via `search_progress.is_running` (B6); separate UI-intent mode from scan identity (B7); chip selected no-op states (B8); remove bad `@ft.memo` (B9); paste normalization on `_on_paste` (B10); consolidate email helpers (B11); `_load_history` race (B12); redundant `progress_version` bumps (B14); UX: `ft.SegmentedButton`, `ft.AutoComplete`, inline validation, phone region dropdown + live validity, target chips, ActiveScanBanner on Home.

**results_screen.py**: capability-based progress reads (getattr defaults) + phone bucket mapping (K1/N1); real phone branch (N3); `TabBar.on_click` with `e.data` (K2); pooled footer banner (K3); phone card URL from `r.url` (K4); clamps (N5); mode-aware cancel (N2); memoize filter/sort or revision counter (N7); `item_extent`+`first_item_prototype` (N8); normalize rows once (N6); `context.page` guard (N11); fingerprint failure → never-equal (N18); `email_only_found` scope (N4); banner double-ownership (N9); banner_at default (N10); dead "Illegal" (N16); color consistency (N17).

**settings_screen.py**: pooled banners ×3 (H1); health guard via use_state (H2); manifest wire into load_sites or hide (H3); domain-scopes validate at commit + fix hint (H4); slider clamps on restore (M6); double-commit guard (M5); scoped dialog pops (M7); `control.update()` not `page.update()` (M8); dead rows (22) wired or deleted (H6-H8/M2); proxy-file rotation support or removal (M3); responsive layout via ResponsiveRow (M1); terminal as ListView (L2); log_count live (L3); copy-all vs 500 note (L4).

**sites_screen.py**: header-out-of-ListView restructure (restores filters reachability, kills dead scroll_to, unlocks `item_extent` virtualization for ~5,178 rows); reset `checked_states` on mode switch; unify `sites_tag_index` key convention service-side (category filtering broken for username/email); geo chips via flag_for_alpha2; remove dead country-key path :450-470.

**components**: banner_ad — never cache placeholder (B1), iOS unit + test id (B2), `not page.web` guard (B3), page-keyed pool + session-start clear (B5/B9), theme recolor-in-place (B6), drop dead hasattr/params (B4/B8), wire on_paid/on_impression (I2). notify — own open-snack state (kills BUG-1/2/3), ANSI strip + truncation centrally, luminance-derived text color, `persist=False` with actions. active_scan_banner — clamp ratio once, `bar_height`, `ft.ValueKey`, single handler, (structural: Component + own subscription). app_header — theme icon/logo update in place, page resolution from event, reactive version chip. update_dialog — double-open guard, failed-check state, inner width responsive, pop-after-check. profile_detail_dialog — falsiness fixes (`0` counts), un-drop company/occupation/is_verified, pass `others=` from results_screen:391, wire media, phone-mode labels, email dossier → enrichment_rows, lazy JSON, avatar single-fetch + cache update, pop-after-launch, URL validation, mobile overflow. result_card — feed `v2_media` into enrichment rows/merged profile, username-branch dynamic rows, `Skipped` case, hoist imports. empty_state — ICON_BACKDROP tokens. stat_card — digit-count ladder, None placeholder. targets_card — real/omitted total label, callback type, neutral zero-selection copy. history_screen — phone re-run branch, storage order fix on swipe-delete, undo persists, hydrate flushes UI + logs, stable Dismissible keys. onboarding_screen — dead fallback removal, persist-before-flag, idempotency guard.

**core**: state.py — collection lifecycle rule enforced (I2), settings/scan split + typed persistence table + round-trip test (I3/I10), observable progress dataclass + retire global progress_version bump (I8/I11), target_results off worker thread (I7), real LRU (I6), init all collections (I12), first_launch collapse (I14). theme.py — glass page resolution (B1), total is_dark_mode (B2), light snackbar (B3), AA contrast on_primary (B5), tokens adoption + divergent radius (B10/B9), idempotent apply (B11), system_overlay_style, hex-opacity verification (B4). tokens.py — ELEVATION family fix/annotate (B2), opacity rename (B5), STAT_NUMBER relocation, scale gaps, docstring truth, contract block + lint test. notify ANSI (see components). shared_services — mount-target assert (BUG-1), honest fallback (BUG-2), identity test (BUG-3), refcount doc (BUG-4), logger name. tasks.py — loop guard/binding, registry + cancel_all, `exc_info=exc`, `__qualname__` names, spawn_replace helper. use_debounce — sequence guard (B-1), context pin (B-2), deps fix (B-4), mount no-op skip (B-5). changelog — version-ordered nearest-≤ lookup + latest_release() + tests. format.py — shape-regex precision (B1), isascii/isdecimal guard (B2), one slash-date policy (B3), docstring + one-instant-one-string (B4), tz normalize (B5), ms/µs epochs (B6), count fixes (B7-B10). constants.py — URLs (M1), SEARCH_MODES vocabulary, storage-key lifecycle annotations, ad units consolidated + iOS/test ids, CACHED_RESULTS byte cap + co-located MAX_ENTRIES, USE_TEST_IDS rename. permute.py — reimplement on upstream `expand_patterns` (+ `count_patterns` gate, `islice` limit), pattern field in home gate + UI, "N of M" banner, limit setting, tests. enrich_view — date-hint in `_flatten`, raw value to human_date, in-module truncation, comma-joined links. actions.py — pre-check page instead of broad except. geo_utils (M1). logger_handler — engine stdout tee (owns capture), mute table re-derivation, delete dead filter path, file logging, verbose→DEBUG, telemetry fixes. app_state/controller_ctx — context default not a shared singleton, loud unwired defaults, 3 dead fields, AppStateCtx provider story.

---

## M4 — Persistence, notifications & platform plumbing

1. storage_service: `page.client_storage`/`session_id` removal — wire `ft.SharedPreferences` for web or drop web path honestly; `close()` on teardown + atexit; `_save_now` dirty guard; single ordered writer; asyncio.Lock for flush; corrupt-recovery uniform (read_text inside try, backup on any structural failure); schema version; normcase singleton key; tmp sweep; WinError narrowing + dir fsync; str→typed values decision; credentials/PII at rest warning.
2. cache_service: avatar SSRF guard (`is_safe_media_url` + redirect re-check + https-only); content-type/magic-byte validation; serve via bytes (B3); eviction/TTL + size budgets + startup sweep; engine version key `version`; geo trim direction (moot after M1) ; Windows backoff in `_write_atomic`; bounded JSON reads; cache-root memo.
3. http_client: collapse to single `_build()` (proxy=None explicit, timeout re-assert, proxy-leg retries restore, trust_env=False); retire-list instead of use-after-close; close on on_disconnect; docstring truth; retries UI copy.
4. update_service: `UpdateCheckResult` status contract (up_to_date vs error); build-number coercion; cooldown + seen-announcement persistence; host allowlist; case-insensitive scheme + control chars; ETag; explicit exception taxonomy; size cap; truncation marker; consistent fallbacks; tests.
5. ad_service: one-InterstitialAd invariant (no restock during display; identity release on close/error; failed preload released); `_can_request_ads=False` default; platform-unknown ≠ not-mobile; shutdown guard on show; iOS/test unit selection; close() releases ConsentManager + logs; identity-based removal; honest show outcome; restock out of finally; docs 1.0.4.
6. scan_notify: shrink to dependency-free tested seam (mode not is_email; generation token; teardown guard; inline-reply preserved; channel failure propagates; handlers in init(); C7/C12/C17 fixes); flet-notifications stays OUT of deps (roadmap).
7. logger_handler: install stdout tee (isatty False, ANSI strip, `("engine.stdout", ERROR)` in mute); re-derive mute table; RotatingFileHandler 1MB×3; verbose DEBUG; cpu_percent prime; battery None guard.

---

## M5 — Packaging, toolchain & metadata

1. pyproject: description V2→V3; add `[tool.ruff] target-version = "py314"` + `[tool.ruff.format]`; decide `docs/` exclusion for ruff format; restore owner-rationale comments in ignore list; pytest: remove or implement `asyncio` marker (pytest-asyncio absent — anyio plugin exists but decide one), add `filterwarnings` owner rule (module-scoped error filter), keep timeout=60; `[tool.flet.cleanup]` drop pycountry rules.
2. ruff: run `ruff format src tests`; `ruff check` stays green; add CI workflow (check + format --check + pytest -m "not live").
3. `.gitignore`: add `.pytest_cache/`, `.ruff_cache/`, `.flet/`.
4. Version: bump to 3.0.0 / build 14 across pyproject + constants + version.json; add CHANGELOG 3.0.0 entry (M1 test enforces); fix stale test counts in changelog copy.
5. README: write actual content (currently empty).
6. Mobile build decision (owner): cffi has NO Android wheel (uv.lock) → curl_cffi cannot import on Android APK; x86_64 has no wheel at all. Either (a) accept 110 silently-degraded modules with a visible "N sites unavailable on this device" surface (tolerant loader skip count → UI), or (b) vendor a cross-compiled cffi wheel. Document either way; surface module-skip counts in UI (compat B-8 observability).
7. version.json github_url already correct; UPDATE_CONFIG_URL fixed in M1 → verify end-to-end update check against the live repo.

---

## M6 — Tests to green, then to real coverage

1. Fix hanging `test_sherlock_search_returns_progress` (loads live catalog / hits network) — hermetic.
2. conftest.py: replace path-shim with autouse state-reset fixture (http_client, state singleton, StorageService._INSTANCES, proxy manager, spawned tasks); asyncio-marker guard; network block for non-live tests; warning filters.
3. New tests: all-modules offline import smoke; changelog (2 fail-today tests + APP_VERSION guard); permute (upstream-backed); format matrix (~60 inputs); phone contract (progress fields — fails today, drives M2.14); cross-scan scope (fails today — drives M2.1); hudson non-deadlock; proxy staleness; export CSV guard + engine formatter parity; storage disk-backed roundtrip + corrupt-JSON .bak + invalid UTF-8 + concurrent set + atomic guarantees; report cache sig roundtrip; app_shell `_safe_filename`/exports; banner/notify unit tests; update_service table.
4. Rework tautologies: test_services (3 is_available), test_services_all_modes (L44/L45/L56-58/L61-62/L66-67/L72), test_sites_catalog (2), test_phone_mode_parity (4 of 6), test_compat_loader (circular counts → exact 2,521/220/5, zero-skip invariant, iscoroutinefunction), test_storage_resilience (blind roundtrip).
5. Keep: 51 passing tests green throughout; suite time back under ~15s (drop 60s hang).

---

## M7 — Release engineering to publication

1. Full manual QA on desktop: username/email/phone scans (with cross-scan), all exports, history re-run all modes, settings persistence across restart (all 47 keys), proxy paths (http/socks5), theme flips (manual + OS), offline states, update check against live repo, ads on Android device (banner pool + interstitial + consent), notifications seam.
2. Android build: `flet build apk` arm64-v8a + x86_64 (jni override in place); verify ads APPLICATION_ID, permissions, cleartext setting; install + smoke on device/emulator.
3. Windows + Linux desktop builds (`flet build windows` / app + CI artifacts).
4. Tag + GitHub release on `Nwokike/Sherlock` with version.json pushed to `main` (update feed) and APK attached.
5. Play Store: bump build, upload AAB, release notes from version.json.
6. Post-release: monitor update-check hits; keep docs/reference alive (packages age).

---

**Execution order note:** M1 before M2 (dead code out → engine surgery on a smaller tree). M3 items are independent of M2 and can interleave per screen. M4 depends on M1/M3 touches of the same files. M5 partially parallel. M6 rides every milestone (each milestone ends green). M7 last.
