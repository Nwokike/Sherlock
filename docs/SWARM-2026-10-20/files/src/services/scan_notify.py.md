# File audit — `src/services/scan_notify.py`

**Auditor:** file-audit subagent (Sherlock V3 swarm, 2026-10-20)
**Target:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/services/scan_notify.py` (651 lines)
**Truth source:** `.venv\Lib\site-packages\` (flet **1.0.4**, Python **3.14.7**) + the repo itself. `flet-notifications` is **not installed** and no copy of its source exists anywhere on this machine, so every `flet_notifications` symbol below is reported as **unverifiable here**, not as "correct".
**Read-only audit:** no file in the repo was modified except this report.

> **Reconciliation note.** A previous audit artifact existed at this path. It cited a sibling checkout `/home/maikel/.zcode/workspace/default/flet-notifications` as the source for its upstream-API claims. **That directory no longer exists** (`ls /home/maikel/.zcode/workspace/default/` → `CollabShell, DDGS, Sherlock, Sherlock-V3, akili-v2, animepahe-tv, data-formulator, flet, ktv-player, lm-router, nkiri-tv, proot-distro-flet, socolive-tv`), and no wheel exists in any uv/pip cache. Therefore every upstream-API statement in this report is marked **unverifiable-in-this-environment**, and the flet-side findings (which *are* checkable) are the load-bearing ones. Findings that agree with the earlier artifact are re-derived independently here, from the installed flet source and from runtime execution.

---

## 1) File role

`scan_notify.py` is the **OS-notification progress surface** for a running scan: a wrapper around the (absent) `flet_notifications` package that would create two Android channels (`:350-371`), drive an Android **foreground service** whose ongoing notification *is* the progress bar (`:469-516`, `:595-617`), mirror scan ticks into the shade (`:518-552`), post a completion notification with View/Copy actions (`:554-583`), and route Cancel/View/Copy/tap back into the app (`:299-315`).

Public surface: one class `ScanNotifier` (`:162`) with 13 members, plus one test double `_FakeBackend` (`:107`).

**Headline: as shipped this file is a fully-masked no-op.** `flet_notifications` is absent → `_HAS_NOTIFICATIONS = False` (`:75`) → `ensure_ready()` returns `False` at `:237` → every outbound path short-circuits at `:478`, `:520`, `:556`. Runtime-verified in the venv:

```
module import OK
_HAS_NOTIFICATIONS = False
available -> False      is_usable -> False      ensure_ready -> False
scan_started / progress / scan_finished / scan_cancelled / shutdown -> 0 native calls dispatched
```

The service is nevertheless **wired into `main.py` at 21 call sites** — it is live at the call-graph level, dead at the effect level.

---

## 2) Import verification + call-site census

### 2.1 Real imports (verbatim)

`:43-48` — the only unconditional imports, both stdlib:

```python
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)
```

`:65-75` — the only third-party import, guarded:

```python
_HAS_NOTIFICATIONS = True
try:
    from flet_notifications import (
        Importance,
        LocalNotifications,
        NotificationAction,
        NotificationActionInput,
        NotificationChannel,
    )
except ImportError:  # pragma: no cover — dep is pinned in pyproject
    _HAS_NOTIFICATIONS = False
