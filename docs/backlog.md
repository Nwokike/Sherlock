# Sherlock Audit Backlog (P0 → P3)

> **Date:** 2026-10-01 · Source: `docs/file-audit.md` (Track B) + `docs/dependency-study.md`
> §9–§10 (Track A). Ordered by severity, then by blast radius. Each item: file(s) +
> line refs. Gate after every batch: `pytest -q` (196) + `ruff check` + Android smoke.

---

## P0 — crashes / broken features / silent data loss (fix first)

### P0-A — Flet 1.0.1 API verification → OUTCOME (2026-10-01, Fix Batch 1)

Three read-only agents verified every disputed API against installed flet 1.0.1 /
flet-ads 1.0.1 source. **The app code was right; the auditors guessed from public
docs.** Items 1–7, 9–10 below are SETTLED (no rewrite); only the tab clamp (proven
`IndexError`) and the service-accumulation leak were real. Landed in Fix Batch 1:

| # | Original claim | Verification outcome (evidence) | Action taken |
|---|---|---|---|
| 1 | `show_dialog(SnackBar)` wrong, migrate to `page.open()` | **FALSE.** `SnackBar(DialogControl)` (`flet/controls/material/snack_bar.py:155`); `show_dialog(dialog: DialogControl)` (`base_page.py:402`); no `page.open/close` exists in 1.0.1 | Kept; hardened with explicit `ft.Duration` + skip re-show when top dialog is a real AlertDialog |
| 2 | `ft.UrlLauncher()` detached = no-op, use `page.launch_url` | **FALSE.** `UrlLauncher(Service)` + async `launch_url` (`services/url_launcher.py:67`); auto-registers via `context.page` (`services/service.py:39-54`); no `page.launch_url` exists | Kept; routed through shared mounted instance |
| 3 | `use_effect(cleanup=)` hallucinated | **FALSE.** Explicit `cleanup` param (`components/hooks/use_effect.py:42`) | Kept as-is |
| 4 | `Animation(..., "easeOut")` string crashes | **Risk only.** Field typed `AnimationCurve` but deserializer coerces enum values | Hardened to `AnimationCurve.EASE_OUT` (2 sites) |
| 5 | `BannerAd(width/height)` wrong, needs `AdSize` | **FALSE.** `BannerAd(LayoutControl, BaseAd)` — `width/height` valid; `AdSize` exists nowhere in `flet_ads/` | Kept; fixed inaccurate comment only |
| 6 | `page.platform.is_mobile()` hallucinated | **FALSE.** `PagePlatform.is_mobile()` exists (`controls/types.py:843`) | Kept; `hasattr` guards stay as forward-compat |
| 7 | `flet.context.page` missing | **FALSE.** Singleton `context` (`controls/context.py:239`) | Kept as-is |
| 8 | Detached `Clipboard/HapticFeedback` = no-op | **Works BUT leaks.** Each construction appends + pushes a wire update (no dedup in `register_service`) | **Fixed:** `core/shared_services.py` mounts once in `AppController.init`, 22 call sites reuse |
| 9 | `use_dialog(dlg)` / `open_sheet(AlertDialog)` wrong | **FALSE.** `use_dialog(dialog)` verified (`components/hooks/use_dialog.py:52`) | Kept as-is |
| 10 | `page.services` vs overlay, `Connectivity` names, `SHOW`, `window`, `page.render`, `Tab(label=)`, Switch/Scrollbar/Divider props | **ALL VERIFIED-EXISTS** (`services/connectivity.py`, `controls/types.py:1106`, `controls/page.py`, `material/tabs.py:607`) | Kept as-is |
| ★ | NEW: `selected_index=3, length=3` raises `IndexError` (no clamp in `Tabs.before_update`, `material/tabs.py:263-269`) | **PROVEN CRASH** on email→username tab carryover | **Fixed:** `clamp_tab_index()` + regression test |

### P0-B — logic bugs (data loss / wrong results)

