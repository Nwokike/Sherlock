# Audit — `src/components/active_scan_banner.py`

Scope: single file, 109 lines. Truth source: `flet 1.0.4` as installed in
`.venv/Lib/site-packages/flet` (verified `importlib.metadata.version("flet") == "1.0.4"`).
Note: the Flet MCP helper tool runs against flet **1.0.5**; every API claim below was
re-verified against the project's own 1.0.4 tree, and the file was executed live in the
project venv.

---

## 1) File role

`ActiveScanBanner(...)` (`active_scan_banner.py:15`) is a **pure factory function** that
returns a single `ft.Container` (`:37`) describing a floating "a scan is running" strip:

- icon badge (`:40-51`) — mail / phone / person glyph chosen by `search_mode` (`:24-29`),
- title `Scanning '<query>'` with ellipsis truncation (`:56-64`),
- a progress string + `ft.ProgressBar` (`:65-80`),
- a `View` button (`:85-93`) and a tappable container (`:108`) that both call `on_tap`.

It holds **no state, no timers, no subscriptions, and never touches `page`** — it takes
scalars (`checked`, `total`, `finishing`) and renders them. The only caller in the tree is
`app_shell.py:894-902`, which is invoked from the app-shell render body
(`app_shell.py:885-903`).

Consequences for the audit:

- The "progress binding" contract lives in the **caller**, not here. This file never reads
  `state.search_progress`, `checked_sites`, `total_sites`, `checked_modules`,
  `total_modules`, `progress_version`, or any rate/ETA field. Confirmed: grep of the file
  shows no `state`/`AppState` import at all (`:1-12`).
- Because it is a plain function (not a flet `Component`), it cannot subscribe to state
  itself; the shell must re-call it on every progress tick to refresh it.

---

## 2) API verification (flet 1.0.4, project venv)

Executed live in the project venv: `ActiveScanBanner(...)` was constructed for
`search_mode` in {username, `MODE_EMAIL`, `MODE_PHONE`}, for `checked/total` = 5/100,
150/100 and 0/0. All three construct without exception; `flet` reports 1.0.4.

| Line | API used | 1.0.4 verdict |
|---|---|---|
| `:25` | `ft.Icons.ALTERNATE_EMAIL_ROUNDED` | OK — `controls/material/icons.pyi:355` |
| `:26` | `ft.Icons.PHONE_ROUNDED` | OK — `icons.pyi:5703` |
| `:29` | `ft.Icons.PERSON_SEARCH_ROUNDED` | OK — `icons.pyi:5630` |
| `:41-45` | `ft.Icon(icon, size=, color=)` | OK — `IconDataOrControl` accepted positionally |
| `:49`, `:78`, `:106` | `ft.Colors.with_opacity(opacity, color)` | OK — arg order `(opacity, color)` (`controls/colors.py:110`); accepts the raw hex string `AppColors.PRIMARY` (`core/theme.py:16` = `#A68E59`) and returns `"#A68E59,0.15"` |
| `:50` | `ft.Alignment.CENTER` | OK — `controls/alignment.py:67,125` |
| `:59`, `:68`, `:88` | `ft.FontWeight.W_600 / W_500 / BOLD` | OK — `controls/types.py:175,200,205` |
| `:62` | `ft.TextOverflow.ELLIPSIS` | OK — `controls/text_style.py:30` |
| `:63`, `:83` | `expand=True` | OK — `expand` is a `BaseControl` field (`controls/control.py:21`) |
| `:72`, `:73`, `:96` | `ft.Row/Column(controls=)`, `vertical_alignment`, `spacing` | OK |
| `:75-80` | `ft.ProgressBar(value=, color=, bgcolor=, height=)` | **`height` is the wrong knob** — see B2 |
| `:86` | `ft.TextButton(content=...)` | OK — `content: Optional[StrOrControl]` (`controls/material/text_button.py:36`) |
| `:98-100` | `ft.Padding(l, t, r, b)` | OK — field order confirmed (`controls/padding.py:18-35`): left=12, top=4, right=4, bottom=4 |
| `:101-103` | `ft.Margin(l, t, r, b)` | OK — field order confirmed (`controls/margin.py:15-32`): left=16, top=4, right=16, bottom=4 |
| `:106` | `ft.Border.all(width, color)` | OK — `controls/border.py:204-209` |
| `:105` | `ft.Colors.SURFACE_CONTAINER_HIGHEST` | OK — `controls/colors.py:178` |
| `:8`, `:22` | `from flet import Control` / return type | OK |

