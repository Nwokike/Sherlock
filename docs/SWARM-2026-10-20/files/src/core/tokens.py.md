# Audit — `src/core/tokens.py`

**File:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/core/tokens.py` (156 lines, 65 module-level constants)
**Ground truth:** installed `flet 1.0.4` in `.venv` (verified via `inspect.signature` on the real classes), plus the repo at `src/`.
**Scope:** this file only. Other files are cited only as evidence of how a token is (or is not) consumed.

---

## 1) File role

`src/core/tokens.py` is the single-module design-token registry for Sherlock V3's UI layer: typography (families + a 7-step size scale), an 8-step spacing scale, a 7-step border-radius scale, icon dimensions, animation durations, an "elevation" scale, component dimensions, and an opacity scale. Every other module imports it as a module (`from core import tokens` → `tokens.SPACE_SM`) rather than importing individual names — 16 files do this.

It is a pure data module: **no imports at all**, no functions, no classes, no `flet` import, no validation, no typing. All 65 names are plain module-level `int`/`float`/`str` constants.

The file is *well-formed* in the mechanical sense, which matters for the findings below:

- `__all__` (`src/core/tokens.py:90-156`) is **complete and correct**: 65 defined / 65 exported, no duplicates, alphabetically sorted, no drift between the constant block and the export list.
- A cross-repo scan for `tokens.<NAME>` references found **0 referenced-but-undefined names** — i.e. there is no typo in a consumer that produces a silent `AttributeError`/no-op. This is the single most common failure mode for token files and it is absent here.
- All radius/spacing/size tokens are unitless numbers, which is what Flet expects (Flet takes unitless floats, not `"16px"` strings). No string paddings anywhere.

The problem with this file is not its syntax — it is that **the token system's centre of gravity has drifted away from it**. 28 of 65 tokens (43 %) have zero references, the file's own docstring describes a token family (`gradient presets`) that does not exist, and a second, competing token source lives in `src/core/theme.py`.

---

## 2) Token census (used / unused)

Method: regex `\bNAME\b` over every `.py` file in the repo (excluding `tokens.py` itself) for each of the 65 defined names, cross-checked against `tokens.NAME` attribute access (37 distinct names referenced, 0 undefined).

### Used — 37 names (57 %)

| Token | Refs | Files | Token | Refs | Files |
|---|---|---|---|---|---|
| `SPACE_SM` | 59 | 14 | `RADIUS_LG` | 5 | 5 |
| `SPACE_MD` | 48 | 12 | `OPACITY_MEDIUM` | 4 | 4 |
| `FONT_XS` | 47 | 11 | `ICON_BACKDROP` | 7 | 2 |
| `SPACE_LG` | 41 | 10 | `ICON_BACKDROP_RADIUS` | 3 | 2 |
| `SPACE_XS` | 31 | 12 | `RESULT_ICON` | 2 | 1 |
| `FONT_SM` | 29 | 9 | `RADIUS_XL` | 1 | 1 |
| `SPACE_XL` | 18 | 6 | `RADIUS_FULL` | 1 | 1 |
| `OPACITY_SUBTLE` | 36 | 7 | `ICON_EMPTY` | 4 | 1 |
| `FONT_MD` | 19 | 9 | `ICON_FEATURE` | 6 | 1 |
| `OPACITY_LIGHT` | 20 | 8 | `PROGRESS_BAR_HEIGHT` | 1 | 1 |
| `OPACITY_DIM` | 17 | 7 | `MESSAGE_MAX_WIDTH` | 1 | 1 |
| `RADIUS_MD` | 12 | 8 | `DIALOG_WIDTH_LG` | 1 | 1 |
| `RADIUS_SM` | 12 | 4 | `DIALOG_HEIGHT_LG` | 1 | 1 |
| `SPACE_XXS` | 11 | 7 | `BORDER_WIDTH_DEFAULT` | 1 | 1 |
| `ICON_MD` | 8 | 4 | `ANIM_FAST` / `ANIM_SLOW` | 1 / 1 | 1 / 1 |
| `FONT_LG` | 7 | 5 | `FONT_XL` / `FONT_XXL` | 1 / 1 | 1 / 1 |
| `OPACITY_MUTED` | 7 | 3 | `SPACE_XXXL` | 1 | 1 |
| `ICON_SM` | 6 | 5 | | | |

Adoption is **healthy at the bottom of the scales** (`SPACE_SM/MD/LG/XS`, `FONT_XS/SM/MD`, `OPACITY_SUBTLE/LIGHT/DIM`) and **near-zero at the top** (`SPACE_XL+`, `FONT_XL+`, `RADIUS_XS/XXL`, `ICON_XS/LG/XL`). The mid-scale is the only well-governed part of the system.

### Unused — 28 names (43 %) — dead code

`FONT_FAMILY_PRIMARY`, `FONT_FAMILY_MONO`, `FONT_HERO`, `SPACE_XXL`, `RADIUS_XS`, `RADIUS_XXL`, `ICON_XS`, `ICON_LG`, `ICON_XL`, `STAT_NUMBER`, `ANIM_NORMAL`, `ANIM_PAGE`, `ELEVATION_NONE`, `ELEVATION_LOW`, `ELEVATION_MED`, `ELEVATION_HIGH`, `ELEVATION_FLOAT`, `HEADER_HEIGHT`, `NAV_BAR_HEIGHT`, `SEARCH_BAR_HEIGHT`, `TEXT_FIELD_HEIGHT`, `CARD_MIN_HEIGHT`, `HERO_ICON_SIZE`, `CTA_BUTTON_WIDTH`, `BORDER_WIDTH_THIN`, `BORDER_WIDTH_FOCUS`, `OPACITY_STRONG`, `OPACITY_FULL`

Notes on the dead set:
- **All 5 `ELEVATION_*` tokens are unused** — and see Bug 2, the family targets an API that no longer exists.
- **Both `FONT_FAMILY_*` tokens are unused**, while the literal string `"Outfit"` is hardcoded at 15+ call sites — the classic "token exists, everybody bypasses it" failure.
- `HEADER_HEIGHT`, `NAV_BAR_HEIGHT`, `SEARCH_BAR_HEIGHT`, `CARD_MIN_HEIGHT`, `CTA_BUTTON_WIDTH` describe layout that is in fact hardcoded in the screen files (see §1 below).
- `STAT_NUMBER`, `ICON_LG`, `ICON_XL`, `RADIUS_XS` etc. have hardcoded equivalents sitting in the screens (see the hardcode census below).

### Duplicated values across scale families (not a bug by itself — the scales are independent)

`1` (`ELEVATION_LOW`, `BORDER_WIDTH_DEFAULT`) · `2` (`SPACE_XXS`, `BORDER_WIDTH_FOCUS`) · `4` (`SPACE_XS`, `PROGRESS_BAR_HEIGHT`) · `6` (`RADIUS_XS`, `ELEVATION_HIGH`) · `8` (`SPACE_SM`, `RADIUS_SM`) · `12` (`FONT_SM`, `SPACE_MD`, `RADIUS_MD`, `ELEVATION_FLOAT`) · `16` (`FONT_LG`, `SPACE_LG`, `RADIUS_LG`, `ICON_XS`) · `18` (`ICON_SM`, `STAT_NUMBER`, `ICON_BACKDROP_RADIUS`) · `20` (`FONT_XL`, `RADIUS_XL`, `RESULT_ICON`) · `24` (`SPACE_XL`, `RADIUS_XXL`) · `26` (`FONT_XXL`, `ICON_LG`) · `34` (`FONT_HERO`, `ICON_XL`) · `48` (`SPACE_XXXL`, `ICON_EMPTY`) · `56` (`ICON_FEATURE`, `HEADER_HEIGHT`)

The `18` collision (`ICON_SM` vs `STAT_NUMBER`) and the `56` collision are the two that matter — see Bugs 6 and 12.

### Hardcode census in the three biggest files (sampled, counted not enumerated)

| File | Lines | Raw numeric layout literals | Of which duplicate an existing token | `tokens.*` refs |
|---|---|---|---|---|
| `src/main.py` | 2452 | 0 (only `sample_size=25`, a DB param) | 0 | **0** |
| `src/screens/home_screen.py` | 1494 | 31 | **~23** | many (partial) |
| `src/screens/results_screen.py` | 1035 | 8 | 4 (`width=1` ×3 → `BORDER_WIDTH_DEFAULT`; `height=44` → `TEXT_FIELD_HEIGHT`) | partial |

`home_screen.py` duplicates: `size=12` ×6 → `FONT_SM`; `size=16` ×5 → `FONT_LG`; `size=14` ×2 → `FONT_MD`; `size=20` ×2 → `FONT_XL`; `spacing=8` ×2 → `SPACE_SM`; `spacing=4` → `SPACE_XS`; `spacing=2` → `SPACE_XXS`; `padding=12` → `SPACE_MD`; `width/height=26` ×2 → `ICON_LG`; `height=80` → `HERO_ICON_SIZE` (unused token). Off-scale leftovers with no token to reach for: `size=10` ×2, `size=15` ×2, `spacing=6` ×4, `padding=6`, `width/height=38` ×2, `height=1.3`; plus `ft.Padding(12,6,12,6)` ×3, `ft.Padding(4,4,4,4)`, `ft.Padding(32,14,32,14)`, `ft.Padding(12,8,12,8)` and one *mixed* call `ft.Padding(tokens.SPACE_LG, 6, tokens.SPACE_LG, 6)` — token and literal in the same constructor.

`src/main.py` uses **zero** tokens and zero layout literals: it delegates all styling to `screens/`, `components/` and `core/theme.py`. That is a governance hole in the token system — the largest file in the app is not governed by it.

---

## 3) Bugs (severity-ordered)

### B1 — HIGH · `src/core/tokens.py:1-6` · Docstring advertises a token family that does not exist, and overstates adoption

> "Comprehensive token system for typography, spacing, border radii, icon sizes, animation durations, elevation, and gradient presets. All UI components consume these tokens for visual consistency."

- There are **no gradient tokens** in the file (no `Gradient`/`ColorStop`/`LinearGradient` names; `ft.LinearGradient` is used nowhere in `src/`).
- "All UI components consume these tokens" is false: 28/65 tokens are unreferenced, `src/main.py` imports `tokens` **zero** times, and `src/core/theme.py` (which owns the app's card/padding/radius styling) does not import `tokens` at all.

A docstring is the one place a future reader trusts. This one over-promises and will cause a new contributor to look for gradient tokens that will never arrive, and to assume `tokens.py` is authoritative when `theme.py` actually is (partially).

### B2 — HIGH · `src/core/tokens.py:56-61` · The `ELEVATION_*` family targets a Flet API that no longer exists in 1.0.4

Verified against the installed library:

```
inspect.signature(ft.Container.__init__) -> 'elevation' MISSING, 'shadow' present
'elevation' in inspect.getsource(ft.Container) -> False
inspect.signature(ft.Card.__init__)     -> elevation=None   (exists)
```

`ft.Container` in Flet 1.0.4 has **no `elevation` parameter** — shadowing moved to `shadow=`/`ft.BoxShadow`. The obvious consumer mapping, `ft.Container(elevation=tokens.ELEVATION_LOW)`, raises `TypeError` on flet 1.0.4. The family is also 100 % unreferenced, so nothing has caught this.

The tokens are also under-specified for their only valid Flet 1.0.4 home: `ft.Card(elevation=…)` accepts the values fine (0/1/3/6/12 are in Flutter's 0-24 elevation range), but a `Container`-based card — which is what this app builds everywhere — cannot use them at all. `src/core/theme.py:277` and `:328` correctly use `ft.Card(elevation=1)` / `elevation=2`, but hardcode the numbers rather than using `tokens.ELEVATION_LOW` / `ELEVATION_MED`.

Severity is HIGH rather than critical only because nothing consumes them yet — it is a landmine, not a live crash.

### B3 — MEDIUM · `src/core/tokens.py:10` · `FONT_FAMILY_MONO = "JetBrains Mono"` names a font the app does not ship

Only `src/assets/fonts/Outfit-Variable.ttf` is bundled, and `src/main.py:478` registers exactly one family:

```python
self.page.fonts = {"Outfit": "fonts/Outfit-Variable.ttf"}
```

There is no JetBrains Mono asset and no registration for it. Any consumer of `FONT_FAMILY_MONO` would get a silent fallback (Roboto on Android), defeating the purpose of a mono token. The codebase's actual mono usage is `font_family="Courier New"` (`src/components/profile_detail_dialog.py:946`) — a *third* font, unrelated to the token.

Meanwhile `FONT_FAMILY_PRIMARY` (`src/core/tokens.py:9`) is also unreferenced, and the string `"Outfit"` is hardcoded at 15+ sites: `src/main.py:478,481,482`; `src/components/profile_detail_dialog.py:276,417,628,683,714,735,756,1000`; `src/components/targets_card.py:67,73,84`; `src/components/app_header.py:180,189`; `src/components/update_dialog.py:93,106`. The token exists to be the single source for exactly this, and is bypassed everywhere.

### B4 — MEDIUM · `src/core/tokens.py:30-37, 20-28` vs `src/core/theme.py:162-168` · Two competing radius/padding scales

```python
# src/core/theme.py:161-168 — AppStyles, never imports tokens
RADIUS_SMALL = 8      # == tokens.RADIUS_SM   (8)
RADIUS       = 12     # == tokens.RADIUS_MD   (12)
RADIUS_LARGE = 20     # == tokens.RADIUS_XL   (20)
PADDING_SMALL = 8     # == tokens.SPACE_SM    (8)
PADDING       = 16    # == tokens.SPACE_LG    (16)
PADDING_LARGE = 24    # == tokens.SPACE_XL    (24)
```

Six exact value duplicates living in a second module that has no link to `tokens.py`. `theme.py` additionally hardcodes `radius=12` / `radius=20` eight times (`src/core/theme.py:268,277,278,282,319,328,329,333`), `padding=16` (`:202`), `spacing=10` / `spacing=12` (`:192`, `:200`), `size=18` / `size=14` (`:184`, `:187`), and `ft.Colors.with_opacity(0.08, …)` (`:194`) — which is exactly `tokens.OPACITY_LIGHT`.

Net effect: a change to `tokens.RADIUS_MD` changes only part of the app, and the part that most visibly defines the "premium card" look (`theme.AppStyles.section_card`) does not move.

### B5 — MEDIUM · `src/core/tokens.py:81-88` · The opacity scale's naming scheme breaks down and produces two competing "faded text" values

```
OPACITY_SUBTLE 0.05 < LIGHT 0.08 < MEDIUM 0.12 < STRONG 0.20 < MUTED 0.35 < DIM 0.50 < FULL 1.0
```

The first four are an intensity ladder. `MUTED` and `DIM` are semantic adjectives that break it — "DIM" (0.50) is *stronger* than "STRONG" (0.20), and "MUTED" (0.35) is stronger than "STRONG" too. The scale has no single ordering rule.

This is not cosmetic: the same role — faded `ON_SURFACE` secondary text — is encoded by two different tokens in the *same file*:

- `tokens.OPACITY_MUTED` (0.35): `src/components/result_card.py:67` (status icon), `:73` (status icon), `:580` (query-time text)
- `tokens.OPACITY_DIM` (0.50): `src/components/result_card.py:138` (status chip text), `:623`, `:643`; `src/components/empty_state.py:57` (body copy); `src/components/stat_card.py:45`; `src/screens/settings_screen.py:227,735,1339,1406,1423`; `src/screens/history_screen.py:310`; `src/components/profile_detail_dialog.py:300,607,658`

A contributor cannot pick correctly from the name; they must know the file. The 0.35-vs-0.50 difference is exactly the kind of drift that produces "why is this text darker than that one" bugs.

### B6 — LOW-MEDIUM · `src/core/tokens.py:48` · `STAT_NUMBER` is a font size filed inside the icon block, and duplicates `ICON_SM`

```python
# src/core/tokens.py:39-48  — block header says "ICON DIMENSIONS"
ICON_SM = 18
...
STAT_NUMBER = 18  # stat card large number
```

The comment says "stat card large number" — it is a **font size**, not an icon size, and it lives under an `# ─── ICON DIMENSIONS ───` header with the same value as `ICON_SM`. A consumer reading the block (the natural way to discover "what icon size should I use") gets a text size. `src/components/stat_card.py` — the file the token names — does not import or use it; it hardcodes the number's size instead.

