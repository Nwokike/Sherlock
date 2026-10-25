# phonsint 0.1.0 / phonenumbers 9.0.41 — Dependency Audit (Sherlock-V3)

**Auditor:** dependency-audit subagent
**Date:** 2026-10-20
**Source of truth:** the installed venv at `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/`
**Packages:** `phonsint` 0.1.0 (`phonsint-0.1.0.dist-info`), `phonenumbers` 9.0.41 (`phonenumbers-9.0.41.dist-info`)
**Background docs (V2-era, verified):** `docs/reference/dep-phonsint.md`, `docs/reference/dep-phonenumbers.md`

> Scope note: the owner has decided **not to add** a new "phone-osint" dependency set / that phonsint is "not anymore". This audit still covers the **existing** phone-mode wiring that is already in the codebase, because it is live today. Nothing was modified.

---

## 1) Installed API Verification

### 1.1 `phonsint` package layout (as installed)

```
phonsint/
├── __init__.py           # only `__version__ = "0.1.0"`; NO root re-exports
├── __main__.py           # CLI (argparse + rich)
├── core/
│   ├── helpers.py        # ScanConfig, load_categories, load_modules, get_scan_func,
│   │                     # get_site_name, find_category, is_loud, LOUD_MODULES
│   ├── impersonate.py    # curl_cffi browser-impersonating session cache
│   ├── orchestrator.py   # _async_worker, run_scan_async, run_scan
│   ├── parser.py         # PhoneInfo, parse_phone_number
│   └── result.py         # Status, Result
└── modules/
    ├── auth/microsoft.py
    ├── crm/zoho.py
    ├── shopping/amazon.py
    ├── social/facebook.py
    └── social/instagram.py
```

The V2 background doc's layout section is **accurate** for the V3 install. There is no `phonsint.core.confidence`, no `cross_scan`, no `pivots` — those live only in `user_scanner`.

### 1.2 `phonsint.core.parser` — `PhoneInfo` and `parse_phone_number`

`PhoneInfo` is a **frozen dataclass** with exactly 8 fields (`parser.py:6-16`):

| Field | Type | Notes |
|---|---|---|
| `raw_input` | `str` | the untouched input string |
| `is_valid` | `bool` | `phonenumbers.is_valid_number(parsed)` |
| `e164` | `str` | E.164 (`+14155552671`) |
| `international_format` | `str` | `+1 415-555-2671` |
| `national_format` | `str` | `(415) 555-2671` |
| `country_code` | `int` | `parsed.country_code or 0` |
| `national_number` | `int` | `int(parsed.national_number)` |
| `region_code` | `str` | `region_code_for_number(parsed) or ""` |

`parse_phone_number(raw: str, default_region: Optional[str] = None) -> PhoneInfo` (`parser.py:19-60`) — the **fallback chain**:

1. `cleaned = raw.strip()`
2. `test_parse = cleaned` if it starts with `+` **or** a `default_region` was supplied, else `"+" + cleaned`
3. `phonenumbers.parse(cleaned if cleaned.startswith("+") else test_parse, default_region)`
4. On `NumberParseException` → `phonenumbers.parse(cleaned, default_region or "US")`  ← **the "US" fallback**
5. On a second `NumberParseException` → returns an invalid `PhoneInfo` with `e164 = cleaned` (the raw string)

**Empirically measured behaviour** (executed against the installed venv):

| input | region | valid | e164 | region_code |
|---|---|---|---|---|
| `+14155552671` | None | True | `+14155552671` | US |
| `14155552671` | None | True | `+14155552671` | US |
| `4155552671` | None | **False** | **`+4155552671`** | **CH** |
| `(415) 555-2671` | None | **False** | **`+4155552671`** | **CH** |
| `07700900123` | None | **False** | **`+107700900123`** | `''` |
| `07700900123` | GB | False | `+447700900123` | `''` |
| `+1 415 555 2671` | GB | True | `+14155552671` | US |
| `abc` / `''` | None | False | (raw) | `''` |
| `+999123456789` | None | False | `+999123456789` | `''` |

Two upstream defects are visible here and matter to the app:
- A bare 10-digit number is **silently reinterpreted as Swiss** (`+41 55552671`) by the `+`-prepend probe.
- A non-US national number without a region lands on the `"US"` fallback and produces a **fabricated `+1…` E.164** (`+107700900123`).

Both produce a *well-formed but wrong* `e164` with `is_valid=False`. The engine then ships that E.164 to every module (`user_scanner_compat.py:363, 377`). The app never checks `is_valid` (§3, B11).

### 1.3 `phonsint.core.helpers`

