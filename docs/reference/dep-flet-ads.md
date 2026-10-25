# Dependency Reference: `flet-ads` (1.0.4)

> **Package:** `flet-ads`  
> **Installed Version:** `1.0.4`  
> **Source Location (Sherlock-V2 venv):** `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/flet_ads`  
> **Dist-Info:** `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/flet_ads-1.0.4.dist-info`  
> **Flutter Package Location:** `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/flutter/flet_ads`  
> **Original Sherlock Implementation:** `/home/maikel/.zcode/workspace/default/Sherlock/src/components/banner_ad.py` and `/home/maikel/.zcode/workspace/default/Sherlock/src/services/ad_service.py`

---

## 1. Package Metadata & Overview

- **PyPI Package:** `flet-ads`
- **Version:** `1.0.4` (`METADATA:3`)
- **Python Compatibility:** `>=3.10` (`METADATA:11`)
- **Flet Dependency:** Strictly pinned to `flet==1.0.4` (`METADATA:14`). Flet extension packages require an exact match with the core `flet` runtime version.
- **Underlying Flutter Engine:** Built on top of Flutter's `google_mobile_ads: ^9.0.0` (`flutter/flet_ads/pubspec.yaml:15`).
- **License:** Apache-2.0 (`METADATA:6`, `licenses/LICENSE`).
- **Platform Scope:** Mobile only (`Android` and `iOS`). Desktop (`Windows`, `macOS`, `Linux`) and `Web` are unsupported (`METADATA:39-42`).

---

## 2. Public API Specification

The public package exports are defined in `flet_ads/__init__.py:1-29`:

```python
__all__ = [
    "AdRequest",
    "BannerAd",
    "BaseAd",
    "ConsentDebugSettings",
    "ConsentManager",
    "ConsentRequestParameters",
    "ConsentStatus",
    "DebugGeography",
    "InterstitialAd",
    "PaidAdEvent",
    "PrecisionType",
    "PrivacyOptionsRequirementStatus",
]
```

*(Note: `NativeAd` and native styling classes reside in `flet_ads/native_ad.py` and `flet_ads/types.py`, but are not exported in `__init__.__all__` and are disabled in the Flutter extension.)*

### 2.1 Base Class: `BaseAd` (`flet_ads/base_ad.py:8-75`)

Inherits from `ft.BaseControl`. Dataclass with `kw_only=True`. Defines core targeting and lifecycle events shared across ad units:

- **Attributes:**
  - `unit_id: str` (`base_ad.py:21-24`): AdMob ad unit identifier.
  - `request: AdRequest = field(default_factory=lambda: AdRequest())` (`base_ad.py:26-29`): Targeting configuration.
- **Event Handlers:**
  - `on_load: Optional[ft.ControlEventHandler["BaseAd"]]` (`base_ad.py:31-34`): Triggered when an ad successfully finishes loading.
  - `on_error: Optional[ft.ControlEventHandler["BaseAd"]]` (`base_ad.py:36-42`): Triggered when loading or presentation fails; `e.data` carries the error message.
  - `on_open: Optional[ft.ControlEventHandler["BaseAd"]]` (`base_ad.py:44-51`): Triggered when ad opens a full-screen overlay in response to user interaction.
  - `on_close: Optional[ft.ControlEventHandler["BaseAd"]]` (`base_ad.py:53-57`): Triggered when the full-screen view is closed.
  - `on_impression: Optional[ft.ControlEventHandler["BaseAd"]]` (`base_ad.py:59-62`): Triggered when an impression is logged.
  - `on_click: Optional[ft.ControlEventHandler["BaseAd"]]` (`base_ad.py:64-67`): Triggered when the ad is clicked.
- **Platform Enforcement:**
  - `before_update(self)` (`base_ad.py:69-75`): Enforces that `self.page.web` is false and `self.page.platform.is_mobile()` is true, raising `ft.FletUnsupportedPlatformException` otherwise.

