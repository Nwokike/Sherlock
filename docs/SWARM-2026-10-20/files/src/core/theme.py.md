# File Audit — `src/core/theme.py` (339 lines)

Auditor: file-audit subagent · Sherlock V3 swarm 2026-10-20
Truth source: installed **flet 1.0.4** at `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet`
(flet_version = "1.0.4", `.venv/Lib/site-packages/flet/version.py`; flutter 3.44.8)

---

## 1) File role

`src/core/theme.py` is the design-system module. It holds four concerns:

| Symbol | Lines | Purpose |
|---|---|---|
| `AppColors` | 12–116 | Brand palette constants (gold primary, slate dark surfaces, warm light surfaces) + runtime `get_*` resolvers |
| `is_dark_mode()` | 119–133 | Single predicate that resolves "is the app dark right now" |
| Glass overlay constants + `adaptive_glass_bg/border` | 136–155 | Translucent card surface/border for the current theme |
| `AppStyles` | 161–232 | Radii, padding, `section_card()`, `glass_card()`, `brand_gradient()` |
| `AppTheme.get_light_theme()` / `get_dark_theme()` | 238–339 | Material 3 `ft.Theme` factories |

Consumers (grep-verified, `src/`): 15 modules import from it — `main.py:84`, `app_shell.py:16,246`, `components/app_header.py:18`, `components/result_card.py:21`, `components/update_dialog.py:29`, `components/banner_ad.py:31`, `components/active_scan_banner.py:12`, `components/profile_detail_dialog.py:17`, `components/targets_card.py:16`, `screens/{results,home,onboarding,history,settings}_screen.py`. `AppColors` alone is referenced 252 times outside this file — it is the de-facto colour API of the whole app.

The file is **import-safe**: `from __future__ import annotations` (line 7) makes the `ft.Page | None` annotations lazy, so `ft.Page` is never evaluated at import time.

---

## 2) flet API verification

Everything in this file was checked against the **installed** flet 1.0.4 source and instantiated at runtime with the project's own venv (`sys.path.insert(0,'src')`; `AppTheme.get_light_theme()` and `get_dark_theme()` both constructed with no error).

### 2.1 Verified-correct (no hallucinated APIs in this file)

