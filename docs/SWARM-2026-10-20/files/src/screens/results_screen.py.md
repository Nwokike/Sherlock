# Audit — `src/screens/results_screen.py`

**File:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/screens/results_screen.py` (1,035 lines)
**Ground truth:** flet 1.0.4, user-scanner 1.5.2.3, phonsint 0.1.0 — all from `.venv\Lib\site-packages`
**Scope:** this file only. Read-only audit; no file was modified.

---

## 1. File role

`ResultsScreen` is the single `@ft.component` (line 298) that renders live scan output for all three OSINT modes (username / email / phone). It is mounted by `src/app_shell.py:914` whenever `active_view == "results"`.

Key structural facts that drive every finding below:

* The component body is a **pure render function** that rebuilds the entire `ft.Column` tree on every tick. It re-renders at ~2 Hz because `src/main.py:423-450` (`_render_flusher`) bumps `state.progress_version` every 0.5 s while a scan is dirty; the screen subscribes by touching `state.progress_version` at line 304.
* It is a **dual-purpose screen**: one component serves three engines with three *different progress-object contracts* (sherlock `SearchProgress`, holehe `EmailSearchProgress`, phonsint `PhoneSearchProgress`). The username branch is defended by an explicit normalizer (lines 35-105); the email/phone branch is **not**.
* It reads/writes shared global state (`core/state.py` — `@ft.observable AppState`) and drives side effects (`core.tasks.spawn`, `shared_url_launcher`, `shared_haptics`).

---

## 2. API verification summary

Every flet control, field, enum, hook and service used by this file was resolved against the installed flet 1.0.4 source. **No flet API hallucinations were found.** Detail:

| API used | Line(s) | flet 1.0.4 source | Verdict |
|---|---|---|---|
| `ft.Tabs(length, selected_index, on_change, content, expand)` | 617-663, 826-870 | `flet/controls/material/tabs.py:165-269` | OK |
| `ft.Tabs.before_update` range check | (clamp rationale 108-118) | `tabs.py:263-269` — raises `IndexError` outside `[-length, length-1]` | Confirms the `clamp_tab_index` helper is necessary and correct |
| `ft.TabBar(tabs, scrollable, indicator_color, label_color, unselected_label_color, label_padding)` | 623-648, 832-850 | `tabs.py:366-503` — all six fields exist | OK |
| `TabBar` `scrollable=False` + `tab_alignment=None` | 636, 838 | `tabs.py:583-603` — `None` is legal for both scrollable modes | OK |
| `ft.Tab(label=...)` | 625-634, 834-836 | `tabs.py:606-652` | OK |
| `ft.TabBarView(controls, expand)` | 649-657, 851-864 | `tabs.py:323-352` | OK |
| `ft.ListView(controls, spacing, expand, build_controls_on_demand)` | 290-295 | `flet/controls/core/list_view.py:32, 55, 127` | OK — but `build_controls_on_demand` **already defaults to `True`** (`list_view.py:127`), so passing it is redundant |
| `ft.TextField(text_size, content_padding, border{ControlState→OutlineInputBorder}, prefix_icon, filled, bgcolor, height, hint_text, value, on_change)` | 933-957 | verified via `inspect.signature(ft.TextField.__init__)` — all present | OK |
| `ft.ProgressBar(value, color, bgcolor, height)` | 985-992 | `flet/controls/material/progress_bar.py:25-60` | OK, but `value` is validated `V.ge(0)` only — **no upper bound** (see N5) |
| `ft.TextButton(content=ft.Text(...), on_click=...)` | 1003-1011 | `content: str \| Control \| None` confirmed | OK |
| `ft.Colors.with_opacity` | 639-641, 841-843, 921, 941-943, 989, 998, 1057 | `flet/controls/colors.py:110` | OK |
| `ft.Icons.SEARCH_OFF_ROUNDED`, `ft.Icons.FILTER_LIST_ROUNDED` | 255, 936 | verified present | OK |
| `ft.OutlineInputBorder`, `ft.BorderSide`, `ft.ControlState`, `ft.Padding`, `ft.Margin`, `ft.Border.all` | 937-951, 919-925, 959-964 | verified present | OK |
| `ft.use_state` → `(value, setter)` | 327, 329 | `flet/components/hooks/use_state.py:48-118` | OK |
| `ft.use_ref(callable_initializer)` | 334-335 | `flet/components/hooks/use_ref.py:38-68` — callable resolved once at hook creation | OK — the "stable placeholder" trick at 330-335 is correct |
| `ft.use_memo(calculate_value, dependencies)` | 599-616, 803-820 | `flet/components/hooks/use_memo.py:25-68` — shallow dep compare | OK — but see N7 (deps are eager) |
| `ft.Page.pop_dialog` | 385, 415 | verified present | OK |
| `flet.context.page` | 356, 377, 407 | `flet/controls/context.py:64` — **raises `RuntimeError`** when unbound, does not return `None` | See N11 |
| `ft.UrlLauncher.launch_url(url)` | 353 | verified present | OK |
| `ft.HapticFeedback.light_impact()` | 383, 413 | verified present | OK |
| `ResultCard(...)` — all 20 kwargs used | 518-531, 717-737 | `src/components/result_card.py:103-127` | OK — and it calls `on_tap()` with **no** args (`result_card.py:154-155`), so the `lambda item=r:` default-arg trick at 524/724 is correct |
| `show_profile_detail_dialog(...)` — all kwargs used | 391-402, 417-434 | `src/components/profile_detail_dialog.py:1094-1111` | OK |
| `EmptyState(title, message, icon)` | 250-256 | `src/components/empty_state.py:18-24` | OK |
| `StatCard(label, value, color, on_click)` | 674-697, 874-893 | `src/components/stat_card.py:12-17` | OK |
| `controller.cancel_email_search` / `controller.cancel_phone_search` | 712 / — | `src/main.py:1713`, `src/main.py:1849`, `src/state/controller_ctx.py:59, 61` | Both exist — see **N2** (the wrong one is used) |
| `core.tasks.spawn(coro)` | 360, 368-372, 383, 413 | `src/core/tasks.py:18-31` | OK |
| `core.shared_services.shared_url_launcher / shared_haptics` | 350, 381 | `src/core/shared_services.py:82-99` | OK |

**Hook-order audit (confirmed sound).** The file's own claim at 576-577 — "exactly one `use_memo` per branch keeps the hook slot stable across email↔username mode switches" — is **correct**. The hook prefix is identical in both branches: `use_state` (327) → `use_debounce`→`use_state`+`use_ref`+`use_effect` (328) → `use_state` (329) → `use_ref` (334) → `use_ref` (335) → `use_memo` (599 *or* 803). No conditional hooks, no slot drift.

---

## 3. Confirmed known bugs (verdicts)

### K1 — CRITICAL — **CONFIRMED (and worse than reported)**

`src/screens/results_screen.py:475-476`
```python
raw_rate_limited = [_to_dict(r) for r in active_progress.rate_limited]
raw_unavailable  = [_to_dict(r) for r in active_progress.unavailable]
```

**The mismatch table — progress-field contract:**

| Field read by results_screen | Line | `SearchProgress` (username, `src/services/sherlock_service.py:47-57`) | `EmailSearchProgress` (email, `src/services/email_service.py:51-61`) | `PhoneSearchProgress` (phone, `src/services/phone_service.py:38-47`) |
|---|---|---|---|---|
| `found` | 473 | ✅ `found` | ✅ `found` | ✅ `found` |
| `not_found` | 474 | ✅ `not_found` | ✅ `not_found` | ✅ `not_found` |
| `errors` | (not read in email branch) | ✅ `errors` | ❌ **no `errors`** | ✅ `errors` |
| **`rate_limited`** | **475** | ❌ absent | ✅ `rate_limited` (`:58`) | ❌ **ABSENT** |
| **`unavailable`** | **476** | ❌ absent | ✅ `unavailable` (`:59`) | ❌ **ABSENT** |
| `total_modules` | 477 | ❌ absent | ✅ `total_modules` (`:54`) | ✅ `total_modules` (`:41`) |
| `checked_modules` | 479 | ❌ absent | ✅ `checked_modules` (`:55`) | ✅ `checked_modules` (`:42`) |
| `total_sites` | (username branch, 66) | ✅ `total_sites` (`:51`) | ❌ absent | ❌ absent |
| `checked_sites` | (username branch, 68) | ✅ `checked_sites` (`:52`) | ❌ absent | ❌ absent |
| `email` | 425 | ❌ | ✅ `email` (`:53`) | ❌ |
| `phone` | 320, 425 | ❌ | ❌ | ✅ `phone` (`:40`) |

**Why it fires on phone scans.** The branch gate at line 444 is `hasattr(active_progress, "checked_modules")` — and `PhoneSearchProgress.checked_modules` **exists** (`phone_service.py:42`). So a phone scan enters the *email* contract. The mode detector at 320 correctly identifies phone (`hasattr(active_progress,"phone") and not hasattr(active_progress,"email")` → `True`), but the code then routes phone into the email branch anyway (443). The result: `AttributeError: 'PhoneSearchProgress' object has no attribute 'rate_limited'` on **every** phone-mode render.

**It is not limited to the live scan.** `state.search_progress` keeps the `PhoneSearchProgress` object after the scan ends (`src/main.py:1756` live, `src/main.py:2031` history restore), and `state.reset_search()` is the only thing that nulls it. So the phone Results screen is broken for the *whole session after any phone scan*, not merely during one.

**Impact on the UI.** The exception is raised inside the component body. In flet 1.0.4:
* `flet/components/component.py:116-183` — `Component.update()` / `before_update()` call `Renderer(self).render(self.fn, ...)` with **no `try/except`**.
* `flet/messaging/session.py:719-720` — `__updates_scheduler` runs `for control in pending_updates: control.update()` with **no `try/except`**.

So the exception **kills the session's update task** and the UI freezes permanently. This is exactly the failure mode the file's own comment at 262-272 warns about ("a raise inside a component's render ends that loop permanently and silently, so the whole UI freezes mid-scan and nothing is logged"). If the raise instead happens inside a `CONTROL_EVENT` dispatch, flet catches it (`flet/messaging/session.py:458-465`) and calls `session.error()` → `SESSION_CRASHED` (`session.py:592-597`); the app's only handler is `src/main.py:2322 on_error` (wired at `src/main.py:2413`), which logs and shows the generic `ERR_GENERIC` snackbar. Either way the real cause is invisible to the user.

**Structurally wrong even if the attribute read is made safe.** `src/services/phone_service.py:184-185`:
```python
if res.rate_limit or res.unavailable:
    progress.errors.append(res)