- **`ScanConfig`** (`helpers.py:12-18`) — frozen dataclass: `allow_loud: bool = False`, `show_all: bool = False`, `verbose: bool = False`, `timeout: Optional[float] = None`, **`concurrency: int = 15`**.
- **`LOUD_MODULES: List[str] = []`** (`helpers.py:9`) — **empty**, exactly as the V2 doc states. `is_loud(site_name)` is `site_name.lower() in LOUD_MODULES` (an exact-match list membership test), so it is **always `False`** in this version. The entire "loud" code path in the app is dead code today.
- **`load_categories() -> Dict[str, Path]`** (`helpers.py:37-47`) — scans `<pkg>/modules`, returns *unsorted* `dir_name → resolved path`; keys are **lowercase raw dir names** (`auth`, `crm`, `shopping`, `social`).
- **`load_modules(category_path) -> List[ModuleType]`** (`helpers.py:50-64`) — imports each `*.py` via `spec_from_file_location(file.stem, …)`; **silently swallows import errors** (`except Exception: continue`).
- **`get_scan_func(module)`** (`helpers.py:67-74`) — returns the **first** `validate_*` attribute found via `dir(module)` (alphabetical order), if it is a function or coroutine function.
- **`get_site_name(module)`** (`helpers.py:25-27`) — `module.__name__.split(".")[-1].replace("_", " ").title()` → `"Microsoft"`, `"Zoho"`, `"Amazon"`, `"Facebook"`, `"Instagram"`.
- **`find_category(module)`** (`helpers.py:30-34`) — checks `parts[-3] == "modules"`. Because **both** upstream `load_modules` and the app's own loader use `spec_from_file_location(file.stem, …)`, `module.__name__` has no dotted path, so `find_category` **always returns `"General"`**. It must not be used directly. The app correctly sidesteps it by using the directory name (`user_scanner_compat.py:56`), which matches upstream's `cat_override` behaviour.

### 1.4 `phonsint.core.orchestrator`

- **`_async_worker(module, phone_info, sem, configs, cat_override=None, on_start=None) -> Result`** (`orchestrator.py:21-69`)
  - **`on_start` is a real callback**: fired with `site_name` when a module *begins* (`orchestrator.py:31-32`). This is the "module started" progress signal.
  - **Timeout**: `timeout_val = (configs.timeout or 15.0) + 5.0` — i.e. the configured timeout **+ 5 s of grace** (`orchestrator.py:50`).
  - **Signature-based dispatch** (`orchestrator.py:52-53`):
    ```python
    sig = inspect.signature(func)
    arg = phone_info if (len(sig.parameters) == 1
                          and next(iter(sig.parameters.values())).name in ("phone_info", "info")
                          ) else phone_info.e164
    ```
    A single parameter named `phone_info`/`info` receives the whole `PhoneInfo`; anything else receives the **E.164 string**. All 5 installed modules use `async def validate_x(info: PhoneInfo)`, so they take the object path.
  - Coroutine functions are awaited directly; sync functions are run via `asyncio.to_thread`.
  - `Result` type is enforced; non-`Result` returns become `Result.error("Module returned invalid result type")`.
- **`run_scan_async(phone_info, configs, category_filter=None, module_filter=None) -> List[Result]`** (`orchestrator.py:72-167`) — semaphore = `asyncio.Semaphore(configs.concurrency)` (**no clamp**), rich `Progress` bar with `transient=True`, category/module filters are comma-separated lowercase, prints to stdout.
- **`run_scan(phone_info, configs, category_filter=None, module_filter=None) -> List[Result]`** (`orchestrator.py:170-176`) — thin `asyncio.run` wrapper.

**The app uses none of this.** `phonsint.core.orchestrator` is never imported by `src/` (verified by grep). The app re-implements the orchestrator in `src/services/user_scanner_compat.py:299-378`.

### 1.5 `phonsint.core.impersonate`

- **`set_global_timeout(val: Optional[float])`** / `get_global_timeout()` (`impersonate.py:17-23`) — module-level global; default `DEFAULT_TIMEOUT = 15.0`.
- **`set_global_proxy(val: Optional[str])`** / `get_global_proxy()` (`impersonate.py:26-32`).
- **Session cache keying** (`impersonate.py:9-11, 40`): `_sessions[(impersonate, proxy)]`, with per-key `threading.Lock` and a `_warmed` set for the optional warm-up GET.
- `impersonate_request(url, method="GET", warmup_url=None, impersonate="chrome", **kwargs)` — sets `timeout=get_global_timeout()` and `allow_redirects=False` by default.
- `impersonate_request_async(...)` — runs the blocking call through **`asyncio.to_thread`**.

Module usage confirmed on disk:
- `auth/microsoft.py`, `shopping/amazon.py`, `social/facebook.py`, `social/instagram.py` → `impersonate_request_async(url)` with **no `timeout=` override**.
- `crm/zoho.py:20-34` → reads `get_global_proxy()` / `get_global_timeout()` itself and builds its **own** `AsyncSession(impersonate="chrome120", proxies=…, timeout=…)` — it does **not** use the shared session cache.

### 1.6 `phonsint.core.result`

- **`Status`** enum (`result.py:62-76`): `TAKEN=0`, `AVAILABLE=1`, `ERROR=2`, `SKIPPED=3`.
  `to_label()` → `"Registered"` / `"Not Registered"` / `"Error"` / `"Skipped"`.