| Usage in theme.py | Installed flet 1.0.4 truth | Verdict |
|---|---|---|
| `ft.Theme(color_scheme=…, font_family=…, visual_density=…, scrollbar_theme=…, snackbar_theme=…, tab_bar_theme=…, card_theme=…, chip_theme=…, page_transitions=…)` — lines 241–288, 292–339 | `flet/controls/theme.py:3281` `class Theme` declares all nine fields (`color_scheme:3343`, `font_family:3293`, `visual_density:3598`, `scrollbar_theme:3534`, `snackbar_theme:3562`, `tab_bar_theme:3578`, `card_theme:3328`, `chip_theme:3338`, `page_transitions:3448`) | OK |
| `ft.ColorScheme(primary, on_primary, primary_container, on_primary_container, secondary, on_secondary, surface, on_surface, surface_container, surface_container_highest, on_surface_variant, error, on_error, outline, outline_variant)` — lines 242–258, 293–309 | `flet/controls/theme.py:144` `class ColorScheme` declares every one of these (incl. `surface_container` and `surface_container_highest`) | OK |
| `ft.ScrollbarTheme(thumb_color, thickness, radius)` — 261–265, 312–316 | field list: `thumb_visibility, thickness, track_visibility, radius, thumb_color, …` | OK (runtime: `radius` → `int 4`) |
| `ft.SnackBarTheme(behavior, shape, bgcolor)` — 266–270, 317–321 | field list contains all three | OK |
| `ft.TabBarTheme(indicator_size, label_color, divider_color)` — 271–275, 322–326 | field list contains all three | OK |
| `ft.CardTheme(elevation, shape)` — 276–279, 327–330 | field list contains both | OK |
| `ft.ChipTheme(show_checkmark, shape)` — 280–283, 331–334 | field list contains both | OK |
| `ft.PageTransitionsTheme(android=…, ios=…)` — 284–287, 335–338 | `flet/controls/theme.py:98` `class PageTransitionsTheme` (fields android/ios/linux/macos/windows) | OK |
| `ft.ThemeMode.SYSTEM` — line 131 | `flet/controls/types.py:860` | OK |
| `ft.Brightness.DARK` — line 132 | `flet/controls/types.py`; runtime value `'dark'` | OK |
| `ft.VisualDensity.COMFORTABLE` — 260, 311 | `flet/controls/types.py` | OK |
| `ft.TabBarIndicatorSize.TAB` — 272, 323 | `flet/controls/material/tabs.py` | OK |
| `ft.SnackBarBehavior.FLOATING` — 267, 318 | `flet/controls/material/snack_bar.py` | OK |
| `ft.PageTransitionTheme.CUPERTINO` — 285–286, 336–337 | `flet/controls/theme.py:46` | OK |
| `ft.FontWeight.W_600` — 188 | `flet/controls/types.py` | OK |
| `ft.Alignment.TOP_CENTER` / `BOTTOM_CENTER` — 224–225, 229–230 | runtime `Alignment(x=0.0,y=-1.0)` / `(x=0.0,y=1.0)` | OK |
| `ft.Colors.WHITE/BLACK/ON_SURFACE/TRANSPARENT` — 138–141, 196, 274 | present in `flet/controls/colors.py` | OK |
| `ft.Colors.with_opacity(opacity, color)` — 138–141, 196, 245, 296 | `flet/controls/colors.py:110–134` — returns `f"{color_str},{opacity}"` | OK (see B3 for the *hex* input caveat) |
| `ft.Border.all(1, color)` — 205, 214 | `flet/controls/border.py`; runtime signature `all(width, color, side)` | OK |
| `ft.RoundedRectangleBorder(radius=12)` — 268, 278, 319, 329 | `flet/controls/border.py` | OK |
| `ft.LinearGradient(begin, end, colors)` — 223–231 | field list: `colors, tile_mode, rotation, stops, _type, begin, end` | OK |
| `ft.Divider(height=1, color=…)` — 194–197 | `flet/controls/material/divider.py` | OK |
| `from flet import context` — 53, 107, 123 | `flet/__init__.py:1245` exports `context`; `flet/controls/context.py` defines `Context.page` | OK |
| `page.theme_mode` / `page.theme` / `page.dark_theme` | `flet/controls/base_page.py:169` (`theme_mode: Optional[ThemeMode] = ThemeMode.SYSTEM`), `:174` (`theme`), `:181` (`dark_theme`) | OK |
| `page.platform_brightness` | `flet/controls/page.py:571` `platform_brightness: Optional[Brightness] = None` (read-only per docstring) | OK (but see B1/B2) |
| `page.on_platform_brightness_change` | `flet/controls/page.py:614` | exists — **never referenced anywhere in `src/`** |

### 2.2 One undocumented colour-string form (not a hallucination, but unverified)

`theme.py:245` and `:296` call `ft.Colors.with_opacity(0.12, AppColors.PRIMARY)` where `PRIMARY` is a **hex string** `"#A68E59"`. `Colors.with_opacity` (`flet/controls/colors.py:133–134`) does no hex special-casing — it concatenates blindly, producing:

```
primary_container light = '#A68E59,0.12'   # runtime-verified
```

flet's own usages only ever combine opacity with *named* colours (`"grey400,0.3"`, `"white,0.9"` — `flet/controls/core/shimmer.py:53`, `flet/controls/material/tooltip.py:65,74`). The documented contract is `"color,opacity"`. Whether Flutter's colour parser accepts the *hybrid* `"#RRGGBB,opacity"` form is not covered by the Python-side contract and is not provable from the installed package. It is an **app-wide pattern** (also `src/components/active_scan_banner.py:49,78,106`, `src/components/profile_detail_dialog.py:245,265,299,403,426,575,598,607,610,612,614,657`), so if it renders correctly today it is fine — but it should be pinned to the unambiguous 8-digit-hex-with-alpha form (`"#1FA68E59"`) or verified once in the Dart parser.

