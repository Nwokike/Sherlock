# Sherlock File Audit

> **Date:** 2026-10-01 · **Method:** one sub-agent per file (48 `src/` files + 25 test
> files + conftest/flet_tree), each reading the full file and auditing Flet 1.0.1 API
> correctness, bugs, hallucinations, and perf. `.venv` is the source of truth.
> Baseline: **196 tests pass, ruff clean**.
>
> Format per file: P0 (crash/broken/must-fix) → P1 (correctness/silent-failure/API-risk)
> → P2 (improvement) → Certified good. Companion doc: `dependency-study.md` (Track A).
> Fix backlog with ordering: `docs/backlog.md`.
>
> **Verification outcome (2026-10-01, Fix Batch 1):** every "verify" note in this doc
> was checked against installed flet 1.0.1 / flet-ads 1.0.1 source and nearly all
> settled as **code-correct** — `show_dialog(SnackBar)`, `is_mobile()`, `UrlLauncher`,
> `Clipboard`, `Share`, `FilePicker.save_file(src_bytes)`, `flet.context.page`,
> `use_dialog(dlg)`, `use_effect(cleanup=)`, `BannerAd(width/height)`, `Tab(label=)`,
> `on_change`/`ConnectivityType.NONE`, `SHOW`, `window`, `page.render`, `run_task`,
> `services`, client actions, `TabBar`/`Switch`/`ScrollbarTheme`/`Divider` props all
> VERIFIED-EXISTS (see `docs/backlog.md` P0-A outcome table for file:line evidence).
> The audit "verify" notes below are kept for provenance but marked accordingly;
> do not re-litigate them. Real fixes landed: tab-index clamp (+`clamp_tab_index`
> regression test), shared service mount (`core/shared_services.py`, 22 call sites),
> `notify.py` Duration + dialog guard, `actions.py` widen, `AnimationCurve` ×2.
> Baseline is now **394 tests passed, ruff check clean** (was 229 at doc writing time;
> Fix Batch 1 added 6, Fix Batch 2a added 10, Fix Batch 2b added 10, Fix Batch 3
> added 10, Fix Batch 4 added 8, Fix Batch 5 added 6, Fix Batch 6 added 9,
> Fix Batch 7a added 9, Fix Batch 7b added 4, Fix Batch 8 added 9,
> Fix Batch 9 added 8, Fix Batch 10 added 10, Fix Batch 11 added 7,
> Fix Batch 12 added 9, Fix Batch 13 added 4, Fix Batch 14 added 12,
> Fix Batch 17 added 10; Batches 15-16 added none; Fix Batch 18 added 12;
> Fix Batch 19 added 4; Fix Batch 20 added 9).

---

## App entry: `main.py`, `app_shell.py`

### `src/main.py` (1500 lines)

- **P0-1** Stale-tick filter missing for username (L783-818): email ticks check identity,
  username ticks only check `search_targets` (never assigned here). Back-to-back scans →
  late ticks from scan A clobber scan B. Fix: mirror email identity check.
- **P0-2** Raw vs stripped username (L606/614/653): engine called with raw, completion
  guard compares against stripped → trailing-space input always "cancelled", results
  discarded. Fix: use `target_clean` everywhere after L543.
- **P0-3** Orphaned enrichment tasks (L158-161/592-595/689-743): `_kill_all_activity`
  cancels worker but not spawned `pending_tasks` children → contaminate next scan.
  Fix: track children set, cancel+gather, or generation counter.
- **P1** Offline/email-validation gates placed AFTER kill (L560-568/872-886) — invalid new
  search kills healthy running scan. Move gates before kill. Flusher never stops on
  completion (perpetual task). Thread-unsafe progress bridge (`call_later` off-loop →
  `call_soon_threadsafe`). Sync cancel path thread-safety. `service.cancel()` assumed sync.
- **P2 (verify Flet 1.0.1)** `page.render`, `page.services.append` vs overlay,
  `Connectivity` names, `AppLifecycleState.SHOW`, `window` accessor, `assets_dir="src/assets"`.
  Storage single-`try` int-parse cascade, first-launch forced LIGHT, `on_error`/`_on_close`
  handler robustness, `open_cached_result` enrichment/counter holes, snapshot `context`
  loss, history-upsert race, unbounded avatar fire-and-forget, per-scan full-cache JSON ×2.