Fix: move to a `FONT_STAT`/`FONT_DISPLAY` name in the typography block, or into a component-specific block.

### B7 — LOW · `src/core/tokens.py:45-46, 72-73` · Two competing "circular icon backdrop" idioms, and an incorrect comment

```python
ICON_EMPTY = 48        # empty-state icon inside circle backdrop
ICON_BACKDROP = 36     # circular icon backdrop (36x36)
ICON_BACKDROP_RADIUS = 18
```

The comment on `ICON_EMPTY` is wrong. The only consumer, `src/components/empty_state.py:34-40`, does:

```python
size=tokens.ICON_EMPTY,
...
width=tokens.ICON_EMPTY * 2,      # 96
height=tokens.ICON_EMPTY * 2,     # 96
border_radius=tokens.ICON_EMPTY,  # 48  -> a 96px circle
```

So the icon is 48 and the circle is 96 — the opposite of "icon inside backdrop". And it bypasses `ICON_BACKDROP`/`ICON_BACKDROP_RADIUS` (36/18, used by `src/screens/settings_screen.py` and `src/components/targets_card.py`) entirely. Two different circle-backdrop sizes (36 and 96) and two different derivations (`ICON_BACKDROP` pair vs `ICON_EMPTY * 2`) now coexist for the same visual concept, and the file's comment points at the wrong one.

