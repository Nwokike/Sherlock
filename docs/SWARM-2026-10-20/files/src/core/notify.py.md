# Audit — `src/core/notify.py`

**Auditor:** file-audit subagent · **Date:** 2026-10-22 · **Read-only:** no source file modified.
**Truth source:** `.venv/Lib/site-packages/flet` — **flet `1.0.4`** (`flet/version.py:16`, flutter `3.44.8`), Python **3.14.7**.

---

## 1) File role

`src/core/notify.py` (53 lines) is the project's **single notification funnel**. It exports exactly one public symbol:

```
show_snack(page, message, bgcolor=None, duration=4000, action_label=None, on_action=None) -> None
```

Design intent (per its own docstring, `src/core/notify.py:1-9`): a *best-effort* wrapper around flet's `SnackBar` that never raises — failures are logged (`src/core/notify.py:51-52`).

Every user-facing message in the app funnels through here, so this file is the correct place for cross-cutting concerns (ANSI scrubbing, truncation, contrast). It currently owns **none** of them.

**Confirmed from the flet agent's note:** the stale-version comments are real — `src/core/notify.py:1` ("the working Flet **1.0.1** way") and `src/core/notify.py:4` ("verified against the installed flet **1.0.1**") both name a version that is **not** installed. The *technical* half of that comment (no `page.open`, `SnackBar` is a `DialogControl`) is nevertheless **correct for 1.0.4** — see §2.

---

## 2) API verification (against installed flet 1.0.4)

Every symbol used by the file was checked against the installed package. **All construction is valid; there is no hallucinated API in this file.**

| Line | Usage | Installed truth | Verdict |
|---|---|---|---|
| `src/core/notify.py:13` | `import flet as ft` | flet 1.0.4 | OK |
| `src/core/notify.py:30` | `ft.SnackBarAction(action_label, on_click=on_action)` | `flet/controls/material/snack_bar.py:102` — `label: str` is the first field, `on_click` is a valid handler | OK |
| `src/core/notify.py:31` | `ft.SnackBar(...)` | `flet/controls/material/snack_bar.py:155` — real, subclasses `DialogControl` | OK |
| `src/core/notify.py:32` | `ft.Text(message, color=ft.Colors.WHITE)` | `Text.value` is the first positional field; `ft.Colors.WHITE` = `"white"` (`colors.py:469`) | OK (but see BUG‑4) |
| `src/core/notify.py:33` | `ft.Colors.BLACK` | `colors.py:204` = `"black"` | OK |
| `src/core/notify.py:35` | `ft.Duration(milliseconds=duration)` | `flet/controls/duration.py` — `DurationValue = Union[Duration, int]` (line 236) | OK (comment at `:34` is accurate) |
| `src/core/notify.py:39` | `page.show_dialog(snack)` | `flet/controls/base_page.py:402` | OK — **but semantics differ from the docstring, see BUG‑2** |
| `src/core/notify.py:41` | `page.pop_dialog()` | `flet/controls/base_page.py:427`; returns the closed `DialogControl` or `None` | OK — **but side effect is destructive, see BUG‑1** |
| `src/core/notify.py:44` | `isinstance(popped, ft.SnackBar)` | valid | OK |

**Refuted hypotheses (checked so they are not re-reported):**

- ❌ "`SnackBar` needs `open=True`" — **not required**. `DialogControl.open` defaults to `False` (`flet/controls/dialog_control.py`), but `show_dialog` sets `dialog.open = True` itself (`base_page.py:422`). The file correctly omits it.
- ❌ "`page.open(...)` / `page.close(...)`" — **do not exist** in 1.0.4 (`hasattr(ft.Page, "open")` → `False`; `base_page.py` exposes only `show_dialog` / `pop_dialog` as public dialog APIs). `src/core/notify.py:4`'s claim holds.
- ❌ "`flet 0.86.5` internals" — no 0.x-only API is used anywhere in this file.
- ⚠️ `SnackBar.duration` **already defaults to `Duration(milliseconds=4000)`** (`snack_bar.py:233`), so `src/core/notify.py:35` restates the default — harmless, and necessary when the caller overrides it.

