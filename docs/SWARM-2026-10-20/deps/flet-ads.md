# flet-ads dependency audit — Sherlock-V3

**Date:** 2026-10-20
**Scope:** installed `flet-ads` 1.0.4 (Python + bundled Flutter/Dart extension) vs. the app's ad wiring.
**Method:** the venv is the only source of truth. Every claim below is cited to the installed package or to the app source. No API is inferred from training data.

**Path legend (all absolute):**

| Alias | Path |
|---|---|
| `PKG` | `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet_ads` |
| `DART` | `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flutter/flet_ads/lib` |
| `FLET` | `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet` |
| `APP` | `/home/maikel/.zcode/workspace/default/Sherlock-V3` |

**Environment confirmed:** `flet` 1.0.4, `flet_ads` 1.0.4, Python **3.14.7** (`.venv\Scripts\python.exe -V`). This matters: flet's service-GC threshold is Python-version dependent (`FLET\controls\page.py:238`).

**Owner rule honoured:** the ad subsystem is intentionally "untouched". Nothing below proposes redesigning ads, restructuring the ad service, or changing the ad UX. Only correctness / robustness findings, plus small, local fixes.

---

## 1) Installed-package verification

### 1.1 Package layout

`PKG` contains exactly seven Python modules:

- `PKG\__init__.py` (29 lines)
- `PKG\base_ad.py` (75)
- `PKG\banner_ad.py` (41)
- `PKG\consent_manager.py` (136)
- `PKG\interstitial_ad.py` (36)
- `PKG\native_ad.py` (33)
- `PKG\types.py` (265)

The bundled Flutter extension is a separate Dart package at `DART`: `flet_ads.dart`, `src/extension.dart`, `src/banner.dart`, `src/interstitial.dart`, `src/consent_manager.dart`, `src/native.dart`, `utils/ads.dart`, `utils/consent.dart`, `utils/native.dart` (`pubspec.yaml` pins `google_mobile_ads: ^9.0.0`).

### 1.2 `__all__` — exact exports

`PKG\__init__.py:16-29` declares exactly **12** names:

```
AdRequest, BannerAd, BaseAd, ConsentDebugSettings, ConsentManager,
ConsentRequestParameters, ConsentStatus, DebugGeography, InterstitialAd,
PaidAdEvent, PrecisionType, PrivacyOptionsRequirementStatus
```

`PKG\__init__.py:1-14` imports only `BannerAd`, `BaseAd`, `ConsentManager`, `InterstitialAd` plus the nine type names.

**`NativeAd` exists but is NOT exported.** `PKG\native_ad.py:8-9` defines `class NativeAd(BannerAd)` and `PKG\native_ad.py:5` sets `__all__ = ["NativeAd"]` for that module only. Verified at runtime:

```
from flet_ads import NativeAd
-> ImportError: cannot import name 'NativeAd' from 'flet_ads'
```

Worse, the Dart side has the widget case commented out (`DART\src\extension.dart:34-37`), so `createWidget` returns `null` for `"NativeAd"` — even if imported directly it would render nothing. **`NativeAd` is non-functional in this build.** The app does not use it. Do not reach for it.

### 1.3 `BaseAd` — `PKG\base_ad.py`

- `@dataclass(kw_only=True)` subclass of `ft.BaseControl` (`base_ad.py:8-9`).
- Fields (`base_ad.py:21-67`): `unit_id: str` (**required, no default** — must be passed as a keyword), `request: AdRequest` (default factory `AdRequest()`), and event handlers `on_load`, `on_error`, `on_open`, `on_close`, `on_impression`, `on_click`, all typed `ft.ControlEventHandler[...]`.
- **Mobile-only guard:** `base_ad.py:69-75`

  ```python
  def before_update(self):
      super().before_update()
      if self.page.web or not self.page.platform.is_mobile():
          raise ft.FletUnsupportedPlatformException(...)
  ```

  `Page.web` exists (`FLET\controls\page.py:516`); `PagePlatform.is_mobile()` is `IOS | ANDROID` (`FLET\controls\types.py:843-849`).
- **MRO check (runtime-verified):** `BannerAd.before_update` → `BaseAd.before_update`; `InterstitialAd.before_update` → `BaseAd.before_update`. Neither `LayoutControl` nor `Control` defines `before_update` (only `FLET\controls\base_control.py:344` in the core), so the guard is **live** for both ad classes.
- The guard fires in `before_update` (page-update time), **not** at construction. A control constructed on desktop does not raise until it is mounted into the tree.

### 1.4 `BannerAd` — `PKG\banner_ad.py`

- `@ft.control("BannerAd")`, `class BannerAd(ft.LayoutControl, BaseAd)` (`banner_ad.py:8-9`).
- Adds `on_will_dismiss` (`banner_ad.py:28-34`, iOS only) and `on_paid: Optional[ft.ControlEventHandler[PaidAdEvent["BannerAd"]]]` (`banner_ad.py:36-40`).
- Runtime field list confirms `width`, `height` (inherited `LayoutControl`) and `on_will_dismiss`, `on_paid` are real fields → the app's `width=320, height=50` is valid.
- Documented AdMob **test** ids (`banner_ad.py:13-21`): Android `ca-app-pub-3940256099942544/9214589741`, iOS `ca-app-pub-3940256099942544/2435281174`.

