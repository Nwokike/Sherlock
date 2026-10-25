# Audit — `src/services/email_service.py` (445 lines)

Sherlock V3 · file-audit subagent · 2026-10-20
Ground truth: installed `user-scanner 1.5.2.3` at `.venv\Lib\site-packages\user_scanner` (Python 3.14.7).
Read-only audit — no file was modified.

---

## 1) File role

`EmailService` is the Flet-facing facade for **email OSINT**. It loads user-scanner's `email_scan/*` modules,
drives them through `services/user_scanner_compat.run_email_scan`, and re-shapes upstream `Result` objects into
the legacy Sherlock contract (`EmailResult` / `EmailSearchProgress`) so `src/main.py` and the results screen need
no changes. It also exposes `run_hudson()` (Hudson Rock infostealer lookup) and `cancel()`.

Structure:

| Lines | Role |
|---|---|
| 25–100 | Pure helpers: `validate_email`, `_domain_from`, `_first`, `_recovery_from`, `_phone_from`, `_RATE_LIMITED_RE` |
| 112–160 | `_map_result` — upstream `Result` → `EmailResult` translation |
| 163–198 | `EmailService.__init__`, `load_sites`, `is_available`, `total_modules` |
| 200–341 | `search()` — the async entry point (proxy/timeout setup, progress, worker dispatch) |
| 343–412 | `_run_worker` — runs the scan on a private event loop in a worker thread, then an optional cross-scan pass |
| 414–427 | `run_hudson` — Hudson Rock wrapper |
| 429–445 | `cancel` — cancellation entry point |

The file deliberately **bypasses** upstream's `user_scanner.core.email_orchestrator` (which is CLI-coupled:
`rich.Progress` + `print()`), re-implementing the batch loop in `services/user_scanner_compat.py`.
That decision is the root of the most serious bug in this file (see **C5**).

---

## 2) Engine API verification

Every upstream symbol this file touches was checked against the installed package.

| API used | Where | Installed location | Verdict |
|---|---|---|---|
| `user_scanner.core.helpers.is_valid_email(email) -> bool` | `:31` | `core/helpers.py:465` | ✅ real |
| `user_scanner.core.helpers.set_global_timeout(float)` | `:256` | `core/helpers.py:457` | ✅ real (module-global, **never reset** — see C3) |
| `user_scanner.core.helpers.set_proxy_manager(proxies=[...])` | `:264` | `core/helpers.py:680` | ✅ real, kwargs match |
| `user_scanner.core.result.Status` (`TAKEN/AVAILABLE/ERROR/SKIPPED`) | `:113` | `core/result.py:68` | ✅ real |
| `Result.status / .reason / .url / .extra / .media / .get_reason()` | `:115-152` | `core/result.py:87-190` | ✅ all present |
| `user_scanner.core.cross_scan.CrossScanConfig(links, emails, depth, sweep)` | `:375-380` | `core/cross_scan.py:60-79` (`@dataclass(frozen=True)`) | ✅ real; all 4 kwargs are valid fields (`modules`/`categories` left default) |
| `user_scanner.core.hudson.run_hudson_scan(target, is_email=False)` | `:423` | `core/hudson.py:49` | ✅ signature matches |
| `services.user_scanner_compat.{load_email_modules, run_email_scan, get_site_name_user, is_loud_user, load_user_modules, run_cross_scan_async}` | `:18-21, :178, :222, :370` | `src/services/user_scanner_compat.py` | ✅ all exist |
| `user_scanner.core.helpers.get_site_name(module)` | via compat | `core/helpers.py:496` | ✅ real — **but see N1**, it never leaves underscores in the result |

**No hallucinated APIs.** Every import resolves against the installed package.

Three upstream APIs the audit brief asked about are *deliberately not used*:

- **`ScanConfig`** — not imported anywhere in this file or in `user_scanner_compat`. Upstream's
  `email_orchestrator._run_batch` takes a `ScanConfig`; the app re-implements the batch loop instead
  (`user_scanner_compat.py:220-258`). Consequence: the module-level `httpx` monkeypatch that upstream installs
  as an import side-effect (`core/email_orchestrator.py:24-52`) is **never** installed by this code path → **C5**.
- **`Result.is_visible(configs)`** (`core/result.py:291`) — not used. This is *correct* for the app: upstream
  hides `AVAILABLE`/`ERROR` results unless `show_all=True`, but the app needs every result to fill its four
  buckets. No change needed.