`ICON_BACKDROP`/`ICON_BACKDROP_RADIUS` are internally consistent (36 / 2 = 18 ✓), which is good — but see Improvement 4 for making that relationship structural rather than arithmetic.

### B8 — LOW · `src/core/tokens.py:21-28, 12-18` · Scale gaps force consumers off-scale

- Spacing scale: 2, 4, **8**, 12, 16, 24, 32, 48 — no 6. Yet `spacing=6` appears 4× in `src/screens/home_screen.py` (lines 1012, 1051, 1088, 1125) and `padding=6` once (line 1351), plus `ft.Padding(12,6,12,6)` ×3 and `ft.Padding(tokens.SPACE_LG, 6, tokens.SPACE_LG, 6)`.
- Type scale: 11, 12, **14**, 16, 20, 26, 34 — no 10, no 15. Yet `size=10` ×2 (home_screen 207, 213), `size=15` ×2 (137, 156), and `ft.Padding(32,14,32,14)` (padding 14 has no spacing token either).
- Border widths: `1` and `2` are tokenized, but `ft.Border.all(1.2, …)` (`src/components/active_scan_banner.py:106`) has no token.

Gaps are normal in a scale; the bug is that the gaps fall exactly where the UI actually needed a step, so the tokens get bypassed rather than extended.