```

`flet` itself is **never imported** — the module duck-types `page`, so no flet symbol can go stale here.

### 2.2 Direct answers

**Does the file define a stub shim?** **No.** There is no `sys.modules` injection, no `except ImportError:` branch that defines a replacement module or re-defines `Importance` / `NotificationAction` / `NotificationActionInput` / `NotificationChannel` / `LocalNotifications`. The sole fallback is the **boolean flag** `_HAS_NOTIFICATIONS = False` (`:75`); every guard in the file tests that flag or `self._service is None`. The module imports cleanly and does nothing.

**Does it import a missing package?** **Yes — exactly one, and it is missing.**

| Check | Command | Result |
|---|---|---|
| installed? | `ls .venv/Lib/site-packages \| grep -i notif` | nothing — only `flet`, `flet_ads`, `flutter/`, `user_scanner`, `phonsint` |
| importable? | `.venv/Scripts/python.exe -c "import flet_notifications"` | `ModuleNotFoundError: No module named 'flet_notifications'` |
| vendored in repo? | `find . -path ./.venv -prune -o -iname "*flet_notification*" -print` | no hits |
| source checkout anywhere? | `ls ~/.zcode/workspace/default/` | **no `flet-notifications`** |
| wheel in cache? | `find ~/.cache ~/AppData/Local/uv ~/AppData/Local/pip -iname "*flet_notification*"` | no hits |
| declared dependency? | `pyproject.toml` `[project].dependencies` | `flet>=1.0.4`, `flet-ads>=1.0.4`, `user-scanner>=1.5.2.3`, `phonsint>=0.1.0` — **no `flet-notifications`** |

**The comment at `:74` — "dep is pinned in pyproject" — is false.** The repo's own roadmap says the opposite:
- `docs/roadmap.md:34` — "flet-notifications scan progress notification → **deferred (not in V2 deps; add later if parity wanted)**"
- `docs/roadmap.md:22` — M5 row: "notifications (if flet-notifications added) | pending"

### 2.3 False citations inside the docstring

Three citations point at files that **do not exist on this machine** (all verified `MISSING`):

| Docstring | Cited path | Reality |
|---|---|---|
| `:14` | `.venv/flet_notifications/channels.py:13-16` | absent (package not installed) |
| `:26` | `.venv/flet_notifications/actions.py:9-28` | absent |
| `:92` | `.venv/flutter/flet_notifications/lib/src/notifications_service.dart:1254-1265` | absent — `.venv/Lib/site-packages/flutter/` contains **only `flet_ads/`** |

They read as citations of inspected code; they cannot be checked here.

### 2.4 Call-site census (grep over `src/` + `tests/`, excluding the file itself)

| Symbol | Line | External call sites | Verdict |
|---|---|---|---|
| `ScanNotifier` | `:162` | `main.py:89` (import), `main.py:117` (ctor) | used |
| `ensure_ready` | `:216` | 1 — `main.py:278` (awaited) | used |
| `set_handlers` | `:456` | 1 — `main.py:266` | used |
| `scan_started` | `:469` | 1 — `main.py:281` | used |
| `progress` | `:518` | 1 — `main.py:1406` | used |
| `scan_finished` | `:554` | 3 — `main.py:1039`, `:1570`, `:1800` | used |
| `scan_cancelled` | `:585` | 7 — `main.py:1034, 1441, 1558, 1717, 1791, 1839, 1853` | used |
| `stop_service` | `:595` | 7 — `main.py:233, 380, 1147, 1179, 1671, 1681, 1693` | used |
| `shutdown` | `:634` | 1 — `main.py:2431` (`page.on_close`) | used |
| `open_settings` | `:435` | 1 — `main.py:335` | used |
| `available` | `:187` | **0** | **dead** |
| `is_usable` | `:191` | 0 external (internal: `:478`, `:520`, `:556`) | internal-only public method |
| `request_permission` | `:444` | **0** | **dead** |
| `_dismiss_progress` | `:619` | **0** | **dead** |
| `_FakeBackend` | `:107` | **0** | **dead** (53 lines) |
| `_warn_denied` | `:422` | 1 internal (`:419`) | used |
| `_fire_view` | `:627` | 2 internal (`:302`, `:313`) | used |

**No test anywhere touches this module** — `grep -rn "scan_notify\|ScanNotifier\|notification" tests/` → **zero hits**. The file is 100 % untested.

### 2.5 flet 1.0.4 API verification (the half that *is* checkable)

| Used here | flet 1.0.4 reality | Status |
|---|---|---|
| `page.services` (`:328-329`) | **Exists**: `flet/controls/base_page.py:822-825` → `self.__root_view().services` | OK (but see C8) |
| `page.run_task(handler, *args, **kwargs)` (`:482, 526, 566, 614, 615, 623, 646, 647`) | `flet/controls/page.py:929-967` — `asyncio.run_coroutine_threadsafe`; **raises `TypeError` unless `handler` is a coroutine function** | OK; latent risk (C10) |
| `Service.__post_init__` self-registration (docstring `:34-38`) | `flet/controls/services/service.py` → `page._services.register_service(self)`; silently skipped when `context.page` is unset | docstring accurate; see **C9** |
| `ServiceRegistry.unregister_services` "refcount <= 3" (docstring `:36-38`) | `flet/controls/page.py:228-246`: `min_refs = 3 if sys.version_info >= (3, 14) else 4`, keeps `sys.getrefcount(service) > min_refs` → **accurate for this project** (`requires-python = ">=3.14"`). It runs after *every* event dispatch (`flet/messaging/session.py:570`), not only at app close. | accurate |
| "flet's own invoke timeout is 10s per call" (`:50-53`, `:226-231`) | **No such default.** `base_control.py:451` and `session.py:471` both declare `timeout: Optional[float] = None` → an unanswered invoke waits **indefinitely**. | **false premise (C11)** |

---

## 3) Correctness findings

### C1 — CRITICAL — the whole feature is unreachable, and the file claims otherwise
`flet_notifications` is absent → `_HAS_NOTIFICATIONS = False` (`:75`) → `ensure_ready` returns `False` at `:237` → `scan_started` (`:478`), `progress` (`:520`), `scan_finished` (`:556`) all return immediately → **zero notifications on every platform in every scan mode**, silently. `main.py:278` treats `ready == False` as "scan without notifications" and proceeds. The `:74` "pinned in pyproject" comment is why this survived review.

### C2 — HIGH — teardown is gated on the "unavailable" latch, so the foreground service can never be retracted
`_can_dispatch()` (`:204-214`) returns `self._service is not None and not self._unavailable`, and it guards **`stop_service` (`:611`)**, **`shutdown` (`:643`)**, `open_settings` (`:437`), `request_permission` (`:446`), `_dismiss_progress` (`:620`).

The latch only means "a **probe** got no answer" (`:269`, `:279`) — it does not mean the native layer is gone. But because it also disables the *teardown* calls, an already-running foreground service can never be stopped and `NOTIF_ID_SCAN` can never be cancelled. That is exactly the orphan-bar symptom the file claims to fix (`:596-609`) and that `main.py:225-232` relies on ("the orphaned bar looked exactly like a scan stuck at 99%"). **Teardown needs a weaker guard** (e.g. `self._service is not None`) than the outbound-post guard.

### C3 — HIGH — cancel-vs-show race: a late progress tick resurrects the "stuck at N %" bar
`stop_service()` (`:613-615`) submits **two independent** tasks (`stop_foreground_service`, then `cancel(NOTIF_ID_SCAN)`); `scan_finished` (`:566`) submits a **third** (`show(NOTIF_ID_DONE)`). `page.run_task` schedules each as its own task on the connection loop, so *submission* order is preserved but **completion order is not** — the "Stop comes first so the OS cannot re-post…" claim at `:608-609` is a claim about submission only.

Worse, `progress()` (`:518`) is driven from the scan progress path (`main.py:1406`) and can submit `show(NOTIF_ID_SCAN, …)` **after** the cancel landed → the progress bar is re-posted and stays at its last percentage. There is **no generation counter / invalidation token** on `ScanNotifier`, so nothing distinguishes a stale tick from a current one. Fix: one coroutine that awaits stop-then-cancel, plus a per-scan generation guard.

### C4 — HIGH — the inline-reply Cancel action is destroyed by the very next progress tick
`scan_started` gives Cancel an inline text input (`:493-500`):
```python
NotificationAction(id=_ACTION_CANCEL, title="Cancel",
                   input=NotificationActionInput(label="Reason (optional)")),