**Version-comment defect (confirmed):** `src/core/notify.py:1` and `src/core/notify.py:4` say `1.0.1`; installed is `1.0.4`.

---

## 3) Call census

`show_snack` is imported by **7 modules**, ~40 call sites. The import style is *function-local* in every module except one:

| Call site | Notes |
|---|---|
| `src/main.py:2316-2320` | `MainPage._show_snack(message, duration=4000)` — **wrapper used by ~20 call sites** (`src/main.py:922, 1123, 1174, 1459, 1484, 1491, 1579, 1683, 1710, 1731, 1740, 2273, 2288, 2312, 2325, 2353, 2356`) |
| `src/main.py:306-308, 316-319, 2371-2373` | direct `show_snack` |
| `src/app_shell.py:157-190, 207-222, 443-464` | direct; passes `bgcolor=AppColors.WARNING / SUCCESS` |
| `src/screens/results_screen.py:349-358` | direct; `bgcolor=AppColors.ERROR` |
| `src/screens/history_screen.py:18` | **only module-level import** (`from core.notify import show_snack`) |
| `src/components/update_dialog.py:42-44, 76-78` | direct; `bgcolor=AppColors.ERROR` |
| `src/components/profile_detail_dialog.py:172-222, 504-506, 1156-1158` | direct; `bgcolor=AppColors.ERROR / SUCCESS` |

Census observations:

1. **One funnel.** Every user-visible message passes through `show_snack`. A single fix inside this file fixes all ~40 call sites — this is the decisive argument for handling ANSI and truncation *here* rather than at the call sites.
2. **`duration` is overridden widely** (`8000`, `10000` ms) but **never `action_label`/`on_action`** — the entire `action` code path (`src/core/notify.py:29-30, 36`) is **currently dead in production**. `grep` across `src/` shows no caller ever passes `action_label=`.
3. `src/main.py:1123` and `src/main.py:1579` push **raw hudson subprocess output** into the message (`hudson_out[:120]`) — the ANSI-leak path (§4 BUG‑6).
4. Callers truncate ad hoc at the call site (`hudson_out[:120] + "..."`) rather than letting the helper do it.

---

## 4) NEW bugs

### BUG‑1 (HIGH) — The "never dismiss a real dialog" guard is checked *after* the pop, so it dismisses the dialog anyway
`src/core/notify.py:38-50`

```python
try:
    page.show_dialog(snack)
except RuntimeError:
    popped = page.pop_dialog()          # <-- ALREADY closed the top dialog
    if popped is None or isinstance(popped, ft.SnackBar):
        page.show_dialog(snack)
    else:
        logger.debug("show_snack skipped: top dialog is %s, not a SnackBar", ...)
```

`page.pop_dialog()` (`base_page.py:427-444`) unconditionally finds the topmost **open** dialog, sets `dialog.open = False` and calls `dialog.update()`. The `isinstance` test at `:44` happens **after** the destructive side effect. So when a real `AlertDialog` is on top, it **is dismissed** (it disappears from the screen) and the snack is merely skipped — exactly the outcome the comment at `:42-43` claims to prevent ("never dismiss a real AlertDialog just to deliver a snackbar").

Net effect: a user's confirmation dialog vanishes because a background task fired a notification.

**Fix:** the type check must be a *peek* that happens **before** any mutation. Because `_dialogs` is private, the helper must own the state: keep the currently-open snack in a module-level `WeakKeyDictionary[ft.Page, ft.SnackBar]` and only ever `pop_dialog()` a snack the helper itself opened.

---

### BUG‑2 (HIGH) — Identical consecutive messages are silently dropped; the docstring's stated failure mode is wrong
`src/core/notify.py:5-8`, `:38-45`

The docstring claims *"showing a second snack while the first is still open raises RuntimeError"*. In flet 1.0.4 that is **false as stated**: `show_dialog` raises only when `dialog in self._dialogs.controls` (`base_page.py:418`) — an `in` test over a list of **dataclass controls**, whose generated `__eq__` compares *field values* (`base_control.py:160`, `dataclass(**dataclass_kwargs)`; identity `__hash__` at `base_control.py:280`).