- **`Result.to_csv()`** (`core/result.py:200`) — not used. The app's export path is
  `services/report_service.generate_csv_report` (`src/services/report_service.py:119`), which uses a plain
  `csv.writer` and therefore **never runs upstream's `_neutralize_csv_cell()` formula-injection guard**
  (`core/result.py:26-33`). Email rows carry attacker-controlled `extra` strings from remote sites, so the
  CSV-export hardening that upstream ships is bypassed for every email result. (Export code lives outside this
  file; flagged because this file is the producer of that data.)

**Result-mapping fidelity** (`_map_result`, `:112-160`): `TAKEN` → `exists=True`, `AVAILABLE` → `exists=False`,
everything else → `exists=None` + rate/unavailable split. Two gaps: `Status.SKIPPED` is not special-cased
(**N3**) and the tuple tag `"error"` produced by the compat layer is dropped entirely (**N2**).

---

## 3) Confirmed known bugs

### C1 — Hudson: `input()` deadlock + raw ANSI capture — **CONFIRMED (worse than described)**
`:414-427`
```python
def run_hudson(self, target: str, is_email: bool = True) -> str:
    import contextlib, io
    from user_scanner.core import hudson
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            hudson.run_hudson_scan(target, is_email=is_email)
    except Exception as exc:
        logger.warning("hudson scan failed: %s", exc)
        return f"Hudson check failed: {exc}"
    return buf.getvalue().strip()
```
- `run_hudson_scan` → `check_hudson_permission(target)` (`core/hudson.py:22-46`). When
  `user_scanner/config.json` has `auto_hudson_prompt` unset (default **True**), it executes
  `input(...)` at `core/hudson.py:36`. `contextlib.redirect_stdout` redirects **stdout only** — `input()` reads
  `sys.stdin` and writes its *prompt* to stdout. Result: the prompt is swallowed into `buf` while the read
  blocks on the real stdin. In a Flet desktop app stdin is usually not a console → immediate `EOFError`
  (caught → `"Hudson check failed: EOF when reading a line"`) or an indefinite block of the worker thread.
  The call site is `src/main.py:1575` (`asyncio.to_thread(self.email_service.run_hudson, ...)`), so the hang
  occupies a thread-pool thread indefinitely, and the "result" is the prompt text, not a report.
- The returned string is the raw captured stdout and contains **colorama ANSI escapes**
  (`core/hudson.py:9-12`: `R/G/C/Y/M` = `Fore.*`, `X` = `Style.RESET_ALL`). `buf.getvalue().strip()` (`:427`)
  removes whitespace, not escape sequences. `src/main.py:1579` renders the first 120 chars in a SnackBar →
  the user sees raw `\x1b[31m…` sequences.
- `run_hudson_scan` returns `None`; the "permission denied" case and the "no infostealer infections found"
  case are indistinguishable in the returned blob.

### C2 — Dead cancel path: `loop.is_running()` always False, `_tasks` never populated — **CONFIRMED**
`:429-445` / `:317-319` / `:343-412`
- `self._worker_loop` (`:319`) is set to `worker_loop`, created at `:317` **in the caller's (UI) thread** and
  never `run_forever()`/`run_until_complete()`-ed → `loop.is_running()` is **always False** → the
  `if loop is not None and loop.is_running():` guard at `:434` can never be true → `_cancel_all` is never
  scheduled → `self._tasks` is never iterated.
- The **real** work runs on a *different* loop, created inside the worker thread at `:346`
  (`loop = asyncio.new_event_loop()`) and driven by `loop.run_until_complete(_run())` at `:401`. That loop is
  never assigned to `self._worker_loop`, so `cancel()` structurally cannot reach the live module tasks.
- `self._tasks` is written at `:168` (init), `:234` (clear), `:405` (read), `:411` (clear), `:437` (read) —
  **never appended to**. Both the cancel sweep (`:435-440`) and the pending-task cleanup (`:405-410`) are dead code.
- The only effective cancel is `self._thread_cancel` (a `threading.Event`), honoured by
  `user_scanner_compat.py:248` (`break` out of the `asyncio.as_completed` loop). But that `break` leaves the
  task list created at `user_scanner_compat.py:245` **running and un-awaited**, and the loop is then
  `close()`d at `:412` → `Task was destroyed but it is pending!` and skipped cleanup/teardown of in-flight
  httpx/aiohttp sessions.