**No hallucinated APIs.** Every flet symbol used by this file exists in 1.0.4 with the
argument shape used here. The only API *misuse* is the `ProgressBar` thickness property (B2).

---

## 3) Progress binding + clamp check

### What is bound
`checked` / `total` are plain `int` parameters (`:18-19`) supplied by
`app_shell.py:890-897`, which derives them from `state.search_progress` via
`getattr(prog, "checked_sites", 0) or getattr(prog, "checked_modules", 0)` and
`total_sites / total_modules`. **This file performs no validation of those ints** and has
no knowledge of the `search_progress` contract — the field-name mismatch risk (`checked_sites`
vs `checked_modules`) lives entirely in the caller, and the caller’s `or` chaining means a
legitimate `checked_sites == 0` falls through to `checked_modules` (`app_shell.py:891-892`).
The banner itself is contract-safe: it accepts two ints and cannot misinterpret the field
names.

### Division by zero — clean
`:31` and `:76` both use `max(total, 1)` **and** guard with `total > 0`, and `:35` guards
the string branch on `total > 0`. No ZeroDivisionError, no `1/0`, no NaN path. Verified at
runtime with `checked=0, total=0`: the bar value is `None` (indeterminate) and the label is
`"Initializing..."` — correct.

### Clamping — **absent (bug B1)**
- `:31` `pct = int(checked / max(total, 1) * 100)` — **not clamped to 100**.
- `:35` renders that `pct` verbatim.
- `:76` `value=(checked / max(total, 1))` — **not clamped to 1.0**.

Runtime proof in the project venv with `checked=150, total=100`:
```
over-100 OK -> 150/100 (150%) | bar value: 1.5
```
So the banner displays **“150/100 (150%)”** and ships `value=1.5` to the client.

Flet-side behaviour: `ProgressBar.value` is validated `Annotated[Optional[Number], V.ge(0)]`
(`controls/material/progress_bar.py:25-28`) — the **Python layer enforces only `>= 0`**, so
`1.5` is accepted and serialized. The docstring’s claim that the value “will be clamped to
be in the range 0.0 - 1.0” (`progress_bar.py:32-33`) is a Flutter-side guarantee; Flutter’s
`ProgressIndicator` asserts `value == null || (value >= 0.0 && value <= 1.0)` in debug
builds and clamps only in the painter. **The percentage text is never clamped anywhere** —
this is the same defect class the results_screen audit flagged, and here it is on the most
visible surface (a floating, always-on-top strip).

The `finishing` flag (`:32-33`) is caller-computed (`app_shell.py:893`:
`bool(total and checked >= total and is_running)`) and is displayed verbatim; it does not
repair the >100 % case — when `checked > total` the banner simultaneously shows
`“Finishing…”` and `150%`.

### Rate / ETA
**Neither exists.** The banner computes no rate and shows no ETA, and no rate/ETA value is
passed in (`:15-22`). This is not a bug, but it means the “2 Hz progress” surface gives the
user a counter with no time estimate; the state layer (`core/state.py:33`, `progress_version`
at `:34`) exposes no rate field to the banner either. Any ETA added later must be supplied
by the caller — it cannot be derived from `checked/total` alone (needs elapsed time).

---

## 4) Bugs (severity-ordered)