### 2.3 Stale flet-version comments — NOT present in this file

Repo-wide grep for `0.86.5` / `1.0.1` finds **5** hits, **none** in `theme.py`:
`src/main.py:427` (0.86.5), `src/core/notify.py:1,4` (1.0.1), `src/screens/results_screen.py:114` (1.0.1), `src/services/ad_service.py:3` (0.86.5), `src/core/shared_services.py:1` (1.0.1).
`theme.py` contains **no version claims** — its docstring (lines 1–5) makes no flet-version assertion. **Known issue refuted for this file.**

---

## 3) Confirmed known issues

### 3.1 "SYSTEM brightness never refreshed" — outcome REAL, stated cause WRONG

> Known claim: *`:129-133` resolves `ThemeMode.SYSTEM` only via `page.platform_brightness`; `main.py:483` sets `page.theme_mode = SYSTEM` but `on_platform_brightness_change` is never wired → the palette goes stale on OS theme flip.*

**Refuted on mechanism, confirmed on outcome.**

- It is true that `on_platform_brightness_change` is never wired: repo-wide grep for `platform_brightness` returns exactly one hit inside `src/` — `theme.py:132`. No subscriber exists anywhere.
- It is **not** true that `page.platform_brightness` therefore goes stale. The Flutter client pushes the value into the Python page **independently of any Python handler**:
  - `packages/flet/lib/src/flet_backend.dart` — `FletBackend.updateBrightness(newBrightness)` does `platformBrightness = newBrightness; updateControl(page.id, {"platform_brightness": newBrightness.name});`
  - `packages/flet/lib/src/widgets/page_media.dart` — a post-frame callback compares `MediaQuery.platformBrightnessOf(context)` against the cached value and calls `updateBrightness` whenever they differ, i.e. **at page creation and on every OS theme flip**.
  - `flet/messaging/session.py:314` `Session.apply_page_patch()` → `patch_dataclass(page, patch)` applies it to the Python `Page` object.
  - The string round-trips cleanly: Dart `Brightness.dark.name == "dark"` == `ft.Brightness.DARK.value == 'dark'` (runtime-verified).
  → `is_dark_mode()` at `theme.py:130–133` therefore returns the **correct** value after an OS flip.
- **What actually goes stale is the rendered UI**, because every palette value in this file is *baked into control properties at construction time*: `theme.py:62, 68, 76, 84, 90, 96` (`get_*`), `:146, :152` (glass), `:176–177, :213–214` (cards), `:221–232` (gradient). Flipping the OS theme rebuilds the Flutter `MaterialApp` (themeMode `system`) but does **not** rebuild the Python-built containers. The app's only rebuild lever is `state.progress_version`, bumped in `src/components/app_header.py:127` on *manual* theme cycling — there is no path for an OS-driven flip.
- **Correct fix**: subscribe `page.on_platform_brightness_change` (main.py) and bump the existing rebuild lever; `theme.py` itself needs no change, but should expose the resolution helper so callers don't re-implement it.

### 3.2 "`state.theme_mode` is not the restore source of truth" — CONFIRMED

