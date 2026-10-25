# Audit — `src/services/phone_service.py`

**File:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/services/phone_service.py` (257 lines)
**Audited against:** installed `phonsint` 0.1.0 (`.venv\Lib\site-packages\phonsint`), `phonenumbers` 9.0.41
**Scope:** this file only. Findings cite `phone_service.py:<line>`; consumers/collaborators are cited for evidence only.

---

## 1) File role

`PhoneService` is the Sherlock-V3 facade over the `phonsint` phone-OSINT engine. It:

- loads the 5 phonsint modules (`microsoft`, `zoho`, `amazon`, `facebook`, `instagram`) via `services/user_scanner_compat.load_phone_modules()` (`:136`);
- publishes a site catalog into the *global* app state (`:100-110`);
- runs a scan in a **dedicated worker thread with its own event loop** (`:213-238`) that drives `user_scanner_compat.run_phone_scan()` — a Sherlock-side re-implementation of `phonsint.core.orchestrator.run_scan_async()` that emits `(kind, category, site_name, result, phone_info)` tuples;
- translates those tuples into two Sherlock-shaped dataclasses, `PhoneResult` (`:25-35`) and `PhoneSearchProgress` (`:38-47`);
- streams progress snapshots to `on_progress` (`:157-171`) so the Flet UI can reuse the email-card shape.

`phonsint.core.orchestrator` and `phonsint.core.helpers.ScanConfig` are **never imported anywhere in `src/`** (verified by grep) — the upstream orchestrator is fully bypassed. That is *correct* (it prints to stdout via `rich.Progress`, `orchestrator.py:116-124`, `orchestrator.py:164`), but it means every upstream capability the compat driver does not replicate is silently lost.

---

## 2) phonsint API verification (every imported/claimed symbol)

| Symbol used by phone_service | Verified against installed phonsint | Verdict |
|---|---|---|
| `phonsint.core.result.Status` (`:51`) | `result.py:62-76`: `TAKEN=0, AVAILABLE=1, ERROR=2, SKIPPED=3` | OK |
| `r.status`, `r.url`, `r.extra`, `r.media` (`:53-62`) | `result.py:79-119` — all exist; `extra`/`media` are plain dicts | OK |
| `r.get_reason()` (`:58`) | `result.py:151-162` — exists; returns `""` when `reason is None`, else `f"{type}: {msg.capitalize()}"` for exceptions | OK |
| `phonsint.core.parser.PhoneInfo` (`:50`, `:179`, `:182`) | `parser.py:6-16`: `raw_input, is_valid, e164, international_format, national_format, country_code, national_number, region_code` | OK — but **`phone_info` is never read** (see F-2.12) |
| `phonsint.core.helpers.get_site_name` (via compat `:102`) | `helpers.py:25-27` → `"Facebook"`, `"Microsoft"`, … (title-cased) | OK |
| `phonsint.core.helpers.load_categories` (via compat `:53`) | `helpers.py:37-47` | OK |
| `phonsint.core.helpers.is_loud` (via compat `:310`) | `helpers.py:9`: **`LOUD_MODULES: List[str] = []`** → `is_loud()` is always `False` | OK, but makes the whole "skipped (loud)" path dead (F-4.1) |
| `phonsint.core.helpers.get_scan_func` (via compat) | `helpers.py:67-73` | OK |
| `phonsint.core.helpers.ScanConfig` | `helpers.py:12-18`: `allow_loud, show_all, verbose, timeout, concurrency` | **Never used** — the compat driver re-implements the loop |
| `phonsint.core.orchestrator.run_scan_async` | `orchestrator.py:72-77`: `(phone_info, configs, category_filter, module_filter)` — **no `on_start` parameter** | **REFUTES the sibling claim "upstream orchestrator offers on_start"** — only the private `_async_worker` (`orchestrator.py:27`) has it, and `run_scan_async` uses it internally for the rich spinner. Never called from `src/`. |
| `phonsint.core.impersonate.set_global_proxy` / `set_global_timeout` | `impersonate.py:17-28` — both exist | **Never called anywhere in `src/`** (grep: only `user_scanner.core.helpers.set_global_timeout` is called, `email_service.py:255`, `sherlock_service.py:101` — a *different* package) → F-3.4 |
| `phonsint.core.impersonate.DEFAULT_TIMEOUT` | `impersonate.py:7` = `15.0` | All curl_cffi requests hard-cap at 15 s regardless of the UI timeout (F-3.5) |
| `phonsint.core.result.Result.update` | `result.py:91-119` — `phone/site_name/category/url` + `extra`/`media` keys are lower-cased and stripped | OK; note `result.phone = phone_info.e164` is set at `user_scanner_compat.py:377` and **dropped** by `_map_result` (F-3.9) |

---

## 3) Confirmed known bugs

### F-3.1 `PhoneSearchProgress` lacks `rate_limited` / `unavailable` → live `AttributeError` (CRITICAL)
- `phone_service.py:38-47` defines only `phone, total_modules, checked_modules, found, not_found, errors, is_running, is_cancelled`.
- `results_screen.py:475-476` reads `active_progress.rate_limited` and `active_progress.unavailable`.
- The path is reachable: `results_screen.py:444` requires `hasattr(active_progress, "checked_modules")` (present), and `results_screen.py:320-325` classifies a `PhoneSearchProgress` as phone mode (`hasattr(x,"phone") and not hasattr(x,"email")`).
- `state.search_progress` is set to a `PhoneSearchProgress` snapshot at `main.py:1395` (via `_apply_progress`) and at `main.py:1756`/`main.py:2031` (history restore). All three paths produce the same class.
- **Result: `AttributeError: 'PhoneSearchProgress' object has no attribute 'rate_limited'`** every time the phone results screen renders a live/progress-backed phone search.

**Fix direction — ADD the fields to `PhoneSearchProgress` (do not change the screen).** Rationale:
1. `EmailSearchProgress` already has exactly `rate_limited` and `unavailable` lists (`email_service.py:58-59`); the phone class is the odd one out, and the screen branch is *shared* with email mode (`results_screen.py:443-479`), so removing the reads would break email mode.
2. The screen's non-progress path already reconstructs the same two buckets from flat row dicts (`results_screen.py:495-500`) — the progress path must supply the same buckets.
3. `_to_dict` (`results_screen.py:446-459`) already handles `PhoneResult` and reads `r.rate_limit` / `r.unavailable` (both exist on `PhoneResult`), so only the *progress-level* lists are missing.

Concretely: add `rate_limited: list[PhoneResult]` and `unavailable: list[PhoneResult]` to `:38-47`, and **populate them** in `_on_result` (`:184-189`) — currently everything non-`exists` is collapsed into `errors`, so adding the fields without populating them would render two permanently-empty tabs and silently drop the rate-limited rows from the "Rate Limited" tab.

### F-3.2 `region` accepted, then hardcoded to `None` (CRITICAL — wrong number scanned)
- `:126` declares `region: str | None = None`; `:198` calls `self._run_worker(phone, None, ...)` — the parameter is discarded. `_run_worker` (`:213`) still takes a `region` argument and forwards it to `run_phone_scan` (`:220`), so the plumbing is 90 % there and broken at exactly one line.
- Empirically verified with the installed `phonsint` parser (`region=None`):
  | input | `parse_phone_number(raw, None)` | `is_valid` | with a region |
  |---|---|---|---|
  | `4155552671` | `+4155552671` (CH, cc=41) | False | `+14155552671` (US) with `region="US"` |
  | `07700900123` | `+107700900123` (fabricated) | False | `+447700900123` with `region="GB"` |
  | `2071838750` | `+2071838750` (EG) | False | — |
  `parser.py:24-27` prefixes a bare national number with `+` and parses it as international, and because that parse *succeeds*, the `"US"` fallback at `parser.py:30` never runs. So a bare US number is scanned as a Swiss number and a bare UK mobile is scanned as a fabricated `+1` number. Every module then queries the wrong identity.
- No `region` setting exists anywhere in the app (`state.py`/`constants.py` have no region field) — `main.py:1773` passes `region=None` explicitly.

### F-3.3 `proxy` accepted and never forwarded (HIGH)
- `:131` `proxy: str = ""` is never read anywhere in the class. `main.py:1778` passes `getattr(state, "proxy_url", "")`.
- `phonsint.core.impersonate.set_global_proxy` (`impersonate.py:26-28`) is **never called in `src/`** → all 5 phonsint modules go out un-proxied while username/email modes honour the proxy (`email_service.py:236-264`, `sherlock_service.py:211`).
- Note the namespace trap: `email_service.py:255` calls `user_scanner.core.helpers.set_global_timeout` — the *user-scanner* package. The phonsint equivalents live in `phonsint.core.impersonate` and are a different, uncalled pair of globals.

### F-3.4 `set_global_timeout` never called → per-request timeout is a hard 15 s (HIGH)
- `impersonate.py:77` does `kwargs.setdefault("timeout", get_global_timeout())` and `get_global_timeout()` returns `DEFAULT_TIMEOUT = 15.0` (`impersonate.py:7,22-23`) because `_global_timeout` is never set.
- The `timeout` argument of `search()` (`:128`) is forwarded only to `run_phone_scan` (`:221`) where it becomes the **module-level** `asyncio.wait_for` budget `timeout + 5` (`user_scanner_compat.py:365`). It never reaches the HTTP layer.
- A module doing two sequential requests (e.g. `facebook.py:29` then `facebook.py:96`, then `facebook.py:211`) burns 15 s per request → the module is killed by `wait_for` at 20 s (default) mid-flow, and the result is reported as `Result.error("Timed out after 20.0s")` — a false negative that the UI shows as "Unavailable".
- Consequence for the UI timeout knob: `main.py:1775` passes `state.timeout` (the **username** knob, default 15) not `state.email_timeout` (default 10) — there is no phone-specific timeout setting at all, and neither value changes the 15 s HTTP cap.

### F-3.5 `phone_concurrency` is dead; `email_concurrency` is used for phone scans (MEDIUM)
- `state.phone_concurrency: int = 15` (`state.py:79`), slider `settings_screen.py:1202-1209`, cycle button `home_screen.py:469-475, 806-809` — all write a value that is never read.
- `main.py:1776` passes `concurrency=getattr(state, "email_concurrency", 15)` into `phone_service.search()`.
- `PhoneService.search` forwards it correctly to `run_phone_scan` (`:221` → `user_scanner_compat.py:331` semaphore), so the *knob* is what's dead, not the plumbing.

### F-3.6 `allow_loud` hardcoded `False` and structurally inert (MEDIUM)
- `main.py:1777` passes `allow_loud=False` unconditionally; there is no settings entry.
- Even if it were `True`: `phonsint.core.helpers.LOUD_MODULES` is an **empty list** (`helpers.py:9`) and `is_loud()` (`helpers.py:21-22`) therefore never matches → `run_phone_scan` (`user_scanner_compat.py:318-322`) never emits a `("skipped", …)` tuple, and the `"skipped (loud)"` branch at `phone_service.py:178-180` is unreachable dead code.
- `settings_screen.py:1220` advertises "phonsint uses pre-auth endpoints only — it never sends SMS or alerts the target" — consistent with upstream reality, which is why the flag is vestigial.

### F-3.7 `PhoneResult` has no phone / E.164 / site-URL identity (HIGH — breaks dedup, enrichment, share)
- `PhoneResult` (`:25-35`) has `name, category, exists, unavailable, rate_limit, url, extra, media, reason`. It has **no phone field** → the E.164 that phonsint already computed (`user_scanner_compat.py:377` sets `result.phone = phone_info.e164`) is dropped, and the raw user input is the only identity (`:152`).
- Consequences:
  - **Dedup across formats is impossible**: `+14155552671`, `4155552671` and `1-415-555-2671` are three different `progress.phone` values for the same target; nothing normalises them.
  - **Enrichment never runs for phone results**: `main.py:1416` looks for `r.url_user` / `r.url_main` on progress results ��� `PhoneResult` has neither → phone results are never queued for avatar enrichment.
  - **The share action crashes**: `app_shell.py:215` does `r.url_user for r in app_state.search_progress.found if r.url_user` — direct attribute access on `PhoneResult` → **`AttributeError: 'PhoneResult' object has no attribute 'url_user'`**. (The sibling copy handler at `app_shell.py:166` uses `getattr(..., None)` and is safe — the two handlers disagree.)
  - The masked email / display name / avatar that phonsint returns (`extra["email"]`, `extra["name"]`, `extra["display_name"]`, `media["avatar"]` — see `modules/social/facebook.py:141-152, 230` and `modules/auth/microsoft.py:121-124`) are copied verbatim into `extra`/`media` (`:81-82`) but are never surfaced as first-class fields, so `main.py:1810` sets `"phoneNumber": None` and `results_screen.py:455` shows `phoneNumber: None`. The most valuable phonsint output (recovered masked email + display name) is invisible in the UI.

### F-3.8 Rate-limit detection is a bare substring; the `errors` bucket swallows both categories (HIGH)
- `:73` `rate_limit = "429" in reason or "rate" in reason.lower()`.
  - False positives: `"rate"` matches *generate, accurate, corporate, separate, moderate, Duration, accelerate*. Any `Result.error(str(exc))` whose message contains one of those is misfiled as rate-limited.
  - False negatives: HTTP **403 / 503 / CAPTCHA / Cloudflare / "Too Many Requests"** are the common block signals and none match except by luck. Upstream modules return `Result.error(...)` for all of them (`facebook.py:112,116`; `microsoft.py:108,112`).
  - The email engine already solved this: `email_service.py:64-67` uses a regex `\b(?:403|429)\b|rate.?limit|too many requests|throttl|cloudflare|captcha|forbidden|waf|blocked`. The phone path should use the same detector.
- `:184-189` routes *both* `rate_limit` and `unavailable` into `progress.errors` — there is no separate bucket, which is exactly why F-3.1 has no consumer. `main.py:1826` then reports `state.phone_error_count = len(result.errors)`, counting rate-limited hits as errors.
- Ordering bug (latent): the `rate_limit or unavailable` test runs **before** the `res.exists` test, so a `TAKEN` result whose reason happens to contain "rate" is moved out of `found` into `errors` and vanishes from the results. Upstream `Result.taken(...)` passes `reason=None` today (`facebook.py:234`) so `get_reason()` returns `""` — no live false positive, but the ordering is wrong by construction and will bite as soon as a module attaches a reason to a hit.

### F-3.9 Phone card URL is `"https://Social"` — the category is used as the domain (HIGH)
Chain, all confirmed:
1. `user_scanner_compat.py:52-57` builds categories as `cat_name.capitalize()` → `"Auth"`, `"Crm"`, `"Shopping"`, `"Social"`.
2. `phone_service.py:77` stores that string in `PhoneResult.category`.
3. `main.py:1801` maps it to the row key `"domain": r.category`.
4. `results_screen.py:522` builds the card link as `url_main=f"https://{r.get('domain','')}"` → **`https://Social`**.
   (`results_screen.py:416` does the same for the detail dialog.)