### 2.2 Banner Ads: `BannerAd` (`flet_ads/banner_ad.py:8-42`)

Inherits from `ft.LayoutControl` and `BaseAd`. Decorated with `@ft.control("BannerAd")`.

- **Control Type:** Visual layout control (`Widget` mounted into the visual control tree).
- **Additional Event Handlers:**
  - `on_will_dismiss: Optional[ft.ControlEventHandler["BannerAd"]]` (`banner_ad.py:28-34`): iOS-only event before dismissing a full-screen ad overlay.
  - `on_paid: Optional[ft.ControlEventHandler[PaidAdEvent["BannerAd"]]]` (`banner_ad.py:36-41`): Triggered when an ad earns revenue (allowlisted accounts only).
- **Dart Implementation:** Mapped to `BannerAdControl` (`flutter/flet_ads/lib/src/banner.dart:7-84`), configuring `AdSize.banner` (standard 320×50 dp). When mounted, if `!_isLoaded`, calls `bannerAd.load()`. If load fails, invokes native `ad.dispose()` (`banner.dart:43`).

### 2.3 Interstitial Ads: `InterstitialAd` (`flet_ads/interstitial_ad.py:5-38`)

Inherits from `ft.Service` and `BaseAd`. Decorated with `@ft.control("InterstitialAd")`.

- **Control Type:** Non-visual headless service.
- **One-Time Display Lifecycle Contract:**
  - "Each instance is allowed to be shown (using `show`) only once. To show another ad, create a new instance. Reusing an already-shown instance will result in errors or unexpected behavior" (`interstitial_ad.py:10-13`).
- **Methods:**
  - `async def show(self)` (`interstitial_ad.py:30-37`): Invokes the native `"show"` method over the Flet bridge. The ad must be loaded before calling `show()`.
- **Dart Implementation:** Mapped to `InterstitialAdService` (`flutter/flet_ads/lib/src/interstitial.dart:7-70`). Auto-triggers `InterstitialAd.load()` upon service `init()` (`interstitial.dart:18-51`). Automatically disposes native resources upon dismissal (`interstitial.dart:38`) or service disposal (`interstitial.dart:67`).

### 2.4 Rewarded Ads: Not Supported / Not Implemented

- **Status:** **NOT IMPLEMENTED** in `flet-ads 1.0.4`.
- **Evidence:** 
  - No `RewardedAd` class exists in `flet_ads/` Python sources or `__all__`.
  - No rewarded ad controller, callback, or service exists in `flutter/flet_ads/lib/src/` or `flutter/flet_ads/lib/src/extension.dart`.
  - Neither AdMob rewarded video nor rewarded interstitial ad formats can be used with `flet-ads 1.0.4`.

### 2.5 Native Ads: Experimental / Disabled Upstream

- **Status:** Incomplete and disabled in upstream Flutter bundle.
- **Python Source:** `flet_ads/native_ad.py:8-34` defines `NativeAd(BannerAd)` requiring either `factory_id` or `template_style`.
- **Dart Status:** In `flutter/flet_ads/lib/src/extension.dart:34-37`, native ad handling is explicitly commented out:
  ```dart
  /* TODO: Finalize NativeAdControl -> https://developers.google.com/admob/flutter/native/platforms
  case "NativeAd":
    return NativeAdControl(control: control);
  */
  ```
  Attempting to render a `NativeAd` returns `null` from `createWidget`, rendering nothing. Do not use `NativeAd`.

### 2.6 Consent Management: `ConsentManager` (`flet_ads/consent_manager.py:13-137`)

Inherits from `ft.Service`. Decorated with `@ft.control("ConsentManager")`. Provides integration with Google's User Messaging Platform (UMP) for GDPR, UK-GDPR, and US State privacy regulations.