### 1.5 `InterstitialAd` — `PKG\interstitial_ad.py`

- `@ft.control("InterstitialAd")`, `class InterstitialAd(ft.Service, BaseAd)` (`interstitial_ad.py:5-6`).
- **Exactly one public method:** `async def show(self)` → `await self._invoke_method("show")` (`interstitial_ad.py:30-36`).
- One-shot contract stated in the docstring (`interstitial_ad.py:10-13`): *"Each instance is allowed to be shown (using show) only once."*
- Because it is an `ft.Service`, it auto-registers with the page (see §1.8).

### 1.6 `ConsentManager` — `PKG\consent_manager.py`

- `@ft.control("ConsentManager")`, `class ConsentManager(ft.Service)` (`consent_manager.py:13-14`). **Not** a `BaseAd` → **no `unit_id`**; runtime field list confirms only base control fields.
- Own mobile-only guard at `consent_manager.py:36-42` (same `FletUnsupportedPlatformException`).
- The complete async API, exact names and arities (`consent_manager.py:44-136`):

  | Method | Line | Returns |
  |---|---|---|
  | `request_consent_info_update(params: Optional[ConsentRequestParameters] = None)` | 44 | `None` |
  | `is_consent_form_available()` | 60 | `bool` |
  | `get_consent_status()` | 73 | `ConsentStatus` |
  | `can_request_ads()` | 85 | `bool` |
  | `get_privacy_options_requirement_status()` | 94 | `PrivacyOptionsRequirementStatus` |
  | `load_and_show_consent_form_if_required()` | 108 | `None` |
  | `show_privacy_options_form()` | 118 | `None` |
  | `reset()` | 128 | `None` (testing only, per docstring 132-135) |

- The documented 3-step flow is explicit (`consent_manager.py:23-27`): `request_consent_info_update` → `load_and_show_consent_form_if_required` → `can_request_ads`. The app follows exactly this order.
- Dart side method names match 1:1 (`DART\src\consent_manager.dart:19-84`).
- `request_consent_info_update()` with no args is safe: Python sends `{"params": None}` (`consent_manager.py:58`), Dart receives `args?["params"] == null` and `parseConsentRequestParameters(null)` returns a default instance (`DART\utils\consent.dart:18-19`). **No null-crash.**

### 1.7 Types — `PKG\types.py`

| Type | Lines | Notes |
|---|---|---|
| `PrecisionType` | 23-36 | `UNKNOWN/ESTIMATED/PUBLISHER_PROVIDED/PRECISE` = `"unknown"/"estimated"/"publisherProvided"/"precise"` |
| `PaidAdEvent(ft.Event[ft.EventControlType])` | 39-58 | `value: float`, `precision: PrecisionType`, `currency_code: str` |
| `AdRequest` (`@ft.value`) | 61-105 | `keywords`, `content_url`, `neighboring_content_urls`, `non_personalized_ads`, `http_timeout` (Android only), `extras` |
| `ConsentStatus` | 139-168 | `NOT_REQUIRED/OBTAINED/REQUIRED/UNKNOWN` |
| `PrivacyOptionsRequirementStatus` | 171-193 | `NOT_REQUIRED/REQUIRED/UNKNOWN` |
| `DebugGeography` | 196-215 | `DISABLED/EEA/REGULATED_US_STATE/OTHER` |
| `ConsentDebugSettings` (`@ft.value`) | 218-242 | `debug_geography`, `test_identifiers` |
| `ConsentRequestParameters` (`@ft.value`) | 245-265 | `tag_for_under_age_of_consent`, `consent_debug_settings` |

- `PaidAdEvent.precision` conversion is consistent with Dart: the extension sends `precision.name` (`DART\src\banner.dart:62-68`), and google_mobile_ads' `PrecisionType` names match flet_ads' enum values.
- **Units caveat:** Dart sends `valueMicros` (`DART\src\banner.dart:62-63`) but `PKG\types.py:45-47` documents `value` as "The monetary value of the ad" — the value is in **micros**. A trap for whoever wires `on_paid` (the app does not).
- `AdRequest` is always serialized (default instance), and `parseAdRequest` (`DART\utils\ads.dart:3-13`) tolerates the all-null dict. It would only break if `keywords` were populated: `value["keywords"]` decodes to `List<dynamic>`, which Dart rejects against `List<String>?`. The app never sets `request`.

### 1.8 flet 1.0.4 service GC semantics (keep-alive verification)

Verified directly against the installed flet source:

- `FLET\controls\services\service.py:11-54` — `Service` is a dataclass with `_auto_register: ClassVar[bool] = True` (line 32). `__post_init__` (39-54) calls `super().__post_init__(ref)` and then, **if `context.page` resolves**, `page._services.register_service(self)` (line 54). A `RuntimeError` from `context.page` means "no page context" → constructed but **not** registered (lines 50-53).
- `FLET\controls\page.py:120-152` — `ServiceRegistry.register_service` appends to `ServiceRegistry._services` (line 139) and pushes an update.
- `FLET\controls\page.py:228-247` — `unregister_services()` keeps only services with `sys.getrefcount(service) > min_refs`, where `min_refs = 3 if sys.version_info >= (3, 14) else 4` (**line 238**). Services that fail the test are dropped from the registry (239-243) and the tree is patched (244-247).
- `FLET\messaging\session.py:554-570` — `after_event()` calls `self.page._services.unregister_services()` **after every UI event** (line 570).
- `FLET\controls\base_page.py:821-832` — `page.services` is `self.__root_view().services` → `views[0].services`; the field is `FLET\controls\core\view.py:144` with `metadata={"skip": True}` → Python-side keep-alive only, never serialized.

**Conclusion: the app's `page.services.append(...)` keep-alive is both necessary and correct.**

- Reference count for an `InterstitialAd` held by `AdService`: registry list (1) + `page.services` list (1) + `AdService.interstitial` attribute (1) + `sys.getrefcount`'s own temporary (1) = 4 → `4 > 3` → survives on Python 3.14.7.
- Without the `page.services` append the count is 3 → `3 > 3` is **False** → the service would be unregistered on the very next event. The append is load-bearing, not decorative.
- `page.render()` (`FLET\controls\page.py:750-773`) assigns `self.views[0].controls = ...` — it does **not** replace `page.views` nor the `View` object, so `page.services` keeps the same list identity for the whole session. The app never reassigns `page.views` either (it only mutates `page.views[0].appbar` / `.navigation_bar`, `APP\src\app_shell.py:766-820`). ⇒ the keep-alive list survives re-renders and theme changes.
- `FLET\controls\page.py:929-964` — `run_task` sets `_context_page.set(self)` (line 939) and **requires a coroutine function** (`TypeError` otherwise, lines 940-941). `FLET\controls\base_control.py:502` also sets the page context when dispatching events, and `FLET\messaging\session.py:171,451` set it in the session loops — which is why `flet.context.page` is available during component renders (needed by `build_banner_ad()` when called without a page).

### 1.9 Naming / deprecation check for everything the app uses

| App usage | Installed truth | Verdict |
|---|---|---|
| `fta.BannerAd(unit_id=..., width=, height=, on_load=, on_error=)` | `unit_id` (`base_ad.py:21`), `width`/`height` (LayoutControl), `on_load`/`on_error` (`base_ad.py:31,36`) | correct names, no deprecation |
| `fta.InterstitialAd(unit_id=, on_load=, on_error=, on_close=)` | `base_ad.py:21,31,36,53` | correct |
| `await ad.show()` | `interstitial_ad.py:30-36` | correct coroutine |
| `fta.ConsentManager()` | `consent_manager.py:13-14` | correct |
| `request_consent_info_update()` / `load_and_show_consent_form_if_required()` / `can_request_ads()` | `consent_manager.py:44 / 108 / 85` | correct names & order |
| `get_privacy_options_requirement_status()` / `show_privacy_options_form()` | `consent_manager.py:94 / 118` | correct |
| `fta.PrivacyOptionsRequirementStatus.REQUIRED` | `types.py:186` | correct |
| `fta.BannerAd.on_paid` / `fta.PaidAdEvent` | `banner_ad.py:36`, `types.py:39-58` | correct (unused by app) |

**Nothing the app uses is misnamed or deprecated.**

### 1.10 Dart extension details that constrain the app

- `DART\src\extension.dart:11-15` — `ensureInitialized()` calls `MobileAds.instance.initialize()` **only** when `isMobilePlatform()`. Desktop is a no-op at the SDK level.
- `DART\src\extension.dart:18-27` — `createService` handles `"InterstitialAd"` and `"ConsentManager"`; `createWidget` (30-41) handles `"BannerAd"`; `"NativeAd"` is commented out (34-37).
- `DART\src\banner.dart:33-47` — event names emitted: `load`, `error`, `open`, `close`, `click`, `will_dismiss`, `paid`, `impression`. These map exactly onto the app's handler names.
- `DART\src\banner.dart:78` — `bannerAd.load()` is invoked on the first build ⇒ **every new `BannerAd` control instance is one AdMob request**.
- `DART\src\banner.dart:23-25` — fallback unit id if `unit_id` is missing: iOS `.../4411468910`, Android `.../1033173712`. The Android value is the **interstitial** test id, not the banner test id documented at `PKG\banner_ad.py:18`. Unreachable in this app (the app always passes `unit_id`), but an upstream copy/paste bug.
- `DART\src\interstitial.dart:10` — **`static InterstitialAd? _interstitialAd;`** — a *single static slot* shared by every `InterstitialAd` service. Overwritten on each load (line 44), disposed by whichever service is torn down (lines 49, 66-69).
- `DART\src\interstitial.dart:54-63` — `_invokeMethod("show")` does `_interstitialAd?.show(); return null;` ⇒ **`show()` resolves at presentation time, not at dismissal.**