- The real per-site URL *is* available: `PhoneResult.url` carries `https://www.facebook.com` / `https://account.microsoft.com` (`facebook.py:11,234`, `microsoft.py:15,124`) and is exported as `others.url` (`main.py:1809`) — but the card never uses it; the "Open" button opens a non-resolving host.
- The category capitalization (`"Crm"` instead of `"CRM"`) is cosmetic; the *category-as-domain* substitution is the actual defect.
- **Fix direction:** give `PhoneResult` a proper `domain` (host parsed from `r.url`) and let the row dict's `"domain"` carry that host; keep the category in a separate key. `PhoneResult.url` should become the card's `url_main`.

### F-3.10 No progress heartbeat for slow modules (MEDIUM)
- `_notify` is only called from `_on_result` (`:194`), i.e. only when a module *finishes*. The 0.25 s throttle (`:192`) bounds the tick rate but cannot create a tick: a module hung for the full `timeout + 5` s window produces **zero** UI updates and the progress bar freezes at the previous count for up to 20 s.
- The sibling claim "upstream orchestrator offers on_start" is **refuted as stated** (`orchestrator.py:72-77` has no `on_start`; only the private `_async_worker` does, `orchestrator.py:27`, and `run_scan_async` consumes it internally). The underlying gap is real but belongs to the Sherlock-side driver (`user_scanner_compat.py:299-344` has no `on_start` hook), so the fix is to add one there and count "started" modules in the service.

