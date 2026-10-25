# Audit: `src/core/state.py`

**File:** `src/core/state.py` (240 lines)
**Scope:** single-file audit — flet observable API correctness, field census, type/default correctness, bugs, improvements.
**Truth source:** installed `flet 1.0.4` at `.venv/Lib/site-packages/flet` (verified `flet/version.py:17` → `flet_version = "1.0.4"`).
**Method:** read the file, verified every flet API against the installed package source, grepped every one of the 85 declared fields across `src/` (outside this file), traced persistence keys through `main.py::_load_saved_state` and `screens/settings_screen.py`, and traced the observable notification path end-to-end.

---

## 1) File role

`src/core/state.py` is the **single mutable state container for the entire app**. It declares one class, `AppState` (state.py:12-13), decorated with `@ft.observable`, and instantiates exactly one module-level singleton at state.py:240 (`state = AppState()`).

Responsibilities it currently owns, all in one flat class:

| Concern | Fields | Lines |
|---|---|---|
| Transient UI flags | `is_loading`, `is_searching`, `is_first_launch`, `has_accepted_terms`, `is_online` | 15-22 |
| Search identity / mode | `search_mode`, `current_username`, `active_username`, `search_targets`, `target_results`, `search_progress`, `progress_version`, `search_error` | 26-35 |
| Theme | `theme_mode` | 38 |
| Username-scan results | `last_results`, `last_results_username`, `total_sites_checked`, `found_count`, `not_found_count`, `error_count` | 41-46 |
| Email OSINT results | `email_results`, `email_results_address`, `email_found_count`, `email_not_found_count`, `email_rate_limited_count`, `email_unavailable_count`, `email_total_modules` | 50-56 |
| Phone OSINT results | `phone_results`, `phone_results_address`, `phone_found_count`, `phone_not_found_count`, `phone_error_count`, `phone_total_modules` | 59-64 |
| Scan-option parity (M3) | `allow_loud` … `phone_concurrency` (13 fields) | 67-79 |
| Enrichment | `enrichments` | 84 |
| History & result cache | `history_unseen`, `history`, `results_cache` | 90-93 |
| **Settings** (~38 fields) | `nsfw_enabled` … `safe_search` | 96-134 |
| Site database | `sites_total`, `sites_version`, `sites_cache`, `sites_tags_map`, `sites_tag_index` | 138-149 |
| Update & announcement | `update_available`, `update_data` | 152-153 |
| Methods | `set_cached_result`, `get_cached_result`, `set_enrichment`, `reset_search` | 173-237 |

**Consumers.** `src/state/app_state.py:7` wraps the singleton in an flet context (`ft.create_context(state)`); every screen calls `use_context(AppStateCtx)`, and per `flet/components/hooks/use_context.py:106-107` that **auto-subscribes** the calling component to the observable (`component._attach_observable_subscription(value)`). So a single `state.<field> = x` re-renders every subscribed screen. `src/state/controller_ctx.py` holds **no** state fields — it is a bag of `ControllerMethods` callables (`controller_ctx.py:45-83`), the only one of which pairs with this file being `open_cached_result: Callable[[str, str], bool]` (controller_ctx.py:66) ↔ `state.get_cached_result` (state.py:181).

**Field-overlap question (asked in the brief): there is ZERO overlap.** `src/state/app_state.py` is 7 lines and declares no fields; `src/state/controller_ctx.py` declares no state fields. The one *conceptual* duplication is different: `AppState.enrichments` (state.py:84) duplicates `AppController._pending_enrichments` (main.py:404) — see B6.

---

## 2) flet observable API verification

All claims below are read from the installed package, not from training data.

### 2.1 The decorator itself — CORRECT

`ft.observable` exists and is exported: `flet/__init__.py` → `'observable' in ft.__all__` → **True**; implementation at `.venv/Lib/site-packages/flet/components/observable.py:18-49`.

```python
ns = dict(cls.__dict__); ns.pop("__dict__", None); ns.pop("__weakref__", None)
Mixed = type(cls.__name__, (Observable, cls), ns)
```

`AppState` is **not** a dataclass, so the decorator's dataclass branch does not apply; `cls.__dict__` (including `__init__` at state.py:155 and the four methods at 173-237) is carried verbatim onto `Mixed`, and `Observable` is first in the MRO. `Observable.__setattr__` (observable.py:204-212) therefore intercepts every non-underscore assignment. This works as intended.

Verified `ft.ThemeMode.LIGHT` (state.py:38) is a valid member of the installed enum. `ft.ThemeMode` is used correctly.

### 2.2 Collection auto-wrapping — CORRECT, and the `__init__` comment is accurate

`Observable._wrap_if_collection` (observable.py:184-201) converts a plain `list`/`dict` on assignment into `ObservableList`/`ObservableDict`. The comment at state.py:156-158 ("Collections must be assigned in `__init__` so the Observable `__setattr__` auto-wraps them") is **verified correct**: class-level defaults are plain `None`, and `__setattr__` only wraps on *instance* assignment. Every collection field listed in `__init__` (state.py:159-169) is therefore a live `ObservableList`/`ObservableDict` at runtime, with `weakref.ref(owner)` back-pointers (observable.py:350) to the module singleton (alive — the singleton is a module global, so the weakrefs never dangle).