- `src/core/state.py:38` initialises `state.theme_mode = ft.ThemeMode.LIGHT`.
- `src/main.py:642/644/646` write `self.page.theme_mode` **only** — `state.theme_mode` is never updated there.
- `src/screens/settings_screen.py:337–339` reads `page.theme_mode` and falls back to `state.theme_mode`; `src/components/app_header.py:112–115` reads `page.theme_mode`.
- Net: after a restart that restores `"dark"`, `page.theme_mode == DARK` while `state.theme_mode` is still `LIGHT` → the two disagree, exactly as claimed.
- Note in this file's favour: `theme.py:130–133` reads **`page.theme_mode`**, i.e. it is the *correct* side of the disagreement. The defect lives in `main.py` / `core/state.py`, not in `theme.py`. The theme module has no defect here.
- Secondary: `main.py:483` unconditionally sets `SYSTEM` and only later does the **async** `_load_saved_state()` (main.py:636) overwrite it from storage — so a dark-mode user gets a brief SYSTEM render before the stored mode lands (flash of wrong theme on slow storage).

### 3.3 Stale flet-version comments — REFUTED for this file (see §2.3).

---

## 4) NEW bugs (severity-ordered)

### B1 — HIGH · `adaptive_glass_bg/border` return the **dark** glass in **light** mode when called without a page (2 live call sites)

`theme.py:144–155`:
```python
if page and not is_dark_mode(page):
    return LIGHT_GLASS_BG
return DARK_GLASS_BG
```
`page` is `None` → the `if` is skipped → **DARK** glass is returned. But the rest of the module resolves the ambient page for you: `AppColors._resolve_page()` (`theme.py:49–57`) falls back to `ft.context.page`, and `is_dark_mode(None)` (`theme.py:121–127`) *also* resolves `ft.context.page` internally. So `adaptive_glass_bg()` and `AppColors.get_bg()` disagree about the active theme in the exact same process.

Live call sites with **no page argument**:
- `src/screens/home_screen.py:228` → `bgcolor=adaptive_glass_bg()`
- `src/screens/home_screen.py:229` → `border=ft.Border.all(1, adaptive_glass_border())`
- `src/screens/home_screen.py:282`, `:283` → same pattern

Consequence in light mode: the card gets `"white,0.05"` over the `#FAFAFA` page background instead of the intended `"black,0.04"` — i.e. a *white-on-white, effectively invisible* panel with a `"white,0.10"` border, on two of the most prominent home-screen containers. (`src/components/banner_ad.py:121–122` and `src/components/targets_card.py:103,108` do pass `page`, so they are unaffected.)

Fix: resolve the page first (`page = AppColors._resolve_page(page)`), then branch on `is_dark_mode(page)`.

### B2 — HIGH · `is_dark_mode()` has no branch for an **unknown** brightness → light palette on a dark OS during first paint

`theme.py:130–133`:
```python
return page.theme_mode == ft.ThemeMode.DARK or (
    page.theme_mode == ft.ThemeMode.SYSTEM
    and page.platform_brightness == ft.Brightness.DARK
)
```
`page.platform_brightness` is `Optional[Brightness] = None` (`flet/controls/page.py:571`). Before the Dart post-frame callback delivers the first value, it is `None` → `None == ft.Brightness.DARK` is `False` → `is_dark_mode()` returns **False (light)**.

But the Flutter side already knows the OS is dark and, with `theme_mode=SYSTEM` + `page.dark_theme` set (`main.py:479–480`), renders the **dark** Material theme. So the first paint on a dark-OS machine is a dark Material chrome carrying **light** hand-picked surfaces (`#FAFAFA` bg, `#FFFFFF` cards, `theme.py:41–46`) — a visible light/dark mismatch that never repairs itself, because the baked colours are not re-evaluated (see §3.1).

Related missing branch: `page.theme_mode` is `Optional[ThemeMode]` (`flet/controls/base_page.py:169`) and may legitimately be `None`. `None` satisfies neither comparison → `is_dark_mode()` says **light**, while Flutter's `control_inherited_notifier.dart` resolves `ThemeMode null` to `parentTheme?.brightness` (i.e. **dark** on a dark OS). The two disagree.

### B3 — HIGH · The light `SnackBarTheme` uses the **dark** surface