### B9 — LOW · `src/core/tokens.py:40-44` · Icon scale is decorative; the real icon sizes are hardcoded

`ICON_XS` (16), `ICON_LG` (26), `ICON_XL` (34) have zero references, while `src/screens/home_screen.py` hardcodes `ft.Icon(icon, size=16)` (line 195) — which is exactly `ICON_XS` — and `width=26, height=26` (lines 301-302) — exactly `ICON_LG`. The tokens exist and the consumers reproduce the values by hand, so the scale and reality can drift.

### B10 — LOW · `src/core/tokens.py:50-54` · The animation scale is nearly absent, and the app's dominant durations have no scale at all

Only `ANIM_FAST` (settings_screen:386) and `ANIM_SLOW` (onboarding_screen:176) are used — both as `ft.Animation(duration, ft.AnimationCurve.EASE_OUT)`, which is correct Flet usage (int milliseconds).

But the numbers that actually dominate the app are snackbar timeouts, and they are all raw: `duration=6000` (`src/main.py:323`), `8000` (`src/main.py:1123,1579,2288,2376`), `10000` (`src/main.py:922,1174,1484,1710,2273,2353`, `src/app_shell.py:468`). The token file has an animation-duration scale but no timeout scale, so the most-repeated duration in the codebase has no home.