### 2.3 The notification path has NO thread hop — the file's biggest structural risk

Verified chain, with no marshalling anywhere:

```
state.target_results[tgt] = progress
  → ObservableDict.__setitem__          observable.py:377-379
  → self._touch()                       observable.py:354-361
  → owner._notify("target_results")     observable.py:165-175
  → fn(self, field)                     ObservableSubscription.__on_change  observable.py:82-92
  → component._schedule_update()        flet/components/component.py (Component._schedule_update)
  → self._state.is_dirty = True; context.page.session.schedule_update(self)
  → Session.schedule_update             flet/messaging/session.py:663-674
        self.__pending_updates.add(control); self.__updates_ready.set()
```

Every step executes **on the calling thread**. `Observable._notify` has no lock, no `run_coroutine_threadsafe`, no thread assertion. This is the mechanism behind B1.

### 2.4 `value_equal` — content equality, not identity — creates a silent no-notify window

`Observable.__setattr__` (observable.py:211) only notifies when `not value_equal(old, value)`. `flet/components/utils.py::value_equal` is `a is b` → `a == b` → NaN special-case. For **collections** `a == b` is *content* equality. So **rebinding a field with an equal-content collection notifies nobody** even though the object identity changed (B8).

### 2.5 `ObservableDict.update()` does not wrap positional values — CONFIRMED

```python
def update(self, *a, **k):                       # observable.py:393-402
    super().update(*a, **{kk: self._wrap(vv) for kk, vv in k.items()})
```

Only **keyword** values are wrapped. A positional mapping's values are stored raw. `main.py:840 state.results_cache.update(res_map)` therefore stores nested **plain** dicts/lists inside the observable dict — nested mutations of a cached snapshot are invisible to the observable (B9).

### 2.6 `ObservableList` does not override `__getitem__`

`state.history[:50]` (main.py:2257) returns a **plain `list`**, not an `ObservableList`. `state.history[:] = state.history[:50]` then goes through `ObservableList.__setitem__` (observable.py:333-335) which *does* wrap each element → each history entry (a dict) becomes an `ObservableDict`. That particular path is correct, but the asymmetry is a trap: `list(state.email_results)` (results_screen.py:482-484) and `list(app_state.phone_results)` (app_shell.py:68-72) all produce plain-list snapshots.

### 2.7 The `object | None` annotation on `search_progress` forces duck-typing

state.py:33 `search_progress: object | None = None` — deliberately untyped ("keep untyped"), but the consequence is that consumers must discriminate progress kinds structurally. `main.py:244-247` and `main.py:386-390` both do `hasattr(prog, "checked_modules")` to tell email-progress from username-progress. Any future progress type lacking that attribute is silently classified as username progress (B12).

### 2.8 `progress_version` — a manual invalidation counter standing in for real reactivity

state.py:34 `progress_version: int = 0`. Because `search_progress` holds a plain dataclass (`SearchProgress`, `services/sherlock_service.py:47-56`), mutating it (`progress.checked_sites += 1`, sherlock_service.py:191) does **not** notify. The app compensates by manually bumping `progress_version`, which invalidates **every** `use_context(AppStateCtx)` subscriber — i.e. a full-tree re-render for one counter increment (B11).

---

## 3) Field census (live / dead table)

**85 fields declared.** Census method: every field name extracted from state.py:15-153, then `(?<![\w.])state\.<field>\b` counted across all of `src/` **excluding this file**. Zero-hit fields are listed first.

### 3.1 Dead fields — declared, written (sometimes), never read

| Field | Declared | Written | Read anywhere? |
|---|---|---|---|
| `is_loading` | state.py:15 | — | **never** |
| `active_username` | state.py:30 | state.py:205 (dead `reset_search`) | **never** |
| `total_sites_checked` | state.py:43 | — | **never** |
| `found_count` | state.py:44 | — | **never** |
| `not_found_count` | state.py:45 | — | **never** |
| `error_count` | state.py:46 | — | **never** |
| `bulk_mode` | state.py:77 | — | **never** |

**7 dead fields.** Note the live counterparts already exist: `email_found_count` (state.py:52), `email_not_found_count` (state.py:53), `phone_found_count` (state.py:62) — so state.py:43-46 are the pre-email/phone era leftovers that were never deleted. `bulk_mode` is worse than dead: its storage key `STORAGE_BULK_MODE` (constants.py:75) is a **complete orphan** — never written, never read, in the entire codebase.

### 3.2 Dead methods

| Method | Line | Called from |
|---|---|---|
| `reset_search()` | state.py:194-237 | **nowhere** — zero call sites in `src/` or `tests/` |
| `set_enrichment()` | state.py:186-192 | **nowhere** — main.py:442-447 re-implements its cap inline instead |

**44 lines of dead method body** (`reset_search`), plus 7 lines of dead method (`set_enrichment`).

### 3.3 Live fields (78)

All remaining 78 fields have ≥1 external reference. Highest-signal ones with their consumer set:

`search_mode` (state.py:26, 62 refs) · `progress_version` (state.py:34, 44) · `is_searching` (state.py:16, 32) · `history` (state.py:91, 28) · `current_username` (state.py:29, 25) · `enrichments` (state.py:84, 18) · `search_progress` (state.py:33, 18) · `is_online` (state.py:22, 12) · `sites_version` (state.py:141, 11) · `email_timeout` (state.py:99, 10) · `no_password_recovery` (state.py:104, 10) · `phone_results` (state.py:59, 10) · `ignore_exclusions` (state.py:97, 9) · `nsfw_enabled` (state.py:96, 9) · `search_error` (state.py:35, 9) · `timeout` (state.py:98, 9) · `email_results` (state.py:50, 8) · `email_total_modules` (state.py:56, 7) · `sites_cache` (state.py:144, 7) · `selected_sites` (state.py:114, 6) · `sites_total` (state.py:138, 6) · `has_accepted_terms` (state.py:18, 5) · `is_first_launch` (state.py:17, 5) · `phone_total_modules` (state.py:64, 5) · `scan_depth` (state.py:117, 5 — but see 3.4) · `update_data` (state.py:153, 5) · …

### 3.4 Live-but-dead-end settings (state.py is the only place this can be fixed)

These fields are persisted to storage **and** restored into state **and** shown in the Settings UI — but **never reach the scan engine**. The engine call (`sherlock_service.py:200-208`) passes only: `timeout`, `concurrency` (from `max_connections`), `allow_loud`, `no_nsfw` (from `nsfw_enabled`), `selected`, `proxy` (from `proxy_url`). Everything else is dropped on the floor.

| Field | Declared | Persist key | Restored? | Reaches engine? |
|---|---|---|---|---|
| `scan_depth` | state.py:117 | `STORAGE_SCAN_DEPTH` | yes (main.py:750) | **no** |
| `retries` | state.py:131 | `STORAGE_RETRIES` | yes (main.py:800) | **no** |
| `check_domains` | state.py:111 | `STORAGE_CHECK_DOMAINS` | yes (main.py:774) | **no** |
| `use_curl_cffi` | state.py:133 | `STORAGE_USE_CURL_CFFI` (constants.py:64) | yes (main.py:808) | **no** |
| `verbose_output` | state.py:69 | `STORAGE_VERBOSE_OUTPUT` | **no** | **no** |
| `show_all_results` | state.py:68 | `STORAGE_SHOW_ALL_RESULTS` | **no** | **no** |
| `email_domains` | state.py:75 | `STORAGE_EMAIL_DOMAINS` | **no** | **no** |
| `proxy_file` | state.py:78 | `STORAGE_PROXY_FILE` | **no** | **no** |
| `safe_search` | state.py:134 | `STORAGE_SAFE_SEARCH` | yes (main.py:833) | **no** |

This **confirms and extends** the brief's "dead settings: `scan_depth`, `retries`, `check_domains`, `use_curl_cffi`, `verbose_output`" — all five are defined in this file, and all five are dead-end. Four more are in the same class.

### 3.5 Persisted-but-never-restored — the gap lives in `main.py`, the broken contract lives here

`_load_saved_state` is `src/main.py:635-851`. Restoring is done there, **not** in state.py — so the *mechanism* gap is main.py's. But **state.py is where the field contract is declared and where the field silently keeps its class default**, so the defect surfaces here: a persisted user preference is written, then the in-memory field reverts to the state.py default on every launch.

| Persist key | constants.py | State field | state.py | Written at | Restored? |
|---|---|---|---|---|---|
| `STORAGE_HUDSON` | :74 | `hudson_enabled` | **state.py:76** | home_screen.py:568 | **NO** → always `False` |
| `STORAGE_EMAIL_DOMAINS` | :73 | `email_domains` | **state.py:75** | settings_screen.py:634 | **NO** → always `""` |
| `STORAGE_PHONE_CONCURRENCY` | :77 | `phone_concurrency` | **state.py:79** | settings_screen.py:1209 | **NO** → always `15` |
| `STORAGE_SHOW_ALL_RESULTS` | :66 | `show_all_results` | **state.py:68** | settings_screen.py:606 | **NO** → always `False` |
| `STORAGE_VERBOSE_OUTPUT` | :67 | `verbose_output` | **state.py:69** | settings_screen.py:610 | **NO** → always `False` |
| `STORAGE_PROXY_FILE` | :76 | `proxy_file` | **state.py:78** | settings_screen.py:641 | **NO** → always `""` |

**Exactly 6 persisted keys never restored** — the brief's count is confirmed. A 7th, `STORAGE_BULK_MODE` (constants.py:75), is orphaned in both directions.

`STORAGE_HISTORY` (constants.py:32) is also absent from `_load_saved_state`, but is restored **lazily** at `history_screen.py:117` and `home_screen.py:785` — a deliberate different pattern, so `state.history` (state.py:91) is empty until the History tab mounts. That interacts with `history_unseen` (state.py:90), which drives the nav badge: on a cold launch the badge under-counts, because history is not yet loaded when the badge renders.

### 3.6 Duplicate / redundant state

| Duplication | Detail |
|---|---|
| `is_first_launch` (state.py:17) + `has_accepted_terms` (state.py:18) | Both set from the **same** key `STORAGE_ONBOARDING_DONE` at main.py:846-847, always equal. One is redundant. |
| `AppState.enrichments` (state.py:84) vs `AppController._pending_enrichments` (main.py:404) | Two owners of the same concept; state.py:83-84 says the cap lives in `set_enrichment`, main.py:442-447 re-implements it. |
| `total_sites_checked`/`found_count`/`not_found_count`/`error_count` (state.py:43-46) vs `email_found_count`…/`phone_found_count`… (state.py:52-63) | Legacy pre-OSINT-modes counters, all dead. |