Verified empirically in the installed venv:

```
a == b  ->  True          # two identically-parameterised SnackBars
a in [b] -> True
```

Consequences:

- **Different** messages → `a != b` → **no RuntimeError** → both SnackBars are appended to `self._dialogs.controls`, which is a **stack** (`base_page.py:856-866`: *"Stack of active dialog controls"*) → **two SnackBars are live simultaneously**, both anchored to the bottom (default `SnackBarBehavior.FIXED`), i.e. **visually overlapping**. There is no replace/queue policy anywhere in the app.
- **Identical** messages → `a == b` → RuntimeError → `pop_dialog()` closes the old snack but **does not remove it from `_dialogs.controls`** (removal only happens in `_remove_dialog` once Flutter reports the dismissal, `base_page.py:488-491`) → the retry `page.show_dialog(snack)` at `:45` **raises the same RuntimeError again** → it escapes the inner `except` (already executing) → caught by the outer `except Exception` at `:51` → logged at WARNING → **the second message is lost**.

Net user-visible behaviour: repeating the same message (e.g. pressing the same button twice) shows the snack once and *nothing* the second time; different messages stack and overlap.

**Fix:** stop creating a second dialog. Track the open snack per page and *update it in place* (content, bgcolor, action, and restart its timer via `open = False` → `open = True`), or guarantee replacement by removing the stale control from the stack before re-showing.

---

### BUG‑3 (HIGH, flet‑1.0.4‑specific) — `duration` is silently ignored whenever an action is present
`src/core/notify.py:22`, `:29-36`

From the installed source (`snack_bar.py:303-314`):

> `persist` — *"If not provided, but the snackbar `action` is not null, the snackbar will persist as well."*

So `ft.SnackBar(action=..., duration=ft.Duration(milliseconds=4000))` **never auto-dismisses** — it stays on screen until the user taps the action or swipes it away. `show_snack`'s `duration` argument is a no-op in exactly the case where the caller explicitly asks for an action button. Compounding it, `SnackBarAction`'s own docstring states *"Snack bar actions will only respond to first click"* (`snack_bar.py:108-112`), so the action becomes a dead button after one use.

**Fix:** pass `persist=False` explicitly whenever an action is supplied (or document that action-snacks persist and require `duration` to be ignored).

---

### BUG‑4 (MEDIUM) — Hard-coded white text on caller-supplied backgrounds is unreadable
`src/core/notify.py:32-33`

```python
content=ft.Text(message, color=ft.Colors.WHITE),
bgcolor=bgcolor or ft.Colors.BLACK,
```

Callers pass `AppColors.WARNING = "#F9A825"` (`src/core/theme.py:23`) and `AppColors.ERROR = "#D32F2F"` (`src/core/theme.py:24`) as `bgcolor`. **White on `#F9A825` is ≈1.9:1 contrast** (WCAG AA needs 4.5:1 for body text, 3:1 for large text) — the "Nothing to copy yet" / "Nothing to share yet" warnings (`src/app_shell.py:161, 176, 212, 218`) are effectively unreadable. White on `#D32F2F` is ≈4.0:1 — also below AA for body text.

**Fix:** derive the text colour from the resolved `bgcolor` (relative luminance → black/white), or add an explicit `color` parameter that defaults to the luminance-derived value.

---

### BUG‑5 (MEDIUM) — Long messages are neither truncated nor bounded in height
`src/core/notify.py:32`

`ft.Text(message, ...)` has no `max_lines` / `overflow`, so a long message produces an arbitrarily tall snackbar that can cover the UI. Truncation is currently done ad hoc by one caller (`src/main.py:1123`: `hudson_out[:120] + "..."`), so every other caller is exposed.

**Fix (owned by the helper):** cap the message (e.g. 200 chars + ellipsis) and set `max_lines=3`, `overflow=ft.TextOverflow.ELLIPSIS`.

