# SWARM-2026-10-20 — File audit: `src/components/stat_card.py`

**File:** `src/components/stat_card.py` (64 lines)
**Environment:** flet 1.0.4 (`.venv/lib/python3.14/site-packages` is the only truth); Python 3.14.
**Method:** Read file in full; verified every flet symbol against the installed flet 1.0.4 package via `inspect`; enumerated every call site; simulated the font ladder over representative value shapes.

---

## 1) File role

`StatCard(label, value, color, on_click) -> Control` renders a single numeric stat as a compact `ft.Container` containing an `ft.Column` of two centered `ft.Text`s: a large value (scaled 15/16/18/20 by string length) and a small dimmed label. The container gets a subtle tinted background (`bgcolor = with_opacity(OPACITY_SUBTLE, color)`), `RADIUS_MD` rounding, and optional tap handling (`on_click` + `ink` ripple paired so ink is only enabled when a handler exists). Consumed exclusively by `src/screens/results_screen.py` as a row of dashboard stat cards, several of which double as tab selectors. The docstring ("gradient accent") is inaccurate — there is no gradient, only a solid tinted bgcolor (§5).

---

## 2) API verification (flet 1.0.4)

| API usage (line) | Verified in flet 1.0.4 | Status |
|---|---|---|
| `ft.Container(..., ink=..., on_click=...)` (27-28) | `ink` and `on_click` are both valid `Container.__init__` kwargs | OK |
| `ft.Column(controls=..., spacing=..., horizontal_alignment=...)` (29, 52-53) | `spacing`, `horizontal_alignment`, `controls` all valid | OK |
| `ft.Text(value=..., size=..., weight=..., color=..., text_align=..., no_wrap=..., max_lines=...)` (31-39, 40-50) | `no_wrap`, `max_lines`, `text_align`, `weight`, `color`, `size` all valid | OK |
| `ft.FontWeight.W_800` / `W_500` (34, 43) | Both exist on `flet.FontWeight` | OK |
| `ft.Colors.with_opacity(opacity, color)` → `str` (44-46, 63) | Exists; signature `(opacity: int\|float, color: ColorValue) -> str`; `Colors.PRIMARY` and `Colors.ON_SURFACE` both exist | OK |
| `ft.Padding(left=..., right=..., top=..., bottom=...)` (56-61) | `flet.controls.padding.Padding` class exists | OK |
| `expand=True` on Container (55) | Valid | OK |
| `color: str` annotation (15) vs callers (`AppColors.SUCCESS`, `ft.Colors.ON_SURFACE`, `ft.Colors.PRIMARY`) | `with_opacity` accepts `ColorValue` (includes str); callers pass str-compatible values | OK |

**No hallucinated APIs.** Every flet symbol used in this file exists in flet 1.0.4 with the used signature. Two notes, neither a bug:
- `no_wrap=True` AND `max_lines=1` (38, 48) are redundant — `no_wrap` alone forces a single line. Harmless, but noisy.
- `ink=on_click is not None` (28) is a correct, deliberate pairing: ripple only when the card is tappable.

---

## 3) Call census

All **9 call sites** live in `src/screens/results_screen.py`; no other module imports `StatCard`.

| results_screen.py line | Label | Value passed | on_click | Notes |
|---|---|---|---|---|
| 674 | "Found" | `str(len(raw_found))` | `_goto_tab(0)` | tab selector |
| 680 | "Not Found" | `str(len(raw_not_found))` | `_goto_tab(1)` | tab selector |
| 686 | "Rate Ltd" | `str(len(raw_rate_limited))` | `_goto_tab(2)` | tab selector |
| 692 | "Unavail" | `str(len(raw_unavailable))` | `_goto_tab(3)` | tab selector |
| 874 | "Found" | `str(len(username_view.found))` | `set_tab_index(0)` | tab selector |
| 880 | "Not Found" | `str(len(username_view.not_found))` | `set_tab_index(1)` | tab selector |
| 886 | "Errors" | `str(len(username_view.errors))` | `set_tab_index(2)` | tab selector |
| 893 | "Total" | `str(total)` | `None` → `ink=False` | plain card, no action |
| import (23) | `from components.stat_card import StatCard` | — | — | — |