- **Typical Initialization & Consent Flow:**
  1. `await consent_manager.request_consent_info_update(params)` (`consent_manager.py:44-59`): Requests latest consent status from Google UMP at app launch.
  2. `await consent_manager.load_and_show_consent_form_if_required()` (`consent_manager.py:108-116`): Loads and displays the consent form if required by the user's jurisdiction (e.g. EEA/UK).
  3. `await consent_manager.can_request_ads()` (`consent_manager.py:85-93`): Returns `True` if consent requirements are met and ads may be requested.
- **Privacy Options (Ongoing Consent Withdrawal/Management):**
  - `await consent_manager.get_privacy_options_requirement_status() -> PrivacyOptionsRequirementStatus` (`consent_manager.py:94-106`): Returns `REQUIRED`, `NOT_REQUIRED`, or `UNKNOWN`.
  - `await consent_manager.show_privacy_options_form()` (`consent_manager.py:118-126`): Presents the privacy settings form (required by GDPR for persistent user consent modification).
- **Diagnostics & Testing:**
  - `await consent_manager.is_consent_form_available() -> bool` (`consent_manager.py:60-72`)
  - `await consent_manager.get_consent_status() -> ConsentStatus` (`consent_manager.py:73-84`)
  - `await consent_manager.reset()` (`consent_manager.py:128-136`): Clears stored consent state (testing only).
- **Platform Enforcement:** `before_update` checks `self.page.web` and `self.page.platform.is_mobile()`, throwing `ft.FletUnsupportedPlatformException` on desktop/web (`consent_manager.py:36-42`).

### 2.7 Supporting Types & Data Models (`flet_ads/types.py:1-266`)

- `AdRequest`: Dataclass decorated with `@ft.value` (`types.py:61-106`).
  - Fields: `keywords: Optional[list[str]]`, `content_url: Optional[str]`, `neighboring_content_urls: Optional[list[str]]`, `non_personalized_ads: Optional[bool]`, `http_timeout: Optional[int]` (Android only, in milliseconds), `extras: Optional[dict[str, str]]`.
- `PaidAdEvent`: Dataclass inheriting from `ft.Event` (`types.py:39-59`).
  - Fields: `value: float` (monetary value), `precision: PrecisionType`, `currency_code: str`.
- `PrecisionType`: Enum (`types.py:23-37`) - `UNKNOWN`, `ESTIMATED`, `PUBLISHER_PROVIDED`, `PRECISE`.
- `ConsentStatus`: Enum (`types.py:139-170`) - `NOT_REQUIRED`, `OBTAINED`, `REQUIRED`, `UNKNOWN`.
- `PrivacyOptionsRequirementStatus`: Enum (`types.py:171-194`) - `NOT_REQUIRED`, `REQUIRED`, `UNKNOWN`.
- `DebugGeography`: Enum (`types.py:196-216`) - `DISABLED`, `EEA`, `REGULATED_US_STATE`, `OTHER`.
- `ConsentDebugSettings`: `@ft.value` dataclass (`types.py:218-243`) - `debug_geography: Optional[DebugGeography]`, `test_identifiers: Optional[list[str]]`.
- `ConsentRequestParameters`: `@ft.value` dataclass (`types.py:245-266`) - `tag_for_under_age_of_consent: Optional[bool]`, `consent_debug_settings: Optional[ConsentDebugSettings]`.

---

## 3. Initialization & Lifecycle Mechanics

### 3.1 MobileAds Engine Auto-Initialization

Unlike standard Flutter code where `MobileAds.instance.initialize()` must be awaited manually, `flet-ads` automatically initializes the native SDK via Flet's extension hook (`flutter/flet_ads/lib/src/extension.dart:10-15`):

```dart
class Extension extends FletExtension {
  @override
  void ensureInitialized() {
    if (isMobilePlatform()) {
      MobileAds.instance.initialize();
    }
  }
  ...
}
```

When running in Python, importing `flet_ads` and constructing controls does not require manual native initialization calls.

### 3.2 Flet Service Keep-Alive Gotcha (Crucial!)