- **`Result`** fields (`result.py:79-89`): `status`, `reason`, **`phone`**, `site_name`, `category`, `url`, `extra` (dict), `media` (dict).
  `update()` only overwrites `phone`/`site_name`/`category`/`url` when the kwarg is non-`None`; `extra` keys are normalised (`strip`, trailing `:` stripped, spaces→`_`, lowercased); `media` keys are lowercased.
- **CSV injection guard** (`result.py:23-30`): `_neutralize_csv_cell` prefixes `'` to any cell whose left-stripped value starts with `=`, `+`, `-`, `@`, `\t`, `\r`, `\n`. Applied in `Result.to_csv()` (`result.py:186-201`).
- `is_visible(configs)` → `True` when `show_all`, else only `TAKEN`/`SKIPPED`. `is_found()` → `status == TAKEN`.
- **`Result.phone` exists but the app never reads it.**

### 1.7 Actual module inventory on disk

| Category | Modules | Files |
|---|---|---|
| `auth` | 1 | `microsoft.py` |
| `crm` | 1 | `zoho.py` |
| `shopping` | 1 | `amazon.py` |
| `social` | 2 | `facebook.py`, `instagram.py` |
| **Total** | **5** | |

Matches `src/core/constants.py:21` and `tests/test_sites_catalog.py:24` (`assert len(names) == 5`). All five export `async def validate_<name>(info: PhoneInfo) -> Result`. Two of them return rich payloads: `facebook` and `instagram` return `Result.taken(extra=…, media=…)`; `microsoft` and `zoho` return `extra`; `amazon` returns no extra.

### 1.8 `phonenumbers` 9.0.41 — available surface vs. app usage

**App usage of phonenumbers: ZERO.** `grep -rn "phonenumbers" src/ tests/` returns no hits anywhere in the app. It is reached only transitively through `phonsint.core.parser`. Across the whole venv, **`phonsint/core/parser.py` is the only non-phonenumbers file that imports it** — so phonenumbers is an orphan the moment phonsint goes.

Runtime-verified available (with data files present in the install: `geodata/` 33 files, `carrierdata/` 3, `tzdata/` 5, `shortdata/` 244):

| API | Status in this install | Verified output |
|---|---|---|
| `is_valid_number`, `is_possible_number`, `is_valid_number_for_region` | available | — |
| `format_number` (E164/NATIONAL/INTERNATIONAL/RFC3966) | available | — |
| `region_code_for_number` | available | `US` |
| `SUPPORTED_REGIONS` | available, **245 codes** | — |
| `country_code_for_region` | available | `US`→1, `GB`→44 |
| `region_code_for_country_code` | available | — |
| `AsYouTypeFormatter(region)` | available | `"4155552671"` → `"(415) 555-2671"` |
| `geocoder.description_for_number` | available | US → `"San Francisco, CA"`, GB → `"United Kingdom"` |
| `carrier.name_for_number` | available | GB → `"Three"`, US 555 → `""` |
| `timezone.time_zones_for_number` | available | US → `("America/Los_Angeles",)`, GB → 4 zones |
| `shortnumberinfo.is_valid_short_number` / `is_possible_short_number` | available | — |
| `phonenumbers.PhoneNumberMatcher` | available | — |
| `parse`, `PhoneNumberFormat`, `NumberParseException` | available | — |

---

## 2) App Wiring Correctness (file:line)

### 2.1 Call → installed-API map

| App call site | Installed API it targets | Verdict |
|---|---|---|
| `user_scanner_compat.py:53` `load_categories()` | `phonsint.core.helpers.load_categories()` | ✅ correct, no args |
| `user_scanner_compat.py:102` `get_site_name(module)` | `phonsint.core.helpers.get_site_name` | ✅ correct |
| `user_scanner_compat.py:107` `get_scan_func(module)` | `phonsint.core.helpers.get_scan_func` | ✅ correct |
| `user_scanner_compat.py:312` `is_loud(name)` | `phonsint.core.helpers.is_loud` | ✅ correct signature (1 arg) |
| `user_scanner_compat.py:314, 316` `parse_phone_number(phone, region)` | `phonsint.core.parser.parse_phone_number(raw, default_region=None)` | ✅ correct signature |
| `user_scanner_compat.py:350` `PResult` | `phonsint.core.result.Result` | ✅ |
| `phone_service.py:51` `Status` | `phonsint.core.result.Status` | ✅ |
| `user_scanner_compat.py:358` `get_scan_func` | ✅ | ✅ |
| `user_scanner_compat.py:362-363` signature dispatch | mirrors `orchestrator.py:52-53` exactly | ✅ correct, incl. `("phone_info","info")` names |
| `user_scanner_compat.py:364` `module_timeout = (timeout or 15.0) + 5.0` | mirrors `orchestrator.py:50` | ✅ correct |
| `user_scanner_compat.py:377` `result.update(site_name=…, phone=e164, category=…)` | mirrors `orchestrator.py:37-41, 69` | ✅ correct |
| `user_scanner_compat.py:322` `on_result(("skipped", cat, name, None, phone_info))` | app-internal 5-tuple | ✅ consistent with `phone_service.py:179` |
| `phone_service.py:73` `"429" in reason or "rate" in reason.lower()` | app-local, not a phonsint API | ⚠️ naive (B7) |

