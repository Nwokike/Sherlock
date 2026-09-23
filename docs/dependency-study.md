# Sherlock Dependency Deep-Study

> **Date:** 2026-09-23 · **Method:** six sub-agent study packets, each reading the
> installed `.venv\Lib\site-packages` source *and* upstream git/PyPI history, cross-referenced
> against a three-agent audit of the app's integration surface, venv inventory, and demand-side
> pain list (TOP-10). Upstream versions studied: flet 1.0.1, flet-ads 1.0.1, maigret 0.6.6,
> holehe-v2 1.0.3, curl-cffi 0.16.3, socid-extractor 0.1.1 + all 79 sub-dependencies
> (83 lock packages, ~126 MB site-packages).
>
> Findings tagged **[FIXED]** were already landed in Phase 2 of this update.

---

## 0. Executive summary

- The dependency bump (flet 0.86.5→1.0.1, maigret 0.6.5→0.6.6, holehe→holehe-v2 1.0.3) is
  complete and verified: **196 tests pass, ruff clean, CI gate added**.
- holehe-v2 is a full rewrite (181 validators vs 121, modern UAs, honest error messages) —
  `email_service.py` was ported to drive validators per-module under our own semaphore
  (v2's `run_all()` has no progress/cancel/timeout) **[FIXED]**.
- The study surfaced **~40 concrete capability proposals** ranked in §8, the biggest being:
  real recursive search (dead advertised toggle), maigret category/country presets, email
  dossier exports, interactive graph viewer, ~20 MB size trims, proxy-everywhere, and
  protection-badge UX.
- Bugs found & fixed along the way: compiled-DB pickle trusted across maigret versions, cache
  hash comparing pickle-bytes vs source-bytes (never matched), `socks5://` proxies silently
  broken on every httpx path (socksio missing → added `httpx[socks]`), stale CI pinning
  `holehe==1.61` wheels on Python 3.12.

---

## 1. P1 — flet 1.0.1 + flet-ads 1.0.1 + oauthlib

### Git history (0.86.5 → 1.0.1, 2026-08-01 → 2026-09-22)

| Tag | Highlights |
|---|---|
| 0.86.5 | flet-ads construction crash fixed (guard moved to `before_update`); Android `false` permissions emit manifest-remove |
| 1.0.0.dev0 | **All deprecated APIs removed** (#6693); InputBorder enum→class hierarchy; client actions; macOS signing lanes; component-diff fix (#6826) |
| 1.0.0 | **Client actions stable** (`action=` on 10 controls); flet-local-auth; exit contract `_exit` (no atexit/flush guarantee); `use_dialog` IndexError fix; `[tool.flet.boot_screen]` named screens |
| 1.0.1 | Service `init()` registration fix; **child-component click-loss fix** (#6859 — "Control with ID not found"); ListTile-in-Row fix; Pyodide 3.14 stack |

### Key verdicts

- **Render batching: NO change.** flet 1.0.1 still sends one wire patch per `page.update()`
  with no time-based coalescing (`messaging/session.py:663-750` drains a set per wake, then
  sends immediately). The app's 2 Hz render flusher stays. The real lever is
  **targeted `page.update(*controls)`** (`controls/page.py:819`) + `ft.memo` so each flush
  patches only the progress subtree.
- **oauthlib is inert** — only used by `flet.auth.AuthorizationService` (no login flow here).
  Prune-safe at build time (~0.7 MB).
- **`page.client_storage` is gone** — replacement `ft.SharedPreferences` service
  (`services/shared_preferences.py:13-97`). Our hasattr-guarded fallback means file storage
  runs everywhere we ship today (correct); web/Pyodide persistence would need SharedPreferences
  **[verified, no crash path]**.

### Unused capabilities mapped to pains

| # | Capability | API | Landing | Effort | UX |
|---|---|---|---|---|---|
| P1-1 | Targeted patching | `page.update(*controls)` + `ft.memo`/`use_memo`/`use_callback` | `main.py` flusher, progress bump sites | M | scan jank ↓ |
| P1-2 | `use_dialog` identity-preserving dialogs | `flet.use_dialog` (#6814 fix) | `app_shell.py` AlertDialog/BottomSheet | S | dialogs survive re-renders (cursor/focus) |
| P1-3 | **Client actions** (no Python round-trip) | `action=ft.OpenUrl(url)` / `ft.CopyToClipboard(data)` / `ft.ShareText(text)` — args precomputed at build | result cards, profile dialog, update dialog | S/button | snappier taps; fixes iOS Safari gesture gating |
| P1-4 | Biometric lock | separate pkg `flet-local-auth`: `LocalAuthentication().authenticate()` | History/settings gate | M (dep+perm) | optional app lock |
| P1-5 | `NativeAd` | `ft.NativeAd(unit_id, template_style=…)` | `ad_service.py` | M | higher-yield ad unit |
| P1-6 | **Offline font** | `page.fonts={"Outfit": "fonts/Outfit-Variable.ttf"}` (local asset path) | `main.py:228-234` | S | offline first paint, no webfont flash |
| P1-7 | TextField borders → `border=OutlineInputBorder(...)` | see §repairs | 4 screen sites | S | **[FIXED]** survives 1.3.0 removal |
| P1-8 | Consent order + `show_privacy_options_form` when REQUIRED | `ConsentManager` full API | `ad_service.py` | S | GDPR-correct revenue path |

Android risks: keep ads behind `is_mobile()` (they raise on desktop/web); InterstitialAd is
**one-shot** (new instance per show — our keep-alive pattern already does this); UMP
`request_consent_info_update()` must run first at every launch (it does).

---

## 2. P2 — holehe-v2 1.0.3 + curl-cffi 0.16.3

### Facts

- **181 validators** (`load_validators()` → `{name: async fn(email) -> Result}`), all
  module-owned clients; v2 core at `holehe_v2/core/{loader,runner,result,helpers,impersonate}.py`.
- Supply chain: **PyPI (1.0.3) is ahead of the public repo (frozen at 1.0.0)** — 2 commits,
  0 stars, license stub. Risk **MEDIUM** → pin `holehe-v2==1.0.3` via lock (done) and treat
  the 10 richest modules as smoke-test targets. curl-cffi risk LOW (active, MIT, ships
  **android arm64 wheels** — verified `cp314-android_24_arm64_v8a`).
- `run_all()` verdict: **do not use** — no callback, no cancel; only 1/181 honours
  `set_global_timeout()`; 18 impersonate-path modules have **no timeout at all**.

### Port (landed) — `src/services/email_service.py` **[FIXED]**

- Drives each validator under our `Semaphore(4..30)` + `asyncio.wait_for(timeout)` on the
  existing worker-thread/private-loop architecture; cancel Event + task-cancel path preserved.
- `Result` → buckets: `is_taken→found`, `is_available→not_found`, `is_error→` message
  classifier `_is_rate_limited` (`429|rate.?limit|waf|cloudflare|datadome|captcha|forbidden|
  bot challenge|ip flagged|403` word-bounded) → `rate_limited`, else `unavailable`.
  This **replaces** the old contextvar HTTP-status hack with v2's honest messages.
- `method_filter` **removed everywhere** (user decision — v2 has no method metadata);
  `no_password_recovery` kept (only `adobe` of the original 4 exists in v2).
- Enrichment arrives **in-band**: `Result.extra/media` → `EmailResult.others` (gravatar
  bio/verified_accounts/phones/emails, github login, etsy stats, avatar URLs — 4 media producers).
- Proxy: v2 ignores it (0/181 accept the param) → **env injection** (`HTTP(S)_PROXY`) scoped
  to the scan + `httpx[socks]` added so socks5 works (P5 found it was silently broken).
- Fingerprint: wrapped `impersonate_request_async` pre-load; stealth toggle now picks
  **chrome131** (UI labels updated) vs upstream chrome120.
- Domain: `urlparse(url)` or name-derived (`chess_com→chess.com`); walmart's prose-url bug
  and rappi's `reason=` TypeError handled/tested.

### Unused capabilities → proposals

| # | Proposal | Effort | UX |
|---|---|---|---|
| P2-1 | Stream `extra`/`media` into email dossier cards (avatar thumbnails, k/v fields) — extends results_screen's existing `others` rendering | M | richer email results |
| P2-2 | gravatar `profile_url` → real profile-URL enrichment (fixes the documented 0% email-enrichment gap for the ~1 producer that has one) | S | email mode gets avatars/bios |
| P2-3 | Fingerprint rotation per scan (chrome131 / chrome131_android / safari184…) — inventory in §2.1 | S | stealth ↑ |
| P2-4 | Pin + smoke-test the 10 richest validators in CI-live | S | regression safety |

### curl-cffi 0.16.3 fingerprint inventory (this wheel)

`edge99-101, chrome99-150 (+android99/131), safari153-2601 (+ios), firefox133-147, tor145`
+ aliases `chrome→chrome150, firefox→firefox147, safari→safari2601, chrome_android→chrome131_android`.
Rotation cost: new connection per fingerprint → keep ONE per scan.

---

## 3. P3 — maigret 0.6.6 + aiohttp stack + socid-extractor

### Facts

- DB census: **5,897 total / 5,203 enabled / 23 engines** (was 3,302/2,611) — app copy
  "3,300+"/"All 3.3k" is stale everywhere (README, pyproject description, settings labels,
  tests). ~300 sites (6%) bot-walled (`protection` tags) — the badge population.
- `maigret()` signature (`checking.py:1209-1234`) exposes **cookies, tor_proxy, i2p_proxy,
  check_domains, cloudflare_bypass, keywords, id_type, forced` — none wired today.
- **Connector injection: NOT possible** (checker built internally, `checking.py:337-344`,
  per-site sessions, no shared DNS cache — prewarm-300 warms a cache nobody reads). Clean
  fix = monkeypatch `SimpleAiohttpChecker.check` (same pattern as `_SilentBar`) with a
  shared connector (`ttl_dns_cache=300, limit_per_host=6`) or upstream PR `connector_kwargs`.
- socid-extractor: 164 schemes, 52 url_mutations; app harvests the display fields but leaves
  **all id-bearing schemes** (orcid, yandex, steam, 77 `*username` schemes) unused — they are
  the recursion fuel.

### Proposals

| # | Proposal (P3 design sketches in study source) | Theme | Effort | UX |
|---|---|---|---|---|
| P3-1 | **Recursive search, for real**: pass 2 via `maigret.maigret.extract_ids_from_results(container, db)` + `ranked_sites_dict(id_type=…)`, depth ≤2, cap 20 new targets, gated by the existing `state.recursive_search` toggle | features | M | **high** (advertised-but-dead toggle becomes real) |
| P3-2 | **Preset chips that re-query**: `ranked_sites_dict(tags=[…])` — coding 332, crypto 95, dating 47, gaming 518, social 803; country tags ru 1398/de 131/ua 126/us 115… (consider dropping `ru` from default row — dwarfs all) | features | M | high |
| P3-3 | **Deep-enrich toggle** (Off / Parse / Parse+Mutations): `is_enrich_enabled=True` → `run_url_mutations` (≤3 extra GETs per CLAIMED site, cap `MAX_MUTATIONS_PER_SITE=3`, cross-site filter); surface `enrich_requests` count in header | features | S | med (costs traffic — metered warning) |
| P3-4 | **Protection badges**: bridge `result.error` (CheckError `.type/.desc`) + `site.protection` into `SiteResult`; BOT set → "bot-walled", `Connecting failure` → "dead"; show `errors.py:solution_of()` advice on tap | UX | M | high (honest error triage) |
| P3-5 | **One-tap report exports** via `maigret.report` (CSV/TXT/JSON simple+ndjson/Markdown/HTML/XMind/Neo4j all work with installed deps; PDF needs absent `xhtml2pdf`) + `generate_report_context()` | features | M | high |
| P3-6 | **Sampled DB-health panel**: `self_check()` on N=50 random enabled sites off-scan-path; `get_db_stats()` counters (`sites.py:678-730`) → Coverage cards; auto-disable failing sites next-scan | features | M | med |
| P3-7 | Cookies jar TextField → `cookies=` (0.6.6 fixed multi-domain import); tor/i2p proxy fields; `check_domains` toggle desktop-only (aiodns dies on Android) | stealth | M | med |
| P3-8 | Shared-connector monkeypatch (`ttl_dns_cache=300`, `limit_per_host=6`) + keep prewarm; retune defaults: mobile scan depth → 500 (upstream default; full scans now 2× longer), max_connections 25 on metered | perf | M | med |
| P3-9 | `keywords=` field → KeywordMatch badge (`KeywordMatchStatus`) | features | S | low-med |

### Risks (P3 §G)

- **Pickle schema skew confirmed**: `MaigretSite` has no `__slots__`, but 0.6.6 added
  `stated_fields`/`url_regexp` with no class defaults → old pickles crash in
  `update_from_engine`. Version check **[FIXED]** + source-hash fix **[FIXED]**.
- 3,424 sites (58%) ship no `checkType` (engine-injected at load) — `ValueError Unknown check
  type` path at `checking.py:893-897` should be verified against executor worker error path.
- `#`-in-username now percent-encoded upstream (probe + display) — inherited automatically.

---

## 4. P4 — reporting cluster (reportlab, pillow, networkx, pyvis, xmind, jinja2, pycountry, lxml)

- **reportlab 5.0.1: all 8 of our imports verified present with unchanged signatures** —
  no breakage (tests green). `pillow>=9` now a hard dep (unconditional `from PIL import` in
  `lib/utils.py:15`) → 15 MB rides along with PDF feature.
- **networkx pinned <3.0.0 by maigret** (`METADATA:37`) — our call set is 3.x-safe
  (zero-kwarg `node_link_data`), upgrade blocked upstream only. Unused algos available now:
  **louvain** (alt-account clustering), **pagerank**, betweenness (cap-gate).
- **pyvis 0.3.2 (dormant, 2023)**: interactive viewer path = `Network(cdn_resources="in_line")`
  → self-contained HTML → needs **flet-webview** (no WebView in core flet; Markdown can't run
  JS) with url_launcher fallback. pyvis hard-imports `IPython.display.IFrame` at module top
  → ipython subtree cannot be pruned while maigret's graph report exists (unless stub-shimmed —
  P5 rates that **high risk**).
- **pycountry 20 MB of 22 MB is `locales/`** (gettext) — our calls (`countries.get`,
  `search_fuzzy`, `subdivisions`, `remove_accents`) are served by `databases/` only; nothing in
  `db.py` reads locales → **trim to `en` post-sync is safe** (smoke-test `flag`/`official_name`).
- jinja2: maigret ships `simple_report.tpl` — reusable shape for an offline HTML report.

| # | Proposal | Theme | Effort |
|---|---|---|---|
| P4-1 | Clickable PDF URLs (`<a href>`, drop 120-char truncation) | exports | S |
| P4-2 | Enrichment field/value Tables in PDF + XMind markers by evidence richness (priority-1..5, task-done) | exports | S |
| P4-3 | **Prune `pycountry/locales` → `en`** (~19 MB) + regression test | size | S |
| P4-4 | PDF footer/page numbers via `onLaterPages` + branded watermark | exports | S |
| P4-5 | Avatar thumbnails in PDF (PIL resize → `Image` flowable) | exports | M |
| P4-6 | **Interactive Graph Viewer** (pyvis in_line + flet-webview, clipboard fallback) | features | M |
| P4-7 | Louvain/PageRank identity analytics ("possible alt accounts") | features | M |
| P4-8 | Offline HTML report (vendored jinja2 template) — also unblocks **email-mode export** (app_shell hard-errors today) | exports | M |
| P4-9 | XMind relationships for shared evidence + fold Uncategorized | exports | M |
| P4-11 | XMind multi-sheet per category | exports | L |

---

## 5. P5 — dead weight + shared plumbing

### CRITICAL

- **`socks5://` was broken on every httpx path** — `socksio` absent → httpx raises
  `ImportError` on socks proxies, swallowed by broad excepts (silent no-proxy). aiohttp leg
  (main scan) and curl_cffi leg worked. → **fixed: `httpx[socks]` added [FIXED]**; shared-client
  work below completes it.

### Measured sizes (du, on-disk)

jedi 25M · pycountry 22M (locales 20M) · PIL 15M · networkx 11M · lxml 9M · reportlab 6.6M ·
pygments 5.5M · flet 4.6M · pyvis 3.8M · ipython-subtree ~33M total (shared pygments) ·
flask stack ~2.3M · alive-progress chain ~0.46M.

### Removal verdicts

| Target | Win | Mechanism | Risk |
|---|---|---|---|
| pycountry locales → `en` | ~19 MB | post-`uv sync` prune of staging dirs (exact placement pending P6's bundle-mechanism read) + keep `en/` dir present | med (data-only; smoke-test) |
| oauthlib | 0.7 MB | staging prune; function-level flet imports only (OAuth) | low |
| flask stack + click | ~2.3 MB | staging prune; only consumer is `maigret/web/app.py` | low |
| ipython subtree | ~33 MB | needs `IPython/display.py` IFrame stub after delete; breaks maigret graph-HTML only | **high** — behind APK `unzip -l` proof |
| alive-progress chain | 0.46 MB | **REJECT** — module-level import in `maigret/checking.py:16`, every scan needs it | high |
| msgpack-cache | 0 | **skip** — JSON debuggability wins | — |

### Plumbing proposals

| # | Proposal | Theme | Effort |
|---|---|---|---|
| P5-1 | **Shared httpx client**: `get_shared_client()` with `Limits(max_connections=50, keepalive=20)`, phased `Timeout`, `proxy=state.proxy_url` — replaces 3 throwaway pools (`update_service.py:61`, `cache_service.py:234`, email fallback) + socks fix | stealth/perf | S |
| P5-2 | pycountry locales prune (same as P4-3) | size | S |
| P5-3 | oauthlib prune | size | S |
| P5-4 | Bound `asyncio.to_thread` fan-out with `anyio.CapacityLimiter(8-16)` | perf | S |
| P5-5 | Lazy `networkx` import in `graph_service.py:17` (module-level today → RAM at startup) | perf | S |
| P5-6 | flask stack prune | size | S |
| P5-7 | ipython stub-prune (behind proof) | size | M/high |
| P5-C | CI size-report step (draft YAML in study) — `ls -l` artifacts + `du` top-15 + `unzip -l` prune verification | CI | S |

---

## 6. P6 — dev/test toolchain + flet build pipeline

- **Prune mechanism SOLVED**: flet packages deps via `dart run serious_python:package` with
  `-r <dep>` per **`project.dependencies`** (`build_base.py:2490-2531`) into
  `<build>/site-packages` — a post-build `rm` CANNOT shrink artifacts. The supported channel
  is **`[tool.flet.cleanup] package_files = [...]`** globs → `--cleanup-package-files`
  (`build_base.py:2679-2717`). `--exclude` is app-files only.
- **Dev deps never ship**: packager never reads `[dependency-groups]` — pytest/ruff cannot
  leak into artifacts; no flag needed.
- **Pytest hardening (P6-1)**: `strict_markers`, `strict_config`, `addopts=["-ra","-q"]`,
  `pytest-timeout>=2.4` + `timeout=60` for live hangs. **Warning policy (owner rule — no
  suppression, ever):** `filterwarnings` has NO `ignore` entries; warnings raised by OUR
  modules escalate to hard errors (must be fixed), third-party warnings print in every run's
  warnings summary and are never silenced. Do NOT add asyncio_mode or the flet pytest plugin
  (would provision a Flutter test host on every run — suite uses FakePage).
- **Ruff expansion (P6-2), measured**: adopt `UP,B,Q,C4,PERF,ERA,I,T20,DTZ` — counts
  UP 4 / I 18 / ERA 1 / C4 2 / PERF 3 (rest 0), all auto-fixable except 3 PERF401 rewrites +
  1 ERA reword → green. Reject `SIM(25: try/except/pass is our defensive style), RUF006
  (65 fire-and-forget tasks are correct Flet idiom), ARG(174 false positives), N(PascalCase
  components), S(605 — asserts in tests)`.
- **Offline font (P6-4)**: TTF → `src/assets/fonts/Outfit-Variable.ttf` (that's where
  `tool.flet.app.path="src"` + `assets_path=src/assets` points, `build_base.py:2047`), then
  `page.fonts={"Outfit": "fonts/Outfit-Variable.ttf"}` — relative asset paths are supported
  alongside URLs.
- Bytecode compile ON by default (`--compile-app/--compile-packages`); cleanup-packages ON;
  `FLET_LOG_LEVEL` is `flet run -v/-vv` only. Cheat-sheet: `flet run -v | flet clean |
  flet doctor | flet build apk --python-version 3.14 -v`.

| ID | Proposal | Theme | Effort |
|---|---|---|---|
| P6-1 | pytest strict config + warnings-as-errors + timeout | C | S |
| P6-2 | ruff UP/B/Q/C4/PERF/ERA/I/T20/DTZ adoption (+`--fix`) | C | S |
| P6-3 | pytest-timeout dev dep | C | S |
| P6-4 | Bundle Outfit TTF (offline first paint) | P | S |
| P6-5 | `[tool.flet.cleanup] package_files` prune list (enables P4-3/P5-3/P5-6 savings) | P | S |
| P6-6 | CI: `ruff --statistics` + artifact size-report + `unzip -l` prune verification | C | S |
| P6-7 | README dev cheat-sheet | C | S |

---

## 7. Demand-list → study crosswalk (TOP-10 from app audit)

| # | Demand item | Covered by | Status |
|---|---|---|---|
| 1 | Whole-tree re-render / 2 Hz flusher | P1 verdict: flusher stays; targeted patches + memo = the win (P1-1) | backlog |
| 2 | Non-preemptive sherlock cancel vs preemptive email cancel | email cancel preserved in port **[FIXED]**; sherlock drain noted, lower priority | partial |
| 3 | Dead `recursive_search` toggle | P3-1 design ready | backlog #1 candidate |
| 4 | Chrome-124 TLS staleness | chrome131 now; rotation P2-3 | **[FIXED]**/backlog |
| 5 | Proxy username-only | email env-proxy **[FIXED]** + socks **[FIXED]**; update/avatar still bare → P5-1 | partial |
| 6 | Export asymmetry (email/XLSX/graph/PDF top-10) | P4-1/4/5/6/8 + P3-5 | backlog |
| 7 | CI zero gates / holehe 1.61 pin / py3.12 drift | quality job + pin removal + py3.14 **[FIXED]** | done |
| 8 | Caps/truncations (history 50, cache 30, share 20, PDF 10) | revisit after features land | deferred |
| 9 | Mobile DNS fragility / prewarm-300 | P3-8 shared connector + P1-6 font | backlog |
| 10 | Rate-limit noise / thin error UX | v2 taxonomy **[FIXED]** + P3-4 badges | partial |

---

## 8. Consolidated ranked backlog

*Final ranking (all six packets in). Themes:* **F**=features/exports · **P**=perf/size ·
**S**=stealth/networking · **C**=CI/quality.

| Rank | ID | Item | Theme | Effort |
|---|---|---|---|---|
| 1 | P6-1/2/3 | Toolchain hardening: pytest strict+warnings-as-errors+timeout, ruff UP/B/Q/C4/PERF/ERA/I/T20/DTZ | C | S |
| 2 | P6-5 + P4-3/P5-3/6 | `[tool.flet.cleanup] package_files` prune list: pycountry locales→en, oauthlib, flask (~21 MB) | P | S |
| 3 | P6-4 | Bundle Outfit TTF → `src/assets/fonts/` (offline first paint) | P | S |
| 4 | P5-1 | Shared httpx client + proxy-everywhere (update/avatar) | S/P | S |
| 5 | P6-6 | CI: ruff --statistics + size report + unzip prune verification | C | S |
| 6 | copy | "3,300+" → "5,200+" everywhere (README, pyproject, settings, tests, version.json) | C | S |
| 7 | P3-1 | **Recursive search** (real, via extract_ids_from_results) | F | M |
| 8 | P3-2 | Preset chips that re-query (tags= engine filter) | F | M |
| 9 | P3-4 | Protection badges (CheckError bridge) | F | M |
| 10 | P4-1/2/4 | PDF polish: clickable URLs, enrichment tables, footer | F | S |
| 11 | P3-5 | One-tap report exports (maigret.report suite) | F | M |
| 12 | P4-8 | Offline HTML report + email-mode export | F | M |
| 13 | P1-3 | Client-action buttons (open/copy/share) | F | S |
| 14 | P3-8 | Shared DNS connector + mobile depth-500 default | P/S | M |
| 15 | P2-1/2 | Email dossier extras/avatars + gravatar enrichment | F | M/S |
| 16 | P1-1 | Targeted `page.update(*controls)` flush | P | M |
| 17 | P4-6 | Interactive graph viewer (flet-webview) | F | M |
| 18 | P4-7 | Louvain/PageRank alt-account analytics | F | M |
| 19 | P3-3 | Deep-enrich toggle (mutations) with metered warning | F | S |
| 20 | P2-3 | Fingerprint rotation (chrome131_android on mobile) | S | S |
| 21 | P1-2 | use_dialog for scan-surviving dialogs | P | S |
| 22 | P3-6 | Sampled DB-health panel | F | M |
| 23 | P3-7 | Cookies jar + tor/i2p fields | S | M |
| 24 | P1-5 | NativeAd experiment | S/C | M |
| 25 | P1-4 | flet-local-auth biometric lock | F | M |
| 26 | P5-4/5 | anyio limiter + lazy networkx | P | S |
| 27 | P5-7 | ipython stub-prune (behind APK proof) | P | M/high |
| 28 | P6-7 | README dev cheat-sheet | C | S |

---

## 9. Phase 2 repairs log (landed in this update)

1. **Bump + sync**: flet/flet-ads 1.0.1, maigret 0.6.6, holehe-v2 1.0.3, reportlab 5.0.1,
   socksio 1.0.0; dead weight removed with old holehe (trio/tqdm/bs4/termcolor/outcome…).
2. **CI quality gate**: version-consistency check (pyproject ↔ version.json ↔ workflow),
   ruff + `pytest -m "not live"` gate before any build; `holehe==1.61`/`stem` pre-compile and
   Python 3.12 pins removed; metainfo copy refreshed; `build_number` dispatch default fixed.
3. **Email port to holehe-v2** (§2) — email mode restored, method-filter removed, proxy +
   chrome131 fingerprint wired, 181-module dynamic totals, 26 new/updated tests.
4. **flet 1.0 migrations**: boot_screen schema, 4× TextField borders, ElevatedButton in test
   helper, client_storage verified.
5. **Cache hardening**: maigret_version validation on load + source-hash comparison fix +
   site-count assertion refresh.
6. **Housekeeping**: phantom `sherlock-app` workspace member removed.

## 10. Implementation status (landed in v2.2.0 / build 12)

**Wave A**: toolchain hardening (pytest strict config, module-scoped warnings-as-errors with
**zero ignore entries** per owner rule, ruff UP/B/Q/C4/PERF/ERA/I/T20/DTZ, pytest-timeout) ·
`[tool.flet.cleanup] package_files` prune list (~21 MB: pycountry locales, oauthlib, flask
stack) · bundled Outfit font (offline first paint) · proxy threaded through update/avatar
httpx paths + avatar logs promoted to visible INFO/WARNING · CI `ruff --statistics` + artifact
size report + APK prune verification · copy sweep 3,300+→5,200+ / 121→181 (historical
changelog/version records untouched).

**Wave B**: **recursive search** (opt-in, depth-2 by construction, 20-target cap, 500-site
username scope, full-DB for rare id types, staleness-safe target appending) · **protection
badges** (CheckError bridge → WAF status, typed chips, `solution_of` advice line, protection
shield, keyword-hit chips, snapshot round-trip) · **category presets** (Dating + FR/GB/JP/IN
chips, "Scope to Filter" button via the O(1) tag index → selected-sites persistence).

**Wave C**: PDF tappable URLs (no truncation) + gold footer/page numbers + enrichment
field-tables + XMind evidence markers · **email-mode exports** CSV/JSON/TXT (replaces the
hard-error) with visible guidance for PDF/XMind · holehe-v2 `Result.extra/media` rendering
(avatars + ≤6 fact lines per card).

**Version**: 2.2.0 / build 12 consistent across pyproject, version.json, workflow defaults —
CI version gate passes. Suite: **212 passed + 1 live deselected, ruff clean, no ignored
warnings**.

**Wave D (owner: "do everything")**: every deferred item landed —
**P1-1** use_memo active-tab card lists (one hook per mode branch, membership-keyed) ·
**P1-2** use_dialog portals for AppShell export/graph dialogs + History confirm (page-overlay
dialogs in profile/update/settings keep show_dialog — they're re-render-immune and converting
them requires cross-file close-callback threading for zero behavioral gain) ·
**P1-3** client-side `ft.OpenUrl` actions with a page-context fallback (`core/actions.py` —
actions bind services at construction, so out-of-app builds fall back to the Python launcher
with its visible errors; copy operations stay Python-side for live-state payloads) ·
**P1-4** biometric History lock (`flet-local-auth` dep + service + Settings toggle + unlock UI +
`USE_BIOMETRIC` permission) · **P1-5** NativeAd preview in Settings/Troubleshooting (Google
TEST unit, mobile-gated, honest failure messages) · **P2-2** email avatar-cache warming ·
**P3-3** Deep Enrichment toggle (`is_enrich_enabled`, mutation-traffic logged per pass) ·
**P3-6** sampled DB-health check (Settings button → 25-site probe → persist flags → excluded on
load, healthy run clears) · **P3-7** cookies/tor/i2p fields + desktop-only domain-check toggle ·
**P3-8** aiohttp connector patch (ttl_dns_cache=300s — prewarm now actually reused) + mobile
scan-depth default 500 · **P3-9** keywords field (KEYWORD badge already bridged) ·
**P4-6** interactive graph viewer (pyvis inline HTML → browser; 700 KB self-contained file) ·
**P4-7** evidence communities + capped betweenness in analytics dialog · **P4-8/P3-5**
Markdown + HTML dossiers (username **and** email modes, export sheet entries, cache-tiered) +
graph Cypher copy · **P4-5** cached-avatar embeds in PDF enrichment cards ·
**P4-9/P4-11** XMind shared-evidence relationships, folded Uncategorized, per-category sheets ·
**P5-1** shared pooled httpx client (proxy-keyed rebuild, closed on page close, per-test reset) ·
**P5-4** anyio CapacityLimiter(12) on enrichment thread offload · **P6-7** README dev
cheat-sheet.

**P1-5 NativeAd preview REMOVED at owner's direction (2026-09-23)**: ads must never be
user-toggleable — Sherlock's monetization is untouchable; `ad_service.py`/`banner_ad.py` are
byte-identical to their pre-update state (verified: empty git diff vs the original commit).
**Defaults restored at owner's direction**: the mobile Top-500 scan-depth default was reverted —
`scan_depth` defaults to `"all"` everywhere, exactly as before the update; new features are all
opt-in/off so out-of-the-box behavior matches the pre-update app.

**P5-7 remains physically blocked** (not deferred by choice): pyvis imports
`IPython.display` at module top; serious_python's cleanup channel only *deletes* files (no
negation/stub support — verified in `build_base.py`), so a partial IPython tree can't be
shipped. Unblocking requires a pyvis fork/override. The CI `/jedi/` probe in the size-report
step measures its presence on every build so the ~33 MB cost stays visible.