---

## 2) Correctness of app wiring

App files audited: `APP\src\services\ad_service.py`, `APP\src\components\banner_ad.py`, `APP\src\main.py`, `APP\src\app_shell.py`, `APP\src\screens\{home,results,history,sites,settings}_screen.py`, `APP\src\components\app_header.py`, `APP\src\core\constants.py`.

### 2.1 Unit IDs

- Banner: `APP\src\core\constants.py:86` → `AD_BANNER_UNIT_ID = "ca-app-pub-5679949845754640/5131365762"`, passed as `unit_id=` at `APP\src\components\banner_ad.py:97`. Format `ca-app-pub-<publisher>/<unit>` is well-formed. ✔
- Interstitial: `APP\src\services\ad_service.py:54` → `INTERSTITIAL_ID_ANDROID_PROD = "ca-app-pub-5679949845754640/2758003779"` (same publisher id as the banner — plausible pairing). ✔
- Test id: `APP\src\services\ad_service.py:53` → `ca-app-pub-3940256099942544/1033173712`, which matches Google's documented Android **interstitial** test id (`PKG\interstitial_ad.py:20`). ✔
- `USE_TEST_IDS = False` (`ad_service.py:51`) ⇒ shipped builds use the production ids. ✔
- ⚠ **Only Android-shaped ids exist.** `ad_service.py:76-80` (`interstitial_id`) and `core\constants.py:86` have no iOS variant, although the extension distinguishes platforms (`DART\src\banner.dart:23-25`, `DART\src\interstitial.dart:21-23`). AdMob unit ids are per-platform, so on iOS the app sends an Android unit id → no fill (not a crash). See §3, issue 3.

### 2.2 Banner pooling

- Pool implementation: `APP\src\components\banner_ad.py:41` (`_BANNER_POOL`), `:44-54` (`pooled_banner_ad`), `:57-65` (`clear_banner_pool`).
- Pooled slots: `home_screen.py:1375` ("home-1"), `home_screen.py:1408` ("home-2"), `history_screen.py:470` ("history-1"), `results_screen.py:340-343` (`results-{ordinal}`), `sites_screen.py:770` (`sites-list-{slot}`; `_BANNER_EVERY = 10`, `_BANNER_MAX = 15` at `sites_screen.py:78-79` ⇒ ≤ 15 banners in the sites list).
- ✔ The pool returns the *same* control instance per slot, so a re-render does not re-request an ad. This is the intended behaviour and it works: flet patches by control uid, and the instance keeps its `_i`.
- ✔ Pool invalidation on theme change: `settings_screen.py:319-324` and `app_header.py:135-139` both call `clear_banner_pool()`; on teardown: `ad_service.py:314`.
- ✘ **Four call sites bypass the pool** — `results_screen.py:1031`, `settings_screen.py:1760`, `:1771`, `:1776` call `build_banner_ad()` directly. See §3, issue 1 (the most serious finding).
- ⚠ The pool caches fallback containers — see §3, issue 4.
- ✔ The pool is module-global, but the app is single-page and `ad_service.close()` clears it on `page.on_close` (`main.py:2422-2428` → `ad_service.py:305-314`), so no cross-page leakage of stale controls.

### 2.3 Interstitial one-shot contract

- ✔ The app honours the contract (`PKG\interstitial_ad.py:10-13`): the preloaded instance is consumed exactly once (`ad_service.py:243-245` sets `self.interstitial = None` before showing), and the fallback path always constructs a brand-new instance (`ad_service.py:284-289`).
- ✔ Release on close: `on_close=self._handle_close` (`ad_service.py:194`, `:288`) → `_handle_close` (`ad_service.py:211-219`) drops `_shown_interstitial` and removes it from `page.services`, then invokes the caller's `on_close` (awaiting it when it is a coroutine function — `asyncio.iscoroutinefunction` check at `:216-219`).
- ⚠ But the Dart extension has a stricter, *shared* one-shot: `DART\src\interstitial.dart:10` is a **static** slot for all instances. See §3, issue 2.

### 2.4 Consent flow ordering

- `APP\src\services\ad_service.py:90-131` (`gather_consent`):
  `request_consent_info_update()` (`:106`) → `load_and_show_consent_form_if_required()` (`:107`) → `can_request_ads()` (`:108`) → `get_privacy_options_requirement_status()` (`:110-115`).
  ✔ This is exactly the documented UMP order (`PKG\consent_manager.py:23-27`) and matches the Dart implementations (`DART\src\consent_manager.dart:22-63`).
