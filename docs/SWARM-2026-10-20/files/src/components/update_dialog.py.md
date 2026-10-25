# Audit — `src/components/update_dialog.py`

Scope: single file, 246 lines. Truth source: `flet 1.0.4` as installed in
`.venv/lib/python3.14/site-packages/flet` (verified `flet.__version__ == "1.0.4"`).
Every API claim below was re-verified against the project's own installed 1.0.4 package
and imported live in Python 3.14.

---

## 1) File role

`src/components/update_dialog.py` is a dialog factory module with four public-ish entry
points:

- `_launch` (`:34-46`): schedules an async `shared_url_launcher(...).launch_url(url)` and,
  on failure, shows `ERR_OPEN_URL` snack.
- `_pop_and_launch` (`:49-57`): dismisses the top dialog, then `_launch`es (legacy fallback
  when `core.actions.open_url_action` returns `None`).
- `check_from_dialog` (`:60-79`): async live re-check invoked from the up-to-date
  dialog's "Check for Updates" button; morphs to update mode on a newer build.
- `_build_update_buttons` (`:81-137`): platform split (Android → Play Store + Direct APK;
  else GitHub only), plus "Later" unless mandatory.
- `_build_current_buttons` (`:140-152`): "Check for Updates" + "Close".
- `show_update_dialog` (`:154-247`): opens an `ft.AlertDialog` in either update mode
  (`is_update = bool(data)`) or up-to-date mode, sizing content to the page width.

Callers: `src/components/app_header.py:38-40`, `src/screens/settings_screen.py:1379-1381`,
`src/main.py:2294` (via `open_update_dialog`), and `main.py:2306` (mandatory auto-open).

---

## 2) API verification (flet 1.0.4, project venv)

| Line | API used | 1.0.4 verification |
|---|---|---|
| `:19` | `import flet as ft` | OK. |
| `:34` | `page.run_task(_run)` | OK — `BasePage.run_task(target, *args)`. |
| `:54` | `page.pop_dialog()` | OK — returns top open dialog or `None`. |
| `:85` | `page.platform == ft.PagePlatform.ANDROID` | OK — `PagePlatform.ANDROID` exists. Note `page.platform` may be `None` early; comparison is then `False` (no crash). |
| `:87` | `from core.actions import open_url_action` | OK — returns `ft.OpenUrl \| None`. |
| `:90,103,117` | `ft.FilledButton` / `ft.OutlinedButton` with `action=`, `on_click=` | OK — both are `ActionControl` subclasses with `action` and `on_click`. |
| `:95,109,123` | `action=play_action` (client-side `ft.OpenUrl`) | OK. |
| `:132` | `ft.TextButton(content=..., on_click=...)` | OK. |
| `:145` | `page.run_task(check_from_dialog, page)` | OK. |
| `:181,205` | `ft.Markdown(value, selectable=True, extension_set=..., on_tap_link=...)` | OK — first positional is `value: str`; `on_tap_link` is `ControlEventHandler`. `extension_set=ft.MarkdownExtensionSet.GITHUB_WEB` exists. |
| `:185,209` | `on_tap_link=lambda e: _launch(page, e.data)` | OK — `e.data` is the tapped link URL string. |
| `:191,215` | `scroll=ft.ScrollMode.AUTO` on `ft.Column` | OK. |
| `:227-228` | `except TypeError, ValueError:` | **BUG** — see §4 (Severity 1). In Python 3.14 this parses as `except TypeError as ValueError:` (PEP 758 alias form), catching only `TypeError` and shadowing the builtin `ValueError`. |
| `:232-246` | `ft.AlertDialog(modal=, title=, content=, actions=, actions_alignment=)` | OK — `AlertDialog` is a `DialogControl`. |
| `:234` | `ft.Row(controls=[ft.Icon(...), ft.Text(...)], spacing=8)` | OK. |
| `:241` | `content=ft.Container(content=body, width=content_width)` | OK. |
| `:243` | `actions_alignment=ft.MainAxisAlignment.END` | OK. |
| `:246` | `page.show_dialog(dlg)` | OK — raises `RuntimeError` if `dlg` already open. |
| `:21` | `from core.changelog import notes_for` | OK — function exists. |
| `:22-27` | imported constants | OK — all exist. |

Flet API surface is otherwise valid; no hallucinated control names or fields.

---

## 3) State / branch correctness

Branch structure in `show_update_dialog` (`:154-220`):

