# Audit Report — src/components/targets_card.py

**File:** `src/components/targets_card.py` (112 lines)
**Audited:** read-only; no files modified
**Flet runtime:** 1.0.4 (`.venv/lib/python3.14/site-packages/flet`)
**Report sections:** 1) File role; 2) API verification; 3) Call census; 4) Bugs (severity-ordered); 5) Improvements; 6) Verdict.

---

## 1) File role

`TargetsCard(...)` is a plain (hook-free, unit-testable) function returning an `ft.Control` — a gold-tinted "network-scope summary card" on the Home dashboard. It communicates whether the search will scan **all networks** or a **custom subset**, and tapping anywhere fires `on_open()` to open `SitesScreen` for network selection.

Two branches (line 36):
- `selected_count > 0` → "custom scope": title shows `{n} networks selected`, subtitle "Scanning your custom network list", icon `CHECK_CIRCLE_ROUNDED`, brand-gold border.
- `selected_count == 0` → "everything": title "All networks selected", subtitle "Scanning all {total_label} social networks", icon `PUBLIC_ROUNDED`, adaptive glass border.

---

## 2) API verification (against flet 1.0.4)

Every flet symbol used in the file exists and is called with a compatible signature:

| Symbol / usage | Line | Verified? | Notes |
|---|---|---|---|
| `ft.Container(..., ink=True, on_click=...)` | 48-112 | YES | `ink: bool = False` exists (controls/material/container.py:109-111); `on_click` is `ControlEventHandler` |
| `ft.Border.all(width, color)` | 104 | YES | `Border.all` classmethod (controls/border.py:203-209) |
| `ft.Colors.with_opacity(opacity, color)` | 56, 106 | YES | Returns `str` (controls/colors.py:110) |
| `ft.Colors.ON_SURFACE_VARIANT` | 72 | YES | present in `Colors` enum |
| `ft.Icons.CHECK_CIRCLE_ROUNDED` | 41 | YES | present in icons.json |
| `ft.Icons.PUBLIC_ROUNDED` | 46 | YES | present in icons.json |
| `ft.Icons.CHEVRON_RIGHT_ROUNDED` | 87 | YES | present in icons.json |
| `ft.Row`/`ft.Column`/`ft.Icon`/`ft.Text`/`ft.Padding`/`ft.Margin`/`ft.Alignment.CENTER`/`ft.FontWeight.W_600` | 49-94 | YES | standard flet controls |
| `adaptive_glass_bg(page)` / `adaptive_glass_border(page)` | 103, 108 | YES | accept `ft.Page \| None` (theme.py:144,151) |

**No hallucinated flet APIs** in this file. All constructors and enum members check out.

---

## 3) Call census

**Exactly one call site** — `src/screens/home_screen.py:1258-1265`:

```python
content=TargetsCard(
    selected_count=len(state.selected_sites) if state.selected_sites else 0,
    total_count=state.sites_total,
    on_open=lambda e: controller.show_sites(),
    page=_get_page(),
),
visible=state.search_mode == MODE_USERNAME,
```

Arguments passed:
- `selected_count` → `int` (0 when nothing selected). ✓
- `total_count` → `state.sites_total`. ✓
- `on_open` → `lambda e: controller.show_sites()` — accepts the `ControlEvent` flet passes. ✓ (runs `controller.show_sites()`)
- `page` → `_get_page()` which returns `flet_context.page` or `None` on exception (home_screen.py:378-382). ✓ page IS passed, not defaulted to `None` at the call site.

**Card is conditionally visible** only in `MODE_USERNAME` (home_screen.py:1266).

No tests reference `TargetsCard` (grep over `**/test*.py` found nothing). No other call sites exist.

---

## 4) Bugs (severity-ordered)

### Bug 1 — Stale/wrong fallback total label (HIGH)

`src/components/targets_card.py:19` — `FALLBACK_TOTAL_LABEL = "2,700+"`.

The known-context catalog figures are 2,521 username + 220 email + 5 phone = **2,746**, so "2,700+" undercounts by ~46 and is stale relative to the verified catalog.

Worse, the fallback is only reached when `total_count` is falsy (`format_count(total_count) if total_count else FALLBACK_TOTAL_LABEL`, line 43) — i.e. when no total has been loaded yet (0 / None / ""). In that state the subtitle reads "Scanning all 2,700+ social networks", asserting a precise-sounding total that (a) is wrong and (b) may not even be known yet. The card fabricates a number instead of admitting the count is unavailable.

**Fix:** drop the hardcoded fallback; when `total_count` is falsy, render copy without a number (e.g. "Scanning all social networks") or source the real total from the catalog rather than hardcoding "2,700+".

### Bug 2 — `on_open` type annotation lies about the flet click-event argument (MEDIUM)