- ✔ `show_privacy_options` (`ad_service.py:133-171`) re-checks the requirement status before showing the form (`:150-160`) and re-reads `can_request_ads` afterwards (`:163`) — matches `PKG\consent_manager.py:118-126`.
- ✔ The consent manager is created once and kept alive for the app lifetime (`ad_service.py:101-105`); it is deliberately never released in `close()` (`ad_service.py:305-314`), which is right — it must outlive individual ads.
- ✔ On a privacy-status probe failure the app degrades gracefully and keeps the ad gate as-is (`ad_service.py:121-122`).

### 2.5 Rate limiting

- `INTERSTITIAL_MIN_INTERVAL_SEC = 30.0` (`ad_service.py:60`).
- ✔ `_last_interstitial_at` is initialised to `None`, not `0.0` (`ad_service.py:71-74`) — the in-code rationale (monotonic clock can be small right after boot) is correct.
- ✔ The guard (`ad_service.py:232-241`) computes `time.monotonic() - last` and skips below the threshold.
- ✔ The timestamp is stamped at *trigger* time (`:242`) before any show attempt, so a burst of triggers cannot queue a show the instant the window opens — matching the stated intent (`:230-231`).
- ⚠ Minor: the stamp is set even when the subsequent show fails, so a failed attempt still consumes the 30 s window. Acceptable, but worth knowing.

### 2.6 Teardown

- `close()` (`ad_service.py:305-314`): sets `_is_shutting_down = True`, releases both `self.interstitial` and `self._shown_interstitial` from `page.services`, nulls them, and clears the banner pool.
- ✔ `_release_service` (`ad_service.py:317-323`) removes from the list and swallows only `ValueError` (already gone) — safe against a torn-down page.
- ✔ Wired to `page.on_close` at `APP\src\main.py:2422-2439`.
- ✔ `_is_shutting_down` correctly suppresses the `finally`-block preload (`ad_service.py:262`) so teardown does not create a new ad.
- ⚠ The teardown call sits inside `contextlib.suppress(Exception)` (`main.py:2426-2428`), which contradicts the module's own policy statement ("we log every error, we never swallow", `ad_service.py:19-20`). See §3, issue 8.

### 2.7 Desktop no-op guard (developer runs on Windows desktop)

- `AdService._is_mobile()` (`ad_service.py:82-86`) → `page.platform.is_mobile()`, with a defensive `except Exception → False`.
- ✔ `gather_consent` returns before constructing anything on non-mobile (`ad_service.py:96-99`).
- ✔ `preload_interstitial` returns before constructing anything (`ad_service.py:181-183`).
- ✔ `show_interstitial` returns `False` (`ad_service.py:225-229`).
- ✔ `build_banner_ad` returns a zero-size `ft.Container` on non-mobile and **never constructs `fta.BannerAd`** (`banner_ad.py:84-91`).
- ⇒ On Windows desktop **no `BannerAd`, `InterstitialAd` or `ConsentManager` is ever constructed**, so `BaseAd.before_update` (`PKG\base_ad.py:71-75`) and `ConsentManager.before_update` (`PKG\consent_manager.py:38-42`) can never raise `ft.FletUnsupportedPlatformException`, and `DART\src\extension.dart:11-15` never initializes the Google Mobile Ads SDK. **No crash on desktop.**
- ⚠ Informational: `gather_consent` sets `_can_request_ads = True` on non-mobile (`ad_service.py:96-99`), which reads as "consent granted" on a platform where UMP does not exist. Harmless today because every ad path re-checks `_is_mobile()`.

### 2.8 Exception handling around awaits

| Await | Guard | Verdict |
|---|---|---|
| `request_consent_info_update()` (`ad_service.py:106`) | outer try/except (`:100-131`) | ✔ |
| `load_and_show_consent_form_if_required()` (`:107`) | same | ✔ |
| `can_request_ads()` (`:108`) | same | ✔ |
| `get_privacy_options_requirement_status()` (`:111`) | nested try/except (`:109-122`) | ✔ |
| `show_privacy_options_form()` (`:162`) | try/except (`:161-171`) | ✔ |
| `can_request_ads()` after the form (`:163`) | same | ✔ |
| `await ad_to_show.show()` (`:250`) | try/except Exception (`:249-260`) | ✔ |
| `fta.InterstitialAd(...)` construction (`:188`, `:284`) | try/except (`:187-198`, `:268-292`) | ✔ |
| `page.services.append(...)` (`:201-202`, `:295-296`) | try/except (`:200-208`, `:294-301`) | ✔ |
| `await self.preload_interstitial(...)` in `finally` (`:263`) | `preload_interstitial` contains no `await` of its own, and has its own internal guards | ✔ |
| `e.control.show()` inside `_show` (`ad_service.py:271`) | reached via `page.run_task` → flet does not await a sync handler's return value (`FLET\controls\base_control.py:514-516`) | ⚠ see §3, issue 9 |

- ✔ Callers also guard: `main.py:953-963`, `main.py:1515-1525`, `main.py:1761-1768`, `app_shell.py:452-459` each wrap `await ad_service.show_interstitial()` in `try/except Exception` and separately re-raise `asyncio.CancelledError` (correct — `except Exception` does not catch `CancelledError` on Python 3.8+).

