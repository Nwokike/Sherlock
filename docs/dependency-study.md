# Sherlock Dependency Deep-Study v2

> **Date:** 2026-10-01 · **Method:** ~40 sub-agent study packets, each reading the
> installed `.venv\Lib\site-packages` source (`.venv` is the source of truth),
> cross-referenced against `src/` usage via import scans and per-file audits.
> Scope: **all 102 installed distributions** (7 direct runtime + 3 dev + 92 transitive),
> **all 48 `src/` files**, **all 25 test files**. Baseline: **196 tests pass, ruff clean**.
>
> Supersedes the 2026-09-23 study (413 lines, 6 packets, 83 lock packages).
> New in v2: full transitive coverage, test-suite audit, stray-package discovery,
> and a ranked opportunity backlog (§9) plus a P0→P3 fix backlog (§10).

---

## 0. Executive summary

- Every dependency and subdependency in `.venv` now has a one-agent verdict: **utilize,
  keep-as-infra, prune-at-build, or remove-as-stray**.
- Biggest untapped wins: maigret full tag/country/engine filtering + DB auto-update,
  holehe `extra`/`media` rendering + username pivot, socid pivot-search + cookie
  forwarding, flet SelectionArea/Banner/Shimmer/ResponsiveRow/Wakelock, flet-ads
  AdRequest targeting + frequency cap, httpx `Timeout`/`http2`/streaming avatars,
  curl-cffi fingerprint rotation + session reuse, `python-slugify` for filename safety,
  `arrow.humanize` for timestamps, `qrcode` + reportlab-QR for dossier handoff,
  `pillow` thumbnails for the avatar cache.
- Hygiene finds: 5+ stray packages **not in `uv.lock`** (cookiecutter, binaryornot, rich,
  markdown-it-py, pygments …) from a manual `pip install flet-cli` into `.venv` —
  dead weight, safe to drop on venv rebuild. IPython chain (~tens of MB) is pure
  transitive weight and a build-pruning candidate. `[tool.flet.cleanup]` already covers
  flask/werkzeug/click/blinker/itsdangerous/asgiref/oauthlib.
- Test-suite verdict: suite is mostly real-behavior (good), but FakePage lacks
  `platform/client_storage/width/brightness/lifecycle`, smoke tests never render,
  several tests patch dead code paths (`httpx.AsyncClient` vs `get_client()`), one test
  **encodes a bug** (`test_state.py` asserts `reset_search` forces `is_online=True`),
  and P0 cancel/timeout paths in both engines are untested.
- App icons (`src/assets/icon.png`) are never wired to the build — packaged apps ship
  the default Flet icon/splash. One config block fixes it.

---

## 1. Direct runtime dependencies (7)

| Package | Ver | Role | Utilization | Verdict |
|---|---|---|---|---|
| flet | 1.0.1 | GUI framework (Flutter 3.44.8) | Heavy, 30 files; Cupertino/Router/GridView/Wakelock etc. unused | Utilize §1.1 |
| flet-ads | 1.0.1 | AdMob banner + interstitial + UMP consent | Banner + interstitial + consent wired; targeting/cap/retry missing | Utilize §1.2 |
| flet-local-auth | 1.0.1 | Biometric/device-credential auth | History gate only; 11/14 error codes + stop/timeout unused | Utilize §1.3 |
| holehe-v2 | 1.0.3 | 181 email validators | Per-validator driver w/ semaphore/timeout/cancel; `extra`/`media` saved but barely rendered | Utilize §2 |
| httpx (+http2,socks) | 0.28.1 | App HTTP (update check, avatars) | 2 call sites; no Timeout/http2/retries/streaming | Utilize §3 |
| maigret | 0.6.6 | 5,897-site username engine | Core engine; tags/names/id_type/Tor/activation/exports unused | Utilize §4 |
| socid-extractor | 0.1.1 | 164-scheme profile enrichment | Thin wrapper; cookies/hints/2nd-hop/pivot unused | Utilize §5 |

### 1.1 flet 1.0.1 — untapped (verified present, zero hits in `src/`)

- UI feedback: `Badge` (History/results counts), `Tooltip` on IconButtons,
  `ft.Banner` for offline (persistent + Retry action) instead of SnackBar-only,
  `SnackBarAction`, `Shimmer` skeleton rows, `AnimatedSwitcher` for count/banner transitions.