**Value shapes in the wild:** every caller passes `str(len(...))` — a plain non-negative integer string with no thousands separators, no sign, no decimal point, no suffix. Current values fit the ladder's assumptions: 1–4 digits → sizes 20/18/16. No "5,203+"-style formatted strings are fed today, so the scaling assumptions are not violated *at current call sites* — but the ladder is fragile if a caller later passes a formatted string (see Bug 1).

---

## 4) Bugs

**B1 — Font ladder counts characters, not digits (`stat_card.py:20-24`).**
`len(val_str)` includes commas, minus signs, decimal points, and suffixes, so a value the docstring promises fits ("5203" → 16) gets demoted the moment it is formatted: `"5,203"` (len 5) → 15, `"5,203+"` (len 6) → 15, `"-509"` (len 4) → 16, `"52.03"` (len 5) → 15. The ladder's intent ("3- and 4-digit numbers fit without wrapping") is violated for any formatted/negative/float input. Not triggered by current callers (§3) but a latent correctness bug for any future formatted value — exactly the "5,203+" overflow case in the audit scope.

**B2 — `None` renders as the literal string `"None"` (`stat_card.py:18-24`).**
`str(None)` = `"None"` (len 4) → size 16, and the card displays the text "None" instead of a placeholder such as "0" or "–". No crash occurs (so it passes smoke tests), but it silently displays misleading data. Applies to any non-numeric/non-string input (e.g. `True` → `"True"`).

**B3 — Redundant `no_wrap=True` + `max_lines=1` (`stat_card.py:38, 48`).**
Not a crash, but contradictory/noisy: `no_wrap` alone implies single-line; pairing both is dead configuration that can confuse future edits (e.g. someone removes `no_wrap` expecting wrapping, while `max_lines=1` still clamps).

---

## 5) Improvements

1. **Scale on digit count, not string length** (`stat_card.py:18-24`). Count digits only (`sum(c.isdigit() for c in val_str)` or strip non-digits before `len()`), so `"5,203"`, `"-509"`, `"52.03"` and `"5,203+"` map to the same size as their bare digit counts. Keep a floor (15) and document it.
2. **Handle `None`/non-numeric explicitly** (`stat_card.py:18`). Coerce `None` (and ideally non-numeric input) to a defined placeholder (e.g. `"0"` or `"–"`) instead of rendering `"None"`.
3. **Use `tokens.STAT_NUMBER = 18`** (`src/core/tokens.py`) as the baseline size instead of hardcoding 15/16/18/20, so the card stays consistent with the design system (tokens declares `STAT_NUMBER = 18` for precisely this purpose).
4. **Drop `max_lines=1`** (keep `no_wrap=True`) at lines 38 and 48 — removes redundancy.
5. **Fix the docstring** (lines 1-2): remove the "gradient accent" claim or add a `gradient` — the card uses a solid tinted `bgcolor` (line 63).
6. (Minor) Consider giving the non-clickable "Total" card `disabled=True` or a visual distinction, since `ink=False`/`on_click=None` makes it visually identical to tappable cards except for the absent ripple.

---

## 6) Verdict

**Not perfect.** Zero flet API violations — every symbol (`Container.ink/on_click`, `Column`, `Text.no_wrap/max_lines`, `Colors.with_opacity`, `Padding`, `FontWeight`) is valid in flet 1.0.4, `on_click`/`ink` pairing is correct, and current call sites pass only `str(len(...))` values that fit the ladder. However, there are two concrete bugs: the font ladder counts *characters* rather than *digits* (`stat_card.py:20-24`, breaks the "5,203+" assumption the moment formatted strings appear), and `None` renders as the literal `"None"` (`stat_card.py:18`). Plus three refinements (token usage, redundant `max_lines`, stale docstring). The file is safe to ship as-is today, but B1/B2 should be fixed before any caller passes formatted or optional values. No code changes were made (read-only audit).