### 2.9 Platform gating (`ft.FletUnsupportedPlatformException`)

- The exception exists at `FLET\controls\exceptions.py:21-24` (`FletUnsupportedPlatformException(FletException)`).
- It is raised only from `before_update`, i.e. during a page update, never at construction. The app never constructs an ad control on a non-mobile platform (§2.7), so it is never raised.
- The app does not import or catch it anywhere. Safe today, but a future ad-construction site outside `build_banner_ad` / `AdService` would fail loudly during the render instead of degrading. Informational only (§3, issue 11).

### 2.10 Summary of what is correct

- Consent flow order, method names, and arities: correct.
- `unit_id` parameter name, `on_load`/`on_error`/`on_close` handler names, `await show()`: correct, nothing deprecated.
- Service keep-alive via `page.services.append(...)`: **necessary and correct** for flet 1.0.4 on Python 3.14.7 (§1.8).
- Interstitial one-shot contract at the Python level: correct.
- Rate limiting: correct, with a sane non-zero sentinel.
- Desktop no-op: complete — nothing is constructed, nothing crashes.
- Teardown: releases services, clears the banner pool, suppresses the shutdown preload.
- Every await around the ad APIs is inside a `try/except`.

---

## 3) Bugs & issues (severity)

### Issue 1 — HIGH — Unpooled banners re-request an ad on every render

`APP\src\screens\results_screen.py:1031`, `APP\src\screens\settings_screen.py:1760`, `APP\src\screens\settings_screen.py:1771`, `APP\src\screens\settings_screen.py:1776` call `build_banner_ad()` directly instead of `pooled_banner_ad(<slot>)`.

- Every such call constructs a **new** `fta.BannerAd`, and every new `BannerAd` control is one AdMob request (`DART\src\banner.dart:78` → `bannerAd.load()`).
- The Results screen re-renders at ~2 Hz during a scan — the module's own comment at `results_screen.py:337-339` says exactly this ("the 2Hz progress ticks never re-request an ad (a fresh BannerAd per tick would burn requests and flash the slot)"), yet the bottom banner at `results_screen.py:1031` is *not* pooled and therefore violates that rule.
- Settings builds **three** fresh banners per render (`:1760`, `:1771`, `:1776`).
- This directly contradicts the contract stated in `APP\src\components\banner_ad.py:36-40` ("A fresh BannerAd per render throws away a live ad (resetting AdMob's own refresh cycle) and flashes the slot, so callers request from this pool by slot key instead of building new controls").
- AdMob policy impact: repeated requests for the same banner unit are a standard invalid-traffic signal.

### Issue 2 — MEDIUM — Overlapping `InterstitialAd` services fight over the extension's single static ad slot