### C3 — Stale proxy leak: `set_proxy_manager` only called when a proxy exists — **CONFIRMED**
`:260-266`
```python
try:
    from user_scanner.core.helpers import set_proxy_manager
    if proxy:
        set_proxy_manager(proxies=[proxy])
except Exception:
    pass
```
`set_proxy_manager()` (`core/helpers.py:680-686`) assigns the global `_proxy_manager`, and **resets it to
`None` when called with neither argument**. Because the call is guarded by `if proxy:`, a proxy installed by a
previous scan (the username path, `user_scanner_compat.py:132-135`, or the previous email scan) stays live for
the next scan that has no proxy. Repro: set a proxy → run an email scan → clear the proxy in settings → run
another email scan → the old proxy is still used for the 40 impersonate modules (they call `get_proxy()`
directly, `core/impersonate.py:44`). Fix: always call
`set_proxy_manager(proxies=[proxy] if proxy else [])`.

### C4 — `use_curl_cffi` / `use_stealth_fingerprint` are a no-op — **CONFIRMED (worse than described)**
`:207`, `:210`, `:250-251`
```python
use_curl_cffi: bool = True,
...
*, use_stealth_fingerprint: bool | None = None,
...
if use_stealth_fingerprint is None:
    use_stealth_fingerprint = use_curl_cffi
```
`use_stealth_fingerprint` is assigned at `:251` and **never read again** — grep shows only three occurrences
(`:210` the parameter, `:250`, `:251`). It is never passed to `run_email_scan` (`:357-365`), never to
`set_proxy_manager`, never to any upstream call. `use_curl_cffi` is read exactly once, at `:251`, to feed that
dead value.

Meanwhile the 40 curl_cffi/impersonate email modules **always** impersonate (`"chrome"` default,
`core/impersonate.py:9`) regardless of the flag. So the settings toggle labelled *"Chrome 131 JA3/H2 fingerprint
to bypass WAF 403 blocks"* (`src/screens/settings_screen.py:959-962`) is a lie on the email path: it can neither
be turned on nor off. This is a **user-visible false affordance**, not just dead code.

### C5 — 180/220 email modules never receive the proxy (httpx monkeypatch never installed) — **CONFIRMED**
`:357-368`
Measured on the installed package (`user_scanner/email_scan/*/*.py`, 220 modules total):

| Stack | Count | Gets the proxy? |
|---|---|---|
| raw `httpx.AsyncClient` | **180** | ❌ only if `user_scanner.core.email_orchestrator` was imported |
| `core.impersonate` (curl_cffi) | **40** | ✅ via `get_proxy()` inside `core/impersonate.py:44` |

The raw-httpx path receives the proxy **only** through the module-level monkeypatch in
`core/email_orchestrator.py:24-52` (it rewrites `httpx.AsyncClient.__init__`/`httpx.Client.__init__` to inject
`get_proxy()` and the global timeout). `user_scanner.core.email_orchestrator` is imported by exactly three
places in the whole package: `core/cross_scan.py:26`, `__main__.py:23`, `mcp/handlers.py:26`.

This file reaches it only at **`:368`**, via `from user_scanner.core.cross_scan import CrossScanConfig`, which is:
1. inside `if getattr(state, "cross_scan_enabled", False):` — and `src/core/state.py:70` defaults
   `cross_scan_enabled = False`; **and**
2. **after** `await run_email_scan(...)` at `:357` has already completed.

⇒ In the default configuration the email scan never installs the monkeypatch, so **180 of 220 email modules
talk to the internet directly, ignoring the user's proxy**, and the `proxy=` argument of `search()` is a no-op
for them. It also means `set_global_timeout(float(timeout))` (`:256`) never reaches those 180 modules — they
silently use httpx's default **5 s** timeout instead of the user's `email_timeout`.

Worse, the behaviour is **order-dependent**: if the user has ever run a *username* scan with cross-scan enabled
(`src/services/sherlock_service.py:223` imports `cross_scan` → `email_orchestrator`), the monkeypatch leaks into
the process and then **all 220** modules get the proxy. Same settings, different network path, depending on
scan history. A second side-effect of the patch: it forces `kwargs["timeout"] = get_global_timeout()` on *every*
httpx client in the process, overwriting `core/hudson.py:68`'s explicit `httpx.Client(timeout=10.0)`.

