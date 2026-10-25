# Audit — `src/components/app_header.py`

Scope: single file, 252 lines. Truth source: `flet 1.0.4` as installed in
`.venv/lib/python3.14/site-packages/flet` (verified `flet.__version__ == "1.0.4"`).
Every API claim below was re-verified against the project's own installed 1.0.4 package
and material `icons.json` (`.venv/lib/python3.14/site-packages/flet/controls/material/icons.json`),
and imported live in Python 3.14.

---

## 1) File role

`AppHeader(...)` (`src/components/app_header.py:98-252`) is the unified top application bar
factory function used across the primary screens of Sherlock V3:
- `HomeScreen` (`src/screens/home_screen.py:982`)
- `HistoryScreen` (`src/screens/history_screen.py:441`)
- `SettingsScreen` (`src/screens/settings_screen.py:1788`)

It constructs a horizontal two-column header (`src/components/app_header.py:226-252`):
- **Left**: Sherlock brand icon (`/icon.svg`, `:161-167`), optionally tinted white in dark mode,
  plus an optional title and subtitle column (`:174-198`).
- **Right**:
  - Screen-specific extra action controls (e.g. History "Clear All" button, `:202-204`),
  - KTV-style version / update chip (`_build_version_chip`, `:31-96`),
  - Theme mode cycle button (`:207-214`), cycling between Dark -> Light -> System -> Dark,
  - Optional settings gear icon button (`:216-224`).

### Architectural Nature: Pure Factory Function vs. Component
Like other controls in `src/components/`, `AppHeader` is a **plain Python factory function**,
**not** an `@ft.component`. It returns a tree of controls (`ft.Container` containing an `ft.Row`).
Because it is not an `@ft.component`:
- It cannot register hooks (`use_state`, `use_context`, `use_effect`).
- It does not subscribe reactively to `AppStateCtx` or any `@ft.observable` properties.
- State changes (such as theme toggling or background update detection) cannot trigger
  re-renders of `AppHeader` unless its caller screen observes those exact fields and completely
  rebuilds the view.

---

## 2) API verification (flet 1.0.4, project venv)

Executed live against Python 3.14 and `flet 1.0.4` in the local virtual environment.

| Line | API used | 1.0.4 verification |
|---|---|---|
| `:24-28` | `ft.ThemeMode.DARK`, `LIGHT`, `SYSTEM` | OK — enum members in `flet.controls.theme.ThemeMode`. |
| `:25` | `ft.Icons.DARK_MODE_ROUNDED` | OK — code `67349` in `icons.json`. |
| `:27` | `ft.Icons.LIGHT_MODE_ROUNDED` | OK — code `69717` in `icons.json`. |
| `:28` | `ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED` | OK — code `72323` in `icons.json`. |
| `:219` | `ft.Icons.SETTINGS_ROUNDED` | OK — code `72315` in `icons.json`. |
| `:56, 85, 179` | `ft.FontWeight.BOLD` | OK — `FontWeight.BOLD = "bold"`. |
| `:58` | `AppColors.PRIMARY` | OK — string hex `#A68E59` (`core/theme.py:16`). |
| `:59, 87` | `ft.Text(no_wrap=True)` | OK — boolean field on `flet.controls.core.text.Text`. |
| `:73, 89, 246` | `ft.Padding(10, 4, 10, 4)`, `ft.Padding(left=...)` | OK — `Padding(left, top, right, bottom)`. |
| `:75, 91` | `ft.Colors.with_opacity(opacity, color)` | OK — signature `(opacity: int \| float, color: ColorValue) -> str`. |
| `:76` | `ft.Border.all(1.5, AppColors.PRIMARY)` | OK — classmethod returning `Border` with all four sides. Note: `ft.border.all` does not exist in 1.0.4; `ft.Border.all` is the correct form. |
| `:77, 92` | `ft.Container(ink=True)` | OK — boolean property on `Container`. |
| `:161-167` | `ft.Image(src=, width=, height=, color=, fit=)` | OK — `fit=ft.BoxFit.CONTAIN` and `color` tint are valid. |
| `:170` | `ft.Alignment.CENTER` | OK — `Alignment(x=0.0, y=0.0)`. |
| `:208-214` | `ft.IconButton(icon=, icon_size=, on_click=, tooltip=)` | OK — standard `IconButton` attributes. |
| `:240, 241` | `ft.MainAxisAlignment.SPACE_BETWEEN`, `ft.CrossAxisAlignment.CENTER` | OK — enum members. |
| `:244` | `ft.Row(scroll=ft.ScrollMode.AUTO)` | OK — `ScrollableControl` mixin supports `ScrollMode.AUTO`. |

All Flet API usages, control classes, arguments, and icon constants exist and match `flet 1.0.4`.

---

## 3) State binding & Theme Synchronization

