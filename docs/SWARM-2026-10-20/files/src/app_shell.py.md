# Audit — `src/app_shell.py`

**File:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/app_shell.py` (941 lines)
**Audited:** 2026-10-20 · read-only
**Truth source:** installed `flet 1.0.4` (`.venv\Lib\site-packages\flet`), installed `reportlab`/`jinja2` **absent**

---

## 1) File role

`AppShell` is the single top-level component of the app and the only place that decides *what is on screen*.

Responsibilities, in file order:

| Lines | Role |
|---|---|
| `app_shell.py:22-27` | Module constants: tab names/icons (`Home`, `History`, `Settings`). |
| `app_shell.py:30-32` | `_should_show_onboarding(state)` — branch predicate (`is_first_launch or not has_accepted_terms`). |
| `app_shell.py:35-55` | `_safe_filename()` — slugify + Windows reserved-name guard for the save-dialog filename. |
| `app_shell.py:58-135` | `_email_export_bytes()` — CSV/JSON/TXT/MD/HTML serialization of email/phone (holehe-v2 dict) rows. |
| `app_shell.py:138-701` | `_build_appbar()` — per-view `ft.AppBar` factory, and the home of **all** export / copy / share / retry logic. |
| `app_shell.py:704-941` | `AppShell()` — the `@ft.component`: branch state, controller-closure injection, chrome sync effect, screen memoization, live scan banner. |

The shell is a **single-view** app: `main.py:588` calls `page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))`, so `page.views[0].controls` is the component tree. There is **no router** and **no `page.route` usage** anywhere in the repo — navigation is 100 % in-memory `use_state` (`app_shell.py:707-708`).

Key architectural pattern (verified correct against flet 1.0.4):
`use_state` for `active_tab`/`active_view`/`active_dialog` → per-render closure injection into the shared `ControllerMethods` dataclass (`app_shell.py:725-754`) → `use_effect` chrome sync into `page.views[0].appbar` / `.navigation_bar` (`app_shell.py:758-849`) → `use_memo` screen construction keyed on `[branch, active_tab]` (`app_shell.py:909-932`).

---

## 2) API verification summary

Everything below was checked against the **installed** `flet 1.0.4` source, not training data. **No hallucinated or deprecated flet APIs were found in this file.**

### Verified present and correct

| Usage (app_shell.py) | flet 1.0.4 source | Verdict |
|---|---|---|
| `ft.use_state` `:707,708,712` | `components/hooks/use_state.py:48` | OK |
| `ft.use_effect` `:835` | `components/hooks/use_effect.py:42` | OK — deps compared element-wise by `==` (`components/component.py:336-341`) |
| `ft.use_memo` `:909` | `components/hooks/use_memo.py:25` | OK — `shallow_compare_args` |
| `ft.use_context` `:721,722` | `components/hooks/use_context.py:84` | OK — **auto-subscribes** to `Observable` values |
| `ft.use_dialog` `:717` | `components/hooks/use_dialog.py:52` | OK — `context.page` raises `RuntimeError` outside a live app (`controls/context.py:63-70`); `use_ref` is called *before* the raise, so hook ordering stays stable in the harness |
| `ft.component` `:704` | `components/component_decorator.py` | OK |
| `ft.BottomSheet(content=…, scrollable=…, show_drag_handle=…)` `:567-579` | `controls/material/bottom_sheet.py` (subclass of `DialogControl`) | OK — all 3 fields exist |
| `ft.Badge(label/bgcolor/text_color/small_size/large_size)` `:802-808` | `controls/material/badge.py:28,63,75,97,105` | OK |
| `ft.NavigationBarDestination(icon,label,badge=…)` `:799-812` | `badge` inherited from `AdaptiveControl` (not declared locally — my first grep missed it) | OK — constructed successfully in a live check |
| `ft.SafeArea(content=…, expand=True)` `:941` | `controls/core/safe_area.py:29` | OK |
| `ft.Padding(0,0,0,n)` `:572,574` | `controls/padding.py:13` (left,top,right,bottom) | OK |
| `ft.ListTile(title,subtitle,leading=ft.Icon)` `:491-505` | `controls/material/list_tile.py:112,120,147` | OK |
| `ft.AppBar(leading,title,center_title,bgcolor,actions)` `:668-682` | OK | OK |
| `ft.NavigationBar(destinations,selected_index,on_change)` `:820-824` | OK | OK |
| `ft.FilePicker().save_file(src_bytes=…)` `:420-426` | `controls/services/file_picker.py:278-286` | OK — `src_bytes` exists; `Service._auto_register = True` (`controls/services/service.py:42`) means it self-registers, so the comment at `:418-419` is **accurate** for 1.0.4 |
| `ft.Colors.PRIMARY / TRANSPARENT / WHITE` `:680,804,805` | present | OK |
| `ft.FontWeight.W_600` `:494,513,676,695` | `controls/types.py:205` | OK |
| All 14 icon names `:24-26,523,531,539,547,555,563,640,645,656,663,670,687` | `controls/material/icons.json` (8825 entries) — every one present | OK |
| `await cb.set("\n".join(urls))` `:182` | `controls/services/clipboard.py:19` — `async def set(self, value: str)` | **CORRECT** (sibling flag on `main.py:305` does *not* apply here) |
| `await share_service.share_text(text)` `:231` | `controls/services/share.py:162` — async, positional `text` | OK |
| `shared_haptics().medium_impact()/light_impact()` `:149,200` | `controls/services/haptic_feedback.py:19,25` | OK |
| `page.views[0].appbar` / `.navigation_bar` `:766,772,781,789,820` | `controls/core/view.py:58,80` | OK |
| `zip(_TAB_ICONS, _TAB_NAMES, strict=True)` `:812` | Python 3.14 (`pyproject.toml` requires-python `>=3.14`) | OK |

### Sherlock-side APIs verified

`core.shared_services.shared_clipboard/shared_share/shared_haptics` (all present, `:82-97`) · `core.tasks.spawn` (`core/tasks.py:18`) · `core.notify.show_snack` (`core/notify.py:18`) · `core.tokens.SPACE_XS/SPACE_MD/FONT_LG` · `core.theme.AppColors.PRIMARY/SUCCESS/WARNING/ERROR` · `core.constants.SITES_TOTAL_FALLBACK/MODE_USERNAME/MODE_EMAIL/MODE_PHONE` · `core.state.state` (all fields read by this file exist: `is_first_launch`, `has_accepted_terms`, `theme_mode`, `history_unseen`, `is_searching`, `current_username`, `search_progress`, `search_mode`, `email_results*`, `phone_results*`, `last_results_username`, `enrichments`, `progress_version`) · `services.report_service.{generate_csv_report,generate_txt_report,generate_markdown_report,generate_html_report,generate_pdf_dossier,generate_email_markdown_report,generate_email_html_report}` (all exist) · `services.cache_service.{load_cached_report,save_cached_report}` · `services.sherlock_service.SearchProgress/SiteResult` (every field the JSON export reads exists: `username,total_sites,checked_sites,found,not_found,errors` + `site_name,url_main,url_user,status,http_status,query_time,context,tags`).

Screen constructors match exactly: `OnboardingScreen()` `ResultsScreen()` `SitesScreen()` `HomeScreen(banner=None)` `HistoryScreen(banner=None)` `SettingsScreen(banner=None)` · `ActiveScanBanner(target_query, search_mode, checked, total, on_tap, finishing)`.

**Ruff:** `ruff check src/app_shell.py` → *All checks passed*. `ruff format --diff` → **the file is not formatted per the project's own formatter** (8 hunks, mostly the long lines at `:252`, `:254`, `:170`, `:172`).

---

## 3) Confirmed known issues (sibling audit claims)

### 3.1 Export tiles reference dead paths — **CONFIRMED (worse than stated)**

`reportlab` and `jinja2` are **not installed** and **not declared in `pyproject.toml`** (dependencies are only `flet`, `flet-ads`, `user-scanner`, `phonsint`).

* `generate_pdf_dossier` → `services/report_service.py:605` `if not _REPORTLAB_AVAILABLE or not found: return None` → `app_shell.py:307-310` raises `RuntimeError("PDF generation returned empty output")`.
* `generate_html_report` → `services/report_service.py:338-341` returns `None` when jinja2 is missing → `app_shell.py:397-400` raises `RuntimeError("HTML generation returned empty output")`.
* `generate_email_html_report` → `services/report_service.py:498-501` returns `None` → `_email_export_bytes` (`app_shell.py:84`) returns `None` → `app_shell.py:284-288` raises the **wrong** `ValueError`.
* Working: `generate_markdown_report` (pure stdlib), `generate_csv_report`, `generate_txt_report`.

**Net effect:** the "PDF Intelligence Dossier (.pdf)" tile (`:520-526`) and the "HTML Dossier (.html)" tile (`:551-558`) are **guaranteed failures in the shipped build** — 2 of 5 tiles in username mode, 1 of 5 in email mode. The user only ever sees `Failed to save: PDF generation returned empty output`.

### 3.2 Does app_shell build ad banners directly (bypassing the pool)? — **NO**

`grep -n "ad|banner|Banner" src/app_shell.py` shows **no banner construction at all**. app_shell only calls `ad_service.show_interstitial()` at `:452-459`. The pool bypass the flet-ads audit found lives in **`settings_screen.py:1760, 1771, 1776`** (`build_banner_ad()` directly) vs `home_screen.py:1375, 1408` (`pooled_banner_ad("home-N")`). app_shell passes `banner=None` to every screen (`:920, 923, 925`), so it neither builds nor pools banners.

The comment at `:450-451` ("The service's own interval guard prevents stacking") is **accurate** — `services/ad_service.py:232-241` implements `INTERSTITIAL_MIN_INTERVAL_SEC`.

Caveat (see NEW-18): app_shell reaches the ad service via `from main import _AD_SERVICE_REF` (`:453`) — a module-global dict (`main.py:104`, set at `main.py:513`). This is a layering violation (shell → app entrypoint), not a pool bypass.

### 3.3 use_state / closure injection / screen memo / system back — **CONFIRMED as described**

`app_shell.py:707-708` state, `:725-730` + `:743` + `:753-754` injection, `:732-743` system-back, `:909-932` memo. One correction to the sibling note: the memo is keyed `[branch, active_tab]`, and `branch` already encodes `active_view`, so `active_view` is intentionally absent.

### 3.4 `app_shell.py:182` clipboard — **CORRECT** (verified above)

Uses `await cb.set(...)` on `ft.Clipboard` via `shared_clipboard(page)`. Not the `main.py:305` defect.

---

## 4) NEW bugs / hallucinations (severity-ordered)

> No flet API hallucinations. Everything below is logic, wiring, or wiring-gap.

### NEW-1 · HIGH — The History badge is built once and never updated again

`app_shell.py:789-791`

```python
current_nav = page.views[0].navigation_bar
if isinstance(current_nav, ft.NavigationBar):
    current_nav.selected_index = active_tab