### F-3.11 No `is_valid` check on the target number (MEDIUM)
- `phonsint`'s own CLI warns and proceeds best-effort (`__main__.py:117-119`).
- The service never inspects `phone_info.is_valid`; the number is parsed inside `run_phone_scan` (`user_scanner_compat.py:316`) where the result is invisible to the service, and the service has no `phone_info` of its own (`:136-152`). So the "not a standard allocated number according to E.164" case — which is *exactly* what a mis-parsed bare national number looks like (F-3.2) — is silently scanned.
- `search()` also does not reject an empty/garbage target; `main.py:1735` only rejects an empty string after `strip()`.

---

## 4) NEW bugs (not in the sibling list)

### F-4.1 `("error", …)` tuples are silently dropped and the counter never reaches 100 % (HIGH)
- `user_scanner_compat.py:360` returns `("error", category, site_name, Exception("no validate_ function"), phone_info)` when a module exposes no `validate_*` function.
- `phone_service.py:176` — `if not item or item[0] not in ("result", "skipped"): return` — discards the `"error"` kind **before** `progress.checked_modules += 1` (`:190`).
- Effect: (a) the failure is never surfaced anywhere; (b) `checked_modules` never reaches `total_modules`, so the progress bar sticks below 100 % and the scan looks hung even though it finished.
- The same drop applies to any module whose coroutine raises outside the driver's `try` (the driver catches per-item exceptions at `user_scanner_compat.py:337-340` and `continue`s **without** emitting an item) — those modules silently vanish from both the results and the counter.