- The extension stores the loaded ad in a **static** field: `DART\src\interstitial.dart:10` (`static InterstitialAd? _interstitialAd;`), overwritten on every load (`:44`), disposed by whichever service is torn down (`:49` `onAdFailedToLoad` → `_interstitialAd?.dispose()`, and `:66-69` `dispose()`).
- `show()` resolves at **presentation** time, not dismissal: `DART\src\interstitial.dart:57-59` → `_interstitialAd?.show(); return null;`.
- Therefore in `APP\src\services\ad_service.py:249-263`, `await ad_to_show.show()` returns while the ad is still full-screen, and the `finally` block immediately calls `preload_interstitial()` → `ad_service.py:188` constructs a **second** `InterstitialAd` control, whose Dart `init()` (`DART\src\interstitial.dart:13-52`) starts another `InterstitialAd.load(...)`.
- Consequences: (a) the static slot can end up pointing at the second, not-yet-loaded ad, so a later `show()` shows nothing (or shows an already-disposed ad → Flutter's "InterstitialAd was used after being disposed" assertion); (b) `dispose()` of either service disposes whichever ad happens to be in the static slot, which may belong to the *other* instance; (c) two `InterstitialAd.load()` calls can be in flight simultaneously.
- The app cannot see the static; it only sees "shown (preloaded instance)" followed by a load error or a silent no-show.

### Issue 3 — MEDIUM — No platform-specific ad unit ids: iOS gets zero fill

`APP\src\core\constants.py:86` and `APP\src\services\ad_service.py:53-54, 76-80` hard-code Android-shaped unit ids. `interstitial_id` (`ad_service.py:76-80`) and `AD_BANNER_UNIT_ID` have no iOS branch, yet the extension itself distinguishes platforms (`DART\src\banner.dart:23-25`, `DART\src\interstitial.dart:21-23`) and flet_ads documents separate Android/iOS test ids (`PKG\banner_ad.py:18-19`, `PKG\interstitial_ad.py:20-21`). AdMob unit ids are per-platform, so the iOS build sends an Android id and receives no fill. Not a crash — a silent revenue loss on iOS.

### Issue 4 — MEDIUM/LOW — The banner pool caches the zero-size fallback

`APP\src\components\banner_ad.py:50-54` stores whatever `build_banner_ad` returns, including the `ft.Container(width=0, height=0)` fallbacks returned at `:82` (no page context), `:85` (no page/platform), `:89` (non-mobile), `:91` (platform probe raised) and `:107` (construction failed). If the first call for a slot happens while the page/platform is unresolvable, that slot is permanently a 0×0 container for the session — the ad silently never appears, and nothing logs it (the fallbacks are silent; only `:107` logs).

### Issue 5 — LOW — Wrong-ad release in the fresh-instance error handler

`APP\src\services\ad_service.py:274-282`: the fresh path's `_on_error` releases `self._shown_interstitial`, which may be holding a *different* instance (e.g. the preloaded ad) rather than the one that failed to load. The released object is still "an ad the app wants to release" in most flows, so the impact is small, but the ownership is wrong.

### Issue 6 — LOW — Extension fallback banner unit id is an interstitial id

`DART\src\banner.dart:23-25` falls back to `ca-app-pub-3940256099942544/1033173712` (the Android **interstitial** test id) when `unit_id` is missing; the documented **banner** test id is `ca-app-pub-3940256099942544/9214589741` (`PKG\banner_ad.py:18`). Unreachable in this app (the app always passes `unit_id`), but it would serve an interstitial unit as a banner. Upstream defect — file an issue, do not patch the venv.

### Issue 7 — LOW — `PaidAdEvent.value` is in micros but documented as a plain value

Dart sends `valueMicros` (`DART\src\banner.dart:62-63`); `PKG\types.py:45-47` documents `value` as "The monetary value of the ad". The app does not consume `on_paid` today, so there is no live impact, but the units are off by 1e6 for whoever wires it up.

### Issue 8 — LOW — Ad teardown exceptions are swallowed, against the module's stated policy

`APP\src\main.py:2426-2428` wraps `await controller.ad_service.close()` in `contextlib.suppress(Exception)`, while `APP\src\services\ad_service.py:19-20` states the project policy: "No silent failures: every gate, error, and skip reason is logged (project policy — we log every error, we never swallow)". The ad teardown path is the one place that violates it.

### Issue 9 — LOW — Errors raised inside the fresh-interstitial `on_load` bypass the app's logging

`APP\src\services\ad_service.py:286` uses `on_load=lambda e: self.page.run_task(_show, e)`. The handler is a plain lambda, so flet takes the sync branch and does **not** await the returned future (`FLET\controls\base_control.py:514-516`). `run_task` schedules the coroutine and re-raises any exception inside a done-callback (`FLET\controls\page.py:947-962`), so a failure in `_show` (e.g. `e.control.show()` raising) reaches the event loop's default handler rather than the app's `except Exception` blocks and logs. No crash, but the "we log every error" policy is partially bypassed on this path.

### Issue 10 — INFO — `NativeAd` is unusable in this build

Not exported from `PKG\__init__.py` (`ImportError` verified at runtime) **and** the Dart widget case is commented out (`DART\src\extension.dart:34-37`). The app does not use it. Recorded so no one reaches for it.

### Issue 11 — INFO — No defensive handling of `ft.FletUnsupportedPlatformException`

The app never constructs an ad control off-mobile, so the exception (`FLET\controls\exceptions.py:21-24`) is unreachable today. A future construction site outside `build_banner_ad`/`AdService` would raise during the page update and break the whole screen render rather than degrade. Noted for awareness; no change recommended now (owner rule: ad subsystem untouched).

### Issue 12 — INFO — Two consent-flow behaviours worth knowing (not changed)

- `gather_consent` defaults to "ads allowed" when the UMP flow raises (`APP\src\services\ad_service.py:127-131`). Defensible for revenue, but in a regulated region it means ads are requested without a collected decision. Logged as a warning, so it is not silent.
- `gather_consent` sets `_can_request_ads = True` on non-mobile (`ad_service.py:96-99`), which reads as "consent granted" where UMP does not exist. Harmless (every ad path re-checks `_is_mobile()`).

### Issue 13 — INFO — Stale version reference in the module docstring

`APP\src\services\ad_service.py:3` says "verified against flet 0.86.5 source". The installed flet is **1.0.4** and the described behaviour does hold (`FLET\controls\page.py:228-247`, `FLET\messaging\session.py:570`) — but the docstring also states "drops any service whose refcount fell to <=3", which is only true on Python ≥ 3.14 (`FLET\controls\page.py:238`: `min_refs = 3` on ≥3.14, else 4). The venv is 3.14.7, so the app is correct today, but the docstring would be wrong on an older interpreter.

---

## 4) Small correctness improvements only (no redesign)

These are local, minimal, and preserve the existing ad design.

1. **Route the four unpooled banners through the pool** (fixes Issue 1). Add slot keys and call `pooled_banner_ad(...)` at `APP\src\screens\results_screen.py:1031`, `APP\src\screens\settings_screen.py:1760`, `:1771`, `:1776` — e.g. `"results-bottom"`, `"settings-1"`, `"settings-2"`, `"settings-3"`. This is the same mechanism the rest of the app already uses; no behaviour change other than not re-requesting ads. *(The site list already bounds its pool usage via `_BANNER_EVERY`/`_BANNER_MAX`, `sites_screen.py:78-79`.)*
2. **Do not cache the fallback container in the pool** (fixes Issue 4). In `pooled_banner_ad` (`APP\src\components\banner_ad.py:50-54`), only store the control when it is a real banner — e.g. have `build_banner_ad` signal "not a banner" (or check the control's type) and skip caching in that case, so a later render can still build a real ad.
3. **Give the fresh-instance error handler the right ad to release** (fixes Issue 5). In `APP\src\services\ad_service.py:274-282`, close over the specific `ad` instance and release that one instead of `self._shown_interstitial`.
4. **Await the fresh-interstitial `on_load` coroutine through flet's own async path** (fixes Issue 9). Change `on_load=lambda e: self.page.run_task(_show, e)` (`ad_service.py:286`) to an `async def` handler (`async def _on_load(e): await _show(e)`), which flet awaits directly (`FLET\controls\base_control.py:516-520`) so exceptions land in the app's logging.
5. **Log the ad-teardown outcome instead of suppressing it** (fixes Issue 8). Replace `contextlib.suppress(Exception)` around `await controller.ad_service.close()` (`APP\src\main.py:2426-2428`) with a `try/except Exception: logger.warning(...)` that matches the policy stated at `APP\src\services\ad_service.py:19-20`.
6. **Consider platform-specific unit ids** (fixes Issue 3). If iOS is a target, add an iOS constant/variant next to `AD_BANNER_UNIT_ID` (`APP\src\core\constants.py:86`) and an iOS branch in `interstitial_id` (`APP\src\services\ad_service.py:76-80`), mirroring what the extension already does for its own fallbacks. If iOS is *not* a target, this is a no-op — do not add a fake id.
7. **Update the module docstring's version references** (Issue 13). `APP\src\services\ad_service.py:3` should say flet 1.0.4, and the "refcount <= 3" sentence should mention that the threshold is `min_refs = 3` on Python ≥ 3.14 and 4 below (`FLET\controls\page.py:238`).
8. **Optional hardening for Issue 2.** The overlap in `APP\src\services\ad_service.py:261-263` is a consequence of the extension's static slot. A minimal, non-redesign mitigation is to defer the restock preload until the ad is actually closed (i.e. move the `preload_interstitial` call from the `finally` into the `on_close` path in `_handle_close`, `ad_service.py:211-219`), so only one `InterstitialAd` service is ever live. Verify against the 30 s rate limit before shipping — this changes *when* the next ad is requested, not whether ads are shown.
9. **Do not patch the venv.** Issue 6 (`DART\src\banner.dart:23-25`) is an upstream defect; report it to the flet-ads project rather than editing `site-packages`.

---

## 5) Verdict

**ISSUES FOUND.**

The app's ad wiring is fundamentally sound and unusually careful: the flet 1.0.4 service-GC keep-alive via `page.services.append(...)` is both necessary and correct (and was verified to be load-bearing on Python 3.14.7); the consent flow matches the installed UMP contract exactly, with the correct method names, arities and ordering; the interstitial one-shot contract is honoured at the Python level; the rate limiter uses a correct clock and a correct non-zero sentinel; every await around the ad APIs is guarded; teardown releases services and clears the banner pool; and the desktop no-op guard is complete — on Windows desktop **nothing ad-related is constructed**, so `ft.FletUnsupportedPlatformException` is unreachable and the developer's desktop session cannot crash. Nothing the app uses is misnamed or deprecated.

Against that, one issue is serious enough to fix before shipping: **Issue 1 (HIGH)** — four banner call sites bypass the pooling helper, so the Results screen re-requests an ad on every 2 Hz tick and the Settings screen builds three fresh banners per render, contradicting the module's own documented contract and creating an AdMob invalid-traffic pattern. **Issue 2 (MEDIUM)** is the deepest structural risk: the bundled extension keeps the loaded interstitial in a single `static` slot (`DART\src\interstitial.dart:10`) while `show()` resolves at presentation time, so the app's immediate restock preload (`ad_service.py:261-263`) puts two `InterstitialAd` services in flight against that one slot. **Issue 3 (MEDIUM)** — the absence of iOS unit ids means the iOS build silently earns nothing.

Everything else is low-severity or informational: a pooled fallback container that can permanently disable a slot (Issue 4), a wrong-instance release in one error handler (Issue 5), a swallowed teardown exception that contradicts the app's own logging policy (Issue 8), and an `on_load` lambda whose exceptions bypass the app's logging (Issue 9). `NativeAd` is confirmed dead in this build (Issue 10) and must not be used.

Recommended order: fix Issue 1 → decide Issue 3 (iOS target yes/no) → evaluate the Issue 8 mitigation → then the remaining small improvements in §4.