`src/components/targets_card.py:25` — `on_open: Callable[[], None] = None`; `src/components/targets_card.py:111` — `on_click=on_open`.

Flet's `Container.on_click` is a `ControlEventHandler`, which invokes the handler with a `ControlEvent` argument. The annotation `Callable[[], None]` promises zero arguments, so a caller passing a true zero-arg function would get a `TypeError` at click time (flet calls `handler(event)`). The single live call site happens to use `lambda e: ...` (home_screen.py:1263), so it works today, but the type signature is incorrect and invites future crashes.

**Fix:** annotate `on_open: Callable[[ft.ControlEvent], None] | None = None` (or `Callable[..., None]`) to match flet's `ControlEventHandler`.

### Bug 3 — "All networks selected" copy can be inaccurate when nothing is chosen (MEDIUM)

`src/components/targets_card.py:36,44` — `custom_scope = selected_count > 0`; when `selected_count == 0` the title is hardcoded "All networks selected" (line 44).

`selected_count == 0` merely means "no custom sites chosen" — it does not necessarily mean the user has explicitly opted into "all networks". At initial load (home_screen.py:1259) `selected_count` is 0 before any selection exists, yet the card declares "All networks selected" as a settled fact. The copy overstates user intent.

**Fix:** distinguish "no selection made yet" from "all networks explicitly selected"; use neutral copy such as "Scanning all networks" (or "No custom selection — scanning all networks") when `selected_count == 0`.

### Bug 4 — Silent no-op tap when `on_open` is None (LOW)

`src/components/targets_card.py:110-111` — `ink=True, on_click=on_open` where `on_open` defaults to `None`.

`ink=True` produces a ripple on tap, but if `on_open` is `None` the tap does nothing visible beyond the ripple — an affordance with no outcome. The live call site always passes a handler, but the default invites dead taps.

**Fix:** either make `on_open` required, or guard `ink=True` / the tap region behind `if on_open` so a card without a handler doesn't pretend to be interactive.

---

## 5) Improvements (concrete)

1. **Replace hardcoded `FALLBACK_TOTAL_LABEL`.** Source the real catalog total (2,746) or omit the number when unknown (see Bug 1). Do not ship a stale marketing number as a data fact.
2. **Correct the `on_open` callback type** to accept `ft.ControlEvent` (see Bug 2).
3. **Make the chevron a clearer affordance.** The `CHEVRON_RIGHT_ROUNDED` icon (line 86-90) is present but small (`ICON_SM=18`) and same-color as the subtitle (`ON_SURFACE_VARIANT`). Consider giving it `AppColors.PRIMARY` or a slightly larger size so "tap to customize" is more discoverable. The "Customize" text label (line 79-85) already helps.
4. **Pass `page` explicitly and document it.** `page` defaults to `None` (line 26); `adaptive_glass_bg`/`adaptive_glass_border` fall back to DARK glass when `page is None` (theme.py:146-148, 153-155). The live call site passes `_get_page()` (home_screen.py:1264), so the dark-glass-in-light-mode bug does **not** fire here in normal operation — but if `_get_page()` returns `None` (context unavailable), the card would render dark glass in light mode. Document that callers should pass a real `page`, or have `TargetsCard` resolve `flet.context.page` internally when `page is None` (mirroring `AppColors.grey_dim`, theme.py:104-116).
5. **`format_count` on `total_count` when it could be 0.** Line 43 short-circuits to the fallback for falsy totals; consider validating `total_count >= 0` and handling `None` explicitly rather than relying on truthiness (e.g. `total_count == 0` legitimately means "zero networks", not "unknown").

---

## 6) Verdict

**`src/components/targets_card.py` is flet-API-correct: zero hallucinated APIs, all constructors/enums valid against flet 1.0.4, and the single call site (home_screen.py:1258) passes `page`, `selected_count`, `total_count`, and `on_open` correctly.**

It is **not bug-free**. The defects are:

| Severity | Finding | Line(s) |
|---|---|---|
| HIGH | Stale/wrong `FALLBACK_TOTAL_LABEL = "2,700+"` (real total 2,746); shown when total is unknown | 19, 43 |
| MEDIUM | `on_open: Callable[[], None]` contradicts flet's `ControlEvent`-passing `on_click` | 25, 111 |
| MEDIUM | "All networks selected" overstates intent when `selected_count == 0` (initial state) | 36, 44 |
| LOW | `ink=True` ripple with `on_open=None` is a dead tap | 110-111 |

**Recommended fix order:** (1) remove/stale-proof the hardcoded total label, (2) correct the `on_open` callback type, (3) make the zero-selection copy neutral, (4) document/require `page` so the dark-glass fallback never renders in light mode.

No changes were made to any file; this is a read-only audit.