### B11 — INFO · `src/core/tokens.py:1-156` · No `flet` import; `ft.BorderRadius` is never constructed anywhere

The file imports nothing, so it cannot express a per-corner radius. `ft.BorderRadius` **does** exist in flet 1.0.4, and `BorderRadiusValue = int | float | flet.controls.border_radius.BorderRadius` — so passing the raw `int` radii straight into `border_radius=` is valid and is what every consumer does (`src/components/result_card.py`, `src/screens/home_screen.py`, etc.). That part is type-correct.

Two consequences worth recording:
- The `int`-radius convention is correct but **undocumented** — nothing in the file says "these are ints for `border_radius=`, not `ft.BorderRadius` objects", so a future contributor may "fix" it by wrapping every radius in `ft.BorderRadius(all=...)` and break the `RADIUS_FULL` idiom.
- Asymmetric radii (e.g. top-only rounded headers) cannot be expressed through this module at all.

### B12 — INFO · `src/core/tokens.py:56-61` · No z-index family — and, correctly, none is needed

The app has zero `ft.Stack` and zero `z_index` usages, and flet 1.0.4's `ft.Stack` has **no** `z_index` parameter (paint order is the list order). So a `Z_INDEX_*` family would be meaningless for this stack. The correct Flet-1.0 concept for "shadow depth" is `ft.Container.shadow` / `ft.BoxShadow`, not `elevation` — which is exactly the trap in B2.