### F-4.2 `status == SKIPPED` is mapped to "Unavailable", losing the upstream "Skipped" state (LOW-MEDIUM)
- `:67-68` → `exists=None`; `:72` → `unavailable = (status == ERROR) or (status == SKIPPED)`; `:79` → `unavailable = unavailable and not rate_limit`.
- The screen's `_make_email_card` (`results_screen.py:509-517`) maps `exists → Claimed`, `rateLimit → Error`, `unavailable → Unavailable`, else `Available`. A SKIPPED module therefore renders as "Unavailable" (an error), and upstream's dedicated "Skipped" label (`result.py:68-73`, `Result.is_visible` treats SKIPPED as visible, `result.py:265-269`) is lost. `PhoneResult` has no `skipped` flag.
- Same lossy mapping for genuine `ERROR`: upstream label "Error" (`result.py:70`) becomes "Unavailable". The screen's `rateLimit → "Error"` branch only fires for rate-limited hits, so ordinary network failures are mislabelled.

### F-4.3 `_map_result` drops the `phone_info` argument and the `Result.phone` value (MEDIUM)
- `:50` `def _map_result(cat, site_name, r, phone_info)` — `phone_info` is **never read** in the body (`:51-85`), and `:183` passes it positionally. Dead parameter.
- `Result.phone` (`result.py:83`, set to `phone_info.e164` at `user_scanner_compat.py:377`) is likewise never read → the service has no way to know the normalised E.164 of the target it just scanned, even though phonsint computed it.