`InterstitialAd` and `ConsentManager` are subclasses of `ft.Service`. In Flet:
1. `Service.init()` self-registers the service with `ft.context.page.services` only when constructed inside an active page context (e.g., inside an event handler or `page.run_task`).
2. **Flet Session Refcount Garbage Collection:** Flet runs `ServiceRegistry.unregister_services()` after **every event**, pruning any service whose reference count drops to 3 or lower.
3. **Keep-Alive Requirement:** To prevent premature unregistration while waiting for ads or UMP responses, the application must explicitly append the service instance to `page.services`:
   ```python
   if ad not in page.services:
       page.services.append(ad)
   ```
4. **Cleanup:** Once an interstitial ad closes or fails to load, it must be removed from `page.services`:
   ```python
   def _release_service(services: list, item) -> None:
       try:
           services.remove(item)
       except ValueError:
           pass
   ```

### 3.3 Control Teardown and Resource Cleanup

- `BannerAd` has no Python-level `.dispose()` method. When its parent container is unmounted or replaced in the Flet page tree, the Flutter widget `_BannerAdControlState` triggers native disposal upon unmount or on load failure (`flutter/flet_ads/lib/src/banner.dart:43`).
- Re-creating `BannerAd` on every screen re-render causes visible flashing and resets AdMob's automatic 30–60 second ad refresh timer. Banners should be pooled/reused across screen renders.

---

## 4. Platform Support Matrix & Guard Rails

| Platform | Support | Behavior on Attempted Use |
| :--- | :---: | :--- |
| **Android** | Supported | Loads Google Mobile Ads SDK and native AdView / Interstitial / UMP. |
| **iOS** | Supported | Loads Google Mobile Ads SDK and native AdView / Interstitial / UMP. |
| **Windows** | Unsupported | Raises `ft.FletUnsupportedPlatformException` on `before_update`. |
| **macOS** | Unsupported | Raises `ft.FletUnsupportedPlatformException` on `before_update`. |
| **Linux** | Unsupported | Raises `ft.FletUnsupportedPlatformException` on `before_update`. |
| **Web** | Unsupported | Raises `ft.FletUnsupportedPlatformException` on `before_update`. |

### 4.1 Safe Non-Mobile Gating Pattern

Because `before_update` raises `ft.FletUnsupportedPlatformException` when attached to a desktop or web page, application code must verify platform support before mounting:

```python
def is_ad_supported(page: ft.Page) -> bool:
    try:
        return bool(page and hasattr(page, "platform") and page.platform.is_mobile() and not page.web)
    except Exception:
        return False
```

If not supported, components should return a harmless placeholder (e.g., `ft.Container(width=0, height=0)`).

---

## 5. Ad Unit IDs & Test Identifiers

### 5.1 Google AdMob Official Test IDs

Documented in `flet-ads` source docstrings (`banner_ad.py:18-20`, `interstitial_ad.py:20-22`) and fallback constants in Dart (`banner.dart:23-25`, `interstitial.dart:21-23`, `native.dart:25-27`):

| Ad Format | Android Test Unit ID | iOS Test Unit ID |
| :--- | :--- | :--- |
| **Banner Ad** | `ca-app-pub-3940256099942544/9214589741` | `ca-app-pub-3940256099942544/2435281174` |
| **Interstitial Ad** | `ca-app-pub-3940256099942544/1033173712` | `ca-app-pub-3940256099942544/4411468910` |
| **Native Ad (Test)**| `ca-app-pub-3940256099942544/2247696110` | `ca-app-pub-3940256099942544/3986624511` |

### 5.2 Original Sherlock Production Unit IDs

Defined in Sherlock's codebase (`Sherlock/src/core/constants.py:71` and `Sherlock/src/services/ad_service.py:54`):

- **Banner Production ID (Android):** `"ca-app-pub-5679949845754640/5131365762"` (`constants.py:71`)
- **Interstitial Production ID (Android):** `"ca-app-pub-5679949845754640/2758003779"` (`ad_service.py:54`)

---

## 6. How Original Sherlock Implements `flet-ads`