`theme.py:266–270` (light) and `theme.py:317–321` (dark) are byte-identical:
```python
snackbar_theme=ft.SnackBarTheme(
    behavior=ft.SnackBarBehavior.FLOATING,
    shape=ft.RoundedRectangleBorder(radius=12),
    bgcolor=AppColors.DARK_SURFACE_2,   # #252A30 — in BOTH themes
)
```
Runtime-verified: `light snackbar bgcolor = #252A30`, `dark snackbar bgcolor = #252A30`.

A floating snackbar in light mode is painted `#252A30` (dark slate) while the light `ColorScheme` still supplies the *light* on-surface content colour — dark-on-dark, i.e. unreadable. This is a copy-paste from the dark branch; the light branch should use `AppColors.LIGHT_SURFACE_2` (`#F5F5F5`) or an inverse surface, plus an explicit `content_text_style` / `action_text_color` for contrast.

### B4 — MEDIUM · `with_opacity()` on a hex colour emits an unproven `"#RRGGBB,opacity"` string

`theme.py:245`, `theme.py:296`. See §2.2. Runtime output: `'#A68E59,0.12'`, `'#CD995F,0.15'`. flet's documented contract is `"color,opacity"` with named colours only. Low runtime risk (app-wide pattern, presumably rendering), but it is the one colour form in this file that is not backed by flet's contract, and it silently degrades to *no colour* if the parser rejects it.

### B5 — MEDIUM · `on_primary = WHITE` on the gold primary fails WCAG AA

`theme.py:244` (light) and `theme.py:295` (dark) both set `on_primary=ft.Colors.WHITE` against `primary = "#A68E59"`.

Relative luminance of `#A68E59` ≈ **0.281** → contrast vs white = **3.17 : 1**. WCAG AA requires 4.5 : 1 for normal-size text; 3 : 1 only for large text. Every gold-filled button/label in the app (primary buttons, active chips, FAB) therefore renders white-on-gold below AA.

A drop-in fix that passes: use the existing `AppColors.PRIMARY_DARK = "#8A7347"` (`theme.py:18`, luminance ≈ 0.182 → **4.53 : 1** vs white) as the interactive fill, or keep the gold and set `on_primary` to a dark ink (`#0F1114` → **6.6 : 1**). `AppColors.PRIMARY_DARK` is currently declared but never used anywhere in `src/` — it exists precisely for this.

### B6 — MEDIUM · Divider colour ignores the app's own `ColorScheme.on_surface`

`theme.py:196`: `ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)` uses the **Flutter default** `onSurface`, not the app's `ColorScheme.on_surface` (`#000000` light / `#ECEFF1` dark, `theme.py:250, :301`). The Flutter default in dark mode is ~`#E6E1E5` (near-white) at 8 % over `#1A1D22` → a washed-out, near-invisible divider that does not match `AppColors.DARK_BORDER` (`#2E3339`) used everywhere else. In light mode the default is ~`#1C1B1F`, i.e. *near-black* at 8 % → a heavy dark rule instead of the intended soft `#E0E0E0`.

### B7 — MEDIUM · Light-mode glass is a ~2 % luminance delta — effectively invisible

`theme.py:140–141`: `LIGHT_GLASS_BG = "black,0.04"`, `LIGHT_GLASS_BORDER = "black,0.08"`. Over `AppColors.LIGHT_BG = "#FAFAFA"` that is a 4 % black wash — a ~2 % luminance difference. The "premium glass card" reads as a flat block with no edge. Bumping to `0.06` / `0.14`, or pairing with an actual shadow, would make the hierarchy visible. (The same file already has `AppStyles` radii for this purpose but never combines them with the glass background.)

### B8 · MEDIUM · `AppColors.grey_dim()` and `get_text_dim()` disagree on the failure fallback

`theme.py:103–116` (`grey_dim`) catches any exception and returns **`LIGHT_TEXT_DIM`**; `theme.py:94–101` (`get_text_dim`) resolves the page to `None` and then calls `is_dark_mode(None)` (`theme.py:121–127`), which returns **`True`** on the same failure → **`DARK_TEXT_DIM`**. Same intent, two different answers. (`grey_dim` is also entirely unused — see B9.)