---

### BUG‑6 (MEDIUM) — ANSI escape sequences from hudson reach the Flutter client verbatim
`src/core/notify.py:32` (inbound path: `src/main.py:1123`, `src/main.py:1579`)

`src/main.py:1123` / `:1579` slice raw hudson subprocess output into the message and hand it to `show_snack`, which passes it unchanged into `ft.Text`. If the child process emits ANSI CSI/OSC sequences, the literal escape bytes are shipped to the client and render as garbage glyphs (`[?25l`, `[0m`, …). The repo has **no** `colorama` usage (`grep -rn "colorama\|Fore\.\|Style\." src/` → empty), so any such bytes arrive raw from the child process. (Whether the pinned hudson build currently emits ANSI was not verifiable from the venv — no `x1b`/`ansi` matches under `.venv/Lib/site-packages/hudson/`. Treat this as a latent, must-defend-against path.)

**Where the fix belongs — here, not at the call sites.** The colorama agent proposed stripping at ~40 call sites. That is strictly worse:
- 40 duplicated strips, each able to drift or be missed;
- new call sites will forget it;
- `show_snack` is already the *single* choke point through which 100% of user-visible text flows (§3).

Strip once inside `show_snack`, before building the `Text`:

```python
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
message = _ANSI_RE.sub("", message)
```
(also strip the remaining C0 control characters except `\n`/`\t`).

---

### BUG‑7 (LOW) — Broad `except Exception` hides programming errors and loses the traceback
`src/core/notify.py:51-52`

`logger.warning("show_snack failed: %s", ex)` flattens every failure — including a `TypeError` from a malformed `bgcolor` or a genuine programming error — into a one-line WARNING with no traceback. Note this is also the sink where BUG‑2's second `RuntimeError` disappears. Use `logger.exception(...)`/`exc_info=True` for unexpected exception types, keeping the intended WARNING level only for the expected `RuntimeError` path.

---

### BUG‑8 (LOW, correctness of the stated contract) — `on_action` is untyped
`src/core/notify.py:24`

Every other parameter is annotated; `on_action=None` is not. It should be `ft.ControlEventHandler[ft.SnackBarAction] | None = None` (or `Callable[[ft.SnackBarAction], None] | None`), matching `SnackBarAction.on_click` (`snack_bar.py:148`).

---

## 5) Improvements (concrete, minimal)

**Dead code / unused exports**
- The module exports only `show_snack`; `logger` is module-private; both imports (`logging`, `flet as ft`) are used. **No unused imports, no unused exports.**
- The `action` branch (`src/core/notify.py:29-30`, `:36`) is **dead in production** — no caller passes `action_label=` (§3). It is not harmful, but it is untested and carries BUG‑3. Either delete it or add a caller + a test.
- The inner `except RuntimeError` block (`:40-50`) is **effectively broken** (BUG‑1/BUG‑2): its guard is a no-op and its retry always re-raises.

**Fix list (ordered by value)**