else:
    ...  # destinations with the Badge are built ONLY here  (:798-813)
    page.views[0].navigation_bar = ft.NavigationBar(...)   # :820
```

The badge exists **only** in the `else` branch. After the first build, `page.views[0].navigation_bar` *is* a `ft.NavigationBar`, so every subsequent `_sync_chrome` run takes the `isinstance` branch and updates **only** `selected_index`.

Consequence: `state.history_unseen` is declared as a dependency at `:847`, and the comment at `:843-846` explicitly claims that "Without it as a dep the effect never re-ran on a completed scan, so the badge appeared only after an unrelated change". **That reasoning is wrong** — the dep *does* re-run the effect, but the effect's `isinstance` branch never touches the badge. The unseen-history count is frozen at whatever it was the first time the nav bar was created (typically 0) for the whole app session.

### NEW-2 · HIGH — Export failures are mis-attributed (three different causes, one message)

`app_shell.py:283-288`

```python
report_bytes = _email_export_bytes(format_type, app_state)
if report_bytes is None:
    raise ValueError("PDF dossiers are username-mode — email results export as CSV, JSON, TXT, Markdown, or HTML")
```

`_email_export_bytes` returns `None` for **three unrelated reasons**:
1. `format_type == "pdf"` (`:64-65`) — legitimately username-mode.
2. `format_type == "html"` → `generate_email_html_report` returns `None` because **jinja2 is missing** (`report_service.py:498-501`).
3. `format_type == "md"` → `generate_email_markdown_report` returns `None` when **rows are empty** (`report_service.py:411-412`).

All three produce the same message telling the user PDF/username-mode is the problem. In the shipped build (no jinja2) **every email HTML export blames PDF**. Likewise the username path reports `"PDF generation returned empty output"` / `"HTML generation returned empty output"` instead of naming the missing optional dependency.

### NEW-3 · MEDIUM-HIGH — The export sheet has no `on_dismiss`; native dismissal is invisible to the shell

`app_shell.py:567-579` builds the `ft.BottomSheet` with `scrollable=True, show_drag_handle=True` and **never sets `on_dismiss`** — even though `ft.BottomSheet` inherits `on_dismiss` from `DialogControl` (`flet/controls/dialog_control.py:19`).

flet's own `use_dialog` source explicitly handles a *"mid-dismiss, awaiting the client's on_dismiss round-trip"* state (the `else` branch of the append path in `flet/components/hooks/use_dialog.py`, comment: *"the dismissing one finish on its own"*). That state is **only reachable if the app wires `on_dismiss`** — flet cannot infer it.

Consequence: when the user swipes/taps the sheet away, `active_dialog` still holds the sheet, `use_state` still believes it is open, and the next render's `use_dialog` call takes the *frozen-diff* path (`: prev.open and type(prev) is type(dialog)`) against a dialog the client already dismissed — a desync between Python state and the client overlay that can leave the sheet unable to re-open.

### NEW-4 · MEDIUM — The live-banner `ft.Column` wrapper re-mounts the whole screen at every scan start/finish

`app_shell.py:934-939`

```python
if live_banner is not None and branch not in ("onboarding", "results", "sites"):
    screen = ft.Column(controls=[live_banner, screen], spacing=0, expand=True)