**No API name/signature hallucination was found.** Every phonsint symbol the app calls exists in the installed package with a compatible signature.

### 2.2 Concurrency wiring

- `ScanConfig.concurrency` (the installed field) is **never used** — `phonsint.core.helpers.ScanConfig` is not imported by the app at all.
- Concurrency is handled by the app's own driver: `user_scanner_compat.py:329` `sem = asyncio.Semaphore(max(1, min(100, concurrency)))` — hard **clamp to 100**, whereas upstream `orchestrator.py:112` has **no clamp**.
- The value that reaches the engine is **wrong**: `main.py:1776` passes `concurrency=getattr(state, "email_concurrency", 15)`. The dedicated phone setting `state.phone_concurrency` (`state.py:79`) — wired to a home-screen cycler (`home_screen.py:469-477, 806-809`) and a settings slider 5…30 (`settings_screen.py:636-637, 1202-1209`) — **never reaches the engine**. The UI knob is dead.
- Default `state.email_concurrency = 12` (`state.py:100`) is what actually applies.

### 2.3 `on_start` progress

- Upstream `_async_worker` accepts and fires `on_start(site_name)` (`orchestrator.py:27, 31-32`). The app **never uses it** (upstream orchestrator is not imported).
- The app's substitute is a **result-completion** callback: `phone_service.py:173-194` `_on_result`, throttled at 0.25 s (`phone_service.py:192`). There is **no heartbeat**, so a scan whose modules are all still in flight shows a frozen progress bar for the entire in-flight window.
- The upstream "module started" signal is exactly the missing piece and has no equivalent in the app.

### 2.4 Loud filtering

- Upstream: `is_loud` + `LOUD_MODULES` (empty) + `Result.skipped(reason="Loud module skipped (use --allow-loud)")` (`orchestrator.py:46-47`).
- App: `user_scanner_compat.py:321-323` mirrors it, emitting `("skipped", cat, name, None, phone_info)`; `phone_service.py:178-180` maps it to `PhoneResult(exists=None, unavailable=True, reason="skipped (loud)")`.
- Because `LOUD_MODULES == []`, `is_loud` is always `False` → **the skipped path is unreachable**. Additionally `main.py:1777` hardcodes `allow_loud=False`, overriding `state.allow_loud` (which *is* honoured for email/username: `email_service.py:364`, `sherlock_service.py:208`).
- `Result.get_reason()`'s "Skipped because it may alert the target" fallback (`result.py:152-153`) is therefore also unreachable.

### 2.5 E.164 normalization / dedup

- Normalization **does** happen inside the engine: `user_scanner_compat.py:316` `parse_phone_number(phone, region)`, and every module receives `phone_info.e164` (`user_scanner_compat.py:363, 377`). Within a scan, all 5 modules see the same canonical number. ✅
- But the **normalized value never leaves the engine**:
  - `phone_service.py:152` `PhoneSearchProgress(phone=phone)` → **raw** input.
  - `main.py:1746` `state.current_username = phone_clean` → **raw**.
  - `main.py:1754, 1822` `state.phone_results_address = phone_clean` → **raw**.
  - `PhoneResult` (`phone_service.py:25-35`) has **no phone field at all**.
  - `state.py:175` cache key = `f"{mode}:{query.strip().lower()}"` → raw.
- Consequence: `+14155552671`, `14155552671` and `+1 415-555-2671` are **three separate cache/history entries**. No dedup across input formats. The app also has no way to show the user the canonical number it actually scanned.

### 2.6 UI parity

| Capability | Present? | Evidence |
|---|---|---|
| Region / country selector | **No** | `grep -rn "region_code\|AsYouType\|e164\|geocod\|carrier\|timezone" src/` → zero hits in the phone context. `main.py:1773` hardcodes `region=None`. |
| Live validation feedback | **No** | `home_screen.py:638-640`: `elif mode == MODE_PHONE: # phone numbers: accept anything non-empty; engine validates` → `pass`. No `is_valid_number` call anywhere. |
| Formatted (as-you-type) display | **No** | `AsYouTypeFormatter` unused. |
| E.164 / canonical display | **No** | Only the raw input is displayed (`state.current_username`). |
| Country / carrier / timezone context | **No** | `phonenumbers.geocoder`/`carrier`/`timezone` never imported. |
| Validity warning banner | **No** | Upstream CLI does this (`phonsint/__main__.py:117-119`); the app does not. |
| Concurrency control | **UI yes → engine no** | See §2.2 (dead knob). |
| Loud toggle | **UI yes → engine no** | `main.py:1777` hardcoded `False`. |
| Correct open-URL on result cards | **No** | `results_screen.py:522` `url_main=f"https://{r.get('domain','')}"` — for phone rows `domain` is the **category** (`"Social"`, `"Auth"`, `"Crm"`, `"Shopping"`) → the button points at `https://Social`. The real URL is in `others.url` and is ignored. |