---

## 4) NEW bugs (severity-ordered)

### B1 — HIGH — `state.target_results` is mutated from a non-UI thread; the notify path has no thread hop

**Where:** the field is declared at **state.py:32** (`target_results: dict | None = None`) and materialised as an `ObservableDict` at **state.py:164** (`self.target_results = {}`).

**Who mutates it off-thread:** `services/sherlock_service.py:154`

```python
last_prog = await asyncio.to_thread(
    self._run_worker, targets, all_modules, selected, timeout, on_progress, after_primary, app_state
)
```

`_run_worker` (sherlock_service.py:263-277) creates a **new event loop inside a real OS thread**. Inside that thread, `_run` executes **sherlock_service.py:179**:

```python
app_state.target_results[tgt] = progress
```

That is an `ObservableDict.__setitem__` → `_touch()` → `owner._notify("target_results")` → **every** component subscribed via `use_context(AppStateCtx)` gets `component._schedule_update()` **on the worker thread** (§2.3). `Session.schedule_update` (flet/messaging/session.py:663-674) then does `self.__pending_updates.add(control)` + `self.__updates_ready.set()` from that thread, concurrently with the session's update-drain on the event loop.

Note the contrast: **sherlock_service.py:163** (the same statement in `search()`, after the `await`) runs on the loop thread and is safe; **:179** (inside `_run`) does not. The bug is real but easy to mis-locate — the *enabling* declaration is state.py:32/164.

**Impact:** flet 1.0.4 has no thread affinity check, so the failure mode is silent: torn renders, cross-thread mutation of the pending-update set, and (if the drain iterates the set concurrently) `RuntimeError: Set changed size during iteration`. It is exactly the "worker-thread mutation of a flet ObservableDict" the sibling `sherlock_service` audit flagged; **the root cause is the field type chosen at state.py:32/164**.

**Fix direction:** either (a) don't store per-target progress in an observable dict — accumulate it in a plain dict in the worker and publish it on the loop thread (the app already has the right pattern: `main.py:423-467` `_render_flusher`), or (b) make the worker's writes go through a plain `dict` that the loop copies into `state.target_results` on the flusher tick. Also note `state.progress_version` (state.py:34) is the loop-side bump that makes such a copy visible.

### B2 — HIGH — `state.theme_mode` is not the source of truth for the restored theme; header and page disagree

**state.py:38** `theme_mode: ft.ThemeMode = ft.ThemeMode.LIGHT`.

`_load_saved_state` (main.py:638-644) restores the theme by writing **`self.page.theme_mode` directly**:

```python
saved_theme = await self.storage.get(STORAGE_THEME)
if saved_theme == "dark":   self.page.theme_mode = ft.ThemeMode.DARK
elif saved_theme == "system": self.page.theme_mode = ft.ThemeMode.SYSTEM
else:                        self.page.theme_mode = ft.ThemeMode.LIGHT
```