### Positive check (no issue) — type correctness across the file

- Padding/spacing/size/radius tokens are all plain `int`; Flet accepts unitless numbers for `padding`, `margin`, `spacing`, `size`, `width`, `height`, `border_radius`. No `"16px"`-style strings anywhere. ✓
- `BORDER_WIDTH_THIN = 0.5` (`src/core/tokens.py:75`) is the only float in the integer family; Flet's `BorderSide(width=…)` accepts a float, so it is valid — but it is the only value of its kind and `1.2` borders exist in the app (`active_scan_banner.py:106`) with no token.
- `OPACITY_*` are floats; `Container.opacity` defaults to `1.0` and accepts floats. ✓
- `DIALOG_WIDTH_LG`/`DIALOG_HEIGHT_LG` map to Flet `Dialog.width`/`height`. ✓
- `RADIUS_FULL = 999` is used at `src/screens/home_screen.py:1316` inside `ft.RoundedRectangleBorder(radius=999)`, which Flet clamps to a pill shape. Correct idiom. ✓
- `ANIM_*` are used as `ft.Animation(ms, curve)` — correct unit (milliseconds). ✓

---

## 4) Improvements (concrete)

1. **Reconcile `theme.py` into `tokens.py` (fixes B4).** Delete `AppStyles.RADIUS_SMALL/RADIUS/RADIUS_LARGE` and `AppStyles.PADDING_SMALL/PADDING/PADDING_LARGE` (`src/core/theme.py:162-168`), and have `theme.py` import `tokens` (it currently doesn't) and alias: `RADIUS = tokens.RADIUS_MD`, `PADDING = tokens.SPACE_LG`, etc. — or better, replace the alias layer entirely with direct `tokens.*` references in `section_card` / the card builders. Then replace the eight hardcoded `radius=12/20` literals in `theme.py` with `tokens.RADIUS_MD` / `tokens.RADIUS_XL`.

2. **Either wire up or delete the 28 dead tokens (fixes B2, B6, B8, B9, B10).** Concretely: `ELEVATION_*` → rename to `CARD_ELEVATION_*` with a one-line comment that they map to `ft.Card(elevation=…)` **not** `ft.Container(elevation=…)` (which does not exist in flet 1.0.4), and use them at `src/core/theme.py:277,328`. `STAT_NUMBER` → move to the typography block as `FONT_STAT = 18`. `HEADER_HEIGHT`/`NAV_BAR_HEIGHT`/`TEXT_FIELD_HEIGHT`/`CARD_MIN_HEIGHT`/`CTA_BUTTON_WIDTH` → either apply them in `home_screen.py`/`app_shell.py` (which currently hardcode `height=80`, `height=44`, `width=280`-ish geometry) or delete them. `ICON_XS/LG/XL` → replace the hand-written `size=16` (home_screen:195) and `width/height=26` (301-302). `BORDER_WIDTH_THIN/FOCUS` → use at `active_scan_banner.py:106` and in focus states. Anything left dead should be deleted, not exported: 43 % dead weight in a "design system" file teaches contributors to ignore it.

3. **Rename the opacity scale to be unambiguous (fixes B5).** Replace `OPACITY_SUBTLE/LIGHT/MEDIUM/STRONG/MUTED/DIM/FULL` with a single naming rule, e.g. `OPACITY_05 / OPACITY_08 / OPACITY_12 / OPACITY_20 / OPACITY_35 / OPACITY_50 / OPACITY_FULL`, or `OPACITY_HAIRLINE / SUBTLE / SOFT / MUTED / DIM / DISABLED`. Then pick exactly one token for "faded secondary text" and use it in `result_card.py`, `empty_state.py`, `stat_card.py`, `settings_screen.py`, `history_screen.py`, `profile_detail_dialog.py` (currently a 6-way split between 0.35 and 0.50).

4. **Make the circular-backdrop relationship structural (fixes B7).** Replace the three-value idiom (`ICON_EMPTY`, `ICON_BACKDROP`, `ICON_BACKDROP_RADIUS`) with one: define `ICON_BACKDROP = 36` and `ICON_BACKDROP_RADIUS = ICON_BACKDROP // 2` (derived, so it can never disagree), and change `empty_state.py:37-39` to use `ICON_BACKDROP` + `ICON_BACKDROP_RADIUS` instead of `ICON_EMPTY * 2`. If the empty state genuinely wants a 96 px circle, add `ICON_BACKDROP_LG = 96` / `ICON_BACKDROP_LG_RADIUS = 48` rather than multiplying a font-ish size by two.

5. **Close the scale gaps where the UI already needed a step (fixes B8).** Add `SPACE_6 = 6` (used 6+ times already) and `FONT_10 = 10`, `FONT_15 = 15`; add `BORDER_WIDTH_HAIRLINE = 1.2` or fold it into `BORDER_WIDTH_THIN`. Then convert `home_screen.py`'s ~23 duplicate literals and the 5 `ft.Padding(...)` literals to tokens — including the mixed call `ft.Padding(tokens.SPACE_LG, 6, tokens.SPACE_LG, 6)`, which is the clearest signal that adoption stopped halfway.

6. **Adopt the font-family tokens and remove the 15 hardcoded `"Outfit"` literals (fixes B3).** Replace them with `tokens.FONT_FAMILY_PRIMARY`, including `src/main.py:478,481,482` where the family is registered. Either bundle a JetBrains Mono asset + register it in `src/main.py:478` or delete `FONT_FAMILY_MONO`; if the intent is a mono face, `Courier New` (`profile_detail_dialog.py:946`) should become the token, not a third name.

7. **Fix the docstring to match reality (fixes B1).** Drop "gradient presets" (or add a real `GRADIENT_*` family — `ft.LinearGradient`/`ft.RadialGradient` exist in flet 1.0.4 and the app's "glass" treatment in `theme.py:138-140` is a natural fit), and replace "All UI components consume these tokens" with the true coverage statement plus the rule for how to use them.

8. **Add a 10-line contract block to the top of the file.** It should state: (a) all values are unitless numbers in logical pixels; (b) radius tokens are plain `int`s for `border_radius=` / `RoundedRectangleBorder(radius=…)` — **not** `ft.BorderRadius` objects; (c) `*_HEIGHT`/`*_WIDTH` are logical px; (d) `ANIM_*` are milliseconds; (e) `OPACITY_*` are 0-1 floats; (f) elevation tokens map to `ft.Card(elevation=…)` only, because `ft.Container` in flet 1.0.4 has no `elevation`; (g) spacing is on a 4 px base with one documented 2 px half-step. This is the cheapest possible fix for B1/B2/B11 and prevents each of the landmines above from being re-triggered.

9. **Add a machine-checkable lint.** A ~15-line test that (i) asserts `set(__all__) == set(names defined in the module)`, (ii) asserts every name in `__all__` is referenced at least once outside `tokens.py` (or is explicitly allow-listed as "reserved"), and (iii) asserts `src/core/theme.py` contains no numeric literals for radius/padding. The repo already has a `tests/` directory; this is a 15-line file and it would have caught all of B2, B4, B6 and B7 automatically.

10. **Consume the tokens in `src/main.py`.** It has 2452 lines, zero `tokens.*` references and zero raw layout literals, meaning its styling is entirely delegated — but the app shell chrome it builds (`app_shell.py:468` uses `duration=10000`; `main.py:323` uses `duration=6000`) would benefit from the timeout scale from Improvement 5/B10.

---

## 5) Verdict

**Conditionally sound — keep the file, fix the semantics.**

Positives: the module is syntactically and mechanically correct. `__all__` is complete, sorted and duplicate-free (65/65); there are **zero** typo-induced `AttributeError`s across 16 consuming files; every value is a unitless number of the right type for Flet 1.0.4; the spacing and radius scales are internally sane; and the mid-scale (`SPACE_SM/MD/LG/XS`, `FONT_XS/SM/MD`, `OPACITY_SUBTLE/LIGHT`) is genuinely, consistently adopted across the app.

The problems are all of governance, not code:

- **Two HIGH findings are documentation/API traps**: the docstring advertises a nonexistent gradient family and claims universal adoption (B1), and the `ELEVATION_*` family maps to a `ft.Container.elevation` parameter that **does not exist in flet 1.0.4** (B2) — the first consumer to try it gets a `TypeError`.
- **The token file is not the single source of truth.** `src/core/theme.py:162-168` holds a second, unlinked copy of six radius/padding values and hardcodes eight more; `src/main.py` (the largest file) uses no tokens at all; and `src/screens/home_screen.py` reproduces ~23 token values by hand. That is the real "design system" gap.
- **43 % of the file is dead code** (28/65 unused), concentrated in the top of every scale, which is why drift is invisible: `ICON_XS` and `ICON_LG` are unused while `home_screen.py` writes the same numbers by hand.
- **Naming actively misleads in three places**: `STAT_NUMBER` is a font size filed under "ICON DIMENSIONS" (B6); `OPACITY_MUTED` (0.35) and `OPACITY_DIM` (0.50) are competing encodings of the same "faded secondary text" role with an inverted intensity ladder (B5); and `ICON_EMPTY`'s comment describes the inverse of its actual 96 px-circle use (B7).

**Priority order:** B2 → B1 → B4 → B5 → B3 → B6/B7 → B8/B9/B10 (i.e. fix the two API/doc traps, unify the two token sources, then rename the ambiguous scales, then either adopt or delete the 28 dead tokens). Nothing here requires a redesign — the file's shape is right, its contract needs to be stated and enforced, and its dead half needs to go.