### 2.7 Test coverage — `tests/test_phone_mode_parity.py`

6 tests, all pass (`pytest tests/test_phone_mode_parity.py …` → 27 passed across the phone-related files). Coverage is **shallow and partly tautological**:

| Test | What it actually asserts | Gap |
|---|---|---|
| `test_state_has_phone_results_field` | `state.reset_search()` leaves `phone_results` non-`None` | no engine |
| `test_reset_search_clears_phone_rows` | state reset clears rows | no engine |
| `test_phone_snapshot_row_shape_matches_email_card_contract` | asserts keys exist **on a dict literal it just wrote** | **tautology — tests nothing in the app** |
| `test_phone_result_mapping_registered` | asserts on a **hand-built `PhoneResult`** | **never calls `_map_result`** — the actual phonsint-`Result` → `PhoneResult` mapping is entirely untested |
| `test_phone_service_has_worker_loop_for_cancel` | `hasattr(svc, "_worker_loop")` | no cancel behaviour exercised |
| `test_mode_phone_constant_is_phone` | `MODE_PHONE == "phone"` | trivial |

**Not covered anywhere:** `parse_phone_number` / E.164 normalization; `run_phone_scan` / `_run_one_phone`; `_map_result`; the `"error"` tuple drop; the rate-limit heuristic; concurrency / region / proxy / allow_loud plumbing; the results-screen rendering of a live `PhoneSearchProgress` (which is where the crash in B1 lives); progress accounting reaching `total_modules`.

The only test that pins the module inventory is `tests/test_sites_catalog.py:21-24` (`assert len(names) == 5`).

---

## 3) Bugs & Hallucinations

No API hallucination was found — every phonsint/phonenumbers symbol the app calls exists in the installed package. All defects below are **logic/wiring** bugs.

### B1 — CRITICAL: the Results screen raises `AttributeError` during every live phone scan
`src/screens/results_screen.py:475-476`
```python
raw_rate_limited = [_to_dict(r) for r in active_progress.rate_limited]
raw_unavailable  = [_to_dict(r) for r in active_progress.unavailable]
```
`PhoneSearchProgress` (`src/services/phone_service.py:38-47`) has only `phone, total_modules, checked_modules, found, not_found, errors, is_running, is_cancelled` — **no `rate_limited`, no `unavailable`** (unlike `EmailSearchProgress`, `email_service.py:58-59`). Runtime-verified:
```
AttributeError: 'PhoneSearchProgress' object has no attribute 'rate_limited'
```
The branch is reached whenever `active_progress` has `checked_modules` (`results_screen.py:444`) — `PhoneSearchProgress` does — and `is_phone_mode` is `True` (`results_screen.py:320-325`). Since `main.py:1755-1756` installs a `PhoneSearchProgress` as `state.search_progress` and `main.py:1748` sets `state.is_searching = True`, **every phone scan that opens the Results tab throws**. `main.py:2322 on_error` downgrades it to a generic snackbar, so the failure is silent apart from the log line. (The post-scan path is fine because it uses `state.phone_results` instead.)

### B2 — `state.phone_concurrency` is a dead knob; phone scans use email concurrency
`src/main.py:1776` → `concurrency=getattr(state, "email_concurrency", 15)`.
The phone-specific setting exists and is fully UI-wired (`core/state.py:79`, `screens/home_screen.py:469-477` + `:806-809`, `screens/settings_screen.py:636-637` + `:1202-1209`, persisted via `STORAGE_PHONE_CONCURRENCY`) — and none of it reaches the engine.

### B3 — `region` is accepted by the service and then thrown away
`src/services/phone_service.py:126` declares `region: str | None = None`; `src/services/phone_service.py:198` passes a **hardcoded `None`** into `_run_worker`; `src/main.py:1773` passes `region=None`. `parse_phone_number` therefore always runs with `default_region=None`, which per §1.2 silently mis-parses national numbers (a bare `4155552671` becomes Swiss `+41…`; `07700900123` becomes fabricated `+107700900123`).

### B4 — `proxy` is accepted and silently dropped; phone traffic never uses the proxy
`src/main.py:1778` passes `proxy=state.proxy_url`; `src/services/phone_service.py:131` accepts `proxy: str = ""` but **never uses it** — `_run_worker` (`:213`) and `run_phone_scan` (`user_scanner_compat.py:299-308`) have no proxy parameter. `phonsint.core.impersonate.set_global_proxy` is **never called anywhere in `src/`** (verified by grep). `get_global_proxy()` therefore always returns `None` → every phone request goes direct, regardless of the app-wide proxy setting. `crm/zoho.py:20-21` reads `get_global_proxy()` and also gets `None`.