| # | Item | Files |
|---|---|---|
| 11 | Username stale-tick guard + `target_clean` everywhere + orphaned enrich tasks — **FIXED Batch 2b** (identity check, `target_clean`, generation counter) | `main.py:543-653/812-818` |
| 12 | Orphaned enrichment tasks contaminate next scan — **FIXED Batch 2b** (generation counter) | `main.py:158-161/592-595/689-743` |
| 13 | Email export unreachable (always show Export, filter by mode) — **FIXED Batch 2a** | `app_shell.py:907-926` |
| 14 | Results tab-index clamp + stats-zeroing + memo deps — **FIXED Batch 1+2a** (clamp, shown_* separation, content fingerprints) | `screens/results_screen.py:170/322-326/373-389/526-545` |
| 15 | `state.reset_search` sets `is_online=True` — remove; nil-guard clears — **FIXED Batch 2a** (test updated to assert preservation) | `core/state.py` (+ fix `tests/test_state.py:43-51` which encodes the bug) |
| 16 | Geo flush never fires twice (`or _GEO_FLUSH_DIRTY`) — **FIXED Batch 2a** (flag-only fix; `flag`/`-`-split/`uk` claims REFUTED, no change) | `core/geo_utils.py` |
| 17 | Changelog inverted fallback (`reversed` → oldest) — **FIXED Batch 2a** | `core/changelog.py` |
| 18 | `url_main`/`http_status` always empty in SiteResult — **FIXED Batch 2b** (`url_main` from `site_obj`, best-effort `http_status`; no maigret fork) | `services/sherlock_service.py:262-264/297-302` |
| 19 | Primary-target exception aborts multi-target scan (continue like secondaries) — **FIXED Batch 2b** | `services/sherlock_service.py:538-543` |
| 20 | `search()` skips reload on config change — **FIXED Batch 2b** (unconditional `load_sites()`, early-return covers) | `services/sherlock_service.py:836-837` |
| 21 | Dead cancel primitives (`asyncio.Event`, `_search_task`) + cancel-between-targets-only — **FIXED Batch 2b** (deleted dead paths, documented boundary-only, fixed annotation) | `services/sherlock_service.py` §10 items 1/5 |
| 22 | Impersonate wrapper drops `**kwargs` (all impersonate modules degrade) — **FIXED Batch 2b** (passthrough) | `services/email_service.py:94-109` |
| 23 | `others` shape mismatch (`error` vs `extra/media` keys) — **FIXED Batch 2b** (unified + alias) | `services/email_service.py:229-234/263-271` |
| 24 | Overlapping scans corrupt state (guard `is_running`) — **FIXED Batch 2b** (`RuntimeError` guard) | `services/email_service.py:408-409/433/507` |
| 25 | `EMAIL_FORMAT` allows `\|` in TLD — **FIXED Batch 2b** | `services/email_service.py:140` |
| 26 | Home: no active-scan guard + history bypasses offline/email gates — **FIXED Batch 2a** (shared `_submit_guards` + button disable) | `screens/home_screen.py:513-547/579-601` |
| 27 | `status_color` undefined fallback + `json.dumps` without `default=str` — **FIXED Batch 2a** (hoisted + `default=str`/truncate; `action=` VERIFIED-EXISTS, kept) | `components/profile_detail_dialog.py:484-490/740/369-380` |
| 28 | ResultCard click ignores `url_main` + clickable-no-handler + falsy-`or` numerics — **FIXED Batch 2a** (url fallback, inert without handler, `_first_present`, isinstance guards) | `components/result_card.py:107-111/570-575/292-293` |
| 29 | Report: `datetime.UTC` <3.11 crash (REFUTED — floor is 3.14) + Paragraph XML injection + XMind key collision — **FIXED Batch 2b** (escape ×3, URL keys) | `services/report_service.py:12/539/631/645/758/792/824` |
| 30 | Sites: full 5,200-control rebuild + typing-lag — **FIXED Batch 6** (memos + isolated search bar + item_extent) | `screens/sites_screen.py:78-79/195-244/271-292` |
| 31 | Storage debounce lost-write race + web/client_storage branch + corrupt-file wipe + no close-flush — **FIXED Batch 2b** (reorder + `close()` + backup + explicit detection) | `services/storage_service.py:65-80/82-92/121-137` |
| 32 | Cache shared-tmp race + unhashed pickle + dead-DNS immortal — **FIXED Batch 2b** (mkstemp + payload hash + 1h dead TTL; test updated to new behavior) | `services/cache_service.py:73-79/150/402-413` |
| 33 | Graph analytics schema inconsistency + phone.strip crash — **FIXED Batch 2b** (schema keys + isinstance guards) | `services/graph_service.py:183/230-238` |
| 34 | Biometric: Linux/Web permanently locked (REFUTED — explicit `return True` paths) | `services/biometric_service.py:71-78` |
| 35 | `open_cached_result` enrichment leak + email counters unrestored (test asserts merge-only) — **FIXED Batch 3** (clear-first, 4-bucket restore, re-attach, context save) | `main.py:1168/1179`, `tests/test_cached_results_and_reattach.py:84` |
| 36 | Tests patch dead code (`httpx.AsyncClient` vs `get_client()`) — cache/update tests hit real net — **FIXED Batch 3** (rewired to `get_client` stubs, hermetic) | `tests/test_cache_service.py:209/228`, `tests/test_update_service.py:70/94/118/138/149` |