```
Phone mode collapses rate-limited **and** unavailable rows into a single `errors` bucket, which the email branch has no tab for. See N1.

**Note the asymmetry:** the username branch got a dedicated normalizer for exactly this class of bug (lines 35-105, whose docstring names the v2.0.0 "email→username hang"). The email/phone branch got none. That is the gap.

---

### K2 — **PARTIALLY CONFIRMED / DOWNGRADED**

`src/screens/results_screen.py:620` and `:829`
```python
on_change=lambda e: set_tab_index(e.control.selected_index),
```

* **CONFIRMED (the API is the wrong shape):** `Tabs.on_change` is documented as *"Called when `selected_index` changes"* (`flet/controls/material/tabs.py:255-261`) — a **change notification**. The user-intent hook is `TabBar.on_click` (`tabs.py:563-569`), whose docstring states *"The `flet.Event.data` property of the event handler argument contains the index of the clicked tab."* The code also reads the index off `e.control.selected_index` rather than the documented `e.data`.
* **REFUTED (no feedback loop, and it does fire on a user tap):** flet only dispatches `on_*` handlers from an explicit `CONTROL_EVENT` message (`flet/messaging/flet_socket_server.py:400-406`). A Python-side assignment to `selected_index` does **not** dispatch an event — `apply_patch` → `patch_dataclass` (`flet/messaging/session.py:303-312`) has no event dispatch, and the stat-card buttons (678/684/690/696, 878/884/890) set React state rather than the control. So `on_change` fires only on client-side interaction, and the `use_state` setter's `new_value != hook.value` guard (`use_state.py:111`) prevents any loop.
* **REMAINING REAL RISK:** the handler depends on the client having *already* patched `selected_index` back into the Python control before the `CONTROL_EVENT` arrives — two separate wire messages (`UPDATE_CONTROL_PROPS` then `CONTROL_EVENT`, `flet_socket_server.py:400-410`). The guaranteed, documented carrier of the index is `Event.data`.
* **Recommended:** bind `ft.TabBar(..., on_click=lambda e: set_tab_index(int(e.data)))` and drop `Tabs.on_change`; or, minimally, `on_change=lambda e: set_tab_index(int(e.data))`.

---

### K3 — **CONFIRMED**

`src/screens/results_screen.py:1031` — `build_banner_ad()` (imported at `:20`) is called **directly**, bypassing the pool.

* `src/components/banner_ad.py:68-108` — `build_banner_ad()` constructs a brand-new `fta.BannerAd` on every call.
* `src/components/banner_ad.py:44-54` — `pooled_banner_ad(slot)` caches one control per slot key.
* Every other screen uses the pool: `src/screens/history_screen.py:470`, `src/screens/home_screen.py:1375, 1408`, `src/screens/sites_screen.py:770`.
* Because the whole `return ft.Column(...)` (1025-1035) is rebuilt on every 2 Hz tick, a live scan on **mobile** fires a fresh ad request ~2×/second. The file's own comment at 337-339 states the pool exists precisely to prevent this.

---

### K4 — **CONFIRMED, with a concrete phone-mode failure the report did not name**

`src/screens/results_screen.py:416` (and the identical f-string at `:522`)
```python
domain_url = f"https://{r.get('domain', '')}" if r.get("domain") else None
```

The f-string is unvalidated, **and in phone mode the "domain" is not a domain at all**:
* `results_screen.py:446-459` — `_to_dict` maps a `PhoneResult` to `{"domain": r.category, ...}`.
* `src/services/user_scanner_compat.py:52-58` — `load_phone_modules()` returns `[(cat_name.capitalize(), mod) ...]`.
* phonsint's categories are `['auth', 'crm', 'shopping', 'social']` → `PhoneResult.category` is `"Social"`, `"Shopping"`, `"Auth"`, `"Crm"`.

So the phone card's `url_main` is literally **`"https://Social"`**, and `show_profile_detail_dialog(url_main=domain_url)` (`:427`) receives the same garbage. The "open profile" action launches a non-existent host. The real per-site URL is already available on `PhoneResult.url` (`src/services/phone_service.py:32, 79`) and is currently buried in `others["url"]` (`:458`) instead of being used as `url_main`.

---

## 4. NEW bugs / hallucinations (severity-ordered)

### N1 — CRITICAL — phone mode has no bucket mapping, so results are silently under-reported

The email branch (444-571) assumes four independent progress lists. `PhoneSearchProgress` exposes only `found` / `not_found` / `errors` (`phone_service.py:43-45`), and `phone_service.py:184-185` routes rate-limited **and** unavailable rows into `errors`. Correct phone mapping:

* `found` ← `progress.found`
* `not_found` ← `progress.not_found`
* `rate_limited` ← `[r for r in progress.errors if r.rate_limit]`
* `unavailable` ← `[r for r in progress.errors if r.unavailable and not r.rate_limit]`

Consequence once K1 is fixed: the "Rate Limited" and "Unavailable" stat cards (`:688`, `:696`) and tabs (`:629-634`) are permanently `0` in phone mode, and every rate-limited/unavailable row is **invisible** — the email branch has no Errors tab, so those rows are dropped from the UI entirely.

### N2 — HIGH — the Cancel button does not cancel a phone scan

`src/screens/results_screen.py:711-712`
```python
def cancel_callback(e):
    controller.cancel_email_search()