### B9 · LOW · Dead code — 9 public helpers and 6 constants with **zero** callers outside this file

Grep-verified across `src/` (all counts exclude `theme.py` itself):

| Dead symbol | Line | Hits outside `theme.py` |
|---|---|---|
| `AppColors.get_bg` | 60 | 0 |
| `AppColors.get_surface` | 65 | 0 |
| `AppColors.get_surface_2` | 74 | 0 |
| `AppColors.get_border` | 83 | 0 |
| `AppColors.get_text` | 90 | 0 |
| `AppColors.get_text_dim` | 95 | 0 |
| `AppColors.grey_dim` | 104 | 0 |
| `AppStyles.section_card` | 171 | 0 |
| `AppStyles.glass_card` | 209 | 0 |
| `AppStyles.PADDING_SMALL` / `PADDING` / `PADDING_LARGE` | 166–168 | 0 |
| `AppStyles.RADIUS_SMALL` / `RADIUS_LARGE` | 162, 164 | 0 |
| `DARK_GLASS_BG`, `LIGHT_GLASS_BG`, `DARK_GLASS_BORDER`, `LIGHT_GLASS_BORDER` (module-level) | 138–141 | 0 (only used internally by `adaptive_glass_*`) |

Only `AppStyles.brand_gradient` (`theme.py:219`) has an external caller (`src/screens/home_screen.py:1490`), and `AppStyles.RADIUS` (`theme.py:163`) is used only inside `theme.py`.

Also internally inconsistent: `section_card` hard-codes `padding=16` (`theme.py:203`), `spacing=10` (`theme.py:192`) and `spacing=12` (`theme.py:200`) instead of the `AppStyles.PADDING` / `AppStyles.RADIUS` constants it defines two lines above.

### B10 · LOW · Palette & scale duplicated from `src/core/tokens.py`

`src/core/tokens.py` already defines the same numbers under different names, and `theme.py` ignores them:

| `theme.py` | `tokens.py` | Divergence |
|---|---|---|
| `AppStyles.RADIUS_SMALL = 8` (162) | `RADIUS_SM = 8` (33) | same value, two names |
| `AppStyles.RADIUS = 12` (163) | `RADIUS_MD = 12` (35) | same value, two names |
| `AppStyles.RADIUS_LARGE = 20` (164) | `RADIUS_LG = 16` (37) / `RADIUS_XL = 20` (38) | **"large" is 20 here, 16 there** |
| `AppStyles.PADDING_SMALL = 8` (166) | `SPACE_SM = 8` (20) | same value, two names |
| `AppStyles.PADDING = 16` (167) | `SPACE_LG = 16` (22) | same value, two names |
| `AppStyles.PADDING_LARGE = 24` (168) | `SPACE_XL = 24` (23) | same value, two names |
| literal `0.05` / `0.08` / `0.12` (138, 196, 245) | `OPACITY_SUBTLE = 0.05` (78), `OPACITY_LIGHT = 0.08` (79), `OPACITY_MEDIUM = 0.12` (80) | literals instead of tokens (which *are* used elsewhere, e.g. `src/components/empty_state.py:35,40`) |
| literal `"Outfit"` (189, 259, 310) | `FONT_FAMILY_PRIMARY = "Outfit"` (9) | literal instead of token |

The `radius 20 vs 16` split means the codebase has two different answers for "large card radius".

### B11 · LOW · No `apply` function; themes are re-allocated on every call

`AppTheme` exposes only `get_light_theme()` (239) and `get_dark_theme()` (290). Each call allocates a **brand-new** `ft.Theme` object (`theme.py:241`, `theme.py:292`). `main.py:479–480` assigns them to `page.theme` / `page.dark_theme`, and then `main.py:481–482` mutates `self.page.theme.font_family = "Outfit"` — a **no-op**, because `get_light_theme()` already sets `font_family="Outfit"` (`theme.py:259`, `theme.py:310`). Because the objects are per-call, any caller that wants to re-apply the theme must rebuild the whole `ColorScheme` tree and re-send it over the wire. There is no idempotent `AppTheme.apply(page)`.