---

## P1 — correctness gaps / silent failures / flaky tests (fix second)

- Sherlock (**FIXED Batch 2b:** WAF/rate substring fallback,
  ILLEGAL→Skipped→errors, dead cancel primitives removed, boundary-only documented;
  **FIXED Batch 12:** per-target `after_primary` id + recording wrapper (last-target
  contract documented), `alive_bar` guard, loop save/restore, max_conns/timeout/
  retries clamps, conditional containers, `_resolve_local_db` atomic+cache-tier+
  correct pkg name + single synced-check, pickle-raise fallback, `_maigret_kwargs`
  filter, `run_db_health` clamp/cancel/typed, cancel-mark helper, `on_progress`
  debug log, dead import removed, SCAN_ALL, cross-thread snapshot note):
  `on_progress` thread-safety note.
- Email (**FIXED Batch 8:** progress snapshot isolation; `cancel()` live-guard;
  outer-cancel link; `_FINGERPRINT` → ContextVar; semaphore floor 1;
  `frequent_rate_limit` broad-throttle flag; `_RATE_LIMITED_RE` gaps;
  `_first` int passthrough; `use_stealth_fingerprint` + alias kept;
  `Lock()` pre-loop REFUTED on 3.14; **FIXED Batch 13:** `total_modules` → 0 +
  warning (no 181 drift), proxy env-race doc-note; `TimeoutError` alias,
  `core.constants` root, `chrome131_android` all REFUTED-verified):
- Main (**FIXED Batch 7a:** gate-before-kill reorder; flusher cancel-on-completion;
  `call_soon_threadsafe` bridge + threadsafe cancel helper; storage per-field
  guards; `on_error` getattr + connectivity guard; `_on_close` suppress; cached
  email enrich-clear + gen-bump; history `asyncio.Lock`; avatar cap 50):
  async-cancel verify; LIGHT default; open_cached holes; snapshot `context`.
- AppShell (**FIXED Batch 7a:** copy/share empty + truncation snacks; restart
  state-first; banner explicit per-mode + isinstance): onboarding
  dep; render-phase controller mutation; double-setter flash; chrome sync; back divergence;
  `_system_back` wiring; dialog/sheet responsiveness; tooltips; tuple lambdas; magic 5203.
- Results: re-render split; scroll preservation; item_extent; slot reuse; filter index;
  email filter keys; username empty parity; skeleton; `checked=total` mask.
- Home: empty-input snack; username-shape validation; `@` vs `validate_email`; paste-only
  switch; suggestion filter; clear button; chip `on_select`; chip-row alignment; memo
  lambdas; dead code; `full_screen`; `ink` without handler; enum style; persist helper;
  stale query on switch.
