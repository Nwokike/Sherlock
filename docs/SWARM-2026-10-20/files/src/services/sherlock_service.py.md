# Audit — `src/services/sherlock_service.py`

File: `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/services/sherlock_service.py` (367 lines)
Engine: `user-scanner 1.5.2.3` (`.venv\Lib\site-packages\user_scanner`) — the only truth
UI: `flet 1.0.4` (`.venv\Lib\site-packages\flet`)
Read-only audit. Nothing was modified.

---

## 1) File role

`SherlockService` is the **username-scan facade** of Sherlock-V3. It is the only place that
translates user-scanner's `user_scan/*` module catalog into the app's `SiteResult` /
`SearchProgress` contract, and it owns the whole scan lifecycle:

| Responsibility | Lines |
|---|---|
| Public dataclasses mirroring the original Sherlock contract (`SiteResult`, `SearchProgress`) | `sherlock_service.py:29-56` |
| Username list parsing | `sherlock_service.py:59-72` |
| Badge classification from the upstream error reason | `sherlock_service.py:75-87` |
| Site-catalog load (module discovery → app `state`) | `sherlock_service.py:100-128` |
| Scan entry point (targets → worker thread → progress) | `sherlock_service.py:130-167` |
| Per-target scan loop + cross-scan (pivot) second pass | `sherlock_service.py:169-257` |
| Worker thread + private event loop | `sherlock_service.py:259-274` |
| Hudson Rock breach-intel check | `sherlock_service.py:276-290` |
| Cancellation handle | `sherlock_service.py:292-293` |
| Legacy DB-health stub | `sherlock_service.py:295-296` |
| upstream `Result` → `SiteResult` mapping | `sherlock_service.py:299-367` |

Callers: `src/main.py:1003` (`search`), `src/main.py:1120` (`run_hudson` via `asyncio.to_thread`),
`src/screens/home_screen.py:587` (`run_hudson` via `asyncio.to_thread`),
`src/main.py:869`/`src/main.py:873` (`load_sites`), `src/main.py:2271` (`run_db_health`).

Architecturally the file is meant to be a **thin facade**: `services/user_scanner_compat.py:4-5`
states "This is the ONLY module that imports user-scanner / phonsint internals. Everything else
talks to the SherlockService / EmailService / PhoneService facades, so an upstream upgrade touches
one file." `sherlock_service.py` **breaks that contract** — it imports user-scanner internals
directly at `:101`, `:223`, `:300` and `:301`.

---

## 2) Engine API verification summary

Every symbol the file touches was checked against the installed package.

| Symbol used in this file | Installed location | Verdict |
|---|---|---|
| `user_scanner.core.helpers.set_global_timeout` | `core/helpers.py:457` | ✅ exists, correct arity (`float`/`None`) |
| `user_scanner.core.helpers.load_categories` (via compat) | `core/helpers.py:519` | ✅ exists |
| `user_scanner.core.helpers.get_site_name` (via compat) | `core/helpers.py:496` | ✅ exists |
| `user_scanner.core.result.Status` (TAKEN/AVAILABLE/ERROR/SKIPPED) | `core/result.py:68-72` | ✅ all four members exist; the comparisons at `:311-318` are correct |
| `Result.get_reason()` | `core/result.py:158` | ✅ exists; used correctly at `:318`/`:324` |
| `Result.extra` / `Result.media` | `core/result.py:95-96` | ✅ dicts; `Result.update` lower-cases extra keys (`core/result.py:111`), so `extra.get("confidence")` (`:343`) and `extra.get("pivot_source")` (`:347`) are the **correct** key spellings |
| `Result.url` / `Result.site_name` | `core/result.py:94`, `:90` | ✅ exist; `getattr(r, "url", "")` at `:355` is safe |
| `Result.taken` / `Result.available` | `core/result.py:128-134` | ⚠️ exist, but the two uses at `:304` and `:307` are **dead / malformed** (see N17) |
| `Result.is_visible(ScanConfig)` | `core/result.py:291` | ❌ **never called** → `state.show_all_results` is silently dropped (see N12b) |
| `ScanConfig` fields | `core/helpers.py:447-453` (`allow_loud, no_nsfw, show_all, verbose, timeout`) | ⚠️ the service never builds one; `verbose`/`show_all` are therefore never honoured |
| `user_scanner.core.cross_scan.CrossScanConfig(links, emails, depth, sweep)` | `core/cross_scan.py:61-79` | ✅ the four kwargs at `:224-229` are real fields — but `modules` and `categories` exist (`core/cross_scan.py:67-72`) and are **never set** (see N1) |
| `extra["confidence"]` written by upstream | `core/cross_scan.py:512` (`result.update(extra={"confidence": rating.value})`) | ✅ key is real — but written *after* this file snapshots it (see N9) |
| `extra["pivot_source"]` written by upstream | `core/cross_scan.py:471` and `:480` | ✅ key is real and is set *before* `on_result` fires → `pivot_source`/`context` works |
| `user_scanner.core.hudson.run_hudson_scan(target, is_email=…)` | `core/hudson.py:49` | ✅ signature matches — but the function is **CLI-interactive** (see K1) |
| `user_scanner.core.orchestrator.run_user_full(username, configs)` | `core/orchestrator.py:259` (`asyncio.run` wrapper) | ✅ the docstring's claim at `:3-4` is accurate: it is `asyncio.run`-based and CLI-coupled, so not using it is correct |
| `user_scanner.core.pivots` | `core/pivots.py` | ⚠️ never imported here — pivot extraction happens inside the compat layer, so the file's "pivot" support is entirely delegated (correct) |
| `LOUD_MODULES["user"]` | `core/helpers.py:28` → **`[]`** | ⚠️ empty → `allow_loud` (`:208`, `:240`) is a **no-op for username mode** and no "skipped" tuple is ever emitted for usernames (see N10) |
| `Result.to_csv` / `_neutralize_csv_cell` | `core/result.py:26-33`, `:218` | ⚠️ upstream neutralizes every cell; **the app's export does not** (see N11) |
| `auto_hudson_prompt` default | `user_scanner/config.json` → `true`; `core/helpers.py:749` | ✅ confirmed `true` on disk → the consent prompt fires (see K1) |