Sherlock manages ads via two primary modules:
1. `src/components/banner_ad.py`: Shared UI wrapper and banner caching.
2. `src/services/ad_service.py`: Lifecycle coordinator for UMP consent and interstitials.

### 6.1 Canonical Banner Component (`src/components/banner_ad.py:1-135`)

- **Screen Standardization:** Used across Home, Results, History, Settings, and Networks screens (`banner_ad.py:3-5`).
- **Layout Architecture:**
  - The banner is sized at fixed `320×50` inside a centered `ft.Container`.
  - Wrapped in a glass card container (`expand=True`, adaptive glass background and border).
  - Hosted inside an outer `ft.Row(alignment=ft.MainAxisAlignment.CENTER)` (`banner_ad.py:131-134`).
  - Sizing constraint: Never set `alignment` on the wide outer container itself, as Flet will expand it to fill parent vertical height, causing full-page blank ad regressions (`banner_ad.py:12-14`).
- **Banner Pooling (`pooled_banner_ad`):**
  - Uses `_BANNER_POOL: dict[str, Control] = {}` keyed by screen slot (`banner_ad.py:41-54`).
  - Prevents rebuilding the `BannerAd` on screen state changes or re-renders, avoiding visual flashes and preserving AdMob's internal auto-refresh cycle.
  - `clear_banner_pool()` (`banner_ad.py:57-65`): Clears the pool on page teardown or theme switch.

```python
# Sizing and structure in Sherlock banner_ad.py:96-134:
ad = fta.BannerAd(
    unit_id=AD_BANNER_UNIT_ID,
    width=320,
    height=50,
    on_load=lambda e: logger.info("BannerAd loaded"),
    on_error=lambda e: logger.warning("BannerAd load error: %s", getattr(e, "data", e)),
)
banner = ft.Container(
    content=ft.Column(
        [ft.Container(content=ad, width=320, height=50)],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=tokens.SPACE_XS,
        tight=True,
    ),
    expand=True,
    padding=tokens.SPACE_SM,
    border_radius=tokens.RADIUS_LG,
    bgcolor=adaptive_glass_bg(page),
    border=ft.Border.all(1, adaptive_glass_border(page)),
)
return ft.Row(controls=[banner], alignment=ft.MainAxisAlignment.CENTER)
```

### 6.2 AdService Orchestration (`src/services/ad_service.py:1-324`)

- **Consent Gathering:**
  - Instantiates `fta.ConsentManager()` (`ad_service.py:101`).
  - Calls `page.services.append(self._consent_manager)` to survive Flet event GC (`ad_service.py:105`).
  - Calls `request_consent_info_update()` followed by `load_and_show_consent_form_if_required()` (`ad_service.py:106-107`).
  - Sets `_can_request_ads = await self._consent_manager.can_request_ads()` (`ad_service.py:108`).
  - Queries `get_privacy_options_requirement_status()` to decide if a "Privacy Options / Manage Consent" button must be exposed in Settings (`ad_service.py:110-115`).
- **Interstitial Rate-Limiting & Policy Safety:**
  - `INTERSTITIAL_MIN_INTERVAL_SEC = 30.0` (`ad_service.py:60`): Prevents stacking ads when users rapidly trigger searches or exports, protecting the AdMob account against policy strikes.
- **Preloading & Showing Interstitials:**
  - `preload_interstitial()` (`ad_service.py:175-210`): Instantiates `fta.InterstitialAd` in advance, appends to `page.services`, and wires `on_close` to trigger replenishment.
  - `show_interstitial()` (`ad_service.py:221-304`):
    - Checks rate limit interval.
    - If preloaded ad is ready: retains strong reference in `self._shown_interstitial`, calls `await ad.show()`, and restocks in `finally`.
    - If preloaded ad is not ready: constructs a fresh self-loading ad with `on_load=lambda e: self.page.run_task(_show, e)` (spaninsight fallback pattern).
