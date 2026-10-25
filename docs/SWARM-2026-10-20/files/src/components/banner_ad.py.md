# Audit — `src/components/banner_ad.py`

**File:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/components/banner_ad.py` (134 lines)
**Truth sources:** `.venv\Lib\site-packages\flet` (flet 1.0.4), `.venv\Lib\site-packages\flet_ads` (flet-ads 1.0.4), `.venv\Lib\site-packages\flutter\flet_ads` (Dart client), `docs/reference/dep-flet-ads.md`, `pyproject.toml`
**Method:** every API below was read out of the installed packages; the exact `:96-134` control tree and the exact `fta.BannerAd(...)` kwargs were executed in the project venv to confirm they construct cleanly.

---

## 1) File role

Single canonical banner-ad component for the whole app (mobile only).

| Symbol | Line | Role |
|---|---|---|
| `_BANNER_POOL: dict[str, Control]` | `banner_ad.py:41` | Module-global slot → control cache |
| `pooled_banner_ad(slot, page=None)` | `banner_ad.py:44-54` | Pool accessor used by render paths |
| `clear_banner_pool()` | `banner_ad.py:57-65` | Drops the pool (theme change / teardown) |
| `build_banner_ad(page=None)` | `banner_ad.py:68-134` | Actual builder: platform gate → `fta.BannerAd` → glass container → stretcher Row |

**Consumers (all 9 call sites):**

- Pooled: `home_screen.py:1375` (`home-1`), `home_screen.py:1408` (`home-2`), `history_screen.py:470` (`history-1`), `sites_screen.py:770` (`sites-list-N`), `results_screen.py:343` (`results-N`, pooled helper `_banner_at`).
- Raw (bypass the pool): `results_screen.py:1031`, `settings_screen.py:1760`, `settings_screen.py:1771`, `settings_screen.py:1776`.
- Pool clearing: `app_header.py:136` (theme cycle), `settings_screen.py:320` (theme change), `services/ad_service.py:314` (`AdService.close()` → teardown).

**Answering the "is pooling easy here?" question:** yes — the API is correct and the bypass is a caller decision, not a defect in this file. `pooled_banner_ad` takes exactly one required argument (`slot`), every pooled call site uses it that way, and slot keys are screen-namespaced (`home-1`, `history-1`, `results-N`, `sites-list-N`) so no two screens ever share one control object. The four raw `build_banner_ad()` call sites are the ones paying the cost (a fresh native ad request per render — `results_screen.py:1031` re-requests on every results render; `settings_screen.py:1760/1771/1776` request **three** live ads per settings render).

---

## 2) API verification

### 2.1 flet-ads (`flet_ads` 1.0.4)

| Usage in file | Installed truth | Verdict |
|---|---|---|
| `fta.BannerAd(unit_id=…, width=320, height=50, on_load=…, on_error=…)` `:96-104` | `flet_ads/banner_ad.py:8-41` — `BannerAd(ft.LayoutControl, BaseAd)`; `unit_id` is a **required** field (`base_ad.py:21-24`); `on_load`/`on_error` are real dataclass `ControlEventHandler` fields (`base_ad.py:31-42`); `width`/`height` come from `ft.LayoutControl` (`flet_ads/banner_ad.py:9`) | **Correct.** Executed with exactly these kwargs in the venv — constructs, `ad.width == 320`, `ad.height == 50`, `ad.unit_id` set. No hallucinated kwarg. |
| `import flet_ads as fta` inside the function `:94` | Package is a hard dependency (`pyproject.toml:9`), and the local import keeps desktop/web runs safe if it is ever absent | Acceptable, but see B7: a failed import is converted into a permanent silent no-op. |
| `on_load` / `on_error` lambdas `:100-103` | `BaseAd.on_load` / `on_error` are dataclass fields → plain callables are correct; `e.data` carries the Dart payload (`banner.dart:41` → `triggerEvent("error", error.toString())`) | **Correct.** `getattr(e, "data", e)` is a safe accessor. |
| Unused ad events | `base_ad.py:49-58` also exposes `on_open`, `on_close`, `on_impression`, `on_click`, `on_paid`; `flet_ads/banner_ad.py:36-41` adds `on_paid` | **Gap** (I2): `on_paid` is the only revenue-verification signal AdMob offers (allowlisted accounts) and is not wired. |
| `AD_BANNER_UNIT_ID` `:30, :97` | `core/constants.py:86` = `"ca-app-pub-5679949845754640/5131365762"`, recorded as the **Android** production banner id in `docs/reference/dep-flet-ads.md:227` | See **B2**. |

### 2.2 flet 1.0.4 platform/context APIs

| Usage | Installed truth | Verdict |
|---|---|---|
| `from flet import context` / `context.page` `:78-80` | `flet/controls/context.py` — `Context.page` raises `RuntimeError("The context is not associated with any page…")` when the `_context_page` ContextVar is unset. Verified at runtime. | Exists and behaves as the `except Exception` at `:81` assumes. `page.run_task` explicitly re-sets the ContextVar (`flet/controls/page.py:939`), but a raw thread does **not** inherit it → see B9. |
| `page.platform.is_mobile()` `:88` | `flet/controls/page.py:595` — `platform: Optional[PagePlatform] = None`. `PagePlatform` = ios / android / android_tv / macos / windows / linux. Runtime-verified: `IOS.is_mobile() → True`, `ANDROID.is_mobile() → True`, `ANDROID_TV.is_mobile() → False`, `WINDOWS.is_mobile() → False`. | Call is valid, but the **gate is incomplete** — see B3 (web) and B4 (`None` platform). |
| `hasattr(page, "platform")` `:84` | `platform` is a dataclass field → the attribute always exists; `hasattr` is always `True` | **Dead check** (B4). |
| `page.web` | `flet/controls/page.py:516` — `web: bool = False` | **Never consulted by this file**, even though `flet_ads`' own guard requires it (`base_ad.py:69-75`) and the repo's own dependency doc prescribes it (`docs/reference/dep-flet-ads.md:202`). See B3. |
| `ft.Container` / `ft.Column` / `ft.Row` / `ft.Border.all` / `ft.CrossAxisAlignment.CENTER` / `ft.MainAxisAlignment.CENTER` | All present in flet 1.0.4; `ft.Border.all(1, "#fff")` executed successfully | **Correct — no hallucinated control or enum.** |
| `expand=True` on the glass container `:118` | `flet/controls/control.py:21-35` — “Has effect only if the direct parent of this control is one of the following controls … Column, Row, View, Page”; `flet/controls/core/row.py:18-19` documents `expand` for filling horizontal space in a Row | **Correct:** the direct parent is the `ft.Row` at `:131`. The inner ad container `:112` correctly does *not* set `expand`. |
| `ft.Column(..., tight=True)` `:116` | Maps to Flutter `mainAxisSize.min` | **Load-bearing, keep it.** Without it, the single-child Column takes `mainAxisSize.max` in a Column parent → the "full-page regression" the module docstring warns about at `:12-14`. |

### 2.3 Layout chain `:96-134` — verified against the flet-ads doc recommendation

- The Dart client hard-codes `size: AdSize.banner` (`.venv\Lib\site-packages\flutter\flet_ads\lib\src\banner.dart:30`) — i.e. **320×50 dp natively**. The Python `width=320, height=50` `:98-99` only sizes the Flet layout box, and it matches `AdSize.banner` exactly, so the ad is neither clipped nor letterboxed. `docs/reference/dep-flet-ads.md:72` records the same mapping.
- Constraint chain (Flutter semantics): `ft.Row` with a flex child takes `maxMainSize` → full available width → `Container(expand=True)` receives a **tight** width → `padding` deflates it → the inner `ft.Column` inherits a tight width → `horizontal_alignment=CENTER` `:114` centers the 320 px ad inside the stretched glass. The docstring's claim at `:9-12` (“glass stretches full width, ad pinned at native 320×50 and centered inside the stretched glass”) **holds**.
- `Row(alignment=MainAxisAlignment.CENTER)` `:133` is a **no-op** (the single child is expanded, so the Row has no free space to distribute). The centering that actually matters is the inner Column's `horizontal_alignment` `:114`. See I8.

### 2.4 One upstream caveat found in the installed Dart

`flutter/flet_ads/lib/src/banner.dart:16-84` — `_BannerAdControlState` has **no `dispose()` override**; `ad.dispose()` is only called in the `onAdFailedToLoad` branch (`:43`). `docs/reference/dep-flet-ads.md:179` claims the native view is disposed on unmount; the installed source shows it is not. This file's docstring `:20-21` (“Flet's renderer unmounts the native ad view with the tree”) inherits that inaccuracy — see B6.

---

## 3) Pool correctness

**Key handling.** Slot keys are opaque strings supplied by callers. All five pooled call sites namespace them per screen (`home-1`, `home-2`, `history-1`, `sites-list-N`, `results-N`), so no two screens ever receive the same control object — the pool cannot hand one `BannerAd` to two live screens. Correct as designed.

**Not keyed by page/session.** `_BANNER_POOL` `:41` is keyed by slot only. The control it stores carries the page it was built under, so a stale entry survives a page/session change unless `clear_banner_pool()` runs. It does run on teardown (`services/ad_service.py:314`) and on both theme paths (`app_header.py:136`, `settings_screen.py:320`), but nothing clears the pool at session start and no teardown path other than `AdService.close()` is guaranteed. See B5.

**Eviction.** There is none — the pool only grows until cleared. In practice it is bounded by the callers' slot naming (`sites-list-N` capped by `_BANNER_MAX`, `results-N` by the result count), so unbounded growth is not reachable today. Fine.

**Theme-switch clearing.** `clear_banner_pool()` `:57-65` is correct as a *teardown* mechanism, but wrong as a *theming* mechanism: it discards a live ad (the exact thing the pool exists to prevent, per this file's own `:36-40`) and, because the Dart control has no `dispose()`, leaks the native ad. See B6.

**Fallback caching — the flet-ads audit's finding is CONFIRMED.** `pooled_banner_ad` `:50-54` stores whatever `build_banner_ad` returns, and `build_banner_ad` returns a `ft.Container(width=0, height=0)` placeholder at `:82`, `:85`, `:89`, `:91` and `:107`. The pool therefore cannot distinguish “this slot has an ad” from “this slot is a placeholder”, so **a slot is permanently disabled for the lifetime of the pool if its first build fails to resolve a page / import flet_ads / hit a bad platform**. See B1.

**Thread-safety.** `_BANNER_POOL` is a plain dict mutated without a lock at `:50-54`. Flet UI code is single-threaded, but `page.run_thread` does **not** inherit the `_context_page` ContextVar (only `page.run_task` re-sets it — `flet/controls/page.py:939`), so an off-thread build hits the `ft.context.page` RuntimeError → placeholder → poisons the slot. See B9.

**Dead parameters.** The `page` argument of `pooled_banner_ad` `:44` and of `build_banner_ad` `:68` is **never supplied by any of the nine call sites** — every one of them calls with zero arguments. So `:76-85` always takes the `ft.context.page` branch, and the `page`-specific branches at `:84` and `:121-122` are effectively unreachable through the public API. See B8.

---

## 4) Bugs (severity-ordered)

### B1 — HIGH — A failed first build permanently poisons the slot (fallback cached as if it were the ad)
`banner_ad.py:50-54` caches the return value of `build_banner_ad` unconditionally; `build_banner_ad` returns a zero-size placeholder at `:82` (no page context), `:85` (no page), `:89`/`:91` (non-mobile or unusable platform) and `:107` (`flet_ads` import/construction failure). Consequences:
- The slot shows no banner for the rest of the session (until a theme change or `AdService.close()`), even after the cause is gone.
- `ft.context.page` raises `RuntimeError` whenever it is read outside a Flet callback (verified) — a banner built from a thread or a raw `asyncio` task yields a placeholder that is then cached permanently.
- The failure is invisible in the UI and, for the `:82`/`:85`/`:89`/`:91` branches, produces **no log line at all** (`:105-107` is the only branch that logs).
**Fix:** never cache a placeholder — either return `None` for “no ad here” and let callers skip it, or tag the placeholder and keep it out of `_BANNER_POOL`.

### B2 — HIGH — iOS is served an Android ad unit (silent zero revenue)
The gate at `:88` accepts **any** mobile platform (`PagePlatform.IOS.is_mobile()` → `True`, runtime-verified), and `:97` always passes the single constant `AD_BANNER_UNIT_ID` = `"ca-app-pub-5679949845754640/5131365762"`, which the repo's own reference doc records as the **Android** production banner id (`docs/reference/dep-flet-ads.md:227`; the id is also the only one in the codebase — `core/constants.py:86`). AdMob ad units are per-platform, so an iOS build requests an Android unit → the request never fills → no exception, no revenue; the Dart listener reports it only through `onAdFailedToLoad` (`banner.dart:40-47`) → our `on_error` `:101-103` logs a warning.
**Fix:** select the unit id from `page.platform` (add `AD_BANNER_UNIT_ID_IOS` next to `core/constants.py:86`), and add a test-unit escape hatch like `AdService.USE_TEST_IDS` (`ad_service.py:51`) so an empty banner is diagnosable.

### B3 — MEDIUM — The platform guard omits `not page.web`
`:88` checks only `page.platform.is_mobile()`. `flet_ads`' own guard (`base_ad.py:69-75`) raises `ft.FletUnsupportedPlatformException` when `self.page.web` **or** the platform is not mobile, and the repo's own dependency doc spells out the correct application-level guard: `page.platform.is_mobile() and not page.web` (`docs/reference/dep-flet-ads.md:202`, with “return a harmless placeholder” at `:207`). If the web client ever reports a mobile platform, `:96-104` builds a real `BannerAd`; the exception is raised later, at **mount time**, from `before_update` — outside the `try/except` at `:93-107`, which only covers *construction* — so it escapes into the page update and can break the screen render.
*Mitigating:* `pyproject.toml` configures only `[tool.flet.android]` (no web/iOS section), and if `page.platform` is `None` on web the `AttributeError` is swallowed at `:90-91`. Latent, not currently reachable in a shipped build — but the file is the app's only ad-platform gate.

### B4 — MEDIUM — `hasattr(page, "platform")` `:84` is a dead check, and a `None` platform is silently read as “desktop”
`page.platform` is `Optional[PagePlatform]` (`flet/controls/page.py:595`): the attribute always exists, so `hasattr` is always `True` and the branch never fires. When the platform is genuinely `None`, `None.is_mobile()` raises `AttributeError`, which the bare `except Exception` at `:90-91` converts into “this is a desktop, show nothing” — an undiagnosed null platform is indistinguishable from a desktop platform, and nothing is logged.

### B5 — MEDIUM — The pool is keyed by slot only, not by page/session
`_BANNER_POOL` `:41` / lookup `:50`: a control built under page A is reused after a session or page change whenever `clear_banner_pool()` did not run first. The pooled `BannerAd` keeps `self.page` bound to the **old** page, so `BaseAd.before_update` (`base_ad.py:69-75`) evaluates the *old* page's `web`/`platform` flags for a control that is being mounted on the *new* page — a stale guard result applied to a live mount. `clear_banner_pool()` is currently called from three places (`app_header.py:136`, `settings_screen.py:320`, `ad_service.py:314`); nothing clears at session start, and `AdService.close()` is the only teardown hook.

### B6 — LOW/MEDIUM — Clearing the pool on a theme change discards a live ad and leaks its native view
`clear_banner_pool()` `:57-65` is invoked on every theme toggle (`app_header.py:136`, `settings_screen.py:320`). Each toggle therefore (a) requests a brand-new ad, resetting AdMob's own refresh cycle — precisely what `:36-40` says the pool exists to prevent — and (b) drops the old control **without disposing the native ad**: the installed Dart control has no `dispose()` override (`flutter/flet_ads/lib/src/banner.dart:16-84`; `ad.dispose()` exists only at `:43`). The file's docstring `:20-21` and `docs/reference/dep-flet-ads.md:179` both assert unmount-disposes; the source shows otherwise.
**Fix:** keep the pool on theme change and re-apply the colours in place (`banner.bgcolor = adaptive_glass_bg(page)`, `banner.border = …`) instead of rebuilding.

### B7 — LOW — Four distinct failure modes collapse into one silent no-op
`except Exception` at `:81`, `:90-91` and `:105` swallow (i) missing page context, (ii) unusable platform, (iii) `flet_ads` not installed / construction failure, (iv) an invalid unit id, and produce the same `ft.Container(width=0, height=0)`. Only `:105-107` logs. Combined with B1 the outcome is a permanent, invisible loss of the ad.

### B8 — LOW — Dead parameters and unreachable branches
`page` is never passed to either public function (verified across all nine call sites), so `pooled_banner_ad`'s `page` parameter `:44` and `build_banner_ad`'s `page` parameter `:68` are dead API surface; `:84` is unreachable in practice (see B4). The `if not page` branch `:85` can only fire when `ft.context.page` returned `None`, which the flet implementation never does (it raises instead) — also effectively dead.

### B9 — LOW — Not thread-safe; a thread-side build poisons the slot
`_BANNER_POOL` `:41-54` has no lock. Two threads can both build an ad for the same slot (one native ad leaked, one ad request wasted), and because `page.run_thread` does not carry the `_context_page` ContextVar (only `page.run_task` does — `flet/controls/page.py:939`), a thread-side build lands in the `:81` placeholder branch and caches it (B1).

### B10 — LOW — Module docstring is stale / describes behaviour this file does not implement
`:7-15` claims “Home/History/Results wrap their banners in shrink-wrap Columns (320px, left-aligned)”. The current call sites do not do that: `home_screen.py:1375` and `:1408` put the banner directly in the root `ft.Column`, and `history_screen.py:470` puts it directly in a `ft.ListView` — so the banner is full-width on all of them (the 320 px shrink-wrap regime the docstring describes is gone). `:17-21` also claims the `on_error` handler “writes the exact AdMob failure code” to Settings → Troubleshooting & Logs; the handler only calls `logger.warning` `:101-103` — that text reaches the in-app log solely because `main.py:2398-2404` attaches `in_memory_log_handler` to the root logger, an indirect dependency this file does not own.

---

## 5) Improvements (concrete)

- **I1 (fixes B1).** Separate “no ad here” from “ad here”. Make `build_banner_ad` return `Control | None` (or a sentinel) and have `pooled_banner_ad` cache **only** real ad controls; the placeholder must never enter `_BANNER_POOL`. Cheapest patch: build the control, check whether it contains a `BannerAd` (e.g. return `(control, is_real)`), and store only real ones.
- **I2 (fixes B2, adds telemetry).** Add `AD_BANNER_UNIT_ID_IOS` and `AD_BANNER_UNIT_ID_TEST` beside `core/constants.py:86` and pick by `page.platform` at `:96-104`. Wire the unused base events — `on_click`, `on_impression`, `on_paid` (`base_ad.py:49-58`, `flet_ads/banner_ad.py:36-41`) — so clicks and (allowlisted) paid events are logged; `on_paid` is the only ground truth for revenue.
- **I3 (fixes B3/B4).** Replace `:84-91` with the guard the repo already documents (`docs/reference/dep-flet-ads.md:202`): `page.platform is not None and page.platform.is_mobile() and not page.web`. Delete the `hasattr` check and the bare `except Exception` around `is_mobile()`.
- **I4 (fixes B5/B9).** Key the pool by `(id(page), slot)` — or store `(page, control)` and rebuild when the page differs — and clear it at session start. Add a `threading.Lock` around the get/create sequence in `:50-54` so a slot is never built twice.
- **I5 (fixes B6).** Stop clearing the pool on theme change. Export a `refresh_banner_pool_theme(page)` that walks the pooled containers and re-applies `adaptive_glass_bg(page)` / `adaptive_glass_border(page)` (`:121-122`) in place — the live ad, its refresh cycle and its native view all survive the toggle.
- **I6.** Make ad failures diagnosable: log the unit id and platform once at INFO when the ad is built, and include them in the `on_error` message (`:101-103`). The Dart payload is just `error.toString()` (`banner.dart:41`), so the Python side should add the context. This is also what makes the “empty banner” recipe in `:17-21` actually usable.
- **I7.** Either drop the unused `page` parameters (`:44`, `:68`) or use them: making `pooled_banner_ad` take a mandatory `page` would remove the `ft.context.page` lookup from the hot path and eliminate the B1 placeholder path entirely.
- **I8.** `ft.Row(alignment=ft.MainAxisAlignment.CENTER)` `:133` is a no-op (the only child is expanded). Either drop it or comment it, so a future reader does not “fix” the wrong line — the centering that matters is the inner Column's `horizontal_alignment` `:114`.
- **I9.** `spacing=tokens.SPACE_XS` `:115` is inert for a single child; the inner `ft.Container(content=ad, width=320, height=50)` `:112` duplicates the ad's own `width`/`height` `:98-99` — if the size ever changes, both must change in lockstep (the Dart side hard-codes `AdSize.banner` anyway, `banner.dart:30`).
- **I10.** `AdRequest` (`base_ad.py:26-28`) is never used — no keywords, no `non_personalized_ads`, no `content_url`. Worth a deliberate decision rather than silence, since the iOS/Android UMP consent flow can require `non_personalized_ads` in regulated regions.

---

## 6) Verdict

**API correctness: PASS.** Every flet / flet-ads API used in this file exists in the installed flet 1.0.4 / flet-ads 1.0.4 with the exact signature used — `fta.BannerAd(unit_id=, width=, height=, on_load=, on_error=)` was executed with the file's own kwargs, and the complete `:96-134` control tree was constructed successfully. There are **no hallucinated controls, kwargs or enums**. The layout chain `:96-134` is correct and matches the flet-ads doc's `AdSize.banner` (320×50) recommendation, and the pool API is used consistently by 5 of 9 call sites (the four raw `build_banner_ad()` calls are caller-side, not a defect here).

**Behaviour: FAIL on two counts.** Two high-severity functional bugs are confirmed: the placeholder-cached-as-ad defect (B1, live today on Android) and the Android-only ad unit served on iOS (B2). Three medium issues (web gap, dead `hasattr`/`None`-platform handling, pool not keyed by page) and four low ones (theme-switch ad destruction + native leak, collapsed exception handling, dead parameters, thread-safety) plus a stale docstring round it out.

**Priority patch set (smallest change, largest revenue protection):**
1. I1 — never cache a placeholder (fixes B1).
2. I2 + I3 — platform-accurate unit id and the `not page.web` guard (fixes B2/B3/B4).
3. I4 — key the pool by page and clear it at session start (fixes B5).
4. I5 — recolour in place instead of clearing the pool on theme change (fixes B6 and preserves AdMob's refresh cycle).

The pre-existing flet-ads audit's three claims are all **confirmed**: the pool does cache the 0×0 fallback (`:50-54`), `:88` does gate only on `is_mobile()`, and the `:96-134` layout is sound as written. Note also one new upstream finding for the SWARM: `flutter/flet_ads/lib/src/banner.dart` has **no `dispose()` override**, so the “unmount disposes the native ad” claim in this file's docstring `:20-21` and in `docs/reference/dep-flet-ads.md:179` is not backed by the installed Dart source.