### Theme Mode Truth Source: `page.theme_mode` vs `state.theme_mode`
- **Known Context Confirmed**: At app startup (`src/main.py:640-646`), the stored theme preference
  is read from disk and written **only** to `self.page.theme_mode`:
  ```python
  saved_theme = await self.storage.get(STORAGE_THEME)
  if saved_theme == "dark":
      self.page.theme_mode = ft.ThemeMode.DARK
  elif saved_theme == "system":
      self.page.theme_mode = ft.ThemeMode.SYSTEM
  else:
      self.page.theme_mode = ft.ThemeMode.LIGHT
  ```
  `main.py` never updates `state.theme_mode` during restore. `core/state.py:38` initializes
  `theme_mode: ft.ThemeMode = ft.ThemeMode.LIGHT`.
- **How `AppHeader` reads theme**:
  `AppHeader` reads `page.theme_mode` directly (`:24`, `:112`, `:158`), **not** `state.theme_mode`.
  Therefore, when `page` is provided, `AppHeader` correctly initializes its theme icon from
  `page.theme_mode`.
- **The Divergence**: `state.theme_mode` and `page.theme_mode` diverge immediately upon cold start
  whenever `saved_theme` is `"dark"` or `"system"`:
  - `page.theme_mode` == `DARK` (or `SYSTEM`),
  - `state.theme_mode` == `LIGHT`.
- In `src/components/app_header.py:127`, `_cycle_theme` writes `state.theme_mode = new_mode` and bumps
  `state.progress_version += 1`. Only after the user manually clicks the header's theme button does
  `state.theme_mode` synchronize with `page.theme_mode`.

### Lack of Live Brightness Binding (`on_platform_brightness_change`)
- Neither `AppHeader` nor `main.py` registers any handler for `page.on_platform_brightness_change`.
- When `page.theme_mode == ft.ThemeMode.SYSTEM`, an OS brightness change (e.g. day/night transition)
  swaps the platform brightness, but no listener exists in the app to trigger a re-render or
  re-tint of the header logo (`:165`).

### Badge State Binding: Frozen Version Chip
- `_build_version_chip` (`:31-96`) reads `core_state.update_available` at construction time (`:42`).
- On app launch, `update_available` is `False` because update checking is performed asynchronously
  in the background (`main.py:2295-2310`).
- Because `AppHeader` is not an `@ft.component`, and none of the screen components observe
  `update_available`, the version chip is **frozen for the entire session** as `v{APP_VERSION}`
  (`:81-95`). When `state.update_available` flips to `True`, the header never transitions to the
  "Update Available" pill.

---

## 4) Bugs (severity-ordered)

### Severity 1 (High): Theme icon and logo color do not update when theme is cycled
**Location**: `src/components/app_header.py:109-156`, `:165`, `:208-214`

**Mechanism**:
1. In `_cycle_theme(e)` (`:109`), clicking the theme toggle changes `page.theme_mode` and calls
   `page.update()` (`:153`).
2. However, the theme `IconButton` was instantiated with a static icon:
   ```python
   ft.IconButton(
       icon=_theme_icon(page),  # evaluated once at build time!
       on_click=_cycle_theme,
       ...
   )
   ```
3. `_cycle_theme` never mutates `e.control.icon = _theme_icon(page)`!
4. Furthermore, the screens mounting `AppHeader` (`HomeScreen`, `HistoryScreen`, `SettingsScreen`)
   do **not** read `state.theme_mode` in their render functions, nor do they observe
   `state.progress_version`. Bumping `state.progress_version += 1` (`:128`) does not invalidate
   these screens.
5. As a direct result:
   - When the user clicks the theme button, the page background and text shift light/dark,
     but **the theme button icon itself stays stuck on the previous mode icon** indefinitely.
   - The brand logo image tint (`:165`, `color=ft.Colors.WHITE if is_dark else None`) is never
     updated. When switching from Dark to Light mode, the logo remains tinted solid `WHITE` against
     a light surface, rendering the brand icon invisible or severely washed out.

### Severity 2 (Medium): Version chip and theme cycle fail silently when `page` is `None`
**Location**: `src/components/app_header.py:36-40`, `:79`, `:94`, `:110-111`

**Mechanism**:
1. When screens call `AppHeader(_get_page(), ...)`, if the screen is constructing its tree before
   the page context is attached, `_get_page()` returns `None`.
2. In `_open_dialog` (`:36-40`):
   ```python
   def _open_dialog(e=None):
       if page is not None:
           show_update_dialog(page)
   ```
   Both click handlers on lines `:79` and `:94` use `on_click=lambda e: _open_dialog()`, discarding
   the event parameter `e`. When clicked, `page` in the closure is still `None`, even though `e.control.page`
   is fully available at click time. The dialog fails to open with zero user feedback.
3. In `_cycle_theme` (`:109-111`):
   ```python
   def _cycle_theme(e):
       if page is None:
           return
   ```
   `_cycle_theme` receives the event `e`, but immediately bails out if `page is None` without
   checking `getattr(e.control, "page", None)`. Theme cycling becomes permanently dead.

### Severity 3 (Medium): Update pill is never displayed during the session (frozen badge)
**Location**: `src/components/app_header.py:42-43`