```

`screen` is memoized (identity-stable, `:909-932`), but the moment `live_banner` flips `None → banner` (scan starts) or `banner → None` (scan ends) the **tree shape changes** from `screen` to `Column([banner, screen])`. The renderer then unmounts and re-mounts the screen: scroll position lost, mount effects re-run, and the ~1400-line Home screen (with its pooled banner ads) rebuilt — on the exact transitions the user is most likely to be looking at.

The screens **already accept a `banner=` parameter for precisely this** (`home_screen.py:360,990`; `history_screen.py:95`; `settings_screen.py:290,1795`), but app_shell always passes `banner=None` (`:920, 923, 925`) — that parameter is **dead code** in the current design.

### NEW-5 · MEDIUM — `controller.back` and `controller.go_home` are identical, and the in-app Back button does not reset the tab

`app_shell.py:727-728`

```python
controller.go_home = lambda: set_active_view("dashboard")
controller.back   = lambda: set_active_view("dashboard")
```

The Results appbar's Back arrow calls `controller.go_home()` (`:672`); the Sites appbar's calls `controller.back()` (`:689`). Neither resets `active_tab`, so backing out of Results while the Settings tab was last active lands the user on **Settings**, not Home. `_system_back` (`:738-741`) *does* force `set_active_tab(0)` — the two back paths are semantically inconsistent, and one of the two controller methods is a redundant alias.

### NEW-6 · MEDIUM — Every exception in the chrome sync is swallowed

`app_shell.py:767-768, 774-775, 783-784, 827-828` — four bare `except Exception: pass` blocks, and **no `logger.exception` anywhere in `_sync_chrome`**.

If `_build_appbar` raises (bad icon, `token` typo, a `KeyError` from `core.constants`), the appbar silently keeps the *previous* view's chrome: the user can be left in the Results view wearing the Sites appbar, or with no Back button and no Export action. The `logger` created at `:20` is not used in this function at all.

### NEW-7 · MEDIUM-LOW — The report cache can never hit; the scan-signature mechanism is inert

app_shell calls `load_cached_report(fmt, username, found, fmt, _sig)` (`:292-294`, `:374-377`) and `save_cached_report(fmt, username, found, fmt, bytes, _sig)` (`:312-315`, `:401-408`).

But in `services/cache_service.py`:
* `load_cached_report` → `cached_report_path(mode, query, found, ext, sig)` (`:403`) — **sig included**
* `save_cached_report` → `cached_report_path(mode, query, found, ext)` (`:418`) — **sig dropped**

and `cached_report_path` folds `sig` into the filename fingerprint (`:391` `results_fingerprint(found, sig)`). The write path and the read path therefore resolve to **different files** → 100 % cache miss → every PDF/Markdown export regenerates. The entire scan-signature block (`:266-280`, the careful "mid-scan export must not be served as the completed one" logic) is dead weight.

### NEW-8 · LOW-MEDIUM — `_share_urls` is not defensive where `_copy_urls` is

`app_shell.py:214-216` → `urls = [r.url_user for r in app_state.search_progress.found if r.url_user]` — pure attribute access.
`app_shell.py:165-174` → handles dataclass rows, **dict rows**, and `others.extra.url`.

The two handlers sit 30 lines apart in the same closure and disagree about the row type. In any mode where `found` holds dicts (the holehe-v2 email shape), `_share_urls` raises `AttributeError` inside the spawned task, swallowed by `core/tasks.spawn`'s logger (`core/tasks.py:21-28`) — the user sees *nothing*. `_copy_urls` shows an error snackbar (`:188-192`); `_share_urls` only logs (`:232-233`).

### NEW-9 · LOW-MEDIUM — The History tab always shows a badge dot, even at zero

`app_shell.py:802-808` attaches a `ft.Badge` to the History destination unconditionally, with `label=str(unseen) if unseen else None`.

flet's own docstring (`flet/controls/material/badge.py:34-36`): *"If the label is not provided, the badge is shown as a filled circle of `small_size` diameter."* → a permanent 10 px gold dot on the History tab. Should be `badge=None` when `unseen == 0`.

### NEW-10 · LOW — The `progress_version` touch is redundant and its comment is stale

`app_shell.py:905-906`

```python
# Touch progress_version so this component subscribes to scan ticks.
_ = state.progress_version
```

`use_context` already subscribes to the **whole** observable — `flet/components/hooks/use_context.py`: `if isinstance(value, Observable): component._attach_observable_subscription(value)`. The shell already re-renders on every field write; the line adds nothing. (The sibling's `:875-877` claim about `Observable.__on_change` firing on any field is **correct** — and that same fact is what makes this line redundant.)

### NEW-11 · LOW — `_should_show_onboarding` is "exported for tests" but has no test

`app_shell.py:31` — `"""Mirror of the branch in AppShell — exported for tests."""`. `grep -rn "_should_show_onboarding"` over the repo (excluding `.venv`) returns **only the three uses inside app_shell.py itself** (`:736, 771, 862`). There is no `tests/test_app_shell.py` at all.

### NEW-12 · LOW — `_build_appbar` is annotated `-> ft.AppBar` but returns `None`

`app_shell.py:138` vs `:701` (`return None` for the dashboard branch). `page.views[0].appbar = None` is legal flet, so this is a type-lie, not a crash — but ruff's `ANN` rules are not enabled (`pyproject.toml` `select = [...]` omits `ANN`), so nothing catches it.

### NEW-13 · LOW — The exported file is written twice

`app_shell.py:420-441`: `file_picker.save_file(src_bytes=report_bytes)` already writes the bytes on desktop — flet's own docstring (`flet/controls/services/file_picker.py:291-295`): *"On desktop … If `src_bytes` is provided, those bytes are written to the selected file."* The subsequent `open(path,"wb")` + `asyncio.to_thread(_write_file)` re-writes the same bytes to the same path. Redundant I/O plus a second failure point (e.g. a file the picker just created with different permissions/locking semantics).

### NEW-14 · LOW — `controller.close_dialog()` is invoked twice per export

`:501-504` (the tile's `on_click` lambda calls `controller.close_dialog()`) and again at `:248` inside `_do_export`. Harmless but it forces an extra state transition + re-render per export.

### NEW-15 · LOW — "Email formats" wording is wrong in phone mode

The mode test at `:252`, `:479-483` and `:630-634` includes `MODE_PHONE`, so a **phone** scan shows the sheet header `"Email formats: CSV, JSON, Markdown, HTML, TXT"` (`:512`) and the subtitle `"PDF dossiers are username-mode only"` (`:515`) — and the PDF tile is hidden — all of which is wrong for phone results.

### NEW-16 · LOW — Export mode is derived from the UI mode, not from the results being displayed

`app_shell.py:252` — `is_email` includes `app_state.search_mode in (MODE_EMAIL, MODE_PHONE)`. `search_mode` is the **currently selected UI mode**, not a property of the progress object on screen. If the user changes the mode selector after a scan, a **username** scan's results get exported through `_email_export_bytes` (`:283`) → which reads `app_state.email_results` (empty) → an empty report — while the PDF tile silently disappears. The mode should be derived from the progress object itself (`progress.username` vs `progress.email`/`progress.phone`).

### NEW-17 · LOW — The `username` expression at `:253-258` is a precedence-dependent trap

```python
username = (
    (app_state.phone_results_address if app_state.search_mode == MODE_PHONE else app_state.email_results_address)
    or "unknown"
    if is_email
    else (app_state.last_results_username or "unknown")
)
```

It currently parses as `(A or "unknown") if is_email else (B or "unknown")` — correct, but the `or`/ternary precedence is invisible to the reader and one edit from silently exporting the wrong target. `ruff format --diff` already wants to reformat this block.

### NEW-18 · LOW — The shell imports the app entrypoint to reach the ad service

`app_shell.py:453` — `from main import _AD_SERVICE_REF`. The shell reaches into the application entry module for a module-global dict, bypassing the `ControllerMethods` indirection used for everything else (`controller.open_update_dialog`, `controller.show_results`, …). Both imports are lazy so there is no import cycle, but it inverts the layering.

### NEW-19 · INFO — No deep-link / route support; view state is volatile

`page.render()` (single view) + `use_state`-only view state (`:707-708`) with **no** `page.route` write, no `ft.Router`, no route persistence. Consequences: a process restart always returns to Dashboard/tab 0; no URL can be shared or deep-linked; the OS back button is the only external navigation affordance. The sibling's "deep-link absence" note is confirmed and it is a *design* gap, not a bug.

### NEW-20 · INFO — `state.theme_mode` as an effect dep forces a full chrome rebuild for nothing

`:842` puts `theme_mode` in the `use_effect` deps, but `_build_appbar` never reads the theme — every theme switch rebuilds the appbar and the navigation bar from scratch for no benefit.

---

## 5) Improvements (concrete, ordered)

1. **Fix the History badge (NEW-1).** In the `isinstance(current_nav, ft.NavigationBar)` branch (`:789-791`), also refresh the badge: either rebuild the `NavigationBar` when `state.history_unseen` changed, or hoist the badge into a memoized child that owns its own `use_state` subscription. Cheapest correct version: keep a `last_unseen` ref and rebuild the destinations list when it differs.
2. **Make the export sheet capability-aware (NEW-1/3.1).** Export the availability flags from `services/report_service` (e.g. `REPORTLAB_AVAILABLE`, `JINJA_AVAILABLE`) and **hide or disable** the PDF and HTML tiles when the generator is unavailable, instead of shipping guaranteed failures.
3. **Give every export failure a distinct, actionable message (NEW-2).** "jinja2 not installed", "reportlab not installed", "PDF is username-mode only", "no results to render" must be four different strings, not one.
4. **Wire `on_dismiss` on the sheet (NEW-3).** `ft.BottomSheet(content=…, on_dismiss=lambda e: controller.close_dialog())` so `use_dialog`'s dismiss round-trip works and `active_dialog` cannot go stale.
5. **Use the screens' `banner=` parameter instead of the `ft.Column` wrapper (NEW-4).** Pass `live_banner` into `HomeScreen(banner=…)` / `HistoryScreen(banner=…)` / `SettingsScreen(banner=…)` and drop `:934-939`; this removes the re-mount and revives the currently-dead `banner` parameter.
6. **Derive the export mode from the progress object, not `search_mode` (NEW-16).** `is_email = getattr(progress, "email", None) is not None or getattr(progress, "phone", None) is not None`, with `search_mode` only as a fallback.
7. **Make the two back paths agree (NEW-5).** Give `controller.back` and `controller.go_home` distinct semantics (e.g. remember the tab the user left from and restore it) and make the in-app Back arrow reset/return consistently with `_system_back`.
8. **Stop swallowing chrome-sync errors (NEW-6).** Replace the four `except Exception: pass` with `logger.exception("...")` — the `logger` at `:20` already exists.
9. **Fix the cache round-trip (NEW-7).** Either pass `sig` through in `save_cached_report` (`services/cache_service.py:418`) or drop the cache branches from app_shell; today the cache can never hit and the `_sig` logic at `:266-280` is inert.
10. **Factor out row-URL extraction (NEW-8).** One helper `_row_url(r) -> str | None` used by both `_copy_urls` (`:165-174`) and `_share_urls` (`:214-216`); add an error snackbar to the share failure path.
11. **Suppress the empty badge (NEW-9).** `badge=ft.Badge(...) if unseen else None` on the History destination.
12. **Drop the redundant `progress_version` touch and fix the stale comment (NEW-10).** Also refresh the `.venv/flet/components/observable.py:82-92` line-range citation at `:877` (the real `__on_change` is at `:86-97`).
13. **Drop the redundant second write (NEW-13) and the double `close_dialog` (NEW-14).**
14. **Split `_build_appbar` (`:138-701`, 545 lines) into per-view builders** (`_results_appbar`, `_sites_appbar`) and move the export machinery into a separate module — the current shape means one bad statement in any of them silently kills the entire appbar (see NEW-6).
15. **Route the ad interstitial through `ControllerMethods` (NEW-18)** — e.g. `controller.on_export_complete()` — instead of `from main import _AD_SERVICE_REF`.
16. **Add `tests/test_app_shell.py`** covering `_safe_filename` (Windows reserved names, 64-char cap), `_email_export_bytes` (per-format, `None` paths), and the branch table (`:862-871`).
17. **Run `ruff format` on the file** — it currently deviates from the project's own formatter config (8 hunks, including the `:252`/`:254` lines this report cites).

---

## 6) Verdict

**No flet API hallucinations.** Every control, hook, property, icon name, colour and service call in `src/app_shell.py` was verified against the installed `flet 1.0.4` source and constructs successfully; the `Clipboard.set` usage at `:182` is correct (contrary to `main.py:305`); the `FilePicker` self-registration comment at `:418-419` is accurate; and app_shell does **not** build ad banners, so it does **not** bypass the banner pool (that defect is in `settings_screen.py`).

The problems in this file are **logic and wiring**, not API:

* **2 export tiles are guaranteed dead in the shipped build** (PDF + HTML — `reportlab`/`jinja2` are neither installed nor declared in `pyproject.toml`), and every failure is reported with a message that names the wrong cause (NEW-1/3.1, NEW-2).
* **The History unseen-count badge never updates** after the navigation bar's first construction, despite `state.history_unseen` being a declared effect dependency (NEW-1) — the feature documented at `:793-796` and `:843-846` does not work.
* **The export sheet never learns about native dismissal** (no `on_dismiss`), which is the exact case flet's `use_dialog` source is written to handle (NEW-3).
* **The live-scan banner re-mounts the entire screen** on every scan start/finish, while the screens' own `banner=` parameter sits unused (NEW-4).
* **The report cache can never hit** because `save_cached_report` drops the `sig` (NEW-7), rendering the carefully-reasoned signature block inert.
* Plus: duplicated back semantics (NEW-5), four fully swallowed exception handlers (NEW-6), divergent copy/share row handling (NEW-8), a permanently-visible badge dot (NEW-9), redundant progress subscription (NEW-10), a double file write (NEW-13), a mode-mismatch export path (NEW-16), and an entrypoint-layering violation (NEW-18).

**Severity call:** two HIGH (History badge dead; export failures mis-attributed + 2 guaranteed-dead tiles), four MEDIUM-HIGH/MEDIUM (missing `on_dismiss`; screen re-mount; back-path inconsistency; swallowed chrome errors), the remainder LOW/INFO. None of these are memory-safety or crash-class, but the export path and the History badge are user-visible features that are broken in the current build, and they should be fixed before the next release.