```
data = update_data if update_data is not None else state.update_data   # :157
is_update = bool(data)                                               # :158
if is_update:                                                         # :160
    title/icon from data (announcement vs update)                     # :161-173
    body = Column([ "Version X is now available.", "What's New:",
                   Container(Markdown(data.release_notes)) ])          # :174-193
    actions = _build_update_buttons(page, data)                      # :194
    modal = bool(data.get("mandatory"))                               # :195
else:                                                                 # :196
    title = "You're up to date"                                       # :197
    body = Column([ "✓ Latest version · v{APP_VERSION}", "What's New:",
                   Container(Markdown(notes_for(APP_VERSION))) ])       # :200-217
    actions = _build_current_buttons(page)                            # :218
    modal = False                                                     # :219
```

Key correctness observations:

- **No distinction between "up to date" and "check failed".** `UpdateService.check_for_update()`
  returns `None` both when the server reports no newer build and when the request fails/offline
  (`src/services/update_service.py:67-119`). `show_update_dialog` treats any falsy `data` as
  "up to date" (`:158`), and `check_from_dialog` (`:70`) shows
  `f"Sherlock v{APP_VERSION} is up to date!"` for *any* falsy result (`:75-78`). An offline user
  is therefore told they are up to date. This matches the known context; the dialog has no
  failed-check state.
- **No live check on manual open.** Opening via the version chip/settings calls
  `show_update_dialog(page)` with no data, so it never re-queries the server; it shows whatever
  `state.update_data` happens to be (or up-to-date). Staleness is possible.
- **`is_update = bool(data)`** means an empty dict `{}` is treated as up-to-date even if
  `state.update_available` is `True` but data was cleared. Minor.
- **Mandatory handling:** `modal = bool(data.get("mandatory"))` (`:195`) and "Later" is omitted
  when mandatory (`:130`). However the update buttons' `on_click` still calls `page.pop_dialog()`
  (`:97,110,124`), so a mandatory update can be dismissed by clicking a download button before
  anything is installed. Acceptable given browser-based delivery, but worth noting.
- **Dead-URL impact:** `_build_update_buttons` uses `GITHUB_RELEASES_URL` (constants.py:29,
  `https://github.com/Nwokike/Sherlock-V2/releases/latest`) only as the fallback default when
  `data.get("github_url")` is missing (`:86`). The live `version.json` supplies the correct
  `https://github.com/Nwokike/Sherlock/releases/latest`, so the update-mode GitHub button is
  correct in practice. `PLAY_STORE_URL` (`:28`) is used directly for Android's Play Store button
  (`:90`) and is correct. The up-to-date branch uses no URLs at all. So the dead constants
  affect this dialog only in the degraded case (missing `github_url`), but the fallback then
  points users at a 404.
- **`notes_for(APP_VERSION)`** (`:206`): with `APP_VERSION = "2.3.0"` (constants.py:17) the
  changelog has a matching key, so bundled notes render correctly today. But `notes_for`
  (`core/changelog.py:37-39`) falls back to `next(iter(CHANGELOG.values()))` (the newest entry,
  "2.3.0" bullets) for *any* miss, so after a V3 bump to e.g. `3.0.0` without a new
  `CHANGELOG` key the up-to-date dialog would headline "✓ Latest version · v3.0.0" over 2.3.0
  bullets — stale/misleading content. (Confirmed against `core/changelog.py:37-39`.)

---

## 4) Bugs (severity-ordered)

### Severity 1 (High): `except TypeError, ValueError:` is the wrong exception set
**Location:** `src/components/update_dialog.py:227-229`.

```python
try:
    page_width = int(getattr(page, "width", 0) or 0)
except TypeError, ValueError:
    page_width = 0
```

Under Python 3.14 this is parsed as `except TypeError as ValueError:` (PEP 758 alias form): it
catches only `TypeError` and shadows the builtin `ValueError` inside the block. The intent
was to catch both conversion failures. Concretely, if `page.width` is a non-numeric string,
`int(...)` raises `ValueError` which now propagates out of `show_update_dialog`, aborting the
dialog open. Fix: `except (TypeError, ValueError):`.

### Severity 2 (High): No guard against an already-open dialog → crash on repeated open
**Location:** `src/components/update_dialog.py:246` (`page.show_dialog(dlg)`); callers
`src/components/app_header.py:36-40`, `src/screens/settings_screen.py:1379-1381`,
`src/main.py:2291-2295`.

`page.show_dialog` raises `RuntimeError("Dialog is already opened")` if the same dialog instance
is open; more importantly, repeated taps on the version chip / settings row while the dialog is
already displayed call `show_update_dialog` again, creating a *second* `AlertDialog` and pushing
it onto the dialog stack (`page.show_dialog` appends). There is no `try/except` or open-dialog
check. Fix: wrap `page.show_dialog(dlg)` in `try/except RuntimeError`, or check the current
top dialog before opening.

### Severity 3 (Medium): Offline/failed update check is reported as "up to date"
**Location:** `src/components/update_dialog.py:60-79` and `:196-219`.