### B1 — HIGH — progress can exceed 100 % (no clamp) — `:31`, `:35`, `:76`
`checked > total` produces `“150/100 (150%)”` and `ProgressBar(value=1.5)`. Verified at
runtime. The banner is the floating, always-visible surface, so a scan whose `checked`
counter overshoots `total` (retries, `total_sites` reported late — `main.py:944` logs
“total_sites pending”) shows the user a broken-looking 150 % bar. Python-side validation
does not catch it (`V.ge(0)` only), and a Flutter debug build would trip the
`ProgressIndicator` value assert.
Fix: compute one clamped ratio and use it everywhere:
`ratio = 0.0 if total <= 0 else min(1.0, max(0.0, checked / total))`, `pct = int(ratio * 100)`.

### B2 — MEDIUM — wrong `ProgressBar` thickness property — `:79`
`height=3` sets the **constrained height of the whole indicator widget** (inherited
`ConstrainedControl.height`), not the thickness of the drawn line. The correct property in
flet 1.0.4 is `bar_height` (“The minimum height of the line used to draw the progress
indicator”, `controls/material/progress_bar.py:43-46`). With `height=3` the 4 px default bar
is squeezed/clipped inside a 3 px box, and the layout is fighting the parent Row/Column.
Fix: `bar_height=3` (and drop `height`).

### B3 — MEDIUM — rebuilt instance with no stable `key` → subtree re-created every tick — `:37`
The function returns a **new** `ft.Container` on every call, with no `key`. flet 1.0.4 diffs
the new render tree against the previous one in `_maybe_compare_dataclasses`
(`controls/object_patch.py:597-626`): when the old and new values are *different Python
objects of the same type*, flet recurses field-by-field **only if the two share an explicit
`key`** (`get_control_key`, `object_patch.py:1731-1736`; `BaseControl.key` field at
`controls/base_control.py:227`). Without a key the subtree is emitted as remove + add.
Consequence: every scan tick (the shell re-calls this factory at ~2 Hz — `app_shell.py:903`
plus the `progress_version` touch at `app_shell.py:905`) destroys and re-creates all ~13
banner controls on the Flutter side, resetting the ink splash (`:106` `ink=True`) and any
focus/hover state on the `View` button (`:85`), and re-serializing the whole subtree over
the wire.
Fix: `key=ft.ValueKey("active-scan-banner")` on the returned Container (verified to exist
and be accepted in 1.0.4: `ft.ValueKey` is exported; `ft.Container(key=...)` constructs).
Note the same rule applies to the parent wrapper in `app_shell.py:934-939` — a rebuilt
`ft.Column` without a key replaces its whole subtree, which is what drags the memoized
screen (and any ad view inside it) into the re-mount path. The banner cannot fix that
ancestor, but it can stop being the leaf that gets torn down.

### B4 — MEDIUM — two click targets fire the same callback — `:92` and `:108`
The `View` `TextButton` (`:85-93`) and the wrapping `Container` (`:108`) both invoke
`on_tap`. Today the inner button wins the Flutter gesture arena so only one call fires, but
this is an implicit, fragile invariant: changing the button to a plain `Text` (see I5) or
restyling it silently turns every tap into **two** `controller.show_results()` calls
(double navigation). Two handlers for one intent.
Fix: keep exactly one. Recommended — drop the `Container.on_click` (`:108`) and keep the
button, or drop the button and make the whole strip the only hit target.

### B5 — LOW-MED — dead affordance when `on_tap is None` — `:85-93`, `:92`, `:108`
When `on_tap` is `None` the code still renders a visible, tappable `View` button and an
`ink=True` clickable container, but both handlers are no-ops
(`lambda e: on_tap() if on_tap else None`). The user sees an enabled button that does
nothing, and two useless handler registrations are shipped to the client every tick. The
only caller always passes a callback (`app_shell.py:901`), so this is latent — but the
function signature explicitly allows `None` (`:20`).
Fix: render the button only when `on_tap is not None`, and skip `on_click`/`ink` when it is
not.

