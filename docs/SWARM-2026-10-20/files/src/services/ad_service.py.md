# Audit — `src/services/ad_service.py`

**File:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/services/ad_service.py` (323 lines)
**Audited against (installed deps = truth):** `flet 1.0.4` (`.venv/Lib/site-packages/flet`), `flet-ads 1.0.4` (`.venv/Lib/site-packages/flet_ads`), Flutter extension `.venv/Lib/site-packages/flutter/flet_ads/lib/src/interstitial.dart`, CPython 3.14.7.
**Scope:** this file only (call sites cited for context only).

---

## 1) File role

`AdService` is the single AdMob/UMP owner for one Flet session:

| Member | Lines | Role |
|---|---|---|
| `gather_consent()` | `ad_service.py:90-131` | UMP flow: request info → show form if required → read `can_request_ads`; probes the privacy-options requirement. |
| `show_privacy_options()` | `ad_service.py:133-171` | Re-opens the UMP privacy-options form; returns an honest string outcome. |
| `preload_interstitial()` | `ad_service.py:175-209` | Builds + registers a preloaded `InterstitialAd` service. |
| `show_interstitial()` | `ad_service.py:221-303` | Rate-limited show: uses the preloaded ad, else queues a self-loading "fresh" instance. |
| `_handle_close()` | `ad_service.py:211-219` | `on_close` sink: releases the spent ad, then fires the app callback. |
| `close()` | `ad_service.py:305-314` | Teardown: releases both interstitial slots, clears the banner pool. |
| `_release_service()` | `ad_service.py:317-323` | Helper that drops a service from the keep-alive list. |

Instantiated once per session at `src/main.py:512`; show triggers at `src/main.py:955`, `src/main.py:1515`, `src/main.py:1761`, `src/app_shell.py:457`; teardown at `src/main.py:2426-2428`. No tests reference this module (`tests/` has zero hits for `AdService`/`ad_service`).

---

## 2) API verification summary

Every symbol the file uses exists in installed `flet-ads 1.0.4` / `flet 1.0.4`. **No hallucinated APIs were found.** Two behavioural mismatches (not name errors) are called out below.

| Usage in this file | Installed truth | Verdict |
|---|---|---|
| `fta.InterstitialAd(unit_id=, on_load=, on_error=, on_close=)` — `:188-195`, `:284-289` | `flet_ads/interstitial_ad.py:5-6` (`@ft.control("InterstitialAd")`, `ft.Service` + `BaseAd`); fields `unit_id` `base_ad.py:21`, `on_load` `:31`, `on_error` `:36`, `on_close` `:53` | ✅ correct (kw-only dataclass) |
| `await ad.show()` — `:250`, `:271` | `flet_ads/interstitial_ad.py:30-37` → `await self._invoke_method("show")` | ✅ correct API, ⚠️ **semantics**: the Dart side returns `null` immediately (`flutter/flet_ads/lib/src/interstitial.dart:57-59`), so the `await` resolves when the ad is *presented*, not when it is *dismissed* |
| `fta.ConsentManager()` — `:101` | `flet_ads/consent_manager.py:13-14` (`ft.Service`) | ✅ correct |
| `request_consent_info_update()` — `:106` | `consent_manager.py:44` | ✅ correct |
| `load_and_show_consent_form_if_required()` — `:107` | `consent_manager.py:108` | ✅ correct |
| `can_request_ads()` — `:108`, `:163` | `consent_manager.py:85-92` (returns `bool`) | ✅ correct |
| `get_privacy_options_requirement_status()` — `:111`, `:151` | `consent_manager.py:94-106` (returns `PrivacyOptionsRequirementStatus`) | ✅ correct |
| `show_privacy_options_form()` — `:162` | `consent_manager.py:118` | ✅ correct |
| `fta.PrivacyOptionsRequirementStatus.REQUIRED` — `:114`, `:156` | `flet_ads/types.py:171-193` | ✅ correct |
| `on_paid` | only exists on `BannerAd` (`flet_ads/banner_ad.py:36`), **not** on `BaseAd`/`InterstitialAd` | ✅ not used — do **not** add it to `InterstitialAd` (would be a `TypeError`) |
| `page.services` — `:104-105`, `:201-202`, `:213`, `:256`, `:281`, `:295-296`, `:309` | `flet/controls/base_page.py:821-832` → returns `View.services` (`flet/controls/core/view.py:144`, `metadata={"skip": True}`) — a plain Python list, **not** the live registry `page._services` (`flet/controls/page.py:714`) | ⚠️ works as a **keep-alive reference only**; it is not what registers the service with the client (see §3.1) |
| `page.services.remove(item)` — `:321` | `list.remove` compares with `==`; flet's own registry compares by identity (`flet/controls/page.py:148`, `is service`) | ⚠️ equality-based removal of dataclass controls (see N6) |
| `page.platform` — `:84` | `flet/controls/page.py:595` → `platform: Optional[PagePlatform] = None` | ⚠️ `None` until the client patches it (see N4) |
| `PagePlatform.is_mobile()` — `:84` | `flet/controls/types.py:843-849` (IOS/ANDROID) | ✅ correct |
| async `on_close` handler — `_handle_close` `:211` | `flet/controls/base_control.py:514-521` — `inspect.iscoroutinefunction` → awaited | ✅ correct |
| `page.run_task(coro, *args)` — `:286` | `flet/controls/page.py:929-945` (requires a coroutine fn; sets the page context first) | ✅ correct |
| `Service` auto-registration | `flet/controls/services/service.py:42-58` — `__post_init__` calls `page._services.register_service(self)` when a page context is active | ✅ the ad is registered with the client **at construction**, before any `page.services.append` |
| service GC | `flet/messaging/session.py:570` → `page.py:228-247`: keeps services with `sys.getrefcount(service) > 3` (py≥3.14), called after every event | ✅ the keep-alive trick works, but by refcount proxy only |

**Summary:** the API surface is clean. Every defect below is a *lifecycle/ownership* defect, not a wrong-API defect.

---

## 3) Confirmed known bugs

### 3.1 (KNOWN #1) Restock while the shown interstitial is still full-screen — CONFIRMED, and the blast radius is larger than stated

`ad_service.py:261-263` (`finally: await self.preload_interstitial(...)`) creates a **second** live `InterstitialAd` service while the first is still displayed. The Flutter extension has exactly **one static slot** for all instances:

```dart
// .venv/Lib/site-packages/flutter/flet_ads/lib/src/interstitial.dart:10
static InterstitialAd? _interstitialAd;
```

Consequences that follow from the Dart source, all reachable from this file:

1. **`show()` resolves early.** Dart `interstitial.dart:57-59` (`case "show": _interstitialAd?.show(); return null;`) returns as soon as the ad is presented, so `await ad_to_show.show()` (`:250`) completes while the ad is still full-screen → the `finally` restock (`:261-263`) always runs during display. Same for the error path (`:253-260` → `finally` still executes → a failed show *also* creates a second ad).
2. **The slot is overwritten.** When the restocked ad loads, `interstitial.dart:44` does `_interstitialAd = ad` → the slot now points at the *new* ad, while the *shown* ad is still on screen. A later `show()` therefore shows whichever ad loaded last, not necessarily `ad_to_show`.
3. **A failed load destroys the ad on screen.** `interstitial.dart:47-50` (`onAdFailedToLoad`) calls `_interstitialAd?.dispose()` — the slot still holds the *displayed* ad → **the visible interstitial is disposed out from under the user.**
4. **Releasing one ad destroys the other.** `interstitial.dart:65-69` (`InterstitialAdService.dispose()`) also does `_interstitialAd?.dispose()` — i.e. disposing *any* service disposes *whatever is in the shared slot*. So the release of the spent ad (`_handle_close` `:213`, `_on_error` `:281`, `close()` `:309`) can destroy the freshly preloaded ad. The next `show()` then hits `_interstitialAd?.show()` on a null/disposed ad → silently shows nothing, while Python logs `"InterstitialAd shown"`.
5. **Release is not immediate.** `_release_service` (`:317-323`) only drops one strong reference; the client-side dispose happens later, when `unregister_services()` (`flet/controls/page.py:228-247`) sees the refcount fall — i.e. *after* the next event. The static-slot dispose can therefore land seconds later, long after a new ad has been loaded into the slot.

**Verdict:** confirmed. Structural rule the file violates: **at most one `InterstitialAd` may be alive at a time** (one static slot, `interstitial.dart:10`).

### 3.2 (KNOWN #2) Wrong-instance release in the fresh-path error handler — CONFIRMED

`ad_service.py:274-282`: `_on_error` releases `self._shown_interstitial`, which is *not necessarily the ad that failed*.

* Case A — the failing ad is a **preload**: `preload_interstitial` (`:188-195`) registers its own `on_error` (a logging lambda), so the fresh-path `_on_error` is not the preload's handler. But `self._shown_interstitial` is overwritten by the fresh ad at `:293`, so a *stale* preload error arriving later releases the **fresh, still-loading** ad → its keep-alive drops → the registry GC (`page.py:228-247`) unregisters it → the client disposes it → the in-flight load is aborted.
* Case B — the failing ad **is** the fresh ad: `_on_error` releases it correctly, but the ad is **not** removed from `page.services` if `self._shown_interstitial` was replaced meanwhile → the exact leak the comment at `:275-278` claims to fix still happens.
* Case C — the error is a **show** failure, not a load failure: the Dart side fires `"error"` for `onAdFailedToShowFullScreenContent` (`interstitial.dart:30-33`) as well as `onAdFailedToLoad` (`:47`). In that case the ad was loaded and possibly on screen; the handler at `:274-282` releases it → the loaded ad is dropped.

**Verdict:** confirmed. The handler must release *its own* ad (closure-captured instance), never `self._shown_interstitial`.

### 3.3 (KNOWN #3) Rate limiting — implementation basically correct, comment wrong, window measured from the wrong instant

`ad_service.py:60`, `:230-242`.

* ✅ `time.monotonic()` + `None` sentinel (`:71-74`) is correct; the comment explaining why `0.0` would be wrong is accurate and valuable.
* ✅ Check-then-set (`:232` → `:242`) contains **no `await`**, so the 30 s window cannot be bypassed by a concurrent trigger on the single-threaded loop. No lock is needed for that part.
* ❌ **Stale comment**: `:230-231` says "record the intent even when we skip", but the code returns at `:241` **before** updating `_last_interstitial_at` — it never records on a skip. The behaviour is the desirable one; the comment contradicts the code.
* ⚠️ **Window starts at the trigger, not at the dismissal**: `:242` stamps the time *before* the ad is shown. A show that fails (`:253-260`), or a fresh instance that is only queued (`:293-303`) and may never fill, still consumes 30 s of inventory.
* ⚠️ The window is per-`AdService` instance — fine here (one instance per session, `main.py:512`).

**Verdict:** confirmed as *mostly correct*; one stale comment + one semantic nit.

### 3.4 (KNOWN #4) Desktop no-op guard — CONFIRMED CORRECT

No ad object is constructed off-mobile:

* `gather_consent` returns at `:96-99` **before** `fta.ConsentManager()` (`:101`).
* `preload_interstitial` returns at `:181-183` **before** `fta.InterstitialAd(...)` (`:188`).
* `show_interstitial` returns at `:225-229` **before** any construction (`:284`).

The only ad-related import at module scope is `import flet_ads as fta` (`:36-41`, guarded by `try/except ImportError`), which constructs nothing. The banner side is separately guarded (`src/components/banner_ad.py:84-91`).

**Caveat (see N4):** the same guard answers "not mobile" for a *mobile* device whose platform has not been reported yet — the desktop safety comes partly at the price of a mobile false-negative.

### 3.5 (KNOWN #5) Consent ordering — ORDER CORRECT, SETTINGS WIRING MISSING

* ✅ Ordering is exactly the documented one (`flet_ads/consent_manager.py:23-27`): `request_consent_info_update()` (`:106`) → `load_and_show_consent_form_if_required()` (`:107`) → `can_request_ads()` (`:108`).
* ✅ The privacy probe (`:109-122`) is correctly isolated, and `show_privacy_options` (`:149-160`) re-checks `PrivacyOptionsRequirementStatus.REQUIRED` before showing the form (matches `consent_manager.py:118-126`).
* ❌ **GAP CONFIRMED — not wired to Settings.** A repo-wide grep for `show_privacy_options` / `_privacy_options_required` returns hits **only inside `ad_service.py`**. The public entry point (`:133`) has **zero callers**, and `_privacy_options_required` (`:69`, `:113`) is written but never read. A GDPR-regulated app that serves ads must expose a persistent "privacy options" control; today there is none, and nothing tells the user consent can be withdrawn.

### 3.6 (KNOWN #6) `main.py:2426-2428` swallows teardown exceptions — CONFIRMED

```python
# src/main.py:2425-2428
with contextlib.suppress(Exception):
    if controller.ad_service:
        await controller.ad_service.close()