### F-4.4 `PhoneService.__init__` swallows every argument (LOW)
- `:89` `def __init__(self, *args: Any, **kwargs: Any) -> None:` ignores both. Any future constructor option is silently dropped (no `TypeError`), and `main.py:516` `PhoneService()` passes nothing. Compare `EmailService`/`SherlockService` which take explicit parameters.

### F-4.5 `self._tasks` is dead (LOW)
- `:93` initialised, `:150` cleared, never appended to and never read. It is a copy-paste of the email/username service's task registry (`email_service.py` has the same pattern) and does nothing for the phone path.

### F-4.6 `is_available` is hardcoded `True` even when phonsint cannot load (LOW-MEDIUM)
- `:113-115` returns `True` unconditionally; `main.py:1730` gates the whole phone mode on it. If `phonsint` is missing or `load_phone_modules()` raises, the failure surfaces only later as an exception inside `search()` (`:136`) or `_load_and_cache_sites` (`main.py:859-862`) — the user gets "Phone search failed" instead of "Phone search is not available".

### F-4.7 `load_sites()` overwrites the shared global site catalog (MEDIUM)
- `:100-110` writes `state.sites_total` (5), `state.sites_cache`, `state.sites_tags_map`, `state.sites_tag_index` — the *same* globals the email/username engines publish (`email_service.py:177-186`) and that the sites screen and the results-screen fallback consume (`sites_screen.py:228,396,445,589`; `results_screen.py:67,88` → `total = engine_total or state.sites_total or 3300`).
- `main.py:859-862` calls `phone_service.load_sites()` whenever the mode is phone, so the catalog for the whole app collapses to the 5 phone sites until another mode reloads it. `EmailService.load_sites` has the identical flaw, so this is a codebase-wide pattern rather than a phone-only defect — but the phone service is the one that publishes a 5-entry catalog into a field the UI treats as the global site DB.

