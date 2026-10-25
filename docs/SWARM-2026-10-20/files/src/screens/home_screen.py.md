# Audit — `src/screens/home_screen.py` (1,494 lines)

Auditor: file-audit subagent · Sherlock V3 · 2026-10-20
Truth sources: `.venv/Lib/site-packages/flet` (1.0.4), `user_scanner` (1.5.2.3), `phonsint` (0.1.0), `phonenumbers` (9.0.41).
Method: read-only. Every flet control/field was **constructed** against the installed flet to prove validity, not inferred from docs.

---

## 1) File role

`HomeScreen` (`src/screens/home_screen.py:359-360`) is the app's scan-launch dashboard. It is a declarative `@ft.component` that renders, top to bottom:

- an offline banner (`:997-1017`),
- a hand-rolled 3-way mode switcher — Username / Email / Phone (`:1019-1147`),
- an `ft.SearchBar` with history suggestions (`:1149-1255`),
- a `TargetsCard` network-scope summary, username mode only (`:1257-1267`),
- a horizontally scrolling row of **quick-setting chips** whose contents depend on `state.search_mode` (`:802-955`),
- a primary Search button (`:1285-1328`),
- three most-recent search rows (`:1329-1373`),
- two pooled banner ads, feature cards, "How It Works" steps, and a privacy trust banner (`:1374-1475`).

It is also the app's **quick-settings surface**: 11 of the 13 `state.*` toggles it writes (`scan_depth`, `timeout`, `phone_concurrency`, `recursive_search`, `nsfw_enabled`+`safe_search`, `ignore_exclusions`, `email_timeout`, `no_password_recovery`, `use_curl_cffi`, `allow_loud`, `hudson_enabled`, `cross_scan_enabled`) are persisted here and nowhere else in the UI besides Settings.

Submission goes through `ControllerMethodsCtx` (`:663-672`): `controller.start_email_search` / `start_phone_search` / `start_search`, with `controller.show_results()` navigating away first. No engine is called directly from this file except the vestigial `_run_hudson` (`:577-591`).

---

## 2) API verification summary

**Result: zero hallucinated flet APIs in this file.** Every control, field, enum member and helper used was verified against the installed `flet` 1.0.4 by constructing it.

| Construct | Site | Installed source | Verdict |
|---|---|---|---|
| `ft.Chip(label, leading, selected, selected_color, bgcolor, show_checkmark, on_select, border_side)` | `:128-147`, `:149-163` | `flet/controls/material/chip.py` | OK (all 8 props exist) |
| `ft.SearchBar(value, bar_hint_text, bar_leading, bar_trailing, bar_bgcolor, bar_border_side, bar_shape, bar_text_style, bar_hint_text_style, full_screen, on_submit, on_change, autofocus, controls)` | `:1151-1251` | `flet/controls/material/search_bar.py` | OK (all 14 props exist) |
| `ft.FilledButton(content, key, on_click, disabled, style)` | `:1288-1321` | `flet/controls/material/filled_button.py` | OK |
| `ft.FilePicker()` | `:682` | `flet/controls/services/file_picker.py` | OK |
| `ft.Icon`, `ft.Text`, `ft.Row`, `ft.Column`, `ft.Container`, `ft.ListTile`, `ft.IconButton` | various | `flet/controls/core/*`, `flet/controls/material/list_tile.py` | OK |
| `ft.Border.all`, `ft.BorderSide`, `ft.RoundedRectangleBorder`, `ft.Padding`, `ft.Margin`, `ft.Alignment.CENTER`, `ft.TextStyle(height=…)` | various | `flet/controls/{border,box,padding,margin,alignment,text_style}.py` | OK |
| `ft.Colors.with_opacity`, `ft.Colors.TRANSPARENT`, `ft.Colors.ON_SURFACE*`, `ft.Colors.ERROR_CONTAINER` | various | `flet/controls/colors.py` | OK |
| `ft.FontWeight.W_400/W_500/W_600/W_700/BOLD`, `ft.TextOverflow.ELLIPSIS`, `ft.TextAlign.CENTER`, `ft.MainAxisAlignment.*`, `ft.CrossAxisAlignment.CENTER`, `ft.ScrollMode.AUTO` | various | `flet/controls/types.py` | OK |
| `ft.Icons.*` (24 distinct) | `:63-79`, `:84-99`, `:805-953`, `:1001`, `:1036`, `:1073`, `:1110`, `:1159`, `:1222`, `:1292`, `:1347`, `:1438` | `flet/controls/material/icons.py` | **all 24 exist** |
| `ft.memo`, `ft.component`, `ft.use_context`, `ft.use_state`, `ft.use_effect` | `:235`, `:287`, `:359`, `:362-363`, `:365`, `:795` | `flet/components/{memo,component_decorator,hooks/*}.py` | OK |
| `ft.Page.update_async` | `:684` | `flet/controls/page.py` — **only `update` (line 819) exists** | **does not exist** (guarded no-op, see §3) |
| `Page.services` | `:683` | `flet/controls/base_page.py:823-828` → `View.services` (`flet/controls/core/view.py:144`, `metadata={"skip": True}`) | exists but inert for the wire; see §3 |

