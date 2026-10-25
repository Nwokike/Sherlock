# user-scanner 1.5.2.3 — Installed-Source Dependency Audit

**Audited package:** `user_scanner` 1.5.2.3
**Source of truth:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/user_scanner`
**Audit date:** 2026-10-20
**Scope:** every core file, the CLI surface, the on-disk module tree, and the Sherlock-V3 wrapper (`src/services/user_scanner_compat.py` + its callers).
**Background doc (V2-era, unverified):** `docs/reference/dep-user-scanner.md` — cross-checked in §1.6.

> Verdict in one line: **ISSUES FOUND — 18 defects, 12 unused capabilities.** The wrapper is structurally sound and re-implements the CLI-coupled orchestrators well, but five of the defects (Hudson Rock, email proxy injection, thread-pool starvation, stale-proxy leak, cross-scan scope) are parity-critical: they make the app measurably *less* capable than the `user-scanner` CLI it wraps.

---

## 1. Installed API verification

### 1.1 Real counts (counted on disk, not from the background doc)

| Tree | Categories | Modules |
|---|---|---|
| `user_scan/` | **17** | **2,521** |
| `email_scan/` | **20** | **220** |
| **Total vectors** | **37** | **2,741** |

`user_scan/` per category — `adult` 22, `community` 576, `creative` 144, `creator` 41, `dating` 8, `dev` 455, `donation` 7, `email` 1, `entertainment` 108, `finance` 151, `gaming` 198, `learning` 267, `music` 125, `other` 79, `political` 4, `shopping` 56, `social` 279.

`email_scan/` per category — `adult` 17, `community` 5, `creator` 13, `crm` 4, `dating` 11, `dev` 21, `entertainment` 13, `fitness` 5, `gaming` 5, `hosting` 2, `jobs` 14, `learning` 29, `music` 5, `news` 8, `other` 14, `shopping` 18, `social` 18, `sports` 7, `travel` 4, `women_health` 7.

Module-library composition (grep over the trees):

| Pattern | Count | Meaning |
|---|---|---|
| `user_scan/**` importing `core.orchestrator` | 2,455 | use `make_request` / `generic_validate` / `status_validate` |
| `email_scan/**` using `httpx.AsyncClient` | 180 | rely on the **global monkeypatch** for proxy + timeout |
| `email_scan/**` with **no** `proxy=` kwarg | **180 / 180** | proxy comes *only* from the monkeypatch |
| `user_scan/**` importing `core.impersonate` | 68 | curl_cffi TLS impersonation (bypasses DataDome/Cloudflare) |
| `email_scan/**` importing `core.impersonate` | 39 | curl_cffi TLS impersonation |
| `user_scan/**` + `email_scan/**` using `core.nextjs` | 16 | App-Router/Pages-Router extraction |

### 1.2 `core/engine.py` — verified signatures

```python
_shared_executor = concurrent.futures.ThreadPoolExecutor(max_workers=60)          # engine.py:10

async def check(module: ModuleType, target: str) -> Result                        # engine.py:12
async def check_category(category_name: str, target: str, is_email: bool = True) -> List[Result]   # engine.py:45
async def check_all(target: str, is_email: bool = True) -> List[Result]           # engine.py:59
```

- `check()` derives `func_name = f"validate_{module.__name__.split('.')[-1]}"` (engine.py:14) — i.e. it requires the *exact* `validate_<stem>` name, whereas `helpers.get_scan_func()` accepts **any** `validate_*` attribute. `engine.check` is the stricter of the two.
- `check_category` / `check_all` use `asyncio.gather` with **no semaphore** — unbounded fan-out. This is precisely why the app's own driver (bounded, cancellable) is the right call, and why `engine.py` is correctly *not* used by the wrapper.

### 1.3 `core/helpers.py` — verified surface

| Symbol | Signature | Line |
|---|---|---|
| `ScanConfig` | frozen dataclass: `allow_loud=False, no_nsfw=False, show_all=False, verbose=False, timeout=None` | 447-453 |
| `set_global_timeout` / `get_global_timeout` | `(Optional[float]) -> None` / `-> Optional[float]` (module global `_global_timeout`) | 457 / 461 |
| `is_valid_email` | `(email: str) -> bool` (RFC-5322-ish, max 254 / local 64 / domain 253) | 465 |
| `parse_email_domain_scopes` | `(value: str) -> tuple[str, ...]`; raises `ValueError` on unknown scope; `"all"` expands to every scope | 474 |
| `get_site_name` | `(module) -> str` — stem `.capitalize()`, `_`→`.`, `"X"`→`"X (Twitter)"` | 496 |
| `load_modules` | `(category_path: Path) -> List[ModuleType]`, `@lru_cache`, **no try/except around `exec_module`** | 503-517 |
| `load_categories` | `(is_email=False, no_nsfw=False) -> Dict[str, Path]`, `@lru_cache`; skips `adult` when `no_nsfw` | 519-536 |
| `is_loud` | `(name: str, is_email: bool = False) -> bool` | 538 |
| `get_scan_func` | `(module) -> Optional[Callable[[str], Any]]` (any `validate_*`) | 543 |
| `find_module` | `(name, is_email=False, no_nsfw=False) -> List[ModuleType]` (matches **module stem**, case-insensitive) | 554 |
| `find_category` | `(module) -> str \| None` (capitalised parent folder) | 565 |
| `validate_proxies` | `(proxy_list, timeout=5, max_workers=50) -> List[str]` (gstatic 204 probe) | 603 |
| `ProxyManager` | `(proxy_file=None, proxies=None)`; `get_next_proxy` (round-robin, locked), `get_random_proxy`, `count`; normalises missing scheme → `http://` | 608-673 |
| `set_proxy_manager` | `(proxy_file=None, proxies=None) -> None` — `None/None` **clears** the global | 680 |
| `get_proxy` / `get_proxy_count` | `-> Optional[str]` / `-> int` | 689 / 696 |
| `get_random_user_agent` | `-> str` (9 hard-coded UAs) | 706 |
| `load_config` / `save_config_value` | `(path=None) -> dict` / `(key, value, path=None)`; path = `USER_SCANNER_CONFIG` env → `user_scanner/config.json` | 738 / 758 |
| `LOUD_MODULES` | `{"user": [] (0), "email": [53 entries / 52 unique]}` | 27-84 |
| `EMAIL_DOMAIN_SCOPES` | **41 scopes / 273 domains** (`global` = 32 domains) | 86-442 |

### 1.4 Orchestrators — verified

`core/orchestrator.py` (username):
- `MAX_CONCURRENT_REQUESTS = 60` (line 27); `_shared_executor = ThreadPoolExecutor(max_workers=max(60*2, 250))` (line 28).
- `set_concurrency(val: int)` (line 30) — `ValueError` if `< 1`; reallocates the executor.
- `async _async_worker(module, username, sem, configs, printed_cats=None, cat_override=None, on_start=None) -> Result` (line 37). Loud check at 62; `module_timeout = (get_global_timeout() or 15.0) + 10.0` at 66; `on_start(site_name)` callback at 48-49.
- `run_user_module(module|List[module], username, configs) -> List[Result]` (165); `run_user_category(category_path, username, configs)` (172); `run_user_full(username, configs)` (259).
- `make_request(url, **kwargs) -> httpx.Response` (279) — Chrome-141 headers, timeout = `get_global_timeout()` else 5.0, proxy from `get_proxy()`, cached `httpx.Client` per `(http2, proxy, verify)`, `max_retries = 0` hard-coded (309).
- `generic_validate(url, func, **kwargs) -> Result` (319); `status_validate(url, available, taken, **kwargs) -> Result` (337).

`core/email_orchestrator.py` (email):
- **Import-time monkeypatch** of `httpx.AsyncClient.__init__` and `httpx.Client.__init__` (lines 23-52) injecting `get_proxy()` and `get_global_timeout()`. This is the *only* way 180 email modules get a proxy.
- `MAX_CONCURRENT_REQUESTS = 25` (56); `set_concurrency(val)` (58).
- `async _async_worker(module, email, sem, configs, printed_cats=None, cat_override=None, on_start=None) -> Result` (64) — same shape as the user one.
- `run_email_module_batch(module|List, email, configs)` (205); `run_email_category_batch(category_path, email, configs)` (233); `run_email_full_batch(email, configs)` (314).
- **Line 198-200**: `_run_email_module_batch_async` explicitly does `loop.set_default_executor(ThreadPoolExecutor(max_workers=250))` — this is the 250-thread pool the app is missing (see B3).

### 1.5 Remaining core modules — verified

**`core/cross_scan.py`**
```python
@dataclass(frozen=True)
class CrossScanConfig:
    links: str = "all"          # all | verified | none
    modules: Tuple[str, ...] = ()
    categories: Tuple[str, ...] = ()
    emails: str = "verified"    # all | verified | none
    sweep: int = 3              # DEFAULT_SWEEP
    depth: int = 1              # DEFAULT_DEPTH

def run_cross_scan(results: List[Result], configs: ScanConfig, cross_configs: CrossScanConfig) -> List[Result]   # line 82
```
Private helpers the wrapper reuses: `_scope` (187), `_email_scope` (210), `_already_swept` (254), `_fresh_pivots` (265), `_already_scanned` (282), `_fresh_emails` (292), `_followable` (304), `_split_budget` (318), `_sweep_targets` (333), `_email_targets` (362), `_named_targets` (413), `_tag` (455), `_tag_emails` (475), `_apply_confidence` (484), `_print_summary` (520). **All 15 exist in the installed source** — the wrapper's private imports are valid, no hallucinated symbols.

**`core/confidence.py`** — `Confidence(Enum)`: `CONFIRMED`, `LIKELY`, `CANDIDATE`, `CONFLICTING`; `ORDER` tuple (80); `Anchors` frozen dataclass; `RankedEmail` dataclass; `build_anchors`, `score`, `rank_emails`.

**`core/pivots.py`** — registries: `HANDLE_KEYS` (25), `VERIFIED_KEYS` (41), `PLATFORM_HANDLE_KEYS` (49), `EMAIL_KEYS` (77), `_ROLE_LOCAL_PARTS` (92), `_NON_MAILBOX_DOMAINS` (109), `_MEDIA_KEY_PARTS` (124), `_HOST_ROUTES` (168), `_SUBDOMAIN_ROUTES` (266), `_RESERVED` (144). Enums `PivotKind` (HANDLE/VERIFIED/LINK) and `EmailKind` (FIELD/LINK); `Pivot`, `EmailPivot` dataclasses; `extract_pivots`, `select_pivots`, `extract_email_pivots`, `select_email_pivots`, `rank_usernames`, `resolve_url`, `is_platform_host`, `module_stem`, `is_media_key`.

**`core/hudson.py`** — `update_hudson_preference(show_prompt: bool)` (15); `check_hudson_permission(target: str) -> bool` (22) — **calls `input()`** when `auto_hudson_prompt` is true; `run_hudson_scan(target: str, is_email: bool = False)` (49).

**`core/patterns.py`** — `expand_patterns(input) -> Iterator[str]` (178); `expand_patterns_random(input, capacity=1000) -> Iterator[str]` (195, reservoir sampling); `count_patterns(input) -> int` (225, O(blocks)).

**`core/result.py`** — `Status(Enum)` `TAKEN=0, AVAILABLE=1, ERROR=2, SKIPPED=3` with `to_label(is_email)`; `Result` with factories `taken/available/error/skipped/from_number`; `update(**kwargs)`; `as_dict/to_dict/to_json/to_csv`; `has_reason/get_reason`; `is_found`; `is_visible(configs)`; `get_console_output(configs)`; `show(configs)`; `_neutralize_csv_cell` (26-34) — **CSV-formula-injection guard**; `CSV_FIELDS` (23).

**`core/formatter.py`** — native export functions: `into_json(results)` (9), `get_json_data(results)` (13), `into_csv(results, include_header=True)` (18), `into_pdf(results, target, scan_type, total_modules, include_media, version)` (22).

**`core/pdf_generator.py`** — availability flags (import-guarded, module imports cleanly without them):
`RICH_AVAILABLE=True` (16), **`REPORTLAB_AVAILABLE=False`** (26), **`PIL_AVAILABLE=False`** (32), **`SVGLIB_AVAILABLE=False`** (38).
`generate_pdf_report()` raises `ImportError` when `REPORTLAB_AVAILABLE` is false (254-258). Confirmed: `reportlab`, `PIL`, `svglib` are **not installed** in the V3 venv (curl_cffi 0.16.3, httpx 0.28.1, rich, colorama 0.4.6 are). So `formatter.into_pdf` is **unavailable** — but `is_safe_ip` / `is_safe_media_url` (69-127), the SSRF guardrails, **are importable and unused by the app**.

**`core/impersonate.py`** — `impersonate_validate`, `impersonate_request`, `get_warm_session`, `get_impersonate_timeout`, `impersonate_request_async`. `impersonate_request` reads `get_proxy()` directly (56), so impersonating modules **do** honour the proxy.

**`core/loud_prompt.py`** — `update_loud_module_preference(show_prompt)`, `check_loud_module_permission(site_name, target) -> bool`. Note line 33: `if not sys.stdin.isatty()` → skips without prompting. **`core/hudson.py` has no such guard** — that asymmetry is the root of B1.

**`core/nextjs.py`** — `parse_next_pages_data`, `iter_next_app_flight_chunks`, `parse_next_pages_redirect`.

**`core/version.py`** — `load_local_version()`, `get_pypi_version(url)`.

### 1.6 CLI parity — all 30 flags in `__main__.py`

`-u/--username` · `-e/--email` · `-uf/--username-file` · `-ef/--email-file` · `-c/--category` · `-m/--module` · `-lu/--list-user` · `-le/--list-email` · `--list-email-domains` · `--email-domains` · `-v/--verbose` · `--all` · `-s/--stop` (default 100) · `-t/--timeout` · `-C/--concurrency` · `-d/--delay` (default 0) · `-f/--format {csv,json,pdf}` · `--no-pdf-media` · `-o/--output` · `-P/--proxy-file` · `--validate-proxies` · `--allow-loud` · `--no-nsfw` · `--cross-scan` · `--cross-links` · `--cross-emails` · `--cross-depth` · `--cross-sweep` · `-U/--update` · `--hudson/--hudson-scan` · `--version`.

### 1.7 Discrepancies vs. the V2 background doc (`docs/reference/dep-user-scanner.md`)

| Doc claim | Installed truth | Verdict |
|---|---|---|
| §5.5 "**26** geographic and regional scopes"; "global: **31** major providers" | **41** scopes, **273** domains total, global = **32** | **Doc is wrong** (its own scope list enumerates 41 names) |
| §2 "220 email verification modules (**20** categories)" | 220 modules / **20** categories | ✓ correct |
| §2 "2,521 username modules (17 categories)" | 2,521 / 17 | ✓ correct |
| §10.1 "`load_modules()` all user categories ≈ 62.5 s" | V2 machine, not re-measured here | unverified (directionally right — it is a 62-second UI freeze) |
| §11.1 "use `engine.check(module, target)`" | `engine.check` requires the exact `validate_<stem>` name and has no timeout/loud/cancel | **Doc's advice is weaker than what the app actually does** — the app's own driver is better |
| §11.4 "pre-warm the module cache in a background thread" | still true; the app's `_load_modules_tolerant` (user_scanner_compat.py:61) has **no lru_cache**, so it re-imports on every `load_sites(force=True)` | **Doc's mitigation is unimplemented in V3** — see §4, item 13 |
| §10.2 "load_modules has no try/except → one bad file kills a category" | confirmed at helpers.py:513 | ✓ correct; the app correctly avoids it (compat.py:61-83) |

---

## 2. Wrapper mapping table

`src/services/user_scanner_compat.py` (552 lines) is the **only** module that imports user-scanner internals. Mapping of every wrapped symbol:

| # | Wrapper symbol (src/) | Installed API | Signature match | Return | Verdict |
|---|---|---|---|---|---|
| 1 | `load_user_modules(no_nsfw=False)` → `user_scanner_compat.py:33` | `helpers.load_categories(is_email=False, no_nsfw=…)` | ✅ | `list[tuple[str, ModuleType]]` | ✅ correct (but no cache — §4-13) |
| 2 | `load_email_modules(no_nsfw=False)` → `:43` | `helpers.load_categories(is_email=True, …)` | ✅ | same | ✅ correct |
| 3 | `load_phone_modules()` → `:52` | `phonsint.core.helpers.load_categories()` | ✅ | same | ✅ (out of scope) |
| 4 | `_load_modules_tolerant(path)` → `:61` | replaces `helpers.load_modules` | ✅ (deliberate) | `list[ModuleType]` | ✅ **better than upstream** |
| 5 | `get_site_name_user(module)` → `:86` | `helpers.get_site_name` | ✅ | `str` | ✅ |
| 6 | `get_scan_func_user(module)` → `:91` | `helpers.get_scan_func` | ✅ | `Optional[Callable]` | ✅ |
| 7 | `is_loud_user(name, is_email=False)` → `:96` | `helpers.is_loud` | ✅ | `bool` | ✅ |
| 8 | `run_username_scan(username, modules, on_result, cancel_event, timeout=10, concurrency=50, allow_loud=False, no_nsfw=False, selected=None, proxy=None)` → `:116` | *no upstream equivalent* — re-implements `orchestrator._async_worker` | ⚠️ `no_nsfw` **unused** (B5) | `None` | ⚠️ **partial** |
| 9 | `_run_one_user(...)` → `:182` | mirrors `orchestrator._async_worker` | ✅ shape; ❌ executor (B3) | `tuple` | ⚠️ **partial** |
| 10 | `run_email_scan(email, modules, on_result, cancel_event, timeout=10, concurrency=15, allow_loud=False, proxy=None)` → `:220` | mirrors `email_orchestrator._async_worker` | ✅ shape; ❌ executor (B3), ❌ proxy patch (B2) | `None` | ⚠️ **partial** |
| 11 | `_run_one_email(...)` → `:261` | same | ✅ / ❌ | `tuple` | ⚠️ **partial** |
| 12 | `run_phone_scan(...)` → `:299` | phonsint | ✅ | `phone_info` | ✅ |
| 13 | `run_cross_scan_async(initial_results, all_user_modules, all_email_modules, cross_config, on_result, cancel_event, timeout=10, concurrency=50, allow_loud=False, no_nsfw=False, proxy=None)` → `:386` | re-implements `cross_scan.run_cross_scan` using 12 private helpers | ✅ all 12 private imports exist | `list[Result]` | ⚠️ **partial** — scope ignored (B8) |
| 14 | `SherlockService.run_hudson(target, is_email=False)` → `sherlock_service.py:276` | `hudson.run_hudson_scan(target, is_email)` | ✅ signature | `str` (captured stdout) | ❌ **broken** (B1) |
| 15 | `EmailService.run_hudson(target, is_email=True)` → `email_service.py:414` | same | ✅ | `str` | ❌ **broken** (B1) |
| 16 | `EmailService.validate_email` → `email_service.py:28` | `helpers.is_valid_email` | ✅ | `bool` | ✅ |
| 17 | `sherlock_service.load_sites` → `sherlock_service.py:101` | `helpers.set_global_timeout` | ✅ | `int` | ✅ |
| 18 | `email_service.search` → `email_service.py:255` | `helpers.set_global_timeout` | ✅ | — | ⚠️ global bleed (B17) |
| 19 | `email_service.search` → `email_service.py:262` | `helpers.set_proxy_manager(proxies=[proxy])` | ✅ signature | — | ⚠️ **ineffective** (B2), never cleared (B4) |
| 20 | `home_screen._validate_proxy` → `home_screen.py:555` | `helpers.validate_proxies` | ✅ | `list[str]` | ✅ |
| 21 | `settings_screen` proxy validate → `settings_screen.py:666` | `helpers.validate_proxies` | ✅ | `list[str]` | ✅ |
| 22 | `main.py` email-domain generation → `main.py:1071` | `helpers.parse_email_domain_scopes` | ✅ | `tuple[str,…]` | ⚠️ capped at 5 (B12) |
| 23 | `sherlock_service._map_username_result` → `sherlock_service.py:299` | `result.Status` / `Result.get_reason` | ✅ (after the dead code at 304-308) | `SiteResult` | ⚠️ **vestigial code** (B13) |
| 24 | `email_service._map_result` → `email_service.py:112` | `result.Status`, `Result.extra`/`.media` | ✅ | `EmailResult` | ✅ |
| 25 | `sherlock_service` cross-scan config → `sherlock_service.py:224` | `cross_scan.CrossScanConfig` | ✅ but `modules`/`categories` never set (B8) | — | ⚠️ **partial** |
| 26 | `email_service` cross-scan config → `email_service.py:375` | same | ✅ / ⚠️ | — | ⚠️ **partial** |
| 27 | `app` export paths | `formatter.into_json/into_csv/into_pdf`, `Result.to_dict/to_json/to_csv` | ❌ **none used** | — | ❌ **unused** (B18, B16) |

**Not wrapped at all (verified absent from `src/`):** `core/engine.py` (check/check_category/check_all), `core/patterns.py` (all three functions), `core/formatter.py` (all four), `core/pdf_generator.py` (`is_safe_ip`/`is_safe_media_url`/`generate_pdf_report`), `core/impersonate.py` (direct), `core/loud_prompt.py`, `core/nextjs.py` (direct), `core/version.py`, `helpers.set_concurrency`, `helpers.set_proxy_manager(proxy_file=…)`, `helpers.get_proxy_count`, `helpers.load_config`/`save_config_value`, `helpers.find_module` (direct), `helpers.find_category` (only inside the cross-scan path), `helpers.EMAIL_DOMAIN_SCOPES` (only the parser is used), `mcp/` server, `cli/tips.py`.

---

## 3. Bugs & hallucinations (all in `src/`)

### P0 — parity-critical (the app is worse than the CLI it wraps)

**B1 · Hudson Rock is completely non-functional in the GUI.**
`sherlock_service.py:276-290` and `email_service.py:414-427` call `hudson.run_hudson_scan(target, is_email=…)`, which calls `hudson.check_hudson_permission(target)` (`core/hudson.py:54`).
`core/hudson.py:26-28` reads `auto_hudson_prompt` from `user_scanner/config.json`, which ships **`true`** → the `input()` at `core/hudson.py:36` is reached.
Verified empirically: with stdin closed, `check_hudson_permission` raises **`EOFError: EOF when reading a line`** → swallowed by `sherlock_service.py:288` → the user gets the snackbar `"Hudson check failed: EOF when reading a line"`. On a dev machine with a TTY, `input()` **blocks the worker thread forever**, and because `sherlock_service.py:285` redirects stdout into a `StringIO`, the prompt text is swallowed and the user never sees the question. The feature is 100 % dead either way.
Note the asymmetry: `core/loud_prompt.py:33` has an `if not sys.stdin.isatty(): return False` guard; `core/hudson.py` has none.
*Fix:* never call `run_hudson_scan` unguarded. Either set `hudson.update_hudson_preference(False)` (`core/hudson.py:15`) once at startup and drive consent from a Flet dialog, or reimplement the 20-line query in `sherlock_service` and call the API directly.

**B2 · 180 of 220 email modules never receive the configured proxy.**
`core/email_orchestrator.py:23-52` monkeypatches `httpx.Client.__init__` / `httpx.AsyncClient.__init__` to inject `get_proxy()` and `get_global_timeout()`. The app never imports that module on the normal email path — it is only pulled in transitively through `core/cross_scan.py:26`, and the app imports `cross_scan` **lazily inside the cross-scan-enabled branch** (`sherlock_service.py:223`, `email_service.py:368`).
Verified empirically: `httpx.Client.__init__` is unpatched after `import user_scanner.core.helpers`, and patched only after `import user_scanner.core.cross_scan`.
180 email modules construct `httpx.AsyncClient(...)` with **no `proxy=` argument** (all 180 of the 180 that use `AsyncClient`), so with cross-scan off they go out **direct** — the proxy in Settings is a no-op for 82 % of the email vector. The 39 impersonate-based modules *do* get the proxy (`core/impersonate.py:56`).
*Fix:* `import user_scanner.core.email_orchestrator` unconditionally at the top of `services/user_scanner_compat.py`.

**B3 · Thread-pool starvation — 8 concurrent module executions instead of 250.**
`user_scanner_compat.py:203` and `:282` use `loop.run_in_executor(None, func, …)` → the **default** executor, sized `min(32, cpu+4)`. This machine has 4 CPUs → **8 workers**.
Upstream: `core/orchestrator.py:28` → `ThreadPoolExecutor(max_workers=max(60*2, 250))`; `core/email_orchestrator.py:198-200` → `loop.set_default_executor(ThreadPoolExecutor(max_workers=250))`.
The wrapper's semaphore allows up to 200 (user, `:150`) / 30 (email, `:244`) concurrent tasks, but only 8 can actually be in flight. Over 2,521 blocking modules that is roughly a **25–30× throughput loss** versus the CLI. The upstream executor is the *reason* upstream can sweep 2,521 sites in a reasonable time.
*Fix:* own a `ThreadPoolExecutor(max_workers=max(concurrency*2, 250))` in the compat module and pass it to `run_in_executor`.

**B4 · The global proxy manager is never cleared → a stale proxy leaks into later scans.**
`user_scanner_compat.py:130-135`: `if proxy: set_proxy_manager(proxies=[proxy])` — no `else`. `core/helpers.py:680-686` supports `set_proxy_manager(None, None)` to clear, but the app never calls it.
Consequence: scan with a proxy → clear the proxy field → every later scan still routes through the old proxy. `email_service.py:262-265` has the same shape.
*Fix:* `set_proxy_manager(proxies=[proxy] if proxy else None)` unconditionally.

**B5 · The cross-scan ignores the user's site selection (and upstream's `-m`/`-c` scope).**
`user_scanner_compat.py:492`: `named = _named_targets(pivots, swept, checked, scan_cfg, None)` — the `scope` argument is hard-coded `None`, so the site restriction is dropped.
`user_scanner_compat.py:450-457`: `usable_email_modules` is built from **all** email modules, ignoring `cross_config.modules` / `cross_config.categories`.
Upstream honours both: `core/cross_scan.py:187-207` (`_scope`) and `:210-251` (`_email_scope`).
The app never populates those fields either (`sherlock_service.py:224-229`, `email_service.py:375-380`).
Consequence: a user who selected 5 sites in the Sites screen still triggers a **full 2,521-module sweep** in the cross-scan round.
*Fix:* pass `modules=tuple(state.selected_sites)` into `CrossScanConfig` — upstream's `_scope` already normalises `"x.com"` → `"x_com"` at `core/cross_scan.py:196` — and forward the resolved scope into `_named_targets`.

### P1 — correctness / data-loss

**B6 · "Skipped" results are dropped on the username path and the progress counter stalls.**
`user_scanner_compat.py:158` emits `on_result(("skipped", cat, name, None))`.
`sherlock_service.py:186-187`: `if not item or item[0] != "result": return` → the tuple is discarded.
`sherlock_service.py:191`: `progress.checked_sites += 1` runs **only** for `"result"` items → the count under-reports and the progress bar never reaches `total_sites`.
Upstream treats SKIPPED as visible by default (`core/result.py:291-296`). The email path handles it correctly (`email_service.py:293-298`) — the two services disagree.
Impact is currently masked because `LOUD_MODULES["user"]` is empty, but the structure is wrong the moment that changes.

**B7 · "Error" results are dropped by both services.**
`user_scanner_compat.py:195` / `:274` return `("error", category, site_name, Exception(...))` for a module with no `validate_` function. Neither `sherlock_service.py:186` nor `email_service.py:293` handles the `"error"` kind → the module vanishes with no row and no counter increment. Upstream returns a real `Result.error(...)` (`core/orchestrator.py:60`) that *is* surfaced.

**B8 · Cross-scan hits are double-counted into the pass-1 progress object.**
`user_scanner_compat.py:488-489`, `:516-517`, `:541-542` re-emit every tagged cross-scan result through `on_result(...)`, *and* return them in `cross_results`.
`sherlock_service.py:189-197` then appends them to `progress.found` / `.not_found` / `.errors` and increments `progress.checked_sites` **again** → `checked_sites` can exceed `total_sites`, and the progress bar over-counts.
Upstream keeps the two sets separate and lets the caller merge for export (`core/cross_scan.py:88-90`).
*Fix:* keep cross-scan rows in a separate bucket (or tag them `pivot:…` and exclude them from the counter).

**B9 · Vestigial / hallucinated status-mapping code.**
`sherlock_service.py:304-308`:
```python
if status == USResult.taken.__wrapped__ if hasattr(USResult.taken, "__wrapped__") else status:
    pass
status_str = "Available"
if status == USResult.available(0).status if False else None:
    status_str = "Available"
```
`Result.taken` is a plain `classmethod` with no `__wrapped__`, so the first condition degenerates to `status == status` → always true → `pass`. The second is `if False else None` → `status == None` → always false. Both are dead branches from an earlier mapping attempt; the working mapping is the `Status`-enum block at `:310-318`. The `USResult.available(0)` call would have constructed a throwaway `Result` just to read `.status` — evidence the mapping was never validated against the installed API.

**B10 · The app's CSV export drops upstream's CSV-injection guard.**
`core/result.py:26-34` `_neutralize_csv_cell` prefixes any value starting with `= + - @ \t \r \n` with `'`, neutralising formula injection in Excel/LibreOffice.
`src/services/report_service.py:119-156` `generate_csv_report` uses a plain `csv.writer` with **no neutralisation**, and writes `url_user` — an attacker-controlled profile URL — straight into a cell. A URL of `=cmd|'/c calc'!A0` becomes a live formula in the exported sheet.
*Fix:* reuse `user_scanner.core.result._neutralize_csv_cell` on every cell (it is a public-enough module-level helper).

**B11 · Cancelled scans keep hitting the network.**
`user_scanner_compat.py:168-179` (`run_username_scan`) and `:247-258` (`run_email_scan`) iterate `asyncio.as_completed(tasks)` and `break` on cancel — but the **created tasks are never cancelled**. They keep running to completion, keep issuing HTTP requests, and their results are silently discarded. `run_in_executor`/`asyncio.to_thread` calls cannot be interrupted at all.
Upstream has the same limitation (no cancel token), but Sherlock-V3 ships a visible **Cancel** button, so this is a UX-visible gap: the user hits Cancel, the UI updates, and the network keeps going.

### P2 — dead code / dead controls

**B12 · `no_nsfw` is a dead parameter.**
`user_scanner_compat.py:125` declares `no_nsfw: bool = False`; the body never reads it (the NSFW filter is applied at *load* time inside `load_user_modules`/`load_email_modules`). Callers pass it at `sherlock_service.py:209`, `:483`, `:513` believing it has runtime effect.

**B13 · `use_curl_cffi` / `use_stealth_fingerprint` are dead switches.**
`email_service.py:207` and `:210-211` accept them; `:250-251` merely copies one into the other; neither is ever forwarded to `run_email_scan` (`:357-365`). The toggle in Settings (`settings_screen.py:961`, `home_screen.py:535`) changes nothing. And the 39 impersonate-based email modules use curl_cffi unconditionally (`core/impersonate.py`), so "off" isn't honoured either.

**B14 · `scan_depth`, `retries`, `check_domains` are user-facing controls that do nothing.**
`state.scan_depth` (set at `main.py:748-750`, `settings_screen.py:563`, cycled at `home_screen.py:443`) has **no consumer** in any scan path. `state.retries` (`core/state.py:131`, `main.py:800`, `settings_screen.py:593`) — no consumer, and upstream `make_request` hard-codes `max_retries = 0` (`core/orchestrator.py:309`), so there is nothing to wire it to. `state.check_domains` (`main.py:774`, `settings_screen.py:521`) — no consumer.
These are V2 Sherlock-DB leftovers presented to the user as working switches.

**B15 · `verbose_output` is persisted but never consumed.**
`state.verbose_output` is toggled at `settings_screen.py:608` / `home_screen.py` and loaded at `main.py`, but nothing reads it. Upstream's `ScanConfig.verbose` controls URL display (`core/result.py:265-269`) — the app has the URL in the result row already, so the honest mapping is "show/hide the URL column".

**B16 · Email-domain generation is silently capped at 5 addresses.**
`main.py:1081`: `for addr in generated[:5]:  # cap to avoid huge scans`.
Upstream scans **every** `username@domain` pair the scope produces (`core/__main__.py:505-537`). `parse_email_domain_scopes("global")` yields 32 domains; `"all"` yields **273**. The app drops 93 % of them with no UI indication, and it also lacks upstream's pattern × domain cross-product.

**B17 · `set_global_timeout` is a process-wide global shared by two services.**
`sherlock_service.py:101-104` sets it from `state.timeout` (default 15); `email_service.py:254-257` sets it from the email timeout (default 10). Last writer wins for the whole process — including the other scan's in-flight requests. Upstream has the same global (`core/helpers.py:455-462`) but the CLI runs one target type at a time; the app can run both.

**B18 · The canonical `Result` export schema is never used.**
`Result.as_dict()` / `to_dict()` / `to_json()` / `to_csv()` (`core/result.py:171-224`) and `formatter.into_json` / `get_json_data` / `into_csv` (`core/formatter.py:9-19`) are unused; the app rebuilds export rows from its own `SiteResult` (`sherlock_service.py:299-367`) and stores `extra`/`media` under `ids_data` instead of as first-class `extra`/`media` keys.
Consequence: Sherlock-V3's JSON export does **not** match the upstream/MCP schema — `core/mcp/handlers.py:9,174` serialises via `into_json` → `Result.to_dict()`, i.e. `status/reason/username|email/site_name/category/url/extra/media`. Any consumer that expects the upstream shape (including the MCP server) gets a different document from the GUI.

**B19 · Minor: the `"General"` vs `"Unknown"` category fallback diverges.**
`user_scanner_compat.py:496` falls back to `"General"`; upstream uses `"Unknown"` (`core/orchestrator.py:51`). The two code paths (load-time category vs `find_category`) therefore label the same situation differently.

**B20 · Minor: the wrapper drops upstream's second `.capitalize()` on `site_name`.**
`core/orchestrator.py:54` applies `site_name.capitalize()`; the wrapper (`user_scanner_compat.py:211`) uses the raw `get_site_name(module)`. `get_site_name` already capitalises, so the two agree for every current module — but it is an unguarded divergence for a future module with mixed-case output.

**B21 · `formatter.into_pdf` is unusable, and the app's PDF never uses upstream's SSRF guardrails.**
`REPORTLAB_AVAILABLE=False` (verified: reportlab/pillow/svglib are **not installed** in the V3 venv), so `core/formatter.py:22 into_pdf` → `core/pdf_generator.py:254` raises `ImportError`. The app ships its own PDF dossier generator (`report_service.generate_pdf_dossier`), which is a legitimate choice — but it also means upstream's `is_safe_ip` / `is_safe_media_url` SSRF guardrails (`core/pdf_generator.py:69-127`) are **not applied** to the app's own avatar downloader (`services/cache_service.schedule_avatar_download`, used from `main.py:1242` and `main.py:1624`). Those two functions are importable today (the reportlab import is guarded), so hardening is free.

### Hallucination check — no invented upstream symbols
Every upstream symbol the wrapper imports was verified to exist in the installed tree: `helpers.load_categories` ✓, `helpers.get_site_name` ✓, `helpers.get_scan_func` ✓, `helpers.is_loud` ✓, `helpers.set_proxy_manager` ✓, `helpers.ScanConfig` ✓, `helpers.find_category` ✓, `result.Result` / `result.Status` ✓, `cross_scan.CrossScanConfig` ✓, and all 12 `cross_scan` private helpers imported at `user_scanner_compat.py:402-413` ✓. **No hallucinated API references were found.** The only hallucination-class artefacts are the dead mapping code at `sherlock_service.py:304-308` (B9) and the dead `no_nsfw` parameter (B12).

---

## 4. Unused capabilities + concrete proposals (priority-ordered)

### Priority 0 — parity-critical (must fix to be "better than real Sherlock V2")

| # | Capability | Installed API | Proposal | Parity-critical |
|---|---|---|---|---|
| 1 | **Hudson Rock** | `core/hudson.py` `check_hudson_permission`, `run_hudson_scan`, `update_hudson_preference` | **Fix B1 first.** Reimplement the 20-line query in `sherlock_service.run_hudson` (call `https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-{username,email}` directly, `timeout=10`, parse `stealers[]`), and add a **Flet consent dialog** ("This sends the identifier to Hudson Rock, a third party") before the first run — mirroring the upstream disclaimer but as a real dialog. Render the parsed data (`stealer_family`, `date_compromised`, `operating_system`, `computer_name`, `antiviruses`, `top_logins`) in a **dedicated result card**, not the 120-char truncated snackbar at `main.py:1123`. Also call `hudson.update_hudson_preference(False)` once the user consents, so the upstream config stops re-prompting. | **YES** |
| 2 | **Proxy injection for the email vector** | `core/email_orchestrator.py:23-52` monkeypatch | **Fix B2**: add `import user_scanner.core.email_orchestrator  # noqa: F401` at the top of `services/user_scanner_compat.py` (or call `set_proxy_manager` + monkeypatch manually). Also **fix B4**: always call `set_proxy_manager(proxies=[proxy] if proxy else None)`. | **YES** |
| 3 | **250-thread executor** | `core/orchestrator.py:28`, `core/email_orchestrator.py:198-200` | **Fix B3**: in `services/user_scanner_compat.py`, create `concurrent.futures.ThreadPoolExecutor(max_workers=max(concurrency * 2, 250))` once per scan and pass it to `loop.run_in_executor(pool, func, target)` in both `_run_one_user` and `_run_one_email`. Surface `state.max_connections` as the true knob. | **YES** |
| 4 | **Cross-scan scope restriction** | `core/cross_scan.py:187-251` (`_scope`, `_email_scope`), `CrossScanConfig.modules`/`.categories` | **Fix B5**: in `sherlock_service.py:224` and `email_service.py:375`, populate `CrossScanConfig(modules=tuple(state.selected_sites or []))`; in `user_scanner_compat.py:492` resolve the scope via the same `find_module(name.replace(".", "_"), …)` logic and pass it to `_named_targets`, and filter `usable_email_modules` by it. | **YES** |
| 5 | **Cross-scan result isolation** | `core/cross_scan.py:88-90` | **Fix B8**: don't re-emit cross-scan rows through the pass-1 `on_result`; collect them into a separate `cross_progress` bucket and render them under a "Cross-scan hits" section, so `checked_sites` stays truthful. | **YES** |

### Priority 1 — missing capabilities the CLI has and the GUI does not

| # | Capability | Installed API | Proposal | Parity-critical |
|---|---|---|---|---|
| 6 | **Combinatorial pattern engine** | `core/patterns.py` `expand_patterns`, `expand_patterns_random(capacity=1000)`, `count_patterns` | The app's `src/core/permute.py` is a *different* feature (separator swaps, `MAX_VARIANTS=5`). The upstream pattern syntax (`john[0-9]{1-2}`, `john[a-c]{0-2}`) has **no equivalent anywhere in the app**. Add a **"Pattern" field** next to the target input in `home_screen.py`: accept `name[0-9]{1-3}`, call `count_patterns()` to show "**Scanning 100 of 18,279 permutations**" (exactly the upstream copy at `core/__main__.py:520`), sample with `expand_patterns_random(pattern, capacity=stop_limit)`, and feed the comma-joined list into the **existing** multi-target pipeline that `permute_enabled` already uses (`main.py:990-998`). Add a **"-s / limit" stepper** (default 100, upstream `MAX_PERMUTATIONS_LIMIT`). | **YES** — the CLI has it, the GUI does not; this is the single clearest "not yet better than V2" gap |
| 7 | **Proxy pool / rotation** | `helpers.ProxyManager(proxy_file=…)`, `set_proxy_manager(proxy_file=…)`, `get_proxy_count()`, `get_random_proxy()` | `state.proxy_file` already exists (`core/state.py:78`) and is read by `settings_screen.py:650` — but **only for validation**; the scan always uses the single `state.proxy_url`. Add a Settings row: "**Proxy pool (rotate)**" → `set_proxy_manager(proxy_file=state.proxy_file)` so upstream's round-robin rotator drives the scan, and display `get_proxy_count()` next to it. | **YES** |
| 8 | **Bulk target import** | CLI `-uf/--username-file`, `-ef/--email-file` | Add a **"Bulk targets"** affordance on `home_screen.py` (multi-line paste or file picker) that splits on newlines, drops `#` comments, validates each with `helpers.is_valid_email` for email mode, and joins them with commas into the existing `parse_usernames` path. | no |
| 9 | **Email-domain scope picker** | `helpers.EMAIL_DOMAIN_SCOPES` (**41** scopes / 273 domains), `parse_email_domain_scopes`, CLI `--list-email-domains` | `state.email_domains` is a **free-text field** with zero discoverability. Replace it with a chip/multi-select over the 41 scope names (`global`, `usa`, `uk`, `germany`, … `israel`), validated by `parse_email_domain_scopes` (it raises `ValueError` on an unknown name — surface that as a field error). Show the resolved domain count ("**32 addresses**"). Then **fix B16**: raise the 5-address cap to the full scope (or make the cap explicit and user-adjustable, defaulting to the scope size) and add the upstream pattern × domain cross-product. | **YES** |
| 10 | **Explicit scan scope control** | CLI `-c/--category`, `-m/--module`, `helpers.find_module`, `helpers.load_categories` | The Sites screen already filters a *selection list*; there is no first-class "scan scope" control. Add a **"Scope" segmented control** on `home_screen.py` (`All` / `Category ▾` / `Module ▾`) backed by `load_categories()` + `find_module()` so the control maps 1:1 to the CLI's `-c`/`-m`, and so it can be handed to `CrossScanConfig` (item 4). | no |
| 11 | **Loud-module warning** | `core/loud_prompt.py` `check_loud_module_permission`, `helpers.LOUD_MODULES` | The app has only a global "allow loud" toggle. When the user selects a *single* loud email module with `allow_loud` off, show a Flet dialog ("'Netflix' notifies the target by email — run anyway?") and, on "don't ask again", call `loud_prompt.update_loud_module_preference(False)`. Also badge loud modules in the Sites screen the way upstream's `--list-email` does (`core/__main__.py:324`). | no (safety-UX) |
| 12 | **Inter-target delay** | CLI `-d/--delay` | Add a small delay stepper in Settings; apply `await asyncio.sleep(delay)` between targets in `sherlock_service._run` (`:174`). | no |
| 13 | **Module-cache pre-warm** | `helpers.load_modules` `@lru_cache` | The app's `_load_modules_tolerant` (`user_scanner_compat.py:61`) has **no cache**, so every `load_sites(force=True)` re-imports and re-compiles 2,521 modules (the V2 doc measured ≈ 62 s). Add an `@lru_cache` to the tolerant loader and a **background pre-warm thread** started at app launch, with a "Pre-warming OSINT vector cache…" indicator. | no (perf/UX) |

### Priority 2 — deeper parity / hardening

| # | Capability | Installed API | Proposal | Parity-critical |
|---|---|---|---|---|
| 14 | **Canonical export schema + CSV-injection guard** | `Result.to_dict()` / `as_dict()` / `to_json()` / `to_csv()`, `formatter.into_json` / `get_json_data` / `into_csv`, `result._neutralize_csv_cell` | **Fix B10 + B18**: build the app's JSON export from `Result.to_dict()` (so the GUI output matches the upstream/MCP schema) and apply `_neutralize_csv_cell` to every cell in `report_service.generate_csv_report`. | no (security) |
| 15 | **Upstream PDF pipeline + SSRF guardrails** | `core/pdf_generator.py` `is_safe_ip`, `is_safe_media_url`, `generate_pdf_report`; flags `REPORTLAB_AVAILABLE=False`, `PIL_AVAILABLE=False`, `SVGLIB_AVAILABLE=False` | `formatter.into_pdf` is **unavailable** (reportlab/pillow/svglib are not installed) and the app's own PDF generator is a legitimate superset — so **do not re-add reportlab**. But **do** import `is_safe_media_url` / `is_safe_ip` in `services/cache_service.py` and gate `schedule_avatar_download` on them: today the app fetches attacker-supplied avatar URLs with no SSRF protection, while upstream's equivalent has a full guard (private-IP rejection, DNS re-resolution, 5-hop redirect validation). Free win — the module imports cleanly without reportlab. | no (security) |
| 16 | **Canonical `Result` label semantics** | `Status.to_label(is_email)` → "Found"/"Not Found" vs "Registered"/"Not Registered" | The app invents its own labels (`"Claimed"` / `"Available"` / `"Skipped"` / `"WAF"`). Adopt `Status.to_label(r.is_email)` for the underlying truth and keep the app's label as a display overlay, so the two vocabularies cannot drift. | no |
| 17 | **Hudson remediation tips** | `cli/tips.py` `print_hudson_remediation_tip`, `print_proxy_tip`, `print_loud_skip_tip` | Surface the Hudson remediation advice (password resets, session invalidation) as actionable text in the Hudson result card from item 1; show the proxy tip as a one-line hint when a scan returns many WAF/rate-limit errors. | no |
| 18 | **Verbose / show-all semantics** | `ScanConfig.verbose`, `ScanConfig.show_all`, `Result.is_visible(configs)` | **Fix B15**: wire `state.verbose_output` to a real effect — toggle the URL column in the results view (and pass `verbose=state.verbose_output` into the `ScanConfig` the cross-scan path already builds at `user_scanner_compat.py:428`). `show_all` is already equivalent (the app always shows all three buckets). | no |
| 19 | **`set_concurrency` / `get_proxy_count` introspection** | `orchestrator.set_concurrency`, `email_orchestrator.set_concurrency`, `helpers.get_proxy_count` | Not needed once item 3 lands (the wrapper owns its own pool), but `get_proxy_count()` is a good Settings diagnostic to show alongside the proxy pool (item 7). | no |
| 20 | **MCP server** | `mcp/server.py`, `mcp/schemas.py` (`scan_username`, `scan_email`, `list_available_modules`) | The package ships a stdio MCP server the app never touches. Optional: expose the same three tools over a local socket so an agent can drive Sherlock-V3. Low value for a desktop GUI; note it for completeness. | no |
| 21 | **`core/engine.py` public API** | `check`, `check_category`, `check_all` | The app deliberately does not use them (they lack loud/timeout/cancel/semaphore). **No action** — but the wrapper's docstring (`user_scanner_compat.py:1-13`) should state *why*, so a future maintainer doesn't "simplify" back to `engine.check`. | no |
| 22 | **`core/nextjs.py`, `core/impersonate.py`, `core/version.py`** | direct helpers | Already inherited for free (16 + 107 modules use them). No action. Note that `core/impersonate.get_impersonate_timeout()` is unused and that the app's "use curl_cffi" toggle does **not** govern the 39 impersonating email modules (B13). | no |

### Dead controls to remove or wire up (summary)

| Control | Location | Disposition |
|---|---|---|
| `scan_depth` (all/1000/500) | `core/state.py:117`, `settings_screen.py:1240`, `home_screen.py:873` | **Remove** — no consumer, no upstream equivalent (upstream's cap is `-s/--stop`, covered by item 6). |
| `retries` | `core/state.py:131`, `settings_screen.py:593` | **Remove** — upstream `make_request` hard-codes `max_retries = 0`. |
| `check_domains` | `core/state.py:111`, `settings_screen.py:1512` | **Remove** — no consumer. |
| `use_curl_cffi` / `use_stealth_fingerprint` | `core/state.py:133`, `settings_screen.py:961` | **Remove or re-scope** — it governs nothing (B13). |
| `verbose_output` | `core/state.py:69`, `settings_screen.py:891` | **Wire up** → show/hide the URL column (item 18). |

---

## 5. Verdict

### **ISSUES FOUND**

| Category | Count | Detail |
|---|---|---|
| **P0 — parity-critical** | **5** | B1 Hudson dead · B2 email proxy dead (180/220) · B3 executor 8 vs 250 (≈25–30× slow) · B4 stale proxy leak · B5 cross-scan scope ignored |
| **P1 — correctness / data loss** | **6** | B6 skipped dropped + counter stalls · B7 error dropped · B8 cross-scan double-count · B9 vestigial mapping code · B10 CSV-injection guard dropped · B11 cancel does not cancel |
| **P2 — dead code / dead controls** | **8** | B12 dead `no_nsfw` · B13 dead `use_curl_cffi` · B14 dead `scan_depth`/`retries`/`check_domains` · B15 dead `verbose_output` · B16 5-address cap · B17 global-timeout bleed · B18 non-canonical export schema · B19/B20 minor label divergences · B21 no SSRF guard on avatars |
| **Unused capabilities** | **22** (5 P0, 8 P1, 9 P2) | §4 |
| **Hallucinated upstream symbols** | **0** | Every imported upstream symbol verified present; the only artefacts are the two dead-code blocks (B9, B12) |
| **Background-doc discrepancies** | **3** | 41 scopes (not 26) · global = 32 domains (not 31) · the doc's "use `engine.check`" advice is *worse* than what the app does |

**Counts:** 18 numbered defects (B1–B18 with B19–B21 folded as minor), of which **5 are parity-critical**; **22 capabilities** of the installed package are not exposed by the wrapper; **3** factual errors in the V2 background doc.

**Bottom line.** The wrapper's *architecture* is right and, in three places, better than the package it wraps: the tolerant module loader (`user_scanner_compat.py:61`) fixes upstream's single-bad-file-kills-a-category hazard (`core/helpers.py:513`); the cancellable, streaming driver replaces the CLI-coupled `rich` orchestrators; and the app's own report generator is a superset of `core/formatter.py`. But the *implementation* is not yet a maximal one-to-one wrap: it re-implements upstream's orchestrators while silently dropping the two global side-effects those orchestrators rely on (the httpx proxy monkeypatch, the 250-thread executor), hard-codes the cross-scan scope to `None`, and reaches upstream's `input()`-based consent gate in a GUI where `input()` cannot work. Fix the five P0 items and wire the P1 pattern/scope/proxy-pool capabilities, and the wrap becomes maximal; as it stands the GUI is **behind** the `user-scanner` CLI on proxy support, scan throughput, and the Hudson feature, and **ahead** only in presentation.