**Bottom line: no hallucinated symbols.** Every imported name exists in 1.5.2.3. The API problems
are of a different kind: *correctly named APIs used wrongly, or correctly named APIs never used*
(`is_visible`, `ScanConfig.show_all/verbose`, `CrossScanConfig.modules/categories`,
`Result.to_csv`'s neutralizer).

---

## 3) Confirmed known bugs

### K1 — Hudson consent `input()` in a worker thread → EOFError / permanent hang — **CONFIRMED**
`sherlock_service.py:276-290` calls `hudson.run_hudson_scan(target, is_email=is_email)` (`:286`).
Upstream `run_hudson_scan` → `check_hudson_permission` (`core/hudson.py:22-47`) reads the config,
and the **installed** `user_scanner/config.json` has `"auto_hudson_prompt": true`, so it falls
through to `input(f"\n… Query Hudson Rock? (y/n/d …)")` at `core/hudson.py:36` — an unguarded
blocking read with **no `isatty` check**.

The call site is a worker thread: `src/main.py:1120` → `await asyncio.to_thread(self.sherlock_service.run_hudson, target_clean, False)`
and `src/screens/home_screen.py:587` → `asyncio.to_thread(svc.run_hudson, …)`. A Flet worker thread
has no interactive stdin:

* stdin closed / not a TTY → `input()` raises `EOFError` → caught by the broad `except Exception` at
  `:287` → `run_hudson` returns the string `"Hudson check failed: EOF when reading a line"`, which
  the caller shows as a snackbar (`main.py:1121-1122`). The Hudson feature is **100% broken**.
* stdin *is* a console (app launched from a terminal) → `input()` **blocks forever** while the
  prompt text is swallowed into the `StringIO` (`:283-285`) — the user is never shown the question,
  so the thread hangs indefinitely.

`update_hudson_preference(False)` (`core/hudson.py:15-20`) also writes into the **venv** at
`user_scanner/config.json` (`core/helpers.py:444`, `:723-735`) — a packaged directory.

### K2 — `cancel()` only sets a `threading.Event` — **CONFIRMED**
`sherlock_service.py:292-293` is `self._thread_cancel.set()`. There is no handle to the running
future, no `task.cancel()`, no `loop.call_soon_threadsafe`. The only thing the flag does is make
the compat's polling checks (`user_scanner_compat.py:153`, `:187`, `:190`, `:249`, `:267`, `:270`,
`:352`, `:355`) return early. Consequence: **in-flight module calls are not cancelled.** A sync
`validate_*` already running in `loop.run_in_executor` (`user_scanner_compat.py:203`) keeps its
socket open for the full `timeout + 10 s` (`user_scanner_compat.py:197`). `self._cancel_handle`
(`:94`) is the vestige of a real cancel handle — it is **never assigned or read** (N15).