- Settings (**FIXED Batch 5:** clamp-persist, slider range, `_set_nsfw` single
  writer + home dual-key persist, manifest de-keystroke, proxy/i2p/cookies/manifest
  validation, `or ""` defaults, slider live/commit split, health-check guard+disable,
  terminal display cap, `page is None` guards; `narrow` resize documented wont-fix):
  flush in `_persist`; persist wrapper; theme typing; switch colors; manifest header drift.
- History: persistence key+flush+encoding; Dismissible `key` + `secondary_background` +
  Undo; rebuild notification; corrupt guard; swipe-clear race; locked-hydrate skip;
  empty-query snack; found/total coerce; timestamp format; query ellipsis; body Unlock CTA.
- Sites (**FIXED Batch 6:** memoized names/tags/buckets/filter, isolated search
  bar, `item_extent` + fixed rows, checkbox keyboard + double-fire guard,
  debounced persist, live chips + counts + countries, tag-aware search, empty-DB
  state, twitter/x dedupe, filtered count, notify debug log).
- Report (**FIXED Batch 17:** shared Jinja CSS base `_DOSSIER_CSS_CORE`;
  **FIXED Batch 3:**
  md/email table injection, `javascript:` scheme via `_https_url`;
  **FIXED Batch 14:** PDF 500-row cap + overflow, empty-contract docstrings +
  email-md None alignment, palette lazy guard, XMind single-add, note value
  truncation, tags str, avatar `_https_url`, PDF title newlines, hoisted
  datetime imports, WinAnsi doc-note).
- Enrich (**FIXED Batch 4:** deadlock clamp, mutation-wins + provenance, off-loop
  extract, async `on_result`, dedupe, timeout clamp, outer `wait_for`, per-host
  throttle+retry, headers/cookies/UA forwarding, skip flag; cookies+UA wired in
  main drain; tests hermetic; **FIXED Batch 13:** 3xx tighten (<300),
  login-wall distinct debug log):
- Storage (**FIXED Batch 11:** absent-delete/clear noops, `clear()`/`get_all()`,
  snapshot-write outside lock with unchanged-guard, `set()` TypeError +
  loader sanitize, unconditional trim, non-dict load filter).
- Cache (**FIXED Batch 14:** index hash gate + single-build wiring, prewarm
  skip-fresh, fingerprint dict/empty handling, pycountry fallback + trim):
  tmp dotfiles immortal; report template version; avatar unbounded; low nits batch.
- Graph (**FIXED Batch 10:** GraphML/GEXF, PageRank + closeness, physics/kinds;
  **FIXED Batch 14:** strip+lower ids with original-case labels, `_field()`
  dict support, unique acc ids, no `.title()` mangling, cypher newline/backtick
  escaping, dedented email edge, real type hints, sorted communities;
  **FIXED Batch 17:** select/filter menus + reason-colored edges):
  single-node centrality; link truncation +
  scheme; Unknown collapse (mitigated: unique ids).
- Ad: preload-overwrite leak; failed-load cleanup; iOS unit ID; `_handle_close` guard;
  fresh-`show()` Future swallow; append outside try; double-consent guard; `is` vs `in`;
  docstring version.
- Biometric (**FIXED Batch 7b:** auth lock, 60s timeout, `authenticate_detailed()`
  + categorized history UX, reason strip, PIN-fallback doc; ads untouched per
  owner; **FIXED Batch 17:** auth tiers — capability label, stop_prompt,
  biometric_only/sensitive params, persist_across_backgrounding, strict toggle,
  resume re-lock): code-normalization; enrolled types helper.
- Update: announcement-vs-build gate (keep-gated policy documented);
  bool-is-int; float build; TTL cache; sig key (**FIXED Batch 3:** `mandatory is True`,
  URL scheme validation, type allowlist, free-text isinstance + caps).