```
`progress()` re-posts the action list **without** the input (`:536-549`):
```python
NotificationAction(id=_ACTION_CANCEL, title="Cancel"),
```
The file explicitly reasons about this hazard — "Re-show REPLACES the action list, so View must be here too" (`:538-540`) — and fixes only the `View` half. After the **first** progress tick the inline reply is gone, so the feature advertised at `:23-24` ("Cancel (with inline reply so the scan stops without opening the app)") lives for about one tick. And `_on_action` (`:306-313`) never reads the reply payload at all — it inspects only `action_id` — so even when the input is present the typed text is discarded.

### C5 — MEDIUM — channel-creation failure is masked as success
`_ensure_channels` catches its own exception and logs it (`:373-374`), then returns `None`. `_probe` cannot distinguish that from success (which is exactly why it returns a `(completed, value)` tuple, `:255-265`) → `_probe` reports `ok=True` (`:244-246`) → `ensure_ready` sets `_ready = True` (`:250-252`). The notifier then posts to `channel_id="scan_progress"` / `"scan_result"` channels that **were never created** — on Android a post to an unknown channel id is dropped, so the user sees nothing while `is_usable()` reports `True`. The failure must propagate (or set a distinct "channel missing" state).

### C6 — MEDIUM — event handlers are attached *after* the service has already been registered with the client
`_construct` (`:296-331`) does:
```python
svc = LocalNotifications()      # :297  → Service.__post_init__ → page._services.register_service(svc)
svc.on_tap = _on_tap            # :304
svc.on_action = _on_action      # :315
svc.on_dismissed = _on_dismissed  # :326
```
flet 1.0.4's `Service.__post_init__` (`flet/controls/services/service.py`) self-registers on construction, and `ServiceRegistry.register_service` (`flet/controls/page.py:119-153`) **pushes an update immediately** when the page is already mounted. flet's own `Service` docstring states the rule explicitly:

> *"Set client properties and event handlers in `init()` so they are included in registration and available when the Dart service initializes."*

Assigning `on_tap` / `on_action` / `on_dismissed` **after** construction means they are not part of the registration push; nothing in this file triggers a follow-up update (`page.update()` is never called), so the client may never learn the handlers exist. The View / Copy-report / Cancel actions and tap-to-results would then be inert even once the dependency is installed. Fix: subclass `LocalNotifications` and set the handlers in `init()`, as flet prescribes.

### C7 — MEDIUM — `try/except Exception` around `page.run_task` cannot catch the failures it is written to catch
Every dispatch site wraps `self.page.run_task(...)` in `try/except Exception` (`:481-516`, `:525-552`, `:561-583`, `:613-617`, `:619-625`, `:643-650`). But `page.run_task` (`flet/controls/page.py:943-965`) does:
```python
future = asyncio.run_coroutine_threadsafe(handler(*args, **kwargs), self.session.connection.loop)
…
future.add_done_callback(_on_completion)   # re-raises the exception on the loop
```
The handler coroutine **has not started** when `run_task` returns; an exception raised *inside* it surfaces in the Future and is re-raised by flet's `_on_completion` on the event loop. The local `try/except` therefore catches only *scheduling* errors, never *execution* errors — precisely the class of failure the module docstring (`:39-40`) promises to swallow ("Every failure is logged, never raised into the scan path"). The file's own `_can_dispatch` docstring (`:206-212`) describes this correctly ("raising inside `page._on_completion`, which printed a full traceback per call") — but the fix applied was only the `_unavailable` latch, not error capture. **Any native error from `show()` will still print a full traceback.**

### C8 — MEDIUM — `page.services` is a *skipped* list: appending to it does not register the service with the client
`page.services` is `View.services` (`flet/controls/base_page.py:822-825`), declared `services: list[Service] = field(default_factory=list, metadata={"skip": True})` (`flet/controls/core/view.py:144`) → the list is **never serialized to the client**. The only client-visible registration path is `Service.__post_init__` → `page._services.register_service()` (`flet/controls/services/service.py`), which silently no-ops when `context.page` is unset (`RuntimeError` swallowed). So `self.page.services.append(svc)` (`:329`) has **no client-side effect**; it only adds a Python reference — which does help against `unregister_services` (that runs after every event dispatch, `flet/messaging/session.py:570`). The docstring at `:34-38` describes the intent correctly, but the mechanism is "hold a strong reference", not "mount the service".

### C9 — MEDIUM — the two-valued `is_email` flag mislabels phone-mode scans
`scan_started` (`:480`), `progress` (`:522-523`) and `scan_finished` (`:559`) derive the noun from a boolean. The app has **three** modes, and the phone mode calls `main.py:1759` → `_ensure_notifications_ready(phone_clean, is_email=False)` → the notification reads **"Scanning username"** and the completion **"Scan finished — N accounts"** for a phone-number scan. The notification layer models 2 of the app's 3 modes.

### C10 — MEDIUM — scan identity leaks across scans
`_active_target` / `_active_is_email` (`:171-172`) are written by `scan_started` (`:476-477`) and **never cleared** by `scan_finished` (`:554`), `scan_cancelled` (`:585`) or `stop_service` (`:595`). A cancel leaves the previous target in place, so the next completion notification (`:558-560`) can be labelled with a target that is not its own. `stop_service` is the natural reset point.

### C11 — MEDIUM — the risk model behind `_PROBE_TIMEOUT` is wrong about flet
`:50-53` states "flet's own invoke timeout is 10s per call; waiting that out twice (channels + permission) blocked scan start for 20 seconds", repeated at `:229-231`. In flet 1.0.4 there is **no default timeout** — `BaseControl._invoke_method` (`base_control.py:451`) and `Session.invoke_method` (`session.py:471`) both default to `timeout=None` → **an unanswered native call waits forever**. The 1.5 s bound at `:53` is therefore *more* necessary than the comment claims, not less: if someone "fixes" the code believing the 10 s fallback exists, removing `_PROBE_TIMEOUT` would wedge the scan start **indefinitely** rather than for 20 s.

### C12 — MEDIUM — `shutdown()` clears the tray from `page.on_close`, where the loop may already be dead
`shutdown` (`:634-650`) posts both teardown calls through `page.run_task`, and its only caller is `page.on_close` (`main.py:2431`). If the session loop is closed by then, `asyncio.run_coroutine_threadsafe` raises synchronously → caught at `:649` → logged → **the shade keeps a live-looking bar**, the exact failure the docstring (`:635-642`) claims to prevent. Teardown on close should be awaited directly by the closing handler.

### C13 — LOW — `_unavailable` latches on *any* exception, contradicting "the next scan re-probes"
`_probe` sets `_unavailable = True` on a generic exception (`:278-281`), so one transient error ("channel already exists", a service-not-found during a hot restart) disables notifications **for the whole app lifetime** (`is_usable()` → `False` at `:197-201`; `ensure_ready` short-circuits at `:237`). The docstring at `:392-393` ("A timeout here does NOT latch … The next scan re-probes and recovers on its own") is true only for the *permission* path (`:401-407`) and is contradicted by the *probe* path two functions above. Related doc bug: `:235` "Idempotent: safe to call before every scan" is false once the latch is set.

### C14 — LOW — `_probe`'s docstring misstates `asyncio.wait_for` semantics
`:262-264`: "On timeout the coroutine is abandoned deliberately". `asyncio.wait_for` **cancels** the wrapped coroutine (and awaits its cancellation) on timeout; it does not abandon it. The practical effect is benign, but the mental model in the comment is wrong and will mislead the next maintainer about whether the native invoke is still in flight.

### C15 — LOW — `request_permission()` is unbounded (latent hang)
`:444-452` awaits `self._service.request_permissions()` with **no** timeout, unlike `_ask_permission` (`:395-400`) which correctly caps the dialog at `_PERMISSION_TIMEOUT = 15 s` (`:63`). If this method is ever wired up it can block its caller forever. Dead today, so latent.

### C16 — LOW — `_warn_denied` latches before it knows a handler exists
`:426-429`: `self._warned = True` is set **before** `cb = self._on_permission_denied; if cb is None: return`. If `set_handlers` runs after the first decline (or the controller is not attached yet), the user is never warned again for the session — the "one warning per session" budget is spent on a warning nobody saw.

### C17 — LOW — progress percentage is not clamped
`:524`: `pct = int(checked / max(total, 1) * 100)`. With `checked > total` (engine over-count, or `total` derived from a different counter) the title renders **"Scanning username — 137 %"** and `progress=checked` exceeds `max_progress=total`, producing a malformed bar. `max(total, 1)` guards divide-by-zero but not the range.

### C18 — LOW — `on_action` treats every unknown action as "open results"
`:306-313`: an unrecognised `action_id` falls into `else: self._fire_view()`. Combined with the discarded reply payload (C4), a future or unknown action silently navigates the user away from a running scan.

### C19 — LOW — `PAYLOAD_ROUTE` is written on every post and never read
`:100` sets `PAYLOAD_ROUTE = "sherlock://results"` on every post (`:492`, `:535`, `:572`), but `_on_tap` (`:299-303`) fires the View handler unconditionally and never inspects `e.payload`. The docstring's claim (`:97-99`) that "one route covers progress, completion and a cold-start tap alike" describes an intent that is not implemented — the constant is dead weight.

### C20 — LOW — `_on_dismissed` claims to update state and does not
`:317-326`: the comment says "local state must not pretend the bar is still showing", but the handler only writes a DEBUG log — `_active_target`, `_active_is_email` and `_ready` are untouched. The stated purpose is not implemented.

### C21 — INFO — `available` is a constant masquerading as a probe
`:187-189` returns the module-level `_HAS_NOTIFICATIONS`, which can never change after import. The real state probe is `is_usable()` (`:191`). `available` has **zero** call sites — exactly the kind of predicate a caller mis-trusts.

### Hallucinated / unverifiable API summary
Everything below is used by this file but **cannot be checked against any installed or cached source** in this environment (package absent, no vendored copy, no sibling checkout, no wheel in any cache): `Importance`, `LocalNotifications`, `NotificationAction`, `NotificationActionInput`, `NotificationChannel`; the methods `are_notifications_enabled`, `request_permissions`, `create_notification_channel`, `show`, `cancel`, `cancel_all`, `open_app_notification_settings`, `start_foreground_service`, `stop_foreground_service`; the events `on_tap` / `on_action` / `on_dismissed`; and the kwargs `show_progress`, `indeterminate`, `max_progress`, `progress`, `channel_id`, `start_type`, `foreground_service_types`, `payload`, `actions`, `cancel_notification`, `input`, `importance`, `play_sound`, `enable_vibration`, `show_badge`.

Two upstream-behaviour assumptions embedded in the file are **self-contradictory** and therefore suspect before they are even checked:
- the inline-reply `NotificationActionInput` is added at `:497-500` but dropped at `:537` (C4) — an upstream API would not do that;
- the action list is re-sent wholesale on every tick while the file also claims "one notification id per scan, re-shown" (`:21-22`) and "`show()` with the same id updates in place" — if `show()` truly updated in place, the action list would not need re-sending at all, and the "Re-show REPLACES the action list" note at `:538` would be unnecessary.

**No hallucinated flet API was found** — every flet symbol the file touches is real in 1.0.4 (`page.services`, `page.run_task`, `Service.__post_init__`, `ServiceRegistry.unregister_services`). The only *flet-side* factual error is the "10 s invoke timeout" premise (C11).

---

## 4) Dead-code map

| Dead item | Lines | Size | Evidence |
|---|---|---|---|
| `_FakeBackend` (class) | `:107-159` | 53 lines | 0 references outside the file; no test imports it; `ScanNotifier.__init__(self, page)` (`:165`) takes **no** service argument, so the "already-injected service" path the docstring describes (`:286-288`) is reachable only by poking the private `_service` attribute — there is no supported injection seam. |
| `request_permission` | `:444-452` | 9 lines | 0 call sites; superseded by `_ask_permission` (`:380`), the path that actually runs. |
| `_dismiss_progress` | `:619-625` | 7 lines | 0 call sites; duplicates the `cancel(NOTIF_ID_SCAN)` half of `stop_service` (`:615`). |
| `available` (property) | `:187-189` | 3 lines | 0 call sites; returns a constant (C21). |
| `PAYLOAD_ROUTE` | `:100` | 1 const | Written on every post (`:492`, `:535`, `:572`), **never read** — `_on_tap` ignores the payload (C19). |
| `is_usable` as a *public* API | `:191-202` | — | only called from inside the class (`:478`, `:520`, `:556`). |
| `ScanNotifier` as a whole | `:162-650` | 489 lines | reachable but **inert** — 100 % of the native path is gated off by the missing dependency (C1). |
| pyproject per-file-ignore `"src/services/scan_notify.py" = ["A002"]` | `pyproject.toml` | 1 line | exists solely to protect `:152` inside the dead `_FakeBackend` (below). |

### The A002 per-file-ignore — the known context is **REFUTED as stated**

The brief says the ignore "mirrors `flet_notifications.show/cancel(id=...)` signatures … load-bearing at `:152`, `:352`, `:365`, `:495`, `:506`, `:537`". Measured with the repo's own ruff 0.17.1, with the project config **bypassed** so the ignore cannot mask anything:

```
$ .venv/Scripts/ruff.exe check --isolated --no-cache --select A002 src/services/scan_notify.py
A002 Function argument `id` is shadowing a Python builtin
   --> src\services\scan_notify.py:152:28