### F-4.8 Duplicate import and inline `__import__` calls (LOW, style)
- `:102` and `:106` both `from services.user_scanner_compat import get_site_name_phone` in the same function.
- `:155` and `:191` use `__import__("time").monotonic()`; `:231` uses `__import__("contextlib").suppress(Exception)` — instead of top-level `import time` / `import contextlib` (which `email_service.py` does properly). The `__import__` form defeats static analysis and is ~4× slower per call in the hot path.

### F-4.9 `self._progress` is never cleared; the last scan's result lists stay resident (LOW)
- `:153` assigns `self._progress = progress` and nothing ever resets it to `None`. The service retains the full `found/not_found/errors` lists (plus their `extra`/`media` blobs) for the lifetime of the app object.

### F-4.10 `search()` never validates the target and cannot distinguish "0 results" from "scan never ran" (LOW)
- `:135-152` — no parse, no `is_valid` check, no empty-string guard, no E.164 normalisation (F-3.2, F-3.11). `total_modules` is set to `len(modules)` but `phone` keeps the raw string, so `state.current_username` (raw) and the parsed E.164 can differ with nothing recording the difference.

### F-4.11 `_run_worker`'s `except Exception` cannot catch `asyncio.CancelledError` (LOW)
- `:224-225`. On Python 3.8+ `CancelledError` derives from `BaseException`. When `cancel()` (`:246-251`) cancels the driver task, `loop.run_until_complete` raises `CancelledError`, which escapes the `except Exception` handler **unlogged** (the `finally` at `:226-238` still cleans up correctly, so the scan does stop — the defect is the missing diagnostics, not a hang).
- Related: `asyncio.to_thread` (`:197`) cannot interrupt the already-running worker thread; cancellation only takes effect because `run_phone_scan` polls `cancel_event` (`user_scanner_compat.py:333`) and the pending module tasks are cancelled in the `finally` at `:227-232`. In-flight `curl_cffi` calls inside those tasks keep running in their threads until the 15 s HTTP cap.

### F-4.12 Thread-safety of the shared progress object (LOW)
- `progress.found/not_found/errors` are appended from the **worker thread** (`:184-189`) while the main thread reads them via the snapshot copies (`:164-166`). The `list(...)` copies are atomic under the GIL, so no corruption — but `progress.checked_modules += 1` (`:190`) and the list appends are separate operations, and `main.py:1395` assigns the *live* object into `state.search_progress` (the `finally` at `:206-207` passes the live `progress`, not a snapshot) → the UI can read a half-updated object. Low impact, but the live-vs-snapshot asymmetry between `:160-169` and `:206-207` is unintentional.

---

## 5) Minimal fix list (ordered)

Order matters: the contract fix (1-3) must land before the plumbing fixes (4-7), and the plumbing before the cleanup (8-11). Steps 1-3 are strictly additive and cannot break email mode.