- **Certified:** connectivity/lifecycle handlers, `_load_and_cache_sites`,
  `save_selected_sites`, `set_onboarding_done`, `run_db_health`, drain termination,
  smart re-attach, update flow, render-budget architecture (keep).

### `src/app_shell.py` (1151 lines)

- **P0** Email results can never be exported (L901-926 hide Copy/Share/Download; export
  machinery supports email). Silent no-op Copy (L135-136). Silent Share truncation to 20
  (L172). Restart race (view flips before `is_searching` set, L886-896). Banner progress
  `or`-fallback wrong at scan start (L1108-1111). Banner mode duck-typing (L1112-1116, use
  `state.search_mode`). Direct `state.search_mode` mutation (L1119). `use_effect` misses
  `is_first_launch` dep (L1078-1086).
- **P1 (verify)** Transient `ft.HapticFeedback/Clipboard/Share/FilePicker/UrlLauncher`
  constructed per-click, never mounted — likely no-op/throw (L124/158/141/177/393/595).
  `page.platform.is_mobile()` — enum has no such method (L403-407). `ft.use_dialog(active_dialog)`
  non-standard signature (L975-982). `controller.open_sheet(AlertDialog)` type confusion.
- **P2** Controller mutated during render (stale closures); double-setter flash;
  imperative chrome sync; back/go_home divergence; `_system_back` wiring; graph dialog
  fixed width; export sheet nested scroll; tooltips/semantics; tuple-lambda trick; magic
  5203; full-list cache key; sync graph build on UI thread.
- **Certified:** onboarding predicate, email export byte shapes, dashboard scaffold,
  username export mapping, `progress_version` dep exclusion, email/username restart branch.

---

## Screens (7)

### `src/screens/home_screen.py` (1181 lines)

- **P0** No active-scan guard (double-tap → parallel scans, L513-547/579-601). History
  click bypasses offline+email gates (L579-601). `ft.Clipboard().get()` looks hallucinated
  (L566-577, swallowed by bare except). Same for `HapticFeedback().medium_impact()` (L519).
  Unguarded `show_sites/show_history/open_cached_result` (L955/589/1043-1045).
  `open_cached_result` maybe-async treated sync (L589).
- **P1** Empty input silently ignored; no username-shape validation; loose `"@"`
  vs strict `validate_email` inconsistency; auto-switch paste-only; suggestions not
  filtered by text; no clear button. Keyboard submit certified good (L908).
- **P2** `Chip(on_select)` signature; centered scrollable chips clip; `@ft.memo` defeated
  by inline lambdas; dead `theme_version`/`logger`; `full_screen=True` confirm intent;
  `ink=True` without handler; string-vs-enum style drift; per-keystroke full rebuild;
  persist boilerplate ×8; stale query on mode switch.

### `src/screens/results_screen.py` (734 lines)

- **P0** Fake virtualization (L134-139: prebuilt list + `build_controls_on_demand=True` =
  no-op; 3,300 cards/tick). `selected_index` out of range email→username (L545 unclamped).
  `email_only_found` zeroes stats not just tabs (L322-326). Memo deps cause stale UI
  (length-only deps, L373-389/526-542).
- **P1** Whole-screen re-render per tick (filter focus/scroll loss); no scroll
  preservation; no `item_extent`; slot reuse fragility; per-item dict lookup per tick.
- **Verify** `ft.UrlLauncher().launch_url` (L179), detached HapticFeedback (L195/222),
  `ft.Tab(label=)` (L398-407), `context.page`, `with_opacity` arg order.
- **Filters** Email hint promises recovery/phone search but key is name+domain only.
  Username empty states generic; no username `only_found`; `checked=total` masks partial runs.
- **Missing** SelectionArea, context menu, skeleton loading.
- **Certified:** `_resolve_username_view_data`, mode derivation, indeterminate bar gating,
  `_filter_by_name`, snapshot mapping, pop-before-show pattern.