### K3 — `loop.close()` with tasks still pending — **CONFIRMED**
`user_scanner_compat.py:168-170`:

```python
for coro in asyncio.as_completed(tasks):
    if cancel_event.is_set():
        break          # <-- breaks WITHOUT cancelling the pending tasks
```

When the cancel flag trips, the remaining `asyncio.Task`s are abandoned. `_run` returns, and
`sherlock_service.py:270` calls `loop.close()` while those tasks are still pending →
`Task was destroyed but it is pending!` warnings, and the `run_in_executor` worker threads keep
running to completion (they are not interrupted by `loop.close()`; the loop's default executor is
never shut down because `loop.shutdown_default_executor()` is never called). A cancelled scan
therefore leaves up to 50 HTTP requests in flight after the UI says "cancelled", and the inner
loop's `ThreadPoolExecutor` is torn down without draining.

### K4 — `clear()` un-cancels a still-running previous worker (cross-generation race) — **CONFIRMED**
`sherlock_service.py:150` `self._thread_cancel.clear()` runs at the start of every `search()`.
Because `asyncio.to_thread` (`:154`) **cannot** be cancelled, a superseded scan's worker thread
survives the supersede. Sequence:

1. Scan A starts → worker thread A running.
2. User starts scan B → `main.py:202-203` calls `sherlock_service.cancel()` → the shared event is
   set → then B's `search()` reaches `:150` and **clears the same event**.
3. Worker thread A now sees `is_set() == False` again → **it keeps scanning**, and it keeps
   calling `on_progress` and writing `state.target_results` (`:179`) while B is running.

Both generations share one `threading.Event`, one `self._modules` list, and one
`state.target_results` dict. A's late ticks can overwrite B's entry for the same target.

### K5 — `to_thread` → `new_event_loop` → `run_until_complete` nesting — **CONFIRMED**
`sherlock_service.py:154` (`asyncio.to_thread`) → `:259-265` (`_run_worker` creates
`asyncio.new_event_loop()` at `:260`, `asyncio.set_event_loop(loop)` at `:261`,
`loop.run_until_complete(...)` at `:263`). Three consequences:

* A **second** default `ThreadPoolExecutor` is created for the inner loop; the sync module
  functions run there (`user_scanner_compat.py:203`), i.e. a second level of threading on top of
  `asyncio.to_thread`'s executor.
* `asyncio.to_thread` futures are **not cancellable** — cancelling the awaiting task raises
  `CancelledError` in the caller but the thread keeps running (this is what makes K4 possible).
* The inner loop is closed (`:270`) without `shutdown_default_executor()`; `asyncio.run()` /
  `asyncio.Runner()` would have done the cancellation + executor shutdown correctly.

### K6 — Hudson stdout captured into `StringIO` includes raw ANSI — **CONFIRMED**
`sherlock_service.py:283-290` captures the printed output. Upstream uses colorama constants
(`core/hudson.py:8-13`: `R = Fore.RED`, `Y = Fore.YELLOW`, …) which are **unconditional ANSI
escapes** (colorama is not tty-aware here), e.g. `core/hudson.py:80`:
`print(f"{R}[!] FOUND {total_stealers} INFOSTEALER INFECTION(S) …{X}")`. The captured string
therefore contains raw `\x1b[31m` / `\x1b[0m` sequences, which are rendered verbatim in the Flet
snackbar (`main.py:1121-1122`).

Two extra consequences of the same design:
* `contextlib.redirect_stdout` (`:285`) rebinds **`sys.stdout` process-wide** — for the duration of
  the Hudson call, *every other thread's* `print()` (user-scanner module chatter, the app's stdout
  log handler) is swallowed into that `StringIO`.
* The captured text starts with the privacy notice (`core/hudson.py:30-33`), and the caller
  truncates to 120 chars (`main.py:1121`) → **the actual findings never reach the user**; the
  snackbar shows only the legal notice. When the user answers `n`, `run_hudson_scan` returns
  `None` and the app displays "Hudson Rock scan skipped." as if it were a result.