**Step 1 — unblock the crash (must be first).**
1. `phone_service.py:38-47` — add `rate_limited: list[PhoneResult]` and `unavailable: list[PhoneResult]` to `PhoneSearchProgress`, mirroring `email_service.py:58-59`. Keep `errors` as the union (it is read by `app_shell.py:300,324` and `main.py:1826`).
2. `phone_service.py:184-189` — populate all three buckets: `rate_limit → progress.rate_limited`, `unavailable → progress.unavailable`, `exists → progress.found`, else `progress.not_found`; keep appending to `progress.errors` as well so existing consumers keep working.
3. `phone_service.py:176` — accept the `"error"` tuple kind as well (`"result"`, `"skipped"`, `"error"`), map it to a `PhoneResult(exists=None, unavailable=True, reason=str(exc))`, and count it (fixes F-4.1 and makes the counter reach 100 %).
   → After 1-3 the results screen renders, and the Rate Limited / Unavailable tabs show real data instead of a crash or two empty tabs.

**Step 2 — result identity / mapping.**
4. `phone_service.py:25-35` — extend `PhoneResult` with: `phone: str = ""` (E.164), `domain: str = ""` (host parsed from `r.url`), and `url_user`/`url_main` aliases (`url_main = r.url`, `url_user = r.url`). This single change fixes: F-3.7 (dedup identity, enrichment queueing, the `app_shell.py:215` share crash) and unblocks F-3.9.
5. `phone_service.py:50,53-85` — use the real URL for the card: derive `domain` from `url` via `urllib.parse.urlparse(url).netloc`; keep `category` as a separate field; propagate `r.phone` (already the E.164) and the parsed `phone_info.e164` into `PhoneResult.phone`.
6. `main.py:1801` + `results_screen.py:416,522` — map `"domain": r.domain` (host) and use `r.url` for `url_main` instead of `f"https://{domain}"`. With step 4-5 this is a one-line change per site and removes `"https://Social"`.
7. `phone_service.py:184-189` — route on `exists` **first**, then `rate_limit`, then `unavailable` (fixes the latent "hit reclassified as error" ordering bug).
8. `phone_service.py:73` — replace the substring test with the shared regex from `email_service.py:64-67` (`403|429|503|rate limit|too many requests|throttl|cloudflare|captcha|forbidden`) and reuse `email_service._is_rate_limited` rather than duplicating it.