`state.theme_mode` is **never** assigned in `_load_saved_state` (verified: it is absent from the function's `state.*` assignment set). It is only written by `screens/settings_screen.py` when the user toggles the theme. Meanwhile `components/app_header.py` reads `state.theme_mode`.

**Result:** after any restart with a non-default theme, `page.theme_mode` is DARK/SYSTEM but `state.theme_mode` is still the class default `ThemeMode.LIGHT` → the header's theme control shows/derives the wrong theme until the user touches the theme picker. Two fields claiming the same fact, one of them stale.

**Fix:** make `state.theme_mode` the single source of truth (assign it in `_load_saved_state` and derive `page.theme_mode` from it), or delete `state.theme_mode` and have the header read `page.theme_mode`.

### B3 — MEDIUM — six persisted settings are silently discarded on every launch

Listed in §3.5. Each of `hudson_enabled` (state.py:76), `email_domains` (state.py:75), `phone_concurrency` (state.py:79), `show_all_results` (state.py:68), `verbose_output` (state.py:69), `proxy_file` (state.py:78) is written to storage and never read back, so the field keeps its state.py default forever. The user-visible symptom for `hudson_enabled` is the worst: the Hudson breach check (main.py:1117, main.py:1573) is **always off** after a restart even though the user turned it on (home_screen.py:566-568 persists it).

**This is a state.py contract defect**: the class advertises 6 fields that the persistence layer cannot round-trip. Fix belongs in `main.py::_load_saved_state`, but the *invariant* ("every persisted key has a field and vice versa") should be asserted next to the field declarations — ideally by a test that diffs `constants.STORAGE_*` against a declared settings table (see Improvement I3).

### B4 — MEDIUM — `set_cached_result` is FIFO mislabelled as LRU, and the persisted cache bypasses the cap entirely

**state.py:173-179**

```python
def set_cached_result(self, mode: str, query: str, data: dict) -> None:
    """Store search results with an LRU cap of 30 queries."""
    key = f"{mode}:{query.strip().lower()}"
    if len(self.results_cache) >= 30:
        oldest = next(iter(self.results_cache))
        del self.results_cache[oldest]
    self.results_cache[key] = data
```

`dict` preserves insertion order, so `next(iter(...))` evicts the **oldest-inserted**, not the **least-recently-used**. `get_cached_result` (state.py:181-184) does **not** touch recency on a hit. This is a FIFO queue documented as an LRU.

Second, larger problem: the persisted cache is restored with `state.results_cache.update(res_map)` (main.py:840) — **bypassing the 30-entry cap entirely** and **bypassing `set_cached_result`**. `STORAGE_CACHED_RESULTS` = `"sherlock_cached_results"` (constants.py:56) is the ~790 KB blob from the brief. So after every launch `state.results_cache` holds **whatever the storage blob held** (unbounded), not ≤ 30, and the cap only re-establishes itself one eviction per new insert. The `state.py:174` invariant ("LRU cap of 30 queries") is therefore false for the majority of the cache's lifetime.

Fix: make `set_cached_result` do a real LRU (pop + reinsert on hit, or `OrderedDict.move_to_end`), cap the *restored* map to 30 on load, and bound the persisted payload size.

### B5 — MEDIUM — `reset_search()` is dead code, and the invariant it documents is violated by every real caller

**state.py:194-237**. Zero call sites anywhere in `src/` or `tests/`.

Its docstring (state.py:196-199) asserts the architecture's core collection rule:

> *"Mutates assigned collections in place so existing ObservableList/ObservableDict wrappers stay attached to this state and downstream subscribers keep working."*

Every actual caller of this state **violates** that rule by **rebinding** instead of mutating:

- `main.py:228` — `state.search_targets = []` (the comment at main.py:222-227 explicitly says *"REBIND, never clear"*, directly contradicting state.py:196-199)
- `main.py:1057` — `state.last_results = merged_results`
- `main.py:1080` — `state.email_results = []`
- `sherlock_service.py:119` — `state.sites_cache = sorted(set(names))`
- `sherlock_service.py:120` — `state.sites_tags_map = {...}`
- `sherlock_service.py:141` — `app_state.target_results = {}`

A rebind **replaces** the `ObservableList`/`ObservableDict` object. Any component that captured the old object by reference now holds an orphan. The screens snapshot at render time — `results_screen.py:482` `list(state.phone_results)`, `results_screen.py:484` `list(state.email_results)`, `app_shell.py:68/71` — so a rebind between snapshot and render leaves stale rows on screen.

Two sub-issues inside the dead method itself:

- state.py:205 `self.active_username = ""` — writes a field that **nothing reads** (§3.1).
- state.py:230 `if self.phone_results is not None:` — `phone_results` is unconditionally an `ObservableList` (state.py:168), so this is a dead branch. It exists only because the annotation at state.py:59 says `list | None`.
- state.py:212 `self.last_results.clear()` — would `AttributeError` if `last_results` were `None`, which its own annotation (state.py:41, `dict | None`) permits. A type checker would flag this line.

**Action:** either delete `reset_search` and hoist its intent into a real, called `reset()`, or make it the single place that owns collection lifecycle and change the callers to mutate in place. Right now the codebase has two contradictory rules and the documented one is the one nothing follows.

### B6 — MEDIUM — `set_enrichment()` is dead, its cap logic is duplicated, and one flush path applies no cap at all

**state.py:186-192** `set_enrichment` is never called. Its cap is re-implemented inline at `main.py:442-447`:

```python
from core.state import _ENRICHMENT_CAP
while len(state.enrichments) > _ENRICHMENT_CAP:
    oldest = next(iter(state.enrichments))
    del state.enrichments[oldest]
```

Two consequences:

1. **Duplicated invariant in two places** — state.py:188 uses `>=` (evict one, then insert → max 200) while main.py:445 uses `>` in a `while` (trim to 200). They agree today, but nothing keeps them in sync.
2. **A third path applies no cap at all** — `main.py:415` in `_stop_render_flusher`:

```python
pending, self._pending_enrichments = self._pending_enrichments, {}
if pending:
    try:
        state.enrichments.update(pending)
```

   This flushes up to `len(pending)` entries into `state.enrichments` with **no** `_ENRICHMENT_CAP` trim, so `state.enrichments` (state.py:84, capped at `_ENRICHMENT_CAP` = 200 per state.py:9 and the state.py:83 comment) can exceed its documented cap by the whole pending batch — and that is exactly the flush that runs at scan end, when the pending batch is largest.

Also note `ObservableDict.update` with a positional mapping does **not** wrap nested values (§2.5), so the enrichment payloads stored via `main.py:415`/`main.py:441` are plain dicts whose nested mutation is invisible.

### B7 — MEDIUM — one corrupt persisted value aborts the remainder of the settings restore

The numeric settings are restored with bare `int(raw)` calls inside the single shared `try:` of `_load_saved_state` (main.py:635-851): `state.timeout = int(timeout_raw)` (main.py:663), `state.max_connections = int(max_conn_raw)` (main.py:796), `state.retries = int(retries_raw)` (main.py:800), `state.cross_depth = int(cd_raw)` (main.py:825), `state.cross_sweep = int(sw_raw)` (main.py:828). The single handler at main.py:849-850 is:

```python
except Exception as e:
    logger.warning("Settings load failed: %s", e)
```

So one non-numeric value in storage → `ValueError` → **every remaining setting below that line silently falls back to its state.py default** (including `safe_search`, the cached-results restore, and onboarding). The state.py field declarations (state.py:98-100, 129, 131, 73-74) declare `int` but provide **no coercion, clamping, or validation** — nothing in this file enforces the type it advertises. `state.timeout = 15` (state.py:98) also accepts a negative or a 10^9 value without complaint.

### B8 — LOW — content-equality suppresses the notify on a rebind

`Observable.__setattr__` (observable.py:211) uses `value_equal`, which for collections is content equality. So assigning a **new** `ObservableList`/`ObservableDict` whose **content equals** the old one notifies nobody — the field now points at a different object, but no subscriber re-renders. Concrete site: `sherlock_service.py:119` `state.sites_cache = sorted(set(names))` rebinds on every DB load; if the site set is unchanged, no notify fires. It happens to be masked here because `state.sites_version += 1` (sherlock_service.py:121) is bumped separately — but the general hazard stands for `target_results` (sherlock_service.py:141) and `search_targets` (main.py:228), which have **no** companion version counter.

### B9 — LOW — `results_cache` restore stores unwrapped nested values

`main.py:840 state.results_cache.update(res_map)` passes the map **positionally** → `ObservableDict.update` (observable.py:401) only wraps keyword values → the nested per-query result dicts/lists stay plain. A later in-place mutation of a cached snapshot will not notify, and the cached payload is no longer an `ObservableDict`, so a later `state.results_cache[key] = data` (state.py:179) with an already-wrapped value can compare unequal by identity but equal by content — see B8.

### B10 — LOW — the email path bypasses the render-flusher batching; N results = N full-tree re-renders

`main.py:1080` `state.email_results = []` **rebinds** (see B5), then `main.py:1091` `state.email_results.append({...})` runs **once per email result**, each `append` firing `ObservableList._touch()` → `_notify("email_results")` → **every** subscribed screen re-renders. The username path deliberately funnels scan-time mutations through a single 2 Hz flusher (main.py:423-467, whose docstring explains the cost: *"Every bump invalidates every use_context(AppStateCtx) component and re-renders + re-diffs + re-encodes the whole tree"*). The email path has no such funnel, so a 100-module email scan triggers ~100 whole-tree re-renders instead of ~2/second.

### B11 — LOW — `search_progress` is not observable, forcing the global `progress_version` invalidation

state.py:33 declares `search_progress: object | None`, and state.py:34 declares `progress_version: int = 0` as a manual re-render trigger. `SearchProgress` (sherlock_service.py:47-56) is a plain `@dataclass`, so `progress.checked_sites += 1` (sherlock_service.py:191) and `progress.found.append(sr)` (sherlock_service.py:193) are invisible to the observable. The app compensates with a counter bump, but the bump is **global**: it invalidates all subscribers, not just the progress widget. flet 1.0.4 supports `@ft.observable` on dataclasses (documented at `flet/components/observable.py:20-33`), so `SearchProgress` could be made observable and the global counter retired for progress-only updates.

### B12 — LOW — progress kinds are discriminated by attribute sniffing

`main.py:244-247` and `main.py:386-390`:

```python
prog = state.search_progress
if prog is None or hasattr(prog, "checked_modules"):   # email progress, or nothing
    return False
return bool(getattr(prog, "is_running", False))
```

The `object` annotation at state.py:33 makes this structural typing the only option. `EmailProgress` gaining a `checked_modules` attribute — or any future progress type that lacks it — flips the classification with no compile-time signal.

### B13 — LOW — `is_first_launch` and `has_accepted_terms` are one value in two fields

state.py:17-18. Both are set together from the single key `STORAGE_ONBOARDING_DONE` (main.py:846-847), so they are always equal. Two mutable fields that can never diverge is one field too many — and any future code that sets only one of them creates a state that the loader can never reproduce.

### B14 — LOW — `unhealthy_sites` and `sites_tag_index` are the only collections left un-initialised

`__init__` (state.py:155-171) initialises 11 collections to `[]`/`{}`; **`unhealthy_sites` (state.py:113)** and **`sites_tag_index` (state.py:149)** are not among them, so they remain the class default `None` until first assigned. `sites_tags_map` (state.py:146) *is* initialised (state.py:166) while its sibling `sites_tag_index` is not — an inconsistency, not a design choice. Both are read with `| None`-style guards downstream while their siblings need none.

### B15 — LOW — `is_loading` (state.py:15) is a vestigial flag

Never read, never written outside the class. Its name suggests an in-flight spinner that no longer exists — `is_searching` (state.py:16) covers that role.

---

## 5) Improvements

Ordered by value/effort.

**I1 — Delete the 9 dead members.** (highest value, ~zero risk)
Remove `is_loading` (state.py:15), `active_username` (state.py:30), `total_sites_checked` (state.py:43), `found_count` (state.py:44), `not_found_count` (state.py:45), `error_count` (state.py:46), `bulk_mode` (state.py:77), plus the `STORAGE_BULK_MODE` orphan (constants.py:75). Also delete `reset_search()` (state.py:194-237) **or** wire it up — see I2 — and `set_enrichment()` (state.py:186-192) **or** make it the single owner of the enrichment cap (see B6/I5). Deleting `reset_search` also removes the 44 lines of `| None`-typed collection handling that the type checker would otherwise flag at state.py:212 and state.py:230.

**I2 — Decide the collection-lifecycle rule and enforce it in one place.**
The codebase currently has two contradictory rules (state.py:196-199 vs main.py:222-228). Pick one — recommended: **mutate in place, never rebind** — and then replace the rebinds at main.py:228, main.py:1057, main.py:1080, sherlock_service.py:119/120/141 with in-place equivalents (`.clear()` + `.update()` / `[:] = ...`). Add a helper on `AppState` (e.g. `replace_list(field, items)`) so the rule is enforced by construction rather than by comment. This directly removes the stale-snapshot class of bug (B5, B8) and makes the "wrapper stays attached" promise in state.py:196-199 true.

**I3 — Split the class into `ScanState` and `SettingsState`, and derive the persistence contract from it.**
state.py currently mixes three lifetimes: per-scan volatile state (`current_username`, `target_results`, `email_results`, `phone_results`, `enrichments`, `last_results`), durable user settings (`nsfw_enabled` … `safe_search`, ~38 fields), and static DB data (`sites_cache`, `sites_tags_map`, `sites_tag_index`). A concrete, testable improvement: declare the settings as a typed table (e.g. a `Settings` dataclass with one `STORAGE_*` key per field) and add a test that asserts a **bijection** between the settings table and `constants.STORAGE_*`. That single test would have caught all six B3 restore gaps and the `STORAGE_BULK_MODE` orphan. Splitting the class also lets `reset_search` become a method on `ScanState` only, so it stops needing to enumerate which fields are settings.

**I4 — Fix the six restore gaps in `main.py::_load_saved_state` (main.py:635-851).**
Add restore branches for `STORAGE_HUDSON` → `state.hudson_enabled`, `STORAGE_EMAIL_DOMAINS` → `state.email_domains`, `STORAGE_PHONE_CONCURRENCY` → `state.phone_concurrency`, `STORAGE_SHOW_ALL_RESULTS` → `state.show_all_results`, `STORAGE_VERBOSE_OUTPUT` → `state.verbose_output`, `STORAGE_PROXY_FILE` → `state.proxy_file`. And move the per-key `int()` conversions into per-key `try/except` so one corrupt value no longer aborts the whole restore (B7). Better still: give state.py a typed `Settings` object with a `from_storage(mapping)` classmethod that owns the coercion (state.py is the natural home for the schema).

**I5 — Make `AppState` the single owner of the enrichment cap.**
Delete the inline mirror at main.py:442-447 and call `state.set_enrichment(...)` (state.py:186) instead — it already implements the cap. Add the missing trim to the `_stop_render_flusher` flush at main.py:415 so the cap at state.py:9 is actually honoured on every path.

**I6 — Make the result cache a real LRU with a hard bound.**
Replace the FIFO at state.py:173-179 with `OrderedDict.move_to_end` on hit (or an explicit recency bump in `get_cached_result`, state.py:181-184), cap the restored map to 30 on load (main.py:840), and bound the persisted payload size for `sherlock_cached_results` (~790 KB today).

**I7 — Make `target_results` non-observable, or make the worker publish on the loop thread.**
This is the fix for B1. Recommended: keep a plain `dict` in the worker thread, and copy it into `state.target_results` from the existing `_render_flusher` tick (main.py:423-467) — the app already has exactly the right pattern for this. If the field must stay observable, `state.target_results` should be updated only from the loop thread.

**I8 — Make `SearchProgress` observable and retire the global `progress_version` bump.**
`@ft.observable` on the dataclass at `services/sherlock_service.py:47-56` (supported per `flet/components/observable.py:20-33`) lets `progress.checked_sites += 1` notify on its own, so state.py:34's global counter can stop invalidating every subscriber on every progress tick.

**I9 — Fix the `theme_mode` split-brain.**
Pick one source of truth. Recommended: `state.theme_mode` is the field; `main.py:638-644` assigns it and a small effect propagates to `page.theme_mode`; `app_header.py` keeps reading `state.theme_mode`. This removes B2 outright.

**I10 — Coerce and clamp persisted values at the state boundary.**
state.py:98-100, 129, 131, 73-74 declare `int` fields but never validate them. Provide `__setattr__`-level coercion or a typed settings object with `max(1, min(value, cap))` bounds for `timeout`, `max_connections`, `email_timeout`, `email_concurrency`, `phone_concurrency`, `cross_depth`, `cross_sweep`. This makes B7 structurally impossible rather than a per-key try/except.

**I11 — Route the email path through the render flusher.**
Batch `state.email_results` writes and bump `progress_version` once per flush, mirroring main.py:423-467, instead of one full-tree re-render per email result (main.py:1091). See B10.

**I12 — Initialise every collection in `__init__`.**
Add `self.unhealthy_sites = []` and `self.sites_tag_index = {}` (state.py:113, state.py:149) to `__init__` (state.py:155-171) so no collection field can be `None`, and tighten the annotations from `list | None` / `dict | None` to the honest types (`list[str]`, `dict`). The `| None` annotations on 13 fields are currently lies — every one of them is non-`None` after `__init__` — and they are what produced the dead branch at state.py:230 and the checker-visible `.clear()` at state.py:212.

**I13 — Narrow the `object` annotation on `search_progress`.**
state.py:33 → a proper union (`SearchProgress | EmailProgress | PhoneProgress | None`) so `hasattr(prog, "checked_modules")` sniffing (main.py:244-247, main.py:386-390) can become a real `isinstance` check, or add an explicit `kind` discriminator field to each progress type.

**I14 — Collapse `is_first_launch` / `has_accepted_terms` into one.**
state.py:17-18 — keep `has_accepted_terms` (the persisted fact) and derive `is_first_launch` as `not has_accepted_terms`, or vice versa.

---

## 6) Verdict

**state.py is structurally sound and its flet usage is, with two exceptions, correct.** The `@ft.observable` decorator, the auto-wrapping of collections in `__init__` (state.py:155-171), and the `ObservableList`/`ObservableDict` mutation model are all verified against installed flet 1.0.4 and behave as the comments claim. No hallucinated APIs: `ft.observable`, `ft.ThemeMode.LIGHT`, `ObservableList`/`ObservableDict` semantics, `value_equal`, `use_context` auto-subscription — all confirmed in `.venv/Lib/site-packages/flet`.

**But the file has accreted a lot of unowned weight, and the design has drifted away from its own documentation.**

- **Two HIGH issues.** B1 — `state.target_results` (state.py:32/164) is an `ObservableDict` mutated from a real worker thread (sherlock_service.py:179 via `asyncio.to_thread` at :154), and flet 1.0.4's notify path (`Observable._notify` → `ObservableSubscription.__on_change` → `Component._schedule_update` → `Session.schedule_update`) contains **no thread hop**. This is the root cause the sibling `sherlock_service` audit saw as a symptom. B2 — `state.theme_mode` (state.py:38) is not the restore source of truth, so the restored theme and the header's theme disagree.
- **Six MEDIUM issues.** B3 — the brief's "6 persisted keys never restored" is **confirmed exactly**: `STORAGE_HUDSON`, `STORAGE_EMAIL_DOMAINS`, `STORAGE_PHONE_CONCURRENCY`, `STORAGE_SHOW_ALL_RESULTS`, `STORAGE_VERBOSE_OUTPUT`, `STORAGE_PROXY_FILE`. All six map to fields in this file (state.py:76, 75, 79, 68, 69, 78); the restore code lives in `main.py::_load_saved_state` (main.py:635-851), so the *gap is main.py's* but the *broken field contract is state.py's*. A 7th key, `STORAGE_BULK_MODE` (constants.py:75), is orphaned in both directions. B4 — `set_cached_result` is FIFO mislabelled LRU (state.py:173-179), and the ~790 KB `sherlock_cached_results` blob is restored past the 30-cap (main.py:840). B5 — `reset_search()` (state.py:194-237, 44 lines) is **called from nowhere**, and its documented in-place-mutation invariant (state.py:196-199) is violated by every real caller (main.py:228, main.py:1057, main.py:1080, sherlock_service.py:119/120/141), which rebind instead. B6 — `set_enrichment()` (state.py:186-192) is **called from nowhere**; its cap is duplicated at main.py:442-447 and **skipped entirely** on the flush path at main.py:415. B7 — one corrupt persisted int aborts the whole settings restore (main.py:663/796/800/825/828 inside the shared `try` closed at main.py:849-850), because state.py validates nothing it declares.
- **The brief's "dead settings" claim is confirmed and understated.** `scan_depth` (state.py:117), `retries` (state.py:131), `check_domains` (state.py:111), `use_curl_cffi` (state.py:133) and `verbose_output` (state.py:69) are all defined here, all persisted, all restored — and **none reaches the scan engine** (`sherlock_service.py:200-208` passes only `timeout`, `max_connections`, `allow_loud`, `nsfw_enabled`, `selected_sites`, `proxy_url`). Four more are in the same class: `show_all_results` (state.py:68), `email_domains` (state.py:75), `proxy_file` (state.py:78), `safe_search` (state.py:134). `use_curl_cffi` ↔ constants.py:64 confirmed as the dead stealth toggle.
- **Seven fields are pure dead weight** (§3.1) and **two methods (51 lines) are never called** (§3.2). The `| None` annotations on 13 collections are false — every one is non-`None` after `__init__` — and they produced the dead branch at state.py:230 and the `Optional`-unsafe `.clear()` at state.py:212.
- **Overlap with siblings: none.** `src/state/app_state.py` (7 lines) declares no fields; `src/state/controller_ctx.py` declares no state fields. The only conceptual duplication is `AppState.enrichments` (state.py:84) vs `AppController._pending_enrichments` (main.py:404).

**Bottom line:** nothing here is broken at import time and the flet API usage is genuine, but `state.py` is a 85-field grab-bag with two dead methods, seven dead fields, nine settings that persist but never reach the engine, a thread-safety hole on `target_results`, a split-brain theme field, and a documented collection invariant that no caller obeys. The highest-leverage fix is not a patch but a split: **separate durable settings from volatile scan state, give the settings a typed persistence table with a round-trip test, and move per-target progress off the observable dict onto the existing render-flusher path.**