```
This is the branch phone mode also takes (443). `controller.cancel_phone_search` **exists** (`src/main.py:1849`, `src/state/controller_ctx.py:61`) but is never called from this screen. In phone mode the Cancel button (`:1003-1011`) targets the email service and is a no-op.

### N3 — HIGH — no phone branch exists; phone mode is mis-detected as email mode

* `:320` `is_phone_progress = hasattr(active_progress, "phone") and not hasattr(active_progress, "email")` → `True` for `PhoneSearchProgress`.
* `:321-322` `is_email_mode = hasattr(active_progress, "checked_modules") and not is_phone_progress` → `False`; `is_phone_mode = is_phone_progress` → `True`.
* `:325` (not-running branch) `is_email_mode = (state.search_mode == MODE_EMAIL) or is_phone_mode` → **`True`** in phone mode.

Net effect: `is_email_mode` is `True` while a phone scan is displayed, so the filter hint at `:929-931` reads *"Filter by platform, domain, or recovery hint..."* for a phone scan, and the branch at 444 selects the **email** progress contract for a **phone** progress object. The three progress contracts are structurally different (see the K1 table) and the screen has no branch that honours them separately.

### N4 — MEDIUM — a Settings toggle named for email silently empties three phone tabs

`:537-541` reads `state.email_only_found` — a *Settings* switch (`src/screens/settings_screen.py:471-472, 1020-1021`, persisted under `STORAGE_EMAIL_ONLY_FOUND` / `sherlock_email_only_found`, `src/core/constants.py:45`). Because phone mode rides the shared email/phone branch, the switch also blanks **Not Found / Rate Limited / Unavailable** for phone scans. A "found only" view of a phone scan also loses the rate-limit signal, which is the only signal that the scan was throttled.

### N5 — MEDIUM — the percentage can exceed 100 % and the progress-bar value can exceed 1.0

* `:708` / `:909` — `pct = int(checked / max(total, 1) * 100)`, **no upper clamp**.
* `:979` — `progress_val = checked / total`, **no upper clamp**.

The denominators are fallbacks: `3300` (`:67`, `:88`) and `121` (`:478`, `:501`, `:503`). In the email branch, if `total_modules` is still `0` while `checked_modules` is already non-zero, `total` collapses to `121` while `checked` keeps climbing → *"Checking 300/121 platforms (247%...)"* and a saturated bar. flet 1.0.4 does **not** raise here: `ProgressBar.value` is validated `V.ge(0)` only (`flet/controls/material/progress_bar.py:25-28`), and the docstring notes the client clamps to `[0.0, 1.0]`. So it is a display bug, not a crash.

### N6 — MEDIUM — the render path is only half-protected

The `try/except` at `:273-281` guards **only** `build_card(row)`. Everything else runs unprotected:

* filters `:558-565`, `:757-759`
* sorts `:568-571`, `:762-764`
* fingerprints `:611-614`, `:815-818` (these *are* internally `try/except`-wrapped at `:130-147` / `:157-175` / `:185-198` — but they then return a degenerate `(len(rows),)` tuple, which silently disables memo invalidation)
* key builders `:543-556`, `:739-755`

A single malformed row (non-`str` `name`/`domain`) raises `AttributeError` on `.lower()` at `:568-571` or `TypeError` in `" ".join(parts)` at `:556` → the same scheduler-killing path as K1. The username branch is largely safe because it uses `getattr` with defaults everywhere (`:718-736`, `:739-755`); **the email/phone branch is the exposed one**, and it is the branch that consumes externally-shaped dicts.

### N7 — MEDIUM — the memo does not cover the expensive per-tick work

`use_memo` dependency lists are **eagerly evaluated** on every render (`use_memo.py:64` compares them after they are built). So each 2 Hz tick pays, before the memo is even consulted:

* 4× `_email_fingerprint` over the four result lists (`:611-614`) — 10 field reads per row each;
* 4× `_filter_by_name` (`:558-565`) — one joined key string per row each;
* 4× `.sort()` (`:568-571`) — O(N log N) each, **even when nothing changed**;
* plus, in the username branch, `_resolve_username_view_data` re-copies `found`/`not_found`/`errors` (`:63-65`) and runs 3 filters + 3 sorts (`:757-764`).

The memo only avoids re-building the *card trees*. With a 5,200-result set (the size the repo itself cites at `src/app_shell.py:881`) this is ~8 O(N) passes + 4 O(N log N) sorts **per tick**, at 2 Hz.

### N8 — MEDIUM — the virtualization claim is false

The docstring at `:236-246` says *"Performance is handled by ListView virtualization (build_controls_on_demand, only visible cards are materialized)"*, and `:288-289` repeats *"cards materialize lazily as the user scrolls"*. On the **Python** side all N cards are constructed in the `_cards()` loop (`:273-281`) **before** the `ft.ListView` is created (`:290`). `build_controls_on_demand` only affects the Flutter-side layout of an already-serialized control list (`flet/controls/core/list_view.py:127-133`). The expensive part — `ResultCard` control-tree construction — is therefore *not* lazy, and the comment misleads anyone reasoning about the 2 Hz cost.

### N9 — MEDIUM — a pooled control is simultaneously owned by the global pool and a live tree

`:340-343` / `:285` — `pooled_banner_ad(f"results-{ordinal}")` returns the **same** `Control` instance from the module-global pool on every render (`src/components/banner_ad.py:44-54`), and `_build_result_list` inserts it into a freshly constructed `ft.ListView` (`:290`) each time the memo recomputes. The same pattern exists at `src/screens/sites_screen.py:770`, so it is an accepted repo pattern — but the banner instance is double-owned, and `clear_banner_pool` (`banner_ad.py:57-65`) exists precisely because pooled controls carry the page they were built under.

### N10 — LOW — `banner_at=None` default is a landmine

`:234` declares `banner_at=None`, but `:285` calls `banner_at(ordinal)` unconditionally → `TypeError: 'NoneType' object is not callable` if the default is ever used. Both current call sites (`:606`, `:810`) pass `_banner_at`, so it is currently unreachable — the signature is simply wrong.

### N11 — LOW — `flet.context.page` raises instead of returning `None`

`:356`, `:377`, `:407` read `context.page`. In flet 1.0.4 `flet.context.page` **raises** `RuntimeError("The context is not associated with any page…")` when unbound (`flet/controls/context.py:64`) — it does not return `None`. The `if not page: return` guards (`:378`, `:408`) therefore never observe a `None`; a post-teardown event raises instead of returning cleanly. The `contextlib.suppress(Exception)` blocks (`:380-385`, `:410-415`) protect `page.pop_dialog()` but **not** the `context.page` read that precedes them.

### N12 — LOW — a phone number can be passed as the email dossier target

`:424-425` falls back to `active_progress.phone` when the progress object has no `.email`. In the email branch that yields a **phone number** as `target_query` for an email dossier. Reachable exactly in the mis-routed case of N3 (phone progress, `state.email_results_address` empty).

### N13 — LOW — the username stat cards bypass the shared `_goto_tab` helper

The email branch defines `_goto_tab` (`:668-669`) and uses it (`:678`, `:684`, `:690`, `:696`); the username branch calls `set_tab_index` directly (`:878`, `:884`, `:890`). Cosmetic inconsistency only.

### N14 — LOW — module docstring drift

`:5-6` says email mode shows *"Found / Not Found / Rate Limited tabs"* — there are **four** tabs (Found / Not Found / Rate Limited / Unavailable, `:624-634`) — and names *"holehe"* while the engine is holehe-v2 / user-scanner.

### N15 — LOW — `.sort()` mutates the list returned by `_filter_by_name` in place

`:438-439` — `_filter_by_name` returns the **same list object** when the query is empty. `:568-571` then calls `.sort()` on it. Today this is safe (`raw_found` etc. are fresh comprehensions at `:473-498`), but it is a latent aliasing hazard if any of those lists is ever assigned from a state-owned list. `sorted(...)` would remove the class of bug.

### N16 — LOW — dead `"Illegal"` status in the fallback bucketing

`:77-86` buckets on `"Claimed" / "Available" / "Illegal"`. The installed engine never produces `"Illegal"` — `user_scanner.core.result.Status` is `TAKEN / AVAILABLE / ERROR / SKIPPED` (`.venv/Lib/site-packages/user_scanner/core/result.py:68-73`), and `sherlock_service._map_username_result` (`src/services/sherlock_service.py:306-318`) emits only `"Claimed" / "Available" / "Skipped" / "WAF" / "Error"`. The live path (`:65`) uses the engine's own buckets, so this only affects the post-scan fallback (`:75-92`) — where `"Illegal"` is dead code that misrepresents the engine contract.

### N17 — LOW — status-colour mapping is inconsistent between the stat card and the row

`ResultCard._status_icon_and_color` (`src/components/result_card.py:61-75`) renders `"Unavailable"` as a **muted/dim** chip, and the chip colour map (`result_card.py:132-148`) also treats it as neutral. But the results screen's stat card maps `"Unavail"` to `AppColors.ERROR` (`:696`) — red. The summary says "severe" while every row says "unremarkable".

### N18 — LOW — the fingerprint's failure mode silently disables memoisation

`:130-147`, `:157-175`, `:185-198` each fall back to `return (len(rows or []),)` on exception. A transient exception therefore yields a *length-only* fingerprint, which can compare equal to the previous one and silently keep a **stale** card list — exactly the bug the `_email_fingerprint` docstring (`:121-129`) was written to prevent.

### N19 — INFO — the "stable placeholder" trick is correct

`:330-335` — verified against `flet/components/hooks/use_ref.py:54-61`: the callable initializer is resolved **once** at hook creation, so the four placeholder `Container`s keep a stable identity across renders and `TabBarView` child churn is avoided. The comment's claim that fresh `Container`s caused a "RangeError storm" cannot be independently confirmed from the installed Python source, but the *mechanism* is sound. **No action.**

---

## 5. Improvements (all flet-1.0.4-verified)

1. **Make the progress read capability-based, not class-based** (fixes K1 + N1). Replace the gate at `:444` and the reads at `:475-476`:
   ```python
   if active_progress and hasattr(active_progress, "checked_modules"):
       raw_rate_limited = [_to_dict(r) for r in getattr(active_progress, "rate_limited", [])]
       raw_unavailable  = [_to_dict(r) for r in getattr(active_progress, "unavailable", [])]
       if is_phone_mode:  # PhoneSearchProgress has only `errors`
           raw_rate_limited = [_to_dict(r) for r in active_progress.errors if r.rate_limit]
           raw_unavailable  = [_to_dict(r) for r in active_progress.errors
                               if r.unavailable and not r.rate_limit]
   ```
   `getattr` with a default is the cheapest possible fix and eliminates the whole class of crash.

2. **Add a phone branch** (fixes N3) so `is_email_mode` / `is_phone_mode` are mutually exclusive, and derive `is_email_mode` at `:325` as `(state.search_mode == MODE_EMAIL) and not is_phone_mode`.

3. **Use `TabBar.on_click` with `Event.data`** (fixes K2). `TabBar.on_click` exists in flet 1.0.4 (`tabs.py:563-569`) and carries the clicked index on `e.data`:
   ```python
   ft.TabBar(tabs=[...], on_click=lambda e: set_tab_index(int(e.data)), ...)
   ```
   and drop `Tabs.on_change` (or keep it as `on_change=lambda e: set_tab_index(int(e.data))`).

4. **Pool the footer banner** (fixes K3): `pooled_banner_ad("results-footer")` instead of `build_banner_ad()` at `:1031`, and change the import at `:20`.

5. **Open real phone profile URLs** (fixes K4): in `_to_dict` (`:446-459`) keep `r.url`, and pass `url_main = r.url or None` to `ResultCard` (`:522`) and to `show_profile_detail_dialog` (`:427`) instead of the `f"https://{domain}"` f-string. For the email path, keep the f-string but validate it (`domain` must contain a `.`).

6. **Clamp the percentage and the bar** (fixes N5): `pct = min(100, int(checked / max(total, 1) * 100))` and `progress_val = min(1.0, checked / total)`.

7. **Make the Cancel button mode-aware** (fixes N2): `:711-712` → `controller.cancel_phone_search()` when `is_phone_mode`, else `controller.cancel_email_search()`.

8. **Memoize the filter+sort, not just the card list** (fixes N7). Either fold the filter/sort into the same `use_memo` (`:599`, `:803`), or better: replace the four O(N) fingerprints with a cheap **revision counter** owned by the engine (e.g. `progress.checked_sites` + list lengths), so a tick that changed nothing costs O(1) instead of 8 O(N) passes + 4 O(N log N) sorts.

9. **Use the ListView knobs flet 1.0.4 already provides** (N8/N7): `ft.ListView(..., item_extent=<card height>, first_item_prototype=True)` — `item_extent` at `list_view.py:60-68` and `first_item_prototype` at `:70-76` make the lazy layout cheap and uniform. Also drop the redundant `build_controls_on_demand=True` (already the default at `list_view.py:127`) and correct the docstring at `:236-246` / `:288-289` so it no longer claims Python-side laziness.

10. **Normalise rows once** (fixes N6): in `_to_dict` (`:446-471`) coerce `name` / `domain` to `str` and coerce `others` to `dict`, so `:568-571` and `:556` cannot raise. Add one `try/except` around the whole filter+sort+fingerprint block as a belt-and-braces guard, mirroring the existing row-level guard at `:273-281`.

11. **Guard `context.page`** (fixes N11): replace `page = context.page` with a helper that swallows the `RuntimeError` raised by `flet/controls/context.py:64`:
    ```python
    try:
        page = context.page
    except Exception:
        return
    ```

12. **Tighten the fingerprint failure mode** (fixes N18): on exception, return a value that is *never* equal to a previous one (e.g. `("__error__", time.monotonic_ns())`) so a transient error forces a rebuild rather than silently keeping a stale list.

13. **Cleanups:** drop the dead `"Illegal"` status (`:77-86`, N16); reuse `_goto_tab` in the username branch (`:878-890`, N13); use `sorted(...)` instead of `.sort(...)` (`:568-571`, `:762-764`, N15); give `banner_at` a `lambda _o: ft.Container(width=0, height=0)` default instead of `None` (`:234`, N10); move the `pooled_banner_ad` import to module scope (`:341`, alongside the existing `:20` import).

---

## 6. Verdict

**SHIP-BLOCKING for phone mode.**

* **1 CRITICAL crash** (K1) — `results_screen.py:475-476` reads `rate_limited`/`unavailable` off `PhoneSearchProgress`, which has neither (`src/services/phone_service.py:38-47`). Reached because the gate at `:444` tests `checked_modules`, which phone *does* have. The raise lands in an unguarded flet render (`flet/components/component.py:116-183`, `flet/messaging/session.py:719-720`) and kills the update loop — the same "frozen UI, no log" failure the file's own comment at `:262-272` documents. It is not confined to the live scan: the phone results screen stays broken for the rest of the session.
* **1 CRITICAL data-loss bug** (N1) — phone rate-limited/unavailable rows live in `progress.errors` (`phone_service.py:184-185`) and have no home in the 4-tab email layout, so they are invisible.
* **1 HIGH functional bug** (N2) — the Cancel button calls `cancel_email_search()` (`:712`) in phone mode; `cancel_phone_search` (`src/main.py:1849`) is never used.
* **1 HIGH structural bug** (N3) — there is no phone branch; phone mode is routed through the email contract, which is the root cause of K1 and N1.
* **~5 MEDIUM** (N4-N9) — a settings toggle leaking across modes, unclamped percentages, a half-protected render path, O(N)-per-tick work the memo does not cover, a false virtualization claim, and a double-owned pooled control.
* **~10 LOW/INFO** (N10-N19).

**Positive findings worth recording:** there are **zero flet API hallucinations** in this file — every control, field, enum, hook and service resolves correctly in flet 1.0.4 (full table in §2). The username branch's `_resolve_username_view_data` normalizer (`:35-105`) is a genuinely good pattern that should be extended to the email/phone branch. The hook ordering is correct and stable across mode switches (`:576-577` claim verified). The `clamp_tab_index` helper (`:108-118`) correctly addresses a real flet 1.0.4 behaviour (`tabs.py:263-269` raises `IndexError` on an out-of-range `selected_index`).

**Estimated remediation:** ~40 lines in the email/phone branch (K1 + N1 + N2 + N3) plus ~8 one-line fixes elsewhere (K2, K3, K4, N5). All are flet-1.0.4-verified as described in §5.
