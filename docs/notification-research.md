# Flet Notifications — Deep Research

Research date: 2026-10-10 · Target: flet 1.0.4 (installed, verified)
Scope: every notification mechanism reachable from a Flet 1.0.4 app, what
each needs, and what fits Sherlock.

---

## The headline finding

**Flet 1.0.4 has no notification service. At all.**

I verified this two ways, not from memory:
- `list_flet_api` on the installed 1.0.4 returns the complete `Services`
  list: Accelerometer, Barometer, Battery, BrowserConfiguration, Clipboard,
  Connectivity, FilePicker, Gyroscope, HapticFeedback, Magnetometer, OpenUrl,
  PickFiles, ScreenBrightness, SemanticsService, ShakeDetector, Share,
  SharedPreferences, StoragePaths, UrlLauncher, UserAccelerometer, Wakelock,
  WebViewConfiguration. **No local-notification, no push-notification, no
  NotificationManager.**
- A full-text search of the installed `flet` package for "notification"
  returns only: observable change emissions, scroll notifications, keyboard
  notifications, `Badge`'s docstring, and one example icon name. Nothing that
  posts to the OS notification shade.

So the answer to "what is the best way to do notifications in Flet" is:
**there isn't one in core, and every third-party route adds a dependency.**

---

## What you CAN do today — zero new dependencies

### 1. In-app transient message: `SnackBar` (+ `SnackBarAction`)
Already the app's feedback channel (87 call sites) and correct for it.
- `ft.SnackBar(content, bgcolor, duration, action=SnackBarAction(label, on_click))`
- Shown via `page.show_dialog(...)` — SnackBar is a `DialogControl` in 1.0.
- Limitation: only visible while the app is in the foreground.

**Use for:** scan errors, copy/share confirmation, validation messages.
Already implemented; no work needed.

### 2. In-app persistent strip: `Banner`
`ft.Banner` — a Material banner pinned to the top of the screen, dismissible,
with up to two actions. Unlike a SnackBar it does not auto-dismiss and can
carry a progress indicator.

**Use for:** the active-scan banner (today it's a custom `Container`
equivalent — `ActiveScanBanner`), or a persistent "new results available"
strip.

### 3. Count badge on navigation: `Badge`  ← the interesting one
`ft.Badge` (verified API, flet 1.0.4) attaches to
`NavigationBarDestination` / `NavigationRailDestination` / icon buttons:

```python
ft.NavigationBarDestination(
    icon=ft.Icons.HISTORY,
    label="History",
    # badge=ft.Badge(label="3")  <- when new entries landed
)
```
Key properties: `label` (1–4 chars, or None for a dot), `label_visible`
(conditionally hide without rebuilding the nav), `bgcolor`, `text_color`,
`small_size`, `large_size`, `offset`, `alignment`.

**Use for:** "N new results/history while you were on another tab." This is
the closest thing to a real notification Flet gives you for free, and it is
the one genuinely missing affordance in Sherlock today.

### 4. Reacting to background/foreground: `AppLifecycleState`
`page.on_app_lifecycle_state_change` with `AppLifecycleStateChangeEvent`,
states include `RESUME`, `SHOW`, `HIDE`, `PAUSE`, `DETACH` (already wired in
`main.py` for biometric re-lock).

**Use for:** when the app comes back to the foreground, check whether a scan
finished while you were away and surface a Badge + one SnackBar.

### 5. Physical feedback: `HapticFeedback`
`HapticFeedback().medium_impact()` etc. — already used on search/submit.

### 6. Keeping the device awake during a scan: `Wakelock`
`ft.Wakelock` service exists. Not currently used; a multi-minute scan with the
screen off can be throttled by the OS.

---

## What needs a NEW dependency (your rule blocks these)

| Option | What it is | Adoption | Verdict |
|---|---|---|---|
| `flet-android-notifications` | Native Android notification shade | 7★, verified package | Best-in-class if you ever lift the rule |
| `flet-local-notifications` | Multi-platform local notifications | 0★, verified | Too young to trust with your revenue app |
| Pyjnius DIY (`Flet-Post-Notification`) | Calls the Android API directly via Pyjnius | 2★, demo-grade | Possible without a package — still a dep (pyjnius) |
| `flet-geolocator` `ForegroundNotificationConfiguration` | The only notification object in official Flet docs — drives a foreground-service notification | official | Only meaningful if we adopt geolocation (we don't) |

None of these can be used under the current "no new dependencies" rule.

---

## The DIY route (no package, still a dependency)

flet-local-auth proves the pattern: a small Dart/Flutter plugin wrapped as a
Flet `Service`. A `LocalNotifications` service over
`flutter_local_notifications` is maybe 300 lines of Dart plus the Python
wrapper, then a `pyproject` dependency on it. It is genuinely
cross-platform and is what I would build **if you approve one dependency**.
Without approval it is off the table.

---

## Recommendation for Sherlock

**Build now, zero dependencies (highest value first):**

1. **Badge on the History nav destination** — when a scan completes while the
   user is on Home/Results, the History tab shows the count of new entries;
   it clears when they open History. This is the single most useful
   "notification" the app can have and needs nothing new.
2. **Scan-completion SnackBar with action** — on foreground resume, if a scan
   finished while backgrounded, show "Scan finished — 14 accounts found" with
   a "View" action that jumps to Results. Uses the existing `AppLifecycleState`
   hook and the existing `show_snack`.
3. **Optional `Wakelock` during scans** — set on scan start, released on
   completion/cancel. Two lines, prevents OS throttling of long scans.

**Explicitly not possible without a dependency:** anything that appears in
the Android notification shade ("your scan is done") while the app is closed
or backgrounded. If that is a goal, the decision you need to make is whether
`flet-android-notifications` (7★, verified) is acceptable as the single
exception to the no-new-deps rule.

---

## Notes for whoever picks this up

- Verified against `flet==1.0.4` in `.venv`; the Badge/Banner/SnackBarAction
  APIs were read from installed source, not documentation memory.
- `ft.Banner` exists in the Material controls list but is currently unused by
  this app.
- The app's nav bar is rebuilt in `app_shell.py:1089–1102` (it re-creates
  destinations when the tab set changes), so the Badge must be attached to
  the destination construction there, not bolted on afterwards.