- Tests: FakePage platform/storage/width/brightness/lifecycle + awaiting run_task;
  flet_tree appbar/actions/dialog traversal + ElevatedButton/str/Row labels; maigret cancel
  + http_status + impersonate-kwarg tests; MagicMock→real results; `>4000`→registry
  length; state restore fixtures; `monkeypatch` fixture; missing-dep skips; network mocks;
  exact stat-card asserts; state reset per test; dialog handler invocation; loader-order +
  enrichment-clear + upsert tests; flusher isolation; `wait_for`/Event streaming tests.

---

## P2 — utilization upgrades (fix third, highest value first)

1. Report filename safety — **FIXED Batch 9** (stdlib `_safe_filename`, no new dep).
2. History relative times — **FIXED Batch 9** (stdlib `_relative_time`, no new dep;
   enrichment date parsing still open).
3. QR codes in PDF + profile dialog (device handoff) — `qrcode`.
4. Avatar thumbnails at download (cache size + PDF speed) — `pillow`.
5. `Timeout` + `http2=True` + `retries=state.retries` + streaming avatars — **FIXED Batch 9**
   (client Timeout, explicit transports + proxy mounts, rebuild key, 5MB streaming cap).
6. Fingerprint rotation + session reuse + bot-retry + `CurlFollow.SAFE` — `curl-cffi`.
7. Render/export holehe `extra`/`media` (**FIXED Batch 10:** card identity rows,
   email report bio/login/avatar, graph linked-identity edges, holehe→Maigret
   recursive pivot); widen recovery/phone; SSO badges; single-module re-check;
   429 backoff; UA rotation.
8. Full tag/country/engine filter UI; non-username id search (**FIXED Batch 10:**
   native CSV/TXT/NDJSON writers + app_shell rewire, cypher via own graph export,
   DB-update check action); Tor + CF-bypass + activation cache; Permute;
   error analytics; DB stats header + paste-URL detect.
9. Socid pivot actions (**FIXED Batch 10:** dialog Pivot buttons + results-screen
   re-search wiring) + 2nd-hop mutations (**FIXED Batch 10:** max_depth frontier);
   cookies forwarding; relevance precheck + rich dossier tail + Gravatar-hash
   matching + custom schemes + full exports.
10. Flet: Banner/SnackBarAction/Shimmer/AnimatedSwitcher/SelectionArea/client-action
    buttons/ContextMenu/ResponsiveRow/Drawer/Router/AutoComplete/DataTable/Hero/
    Screenshot/Wakelock/StoragePaths/KeyboardListener/extended themes/use_memo.
11. Ads: AdRequest targeting; consent row; frequency cap; retry+collapse; lifecycle events;
    responsive size; NativeAd pilot; iOS IDs; consent probes; interstitial-gated exports.
12. Auth (**FIXED Batch 17:** `capability_label()`, `stop_prompt()`,
    `authenticate_detailed(biometric_only, sensitive)` with
    `persist_across_backgrounding=True` + branded messages, `biometric_strict`
    state/storage/settings toggle + capability subtitle, history
    `sensitive=False`, re-lock on resume, history unmount cleanup):
    error-code UX; remaining: biometric_only toggle.
13. Enrich: auth/cookies/proxy params; skip-if-no-hint (**FIXED Batch 10:** 2nd-hop
    max_depth frontier); anyio task groups + cancel scopes; per-host throttle.
14. Graph (**FIXED Batch 10:** GraphML/GEXF export, PageRank + closeness, physics
    toggle + kind filter; **FIXED Batch 17:** select/filter menus on,
    reason-colored edges [member -> dark gold]); member sorting.
15. Reports: caps/escaping/scheme validation (P1.5-8 are P1, rest P2);
    **FIXED Batch 17:** shared Jinja CSS base (`_DOSSIER_CSS_CORE`);
    custom filters; chart/QR additions.