### B5 — The UI timeout never reaches the HTTP transport
`phonsint.core.impersonate.get_global_timeout()` returns `15.0` unless `set_global_timeout` is called — and **no `src/` file calls it**. All four curl_cffi modules call `impersonate_request_async(url)` with no `timeout=` override (`modules/auth/microsoft.py:61,96`, `modules/shopping/amazon.py:30,64`, `modules/social/facebook.py:29,96,173,211`, `modules/social/instagram.py:45,93,173`); zoho reads `get_global_timeout()` (`modules/crm/zoho.py:5,34`).
Consequence: the user's timeout choice (5/10/15/30/60 via `state.timeout`) only changes the **outer** `asyncio.wait_for` in `user_scanner_compat.py:364`. Choosing 30 or 60 **cannot** lengthen a request — it still dies at 15 s from curl. Choosing 5 cannot shorten it either.

### B6 — `allow_loud` is hardcoded off for phone mode
`src/main.py:1777` `allow_loud=False`, overriding `state.allow_loud` (honoured for email/username). Moot today (`LOUD_MODULES` is empty) but it is a hardcoded override of a user-visible setting.

### B7 — Rate-limit detection is a naive substring match (weaker than the email path)
`src/services/phone_service.py:73`
```python
rate_limit = "429" in reason or "rate" in reason.lower()
```
- **False positives:** `"rate"` matches inside `gene**rate**`, `mode**rate**`, `accu**rate**`, `sepa**rate**`, `corpo**rate**`, `opera**te**`… Any module exception containing e.g. "generate" is misclassified as a rate limit and moved into the error bucket (`phone_service.py:184-185`).
- **False negatives:** unlike the email path (`email_service.py:64-71`, regex `\b(?:403|429)\b|rate.?limit|too many requests|throttl|cloudflare|captcha|forbidden|waf|blocked`), phone mode misses `403`, `captcha`, `forbidden`, `WAF`, `blocked`, `too many requests`. phonsint's modules actually emit "Amazon presented a bot CAPTCHA" (`modules/shopping/amazon.py:43`) and "Facebook rate limit reached (HTTP 429)" — the latter is caught only by the accidental `"429"` substring.

### B8 — The `"error"` result tuple is silently dropped and permanently breaks progress accounting
`src/services/user_scanner_compat.py:360` returns `("error", category, site_name, Exception(...), phone_info)` when a module has no `validate_` function. `src/services/phone_service.py:176` filters:
```python
if not item or item[0] not in ("result", "skipped"):
    return
```
→ the error tuple is discarded, `progress.checked_modules` is **never incremented**, and the progress bar can never reach `total_modules`. The same tuple shape also means the "error" branch in `_map_result` is unreachable, so a module with no validator produces no user-visible error at all.

### B9 — Raw phone string is the identity everywhere → no E.164 dedup
`src/services/phone_service.py:152`, `src/main.py:1746, 1754, 1822`, `src/core/state.py:175`.
`+14155552671` / `14155552671` / `+1 415-555-2671` produce three separate cache entries (`state.results_cache`) and three separate history entries, and the UI shows only the raw string. The canonical `e164` is computed correctly in the engine (`user_scanner_compat.py:316, 377`) and then discarded.

### B10 — Phone result cards link to a non-existent host
`src/screens/results_screen.py:522` `url_main=f"https://{r.get('domain', '')}" if r.get("domain") else None`. For phone rows `domain` is the **category** → `https://Social`, `https://Auth`, `https://Crm`, `https://Shopping`. The real per-site URL (e.g. `https://facebook.com`) is delivered in `others.url` by `main.py:1814` and ignored by the card.

### B11 — `is_valid` / `region_code` are never surfaced to the user
`grep -rn "is_valid" src/` → zero hits (outside `email_service.is_valid_email`). The upstream CLI warns on invalid numbers (`phonsint/__main__.py:117-119`: *"not a standard allocated number according to E.164"*). The app scans silently with whatever `e164` the parser produced — including the fabricated `+107700900123` case.

### B12 — Dead parameter and missing field
`src/services/phone_service.py:50` `_map_result(cat, site_name, r, phone_info)` — `phone_info` is never referenced in the body. `PhoneResult` (`phone_service.py:25-35`) has no `phone` field, so even if it were used it could not be carried.

### B13 — Upstream `find_category` is unusable for spec-loaded modules (app works around it correctly)
`phonsint/core/helpers.py:30-34` — `parts[-3] == "modules"` never matches because `module.__name__` is a bare stem. Any future code that calls `phonsint.core.helpers.find_category` directly will get `"General"` for every module. The app currently avoids it (`user_scanner_compat.py:56`).

### B14 — Category label casing is wrong for CRM
`user_scanner_compat.py:56` `cat_name.capitalize()` → `"Crm"` (not `"CRM"`); also `"Auth"`, `"Shopping"`, `"Social"`.

### B15 — Category iteration order is non-deterministic
`phonsint/core/helpers.py:43` `for subfolder in root.iterdir()` — unsorted; `load_phone_modules` inherits it, so the Sites catalog order for phone mode varies by filesystem.

### B16 — One shared `curl_cffi` Session is driven from many threads
`phonsint/core/impersonate.py:9, 40` caches by `(impersonate, proxy)`. With proxy never set, all four curl-based modules share the single `("chrome", None)` `cffi.Session`, and `impersonate_request_async` runs the blocking call through `asyncio.to_thread` (`impersonate.py:90`). Up to `concurrency` OS threads (up to 30 via the settings slider) can therefore drive the same libcurl handle concurrently. Zoho is exempt (its own `AsyncSession`, `impersonate="chrome120"`).