### C6 — Main-thread event loop clobbered — **CONFIRMED, but severity LOW (not a crash)**
`:317-318`, `:335-340`
```python
worker_loop = asyncio.new_event_loop()
asyncio.set_event_loop(worker_loop)     # :318  (UI thread)
self._worker_loop = worker_loop
...
asyncio.set_event_loop(None)            # :337  (finally, UI thread)
worker_loop.close()                     # :340
```
`search()` runs as a coroutine on the Flet main loop, so `:318` replaces the main thread's *current* loop with a
brand-new loop that is never run, and `:337` unsets it entirely. In Python **3.14** (this venv is 3.14.7)
`asyncio.get_event_loop()` raises `RuntimeError` when no current loop is set, so any main-thread code that
later calls `get_event_loop()` breaks. In-app impact is limited because the codebase consistently uses
`asyncio.get_running_loop()` (`src/main.py:471`, `src/services/cache_service.py:675`,
`src/services/http_client.py:91`, `user_scanner_compat.py:201,280`) — but flet internals and third-party code are
exposed. Note the same pattern exists in `src/services/sherlock_service.py:261/272` and
`src/services/phone_service.py:215/236`; the email variant is the worst of the three because its loop is pure
dead weight (it exists only to feed the broken cancel path of C2).

### C7 — Rate-limit detection "by substring instead of regex" — **REFUTED, the claim is INVERTED**
The **email** path is the one that uses a proper regex:
`src/services/email_service.py:64-71`
```python
_RATE_LIMITED_RE = re.compile(
    r"\b(?:403|429)\b|rate.?limit|too many requests|throttl|cloudflare|captcha|forbidden|waf|blocked",
    re.IGNORECASE)
```
used at `:153` via `_is_rate_limited(message)`.