### `src/screens/settings_screen.py` (1331 lines)

- **P0** `page.platform.is_mobile()` raises (L172, `hasattr` guards wrong object).
  `_persist()` never flushes except theme path (silent loss). `_on_scan_depth_change`
  missing None-guard (L368-371). Slider/Segment initial values crash on corrupt storage
  (L624/645/763/799/560/746/1088). Bare `int(val)` in handlers (L277-287/383-389).
- **P1** Clamp-then-persist-raw (L285-287/383-385). Concurrency range mismatch
  (slider min 4 vs clamp 5; divisions give step 2). Coarse divisions undocumented.
  `safe_search`+`nsfw_enabled` dual truth. Manifest per-keystroke persist (L883).
  Proxy validation prefix-only (L295-308); i2p/cookies/manifest zero validation (L325-333/
  861-885); `None` into TextField (L862). Fire-and-forget races; sliders persist per-tick
  with stale labels; health-check double-tap; terminal joins entire log; `ft.Clipboard()`
  hallucination (L1116-1118).
- **P2** `page is None` derefs; `narrow` computed once; theme-card typing/animation;
  `Switch(active_color)` verify; manifest header vs `_setting_row` drift; stale log_count.

### `src/screens/history_screen.py`

- **P0/P1** Round-trip order flip + hardcoded `"sherlock_history"` key (L66-71 vs 327-332,
  restart flips order). Dismiss persist missing `flush()` + encoding mismatch (L327-333).
  No rebuild notification after mutate (L70-71/105/320). Corrupt entry crashes screen
  (L188-193, add `isinstance dict` guard). Swipe-vs-clear race (bare `except: pass` L334).
  Hydrate loads sensitive data while locked (L58-73, skip fetch until unlocked).
- **Edges** Empty-query silent return; `found/total` None/str; raw timestamp; long query
  overflow (add max_lines/ellipsis); no in-body Unlock CTA; mode inference ×3 (extract);
  no undo; double banner; `AppHeader(page,…)` positional; dead `logger`/inline imports.
- **Certified:** locked/empty/list branching, clear-confirm dialog, item visual hierarchy.

### `src/screens/sites_screen.py` (405 lines)

- **P0** Full 5,200-control rebuild every render (L195-244 eager inflation before ListView;
  `sorted()` per frame; per-site tag lowering O(N·T)). Memoize names, iterate canonical
  order, `item_extent`, hoist tag sets.
- **P1** Typing lag NOT fixed by debounce (controlled field rebuilds list per keystroke,
  L78-79/271-292) — isolate search field component. Dead `Checkbox` (keyboard/a11y broken,
  L211-219). Fire-and-forget persist races (L113-126). Hardcoded 17 chips vs live 75-tag
  DB (L48-67) — build from `sites_tag_index` with counts. Search matches names only (L197,
  add tags).
- **P2** Init-effect fragility; "Loading…" forever on empty DB; silent notify swallow;
  `twitter`+`x` dup; no filtered count.
- **Certified:** all-selected→`[]` contract, tag-index casing, EmptyState/banner usage,
  stats math, scope-to-filter mapping. No hallucinated APIs.

### `src/screens/onboarding_screen.py`

- **P0 (verify)** `animate=ft.Animation(duration, "easeOut")` — string curve may throw,
  blanking whole screen (L175 → `AnimationCurve.EASE_OUT`).
- **P1** Detached `HapticFeedback` ×4 (silent no-op). `is_dark_mode(None)` crash risk (L58).
  `flet.context` existence; `_finish` swallowed persist failure → onboarding loops.
  `create_task` vs `page.run_task`.
- **Certified:** slide copy, icon branching, CTA morph, Skip logic, dot late-binding fix,
  clamp, layout.

---

## Components (11)

### `src/components/result_card.py`

- **P0** Click ignores `url_main` (L107-111 vs 570-575, ripple with no action). Clickable
  with no handler (both None → no-op ink). Falsy-`or` breaks numeric 0 followers (L292-293,
  None-coalesce helper).