### B6 — LOW — `TextButton` label colour likely overridden by the theme — `:86-91`
`ft.TextButton` renders its `content` through the Material 3 button style; the inner
`ft.Text(color=AppColors.PRIMARY)` (`:90`) is frequently overridden by the theme’s
foregroundColor, so the gold `#A68E59` may not appear at all. Cosmetic, but if the gold
brand colour is intended, style the button (`ft.ButtonStyle`) instead of the inner text.

### B7 — LOW — hardcoded M3 surface token ignores the app palette / dark mode — `:105`
`bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST` is a raw Material 3 role token, while the
project defines its own surface ramp (`core/theme.py:31-45`, e.g. `DARK_SURFACE`,
`LIGHT_SURFACE`). If the theme does not map `surfacecontainerhighest`, the banner gets a
default M3 surface that will not match dark mode. Same class of issue for `AppColors.PRIMARY`
gold on a light surface (contrast).
Fix: consume the theme’s surface token for the active mode.

### B8 — INFO — no progress semantics for screen readers — `:75-80`
`ft.ProgressBar` supports `semantics_label` / `semantics_value` in 1.0.4
(`controls/material/progress_bar.py:76-79`); neither is set, so the bar is announced as an
unlabelled 0–100 % indicator.

### Non-findings (checked, clean)
- **No None-page risk**: the component never touches `page`.
- **No unmount cleanup / leaked callbacks**: it registers no timers, no subscriptions, no
  `on_mount`/`on_unmount` hooks, and allocates no services. The only captured references are
  the two lambdas holding `on_tap` (`:92`, `:108`), which die with the discarded subtree.
  This is the cleanest part of the file.
- **No division by zero** (see §3).
- **No unreachable branches**: all three icon branches (`:24-29`) are reachable
  (`MODE_EMAIL`/`MODE_PHONE` from `core/constants.py`); `finishing` (`:32`) and the
  `total > 0` / `else` branches (`:35`) are all reachable; `on_tap` optional path (`:92`,
  `:108`) is reachable in principle (see B5).
- **Raw user input in the title** (`:57` `f"Scanning '{target_query}'"`) is contained by
  `max_lines=1` + `overflow=ELLIPSIS` (`:61-62`); a newline in a username is truncated, not
  a layout break.

---

## 5) Improvements (concrete)

**I1 — Clamp once, reuse everywhere (fixes B1).** `:31`, `:35`, `:76` each recompute the
ratio with the same `max(total, 1)` idiom. Compute `ratio` and `pct` once at the top:
```python
ratio = 0.0 if total <= 0 else min(1.0, max(0.0, checked / total))
pct = int(ratio * 100)
```
then use `pct` in the string and `ratio` for `ProgressBar(value=ratio if total > 0 else None)`.
This removes the duplicated division and the >100 % class of bug in one edit.

**I2 — Use `bar_height=3` instead of `height=3` (fixes B2)** at `:79`.

**I3 — Give the banner a stable identity (fixes B3).** Add
`key=ft.ValueKey("active-scan-banner")` to the returned Container (`:37`). flet 1.0.4 then
diffs the rebuilt banner **in place** (`object_patch.py:597-626`), so a tick emits only
`progress_str` + `ProgressBar.value` updates instead of a remove/add of 13 controls — a
direct win at 2 Hz, and it stops the ink splash (`:106`) from restarting every tick.

**I4 — One handler, one hit target (fixes B4/B5).** Either drop `Container.on_click` (`:108`)
or drop the `TextButton` (`:85-93`); and render the button only when `on_tap` is not `None`.

**I5 — Promote the whole strip to the hit target.** The current design makes a 30 px button
inside a full-width strip the only reliable tap area, and the strip already has `ink=True`
(`:106`). Making the strip the single clickable element and rendering “View” as a plain
`ft.Text` (`:86-91`) removes the double-fire risk, improves the touch target, and keeps the
brand colour of the label (which a themed `TextButton` may override anyway, B6).