The **username** path is the naive substring check:
`src/services/sherlock_service.py:81-82`
```python
if "429" in low or "rate" in low:
    return "rate"
```
⇒ The sibling-audit claim is backwards. **No change is needed in this file**; `sherlock_service` should adopt
the email regex. (A real but *different* issue in this file's regex is noted as **N3b**.)

### C8 — "App silently caps generated emails at 5" — **CONFIRMED, but the cap is NOT in this file**
The domain provisioning logic lives in `src/main.py:1067-1105`, not here. Findings:

- `parse_email_domain_scopes` (`core/helpers.py:474`) is called at `src/main.py:1073`. Verified against the
  installed package: **`EMAIL_DOMAIN_SCOPES` has 41 scopes / 273 unique domains**, and
  `parse_email_domain_scopes("all")` returns 273 unique domains. The `all` scope is honoured correctly
  upstream.
- The cap is **`src/main.py:1081`**: `for addr in generated[:5]:  # cap to avoid huge scans` → "all" (273
  addresses) is silently truncated to 5 with **no UI indication**; the other 268 addresses are dropped without
  a log line.
- `src/main.py:1074-1075` `except Exception: domains = []` swallows the `ValueError` that
  `parse_email_domain_scopes` raises for an unknown scope (`"Unknown email domain scope 'x'. Valid scopes: …"`),
  so a typo in the settings field **silently disables the whole feature** with no user-facing error.
- `src/main.py:1099-1102` sets `state.email_found_count` / `email_not_found_count` / `email_rate_limited_count`
  / `email_unavailable_count` from the **last** address only, while `state.email_results` accumulates across all
  5 and `state.email_results_address` (`:1098`) also holds only the last → the results screen shows five
  addresses' worth of rows attributed to a single address.
- In **this** file the only related surface is `EmailResult.domain`, which is broken (**N1**).

---

## 4) NEW bugs / hallucinations

### N1 — HIGH — `_domain_from` fabricates a `.com` domain; the underscore branch is dead code
`:74-81`, used at `:115` and `:297`
```python
def _domain_from(name: str, url: str | None) -> str:
    if url and str(url).startswith(("http://", "https://")):
        from urllib.parse import urlparse
        host = urlparse(str(url)).netloc.lower().split(":")[0]
        if "." in host:
            return host.removeprefix("www.")
    dotted = name.replace("_", ".")
    return dotted if "_" in name else f"{dotted}.com"
```
- `get_site_name` (`core/helpers.py:496-500`) returns
  `module.__name__.split(".")[-1].capitalize().replace("_", ".")` — **underscores are already gone**, so
  `"_" in name` is never True for a real site name. The first branch of the ternary is **dead code**, and
  every name without a URL becomes `<DisplayName>.com`.
- The two branches mean completely different things: with a URL → a real hostname (`classmates.com`); without
  → an invented one (`Classmates.com`, capitalised — the fallback path never lowercases).
- `Result.url` defaults to `""` (`core/result.py:94`), so **every error/skip result** falls into the
  fabricated branch. `src/main.py:1092` and `:1588` copy `r.domain` straight into `state.email_results`,
  which the results screen groups by.
- Fix: return the parsed host when there is one, `""` otherwise — never synthesise `.com`; lowercase the result.

### N2 — MEDIUM — results tagged `"error"` are silently dropped; `checked_modules` never reaches `total_modules`
`:290-294`
```python
def _on_result(item):
    if self._thread_cancel.is_set():
        return
    if not item or item[0] not in ("result", "skipped"):
        return
```
`user_scanner_compat._run_one_email` returns `("error", category, site_name, Exception("no validate_ function"))`
(`user_scanner_compat.py:274`). That tag is filtered out at `:293`, so the module is neither bucketed nor
counted: `progress.checked_modules` stalls below `progress.total_modules` and the UI's "N/M" counter never
reaches M (the final `_notify()` at `:313` requires `checked_modules == total_modules` to fire). Fix: accept
the `"error"` tag and bucket it as unavailable with the exception text.

### N3 — MEDIUM — `Status.SKIPPED` is misreported as "unavailable"
`:141-160`
`_map_result` special-cases `TAKEN` and `AVAILABLE`; **everything else** (including `SKIPPED`) falls into the
last branch → `exists=None, rate_limit=…, unavailable=not rate`. A module that legitimately returns
`Result.skipped()` is therefore reported as a site that is "unavailable", inflating `state.email_unavailable_count`.
Same for the loud-skip path at `:295-298`, whose `"skipped (loud)"` message lands in `progress.unavailable`.
Fix: add a `skipped` bucket (or `others["skipped"] = True`) so skipped ≠ failed.

**N3b — the rate-limit regex conflates "rate limited" with "blocked"** (`:64-67`).
`403|429|rate.?limit|too many requests|throttl|cloudflare|captcha|forbidden|waf|blocked` classifies a WAF/CAPTCHA
block as a **rate limit**. Most email modules report WAF blocks as `Result.error("Caught by WAF (403) …")`
(e.g. `email_scan/social/classmates.py`), so those land in `progress.rate_limited` instead of
`progress.unavailable` — the user is told the site rate-limited them when it actually blocked them. The two
should be separate buckets (mirroring `sherlock_service._badge_for`, which does distinguish `"bot"` from
`"rate"` at `src/services/sherlock_service.py:78-82`).

### N4 — MEDIUM — `cancel()` lets a new scan resurrect the cancelled one and corrupts the shared slot
`:230-234` + `:429-445`
- `cancel()` (`:443-445`) sets `progress.is_running = False` **immediately**, while the worker thread is still
  running.
- The re-entry guard at `:230` only tests `self._progress.is_running` → after a cancel it is False → a new
  `search()` is admitted, and `:233 self._thread_cancel.clear()` **un-sets the cancel flag the old worker is
  still polling**, so the old scan keeps running.
- Both scans then share the **same** `threading.Event` (`self._thread_cancel`) and the same `self._progress`
  slot (overwritten at `:269`) — cancelling the new scan also stops the old one, and `cancel()` flags the wrong
  progress object.
- `src/main.py:1494` (`_kill_all_activity`) and `:1503-1508` rely on exactly this sequence, so the race is
  reachable from the UI.
- Fix: allocate a fresh `threading.Event` per scan, keep the current one in a dedicated slot, and never clear an
  Event a still-running worker may be reading.

### N5 — MEDIUM — the proxy env injection is process-global and restored from a stale snapshot
`:236-248`, `:329-330`
```python
saved = {k: os.environ.get(k) for k in ("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","http_proxy","https_proxy","all_proxy")}
for k in (...): os.environ[k] = proxy
```
- `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` are **process-global**; httpx honours them (`trust_env=True` by
  default), so this affects *any* concurrently running scan (including a username scan) and any other library.
- The same proxy string is advertised for both http and https traffic.
- The restore at `:330` replays a snapshot taken at `:240`; if a second scan started in between, the restore
  reinstates the *first* scan's proxy (snapshot inversion) or clobbers the second scan's proxy.
- Fix: rely on the proxy-manager path (which the impersonate modules already use) and drop the env mutation, or
  serialise it behind a lock with a reference count.

### N6 — MEDIUM — `set_global_timeout` is never restored → process-wide timeout leak
`:253-258`
`set_global_timeout(float(timeout))` sets a **module-global** in `core/helpers.py:455` that is read by
`core/impersonate.py::_timeout()` and by the httpx monkeypatch. It is never reset. `src/services/sherlock_service.py:101`
sets the *same* global from a *different* setting (`state.timeout`), so the two services fight over one global
and whichever ran last wins for the other's modules. Fix: save/restore around the scan, or make the timeout
per-scan.

### N7 — LOW — worker failures are swallowed; the caller cannot distinguish "done" from "crashed"
`:400-403`
```python
try:
    loop.run_until_complete(_run())
except Exception:
    logger.exception("email scan worker failed")
```
`search()` then returns a `progress` with `is_running=False` and whatever partial results arrived.
`src/main.py:1562-1572` logs `"email search COMPLETE"` and fires `scan_notify.scan_finished(...)` as if nothing
went wrong — the only signal is a log line the user never sees. Fix: capture the exception, expose it on the
progress object (or re-raise) and have `main.py` surface it.

### N8 — LOW — `EmailResult.method` and `EmailResult.frequent_rate_limit` are never populated
`:40`, `:44`, `:112-160`; consumed at `src/main.py:1093` / `:1591`
`_map_result` never passes `method=` and never sets `frequent_rate_limit` → they are permanently `""` / `False`.
`main.py` copies them into the result dicts, so the results screen renders an always-empty "method" field and a
constant "not frequently rate limited" badge. Upstream has no such concept (`Result` has no rate counter), so
`frequent_rate_limit` would have to be computed here (per-domain rate-limit counts) or removed from the contract.

### N9 — LOW — `use_stealth_fingerprint` is a public parameter of a public method that does nothing
`:210`, `:250-251` (see C4). A caller passing `use_stealth_fingerprint=False` gets no behaviour change and no
error. Either implement it (forward it to the impersonate layer, e.g. via a `core.impersonate` knob) or delete it.

### N10 — LOW — `load_sites()` writes two mutually-inconsistent global site indexes and duplicates imports
`:171-187`
```python
app_state.sites_tags_map = {get_site_name_user(m): [cat] for cat, m in self._modules}  # site -> [category]
...
by_tag.setdefault(cat, []).append(get_site_name_user(m))
app_state.sites_tag_index = by_tag                                                       # category -> [site]
```
Both maps target the **same globals** that `src/services/sherlock_service.py:120/126` and
`src/services/phone_service.py:104/110` overwrite. The direction is consistent (site→tags, tag→sites), but the
**key format differs between services**: `sherlock_service` fills `sites_tag_index` with the raw module file stem
(`m.__name__.split(".")[-1]`, e.g. `"classmates"`), `email_service` fills it with the display name
(`"Classmates"`). Whichever service loaded last wins, and the Sites screen filter
(`src/screens/sites_screen.py:403-410`, `:445`) silently misses depending on load order.
Also: `from core.state import state as app_state` is repeated at `:172`, `:176`, `:178` and
`from services.user_scanner_compat import get_site_name_user` at `:178` and `:182` (5 redundant imports in a
17-line method); and the `mode` parameter (`:171`) is **ignored** — the method always loads email modules.

### N11 — LOW — `is_available` is hard-coded `True`
`:189-191`
It never verifies that `user_scanner` imports, that the email categories exist, or that the venv is intact — yet
`src/main.py:1069` and `:1458` gate real functionality on it. A broken install presents as "available" and then
every `search()` raises `ImportError` from deep inside the worker (swallowed by N7).

### N12 — LOW — `validate_email` silently degrades to a *looser* regex on any exception
`:28-34`
```python
try:
    from user_scanner.core.helpers import is_valid_email
    return bool(is_valid_email(email))
except Exception:
    return bool(EMAIL_FORMAT.fullmatch(email or ""))
```
The fallback `EMAIL_FORMAT` (`:25`) is looser than upstream's `EMAIL_RE` (`core/helpers.py:25`): it permits a
trailing dot in the domain, consecutive dots, and a local part with leading/trailing dots. If the import ever
fails, the app accepts addresses the engine will reject — and the real error is hidden. Fix: catch `ImportError`
specifically and mirror upstream's semantics in the fallback.

### N13 — LOW — `__import__("re")` instead of `import re`
`:25`, `:64-67`
`__import__("re")` does return the `re` module, so it works — but it is obscure, defeats linting/static
analysis, and is inconsistent with the file's otherwise-clean import block. Use a normal `import re`.

### N14 — LOW — `_first()` silently drops dict-shaped values
`:84-91`
`_first` returns `None` for a `dict` (a plausible shape for `public_emails`/`phone_numbers`) and treats `0` as
falsy, so `_recovery_from` (`:94-100`) and `_phone_from` (`:103-109`) can miss real recovery-email / phone data
without any signal.

### N15 — LOW — the final progress tick passes the **live** object, not a copy
`:331-334` vs `:276-286`
`_notify()` correctly clones the progress before handing it to the callback; the `finally` block passes the live
`progress` object, which the worker thread was mutating until moments earlier. Use the same copy semantics.
Also `:331-334` writes `on_progress(progress) if on_progress else None` as a bare conditional expression and
swallows the exception with `except Exception: pass` (no logging), so a failing final callback is invisible.

### N16 — LOW — `skip_password_recovery` does not change network behaviour, only accounting
`:221-228`
The filter drops modules whose site name is in `LOUD_MODULES["email"]` (`core/helpers.py:29-…`, non-empty).
But `user_scanner_compat.run_email_scan` (`:236-238`) already skips exactly the same set whenever
`allow_loud` is False — and `src/core/state.py:67` defaults `allow_loud = False`. So:
- `allow_loud=False` → loud modules are never contacted either way; the toggle only changes whether they appear
  as "skipped/unavailable" rows or vanish from `total_modules`.
- `allow_loud=True` → `run_email_scan` **does** contact them, and the app's pre-filter is the only thing that
  honours `skip_password_recovery`.
The user-facing toggle ("skip password recovery", `state.no_password_recovery`) therefore does not do what its
name promises in the default configuration.

### N17 — INFO — `progress` object is mutated from the worker thread and read from the UI thread
`:311` (worker) vs `:332` (UI). The GIL makes the increments safe, but the final tick can observe a torn view
(`found` list non-empty while `checked_modules` lags). The copy-based `_notify()` (`:276-286`) is the right
pattern; use it for the final tick too (see N15).

### N18 — INFO — no hallucinated API usage found
Every `import` in this file resolves against the installed `user-scanner 1.5.2.3` package. No invented
functions, no wrong signatures, no calls to removed APIs. The defects above are **lifecycle and semantics**, not
API fabrication.

---

## 5) Improvements (ordered)

**P0 — correctness / user-visible truth**
1. **Install the httpx proxy patch before the scan** (fixes C5, the most impactful bug). Import
   `user_scanner.core.email_orchestrator` (or re-implement its 25-line patch locally in
   `user_scanner_compat.py`) at the **top** of `run_email_scan` — not lazily at `:368` *after* the email pass.
   Until then, 180/220 modules bypass the user's proxy and their timeout.
2. **Fix `_domain_from`** (N1): return the parsed host or `""`; never synthesise `.com`; lowercase. This
   currently feeds fabricated hostnames into the results screen.
3. **Make `cancel()` real** (C2): hand the *worker's* loop to the service (assign `self._worker_loop = loop`
   at `_run_worker:346`), populate `self._tasks` with the module tasks, and cancel them on `cancel()`.
   Otherwise remove the dead code and document that only the `threading.Event` cancels the scan.