**Mechanism**:
`update_available = core_state.update_available` is evaluated synchronously when `AppHeader` is
instantiated. Because the update check (`UpdateService.check_for_update`) is an async background
network call, `update_available` is always `False` when `HomeScreen` is mounted. When the background
task resolves and sets `state.update_available = True`, no reactive subscription exists in `AppHeader`
or `HomeScreen` to re-evaluate `_build_version_chip`. The update pill is never shown during the session.

### Severity 4 (Low): Awkward wording `"Update: Update Available!"` on missing version key
**Location**: `src/components/app_header.py:45-56`

**Mechanism**:
```python
label = (
    update_data.get("version", "Update")
    if update_data.get("type") != "announcement"
    else "News"
)
...
ft.Text(
    f"Update: {label} Available!"
    if update_data.get("type") != "announcement"
    else "News",
    ...
)
```
If an update dictionary does not contain a `"version"` key (or has `version: None`), `label`
defaults to `"Update"`. The resulting string rendered in the pill is `"Update: Update Available!"`.
Additionally, lines `:47-48` and `:54-55` duplicate the ternary check for `type == "announcement"`.

### Severity 5 (Low): Redundant shadow import of `state` inside `_cycle_theme`
**Location**: `src/components/app_header.py:16`, `:125`

**Mechanism**:
Module already imports `from core.state import state as core_state` on line `:16`.
Inside `_cycle_theme`, line `:125` redundantly performs `from core.state import state`.

### Severity 6 (Low): Inert Settings button when `on_settings` is `None`
**Location**: `src/components/app_header.py:216-224`

**Mechanism**:
`AppHeader` defaults `show_settings=True` (`:103`) and `on_settings=None` (`:104`). If a caller
omits `on_settings`, a settings gear icon is still placed in the header, but clicking it executes
`None`, producing no action or feedback.

---

## 5) Improvements (concrete)

### Improvement 1: Live in-place update of theme button icon and logo color
In `_cycle_theme(e)`, resolve the active page from `page or e.control.page`, update the icon button's
own `.icon` property directly, and update the logo container's child `.color`:
```python
target_page = page or getattr(e.control, "page", None)
if target_page is None:
    return

# Update page theme mode
target_page.theme_mode = new_mode

# Directly update theme toggle icon
if hasattr(e.control, "icon"):
    e.control.icon = _theme_icon(target_page)
    e.control.update()

# Directly update logo tint
if left_controls and hasattr(left_controls[0], "content"):
    left_controls[0].content.color = ft.Colors.WHITE if is_dark_mode(target_page) else None
    left_controls[0].update()
```

### Improvement 2: Safely resolve `page` from ControlEvent in `_open_dialog`
Update `_open_dialog` to accept `e: ft.ControlEvent | None` and resolve page via `page or getattr(e, "page", None) or getattr(getattr(e, "control", None), "page", None)`:
```python
def _open_dialog(e=None):
    target_page = page or (getattr(e, "page", None) if e else None) or (getattr(getattr(e, "control", None), "page", None) if e else None)
    if target_page is not None:
        from components.update_dialog import show_update_dialog
        show_update_dialog(target_page)
```
And wire `on_click=_open_dialog` (passing `e` directly instead of discarding it in a lambda).

### Improvement 3: Clean up update pill label logic
Replace duplicate ternary logic with clear fallback formatting:
```python
if update_data.get("type") == "announcement":
    chip_text = "News Available!"
elif update_data.get("version"):
    chip_text = f"Update: v{update_data['version']} Available!"
else:
    chip_text = "Update Available!"
```

### Improvement 4: Add `max_lines=1` and `overflow=ft.TextOverflow.ELLIPSIS` to Title and Subtitle
In `src/components/app_header.py:176-191`, add text overflow constraints so narrow displays (e.g.
360px mobile views) do not wrap the subtitle across multiple lines, keeping header height consistent:
```python
ft.Text(
    title,
    size=tokens.FONT_LG,
    weight=ft.FontWeight.BOLD,
    font_family="Outfit",
    max_lines=1,
    overflow=ft.TextOverflow.ELLIPSIS,
)
```

### Improvement 5: Remove redundant local import
Remove `from core.state import state` on line `:125` and use the module-scoped `core_state`.

---

## 6) Verdict

`src/components/app_header.py` is well-structured and uses valid Flet 1.0.4 controls, styles, and
icon identifiers. However, it suffers from two notable state-synchronization flaws:
1. **Theme toggle UI desynchronization**: Because `AppHeader` is a static factory function and
   `HomeScreen` does not observe `state.theme_mode`, `_cycle_theme` alters the page theme mode
   without mutating the `IconButton.icon` or the logo SVG tint. The icon remains visually stuck
   on the previous theme mode.
2. **Frozen update badge**: Like the previously audited History unseen badge, `_build_version_chip`
   is constructed once at startup before the background update check runs; without a reactive hook
   or explicit rebuild mechanism, the update pill is never rendered during the session.

Both issues have straightforward, zero-dependency remedies within the component.