**I6 — Optional rate/ETA, supplied not derived.** Add `rate: float | None = None` and
`eta_seconds: float | None = None` parameters and show e.g. `42/400 (10%) · 3.2/s · ~2m left`
in the space at `:65-70`. The values must be computed by the caller (`app_shell.py`) from a
timestamp — they cannot be derived from `checked/total` alone.

**I7 — Semantics (fixes B8).** `ft.ProgressBar(..., semantics_label=f"Scanning {checked} of {total}",
semantics_value=pct)`.

**I8 — Theme-aware colours (fixes B7).** Replace `ft.Colors.SURFACE_CONTAINER_HIGHEST`
(`:105`) with the app’s active surface token, and pick the gold/light foreground pair with
enough contrast for the label.

**I9 — Structural: make the banner a flet `Component` (kills the 2 Hz shell re-render).**
The banner is a plain function, so the shell must re-render the whole tree to refresh it
(`app_shell.py:903-905` touches `state.progress_version` and rebuilds the banner on every
tick). If `ActiveScanBanner` became a flet `Component` with its own subscription to
`state.progress_version` (or to a narrow progress slice), it could update itself via
`use_state`/`use_effect`, and the shell could drop the `progress_version` touch, the
`_live_banner()` call and the `ft.Column` wrapper at `app_shell.py:934-939`. That removes the
per-tick re-render of the entire shell subtree (and of anything mounted inside it, including
an ad view — the 2 Hz rebuild is an ad-flicker / wasted-impression risk). This is the only
change in this file that addresses the app_shell audit’s re-mount concern at the root
instead of patching the leaf.

**I10 — Cheap win: return a typed dataclass or accept an optional precomputed `ratio`.**
Minor; skip unless I1 lands as a refactor.

---

## 6) Verdict

**Verdict: functionally correct, API-clean, but with two user-visible defects and one
performance defect.**

- **flet API correctness: PASS.** Every flet symbol used exists in the installed 1.0.4 with
  the signature used; the component builds without error in the project venv for all three
  search modes and for the degenerate `0/0` and `150/100` cases. No hallucinated API, no
  deprecated API, no wrong-arity call. The only API misuse is `ProgressBar(height=…)` where
  `bar_height` is meant (B2).
- **Progress binding: PASS with a caveat.** The banner reads **no** state and depends on no
  `search_progress` field names — the contract risk is entirely in the caller
  (`app_shell.py:891-892`). Zero-division is fully guarded (`:31`, `:35`, `:76`).
- **Clamping: FAIL.** No clamp on either the percentage text (`:31`, `:35`) or the bar value
  (`:76`); `checked > total` renders “150 %” and ships `value=1.5`. Same defect class as the
  results_screen audit, on the more visible surface (B1).
- **Mounting / re-render: FAIL.** The banner is rebuilt as a fresh object every tick with no
  `key` (`:37`), so flet 1.0.4 removes and re-adds the whole 13-control subtree on the
  client each tick instead of patching two fields (B3); the ancestor wrapper in
  `app_shell.py:934-939` has the same problem and drags the memoized screen along with it.
- **Bugs: 1 high (B1), 2 medium (B2, B3), 1 medium-low (B4), 1 low-medium (B5), 2 low
  (B6, B7), 1 info (B8).**
- **Leaks / cleanup: PASS.** No timers, subscriptions, `page` references, or mount hooks —
  nothing to clean up, no None-page hazard.
- **Priority order for a fix PR:** I1 (clamp) + I2 (`bar_height`) + I3 (`ValueKey`) are a
  ~5-line change that removes the high-severity defect and the per-tick client churn;
  I4/I5 (single handler) removes the double-fire hazard; I9 (banner as a flet `Component`)
  is the structural fix that lets the shell stop re-rendering 2x/sec during scans.