4. **Make the Hudson call non-interactive and ANSI-free** (C1): set `auto_hudson_prompt=False` in
   `user_scanner/config.json` before calling, or call the Hudson Rock HTTP API directly instead of
   `hudson.run_hudson_scan`; strip ANSI with a regex (`\x1b\[[0-9;]*m`) from `buf.getvalue()`; and
   distinguish "declined / no results" from "found".
5. **Accept the `"error"` tuple tag** (N2) and add a `skipped` bucket (N3); split "rate limited" from
   "bot-blocked" (N3b).

**P1 — resource / state hygiene**
6. Always call `set_proxy_manager(proxies=[proxy] if proxy else [])` (C3).
7. Save/restore `set_global_timeout` around the scan (N6) and stop sharing one global with `sherlock_service`.
8. Drop the process-global proxy env mutation in favour of the proxy-manager path, or guard it with a
   reference-counted lock (N5).
9. Give each scan its own `threading.Event`; never clear an Event a live worker may read (N4).
10. Remove the dead `worker_loop` at `:317-318` and the `set_event_loop(None)` at `:337` (C6) — or, if the
    pattern must stay (it is duplicated in `sherlock_service`/`phone_service`), make all three consistent and
    restore the *previous* loop instead of `None`.

**P2 — dead code / contract hygiene**
11. Either implement `use_curl_cffi` / `use_stealth_fingerprint` (forward to `core.impersonate`) or remove them
    and the settings toggle that advertises them (C4, N9). Today the toggle is a false affordance.