16. Build config (**FIXED Batch 17:** `[tool.flet]`
    description/company/copyright/icon; ruff `RUF` in select with RUF100/RUF007/
    RUF012 handled; 80-site `asyncio.create_task` -> tracked `spawn()`
    (`core/tasks.py`); `[tool.flet.icons]` + splash wiring;
    ruff `S,TRY,BLE,EM,RUF,A` (+`SIM,RET,RSE`); pytest `timeout=60`;
    pytest-asyncio; `USE_TEST_IDS` + debug geography hooks.

---

## P3 — polish / defer

- **FIXED Batch 18:** `format_count` compact formatter (`core/format.py`, wired into
  TargetsCard); `SectionHeader` auto-uppercase; tokens `__all__`; `update_dialog`
  close-failure logs downgraded to debug; graph export `str | Path`/`set[str]` params;
  final 4 `create_task` sites -> tracked `spawn()` (debounce, enrich gather, storage
  flush, sites persist, holehe bounded); EmptyState handler-less label warning.
  Verified already-done: `targets_card` `Callable`, `stat_card` value typing, theme
  tokens import, `actions` widen + URL guard, logger deque lock, `notify` action
  support, `http_client` timeout default, controller named noops, geo LRU + defs,
  storage `_last_write` + fsync, email regex long tail, report CSV/TXT writers.
  Declined: ad `TimeoutError` mapping (owner ad freeze); storage schema version
  (migration risk); `notify` instance reuse (per-call args vary); watchdog hot-reload
  + rich CLI (friction-gated, no friction felt).
- **FIXED Batch 20 (completion sweep):** permute (`core/permute.py`, capped
  separator swaps, off-by-default toggle + `STORAGE_PERMUTE` persist/hydrate,
  engine multi-target expansion, completion merge over `target_results` with
  Claimed-preferred collision handling); `human_date` (`core/format.py`, ISO /
  unix / month / year precision, None on unparseable) wired into cards,
  profile dialog, and all three report renderers via `_fmt_ident`; shared
  Jinja environment (`_jinja_env()`) with a `human_date` filter actually used
  by the HTML dossier; paste-URL handle extraction in the home submit path
  (`_normalize_pasted_query`, module-level, decorator-safe); email 429
  single-retry backoff (`_RATE_RETRY_DELAY_SEC`, cancel-aware); Gravatar
  fallback avatars (md5 = Gravatar's contract, noqa-documented); test-id
  automation hook (`USE_TEST_IDS`/`test_id`, off by default, wired to
  home/sites/history anchors); sites DB stats header; ruff widened to
  `S,TRY,BLE,EM,A,SIM,RET,RSE` with documented ignore list (message-string
  style, wide-except-and-log, style reshuffles) and per-file `S101` for
  tests; pytest `timeout=60`; `[tool.flet.android] adaptive_icon_background`.
  Post-swarm verification (4 independent agents): UI/API hallucination scan
  clean, engines audit clean except a P2 (jinja2/transitive deps), test/config
  audit found fixture under-coverage in 5 files (fixed) + one vacuous test
  (fixed) + stale version identifiers (bumped to 2.3.0/build 13).
- **FIXED Batch 19 (test hardening):** real `EmailService.cancel()` race -
  liveness evaluated AFTER the loop-wakeup GIL handoff, so a cancel landing
  on a live scan usually failed to mark it (~1/6 marked before; 8/8 after).
  Fix snapshots liveness BEFORE `call_soon_threadsafe`; stale-scan guard
  semantics preserved. Order-dependence hunt (reverse-order suite run found
  2 failures): stale `current_username` (offline fixture now resets on
  setup too), cross-mode tick drops from leaked `search_mode=EMAIL`
  (batch_3/7a cached-result tests now restore state), alice-username leaks
  (polish + cached_results files now snapshot/restore). Rule learned:
  `state.__dict__` surgery is incompatible with @ft.observable (wipes
  wrapper internals) - restore via setattr + in-place collection ops.
  Live network test passes; suite green forward AND reverse.
- **Do NOT do:** platformdirs in storage_service (breaks Flet sandbox); oauthlib login
  flow (no product need); aiohttp second stack; BS4 parsing outside socid; Tor return;
  `run_all()` / `export_json` adoption; rewarding without SDK support.