Found 1 error.

$ .venv/Scripts/ruff.exe check --no-cache src/services/scan_notify.py     # project config
All checks passed!
```

- **Exactly one A002 exists, at `:152`** — `async def cancel(self, id: int)` inside `_FakeBackend`.
- `:352`, `:365`, `:495`, `:506`, `:537` are **keyword arguments at call sites** (`id=CHANNEL_PROGRESS`, `id=_ACTION_CANCEL`, …). A002 is *builtin-argument-shadowing* — it flags **parameter declarations**, not keyword arguments. The isolated run proves they are not flagged.
- The stated rationale is also wrong: the file calls the upstream API **positionally** — `self._service.show(NOTIF_ID_SCAN, …)` (`:528`, `:568`) and `self._service.cancel(NOTIF_ID_SCAN)` (`:615`, `:623`). It never passes `id=` to the upstream API; the only `id` **parameter** in the file belongs to the local test double.

**Consequence:** the per-file-ignore is load-bearing **only for dead test-double code**. Delete `_FakeBackend` and the ignore can go with it — which also removes a file-specific exception from `pyproject.toml` and stops it from masking a *future* real builtin-shadowing bug here (the same objection already recorded at `docs/reference/dep-ruff.md:267`).

---

## 5) Recommendation

**One clear recommendation: REWRITE — shrink `scan_notify.py` to a small, dependency-free, *tested* seam; do not add `flet-notifications` now.**

Weighed against the owner's rule ("no extra dependencies beyond what the wrapped engine needs", restated at `docs/roadmap.md:34`):

**Against "keep-with-declared-dependency" (A).** Adding the package costs a dependency *plus* Android build surgery: `POST_NOTIFICATIONS` and `FOREGROUND_SERVICE_DATA_SYNC` are **absent** from `pyproject.toml`'s `[tool.flet.android.permission]` list (only INTERNET / ACCESS_NETWORK_STATE / WAKE_LOCK / USE_BIOMETRIC are there); the manifest `<receiver>` entries the file itself depends on (`:26-28`) are only injected by the upstream patcher, which `pyproject.toml` does not express; and the Flutter half would have to ship the way `flet_ads` does (`.venv/Lib/site-packages/flutter/flet_ads/`). Net effect: a dependency + a build pipeline for a feature the roadmap explicitly deferred, whose upstream API **cannot be verified in this environment**. Notifications would also exist only in a *built* Android artifact, never under `flet run`.

**Against "remove outright" (B).** `main.py` has 21 call sites plus a permission-denied UX path (`main.py:266-335`, `settings_screen.py:809`); ripping the file out is a wider blast radius than the problem warrants, and the seam (one id per scan, FGS-backed progress, permission asked at first scan, all failures non-fatal) is a sound design worth keeping.

**For "rewrite" (C) — the concrete plan:**
1. **Do not** add `flet-notifications` to `[project].dependencies`. Keep the guarded import (`:65-75`) as an *optional* extension, and change the `:74` comment to the truth: "optional; not a declared dependency — see `docs/roadmap.md:34`".
2. **Delete the dead code**: `_FakeBackend` (`:107-159`), `request_permission` (`:444-452`), `_dismiss_progress` (`:619-625`), `available` (`:187-189`), `PAYLOAD_ROUTE` (`:100`); delete the `["A002"]` per-file-ignore from `pyproject.toml`.
3. **Fix the real bugs while the file is open** (they only bite once a backend exists): teardown must not be gated on `_unavailable` (C2); add a scan-generation counter so a stale progress tick cannot resurrect `NOTIF_ID_SCAN` (C3); keep the inline-reply input on every re-post of the action list and actually read the reply payload (C4); let a channel-creation failure propagate (C5); attach the `on_*` handlers in a `LocalNotifications` subclass's `init()` (C6); capture the dispatched coroutine's exception instead of relying on `page.run_task`'s `try/except` (C7); clear `_active_target` / `_active_is_email` on every exit path (C10); await the shutdown teardown instead of firing it from `on_close` (C12); clamp the percentage (C17).
4. **Make the mode explicit** — replace the `is_email: bool` with a `mode: Literal["username", "email", "phone"]` so phone scans stop saying "username" (C9).
5. **Correct the false claims**: the "10 s invoke timeout" premise (C11), the "abandoned coroutine" semantics (C14), and the "pinned in pyproject" comment (C1) — these are the defects most likely to mislead whoever eventually lands the dependency.
6. **Add the first tests.** The module has zero coverage; a test driving `ScanNotifier` against an injected backend (a small, *used* fake) would have caught C4, C5 and C17 immediately.
7. **If the owner later wants real notifications**, that is a deliberate roadmap change (M5 pending → in progress): declare the dependency, add the two Android permissions, add the patch step, and re-run this audit against the *installed* package — then. Do not do it as a side effect of a cleanup.

---

## 6) Verdict

| Dimension | Verdict |
|---|---|
| **Import verification** | One third-party import (`flet_notifications`, `:67-73`) and it **fails**; **not declared** in `pyproject.toml`; **no shim** is defined — the file degrades to a silent no-op through the `_HAS_NOTIFICATIONS` flag (`:65-75`). The `:74` "pinned in pyproject" comment and the three upstream file citations (`:14`, `:26`, `:92`) are false. |
| **Lifecycle / cleanup** | Structurally sound but **inert** (C1). Teardown is blocked by the unavailable latch (C2); the "stuck at 99 %" bar it claims to fix is still reachable through the cancel-vs-show race (C3); the inline-reply Cancel is destroyed by the first progress tick (C4); `shutdown` cannot be trusted from `on_close` (C12); the `on_*` handlers are attached after client registration (C6). |
| **Bugs** | 21 findings (C1–C21). The high-value ones (C2, C3, C4, C5, C6, C7, C10) are all *latent* — they bite only once a backend exists, which is exactly why nothing has caught them. |
| **Dead code** | ~73 lines (35 % of the file) with zero call sites: `_FakeBackend` (53), `request_permission` (9), `_dismiss_progress` (7), `available` (3), `PAYLOAD_ROUTE` (1). The `["A002"]` per-file-ignore exists **solely** for the dead test double (single A002, at `:152`). |
| **Hallucinated API usage** | No flet API misuse — every flet symbol used is real in 1.0.4. The `flet_notifications` surface is **unverifiable here** (package absent, no source anywhere on disk), and two of its assumed behaviours are self-contradictory inside the file (C4). The only *flet-side* factual error is the "10 s invoke timeout" premise (C11). |
| **Recommendation** | **REWRITE** — shrink to a dependency-free, tested seam; delete the dead code and the A002 ignore; fix C2–C7, C10, C12, C17; keep `flet-notifications` out of the dependency list unless the owner deliberately un-defers M5. |
| **Overall** | **Not fit to ship as-is.** 650 lines, 100 % unreachable, 100 % untested, 35 % dead, asserting a dependency the project does not have. It fails closed and silently, so it is not dangerous at runtime — but it is actively misleading to the next maintainer: it claims a dependency is "pinned in pyproject", cites three source files that do not exist, invents a flet timeout that does not exist, and models a two-mode UI for a three-mode app. |