1. **Own the open-snack state in this module.** Add a module-level `WeakKeyDictionary[ft.Page, ft.SnackBar]` (weak keys avoid leaking `Page`s). On each call: if a snack is currently open for that page, update it **in place** — `snack.content = ft.Text(msg, ...); snack.bgcolor = ...; snack.action = ...; snack.open = False; snack.update(); snack.open = True; snack.update()` — instead of pushing a second control. This single change kills BUG‑1, BUG‑2, and the overlap/stack problem at once, and removes the need for `pop_dialog()` entirely.
2. **Never `pop_dialog()` a dialog this module did not open.** If the RuntimeError path must be kept, decide *before* popping (using the tracked snack identity), not after.
3. **Strip ANSI + control characters once**, at the top of `show_snack` (BUG‑6). Do **not** push this to the call sites.
4. **Truncate centrally** to ~200 chars with `max_lines=3`, `overflow=ft.TextOverflow.ELLIPSIS` (BUG‑5), and remove the ad-hoc `[:120]` slices in `src/main.py:1123` / `:1579`.
5. **Derive the text colour from `bgcolor`** (relative luminance → near-black or white), or expose a `color` parameter (BUG‑4).
6. **Pass `persist=False` explicitly when an action is present** (BUG‑3).
7. **Fix the docstring** (`src/core/notify.py:1-9`): correct the version to `1.0.4`, and replace the incorrect "a second snack while the first is open raises RuntimeError" claim with the real semantics ("`show_dialog` raises only when the *same* control instance (by field equality) is already on the page's dialog stack; a snackbar stack, not a single-dialog model").
8. **Type `on_action`** (BUG‑8) and **use `logger.exception` for unexpected errors** (BUG‑7).
9. **Return `bool`** (success/failure) instead of `None` so callers can react to a dropped notification — currently BUG‑2 is invisible to the UI.
10. **Document that `show_snack` is UI-thread-only.** It mutates `page._dialogs.controls` and calls `update()` (`base_page.py:424-425`); the app runs worker threads (`src/services/sherlock_service.py`, `src/services/phone_service.py`, `src/services/storage_service.py`). No current caller invokes it off-thread, but a cross-thread call would be swallowed by the broad `except` at `:51` with no diagnostic.

**Verified-safe (no change needed)**
- `str | None` annotations (`:21-23`) are fine: the venv is **Python 3.14.7** and there is no `from __future__ import annotations` (not needed at 3.14).
- `ft.Duration(milliseconds=duration)` is valid; `DurationValue = Union[Duration, int]` (`duration.py:236`) — the explicit wrapper is defensive but correct.
- `page.show_dialog` / `page.pop_dialog` are synchronous in 1.0.4 and are used correctly as such.
- `SnackBar.open` is correctly left at its default — `show_dialog` sets it.

---

## 6) Verdict

**Severity: MEDIUM. The module is API-clean but semantically fragile, and it is where three cross-cutting defects concentrate.**

- ✅ **No hallucinated flet API.** Every symbol (`ft.SnackBar`, `ft.SnackBarAction`, `ft.Duration`, `ft.Colors.WHITE/BLACK`, `page.show_dialog`, `page.pop_dialog`) exists in the installed flet **1.0.4** with the expected signatures. The `page.open` removal claim in the docstring is accurate. The flet agent's stale-version finding is **confirmed** (`src/core/notify.py:1, 4` say 1.0.1; installed is 1.0.4).
- ❌ **Three real defects:** BUG‑1 (a real `AlertDialog` gets dismissed because the guard runs *after* `pop_dialog()`), BUG‑2 (identical consecutive messages are silently dropped; different messages stack and overlap instead of replacing), BUG‑3 (`duration` is a no-op when `action` is set, because flet 1.0.4 makes action-snackbars `persist`).
- ⚠️ **Two missed responsibilities at the right layer:** ANSI scrubbing (BUG‑6) and message truncation (BUG‑5) belong in `show_snack`, **not** at the ~40 call sites — the colorama agent's call-site proposal should be redirected here.
- ⚠️ **One legibility defect:** hard-coded white text on `AppColors.WARNING` (#F9A825) ≈1.9:1 contrast (BUG‑4).
- 🧹 **Minor:** untyped `on_action` (BUG‑8), broad `except` without traceback (BUG‑7), inaccurate docstring, and an `action` code path that is dead in production.

**Recommendation:** fix BUG‑1/BUG‑2/BUG‑3 (all three collapse into one change: own the open-snack instance per page and update it in place rather than pushing a second dialog), then add the ANSI strip + truncation, then the colour derivation. Everything else is cosmetic. No call-site changes are needed anywhere in `src/`.

**Files referenced**
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/core/notify.py`
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/base_page.py` (lines 402-491, 856-866)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/material/snack_bar.py` (lines 101-325)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/dialog_control.py`
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/duration.py` (line 236)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/base_control.py` (lines 160, 280)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/core/theme.py` (lines 12-30)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/main.py` (lines 306-319, 922, 1123, 1579, 2316-2320, 2371-2373)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/app_shell.py` (lines 157-222, 443-464)