`check_from_dialog` (`:69`) awaits `UpdateService().check_for_update()`; any falsy result
(`None` from network failure, non-200, parse error, or genuinely up-to-date) falls into the
`else` branch (`:75-78`) and shows `f"Sherlock v{APP_VERSION} is up to date!"`. The
up-to-date branch (`:196-219`) has no failed state either. Fix: distinguish by checking
connectivity/result; show an error/offline snack instead of "up to date" when the check failed.

### Severity 4 (Medium): Inner `ft.Container(width=360)` can overflow narrow viewports
**Location:** `src/components/update_dialog.py:187` and `:211`.

The outer content width is clamped to `[300, 380]` based on `page.width` (`:230`), but both
Markdown containers are hard-coded `width=360` (`:187`, `:211`). On a phone narrower than
~408px the inner 360px container exceeds `content_width`, causing horizontal overflow / clipped
text. Fix: set inner width to `content_width` (or remove the fixed width and let the Markdown
fill).

### Severity 5 (Low): Stale bundled changelog after a version bump without a new key
**Location:** `src/components/update_dialog.py:206`; root cause `src/core/changelog.py:37-39`.

`notes_for(APP_VERSION)` (`:206`) renders whatever `notes_for` returns, and `notes_for` falls
back to the newest entry for any miss. After bumping `APP_VERSION` without adding a matching
`CHANGELOG` key, the dialog headlines the new version over old bullets. Fix in `changelog.py`:
return `""` (or a "no notes" placeholder) on miss instead of the newest entry; or guard in this
file. (Out of scope for this file's edit, but the dialog is the consumer.)

### Severity 6 (Low): `data.get("github_url", GITHUB_RELEASES_URL)` fallback points at a 404
**Location:** `src/components/update_dialog.py:86`; constants `src/core/constants.py:26,29`.

`GITHUB_RELEASES_URL` (`constants.py:29`) is `https://github.com/Nwokike/Sherlock-V2/releases/latest`,
which 404s (real repo is `Nwokike/Sherlock` per `version.json`). It is only used when server
data lacks `github_url`, but in that degraded case the "Download from GitHub" / "Direct APK"
button launches a dead link. Same for `UPDATE_CONFIG_URL` (used by the service, not this file).
Fix: update constants to `Nwokike/Sherlock`.

### Severity 7 (Low): `check_from_dialog` pops the dialog before awaiting, leaving a blank gap
**Location:** `src/components/update_dialog.py:65-69`.

It calls `page.pop_dialog()` (`:66`) *before* `await UpdateService().check_for_update()`
(`:69`), so during the network round-trip (up to 4s) no dialog is shown and a slow check
leaves the user with nothing on screen. Fix: keep the dialog open with a spinner/disabled state,
or pop only after the result arrives.

---

## 5) Improvements (concrete)

1. **Fix the exception clause** (`:227-229`):
   ```python
   except (TypeError, ValueError):
       page_width = 0
   ```

2. **Guard `show_dialog` against double-open** (`:246`):
   ```python
   try:
       page.show_dialog(dlg)
   except RuntimeError as exc:
       logger.debug("Update dialog already open: %s", exc)
   ```

3. **Make the failed-check path explicit** in `check_from_dialog` (`:70-78`): track whether the
   service actually reached the server (e.g. catch/log and set a flag) and show an offline/error
   snack instead of "up to date" on failure.

4. **Responsive inner width** (`:187, :211`): replace `width=360` with `width=content_width` (or
   drop the fixed width) so Markdown never overflows the dialog.

5. **Dead constants** (cross-file, affects `:86`): point `GITHUB_RELEASES_URL` and
   `UPDATE_CONFIG_URL` at `Nwokike/Sherlock` so the fallback links and the check itself work.

6. **Stale changelog** (`:206`): pair with `changelog.notes_for` returning `""` on miss, and
   render a "No release notes available." placeholder when empty.

7. **Repeated-open UX** (callers): debounce or guard so the version chip/settings row does not
   stack multiple dialogs; ideally `show_update_dialog` itself checks `page._dialogs` for an
   existing instance.

---

## 6) Verdict

`src/components/update_dialog.py` uses valid Flet 1.0.4 APIs throughout (AlertDialog, Markdown,
buttons, ScrollView, show_dialog/pop_dialog). Its main defects are logic/state ones: (1) the
`except TypeError, ValueError:` clause catches only `TypeError` and shadows `ValueError`
(Severity 1); (2) no guard against an already-open dialog, so repeated taps stack/crash
(Severity 2); (3) offline and failed checks are indistinguishable from "up to date"
(Severity 3); and (4) a hard-coded 360px inner container can overflow narrow phones
(Severity 4). The dead-URL and stale-changelog issues are real but only bite in degraded
cases. Fixing items 1–4 makes the dialog robust; the rest are quality-of-life improvements.