### B12 · LOW · `PageTransitionsTheme` overrides Android/iOS but not desktop

`theme.py:284–287` and `theme.py:335–338` set only `android` and `ios`; `linux`, `macos`, `windows` stay `None`, and flet documents those as defaulting to `ZOOM` (`flet/controls/theme.py:120–141`). Desktop therefore animates differently from mobile with no stated reason.

### B13 · LOW · Font registration coupling is invisible

`theme.py:189/259/310` reference the family `"Outfit"`, but the **asset** is registered entirely outside this module: `main.py:478` `self.page.fonts = {"Outfit": "fonts/Outfit-Variable.ttf"}` (asset present: `src/assets/fonts/Outfit-Variable.ttf`, 110 884 bytes). Any caller that uses `AppTheme.get_*_theme()` without `main.py` having set `page.fonts` gets a silent fallback to the default system font — there is no comment or assertion recording this dependency.

---

## 5) Improvements (ordered)

1. **Make `is_dark_mode` total and explicit.** Handle `theme_mode is None` and `platform_brightness is None` as distinct "unknown" states rather than defaulting to light (`theme.py:119–133`). Suggested shape: `DARK` → True; `LIGHT` → False; `SYSTEM` → `platform_brightness == DARK` (and treat `None` as "keep the last resolved value" rather than False); `None` → last resolved value.
2. **Resolve `SYSTEM` in Python and drive the page explicitly.** Set `page.theme_mode` to a concrete `LIGHT`/`DARK` after resolving the OS preference, and keep `page.theme`/`page.dark_theme` as the two factories. This removes the whole class of "Python palette ≠ Flutter theme" divergence and makes `is_dark_mode` a one-liner.
3. **Subscribe to `page.on_platform_brightness_change`** (main.py) and bump the existing `state.progress_version` rebuild lever (`src/components/app_header.py:127` is the precedent). Without it, OS-driven theme flips leave every baked surface stale (§3.1).
4. **Fix the light snackbar** (`theme.py:269`): use `AppColors.LIGHT_SURFACE_2` / an inverse surface instead of `DARK_SURFACE_2`, and set `content_text_style` + `action_text_color` so the floating snackbar is legible in both themes (B3).
5. **Raise button-label contrast**: use `AppColors.PRIMARY_DARK` (`#8A7347`, 4.53:1) as the interactive fill, or set `on_primary` to a dark ink — 3.17:1 white-on-gold currently fails AA (B5).
6. **Make `adaptive_glass_bg/border` resolve the ambient page** via `AppColors._resolve_page(page)` before branching (B1) — this is a two-line change that fixes two visible home-screen containers.
7. **Adopt `src/core/tokens.py` instead of redefining the scale.** Import `FONT_FAMILY_PRIMARY`, `RADIUS_*`, `SPACE_*`, `OPACITY_*`; delete `AppStyles.RADIUS*/PADDING*` or reduce them to aliases. This also resolves the "large radius = 20 vs 16" split (B10).
8. **Delete the 9 dead helpers and 6 dead constants**, or wire them. `get_*`/`grey_dim`/`section_card`/`glass_card` have zero callers; keeping them costs maintenance and hides the fact that the live path is `adaptive_glass_*` + raw `AppColors.*` constants (B9).
9. **Make theming idempotent**: cache `_LIGHT_THEME` / `_DARK_THEME` as module-level singletons and add `AppTheme.apply(page, mode)` that assigns `page.theme` / `page.dark_theme` / `page.theme_mode` in one call. Removes the per-call allocation and the no-op mutation at `main.py:481–482` (B11).
10. **Replace `with_opacity(hex)` with 8-digit hex-with-alpha** (`"#1FA68E59"`) or verify the Dart parser once; alternatively pre-compute the rgba int in Python (B4).
11. **Use the app's own `on_surface`** for the `section_card` divider (`theme.py:196`) instead of `ft.Colors.ON_SURFACE`, so the rule matches `AppColors.LIGHT_BORDER` / `DARK_BORDER` (B6).
12. **Raise the light-glass alpha** (`theme.py:140–141`, e.g. `0.06`/`0.14`) and/or add a shadow so the "glass" reads on a `#FAFAFA` page (B7).
13. **Set `system_overlay_style`** on both themes (`ft.Theme.system_overlay_style`, `flet/controls/theme.py:3572`; `SystemOverlayStyle.status_bar_icon_brightness` at `:735`) so Android status-bar / nav-bar icons invert with the theme — currently never set anywhere in the app.
14. **Record the font dependency** in the module docstring (`theme.py:1–5`) and/or add `AppTheme.FONT_FAMILY = tokens.FONT_FAMILY_PRIMARY`, so `page.fonts` registration is not an invisible cross-file contract (B13).
15. **Document the desktop transition gap** at `theme.py:284–287` / `335–338`, or set `linux`/`macos`/`windows` explicitly (B12).
16. **Minor**: hoist `from flet import context` to module scope (`theme.py:53, 107, 123`) — the repeated function-local import runs on every `get_*` call during every rebuild; and narrow the bare `except Exception` blocks (`theme.py:56, 115, 126`) to `RuntimeError`, which is the only exception `ft.context.page` raises (`flet/controls/context.py:66–79`).