Engine-side signatures used by this file, all verified:

| Call | Site | Installed signature | Verdict |
|---|---|---|---|
| `SherlockService.run_hudson(target, is_email)` | `:587` | `src/services/sherlock_service.py:276` | OK |
| `validate_email(email)` | `:170`, `:597` | `src/services/email_service.py:28` | OK |
| `validate_proxies(proxy_list, timeout=5, max_workers=50)` | `:556` | `user_scanner/core/helpers.py:603` (sync; internally `asyncio.run`) | OK — correctly wrapped in `asyncio.to_thread` |
| `hudson.run_hudson_scan(target, is_email=False)` | via `run_hudson` | `user_scanner/core/hudson.py:49` | OK |
| `StorageService(page)`, `.get(key)`, `.set(key, value)` | `:418`, `:434`, `:497`, `:784`, `:785` | `src/services/storage_service.py:65`, `:288` | OK |
| `load_history_entries(raw)` | `:786` | `src/services/storage_service.py:344` | OK |
| `shared_haptics().medium_impact()`, `shared_clipboard().get()` | `:659`, `:738-739` | `flet/controls/services/haptic_feedback.py`, `clipboard.py` — `Clipboard.get(self) -> str \| None` | OK |
| `ControllerMethodsCtx.{start_search, start_email_search, start_phone_search, show_results, show_settings, show_sites, show_history, open_cached_result, refresh_sites}` | `:663-773`, `:985`, `:1263`, `:1356` | `src/state/controller_ctx.py:55-72` — all present, `open_cached_result: Callable[[str,str],bool]` matches the 2-arg call at `:761` | OK |
| `TargetsCard(selected_count, total_count, on_open, page)` | `:1258-1265` | `src/components/targets_card.py:22-27` | OK (`on_open` is `Callable[[],None]` — **called with no args** at `:1263` via `lambda e: controller.show_sites()`, and the lambda's `e` param is unused: correct) |
| `AppHeader(page, title=…, on_settings=…)` | `:982-988` | `src/components/app_header.py:98-106` | OK |

---

## 3) Confirmed known issues (sibling-audit claims)

**✅ CONFIRMED — `:684` `page.update_async()` does not exist in flet 1.0.4, and is a guarded no-op.**
`flet/controls/page.py` defines only `update()` (line 819); `hasattr(page, "update_async")` is `False`.
Important precision the sibling note left implicit: the expression
`await page.update_async() if hasattr(page, "update_async") else None`
parses (AST-verified via `ast.dump`) as
`IfExp(test=hasattr(...), body=Await(page.update_async()), orelse=None)` —
the `await` binds **inside the true-branch only**. Because the guard is `False` on flet 1.0.4, the line evaluates to `None` and **does not raise `TypeError: object NoneType can't be awaited`**. It is dead code, not a crash.
It is also redundant: `ft.FilePicker()` self-registers through `Service.__post_init__` (`flet/controls/services/service.py:39-54` → `page._services.register_service(self)`), which already pushes the wire update. `page.services.append(picker)` at `:683` appends to `View.services`, a field marked `metadata={"skip": True}` (`flet/controls/core/view.py:144`) — a different list from the `ServiceRegistry` (`flet/controls/page.py:714`) that actually carries the client binding. So `:683-684` can be deleted with no behavioural change.

**✅ CONFIRMED — `:587-591` shows raw ANSI in a SnackBar — but the code is DEAD.**
`run_hudson` captures the engine's stdout (`src/services/sherlock_service.py:283-286`), and that output is saturated with colorama escapes (`user_scanner/core/hudson.py:8-13` defines `Fore.RED/GREEN/CYAN/YELLOW/MAGENTA` and `Style.RESET_ALL`). `_run_hudson` dumps `out[:200]` straight into a `SnackBar` at `:591` with no stripping.
Two refinements the sibling note missed:
1. `_run_hudson` is **unreachable**. `grep -rn "_run_hudson" src/` returns exactly one hit — its own definition at `:577`. No chip, button, or effect calls it. The Hudson chip at `:910-916` only flips `state.hudson_enabled`.
2. The **live** instance of the same ANSI bug is in `main.py:1119-1123`, where the post-scan Hudson result is shown via `self._show_snack((hudson_out[:120] + "...") …, duration=8000)` — that one *does* reach users. Fix belongs in `SherlockService.run_hudson` (strip ANSI at the capture boundary), which fixes both.

**✅ CONFIRMED — `:345-348` URL-to-username normalization.**
`_normalize_pasted_query` (`:331-353`) extracts the last non-empty path segment from a pasted URL. It works for the canonical case (`https://github.com/torvalds` → `torvalds`). Two limitations worth documenting (see §5.10): it is applied **only** inside `_on_search` (`:650`), never in `_on_paste` (`:733-747`), so the field displays the raw URL until submit; and "last path segment" mis-handles profile URLs that carry a trailing path (`https://github.com/torvalds/repo` → `repo`).

**✅ CONFIRMED — Phone mode controls exist on this screen, but there is no region/validity UI.**
Phone mode renders 4 chips (`:802-832`): concurrency, timeout, loud, "Silent by default". Answer to the sibling's question: **there is no county/region picker anywhere in the app.** `grep -rn "region" src/` finds only `phone_service.search(region=…)` (`src/services/phone_service.py:126`), the hardcoded `region=None` call at `main.py:1773`, and unrelated ad-service text. `region` is never populated from storage or UI.
There is also **no phone validity display** on this screen — `_submit_guards` accepts "anything non-empty" for phone mode (`:638-640`, comment: *"phone numbers: accept anything non-empty; engine validates"*), but the engine does not validate up front either: `phonsint/core/parser.py:24-30` prepends `"+"` when `default_region is None` and then falls back to `phonenumbers.parse(cleaned, default_region or "US")`. A local number like `07791234567` is therefore parsed as US and reported invalid, with no feedback on the launch screen. `phonenumbers` 9.0.41 **is** installed and would support a proper region/validity check.
One further drop: the phone-mode **"Loud: ON/OFF" chip** (`:818-824`) writes `state.allow_loud`, but the phone scan passes it as a hardcoded `allow_loud=False` (`main.py:1777`). The chip has zero effect on phone scans.

**County/region picker data source:** neither `phonenumbers` nor a hardcoded list — the picker does not exist.

---

## 4) NEW bugs / hallucinations (severity-ordered)

### B1 — HIGH — Operator-precedence bug: the SearchBar suggestion filter never filters (`:1234-1247`)

```python
if (
    h.get("mode")
    or (
        MODE_EMAIL
        if _is_email_query(h.get("query", ""))
        else MODE_USERNAME
    )
    == state.search_mode
    and (
        not search_query.strip()
        or search_query.strip().lower() in (h.get("query", "") or "").lower()
    )
)
```

Python binds `==` tighter than `and`, and `and` tighter than `or`, so this parses as:

```
h.get("mode") or ( (MODE_EMAIL if … else MODE_USERNAME) == state.search_mode
                   and (not typed or typed in query) )
```

Every persisted history entry carries a non-empty `"mode"` (`main.py:2214-2221`), so `h.get("mode")` is always truthy and the whole condition **short-circuits to True**. The mode filter *and* the typed-text filter are both dead.

Verified empirically against the exact expression:

```
email entry in username mode, typed 'zzz' -> included? True   (expected False)
```

Impact: the SearchBar dropdown (`:1214-1250`) lists the first 5 history entries regardless of the active mode and regardless of what the user has typed. Clicking an email-mode suggestion (`:1228`) calls `_on_history_click`, which switches mode and launches an **email scan** from a username-mode screen — surprising and, combined with B2, dangerous.

Fix: parenthesize the intent —
`((h.get("mode") or (MODE_EMAIL if … else MODE_USERNAME)) == state.search_mode) and (not typed or typed in query)`.

### B2 — HIGH — Phone history entries launch a *username* scan (`:749-773`, especially `:767-771`)

```python
async def _run_hist():
    if mode == MODE_EMAIL:
        await controller.start_email_search(query)
    else:
        await controller.start_search(query)
```

`mode` comes from `entry.get("mode")` (`:751`) and can be `MODE_PHONE`: `main.py:1828` saves phone scans with `mode=MODE_PHONE`, and `main.py:2214-2221` writes `"mode"` into every history entry. The recent-search rows at `:959-976` render those phone entries (`m = entry.get("mode", MODE_USERNAME)`), so they are clickable.

Clicking one: `_submit_guards(query, MODE_PHONE)` passes (no validation, `:638-640`) → `_switch_mode(MODE_PHONE)` → `open_cached_result(query, "phone")` (`main.py:1994` does handle phone) → on a cache miss it falls into `_run_hist()`, which has **no `MODE_PHONE` branch** and calls `controller.start_search(query)` — the sherlock username engine, handed a phone number.

Related cosmetic: `_is_email_like` (`:166-172`) is called with `mode=MODE_PHONE` from `_history_row` (`:188`), falls through to `validate_email("555…")` → `False`, so phone rows get the **person-search icon** instead of a phone icon.

Fix: add `elif mode == MODE_PHONE: await controller.start_phone_search(query)`.

### B3 — HIGH — Five quick-setting chips are inert; they write state no engine reads

`grep` across `src/services/`, `src/core/` and `user_scanner/core/` shows these `state.*` fields are never consumed at scan time:

| Chip | Home site | Persist key | Actually read by the engine? |
|---|---|---|---|
| "Scope: All modules / Top 1k / Top 500" (`state.scan_depth`) | `:443-455`, `:868-881` | `STORAGE_SCAN_DEPTH` | **No.** `sherlock_service.search()` (`src/services/sherlock_service.py:130-136`) has no depth parameter, and `load_user_modules(no_nsfw)` (`src/services/user_scanner_compat.py:33`) takes only `no_nsfw`. |
| "Recursive: ON/OFF" (`state.recursive_search`) | `:479-483`, `:917-927` | `STORAGE_RECURSIVE_SEARCH` | **No.** `state.recursive_search` appears only in `core/state.py:121`, `main.py:777` (load), Settings, and here. No `if state.recursive_search` gate exists in `main.py` — the engine's recursive tail (`main.py:1371`) is unconditional. |
| "Disabled Sites: ON/OFF" (`state.ignore_exclusions`) | `:507-515`, `:946-954` | `STORAGE_EXCLUSIONS` | **No.** Read only at `main.py:656` (load) and in Settings/Home. Never forwarded to `load_user_modules` or `run_username_scan`. |
| "Concurrency: N" in phone mode (`state.phone_concurrency`) | `:469-477`, `:803-810` | `STORAGE_PHONE_CONCURRENCY` | **No.** The phone scan uses `concurrency=getattr(state, "email_concurrency", 15)` (`main.py:1776`) — the *email* concurrency. |
| "Hudson: ON/OFF" (`state.hudson_enabled`) | `:565-569`, `:910-916` | `STORAGE_HUDSON` | Partially. It is consumed at `main.py:1117`/`1573` — but only *after* a scan finishes, and only in username/email modes. |

These five chips change a label, mutate observable state, and write a storage key — and the user's scan behaves identically. That is the worst kind of bug in a settings surface: it is actively misleading. `state.cross_scan_enabled` (`:571-575`) **is** live (`sherlock_service.py:221`, `email_service.py:366`), and `state.timeout`/`email_timeout`/`no_password_recovery`/`use_curl_cffi`/`nsfw_enabled` are live — so the row is a mix of real controls and no-ops.

### B4 — MEDIUM-HIGH — Two persisted toggles are never reloaded, so they silently reset on every app start

- `STORAGE_HUDSON` — written at `:568`, but `grep -rn "STORAGE_HUDSON" src/` shows it is referenced **only** in `core/constants.py:74` and this file. `main.py`'s startup loader never reads it, so `state.hudson_enabled` reverts to the `core/state.py:76` default (`False`) on every launch despite a persisted `true`.
- `STORAGE_PHONE_CONCURRENCY` — written at `:477`; `main.py` never loads it either (`grep -n "PHONE_CONCURRENCY" src/main.py` → no match), so the persisted concurrency is discarded at startup. (The value is unused at scan time anyway — B3.)

Every *other* key this screen writes (`STORAGE_TIMEOUT`, `STORAGE_SEARCH_MODE`, `STORAGE_EMAIL_TIMEOUT`, `STORAGE_SCAN_DEPTH`, `STORAGE_RECURSIVE_SEARCH`, `STORAGE_EXCLUSIONS`, `STORAGE_NSFW`, `STORAGE_SAFE_SEARCH`, `STORAGE_USE_CURL_CFFI`, `STORAGE_ALLOW_LOUD`, `STORAGE_CROSS_SCAN`, `STORAGE_NO_PASSWORD_RECOVERY`) *is* read at `main.py:650-833`. The two exceptions are exactly the two whose home chips are the least functional.

### B5 — MEDIUM — The bulk-file path produces a query the shape guard always rejects (`:676-704`)

`_load_bulk_file` ends with `set_search_query(", ".join(lines))` (`:702`). Submitting that runs `_check_username_shape` (`:601-610`), which strips whitespace but not commas:

```
'alice, bob' -> Usernames may only contain letters, numbers, _ . -
'alice bob'  -> None
```

So the user loads a file, the field fills, and Search always fails with a shape error. The engine *can* take comma-separated targets — `main.py:993-1000` joins permuted handles with `","` and `parse_usernames` splits them — so the guard, not the engine, is the obstacle. Related: `state.bulk_mode` (`core/state.py:77`) and `STORAGE_BULK_MODE` are never referenced by any service, so there is no bulk execution path either.

Also, on the web target `files[0].path` is `None` (`:689-690`) and the function returns silently — no message, so the button appears to do nothing.

### B6 — MEDIUM — Double-submit window: `_submit_guards` is checked before `is_searching` is set (`:612-647`, `:649-674`)

`_submit_guards` blocks on `state.is_searching` (`:629`), but that flag is only raised *inside* the engine (`main.py:935` for username, `:1503` email, `:1750` phone). `_on_search` therefore validates, then `spawn(_run())` (`:674`) — an async boundary — before `start_*` sets the flag. Two taps (or Enter + click) inside that window both pass the guard and both spawn a scan.

Mitigation is asymmetric: `main.py:898-912` has a smart re-attach guard, but it is **username-only and requires `state.is_searching` to already be `True`** — the exact condition that is not yet true during the race window. `start_email_search` (`main.py:1490+`) and `start_phone_search` (`main.py:1728+`) have **no** re-attach guard at all, so a double-tap in email/phone mode calls `_kill_all_activity` and restarts the first scan.

The screen already has the correct primitive (`_mode_locked` at `:372-374` reads `search_progress.is_running`). Use the same signal for the submit guard, plus a local in-flight flag.

### B7 — MEDIUM — `state.search_mode` is mutated by a UI chip, but it is the running scan's identity (`:389-423`)

The file's own comments (`:369-374`, `:390-396`) state that `search_mode` is the live scan's IDENTITY — `_apply_progress` drops cross-mode ticks (`main.py:1345-1352`) and the completion guards discard results on a mismatch (`main.py:1010-1014`). `_switch_mode` assigns `state.search_mode = new_mode` directly at `:407`.

The lock at `:398-406` only blocks when `state.is_searching AND prog.is_running AND new_mode != state.search_mode`. Two holes:
- It keys off `state.search_progress`, which is `None` before a scan starts and can be stale after one ends; `main.py:898-905` explicitly guards against the "stuck `is_searching`" state — the same fragility applies here.
- The mode pills go inert visually via `_mode_locked` (`:1060`, `:1097`, `:1134` set `opacity=0.45`, `on_click=None`), but `_switch_mode` is *also* reachable from `_maybe_switch_mode` (`:728-731`) driven by `_on_input_change` (`:711`). Typing during a scan calls `_switch_mode(MODE_EMAIL, keep_query=True)`; the guard normally blocks it, but the guard's condition is weaker than the one that protects the results.

Suggested: separate "UI intent mode" from "scan identity mode" (two fields), or make the chip write only the intent and let `start_*` own the identity.

### B8 — MEDIUM — Chip `selected` state is client-toggled and can stick (`:119-163`)

`flet/controls/material/chip.py` documents `on_select` as: *"It internally changes `selected` property to the opposite value."* The chips here are recreated on every render with `selected=is_active`, so any chip whose handler changes the underlying flag self-corrects on the next render. But three chips have `is_active` fixed at `False` and a handler that changes **no** state:
- "Load from file" (`:889-895`, `is_active=False`)
- "Validate proxy" (`:903-909`, `is_active=False`)
- "Silent by default" (`:825-831`, informational, `on_select=lambda e: None`)

Tapping these flips the client-side `selected` to `True`; no observable state changes, so no re-render occurs, and the chip stays visually selected until some unrelated state change re-renders the screen.

Additionally, `_category_chip` names its parameter `on_click` but binds it to flet's `on_select` (`:146`), and the informational branch attaches a no-op `on_select` (`:162`) — which makes the chip semantically *selectable* (and therefore focusable/tabbable and screen-reader-announced as a toggle) while doing nothing.

### B9 — MEDIUM — `@ft.memo` is applied to plain functions, so it memoizes nothing and leaks a renderer flag (`:235`, `:287`)

`_feature_card` and `_step_row` are decorated with `@ft.memo` but are **not** `@ft.component` functions — they are plain callables returning a fresh `ft.Container`/`ft.Row`. `flet/components/memo.py` implements `memo` as:

```python
def memo_wrapper(*args, **kwargs):
    r = current_renderer()
    r.set_memo()
    return fn(*args, **kwargs)
```

Two consequences:
1. **No memoization happens.** The wrapped function is invoked on every render and returns a brand-new control, so nothing is skipped. (Compare `_history_row`'s explicit note at `:185-187`: *"deliberately not @ft.memo — callers pass a fresh on_click lambda per row, so memoization could never hit."* The same reasoning applies verbatim to `_feature_card`/`_step_row`.)
2. `r.set_memo()` sets `Renderer._is_memo = True` (`flet/components/component.py:410-415`), and that flag is consumed by the *next* `render_component()` call (`component.py:514`, reset at `:520`). Since `_feature_card`/`_step_row` are not components, nothing consumes the flag inside this render pass — it is left dangling on the renderer, ready to mis-mark an unrelated component as memoized if any `@ft.component` is ever added to this body. It also makes the function **raise `RuntimeError` if ever called outside a render context** (`current_renderer()` raises when no renderer is bound — `flet/components/utils.py:29-40`).

Fix: drop `@ft.memo` from both, or convert them to real `@ft.component`s (which is what would actually make memoization work).

### B10 — LOW-MEDIUM — `_on_paste` bypasses URL normalization and the mode auto-switch asymmetry (`:733-747`)

`_on_paste` sets the raw clipboard text (`:742`) and calls `_maybe_switch_mode(value)` with `allow_username_flip=True` (the default). `_on_input_change` (`:706-711`) calls the same helper with `allow_username_flip=False`. Consequences:
- A pasted profile URL lands in the field verbatim; only `_on_search` normalizes it (`:650`), so the user sees `https://github.com/torvalds` until they submit.
- `_maybe_switch_mode` with `allow_username_flip=True` flips Email → Username whenever the pasted value has no `"@"` (`:730`), but only when the *whole* pasted value is known. A user who types an email and then edits it into a username stays stuck in Email mode (`_on_input_change` refuses the flip) and the manual Username pill tap **clears the typed query** (`_switch_mode` → `set_search_query("")` at `:412`). Net effect: the typed target is lost.
- `_is_email_query` is imported and called per keystroke (`:597` → `user_scanner.core.helpers.is_valid_email`); it is fine but does a full import lookup on every character.

### B11 — LOW — Duplicate email-detection helpers (`:166-172` vs `:595-599`)

`_is_email_like(query, mode)` and `_is_email_query(value)` are the same logic with a mode short-circuit; both import `validate_email` inside the function body, so the import is re-executed on every call, and `_history_row` calls it once per rendered row per render. Consolidate into one helper and hoist the import to module scope.

### B12 — LOW — `_load_history` clears live history and can race a concurrent save (`:776-795`)

`_load_history` replaces in-memory history with the persisted copy:

```python
state.history.clear()
state.history.extend(entries)
```

`state.history` is an `ObservableList` (`flet/components/observable.py:227-296`), so `clear()` and `extend()` each notify → **two** re-renders per mount. Worse, the spawn at `:793` races `main.py:2241-2247` (`state.history.insert(0, entry)`): if a scan completes between the storage read (`:785`) and the `clear()` (`:788`), the just-added in-memory entry is wiped and replaced by the stored copy, which may predate it. The new search then vanishes from "Recent" until the next mount.

### B13 — LOW — `hasattr(AppStyles, "brand_gradient")` is always true — dead branch (`:1490-1492`)

`src/core/theme.py:219` defines `brand_gradient` unconditionally, so the `else None` arm is unreachable. Same pattern to check elsewhere: `_get_page()`'s `try/except Exception` (`:378-382`) is legitimate (no page outside a session), but the `hasattr` is not.

### B14 — LOW — `state.progress_version += 1` is redundant on this screen (`:450`, `:466`, `:476`, `:482`, `:489`, `:526`, `:532`, `:538`, `:545`, `:569`, `:575`)

`AppState` is `@ft.observable` (`src/core/state.py:12`), and `use_context(AppStateCtx)` attaches a subscription to the whole observable (`flet/components/hooks/use_context.py` → `component._attach_observable_subscription(value)`; `flet/components/observable.py:104-118`). `Observable.__setattr__` notifies on **any** non-private field write (`observable.py:204-212`). So writing `state.timeout = next_val` already re-renders this screen; the extra `progress_version` bump forces a second render pass on every toggle. `progress_version` is meaningful for the results screen's render flusher (`main.py:1324-1327`), not for Home.

### B15 — LOW — `_validate_proxy` has no in-flight guard and can only ever validate a proxy set elsewhere (`:547-563`)

Repeated taps spawn concurrent 5-second `validate_proxies` calls. More fundamentally, this screen offers a "Validate proxy" chip (`:903-909`) but **no way to set a proxy** — the common path is the error toast "Set a proxy URL in settings first" (`:553`). A validate-only control with no adjacent input is a dead-end affordance.

### B16 — LOW — Dead/stale comments and duplicated imports

- `:44` imports `show_snack` at module scope, but nine call sites re-import it locally (`:550`, `:559`, `:580`, `:590`, `:695`, `:699`, `:703`) — the local imports shadow the module-level one for no reason.
- `:603` `import re` inside `_check_username_shape` — re-executed on every validation.
- `:376` `from flet import context as flet_context` runs on **every render** of the component; `:677` re-imports it again inside `_load_bulk_file`.
- `:185-187` (the `@ft.memo` note on `_history_row`) is accurate and useful, but it contradicts the `@ft.memo` usage at `:235`/`:287` — see B9.
- `:1156` hint text contains a literal `user{?}name` placeholder that was never filled in.

---

## 5) Improvements (concrete, ordered)

Each item names a control that **exists in the installed flet 1.0.4** (verified by construction where noted).

1. **Make the mode switcher a real `ft.SegmentedButton`.** `flet/controls/material/segmented_button.py` defines `SegmentedButton` and `Segment` — note the class is **`flet.Segment`**, *not* `SegmentedButtonSegment` (I verified `ft.SegmentedButtonSegment` raises `AttributeError`). Replace the 130-line hand-rolled pill row (`:1019-1147`) with `ft.SegmentedButton(segments=[ft.Segment(icon=ft.Icons.PERSON_SEARCH_ROUNDED, label="Username", value="username"), …], selected=[state.search_mode], show_selected_icon=False, on_change=…)`. Benefits: real Material semantics, keyboard/screen-reader support, no manual `opacity=0.45` inert hack, and the "locked during a scan" case becomes a single `disabled`/`on_change` guard instead of three duplicated `opacity`/`on_click=None` blocks.

2. **Replace the hand-rolled SearchBar suggestion list with `ft.AutoComplete`.** `ft.AutoComplete` exists in 1.0.4 with `value`, `suggestions`, `suggestions_max_height`, `on_select`, `on_change`; suggestions are `ft.AutoCompleteSuggestion(key=…, value=…)` (both verified by construction). `ft.AutoComplete` gives real keyboard-navigable, type-filtered suggestions and removes the precedence bug (B1) entirely. If `ft.SearchBar` must stay, at minimum fix the parenthesisation in B1.

3. **Add inline live validation.** `ft.SearchBar` has **no** `error`/`error_text` property (verified: `grep -n "error" flet/controls/material/search_bar.py` → no matches); the error affordance lives on `FormFieldControl.error` (`flet/controls/material/form_field_control.py:446`, plus `error_style` and `error_max_lines`) which `ft.TextField` inherits. So: render a sibling `ft.Text(…, color=ft.Colors.ERROR)` under the SearchBar, driven by the existing validators (`_check_username_shape` at `:601`, `_is_email_query` at `:595`) on a debounce. `src/hooks/use_debounce.py` already exists for exactly this.

4. **Add phone validity + region selection.** `phonsint.core.parser.parse_phone_number(raw, default_region)` (`phonsint/core/parser.py:19`) accepts a region and `phonenumbers` 9.0.41 is installed. Add an `ft.Dropdown` of country/region codes (persist a new storage key), thread it through `controller.start_phone_search` → `phone_service.search(region=…)` (`src/services/phone_service.py:126`, currently hardcoded `region=None` at `main.py:1773`), and show "Invalid number — use international format" inline when `phonenumbers.is_valid_number()` fails.

5. **Turn the inert chips into real switches.** `ft.Switch` exists and constructs cleanly (verified). The six boolean toggles (NSFW, Cross-Scan, Hudson, Recursive, Disabled Sites, PW Recovery, Stealth) are semantically switches, not chips — a Material Chip that cycles is a poor affordance. Move them to a small `ft.BottomSheet` (exists: `flet/controls/material/bottom_sheet.py`) or an `ft.AlertDialog` triggered by a single "Options" chip, keeping the horizontal chip row for the two genuinely-cyclic values (scope, timeout).

6. **Show target chips for recent searches.** `ft.Chip` supports `delete_icon` + `on_delete` (verified by construction) — render the last 3–5 targets as deletable chips under the field, and use `ft.Badge(label="3")` (`ft.Badge`'s field is `label`, *not* `content` — `ft.Badge(content=…)` raises `TypeError`) for the "Recent" count.

7. **Surface a running-scan indicator and a cancel affordance on Home.** `src/components/active_scan_banner.py` already exists and is used by `app_shell.py:894-896`, but Home only shows a disabled Search button (`:1313`) while a scan runs. Reusing `ActiveScanBanner` on Home would give the user progress and cancel without navigating away.

8. **Fix the dropped settings (B3/B4) or remove the chips.** Concretely: pass `scan_depth` into `sherlock_service.search()` as a module cap; gate the engine's recursive tail on `state.recursive_search`; forward `ignore_exclusions` into `load_user_modules`; use `state.phone_concurrency` (not `email_concurrency`) at `main.py:1776`; forward `allow_loud` for phone scans (`main.py:1777`); and load `STORAGE_HUDSON` + `STORAGE_PHONE_CONCURRENCY` in `main.py`'s startup loader alongside the other keys. If a setting cannot be wired, the chip must be removed — a control that lies is worse than no control.

9. **Make the bulk path work end to end.** Validate comma-separated targets per-segment (the engine already splits on `,`), set `state.bulk_mode` when a file is loaded, and surface a web-target message when `files[0].path` is `None` (`:689`).

10. **Apply `_normalize_pasted_query` on paste, not just on submit.** Call it in `_on_paste` (`:733-747`) so the field shows the handle immediately, and document its limitation: it takes the *last* path segment, so `https://github.com/torvalds/repo` yields `repo`. Prefer a per-site profile-URL regex table (GitHub `/user`, X `@user`, Reddit `/user/…`) over generic last-segment extraction.

11. **Small cleanups.** Remove the local `show_snack` re-imports (`:550`, `:559`, `:580`, `:590`, `:695`, `:699`, `:703`); hoist `import re` (`:603`) and `from flet import context` (`:376`, `:677`) to module scope; delete the unreachable `hasattr(AppStyles, "brand_gradient")` guard (`:1491`); drop the redundant `state.progress_version += 1` bumps (B14); delete `_run_hudson` (`:577-591`) or wire it to a button; strip ANSI in `SherlockService.run_hudson` (`src/services/sherlock_service.py:283-286`) so the live toast at `main.py:1119-1123` renders clean text; fix the `user{?}name` placeholder (`:1156`).

---

## 6) Verdict

**API hygiene: clean.** Zero hallucinated flet APIs. All 24 `ft.Icons` members exist; every `Chip`/`SearchBar`/`FilledButton`/`FilePicker`/`Text`/`Row`/`Column`/`Container`/`ListTile`/`IconButton` construction was executed against the installed flet 1.0.4 and succeeded. The one non-existent API (`page.update_async`, `:684`) is guarded and evaluates to `None` — dead code, not a crash, and redundant with `Service.__post_init__` self-registration.

**Correctness: not release-ready.** The screen looks complete but several of its controls are decorative:

- **B1** — the SearchBar suggestion filter is a no-op due to operator precedence (proven empirically).
- **B2** — clicking a phone history entry runs the *username* engine on a phone number.
- **B3** — five of the eleven quick-setting chips write state that no engine consumes (`scan_depth`, `recursive_search`, `ignore_exclusions`, `phone_concurrency`, and phone-mode `allow_loud`).
- **B4** — two of those keys are never reloaded, so they silently reset on every app start.
- **B5** — the bulk-file path always fails the username shape guard.
- **B6/B7** — a double-submit window, and a UI chip that mutates the field the engine treats as the live scan's identity.

**Sibling claims:** all four confirmed with refinements — `:684` is a guarded no-op (not a `TypeError`); `:587-591`'s ANSI leak is in **dead code** and the live instance is `main.py:1119-1123`; `:345-348` normalization works but is submit-only and last-segment-based; phone mode has **no** region picker and **no** validity display, and the answer to the region question is *neither* phonenumbers *nor* a hardcoded list — the picker does not exist at all.

**Recommendation:** land B1, B2, B5 and B6 fixes first (small, isolated, high user impact); then decide B3/B4 as a group — wire the settings or delete the chips. The UX upgrades in §5 (SegmentedButton, AutoComplete, inline validation, phone region) are each independently shippable against flet 1.0.4.
