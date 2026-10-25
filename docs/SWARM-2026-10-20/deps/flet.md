# dep-flet — flet 1.0.4 API audit (installed package is the only source of truth)

**Audit date:** 2026-10-20
**Subject:** Sherlock-V3 (`src/`) against the installed `flet` in the project `.venv`
**Installed package root:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet`
**Method:** AST-based static verification of every `ft.*` reference in `src/` against the installed package (dataclass field introspection + class MRO + enum members), plus targeted source reads of the installed flet. No application file, `pyproject.toml` or `uv.lock` was modified.

> The V2-era background doc `/home/maikel/.zcode/workspace/default/animepahe-tv/docs/reference/dep-flet.md` describes **flet 0.85.3** and is stale for this repo. It was not used as a source of truth; every claim below is re-derived from the installed 1.0.4 source. Where the two disagree, 1.0.4 wins and the drift is called out explicitly.

---

## 1. Version & installed-source verification

| Item | Value | Evidence (installed source) |
|---|---|---|
| flet version | **1.0.4** | `flet/version.py:22` → `flet_version = "1.0.4"` |
| Flutter SDK paired with this build | 3.44.8 | `flet/version.py:31` → `flutter_version = "3.44.8"` |
| Import model | Lazy (PEP 562) — `import flet` does **not** execute the ~270-module package | `flet/__init__.py:5-7` ("The public API is imported lazily (PEP 562)") |
| Control families present | `controls/core`, `controls/material`, `controls/cupertino`, `controls/services` | `flet/controls/` listing |
| 1.x component model | `components/` with `component`, `memo`, `observable`, `router`, `hooks/` (`use_state`, `use_context`, `use_effect`, `use_ref`, `use_memo`, `use_callback`, `use_dialog`) | `flet/components/`, `flet/components/hooks/` |
| Runtime / messaging | `flet/messaging/session.py` (has `start_updates_scheduler` at :693, `__updates_scheduler` at :702) | confirms the app's `results_screen.py:265` comment still points at a live symbol |

**Key architectural confirmation:** Sherlock-V3 is already written against the **flet 1.x declarative component model**, not the 0.x imperative model. `ft.component`, `ft.use_state`, `ft.use_context`, `ft.create_context`, `ft.use_effect`, `ft.use_ref`, `ft.use_memo`, `ft.use_dialog`, `ft.memo`, `ft.observable` and `ft.context` all exist in the installed package (`flet/__init__.py` TYPE_CHECKING block; real modules under `flet/components/`). This is important: several *comments* in the app still describe the 0.86.5 imperative model, and one of them encodes a **wrong** layout assumption (BUG-7).

**Verified absence (do not use):** `ft.WebView`, `ft.Lottie`, `ft.Chart`/`ft.BarChart`/`ft.LineChart`/`ft.PieChart`, `ft.Form` and `ft.CupertinoTextfield` do **not** exist in flet 1.0.4 core (charts/media moved to separate extension packages). The app correctly uses none of them.

---

## 2. API surface the app relies on (verified / incorrect)

### 2.1 Automated verification results

Three AST passes over every `src/**/*.py` file:

1. **Name resolution** — 109 distinct `ft.<Name>` references. **0 missing.** Every symbol the app names exists on the installed `flet` module.
2. **Constructor kwargs** — every `ft.<Control>(...)` call site checked against the target class's dataclass fields *and* the whole class MRO. **0 invalid kwargs.** 68 distinct control classes are constructed (Column 47, Container 123, Text 158, Row 66, Padding 60, Icon 49, ListView 11, …).
3. **Enum members** — every `ft.<Enum>.<MEMBER>` access checked. **0 missing members.** (`ft.Colors` ×366, `ft.Icons` ×187, `ft.FontWeight` ×73, `ft.CrossAxisAlignment` ×41, `ft.Alignment` ×32, `ft.MainAxisAlignment` ×25, `ft.ThemeMode`, `ft.TextOverflow`, `ft.ControlState`, `ft.ScrollMode`, `ft.Brightness`, `ft.DismissDirection`, `ft.ClipBehavior`, `ft.PagePlatform`, `ft.AnimationCurve`, `ft.TabBarIndicatorSize`, `ft.ConnectivityType`, `ft.MarkdownExtensionSet`, `ft.SnackBarBehavior`, `ft.VisualDensity`, `ft.AppLifecycleState`, `ft.BoxFit` — all resolve.)

**Conclusion: there are zero hallucinated APIs in this app.** The problems found are behavioural, not lexical.

### 2.2 Verified-good usage (the app gets these right)

| Pattern | Where | Installed-source confirmation |
|---|---|---|
| `ft.Border.all/only`, `ft.BorderSide`, `ft.Padding.all/only/symmetric`, `ft.Margin` | 29 `ft.Border.*` call sites, 60 `ft.Padding(...)` | `flet/controls/border.py` (`all`, `only`, `symmetric`), `border_radius.py`, `padding.py`, `margin.py` — all are dataclasses with `left/top/right/bottom` and the static factories exist |
| `ft.LinearGradient(begin=, end=, colors=)` | `src/core/theme.py:223-232` | `LinearGradient` fields = `colors, tile_mode, rotation, stops, _type, begin, end` — exact match |
| `ft.Animation(duration, curve)` positional | `src/screens/onboarding_screen.py:176`, `src/screens/settings_screen.py:386` | `flet/controls/animation.py` → `Animation(duration, curve=AnimationCurve.LINEAR)`; `DurationValue` accepts int ms, and `tokens.ANIM_SLOW = 350` is int ms (`src/core/tokens.py:54`) |
| `ft.Container(animate=...)` | same two sites | `Container` dataclass has an `animate` field (verified) |
| `ft.Theme(...)` sub-themes | `src/core/theme.py:240-339` | `Theme` fields include `color_scheme, font_family, visual_density, scrollbar_theme, snackbar_theme, tab_bar_theme, card_theme, chip_theme, page_transitions` — all present, and `use_material3` defaults on |
| `ft.ColorScheme` field names | `src/core/theme.py:242-258` | `ColorScheme` has `primary, on_primary, primary_container, …, surface_container, surface_container_highest, on_surface_variant, outline, outline_variant` — all present |
| `ft.Tabs(length=, selected_index=, content=Column([TabBar, TabBarView]))` | `src/screens/results_screen.py:617-668`, `:826-...` | `flet/controls/material/tabs.py:165-204` — the installed docstring's own example uses **exactly this** shape; `Tabs.length` "Must match the length of both `flet.TabBar.tabs` and `flet.TabBarView.controls`" (tabs.py:216-221) — the app's 4/4 and 3/3 match |
| `ft.SnackBar` / `ft.BottomSheet` / `ft.AlertDialog` shown via `page.show_dialog` | `src/core/notify.py:40-46`, `src/app_shell.py:567-580` | All three are `DialogControl` subclasses: `controls/dialog_control.py:9`, `controls/material/snack_bar.py:155`, `controls/material/bottom_sheet.py:16`, `controls/material/alert_dialog.py:24` — and `use_dialog` (`components/hooks/use_dialog.py:60`) is the 1.x portal path the app uses in `app_shell.py:717` |
| `page.pop_dialog()` guard before re-showing a snack | `src/core/notify.py:42-52` | `Page.pop_dialog` exists (`flet/controls/page.py`, Page method list) |
| Service auto-registration awareness | `src/core/shared_services.py:36-40`, `src/services/ad_service.py:4-20` | `Service.__post_init__` → `page._services.register_service(self)` (`flet/controls/services/service.py:44-59`); registry push at `flet/controls/page.py:122-152` |
| `page.services.append(...)` as a keep-alive ref | `src/main.py:492,501`; `src/screens/home_screen.py:683`; `src/core/shared_services.py:57-58` | `Page.services` is a property → `self.__root_view().services`; `View.services` is `field(default_factory=list, metadata={"skip": True})` (`flet/controls/core/view.py:144`) → a pure Python-side strong ref that defeats the registry's refcount GC (`flet/controls/page.py:228-246`, `min_refs = 3` on py≥3.14 else `4`) |
| `page.run_task` / `page.run_thread` | 15 `page.run_task(` sites | Present on `Page` (method list) |
| `page.render(lambda: Component())` | `src/main.py:588` | `Page.render` exists; `page.render` + `ft.component` is the 1.x entry pattern |
| `ft.ValueKey(...)` for list identity | `src/screens/sites_screen.py:730,727` | `flet/controls/keys.py` — `ValueKey(Key)` with `_type = "value"`; `ScrollKey` exists for scroll targets |
| `ListView(build_controls_on_demand=True, cache_extent=2000)` | `src/screens/sites_screen.py:715-727`, `src/screens/results_screen.py:290-295` | `flet/controls/core/list_view.py:108-125` (`cache_extent`, pixels) and `:127-131` (`build_controls_on_demand`) |
| `ft.SelectionArea` | 1 site | `controls/material/selection_area.py` |
| `ft.SafeArea` wrapping the shell | `src/app_shell.py:941` | `controls/core/safe_area.py` |
| `ft.HapticFeedback` service (light/medium impact) | `src/app_shell.py:149,200`; `src/screens/home_screen.py:657-660` | `flet/controls/services/haptic_feedback.py` — methods `light_impact, medium_impact, heavy_impact, selection_click, vibrate` |
| `ft.Clipboard.set(...)` (in app_shell) | `src/app_shell.py:182` | `flet/controls/services/clipboard.py:19` `async def set(self, value: str)` — correct |
| `ft.Share.share_text(...)` | `src/app_shell.py:231` | `flet/controls/services/share.py` — `share_text` present |
| `ft.FilePicker.pick_files / save_file` | `src/screens/home_screen.py:685`; `src/app_shell.py:421` | `flet/controls/services/file_picker.py` — `pick_files`, `save_file`, `upload`, `get_directory_path` |
| `ft.Connectivity.get_connectivity` + `on_change` | `src/main.py:499`, `:2336-2355` | `flet/controls/services/connectivity.py` — `get_connectivity`, `on_change` |
| `ft.UrlLauncher` / `ft.OpenUrl` | `src/core/actions.py` | `flet/controls/services/url_launcher.py` — `launch_url`, `open_window`, `can_launch_url`, `supports_launch_mode` |
| `page.window.min_width/min_height` | `src/main.py:484-485` | `Page.window` defaults to `Window()` (`flet/controls/page.py:502`); `Window` has `min_width, min_height, width, height, resizable, …` |
| `ft.context.page` inside callbacks | `src/core/theme.py:53-55`, `src/app_shell.py:756-760`, many screens | `flet/controls/context.py` — `context.page` raises `RuntimeError` outside a live app; the app guards every access with `try/except` (e.g. `src/core/theme.py:52-57`, `src/app_shell.py:713-719`) |
| `ft.Border.all(1.2, ft.Colors.with_opacity(0.4, …))` | `src/components/active_scan_banner.py:106` | `ft.Colors.with_opacity` exists; float widths are allowed (`BorderSide.width`) |

### 2.3 API surface the app relies on that is **missing / wrong** in 1.0.4

| # | App symbol | Reality in installed 1.0.4 | Site in app |
|---|---|---|---|
| 1 | `ft.Clipboard.set_text` | **Does not exist.** The service exposes `set` / `get` / `set_image` / `get_image` / `set_files` / `get_files` (`flet/controls/services/clipboard.py:19,28,38,55,65,85`). A package-wide grep finds `set_text` **only** as `on_set_text` in `flet/controls/core/semantics.py:313` | `src/main.py:305` |
| 2 | `page.update_async` | **Does not exist.** `Page` exposes `update`, `schedule_update`, `render`, `run_task`, `run_thread`. `hasattr(ft.Page, "update_async")` → `False` | `src/screens/home_screen.py:684` |
| 3 | `page.go` (flet 0.x name) | **Does not exist** in 1.0.4 — it is `Page.navigate` (`flet/controls/page.py:1093`) with `push_route` (`:1012`) / `pop_views_until`. *The app does not use it* — good, no issue | n/a (avoided) |

---

## 3. Bugs & hallucinations found

Severity: **H** = broken user-visible feature · **M** = wrong/fragile behaviour under a plausible condition · **L** = stale knowledge that will cause future bugs.

### BUG-1 · H · `Clipboard.set_text` does not exist → "Copy report" notification action is a silent no-op

- **App:** `src/main.py:305` → `await shared_clipboard(self.page).set_text(line)`
- **Installed truth:** `flet/controls/services/clipboard.py:19` → `async def set(self, value: str) -> None:`. There is no `set_text` on `Clipboard`; the package-wide grep for `set_text` returns only `flet/controls/core/semantics.py:313` (`on_set_text`).
- **Impact:** the OS-notification "Copy report" action always raises `AttributeError`, which is swallowed by the `except Exception` at `src/main.py:309` → `logger.warning("Scan summary copy failed: %s", exc)`. The clipboard is **never written** and the "Scan summary copied" snackbar at `src/main.py:308` never appears. The identical feature elsewhere is correct (`src/app_shell.py:182` → `await cb.set(...)`), so this is an isolated regression, not a pattern.
- **Fix:** `await shared_clipboard(self.page).set(line)`.

### BUG-2 · H · "Jump to top" is a documented no-op on the sites list

- **App:** `src/screens/sites_screen.py:757-767` → `_root_list.current.scroll_to(offset=0, duration=250)`.
- **Installed truth:** `flet/controls/scrollable_control.py:409-411` — *"`scroll_to` … **is ineffective for controls (e.g. `flet.ListView`, `flet.GridView`) that build items dynamically**."*
- **The target list is dynamically built:** `src/screens/sites_screen.py:715-727` → `ft.ListView(controls=controls, …, build_controls_on_demand=True, cache_extent=2000, …)`.
- **Impact:** the "back to the filter controls" affordance cannot work. This is a dead end by design — the app's own comment at `sites_screen.py:744-747` says the filter controls "are list items, so once the user is past ~10 rows this is the only route back to them". The code comment cites `scrollable_control.py:386` (correct line for the signature) but omits the caveat at :409.
- **Fix (preferred):** restructure per BUG-7 — move the header block out of the list into a fixed `ft.Column` header and give the `ListView` `expand=True` as the second child; a non-dynamic list restores `scroll_to`. (Alternatively call `scroll_to` only when `build_controls_on_demand` is `False`.)

### BUG-3 · M · `page.update_async()` does not exist → dead code that masks intent

- **App:** `src/screens/home_screen.py:684` → `await page.update_async() if hasattr(page, "update_async") else None`.
- **Installed truth:** `Page` has no `update_async` (`update` / `schedule_update` only). The `hasattr` guard makes it a permanent no-op.
- **It is also unnecessary:** `ft.FilePicker()` self-registers on construction via `Service.__post_init__` → `page._services.register_service(self)` → `__internal_update()` (`flet/controls/services/service.py:44-59`; `flet/controls/page.py:122-152`), which already pushes the registration to the client. The `page.services.append(picker)` at `home_screen.py:683` is then purely the keep-alive ref.
- **Fix:** delete the line; keep the append. (Also delete the `hasattr` smell — it signals uncertainty about the pinned flet version, which is exactly 1.0.4.)

### BUG-4 · M · Tab taps may not switch tabs: the app binds the *change* event, not the *click* event

- **App:** `src/screens/results_screen.py:617-620` and `:826-829` → `ft.Tabs(selected_index=tab_index, length=4, on_change=lambda e: set_tab_index(e.control.selected_index), content=ft.Column([ft.TabBar(tabs=[ft.Tab(...)]), ft.TabBarView(...)]))`. The nested `ft.TabBar` has **no `on_click`**.
- **Installed truth:**
  - `ft.Tabs.on_change` — "Called when `selected_index` changes. The `Event.data` property … contains the index of the selected tab." (`flet/controls/material/tabs.py:255-261`) — a **change notification**.
  - `ft.TabBar.on_click` — "Called when **a tab is clicked**. The `Event.data` property … contains the index of the clicked tab." (`flet/controls/material/tabs.py:563-569`) — the **user-intent** handler.
  - `ft.Tabs.move_to(index, animation_curve=…, animation_duration=…)` (tabs.py:271-300) is the animated way to change selection.
- **Impact:** in the arrangement the app uses (its own `TabBar` inside `Tabs.content`), the tab strip is a `TabBar` and the tap signal is `TabBar.on_click`; the app never wires it. The stat cards still switch tabs (they call `set_tab_index` directly), so the UI can end up in a state where the cards and the strip disagree. At minimum this is unverified behaviour in the pinned flet; at worst the strip is inert.
- **Fix:** wire `ft.TabBar(on_click=lambda e: set_tab_index(int(e.data)))` and use `ft.Tabs.move_to(idx, animation_duration=ft.Duration(milliseconds=200))` for the animated slide (`Tabs.animation_duration` defaults to 100 ms, tabs.py:245-250).

### BUG-5 · M · SYSTEM theme mode does not follow the OS at runtime

- **App:** `src/main.py:483` → `self.page.theme_mode = ft.ThemeMode.SYSTEM`; the app's own palette is computed in Python by `is_dark_mode()` at `src/core/theme.py:119-133`, which reads `page.platform_brightness` when the mode is SYSTEM. `AppColors.get_bg/get_surface/get_text` (`theme.py:59-101`) and `adaptive_glass_bg/border` (`theme.py:144-155`) all key off that.
- **Installed truth:** `Page.platform_brightness` is **read-only** and pushed by the client (`flet/controls/page.py:571-577` — "This property is read-only"), and the change signal is `Page.on_platform_brightness_change` (`flet/controls/page.py:614-618`). The app assigns it **nowhere** (grep: 0 hits).
- **Impact:** flipping the OS theme while the app is running re-themes the *client* Material theme but leaves every Python-computed surface (backgrounds, glass tints, dim text) stale — and nothing re-renders the component tree, because no observable changed. Result: light-mode glass cards on a dark page, or near-invisible text. Only a manual theme cycle (`src/components/app_header.py:112-122`) or an unrelated re-render fixes it.
- **Fix:** `page.on_platform_brightness_change = lambda e: state.progress_version += 1` (or a dedicated `theme_version`) so the tree re-renders against the new `platform_brightness`.

### BUG-6 · M · No responsive adaptation to desktop window resize

- **App:** `src/screens/settings_screen.py:302` → `narrow = bool(page and getattr(page, "width", None) and page.width < 600)` — a one-shot read during render.
- **Installed truth:** `Page.on_resize` exists exactly for this: `flet/controls/base_page.py:218-228` — "Called when a user resizes a browser or native OS window containing Flet app … Typically used to adapt layout dynamically in response to resizes." The app never assigns it (grep: 0 hits across `src/`).
- **Second defect:** `Page.width` / `Page.height` are `Optional[Number]` (`flet/controls/base_page.py:255`, `:267`) and start as `None`; the `and page.width` guard therefore **silently disables narrow mode at startup** until the first resize event happens to populate them.
- **Impact:** on desktop, dragging the window from 1200 px to 480 px keeps the wide layout until an unrelated re-render; the settings rows never re-stack, and the `SegmentedButton`s the narrow layout was designed to relieve (`settings_screen.py:301` comment) keep squeezing.
- **Fix:** `page.on_resize = lambda e: state.progress_version += 1` (or a dedicated `viewport_width` observable) and derive `narrow` from a *stored* width with an explicit fallback (e.g. `page.width or page.window.width`).

### BUG-7 · L (but architecturally important) · A load-bearing comment is factually wrong for flet 1.0.4 and shaped the layout

- **App:** `src/screens/sites_screen.py:640-651` — *"A Column here would give it unbounded height (**flet 1.0.4 ignores `expand` on column children — no control sets `host_expanded`**) … Header controls ride inside the list instead."*
- **Installed truth:** `flet/controls/core/column.py:88` → `self._internals["host_expanded"] = True` inside `Column.init()` (also `flet/controls/core/row.py:104`, `flet/controls/core/view.py:163`). And `Control.expand`'s own docstring (`flet/controls/control.py:30-39`): *"Has effect only if the direct parent of this control is one of the following controls, or their subclasses: `flet.Column`, `flet.Row`, `flet.View`, `flet.Page`."* — i.e. `expand` **does** work on Column children in 1.0.4.
- **Consequence:** the workaround (header controls riding *inside* the `ListView`) is a 0.x-era constraint that no longer applies, and it is the direct cause of BUG-2 (no `scroll_to` on a dynamically-built list) and of the "filter controls scroll away" dead end. The same pattern is in `src/screens/history_screen.py:466-472` and `src/screens/settings_screen.py:1804-1810`.
- **Fix:** correct the comment, then re-architect as `ft.Column([header_block, ft.ListView(expand=True, …)])` — restoring `scroll_to`, sticky filters, and a stable `item_extent`.

### BUG-8 · L · `page.services.append(...)` is misunderstood as registration (it is only a keep-alive ref)

- **App:** `src/main.py:492`, `src/main.py:501`, `src/screens/home_screen.py:683`, `src/core/shared_services.py:57-58`, `src/services/ad_service.py:104,201,213,256,281,295,309`.
- **Installed truth:** `Page.services` is a **property** returning `self.__root_view().services`; `View.services` is `field(default_factory=list, metadata={"skip": True})` (`flet/controls/core/view.py:144`) → it is **never serialized to the client**. The actual client registration is `Service.__post_init__` → `page._services.register_service(self)` → `__internal_update()` (`flet/controls/services/service.py:44-59`; `flet/controls/page.py:122-152`).
- **Assessment:** the app's usage is *functionally correct* — the append is a strong Python reference that keeps the service alive against the registry's refcount sweep (`ServiceRegistry.unregister_services`, `flet/controls/page.py:228-246`, threshold `sys.getrefcount(service) > 3` on py≥3.14 else `> 4`). But the *comments* describe a 0.86.5 model, and the `if x not in page.services` membership tests are O(n) equality scans over a list that grows for the session lifetime.
- **Fix:** reword the comments to describe the registry + `View.services` keep-alive model, and index by identity (`any(s is x for s in ...)`) rather than `in`.

### DOC-DRIFT · L · Comments cite flet 0.86.5 / 1.0.1 internals

| Location | Stale text | 1.0.4 truth |
|---|---|---|
| `src/main.py:428` | "Flet 0.86.5 has zero internal batching (session.py `__updates_scheduler` drains per wake, MessagePack encode inline)" | The symbol still exists (`flet/messaging/session.py:702`) but the version reference is wrong — it is 1.0.4, and the encoder/transport has changed |
| `src/services/ad_service.py:2` | "Registration model (verified against flet 0.86.5 source)" | 1.0.4 `Service.__post_init__` (`service.py:44-59`) |
| `src/services/ad_service.py:11` | "`Service.init()` suppresses the `RuntimeError` when `ft.context.page` is unset" | The suppression now lives in `Service.__post_init__` (`service.py:53-57`) |
| `src/services/ad_service.py:13-15` | "refcount fell to <=3" | `flet/controls/page.py:239-241`: `min_refs = 3 if sys.version_info >= (3, 14) else 4` |
| `src/core/shared_services.py:1` | "(flet 1.0.1)" | 1.0.4 |

None of these are functional bugs today, but they are exactly the kind of note that produces the next one. The package is pinned at 1.0.4 in `uv.lock`; every comment should say so.

### Hallucination check — clean

**No hallucinated or invented flet APIs were found.** All 109 `ft.*` names resolve; all constructor kwargs are valid dataclass fields; all enum members exist. The three genuinely wrong symbols (BUG-1, BUG-3, and the unused `page.go`) are all *older-flet* spellings, not fabrications.

---

## 4. Unused flet capabilities with concrete integration proposals

Every API below was **verified present** in the installed 1.0.4 package (module path + dataclass field check). Ordered by value-to-effort for Sherlock specifically.

### P0 — high value, low effort

| # | Capability | Verified in | Sherlock-specific proposal |
|---|---|---|---|
| 1 | **`Page.on_platform_brightness_change`** | `flet/controls/page.py:614-618` | Fixes BUG-5. `page.on_platform_brightness_change = lambda e: state.progress_version += 1`. Sherlock computes its own surface palette in Python (`core/theme.py:119-155`), so this is *required* for correct dark mode — not a nice-to-have. |
| 2 | **`Page.on_resize`** | `flet/controls/base_page.py:218-228` | Fixes BUG-6. Wire it to a `state.viewport_width` observable and drive `narrow = viewport_width < 600` from state, not from a transient `page.width` read. Unlocks the compact settings layout on narrow desktop windows. |
| 3 | **`ft.AnimatedSwitcher`** (`content, duration, reverse_duration, switch_in_curve, switch_out_curve, transition`) | `flet/controls/core/animated_switcher.py` | Sherlock's four screens switch instantly (`app_shell.py:863-932` branch swap). Wrap the branch result in `ft.AnimatedSwitcher(content=screen, transition=ft.AnimatedSwitcherTransition.FADE, duration=ft.Duration(milliseconds=200))` for the tab/Results/Sites transitions a consumer app expects. |
| 4 | **`ft.Tabs.move_to(index, animation_curve, animation_duration)`** | `flet/controls/material/tabs.py:271-300` | Gives the Results tabs a real slide animation (`Tabs.animation_duration` defaults to only 100 ms, tabs.py:245-250). Pair with BUG-4's `TabBar.on_click` fix. |
| 5 | **`ft.ProgressRing`** (`value`) | `flet/controls/material/progress_ring.py` | The scan indicator is a `ft.ProgressBar` (2 sites). A `ProgressRing` in the app bar / results header is the modern "scan in flight" affordance; `CircularProgressIndicator` is not in 1.0.4 core — `ProgressRing` is the correct name (verified). |
| 6 | **`ft.Semantics`** (`label, hint_text, heading_level, button, toggled, value, …`) | `flet/controls/core/semantics.py` | Sherlock's result cards, stat cards and site rows are visual-only. Wrapping each card in `ft.Semantics(label=…, button=True)` makes the 2,521-module result list and the 220-module email list navigable by screen readers and by TalkBack/VoiceOver. Directly serves the "consumer app" bar. |
| 7 | **`ft.SemanticsService.announce_message(...)`** | `flet/controls/services/semantics_service.py` | Announce scan completion ("Found 12 accounts for alice") without a snackbar stealing focus. |

### P1 — materially improves the 2,521/220-module surfaces

| # | Capability | Verified in | Sherlock-specific proposal |
|---|---|---|---|
| 8 | **`ft.DataTable` / `DataColumn` / `DataRow` / `DataCell`** (incl. `DataColumn.on_sort`) | `flet/controls/material/datatable.py` | The **sites screen** (5,178 networks) is a hand-rolled `ListView` of switch rows (`sites_screen.py:600-727`). A sortable `DataTable` (columns: Network, Category, Method, Enabled) with `on_sort` gives category/method ordering, bulk-select via header checkbox, and a compact desktop presentation. Keep the `ListView` for the mobile/phone form factor. |
| 9 | **`ft.AutoComplete`** (`options`, `on_change`, …) | `flet/controls/material/auto_complete.py` | The sites filter (`sites_screen.py` `search_bar`) is a plain text field. `ft.AutoComplete` with the 5,178 network names gives type-ahead site selection — the single most useful UI for a 2,521-module engine. |
| 10 | **`ft.TextField(on_submit=…)`, `ft.SearchBar`** (`bar_leading`, `bar_hint_text`, `on_submit`, `view_*`) | `flet/controls/material/search_bar.py`; `flet/controls/material/textfield.py` | `ft.SearchBar` is already imported once but used as a plain container. It ships a built-in "view" (suggestion list) mode and `on_submit` — perfect for the results filter and the sites filter. |
| 11 | **`ft.ReorderableListView`** | `flet/controls/material/reorderable_list_view.py` | Let the user reorder the **category list** (Sherlock has category lists in the site DB) and pin favourite networks to the top of the sites screen. |
| 12 | **`ft.ListView.item_extent` / `prototype_item` / `first_item_prototype` / `semantic_child_count`** | `flet/controls/core/list_view.py:60-105` | The sites list explicitly *rejects* `item_extent` because headers + banners are mixed heights (`sites_screen.py:769-780`). Once BUG-7 is fixed (header out of the list), the body becomes homogeneous → `item_extent` + `prototype_item` unlock true virtualization for 5,178 rows, and `semantic_child_count` gives correct a11y. |
| 13 | **`ft.ResponsiveRow` / `col` / `breakpoints`** | `flet/controls/core/responsive_row.py`; `Control.col` (`flet/controls/control.py:59-63`, default 12) | Replace the hand-rolled `narrow` branch in `settings_screen.py:301` with a `ResponsiveRow` of `col=12` (phone) / `col=6` (desktop) cells. Purely declarative, no JS-style breakpoint bookkeeping. |
| 14 | **`ft.GridView`** | `flet/controls/core/grid_view.py` | The onboarding feature grid and the "category" chips in the sites screen are `Row`s of chips. A `GridView` gives a responsive card grid for onboarding steps and site categories. |
| 15 | **`ft.ContextMenu`** (`content`) | `flet/controls/material/context_menu.py` | Right-click / long-press a result row → "Open in browser, Copy URL, Copy as Markdown, Add to report". Currently long-press is unused on result cards. |
| 16 | **`ft.Dismissible` / `ft.DragTarget` / `ft.Draggable`** | `flet/controls/core/dismissible.py`, `drag_target.py`, `draggable.py` | Swipe-to-delete a history entry (`history_screen.py`) and drag-a-result-into-a-collection. `Dismissible` is already imported once but not used meaningfully. |

### P2 — polish / platform parity

| # | Capability | Verified in | Sherlock-specific proposal |
|---|---|---|---|
| 17 | **`ft.Hero`** (`tag`) | `flet/controls/core/hero.py` | Hero transition from a site avatar in the results list → the profile detail dialog (`components/profile_detail_dialog.py`, 1,162 lines). This is the single biggest "premium app" feel upgrade available and costs ~10 lines. |
| 18 | **`ft.ShaderMask`** (`shader`) | `flet/controls/core/shader_mask.py` | Apply a gold gradient to the Sherlock wordmark in `components/app_header.py` — a brand-identity win that `LinearGradient` (background-only) cannot deliver. |
| 19 | **`ft.Shimmer`** (`content`) | `flet/controls/core/shimmer.py` | Skeleton loaders for the sites list while `state.sites_version == 0` (`sites_screen.py:677-689`) and for the history list — replaces the static "Loading networks…" `EmptyState` with a modern skeleton. |
| 20 | **`ft.InteractiveViewer`** (`content`) | `flet/controls/core/interactive_viewer.py` | Pinch-zoom the PDF dossier preview and the enrichment avatar grids inside the profile dialog. |
| 21 | **`ft.Tooltip`** (`message`, `show_duration`, `wait_duration`, `prefer_below`) | `flet/controls/material/tooltip.py` | Sherlock already uses `tooltip=` on `IconButton` (a different mechanism). Use `ft.Tooltip` for the stat cards, the chips and the `ProgressBar` in the scan banner — hover-to-explain for 2,521 modules. |
| 22 | **`ft.FloatingActionButton`** | `flet/controls/material/floating_action_button.py` | A FAB on the results screen = "Export" (the primary consumer action), and on the sites screen = "Select all / Reset filters". |
| 23 | **`ft.RadioGroup`** (`content, value, on_change`) | `flet/controls/material/radio_group.py` | The Results screen's Found/Not Found/Errors filter is a `SegmentedButton`; a `RadioGroup` gives a compact, accessible single-choice control for "which status" in the compact layout. |
| 24 | **`ft.RangeSlider`** (`start_value`, `end_value`) | `flet/controls/material/range_slider.py` | Filter results by "response time" or by "HTTP status" bucket — useful for the 5,178-network "not found" bulk triage. |
| 25 | **`ft.ExpansionPanel`** / `ft.ExpansionTile` | `flet/controls/material/expansion_panel.py`, `expansion_tile.py` | `ExpansionTile` is used once; `ExpansionPanel` gives the settings screen collapsible sections (Scan Parameters / Enrichment / Storage) so 1,811 lines of settings don't become one endless scroll. |
| 26 | **`ft.MenuBar`** (`controls`, `style`) | `flet/controls/material/menu_bar.py` | A desktop menu bar (File → Export…, Edit → Copy URLs, Tools → Rescan) — a desktop-native affordance the app currently lacks. Pairs with `ft.WindowDragArea`. |
| 27 | **`ft.NavigationRail`** / **`ft.NavigationDrawer`** | `flet/controls/material/navigation_rail.py`, `navigation_drawer.py` | On wide desktop windows, a `NavigationRail` is the expected pattern for a 3-tab app; `NavigationDrawer` for the extra entry points (Results, Sites, Cross-scan, Patterns). |
| 28 | **`ft.KeyboardListener`** (`on_key_down`, `on_key_up`) | `flet/controls/core/keyboard_listener.py` | Ctrl+Enter to run a scan, Ctrl+F to focus the filter, Esc to close the profile dialog, `/` to jump to the search field. A consumer-grade keyboard layer. |
| 29 | **`ft.Screenshot`** (`content`) | `flet/controls/core/screenshot.py` | "Save result card as PNG" for sharing to social media — the `ft.Share` service is already wired (`app_shell.py:231`). |
| 30 | **`ft.BrowserContextMenu`** service | `flet/controls/services/browser_context_menu.py` | Override the right-click menu in the web build so Sherlock's own context menu (item 15) is the only one. |
| 31 | **`ft.SharedPreferences`** service (`get`, `set`, `remove`, `contains_key`, `get_keys`, `clear`) | `flet/controls/services/shared_preferences.py` | The app hand-rolls a settings store (`services/storage_service.py` + `core/constants.py` `STORAGE_*` keys). `SharedPreferences` is the platform-native, cross-platform store — keep the Python store for the desktop profile but use `SharedPreferences` for the small mobile-only prefs. |
| 32 | **`ft.StoragePaths`** service (`get_application_documents_directory`, `get_downloads_directory`, `get_application_support_directory`, …) | `flet/controls/services/storage_paths.py` | Export reports to a real Downloads folder on mobile (`app_shell.py:421` currently writes to whatever path `FilePicker.save_file` returns, and only writes the bytes on desktop, `app_shell.py:430-441`). |
| 33 | **`ft.Wakelock`** (`enable`, `disable`, `is_enabled`) | `flet/controls/services/wakelock.py` | Keep the screen on during a long scan — a scan of 2,521 modules can run for minutes; a consumer app would never let the display sleep mid-scan. |
| 34 | **`ft.Battery`** (`get_battery_level`, `is_in_battery_save_mode`) | `flet/controls/services/battery.py` | Auto-reduce scan concurrency / defer enrichment when on battery — matches the existing `STORAGE_MAX_CONNECTIONS` / concurrency knobs. |
| 35 | **`ft.ScreenBrightness`** (`set_application_screen_brightness`, `reset_application_screen_brightness`) | `flet/controls/services/screen_brightness.py` | Dim the display during long scans (or keep it bright for the terminal log view in `core/theme.py:28-29`). |
| 36 | **`ft.ShakeDetector`** | `flet/controls/services/shake_detector.py` | Shake-to-cancel a running scan — a gesture consumers expect. |
| 37 | **`ft.VerticalDivider`**, `ft.Placeholder`, `ft.RotatedBox`, `ft.WindowDragArea`, `ft.PageView`, `ft.MergeSemantics` | `flet/controls/material/vertical_divider.py`, `flet/controls/core/placeholder.py`, `rotated_box.py`, `window_drag_area.py`, `page_view.py`, `merge_semantics.py` | Small polish: `WindowDragArea` makes the custom header draggable on desktop (the app draws its own header, `components/app_header.py`); `PageView` gives a swipeable onboarding carousel; `VerticalDivider` tidies the settings rows. |

### P3 — not applicable / explicitly ruled out

- `ft.WebView`, `ft.Lottie`, `ft.Chart*` (`BarChart`/`LineChart`/`PieChart`/`ScatterChart`), `ft.Form`, `ft.CupertinoTextfield` — **do not exist** in flet 1.0.4 core. Do not propose them without adding the corresponding extension package.
- `ft.Cupertino*` family: `CupertinoActionSheet`, `CupertinoAppBar`, `CupertinoBottomSheet`, `CupertinoFilledButton`, `CupertinoTintedButton`, `CupertinoSegmentedButton`, `CupertinoSlidingSegmentedButton`, `CupertinoTimerPicker`, `CupertinoDatePicker`, `CupertinoPicker`, `CupertinoContextMenu`, `CupertinoRadio`, `CupertinoSlider`, `CupertinoCheckbox`, `CupertinoTextField`, `CupertinoNavigationBar`, `CupertinoAlertDialog`, `CupertinoActivityIndicator`, `CupertinoListTile`, `CupertinoButton`, `CupertinoSwitch` — all exist and would give Sherlock a native iOS feel; the app currently uses **zero** Cupertino controls, so on iOS it renders as a Material app with no platform identity. Recommended only if iOS is a target (the `CupertinoBottomSheet` in particular would replace the Material `BottomSheet` export sheet on iOS).

---

## 5. Modern-consumer-UI gaps

Ordered by how much they affect the "must match and exceed the wrapped engines" bar.

### 5.1 The engine's data volume is not surfaced as first-class UI

The wrapped engines expose **2,521 username modules**, **220 email modules**, cross-scan, Hudson, pattern search, and PDF/CSV/JSON exports. The UI shows one `ListView` of results with a text filter, and a sites screen listing 5,178 networks as switch rows. A consumer app for this engine would offer:

- **Sortable, filterable, column-oriented views** — `ft.DataTable` with `DataColumn.on_sort` (P1-8) for the "all 2,521 modules" matrix, letting the user sort by hit rate, latency, or category instead of scrolling 2,521 cards.
- **Bulk actions with selection semantics** — currently only "select all / clear" exist for networks (`sites_screen.py` bulk_actions). Results need the same: select N hits → copy / export / share.
- **Per-module metadata chips** — HTTP status, response time, tags (the JSON export already carries `tags`, `http_status`, `response_time_s` — `app_shell.py:334-344`) are **exported but never displayed**. Rendering them on the result card turns a URL list into an intelligence product.

### 5.2 Motion and continuity

The app has **exactly two** `ft.Animation` uses (`onboarding_screen.py:176`, `settings_screen.py:386`) and **zero** `animate_opacity` / `animate_scale` / `animate_rotation` / `AnimatedSwitcher`. Concrete consequences:

- Switching Home → Results is an instant content swap (`app_shell.py:863-932`).
- The live scan banner appears/disappears without a transition.
- Result cards do not animate in as they are found.
- The `Tabs` widget's own `animation_duration` is only 100 ms (`tabs.py:245-250`) and the app never calls `move_to`.

Proposal: `ft.AnimatedSwitcher` for the shell branch (P0-3), `Tabs.move_to` for tab slides (P0-4), `animate_opacity`/`animate_scale` on result-card entry, and `ft.ProgressRing` for the in-flight indicator (P0-5).

### 5.3 Dark mode is half-implemented

`page.theme_mode = ft.ThemeMode.SYSTEM` is set (`main.py:483`) and a full `ft.Theme` pair is authored (`core/theme.py:240-339`), but the app **re-implements theming in Python** (`AppColors`, `is_dark_mode`) instead of using Material 3's `color_scheme` roles. That works only if the Python side re-evaluates on every brightness change — which it does not (BUG-5). Modern approach: express the palette as `ft.ColorScheme` roles only, read the effective role from `page.theme`/`page.color_scheme` at render time, and keep the Python `AppColors` as a *token* source rather than a second rendering path.

### 5.4 Responsiveness

`page.width` is read once (`settings_screen.py:302`), `page.on_resize` is never set (BUG-6), and there is no `ft.ResponsiveRow` / breakpoint system anywhere. On a desktop build the app renders one fixed narrow-ish layout regardless of window size. A consumer app on Windows (the app sets `page.window.min_width = 360`, `min_height = 600` — `main.py:484-485`) should reflow at ~600 px and ~1000 px.

### 5.5 Accessibility

Only one `ft.SelectionArea` in the whole app. No `ft.Semantics`, no `SemanticsService.announce_message`, no `heading_level` on section headers (`components/section_header.py` is a plain `ft.Text`). For a results list of hundreds of rows, TalkBack/VoiceOver users currently get an undifferentiated wall of text. `ft.Semantics` (P0-6/7) and `heading_level` on `SectionHeader` are cheap and high-impact.

### 5.6 Input affordances

The result filter and the sites filter are plain text fields. `ft.AutoComplete` over the 5,178 network names (P1-9) and `ft.SearchBar` with its suggestion "view" (P1-10) would materially cut the time to "run a scan against exactly these 40 networks". `ft.KeyboardListener` (P2-28) adds the Ctrl+Enter / Ctrl+F / `/` shortcuts a consumer app is expected to have.

### 5.7 List performance at 2,521+ rows

`build_controls_on_demand=True` (results_screen.py:294, sites_screen.py:723) defers **client** layout, but the Python side still materialises every control object on every render, and the app's own comment (`results_screen.py:261-270`) notes that flet's update scheduler has no `try/except` around per-control updates — a single bad row kills the screen. The app defends against this with a per-row `try/except` (good) and with a 2 Hz render flusher (`main.py:422-450`, good). The remaining structural win is `item_extent` + `prototype_item` (P1-12), enabled by fixing BUG-7, and moving the hot path off `page.update()` entirely.

### 5.8 Missing native platform surfaces

- No `ft.Wakelock` — the display sleeps mid-scan.
- No `ft.Battery` — no power-aware throttling.
- No `ft.SharedPreferences` / `ft.StoragePaths` — the export path (`app_shell.py:417-441`) writes bytes manually on desktop and does nothing on mobile beyond `FilePicker.save_file`.
- No `ft.Cupertino*` — zero iOS-native identity.
- No `ft.WindowDragArea` — the custom header is not draggable, so the desktop window has no draggable title region.

### 5.9 What the app already does *better* than a typical consumer app (keep it)

- The single render-flusher (`main.py:422-450`) with a 2 Hz budget is a genuinely correct answer to "flet has no internal batching".
- Per-row error isolation in the results list (`results_screen.py:262-272`) prevents a single hostile payload from killing the screen.
- Service keep-alive bookkeeping for the ad services (`services/ad_service.py`) with an interval guard and explicit release.
- `use_memo` on the shell branch (`app_shell.py:909-932`) with a written rationale — this is the correct flet 1.x pattern.
- `use_dialog` for a single portal-managed overlay (`app_shell.py:709-719`) that survives progress re-renders.
- `ft.ValueKey` on list roots to preserve identity across re-renders (`sites_screen.py:727,730`).
- The export sheet's mode-aware tile set and the "PDF dossiers are username-mode" guidance (`app_shell.py:508-526`).

---

## Verdict

**ISSUES FOUND** — 9 issues (0 hallucinations).

| Severity | Count | IDs |
|---|---|---|
| **High** | 2 | BUG-1 (`Clipboard.set_text` does not exist → "Copy report" silently fails), BUG-2 (`scroll_to` documented ineffective on the dynamically-built sites list → "jump to top" is dead) |
| **Medium** | 4 | BUG-3 (`page.update_async` does not exist → dead code), BUG-4 (tab taps bind the change-event, not `TabBar.on_click`), BUG-5 (`on_platform_brightness_change` never wired → SYSTEM mode does not follow the OS), BUG-6 (`page.on_resize` never wired → no responsive reflow) |
| **Low** | 3 | BUG-7 (a load-bearing comment is factually wrong for 1.0.4 and shaped the layout), BUG-8 (`page.services.append` semantics mis-documented), DOC-DRIFT (five comments cite flet 0.86.5 / 1.0.1 internals) |

**API-surface verdict: PERFECT.** All 109 `ft.*` symbols used by `src/` exist in the installed flet 1.0.4; 0 invalid constructor kwargs across 68 control classes; 0 missing enum members; 0 fabricated APIs. The app is genuinely written against the 1.x component model (`ft.component` + hooks + `ft.observable`) and the reactive/observable patterns it uses (`use_memo` on the branch, `use_dialog` for the overlay, a 2 Hz render flusher) are the *right* answers for this framework.

**Owner-goal verdict: NOT YET.** To match and exceed the wrapped engines, the app must (a) fix the two High bugs, (b) close the two Medium theming/responsiveness gaps, and (c) adopt the P0/P1 list — chiefly `DataTable` + `AutoComplete` for the 2,521/220-module surfaces, `AnimatedSwitcher` + `Tabs.move_to` + `ProgressRing` for motion, `Semantics` for a11y, and `Hero` + `ShaderMask` + `Shimmer` for the premium-consumer feel. The single highest-leverage structural change is **BUG-7's layout fix** (header out of the `ListView`), which simultaneously restores `scroll_to`, unlocks `item_extent` virtualization for 5,178 rows, and makes the filter controls permanently reachable.
