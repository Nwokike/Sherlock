# Audit Report: `src/components/empty_state.py` (88 lines)

**Verdict: USABLE — API-correct, no crash-level bugs, but not clean.** Contains a dead defensive branch and a design-token inconsistency (oversized icon backdrop that ignores the dedicated `ICON_BACKDROP` tokens). Prior report claiming "PERFECT — no issues" is wrong.

---

## 1) File role

`EmptyState(title, message, action_label, on_action, icon) -> ft.Control` — a plain function factory (testable without a renderer) returning a centered `ft.Container` holding a `ft.Column` of: an icon inside a circular backdrop, a title `ft.Text`, an optional message `ft.Text`, and an optional `ft.FilledButton`. No state, no memoization, single export. Call sites pass `title`/`message`/`icon` everywhere; only `sites_screen.py:716` passes `action_label`+`on_action` together.

---

## 2) API verification (installed flet 1.0.4)

Verified by `hasattr` + `inspect.signature` against `.venv/lib/python3.14/site-packages/flet 1.0.4`, and confirmed by headless instantiation of all three call patterns (no-action, action+handler, action-without-handler) — no exceptions.

| Usage (line) | Symbol | Status |
|---|---|---|
| :31 | `ft.Container(content, margin, border_radius, alignment, bgcolor, width, height, expand)` | OK — all kwargs valid |
| :32-36 | `ft.Icon(icon, size, color)` | OK |
| :44-50 | `ft.Text(size, weight, text_align, color)` | OK |
| :54-60 | `ft.Text(..., width=...)` | OK |
| :65-77 | `ft.FilledButton(content, on_click, style)` | OK |
| :68-76 | `ft.ButtonStyle(shape, padding)` | OK — accepted via `**kwargs` |
| :69 | `ft.RoundedRectangleBorder(radius=...)` | OK |
| :41, :81 | `ft.Alignment.CENTER` | OK |
| :84-85 | `ft.MainAxisAlignment.CENTER`, `ft.CrossAxisAlignment.CENTER` | OK |
| :48, :58 | `ft.TextAlign.CENTER` | OK |
| :47 | `ft.FontWeight.W_600` | OK |
| :35, :40 | `ft.Colors.with_opacity(opacity, color) -> str` | OK; `PRIMARY`, `ON_SURFACE` exist |
| :42, :63 | `ft.Margin(...)`, `ft.Padding(left/right/top/bottom=...)` | OK |
| :11, :24 | `ft.Control` (return annotation) | OK |
| :82 | `ft.Column(controls, alignment, horizontal_alignment, spacing)` | OK |

**Token verification** (each exists in `src/core/tokens.py` and is in `__all__`): `ICON_EMPTY=48` (:34,:37-39), `OPACITY_MEDIUM=0.12` (:35), `OPACITY_LIGHT=0.08` (:40), `SPACE_XL=24` (:42), `FONT_XL=20` (:46), `FONT_MD=14` (:56), `OPACITY_DIM=0.50` (:57), `MESSAGE_MAX_WIDTH=320` (:59), `SPACE_SM=8` (:63), `RADIUS_MD=12` (:69). All ten tokens resolve — no hallucinated token usage.

**Note on the prior report:** it references `ft.TextOverflow.ELLIPSIS` — that symbol is **not used anywhere in this file** (hallucinated cross-reference).

---

## 3) Call census

Five call sites across three screens:

| File:line | Params passed | action used? |
|---|---|---|
| `src/screens/history_screen.py:248` | title, message, icon | no |
| `src/screens/results_screen.py:250` | title, message, icon | no |
| `src/screens/sites_screen.py:680` | title, message, icon | no |
| `src/screens/sites_screen.py:693` | title, message, icon | no |
| `src/screens/sites_screen.py:716` | title, message, icon, action_label="Reset filters", on_action=_reset_filters | yes |

All five parameters are exercised across callers. `title`/`message`/`icon` are used at every site; `action_label`+`on_action` are always passed together (only sites_screen.py:716). No caller passes `action_label` without `on_action`, nor `on_action` without `action_label`, so no parameter is dead at the call level.

---

## 4) Bugs (severity-ordered)

No crash-level bugs: every flet symbol resolves, signatures match, and the function instantiates headlessly in all three call patterns. The findings below are logic/consistency defects, ordered by severity.

**4.1 Dead defensive branch (moderate)** — `src/components/empty_state.py:25-29`
The `if action_label and on_action is None:` warning branch logs "button omitted" but is **never reached by any current caller** (all five call sites pass both or neither). It is purely defensive/dead code in practice. Worse, the warning and the actual omission are decoupled: the warning logs at :25-29, but the button is only omitted because of the independent guard at :62 (`if action_label and on_action:`). If :62's guard is later changed, the :27 warning message would become inaccurate.

**4.2 Icon backdrop sizing ignores dedicated design tokens (moderate)** — `src/components/empty_state.py:37-40`
The backdrop is `width=ICON_EMPTY*2=96`, `height=96`, `border_radius=ICON_EMPTY=48` — a 96px circle around a 48px icon. `src/core/tokens.py:72-73` defines `ICON_BACKDROP = 36` ("circular icon backdrop") and `ICON_BACKDROP_RADIUS = 18` expressly for this purpose, but `empty_state.py` ignores both and hardcodes a 96px circle. The icon is visually lost in an oversized backdrop and the component is inconsistent with the rest of the design system.

---

## 5) Improvements (concrete)

1. **Align backdrop with design tokens.** Replace `width/height=tokens.ICON_EMPTY*2` and `border_radius=tokens.ICON_EMPTY` with `tokens.ICON_BACKDROP` / `tokens.ICON_BACKDROP_RADIUS`, and scale the icon to fit (e.g., icon size ≈ backdrop minus padding) so the empty-state hero icon matches `ICON_BACKDROP=36` used elsewhere.
2. **Fix the action-without-handler path.** Either (a) render a disabled `FilledButton` instead of omitting it (avoids layout shift and keeps the affordance discoverable), or (b) collapse the warning and the omission into one guarded block so the message can't lie. Currently the warning at :25-29 and the omission at :62 are decoupled.
3. **Cap title width / add overflow handling.** The message `Text` gets `width=tokens.MESSAGE_MAX_WIDTH` (:59) but the title `Text` (:44-50) has no width cap or overflow handling — a long title can overflow on narrow containers. Add `width`, `no_wrap`, `max_lines`, and/or `ft.TextOverflow.ELLIPSIS` to the title.
4. **Use Column spacing instead of a manual spacer.** `spacing=0` on the `ft.Column` (:86) plus a manual `ft.Container(height=tokens.SPACE_SM)` spacer (:63) before the button is inconsistent; use the Column's `spacing`/`run_spacing` instead.
5. **Demote or drop the dead warning.** Given no caller triggers :25-29, consider removing it or keeping it as a one-time guard that is coupled to :62.

---

## 6) Verdict

**USABLE — NEEDS MINOR FIXES.** `src/components/empty_state.py` is flet 1.0.4 API-correct, uses only real tokens, instantiates without errors, and all callers pass valid argument combinations. It is **not** defect-free: the action-without-handler warning branch is dead code, and the icon backdrop disregards the dedicated `ICON_BACKDROP`/`ICON_BACKDROP_RADIUS` tokens (96px circle vs the design system's 36px). Fix #1–#2 in section 5 before treating the component as final.