### K7 — Sweep budget / `scan_depth` / category selection — **PARTIALLY CONFIRMED (a real hole)**
* `selected` (the user's site filter, built at `:148`) **is** passed to the primary pass
  (`:210` → `user_scanner_compat.py:143-144` filters by `get_site_name(mod).lower() in selected`).
* It is **NOT** passed to the cross-scan pass. `run_cross_scan_async`
  (`user_scanner_compat.py:386-398`) has **no `selected` parameter at all**, and its internal
  `run_username_scan` calls (`:475-485`, `:503-513`) therefore sweep against
  `all_user_modules` — the **entire catalog**. `CrossScanConfig.modules` / `.categories`
  (upstream `core/cross_scan.py:67-72`, consumed by upstream's `_scope()` at
  `core/cross_scan.py:187-207`) are **never set** by the service (`:224-229`).
  Net effect: with `cross_sweep = 3` the pivot pass can fire `3 × 2521` extra requests that the
  user's site selection was supposed to exclude. **This is the most expensive defect in the file.**
* `state.scan_depth` (`src/core/state.py:117`, user-facing: `src/screens/home_screen.py:443-449`
  and `src/screens/settings_screen.py:563-564`, values `"all" | "1000" | "500"`) is **never read**
  by this file (or anywhere in the engine path) → the depth chip in the UI is a no-op.

---

## 4) NEW bugs / hallucinations (severity-ordered)

### N1 — CRITICAL — cross-scan sweep ignores the user's site filter and the upstream scope
`sherlock_service.py:221-243`. `CrossScanConfig` is built with only `links/emails/depth/sweep`
(`:224-229`); `modules` and `categories` are left at their defaults (`core/cross_scan.py:67-72`),
and the compat's `run_cross_scan_async` cannot receive `selected` at all. Every pivot username is
swept against all 2521 user modules. (Upstream's own cross-scan is scoped — `_scope()` at
`core/cross_scan.py:187-207` — the app bypasses it.)

### N2 — CRITICAL — the returned `SearchProgress.is_cancelled` is **always False**
`sherlock_service.py:161-167`:
* The reconciliation loop (`:161-166`) only mutates `state.target_results` entries, never the
  object that is returned.
* Its `elif` (`:164`) requires `app_state.target_results[tgt].is_running` to still be `True` —
  but the worker's `finally` at `:249` already set `is_running = False`, so the branch is
  **unreachable** for any target the worker reached.
* On the `CancelledError` path (`:157-159`) `last_prog` is `None`, and `:167` returns a
  **freshly constructed** `SearchProgress(...)` whose `is_cancelled` defaults to `False`.

The app depends on that flag: `src/main.py:1011` (`getattr(result, "is_cancelled", False)`) is the
watchdog that stops a cancelled scan from publishing results, and `src/main.py:1033` is the
"scan_cancelled" notification branch. Both are dead for the username path. Consequence: a
service-level `cancel()` that does not also cancel the task publishes **partial results as
final** (`main.py:1042-1055` merges them into `state.last_results`) and fires the
*scan-finished* notification instead of *scan-cancelled*.

### N3 — HIGH — `load_sites()` executes 2521 module files synchronously on the event loop
`sherlock_service.py:111-113` → `services/user_scanner_compat.py:33-41` → `_load_modules_tolerant`
(`user_scanner_compat.py:61-83`), which `exec_module`s **every** file in `user_scan/*/` —
**2521 user modules** (220 email modules). `load_sites` is `async` but performs **no await**, so
this runs on the flet event-loop thread → a multi-second UI freeze. Worse, the cache at
`:106-115` is keyed on **mode only**, so switching username→email→username re-imports the whole
catalog every time, and `force=True` does too. `load_sites()` is called on every scan (`:145`).

### N4 — HIGH — the first `on_progress` call is unguarded
`sherlock_service.py:178`: `on_progress(progress) if on_progress else None` — no `try/except`,
unlike the two other call sites (`:198-202`, `:251-255`). If the UI callback raises, the
exception escapes `_run` → caught by the broad `except Exception` at `:246` → logged as
"username scan failed for %s" → **the entire target's scan is aborted** (not just the tick).

### N5 — HIGH — the `confidence` badge can never fire
`sherlock_service.py:339-345`. `_map_username_result` **copies** `extra` into a new dict (`:339`),
so it is a snapshot taken at map time. Upstream writes `extra["confidence"]` only in
`_apply_confidence` (`core/cross_scan.py:512`), which runs at the **end** of the cross-scan pass
(`user_scanner_compat.py:551`). But:
* primary-pass results are mapped at `:190`, long before that → no confidence;
* cross-scan results are mapped at `user_scanner_compat.py:489/517/542`, also **before** the final
  `_apply_confidence` at `user_scanner_compat.py:551`;
* even if the write happened later, the copy at `:339` is never refreshed.

So `badge = str(confidence).lower()` (`:345`) is dead code — the confidence feature is inert.

### N6 — MEDIUM — "Skipped" results are bucketed as errors
`sherlock_service.py:191-197`: `Claimed → found`, `Available → not_found`, **everything else →
errors**. Upstream `Status.SKIPPED` is not an error (`core/result.py:76-78` labels it "Skipped",
and `is_visible` at `core/result.py:291-296` treats SKIPPED as a *visible* result). Today the
bucket stays empty because `LOUD_MODULES["user"] == []` (`core/helpers.py:28`), but the mapping is
wrong and will silently mis-classify as soon as upstream populates the user list. Relatedly,
`allow_loud` (`:208`, `:240`) is a **no-op for username mode** — the toggle in the UI does nothing.

### N7 — MEDIUM — the service drops upstream's CSV formula-injection guard
Upstream neutralizes every exported cell (`core/result.py:26-33`, applied at `:218`). The app's
CSV writer (`src/services/report_service.py:125-155`) applies **no** neutralization and writes the
**raw username** as the first cell of every row (`:141`). The username comes straight from
`parse_usernames` (`sherlock_service.py:59-72`), which accepts arbitrary text — `=cmd|' /C calc'!A0`,
`+1+1`, `-2+3` are all accepted and become formula cells when the CSV is opened in Excel. This
file is the producer of both the untrusted value and the unescaped row payload
(`sherlock_service.py:341` packs the upstream `extra`/`media` strings into `ids_data` with no
neutralization either).

### N8 — MEDIUM — worker-thread mutation of a flet observable
`sherlock_service.py:179` `app_state.target_results[tgt] = progress` executes **in the worker
thread**. `state.target_results` is an `ObservableDict` (flet `components/observable.py:342-379`);
`__setitem__` → `_touch()` → `owner._notify(field)` → listeners are invoked **synchronously**
(`flet components/observable.py:165-175`). Today no screen subscribes to `state.target_results`
(the UI re-renders off `progress_version`), so the effect is latent — but any subscription would
call `Component._schedule_update` → `session.schedule_update` → `asyncio.Event.set()` from a
foreign thread (flet `messaging/session.py:663-674`), which is not thread-safe. The same
ObservableDict is also read at `:162-166` on the main thread while the worker may still be writing
to it (the `to_thread` future is not cancellable).

### N9 — MEDIUM — the progress object handed to the UI is still being mutated
`sherlock_service.py:190-201`: the worker thread keeps doing `progress.checked_sites += 1` and
`progress.found.append(sr)` on the **same object** that `on_progress` publishes. The app's bridge
(`src/main.py:1279-1318`) stores that live object in `self._pending_progress` and the main loop
reads it later (`_apply_progress`, `src/main.py:1321+`). There is no snapshot, so the main thread
can iterate a list that the worker is appending to (CPython raises `RuntimeError: list changed
size during iteration` for that) and can render a torn `checked_sites` / `found` pair.

### N10 — MEDIUM — `state.sites_cache` / `sites_tags_map` / `sites_tag_index` are triple-bookkept
`sherlock_service.py:116-126` writes three overlapping indexes:
* `sites_tags_map` is keyed by **site name** → `sites_tag_index` is keyed by **category**;
* the two use different name conventions for the same module — `get_site_name_user(m)` yields
  `"Github"` (`.capitalize()` at `core/helpers.py:497`) while `m.__name__.split(".")[-1]` at `:125`
  yields `"github"`;
* `sites_tags_map` collapses duplicates (two modules with the same display name in different
  categories → last one wins).

Only `sites_tag_index` is a true inverse of `sites_tags_map`; one of the three is redundant and the
name conventions will bite whoever wires the category chips to the `selected` filter.

### N11 — MEDIUM — `load_sites(mode="email")` clobbers the shared global site catalog
`sherlock_service.py:109-126` writes the *global* `state.sites_total / sites_cache /
sites_tags_map / sites_tag_index` regardless of `mode`. The email fallback at
`src/main.py:869` (`await self.sherlock_service.load_sites(mode="email")`) therefore replaces the
username catalog with 220 email modules — the Sites screen then lists email sites. The same call
also flips `self._modules` to the email set (`:111`), and the next username scan re-imports all
2521 modules because the cache is keyed on mode (N3).

### N12 — LOW/MEDIUM — settings accepted by the app but dropped by this file
Verified by grep across `src/`: these are live, user-facing settings that **no engine path reads**:
* `state.scan_depth` (`src/core/state.py:117`; UI at `home_screen.py:443-449`,
  `settings_screen.py:563-564`, `:1240`) → no effect on the scan (K7).
* `state.retries` (`src/core/state.py:131`; `settings_screen.py:593`) → no effect.
* `state.show_all_results` (`src/core/state.py:68`) → upstream's `Result.is_visible(ScanConfig)`
  (`core/result.py:291`) is never consulted.
* `state.verbose_output` (`src/core/state.py:69`) → `ScanConfig.verbose` is never set.
* `state.proxy_file` (`src/core/state.py:78`) → only `state.proxy_url` (`:211`, `:242`) is used.

### N13 — LOW — `url_main`, `http_status`, `query_time` are hard-coded empties
`sherlock_service.py:354`, `:357`, `:358`. `SiteResult` declares them (`:32-36`) and the report
layer writes them as CSV columns (`src/services/report_service.py:145-152`), so the
"http_status" and "response_time_s" columns are **always empty** for username scans, and
"url_main" is always empty. Upstream `Result` carries no such fields, so the app must either
populate them (the module's profile URL is known) or drop the columns.

### N14 — LOW — `search()` returns only the **last** target's progress
`sherlock_service.py:256-257` (`last_prog = progress` per target) and `:167`. For a multi-target
scan (permutations, `src/main.py:991-1000`) the caller receives a single target's
`SearchProgress`; the others are only in `state.target_results`. `main.py:1042-1055` merges both
sources, so the app copes — but the service's own contract is lossy.

### N15 — LOW — dead field `self._cancel_handle`
`sherlock_service.py:94` — assigned, never read, never written. It is the fossil of the cancel
handle that K2 says is missing.

### N16 — LOW — `run_db_health` is a stub
`sherlock_service.py:295-296` always returns `{"error": "user-scanner: no site DB"}` regardless of
its arguments; `src/main.py:2271` calls it with `sample_size=25` and the UI reports a permanent
"no site DB" state.

### N17 — LOW — malformed / dead status-mapping conditionals
`sherlock_service.py:304-308`:
```python
if status == USResult.taken.__wrapped__ if hasattr(USResult.taken, "__wrapped__") else status:
    pass
status_str = "Claimed"
if status == USResult.available(0).status if False else None:
    status_str = "Available"
```
* Line `:304` — `USResult.taken` is a `classmethod`; it has no `__wrapped__`, so the condition
  degenerates to `if status:` (always truthy) → the `pass` branch is a no-op. It also calls
  `USResult.taken` (building a `Result`) purely to test an attribute that can never exist.
* Line `:307` — the conditional expression parses as `(status == USResult.available(0).status) if False else None`,
  i.e. the condition is **always `None`** → the `"Available"` assignment at `:308` is
  **unreachable**, and `USResult.available(0)` (which would pass `0` as the *reason*, not the
  status) is never even evaluated.

The real mapping is the correct `try/except` block at `:310-318`. The two lines above it should
be deleted; as written they look like the mapping and mislead every reader (and any linter).

### N18 — LOW — `is_available` is hard-coded `True`
`sherlock_service.py:96-98`. The property exists purely to satisfy the controller contract
(`src/main.py:531`, `:542`); it never reflects whether user-scanner is importable.

### N19 — LOW — `set_global_timeout` is a process-global set from a cached load
`sherlock_service.py:101-103` writes `user_scanner.core.helpers._global_timeout`
(`core/helpers.py:455-459`) — a module-level global read by upstream modules
(`core/impersonate.py:132`, `core/pdf_generator.py:132`, several email modules). It is only
refreshed when `load_sites` actually reloads (`:106-115`), so a timeout change in Settings does
not reach the engine until the catalog is reloaded, and two concurrent scans with different
timeouts would fight over one global.

### N20 — LOW — the service bypasses the compat layer's single-point-of-contact contract
`sherlock_service.py:101` (`user_scanner.core.helpers`), `:223` (`user_scanner.core.cross_scan`),
`:300-301` (`user_scanner.core.result`) — four direct imports of engine internals, against
`user_scanner_compat.py:4-5`. An upstream upgrade that renames `Status` or `CrossScanConfig`
breaks this file, which is exactly what the compat layer exists to prevent.

### N21 — LOW — `parse_usernames` accepts arbitrary text
`sherlock_service.py:59-72` splits on commas/whitespace and de-duplicates, but performs **no
validation** of the handle. `"not a username!"` becomes a scan against 2521 sites, and the string
becomes the first column of every exported CSV row (N7).

### N22 — LOW — `_badge_for` matches bare substrings
`sherlock_service.py:79-84`: `"403" in low`, `"rate" in low`, `"bot" in low` — a benign reason
containing e.g. "rate" (as in "corporate rate limit page") is tagged `rate`. Low impact, but the
same `reason` is also copied verbatim into `SiteResult.error_type` (`:362`).

### N23 — LOW — the return value of `run_hudson_scan` is ignored and refusals look like results
`sherlock_service.py:286-290`: upstream returns `None` in every case (success, 404, refusal), so
the service's only signal is the captured stdout. When the user answers `n`, the app displays
"Hudson Rock scan skipped." as a result (K6).

### N24 — LOW — `_run` has no type annotations
`sherlock_service.py:169` — every other public signature in the file is annotated; `_run` and
`_run_worker` (`:259`) are not, and `_run` carries eight positional parameters, two of which
(`on_progress`, `after_primary`) are callables with a defined contract that is documented nowhere
(`after_primary(tgt, len(found), total_sites)` at `:216`).

---

## 5) Improvements (ordered by value)

1. **Give each scan generation its own cancel token.** Replace the single
   `self._thread_cancel` (`:92`) with `self._event` + `self._generation`; `cancel()` (`:292-293`)
   sets the *current* generation's event only, and the worker checks
   `event is self._current_event` before touching `state` — this kills K4/N3-race and makes
   supersede deterministic.
2. **Make the returned progress carry the cancel state.** Set `is_cancelled=True` on the object
   returned at `:167` (and on `last_prog`) whenever the worker observed the cancel flag — this
   revives main.py's watchdog (`main.py:1011`, `:1033`) and stops partial results from being
   published as final (N2).
3. **Stop the `to_thread` → `new_event_loop` → `run_until_complete` sandwich.** Either run the
   scan directly on the flet loop (the compat API is already `async`; a plain `asyncio.Event` can
   replace the `threading.Event` and `task.cancel()` then really aborts in-flight waits), or keep
   the thread but use `asyncio.Runner()` (3.11+) / `asyncio.run()` inside it so pending tasks are
   cancelled and the executor is shut down. This addresses K2, K3, K5 at once.
4. **Cancel and drain the pending module tasks.** In `user_scanner_compat.py:168-170`, replace
   `break` with `for t in tasks: t.cancel()` + `await asyncio.gather(*tasks, return_exceptions=True)`
   before returning; then the inner loop closes cleanly and the executor threads are reclaimed.
5. **Pass the site filter (and upstream scope) into the cross-scan pass.** Add a `selected`
   parameter to `run_cross_scan_async` and thread it into both inner `run_username_scan` calls;
   also populate `CrossScanConfig.modules` / `.categories` from `state.selected_sites`
   (`:224-229`). This is the single largest cost saving in the file (N1/K7).
6. **Load the module catalog off the event loop and cache it by `(mode, no_nsfw)`.** Move
   `load_user_modules`/`load_email_modules` into a thread and cache the result in the compat
   layer (upstream's own `load_modules` is `lru_cache`d at `core/helpers.py:503-516`; the tolerant
   loader at `user_scanner_compat.py:61-83` is not). 2521 `exec_module` calls must never happen on
   the UI thread (N3).
7. **Rewrite the Hudson integration.** Do not call `run_hudson_scan` from a worker thread:
   either set `auto_hudson_prompt=false` once (through `hudson.update_hudson_preference`,
   `core/hudson.py:15-20`) and perform the consent prompt in the UI, or call the HTTP endpoint
   directly (`core/hudson.py:57-69`) and build the summary in the app. Then: strip ANSI
   (`re.sub(r"\x1b\[[0-9;]*m", "", text)`), return **structured** data (list of stealers) instead of
   raw stdout so the legal notice cannot crowd out the findings, and stop using the
   process-global `contextlib.redirect_stdout` (K1, K6, N23).
8. **Re-map results after the cross-scan pass** (or defer mapping to the end) so
   `extra["confidence"]` exists when `_map_username_result` reads it — the badge at `:343-345`
   becomes live (N5).
9. **Snapshot the progress before publishing it.** Pass a copy (`dataclasses.replace` + copied
   lists) to `on_progress`, or push the mutation through a thread-safe queue (N9).
10. **Guard the first `on_progress` call** at `:178` with the same `try/except` as `:198-202`
    (N4).
11. **Port `_neutralize_csv_cell` into the export path** (or into the service, before
    `SiteResult` is built) — upstream already has the helper at `core/result.py:26-33` (N7).
12. **Give `Status.SKIPPED` its own bucket** in `SearchProgress` (or map it to a neutral
    "Skipped" list) instead of `errors` (`:191-197`), and honour `state.show_all_results` via
    `Result.is_visible(ScanConfig(show_all=…))` (N6, N12).
13. **Honour `state.scan_depth`** — truncate `all_modules` to the requested depth
    (`"1000" | "500"`) and set `progress.total_sites` accordingly; **honour `state.retries`** by
    retrying failed modules once (N12).
14. **Delete the dead code**: the two malformed conditionals at `:304-308`, the unused
    `self._cancel_handle` (`:94`), the unreachable `elif` at `:164`, and either implement or
    remove `run_db_health` (`:295-296`) (N15-N17).
15. **Move the four direct user-scanner imports** (`:101`, `:223`, `:300-301`) into
    `services/user_scanner_compat.py`, restoring the "one file to touch on upgrade" contract (N20).
16. **Populate or remove the empty columns** `url_main` / `http_status` / `query_time`
    (`:354-358`) so the CSV/PDF reports stop shipping three always-blank fields (N13).
17. **Unify the site index** — keep one `{tag → [site names]}` map with one naming convention and
    derive `sites_tags_map` from it, instead of three overlapping indexes (N10).
18. **Namespace the per-target state by generation** so a superseded scan cannot overwrite the
    live scan's `state.target_results` entry for the same target (K4/N3).
19. **Return a per-target mapping** (e.g. `dict[str, SearchProgress]`) instead of only the last
    target's progress (N14), and document the `after_primary(tgt, found, total)` callback contract
    (`:216`).

---

## 6) Verdict

**Engine API correctness: PASS (no hallucinations).** Every symbol imported or called by this file
exists in `user-scanner 1.5.2.3` with the expected signature: `set_global_timeout`,
`Status.{TAKEN,AVAILABLE,ERROR,SKIPPED}`, `Result.get_reason/extra/media/url/site_name`,
`CrossScanConfig(links,emails,depth,sweep)`, `hudson.run_hudson_scan(target, is_email=…)`,
`run_user_full(username, configs)`. The two `Result` factory uses at `:304`/`:307` are malformed
but dead (N17) — they are the only API-abuse in the file.

**Runtime behaviour: FAIL.** The file compiles and the happy path works, but it carries
**three critical/high defects** that the app's own watchdog logic depends on:

* **N1/K7** — the cross-scan pivot sweep ignores the user's site selection and sweeps the entire
  2521-module catalog per pivot (up to 3× per round), because `CrossScanConfig.modules`/
  `.categories` are unset and `run_cross_scan_async` cannot accept `selected`;
* **N2** — the returned `SearchProgress.is_cancelled` is **always `False`**, which silently
  disables `src/main.py:1011` and `:1033` and lets a cancelled scan publish partial results as
  final with a *scan-finished* notification;
* **K4** — `self._thread_cancel.clear()` (`:150`) plus an uncancellable `asyncio.to_thread` worker
  means a superseded scan keeps running and races the replacement over the shared
  `state.target_results`.

Plus two high-severity operational defects: the **2521-module synchronous import on the flet event
loop** (N3) and the **Hudson `input()` in a worker thread** (K1), which makes that feature
non-functional (EOFError) or hanging (attached console), with raw ANSI in the output (K6) and the
actual findings truncated away by the caller.

**Cancellation is cosmetic.** `cancel()` (`:292-293`) sets a flag that only stops *scheduling*; the
pending tasks are abandoned by `user_scanner_compat.py:168-170` without being cancelled and the
inner loop is closed over them (`sherlock_service.py:270`), so up to 50 in-flight HTTP requests
keep running after the UI reports "cancelled" (K2, K3, K5).

**Highest-value fixes, in order:** (1) per-generation cancel token + real task cancellation;
(2) propagate `is_cancelled` on the returned progress; (3) scope the cross-scan sweep;
(4) move the catalog load off the event loop and cache it; (5) replace the Hudson call with a
direct, non-interactive, ANSI-stripped, structured implementation.