12. Populate or delete `EmailResult.method` and `EmailResult.frequent_rate_limit` (N8).
13. Deduplicate the imports in `load_sites`, honour its `mode` parameter, and align the
    `sites_tag_index` key format with the other two services (N10).
14. Make `is_available` actually probe the engine (N11); narrow `validate_email`'s `except Exception` to
    `ImportError` and align the fallback regex with upstream (N12); use a plain `import re` (N13).

**P3 — robustness / observability**
15. Surface worker exceptions instead of swallowing them (N7) so `main.py` can show a real error.
16. Use copy semantics for the final progress tick (N15, N17).
17. Keep the email regex (C7) and port it to `sherlock_service.py:81-82`, which uses the naive
    `"429" in low or "rate" in low` substring check.
18. Cross-file follow-ups (outside this file, but caused by it):
    `src/main.py:1081` — make the 5-address cap visible (log the truncation, show "5 of 273" in the UI) or
    make it configurable; `src/main.py:1074-1075` — surface the `ValueError` from
    `parse_email_domain_scopes` instead of silently dropping to `domains = []`; `src/main.py:1099-1102` —
    aggregate the per-address counters instead of reporting only the last address;
    `src/services/report_service.py:119` — apply upstream's `_neutralize_csv_cell` guard
    (`core/result.py:26-33`) to email rows, which carry attacker-controlled `extra` strings.