### B17 — No progress heartbeat during slow scans
`src/services/phone_service.py:192` — `_notify()` fires only when a **result** arrives AND ≥0.25 s elapsed. A scan where all five modules are still in flight shows a frozen progress bar for the whole window. Upstream's `on_start` callback is the missing "module started" signal and has no equivalent here.

### B18 — Legacy `121` fallback leaks into the phone branch
`src/screens/results_screen.py:501` `total = state.phone_total_modules or len(all_email) or 121` — 121 is the legacy email module count; phone has 5. Only surfaces when both counters are zero.

### B19 — Duplicated import in `load_sites`
`src/services/phone_service.py:102` and `:106` both do `from services.user_scanner_compat import get_site_name_phone`.

### B20 — The app duplicates the upstream orchestrator instead of using it
`src/services/user_scanner_compat.py:299-378` (`run_phone_scan` + `_run_one_phone`) is a near-verbatim re-implementation of `phonsint/core/orchestrator.py:21-167`, with two behavioural divergences: the semaphore is clamped to 100 (upstream: unclamped) and the timeout semantics are copied by hand rather than derived from `ScanConfig`. `ScanConfig`, `run_scan`, `run_scan_async`, `Result.to_csv` (and its CSV-injection guard), `set_global_timeout`, `set_global_proxy` are **all** dead upstream surface from the app's point of view — upstream fixes will not propagate.

---

## 4) Unused phonenumbers / phone capabilities + concrete UI proposals

The app currently uses **none** of phonenumbers directly. Everything below is available today in the installed 9.0.41, with data files present.

### 4.1 Concrete UI proposals (each is implementable with the installed packages)

1. **Region / country picker** — build the dropdown from `phonenumbers.SUPPORTED_REGIONS` (245 codes) + `country_code_for_region` for the dial-code prefix. Feed the choice into `PhoneService.search(region=…)` → `parse_phone_number(raw, region)`. **Fixes B3** and removes the silent Swiss/`+1` misparses from §1.2.
2. **Live as-you-type formatting + validity chip** — `phonenumbers.AsYouTypeFormatter(region)` on the input field's `on_change` (verified: `4155552671` → `(415) 555-2671`) plus `is_possible_number` / `is_valid_number` for an inline ✓/✗. Today the phone input accepts "anything non-empty" (`home_screen.py:638-640`).
3. **Canonical-identity display and dedup** — surface `phone_info.e164` in the header/history/cache key so `+14155552671` and `14155552671` are one target. **Fixes B9**.
4. **Country / carrier / timezone context card** — `geocoder.description_for_number` (verified: `"San Francisco, CA"`, `"United Kingdom"`), `carrier.name_for_number` (verified: `"Three"`), `timezone.time_zones_for_number` (verified: `("America/Los_Angeles",)`) rendered next to the target. Fully offline, zero extra dependency, and it turns a raw number into something a human can read.
5. **Validity / region warning banner** — show `phone_info.is_valid` and `phone_info.region_code` before scanning, mirroring `phonsint/__main__.py:117-119`. **Fixes B11**.
6. **Bulk number extraction** — `phonenumbers.PhoneNumberMatcher` to pull many numbers out of pasted text or a file (the app already has a bulk file picker for usernames at `home_screen.py:676+`).
7. **Short-code / service-number detection** — `phonenumbers.shortnumberinfo.is_valid_short_number` / `is_possible_short_number` (with `shortdata/`, 244 files installed) to warn "this is an SMS short code, not a subscriber number" before a pointless scan.

### 4.2 Import-hygiene caveat (already noted in `docs/reference/dep-phonenumbers.md:284`)
`phonenumbers.geocoder` and `phonenumbers.carrier` load large localized tables. Import them **lazily**, inside the card builder, never at app startup.

### 4.3 Small, dependency-free improvements
- B2: pass `state.phone_concurrency` instead of `state.email_concurrency` (`main.py:1776`).
- B4: call `phonsint.core.impersonate.set_global_proxy(proxy)` when `state.proxy_url` is set.
- B5: call `phonsint.core.impersonate.set_global_timeout(timeout)` so the transport honours the UI timeout.
- B7: reuse the email path's `_RATE_LIMITED_RE` (`email_service.py:64-71`) instead of the `"rate" in reason` substring.
- B8: accept `item[0] == "error"` in `phone_service.py:176` and count it.
- B10: use `others.url` for the card's `url_main` in phone mode.
- B15: sort categories in `load_phone_modules`.

---

## 5) Note on phone-mode removal impact

The owner's stated position is "not adding phone-osint / phonsint *not anymore*". Note that a **phone mode already ships** in Sherlock-V3 today (installed, wired, tested, and listed in `pyproject.toml:11` as `phonsint>=0.1.0`). "Not adding" is therefore a different decision from "not removing" — the choice is *keep-and-fix*, *keep-as-is*, or *remove*. If removal is on the table, the blast radius is:

**Production code**
- `src/services/phone_service.py` — the whole file (257 lines), deletable.
- `src/services/user_scanner_compat.py` — the phone-specific parts of the shared compat layer: `:52-58` (`load_phone_modules`), `:101-108` (`get_site_name_phone`, `get_scan_func_phone`), `:294-378` (`run_phone_scan`, `_run_one_phone`). The username/email drivers in the same file stay.
- `src/main.py` — `:88` (import), `:208-210` (cancel wiring), `:516` (instantiation), `:552-553` (controller bindings), `:859-862` (`load_sites` dispatch), `:1728-1840` (`start_phone_search` + the cancel/supersede path).
- `src/core/state.py` — `:58-64` (`phone_results` block), `:79` (`phone_concurrency`).
- `src/core/constants.py` — `:21` (module-count comment), `:77` (`STORAGE_PHONE_CONCURRENCY`), `:83` (`MODE_PHONE`).
- `src/screens/home_screen.py` — `:35` (import), `:469-477` + `:806-809` (concurrency cycler), `:638-640` (input gating), `:669-670` (submit dispatch), `:1110-1141` (the Phone mode chip).
- `src/screens/results_screen.py` — `:25`, `:320-325`, `:369-370`, `:424-425`, `:443-560` (the whole shared email-card branch, which phone mode piggybacks on), `:481-501`.
- `src/screens/settings_screen.py` — `:1194-1222` (the "Phone Intelligence (phonsint)" card) and its `:1765` header.
- `src/screens/sites_screen.py` — `:663` (the Phone segment in the mode switch).
- `src/screens/history_screen.py` — `:17`, `:87` (MODE_PHONE in the stored-entry mode classifier).
- `src/services/cache_service.py` — `:324` (`"phonsint"` in the module-name list).
- `src/core/logger_handler.py` — `:59` (comment), `:70-72` (`phonsint` and `services.phone_service` logger entries).

**Tests**
- `tests/test_phone_mode_parity.py` — the entire file.
- `tests/test_sites_catalog.py` — `:9`, `:21-24`.
- `tests/test_services.py` — `:5`, `:19-20`, `:45`.
- `tests/test_services_all_modes.py` — `:7`, `:48-49`.
- `tests/test_compat_loader.py` — `:47-48`.
- `tests/test_imports.py` — `:16`, `:21`.

**Dependencies**
- `pyproject.toml:11` — drop `phonsint>=0.1.0`.
- `phonenumbers` becomes **fully orphaned**: `phonsint/core/parser.py` is the only non-phonenumbers importer of it anywhere in the venv (verified by grep). It is currently only a *transitive* dependency (never declared directly), so removing phonsint removes it for free — no `pyproject.toml` edit needed for it.
- The app's only use of phonenumbers today is the transitive call inside `parse_phone_number` — **zero direct app usage**.

**Net effect of removal:** roughly 1 service file, ~15 scattered call sites, 6 test files and ~800 lines of code go away, and the app loses a mode with **5 platforms** (Microsoft, Zoho, Amazon, Facebook, Instagram) whose value proposition is "find masked recovery emails / profile metadata from a phone number". Removal is mechanically clean; there is no deep architectural entanglement with the username/email engines.

---

## 6) Verdict

**ISSUES FOUND.**

The wiring is **API-correct but functionally broken**. Every phonsint symbol the app calls exists in the installed package with a compatible signature — no hallucinated APIs, no version drift, no import errors. But the phone mode as shipped does not work correctly:

- **One crash on every live phone scan** (B1 — `results_screen.py:475-476` `AttributeError` on `PhoneSearchProgress.rate_limited` / `.unavailable`), which also means the whole phone results path has **zero** working test coverage.
- **Three user-facing settings are silently discarded**: phone concurrency (B2, wired to `email_concurrency`), region (B3, hardcoded `None`), and proxy (B4, never applied to the transport) — plus a fourth, the network timeout (B5, never applied below the `asyncio.wait_for` wrapper) and a fifth, the loud toggle (B6, hardcoded `False`).
- **The phone-number parser's output is never validated or surfaced** (B11), and the app builds its identity on the **raw** input string (B9) — so the same number in three formats is three different targets, and a mis-parsed number like `07700900123` is scanned as the fabricated `+107700900123` with no warning.
- **Secondary defects**: substring rate-limit detection (B7), dropped error tuples (B8), broken result-card URLs (B10), no progress heartbeat (B17), non-deterministic category order (B15), a shared libcurl handle across threads (B16).

Separately, the app **uses zero of phonenumbers' 9.0.41 surface** — every capability that would make a phone-OSINT UI feel modern (region picker, as-you-type formatting, live validity, geocoder/carrier/timezone context, short-code detection, bulk extraction) is installed and unused.

**Recommendation:** if phone mode stays, treat it as an unvalidated feature — B1 alone means it has never been seen working end-to-end. If phone mode goes, the removal is mechanical (§5) and also orphans `phonenumbers` entirely. Either way, the current state should not be shipped as-is.

---

*No files were modified during this audit.*