---

## 6) Verdict

**No hallucinated flet APIs.** Every `ft.*` symbol used in `src/core/theme.py` exists in the installed flet 1.0.4, and both `ft.Theme` factories instantiate cleanly under the project venv. This file is, API-wise, the cleanest module in the audit set. It also contains **none** of the 5 stale flet-version comments (they live in `main.py`, `core/notify.py`, `screens/results_screen.py`, `services/ad_service.py`, `core/shared_services.py`).

The problems are **semantic, not syntactic**:

- **3 HIGH bugs**: the light/dark glass helpers disagree with the rest of the module about the active theme and are called with no page in two live home-screen locations (B1); `is_dark_mode()` has no branch for an unknown/`None` theme mode or an unresolved brightness and silently picks light while Flutter renders dark (B2); the light `SnackBarTheme` is a verbatim copy of the dark one and paints a dark snackbar in light mode (B3).
- **5 MEDIUM**: unproven `"#RRGGBB,opacity"` colour strings (B4), white-on-gold at 3.17:1 failing WCAG AA (B5), a divider colour drawn from Flutter's default `onSurface` instead of the app's own (B6), an invisible light-mode glass surface (B7), and two helpers that disagree on the failure fallback (B8).
- **5 LOW**: ~15 dead symbols (B9), a duplicated and *divergent* scale versus `src/core/tokens.py` (B10), no idempotent apply path and a no-op font mutation at `main.py:481–482` (B11), desktop transitions left unconfigured (B12), and an undocumented font-asset coupling (B13).

Both known issues are **substantiated**: the OS-flip staleness is real but its stated cause (`on_platform_brightness_change` unwired) is only half of it — the Dart backend already keeps `page.platform_brightness` current via `updateControl(page.id, {"platform_brightness": …})`; the real defect is that nothing rebuilds the Python-built surfaces. The `state.theme_mode` divergence is confirmed, though the defect sits in `main.py`/`core/state.py`; `theme.py` is on the correct side of that disagreement.

**Recommended order of work**: B1 → B2 (+ improvement 2/3) → B3 → B5 → improvement 7 (tokens consolidation) → B4/B6/B7 → cleanup of B9/B10. B1 and B3 are each a two-line change with a visible visual payoff; B2 plus the brightness subscription is the only fix that requires touching `main.py`.