- Selection/clipboard: wrap results in `SelectionArea`; replace manual
  `ft.Clipboard().set` / `Share.share_text` with `action=ft.CopyToClipboard(...)` /
  `ft.ShareText(...)` / `ft.OpenUrl(...)` (fixes iOS Safari gesture-window drops);
  `ContextMenu` on result cards.
- Navigation/responsive: `ResponsiveRow` + `GridView` for tablets; `NavigationDrawer`/`Rail`
  on wide windows; `page.on_resize`; adopt `Router`/`Route`/`TemplateRoute` for deep links.
- Input: `AutoComplete` for username/email; expand `SearchBar` to Sites screen;
  `DataTable` for email-module matrix / DB health; `ReorderableListView` for favorites.
- Polish: `Hero` avatar transitions; `InteractiveViewer` for graph/avatars;
  `Screenshot`/`take_screenshot` for share-card-as-image.
- Platform: `Wakelock` during scans; `selection_click`/`vibrate` haptics;
  `StoragePaths` + `SharedPreferences` instead of hand-rolled paths;
  `KeyboardListener` shortcuts (Ctrl+K, Esc); `page.scroll_to` newest hit.
- Theming: extend `AppTheme` with Dialog/BottomSheet/ListTile/Switch/Progress/Tooltip
  themes; `Semantics` labels; `AdaptiveControl`/Cupertino for iOS sheets.
- Perf: `use_callback`/`use_memo`/`memo` around result cards (2 Hz tick re-renders whole
  tree today); `PageView` for onboarding (replaces hand-rolled GestureDetector).

### 1.2 flet-ads 1.0.1 — untapped

No `RewardedAd`/`RewardedInterstitialAd`/`AppOpenAd` in 1.0.1 — rewarded unlocks must use
interstitial-with-continuation or wait for an upgrade. `NativeAd` exists but is **not
exported** from package root (`flet_ads.native_ad` only).
Opportunities, highest value first: (1) `AdRequest` targeting (keywords/content_url/
non_personalized_ads) on both formats; (2) consent-gap — `show_privacy_options()` exists
but Settings hides the row, add conditional row when status is REQUIRED; (3) interstitial
frequency cap (currently fires on **every** search); (4) retry with backoff + collapse
banner to zero-size after K failures; (5) wire `on_impression`/`on_click`/`on_open`/
`on_close`/`on_paid`; (6) responsive banner sizing (pinned 320×50); (7) `NativeAd` in
results lists (experimental); (8) iOS unit IDs (all prod IDs are Android); (9) call
`is_consent_form_available()`/`get_consent_status()` + debug geography for EEA testing.

### 1.3 flet-local-auth 1.0.1 — untapped

Never used: `can_check_biometrics()`, `get_available_biometrics()`,
`stop_authentication()`, `biometric_only`, `sensitive_transaction`,
`persist_across_backgrounding`, localized messages, 11/14 error codes.
Opportunities: (1) granular capability label in Settings + honest disable when nothing
enrolled; (2) `persist_across_backgrounding=True` (one line, fixes background-kill);
(3) `stop_authentication()` on tab-leave (fixes AUTH_IN_PROGRESS dead-end);
(4) full error-code UX (cancel≠error, lockout hints, double-tap guard);
(5) `biometric_only` strict-mode toggle; (6) `sensitive_transaction=False` for History read;
(7) branded Android/iOS dialog strings; (8) re-lock on resume/tab-leave/idle;
(9) Linux/Web graceful disable. P1 bug: Linux/Web stays locked forever (unsupported
platform maps to deny instead of grant) — `biometric_service.py` fix queued in §10.

---

## 2. holehe-v2 1.0.3 + curl-cffi 0.16.3

- Architecture: `Result(url, message, extra, media)` + `taken()/available()/error()`;
  ~182 `validate_*` (~163 httpx, 17 curl-cffi impersonate, 162 hardcoded UA);
  timeouts hardcoded per-request (15s×146, 6s×29, 20s×12); no proxy/retry/category
  metadata; honest error prose enables regex classification. Only 4 modules return
  `media` (gravatar richest, github, duolingo, etsy).
- App already works around upstream gaps: zip-safe loader, own semaphore/timeout/cancel,
  fingerprint wrap, env-proxy injection. Do NOT adopt `run_all()` or `export_json`.
- Untapped: (1) render/export saved `extra` (chips in result_card + Detail column in
  reports); (2) widen `_recovery_from`/`_phone_from` (dropbox/rap
...[truncated 20862 chars]