**Step 3 — plumbing (settings → service → engine).**
9. `phone_service.py:198` — pass the real `region` (`await asyncio.to_thread(self._run_worker, phone, region, ...)`); add a `region` field to `state` + a settings/home entry; default to the user's locale or `"US"` when the input has no `+` and the parse is invalid. Fixes F-3.2.
10. `phone_service.py:131,196-199` — forward `proxy`: call `phonsint.core.impersonate.set_global_proxy(proxy)` before the scan and restore the previous value afterwards (they are **process-global** — `impersonate.py:13-14` — so restore in a `finally`, and note this mutates state shared with any concurrent user-scanner run; `user_scanner`'s proxy path is env-based, `email_service.py:236-247`, so prefer the env-injection pattern if isolation matters).
11. `phone_service.py:128,196-199` — call `phonsint.core.impersonate.set_global_timeout(timeout)` (same global-setter caveat, same restore-in-`finally` pattern) so the HTTP layer honours the UI timeout instead of the hard-coded 15 s; and give phone mode its own timeout setting (currently it borrows `state.timeout`, `main.py:1775`).
12. `main.py:1776` — pass `getattr(state, "phone_concurrency", 15)` instead of `email_concurrency`, so the existing slider (`settings_screen.py:1202`, `home_screen.py:806`) is live.
13. `phone_service.py:135-136` — parse the number in the service (import `phonsint.core.parser.parse_phone_number`), reject empty input, surface `is_valid == False` as a warning on the progress (mirroring `phonsint/__main__.py:117-119`), and normalise `progress.phone` to the E.164 so dedup/history/re-run match across input formats.
14. `user_scanner_compat.py:299-344` + `phone_service.py:173-194` — add an `on_start` callback to the driver and emit a "module started" tick so a hung module does not freeze the UI for 20 s (F-3.10). Also lower the effective per-module budget or make the HTTP timeout strictly smaller than the module budget.

**Step 4 — cleanup (no behaviour change).**
15. `phone_service.py:178-180` — the `"skipped (loud)"` branch is unreachable (`LOUD_MODULES == []`, `helpers.py:9`): either delete it plus the `allow_loud` parameter (`:130`, `:198`, `:221`), or keep it and add the upstream loud-module registry. If kept, expose the flag in settings instead of hardcoding `False` (`main.py:1777`).
16. `phone_service.py:88-94` — drop `*args/**kwargs` from `__init__`; remove the dead `self._tasks` (`:93`, `:150`).
17. `phone_service.py:96-111` — remove the duplicate import (`:106`); namespace the phone catalog so it does not clobber the shared `state.sites_*` globals (F-4.7), or have `main.py` call it through a phone-scoped path.
18. `phone_service.py:113-115` — make `is_available` reflect a real import probe.
19. `phone_service.py:155,191,231` — replace `__import__("time")` / `__import__("contextlib")` with top-level imports.
20. `phone_service.py:50` — drop the unused `phone_info` parameter of `_map_result` (or use it per step 5).
21. `phone_service.py:206-207` — pass a **snapshot** (like `:160-169`) to the final `on_progress`, matching the in-flight ticks.
22. `phone_service.py:153` — clear `self._progress` (or keep only counters) after completion.

---

## 6) Verdict

**Phone mode is functionally broken end-to-end and should not ship in its current form.**

- The results screen raises `AttributeError` on every phone-mode render (F-3.1) — phone mode cannot show results at all.
- Even with that patched, the scan targets the **wrong identity** for any bare national number (F-3.2, empirically confirmed), silently ignores the user's proxy (F-3.3) and the UI timeout (F-3.4), and renders broken `"https://Social"` links (F-3.9).
- The phonsint payload that makes the feature valuable — recovered masked email, display name, avatar (`extra["email"]`, `extra["name"]`, `media["avatar"]`) — is fetched but never surfaced (F-3.7), and phone results never receive enrichment because `PhoneResult` lacks `url_user`/`url_main`.
- Roughly 40 % of the file is dead or inert: `region`, `proxy`, `allow_loud`, `self._tasks`, the `*args/**kwargs` constructor, the "skipped (loud)" branch (unreachable because `LOUD_MODULES` is empty), the unused `phone_info` parameter, and the entire upstream orchestrator/`ScanConfig` surface that is never imported.
- The engine itself is fine: `phonsint` 0.1.0 exposes exactly the symbols the service uses (`Status`, `Result`, `PhoneInfo`, `get_site_name`, `get_scan_func`, `parse_phone_number`, `impersonate.set_global_proxy/set_global_timeout`) — there are **no hallucinated APIs** in this file. The defects are in the wrapper: dropped parameters, dropped fields, and a progress contract that does not match the screen that consumes it.

**Honest note on removing phone mode.** Dropping phone mode is defensible and would delete this whole class of bugs, at the cost of: this file (`src/services/phone_service.py`, 257 lines), the `phonsint` dependency, `phonenumbers` (orphaned — `grep` shows `phonenumbers` is imported only by `phonsint.core.parser`), the 5 phone modules (`microsoft`, `zoho`, `amazon`, `facebook`, `instagram`), the phone UI blocks in `home_screen.py` / `results_screen.py` / `settings_screen.py` / `sites_screen.py` / `onboarding_screen.py` / `app_shell.py` / `profile_detail_dialog.py` / `result_card.py` / `stat_card.py` / `state.py` / `constants.py` / `main.py` (~67 phone references), and 5 test files (`tests/test_phone_mode_parity.py`, `tests/test_services.py`, `tests/test_services_all_modes.py`, `tests/test_compat_loader.py`, `tests/test_sites_catalog.py`, plus `tests/test_imports.py`). That is a large, mostly-mechanical removal — but it deletes a feature that upstream `phonsint` demonstrably supports (pre-auth-only, non-alerting endpoints) and that the settings screen already advertises. **Recommendation: if phone mode stays, apply steps 1-14 above (≈2-4 h of work); if it goes, remove it wholesale rather than leaving it half-wired** — the current state is worse than either option.