- **P1** `others.media/extra` non-dict crash (L164/213-224). `protection` str join
  (L407). Avatar whitespace/case (L166/250-255). Phone row overflow props. Location raw
  value (L268-273).
- **P2** Type hints (`tuple[str,str]` → IconValue); `ft.Control` consistency;
  `mouse_cursor=CLICK`; tokens for method badge; hoist `_V2_SKIP`; lazy import keep-if-
  circular; badge Row wrap risk; title key variants + dup check; links tuple + "+N more";
  cryptic `len(v) linked`; SelectionArea + long-press copy; emoji → Icon+Text;
  `is_verified` string check; tokens for padding.
- **Certified:** Container/Row/Column/Text/Icon/Image props, Padding/Border order,
  BoxFit, ellipsis, alignments, weights, with_opacity order, icon names, circle trick,
  expand layout, avatar fallback + no-download-storm.

### `src/components/profile_detail_dialog.py`

- **P0** `status_color` undefined in empty-fallback (L484-490 vs 840, masked today).
  `json.dumps` without `default=str` kills dialog on datetime/bytes/set (L740).
  `FilledButton(content=+icon=)` + non-standard `action=` — Visit/Open button may never
  open URL (L369-380/874-887, single on_click path).
- **P1** Clipboard pattern (L101-104 → `page.set_clipboard`). `show_dialog/pop_dialog`
  vs `page.open/close` (L135/385/412/783/883). Fixed 380×420 overflow (min with page size).
  `query_time` str crash (L299/729).
- **P2** `str(bio)` vs `_stringify` (L594); `_stringify` dict/None cases; URL guessing
  (L126-132/399-409); status chip inconsistency; overflow/SelectionArea; avatar gate
  (`data:`, `//`, cached paths) + task exception handler.
- **Missing** Pivot-back-to-search, JSON copy button, SelectionArea wrap.
- **Certified:** no HTML injection, `_dossier_row` closure handling, ellipsis/max_lines,
  error_content avatar, rate-limit banner, tri-state, outer try/except + snack.

### Small components (7 — one agent)

- `active_scan_banner`: P1 double-fire View tap (nested on_click bubbles); unclamped
  progress value; `Control` vs `ft.Control`. Certified: zero-div guards, copy branches.
- `app_header`: P1 `theme_mode` enum-vs-str into state (L127); scroll+SPACE_BETWEEN;
  `create_task` vs `run_task`. Certified: theme cycle, version chip, icon tint.
- `banner_ad`: P0-verify `BannerAd(width/height)` vs `AdSize` (silent empty box on every
  screen if wrong). P1 `is_mobile()` bare call (revenue loss); `flet.context` fallback.
  Certified: fail-closed design, glass wrapper.
- `empty_state`: P1 label-without-handler silent drop. Certified: everything else.
- `section_header`: certified entire file.
- `stat_card`: P1 label clip without ellipsis. Certified: scaling, tint, expand.
- `targets_card`: P1 `callable` builtin + `ink=True` with None handler; `page=None`
  helper contracts; `total_count=0` vs fallback label. Certified: scope branching, layout.
- `update_dialog`: P0-verify `ft.UrlLauncher` (all external links dead if hallucinated,
  L37). P1 `action=` on buttons (dialog may never construct); fixed 360/380 overflow;
  `check_from_dialog` outside try; pop-then-show race. Certified: platform rule, mandatory
  modal, offline notes, Markdown wiring.

---

## Services (12)

### `src/services/sherlock_service.py` (1012 lines)

- **P0** Dead/mismatched cancel primitives (`asyncio.Event` never wired, thread Event
  passed, `_search_task/_progress` never assigned, L232/451/695-698/850-851/995-996).
  Primary exception aborts whole multi-target scan (L538-543, mirror secondary continue).
  `url_main`/`http_status` always empty (L262-264/297-302, kills 403-vs-429 analysis).
  `search()` skips reload on config change (L836-837, guard redundant+harmful).
  Cancel cooperative-between-targets-only (single 5,200-site scan uncancel
...[truncated 9113 chars]