- **Service Teardown:**
  - `close()` (`ad_service.py:305-315`): Drops active service references from `page.services` and invokes `clear_banner_pool()`.

---

## 7. Comparison: `flet-ads` 0.86.5 vs 1.0.4

### 7.1 Binary & Source Comparison Findings

A direct file-by-file comparison between the official PyPI wheels of `flet_ads-0.86.5-py3-none-any.whl` and `flet_ads-1.0.4-py3-none-any.whl` reveals:

1. **Python Sources are 100% Byte-Identical:**
   - `flet_ads/__init__.py`
   - `flet_ads/banner_ad.py`
   - `flet_ads/base_ad.py`
   - `flet_ads/consent_manager.py`
   - `flet_ads/interstitial_ad.py`
   - `flet_ads/native_ad.py`
   - `flet_ads/types.py`
   *(Zero diff across all Python source files.)*
2. **Flutter / Dart Sources are 100% Byte-Identical:**
   - `flutter/flet_ads/pubspec.yaml`
   - `flutter/flet_ads/lib/flet_ads.dart`
   - `flutter/flet_ads/lib/src/banner.dart`
   - `flutter/flet_ads/lib/src/interstitial.dart`
   - `flutter/flet_ads/lib/src/consent_manager.dart`
   - `flutter/flet_ads/lib/src/native.dart`
   - `flutter/flet_ads/lib/src/extension.dart`
   - `flutter/flet_ads/lib/utils/ads.dart`
   - `flutter/flet_ads/lib/utils/consent.dart`
   - `flutter/flet_ads/lib/utils/native.dart`
   *(Zero diff across all Dart files and assets.)*

### 7.2 Differences in Distribution & Ecosystem Context

| Aspect | `flet-ads` 0.86.5 | `flet-ads` 1.0.4 |
| :--- | :--- | :--- |
| **Dependency Pin** | `Requires-Dist: flet==0.86.5` (`METADATA:14`) | `Requires-Dist: flet==1.0.4` (`METADATA:14`) |
| **Package Version**| `0.86.5` | `1.0.4` |
| **Runtime Ecosystem**| Flet 0.86.5 runtime | Flet 1.0.4 runtime |
| **Reason for Release**| Release tied to Flet 0.86.5 | Rebuilt and released to satisfy Flet 1.0.4's strict peer-dependency pin and resolve upstream `jni`/`jni_flutter` platform build resolution issues. |

### 7.3 Behavioral Nuances in Flet 1.0.x Environment

While `flet-ads` code did not change, the underlying **Flet 1.0.x core engine** introduced changes that affect `flet-ads` controls:
- **Service Garbage Collection:** In Flet 1.0.x, `page.services.append(service)` is mandatory for services like `ConsentManager` and `InterstitialAd`. Flet's session flusher runs `unregister_services()` after every UI event, meaning unreferenced services are unregistered immediately.
- **Platform Guarding:** In both 0.86.5 and 1.0.4, the platform check is deferred to `before_update(self)` (`base_ad.py:69-75`), enabling unit tests to construct `AdService` and `InterstitialAd` using dummy page objects without raising exceptions, provided `before_update` is not called.

---

## 8. Recommendations for Sherlock-V2

1. **Mirror the Canonical Banner Component:** Port `pooled_banner_ad` and `build_banner_ad` directly from Sherlock (`src/components/banner_ad.py`). The full-width glass wrapper around a centered 320×50 ad unit is battle-tested.
2. **Maintain Service Keep-Alive Registration:** Always append `ConsentManager` and `InterstitialAd` to `page.services` and remove them on completion to prevent Flet 1.0.4's service GC from unregistering active ads.
3. **Respect Rate Limits & Consent Gates:** Maintain the 30-second minimum interval between interstitial ads to protect AdMob account standing.
4. **Avoid NativeAd & RewardedAd:** Do not attempt to use `NativeAd` (disabled upstream in Flutter) or `RewardedAd` (non-existent). Stick to standard 320×50 `BannerAd` and full-screen `InterstitialAd`.