---

## 6) Verdict

**Structurally sound, semantically leaky. Not a rewrite; a focused hardening pass would do.**

- **No hallucinated APIs.** Every import resolves against installed user-scanner 1.5.2.3; the `CrossScanConfig`
  kwargs, the `Result` attribute accesses, `set_global_timeout`/`set_proxy_manager` and
  `hudson.run_hudson_scan` are all real and correctly invoked. This file is *more* careful than its sibling
  `sherlock_service.py`, which uses a naive substring rate-limit check (C7).
- **The central architectural flaw is the bypass of `user_scanner.core.email_orchestrator`** (C5). Re-implementing
  the batch loop to escape the CLI-coupled `rich`/`print` output was the right call, but the app also inherited
  that module's import-time `httpx` monkeypatch as a side effect and never asked for it. Result: **180 of 220
  email modules ignore the user's proxy and timeout in the default configuration**, and the behaviour becomes
  history-dependent once any cross-scan has run. This is the single highest-value fix in the file.
- **Cancellation is a facade** (C2): `self._worker_loop` points at a loop that never runs, `self._tasks` is never
  populated, and the only working mechanism is a `threading.Event` whose `break` leaks pending tasks and closes
  the loop underneath them. The `cancel()` method's cancel-sweep and the pending-task cleanup are both dead code
  that reads as if it works.
- **The proxy/timeout state is not scoped to a scan** (C3, N5, N6): a stale proxy manager, a global timeout
  shared with the username service, and process-wide `HTTP_PROXY` mutation that is restored from a stale
  snapshot.
- **The result contract carries two always-empty fields** (`method`, `frequent_rate_limit`, N8) and a
  **fabricated `domain`** (N1) that the results screen groups by.
- **Two settings are false affordances**: `use_curl_cffi` / `use_stealth_fingerprint` (C4) and, in the adjacent
  file, `skip_password_recovery` (N16).
- **Two silent-truncation / silent-failure paths** originate outside this file but are directly downstream of it:
  the 5-address cap at `src/main.py:1081` (against 41 scopes / 273 domains) and the swallowed scope-parse
  `ValueError` at `src/main.py:1074-1075`.

Recommended order: **C5 → N1 → C2 → C1 → N2/N3** (correctness and truthfulness first), then the P1 hygiene set
(C3, N6, N5, N4, C6), then the P2 dead-code sweep, then the cross-file follow-ups listed in P3.18.