```

`close()` (`ad_service.py:305-314`) has **no internal `try/except`**, so any failure inside it (torn-down page, `_release_service` on a dead list, `clear_banner_pool`) is discarded with no log — directly contradicting this module's own documented policy at `ad_service.py:19-20` ("we log every error, we never swallow"). `close()` must catch and log per-item failures itself.

---

## 4) NEW bugs (severity-ordered)

### N1 — HIGH — `_handle_close` releases the wrong instance too (`:211-219`)
`_handle_close` receives the event but **ignores `e.control`** and releases `self._shown_interstitial` (`:212-214`). With one static Dart slot, the `"close"` event can be triggered by a *different* ad than the one Python believes is showing (`interstitial.dart:34-39` fires `"close"` on whichever ad was actually presented). When that happens, the ad that Python is tracking is released while it is still loading → keep-alive drops → registry GC disposes it → the in-flight load is aborted. **Fix:** release `e.control` (identity), and only fall back to `self._shown_interstitial` when they match.

### N2 — HIGH — `show_interstitial` has no shutdown guard (`:221-229`)
`preload_interstitial` checks `self._is_shutting_down` (`:178-180`); `show_interstitial` does **not**. After `close()` (`:305-314`) flips the flag, a late trigger (`main.py:955`/`1515`/`1761`, `app_shell.py:457`) still constructs and registers a fresh `InterstitialAd` on a closing page: the constructor auto-registers with the client (`flet/controls/services/service.py:42-58`), so the Dart service outlives the page, or `register_service` raises mid-flight (caught at `:290-292`, but the half-registered service is left behind). **Fix:** add the same `_is_shutting_down` early return.

### N3 — MEDIUM-HIGH — Ads can be requested before consent is known (`:67`, `:184-186`, `:225-229`)
`_can_request_ads` starts **True** (`:67`). It is only set False when `flet_ads` is missing (`:94`) or UMP explicitly says no (`:123-126`). `main.py:526` launches consent+preload via `page.run_task`, while a search/export can call `show_interstitial()` before that task completes → **an interstitial is requested with no UMP decision on record** (a UMP/compliance violation; AdMob then refuses to fill in the EEA, so the inventory is wasted as well). **Fix:** default `_can_request_ads = False` and flip it True only after `can_request_ads()` returns True (the non-mobile branch at `:96-99` may keep True, since no ad is ever requested there).

### N4 — MEDIUM — "Platform unknown" is treated as "not mobile" → ads silently dead for the whole session (`:82-86`)
`Page.platform` is `Optional[PagePlatform] = None` (`flet/controls/page.py:595`) until the client patches it; `_is_mobile()` swallows the resulting `AttributeError` and returns `False` (`:83-86`). `gather_consent()` / `preload_interstitial()` run **once**, at startup (`main.py:526`), so a platform that is not yet reported means "non-mobile platform — consent flow skipped" and **no ad is ever requested for the rest of the session** (every later `preload`/`show` hits the same guard). The only trace is one INFO line. **Fix:** distinguish "unknown" from "not mobile" (e.g. `page.platform is None` → defer/retry on the first client event instead of concluding "desktop").

### N5 — MEDIUM — A failed preload is never released → leaked native ad + a dead ad in the show path (`:188-208`, `:243-248`)
The preload's `on_error` (`:191-193`) only logs. The failed ad stays in `self.interstitial` **and** in `page.services` (`:201-202`) forever: it is strongly referenced twice, so `unregister_services()` (`page.py:228-247`, `getrefcount > 3`) will never reap it → a native ad object leaks for the session. Worse, the next `show_interstitial` picks that dead ad (`:243-248`) and calls `show()` on it — the Dart slot was already disposed on load failure (`interstitial.dart:49`) → either a silent no-op or an exception; the first path logs a false `"InterstitialAd shown"`. **Fix:** in the preload `on_error`, release that ad (identity-checked) and clear `self.interstitial`.

### N6 — MEDIUM — `show_interstitial` returns `True` for a *queued* ad, contradicting its own contract (`:221-224` vs `:303`)
The docstring promises "Returns True when a show was triggered", but the fresh path returns `True` after merely *queuing* an instance (`:302-303`) that may never load, never fill, or be superseded by the static slot. Callers ignore the value today (`main.py:955` etc.), but any future analytics would count phantom impressions. The truthful signal is the `on_open` event (`flet_ads/base_ad.py:44`; fired at `interstitial.dart:28` when the ad actually goes full-screen) — currently unused. **Fix:** either return an honest enum/outcome, or wire `on_open`.

### N7 — MEDIUM — The Android ad unit is used on iOS (`:53-54`, `:76-80`)
`interstitial_id` returns `INTERSTITIAL_ID_ANDROID_PROD` for **every** mobile platform, and `USE_TEST_IDS` returns the Android *test* unit for iOS as well. flet-ads ships a distinct iOS test unit (`flet_ads/interstitial_ad.py:21-22`; Dart default `…/4411468910` at `interstitial.dart:22`), and AdMob ad units are per-platform → on iOS the request never fills (silent zero revenue). The constant names say "ANDROID" but are used for iOS. **Fix:** select the unit by `page.platform` (iOS vs Android), with iOS test/prod ids.

### N8 — LOW-MEDIUM — `close()` never releases the ConsentManager (`:305-314`)
`close()` releases the two interstitial slots but leaves `self._consent_manager` in `page.services` (`:104-105`) and in the registry → the native UMP service outlives the teardown, and `self._consent_manager` still points at it, so a late `show_privacy_options()` (`:144-171`) would try to drive a disposed service. `close()` should also drop the manager and null the attribute. (Same leak if `gather_consent()` is ever called twice: `:101` overwrites the attribute while the first manager stays in `page.services`.)

### N9 — LOW-MEDIUM — `_release_service` removes by equality, flet removes by identity (`:317-323`)
`services.remove(item)` removes the **first element that compares equal**. `flet_ads` controls are dataclasses, so `==` compares fields; today the per-instance lambdas (`:190`, `:286`) keep two ads unequal, but `on_close=self._handle_close` is a *bound method* — bound methods of the same `AdService` compare **equal**. Two ads with the same `unit_id` and a shared handler can therefore compare equal, which would make `ad not in self.page.services` (`:201`, `:295`) report "already registered" (no keep-alive for the new ad) and `remove()` drop the **wrong** ad (possibly the one on screen). flet's own registry uses identity (`page.py:148`). **Fix:** identity-based removal.

### N10 — LOW — Dead code / stale comments
* `:3` — "verified against flet 0.86.5 source"; the installed flet is **1.0.4**, and the central mechanism changed: `page.services` is now the **View's own list** (`base_page.py:821-832` → `core/view.py:144`), *not* the live registry `page._services` (`page.py:714`). The keep-alive still works — but only as an extra strong reference feeding the `sys.getrefcount > 3` proxy (`page.py:228-247`) — not because the list *is* the registry, as `:13-17` claims. Additionally the service is registered with the client by `Service.__post_init__` (`services/service.py:42-58`) at **construction**, so `:201-202` / `:295-296` do not "register" anything.
* `:200-208` and `:294-301` — the `try/except` around `self.page.services.append(...)` cannot fire (a plain list append does not raise); the genuine failure path is the constructor's registration, which is already caught at `:196-198` / `:290-292`.
* `:69`, `:113` — `_privacy_options_required` is written and never read.
* `:133-171` — `show_privacy_options` is a public API with **no callers** anywhere in `src/`.
* `:230-231` — comment contradicts the code (see §3.3).
* `:312-314` — `clear_banner_pool()` clears a **process-wide** pool; in an embedded/multi-session deployment one session's teardown wipes another session's banners.

### N11 — LOW — `preload_interstitial` overwrites the callback even when it bails out (`:177` vs `:178-186`)
`self._on_close = on_close` runs **before** the guards, so a call with `on_close=None` (e.g. `main.py:526`) wipes a callback set earlier, and a *skipped* preload still overwrites the stored callback. Move the assignment after the guards.

### N12 — LOW — `await` inside `finally` (`:261-263`)
If `preload_interstitial` ever raises, the exception replaces the pending `return True` (`:252`) or the in-flight exception. The restock is well-guarded today, but it should not live in a `finally` that can override control flow.

### N13 — LOW — Consent failure defaults to "allow ads" (`:127-131`)
If UMP fails (network error, `FletUnsupportedPlatformException`, service error), the app proceeds to request ads with **no consent decision**. Google's UMP guidance is to treat "consent unknown" as "do not request ads yet". The exception is also broad enough to swallow platform errors that should be fatal for this path.

---

## 5) Small correctness improvements (no redesign)

1. **`:211-219`** — release `e.control` (identity) in `_handle_close`, not `self._shown_interstitial`; keep the attribute only as a fallback when it *is* the same object.
2. **`:274-282`** — bind the failing ad in a closure and release *that* instance; also distinguish a load failure from a show failure (the Dart side fires the same `"error"` event for both, `interstitial.dart:30-33` vs `:47`).
3. **`:188-195`** — the preload's `on_error` should release the failed ad and clear `self.interstitial` (N5).
4. **`:67`** — `_can_request_ads = False` by default; set True only after `can_request_ads()` returns True (N3).
5. **`:82-86`** — separate "platform unknown" (`page.platform is None`) from "not mobile" (N4).
6. **`:317-323`** — identity-based removal (mirroring `page.py:148`) instead of `list.remove` (N9).
7. **`:200-208`, `:294-301`** — drop the unreachable `try/except` around `page.services.append`, or reword it as "keep-alive reference" (N10).
8. **`:3`, `:13-17`** — update the module docstring: flet 1.0.4, `page.services` = `View.services` keep-alive list, registration happens in `Service.__post_init__`, GC rule = `getrefcount > 3` (py≥3.14).
9. **`:230-231`** — fix the comment (the code does *not* record the intent on a skip) — either fix the comment or the code.
10. **`:221-229`** — add the `_is_shutting_down` guard that `preload_interstitial` already has (N2).
11. **`:305-314`** — release the consent manager, null it, and log per-item failures (so `main.py:2426-2428`'s `contextlib.suppress` no longer hides them, per the policy at `:19-20`).
12. **`:76-80`** — platform-specific ad-unit selection (iOS vs Android), including the iOS test unit from `flet_ads/interstitial_ad.py:21-22`.
13. **`:177`** — assign `self._on_close` after the guards.
14. **`:303`** — return an honest outcome (e.g. `"shown"` / `"queued"` / `"skipped:<reason>"`), optionally grounded in the unused `on_open` event (`base_ad.py:44`).
15. **`:261-263`** — move the restock out of `finally` into an explicit tail so it cannot override the return/exception.

---

## 6) Verdict

**API correctness: clean.** Every `flet_ads` / `flet` symbol used by this file exists in the installed 1.0.4 packages with the expected signature — including the consent method names, `PrivacyOptionsRequirementStatus.REQUIRED`, the `unit_id`/`on_load`/`on_error`/`on_close` fields, and async event-handler support. There are **no hallucinated APIs**, and the documented consent ordering is exactly right. (One trap to remember: `on_paid` exists only on `BannerAd`, not on `InterstitialAd`.)

**Lifecycle correctness: not safe as written.** The file's design assumes several independent `InterstitialAd` instances can coexist (preload + shown + restock). The installed Flutter extension has **one static slot** (`flutter/flet_ads/lib/src/interstitial.dart:10`) and disposes that slot from *any* service teardown (`:49`, `:66-68`). Consequently:

* the restock at `:261-263` (KNOWN #1) is the trigger for every downstream failure — a failed preload load disposes the ad on screen, and releasing the spent ad disposes the fresh preload;
* the release paths (`:213`, `:281`, `:309`) act on `self._shown_interstitial` rather than on the instance that actually failed/closed (KNOWN #2 + N1), which both releases the wrong ad and leaks the right one;
* the keep-alive bookkeeping (`:104-105`, `:201-202`, `:295-296`, `:317-323`) is built on a list that is **not** the registry in flet 1.0.4, so it survives only via a refcount proxy and its removal is equality-based rather than identity-based.

**Policy/UX gaps:** the UMP privacy-options entry point required in regulated regions is implemented (`:133-171`) but **never reachable from the UI** (KNOWN #5), `_privacy_options_required` is dead state, and `_can_request_ads` defaults to `True` (N3) so an ad can be requested before any consent decision exists. On desktop the module is a correct no-op (KNOWN #4), but the same guard can disable ads for an entire *mobile* session when the platform has not been reported yet (N4).

**Recommended minimum before shipping (frozen-ads-compatible, no redesign):**
1. Treat **one `InterstitialAd` at a time** as the invariant: do not restock while one is shown (`:261-263`), and release by instance identity (`:213`, `:281`, `:317-323`).
2. Default `_can_request_ads` to `False` and enable it only on a confirmed `can_request_ads()`.
3. Distinguish "platform unknown" from "not mobile".
4. Log inside `close()` so `main.py:2426-2428` cannot hide teardown failures.
5. Wire the privacy-options entry point into Settings (or delete `show_privacy_options` + `_privacy_options_required` and document the omission).
6. Pick the ad unit per platform (Android/iOS).

**Risk rating:** HIGH for the interstitial lifecycle (revenue + possible visible-ad disposal), MEDIUM-HIGH for the pre-consent request path (policy), MEDIUM for the platform-unknown path (silent revenue loss), LOW for everything else.
