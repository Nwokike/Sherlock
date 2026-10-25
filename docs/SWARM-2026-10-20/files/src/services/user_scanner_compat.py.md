# Audit — `src/services/user_scanner_compat.py` (552 lines)

**Auditor:** file-audit subagent · **Date:** 2026-10-22 · **Scope:** this file only (read-only; nothing modified)

**Ground truth used:** `user-scanner 1.5.2.3` (`.venv/Lib/site-packages/user_scanner`), `phonsint 0.1.0`, CPython **3.14.7**, `os.cpu_count() == 4`.

---

## 1) File role

`user_scanner_compat.py` is the app's *claimed* single boundary to the third-party engines. Its stated contract (`user_scanner_compat.py:1-13`) is:

1. it is **the only** module that imports `user_scanner` / `phonsint` internals (`:3-5`);
2. it does tolerant module loading so one bad import cannot abort a category (`:8-9`, `:61-83`);
3. it drives scans asynchronously and streams progress via callbacks instead of stdout (`:10-11`);
4. it cancels via `threading.Event` + a private worker loop (`:12`).

What it actually contains is five responsibilities stacked in one file:

| Lines | Unit | Engine touched |
|---|---|---|
| `:33-58` | `load_user_modules` / `load_email_modules` / `load_phone_modules` | user_scanner + phonsint |
| `:61-83` | `_load_modules_tolerant` (private import loader) | — |
| `:86-108` | thin re-export shims (`get_site_name_user`, `get_scan_func_user`, `is_loud_user`, `get_site_name_phone`, `get_scan_func_phone`) | user_scanner + phonsint |
| `:116-212` | `run_username_scan` + `_run_one_user` | user_scanner |
| `:220-291` | `run_email_scan` + `_run_one_email` | user_scanner |
| `:299-378` | `run_phone_scan` + `_run_one_phone` | **phonsint** (different engine, different `Result` class, different tuple arity) |
| `:386-552` | `run_cross_scan_async` — a hand-rolled re-implementation of upstream `run_cross_scan` | user_scanner (+ 12 **private** upstream symbols) |

The file is not an adapter — it is a **re-implementation** of `user_scanner.core.orchestrator`, `user_scanner.core.email_orchestrator` and `user_scanner.core.cross_scan`. Because it re-implements rather than delegates, it must track upstream's *private* API (`_fresh_pivots`, `_split_budget`, `_sweep_targets`, `_email_targets`, `_tag`, `_tag_emails`, `_apply_confidence`, `_followable`, `_named_targets`, `_already_swept`, `_already_scanned`) — a much more fragile coupling than the docstring claims.

**Consumers** (for context, not audited): `src/services/sherlock_service.py:19-23,205,231`, `src/services/email_service.py:18-20,357,384`, `src/services/phone_service.py:17-19,219`.

---

## 2) Engine API verification

Every symbol this file touches, checked against the installed package.

### 2.1 `user_scanner.core.helpers` — **all names exist, all signatures match**

| Compat site | Upstream symbol | Installed signature | Verdict |
|---|---|---|---|
| `:35,44` | `load_categories` | `load_categories(is_email: bool = False, no_nsfw: bool = False) -> Dict[str, Path]` (`helpers.py:519-535`, `@lru_cache`) | OK (kwargs match) |
| `:87` | `get_site_name` | `get_site_name(module) -> str` (`helpers.py:496-500`) | OK |
| `:92` | `get_scan_func` | `get_scan_func(module) -> Optional[Callable[[str], Any]]` (`helpers.py:543-551`) | OK (but never called by the file — see D-3) |
| `:97` | `is_loud` | `is_loud(name: str, is_email: bool = False) -> bool` (`helpers.py:538-540`) | OK |
| `:132` | `set_proxy_manager` | `set_proxy_manager(proxy_file=None, proxies=None)` (`helpers.py:680-686`) | OK **call**, wrong reset semantics — see B-1 |
| `:137-140,184,231,263` | `get_site_name`, `is_loud`, `get_scan_func` | as above | OK |
| `:415,428` | `ScanConfig` | `@dataclass(frozen=True) ScanConfig(allow_loud, no_nsfw, show_all, verbose, timeout: Optional[float])` (`helpers.py:447-453`) | OK — all 5 kwargs exist, in order, with correct types |
| `:415,496` | `find_category` | `find_category(module) -> str \| None` (`helpers.py:565-574`) | OK |
| `:416,446` | `rank_usernames` (`core.pivots`) | `rank_usernames(pivots) -> List[str]` (`pivots.py:423`) | OK |
| `:400,425` | `Confidence` (`core.confidence`) | `class Confidence(Enum)` (`confidence.py:60`) | OK |

**Not used at all (missing capability, not a broken call):** `helpers.load_modules` (`helpers.py:503`, `@lru_cache`), `helpers.find_module` (`helpers.py:554`), `helpers.set_global_timeout` (`helpers.py:457`), `helpers.get_global_timeout`, `helpers.get_proxy`/`get_proxy_count`, `core.orchestrator.run_user_full` / `run_user_module` / `run_user_category` (`orchestrator.py:259,165,172`), `core.email_orchestrator.run_email_full_batch` / `run_email_module_batch` (`email_orchestrator.py:314,205`), `core.engine.check` / `check_category` / `check_all` (`engine.py:12,45,59`), `core.cross_scan.run_cross_scan` + `CrossScanConfig` (`cross_scan.py:82,60`), `core.hudson`, `core.patterns`, `core.formatter`. Every one of these is a public upstream entry point that this file bypasses — the whole point of the adapter.

### 2.2 `user_scanner.core.cross_scan` — 12 **private** symbols, all present, but the public entry point is bypassed

`_already_scanned` (`cross_scan.py:282`), `_already_swept` (`:254`), `_apply_confidence` (`:484`), `_email_targets` (`:362`), `_followable` (`:304`), `_fresh_emails` (`:292`), `_fresh_pivots` (`:265`), `_named_targets` (`:413`), `_split_budget` (`:318`), `_sweep_targets` (`:333`), `_tag` (`:455`), `_tag_emails` (`:475`) — **all exist with the signatures used**. No hallucinated symbol in this file.

But the compat **re-implements** `run_cross_scan` (`cross_scan.py:82-184`) instead of calling it, and in doing so it drops the two scoping mechanisms upstream has: `_scope()` (`cross_scan.py:187-207`) and `_email_scope()` (`:210-251`). See B-4 / N-1 / N-6.

`CrossScanConfig` (`cross_scan.py:60-79`) has 6 fields: `links, modules, categories, emails, sweep, depth`. The compat reads only **`links` (`:440`), `emails` (`:441`), `sweep` (`:419`), `depth` (`:418`)**. **`modules` and `categories` are never read anywhere in the file.** Upstream's CLI *does* populate them (`__main__.py:666-671`: `modules=_csv_names(args.module), categories=_csv_names(args.category)`); the app's callers do not (`sherlock_service.py:224-229`, `email_service.py:375-380`).

### 2.3 `user_scanner.core.result` — OK

`Result.error(reason)` (`result.py:137`), `Result.update(**kwargs)` accepting `("username","site_name","category","is_email","url")` (`result.py:100-104`). The compat's `result.update(site_name=…, username=…, category=…, is_email=False)` at `:211` and `:290` is valid; `is_email=False` is not `None`, so it is applied (`result.py:103`). `USResult.error(exc)` preserves the exception so `get_reason()` can format `"Type: msg"` (`result.py:166-169`).

### 2.4 `phonsint` — OK (all 5 modules, all signatures match)

`phonsint.core.helpers.load_categories()` (no args — `helpers.py:37`), `get_site_name` (`:25`), `get_scan_func` (`:67`), `is_loud(site_name)` (`:21`, single positional — the compat calls `is_loud(name)` at `:321`, correct); `phonsint.core.parser.parse_phone_number(raw, default_region=None)` (`:19`) returns `PhoneInfo` with `.e164` (`parser.py:7-17`); `phonsint.core.result.Result.update` accepts `("phone","site_name","category","url")` (`result.py:91-94`) — the compat's `result.update(site_name=…, phone=…, category=…)` at `:377` is valid. The arg-shape heuristic at `:362-363` is a **faithful copy** of upstream `phonsint/core/orchestrator.py:52-53`.

### 2.5 Module counts and loader behaviour (measured)

| Set | Modules | Categories | With `validate_` | Without |
|---|---|---|---|---|
| `user_scan` (incl. adult) | **2,521** | 16 | 2,521 | **0** |
| `user_scan` (`no_nsfw=True`) | 2,499 | 16 | 2,499 | 0 |
| `email_scan` | 220 | 20 | 220 | **0** |
| `phonsint` | 5 | — | 5 | **0** |

`LOUD_MODULES["user"]` is an **empty list** (`helpers.py:27-28`) → the loud gate at `:156` can never fire for username scans; `LOUD_MODULES["email"]` has 53 unique entries → the email gate at `:236` does fire.

### 2.6 Concurrency ground truth

* Upstream username path: `orchestrator.py:28` — `_shared_executor = ThreadPoolExecutor(max_workers=max(60*2, 250))` → **250 workers**; `set_concurrency` keeps `max(val*2, 250)`.
* Upstream email path: `email_orchestrator.py:200,216,242` — `loop.set_default_executor(ThreadPoolExecutor(max_workers=250))` → **250 workers**, installed on the loop *because* the workers call `run_in_executor(None, …)`.
* Upstream semaphores: `MAX_CONCURRENT_REQUESTS = 60` (`orchestrator.py:27,199`), email `configs.concurrency`.
* **This file:** `loop.run_in_executor(None, …)` at `:203` and `:282`, `asyncio.to_thread` at `:368` — all on an app-created loop (`sherlock_service.py:260`, `email_service.py:346`, `phone_service.py:216`) that **never installs a 250-worker executor**. Default = `min(32, cpu+4)` = **8** on this box.

---

## 3) Confirmed known bugs

### B-1 — Global proxy manager is set but never reset → stale-proxy leak  ✅ **CONFIRMED (High)**

`:130-135`

```python
if proxy:
    try:
        from user_scanner.core.helpers import set_proxy_manager
        set_proxy_manager(proxies=[proxy])
    except Exception:
        pass
```

`set_proxy_manager` (`helpers.py:680-686`) only replaces the global when `proxy_file or proxies is not None`; **`set_proxy_manager(None, None)` is the documented reset** (`helpers.py:685-686` → `_proxy_manager = None`). Because the call is guarded by `if proxy:`, a scan started **without** a proxy leaves the *previous* scan's `ProxyManager` installed. `helpers.get_proxy()` (`helpers.py:689-693`) is consulted by every request through `orchestrator.make_request` (`orchestrator.py:298-301`), so **every subsequent scan silently inherits the old proxy** — including scans from the email service, which sets its own proxy the same way (`email_service.py:262-265`) and never resets it either.

Aggravating: the bare `except Exception: pass` at `:134-135` also swallows `ProxyManager`'s `ValueError("No valid proxies found in list")` (`helpers.py:632`) — a malformed proxy fails *silently* and the scan then runs **without** the proxy the user asked for, while the global manager still holds the previous one.

**Fix:** always call the setter, and reset when there is no proxy:

```python
from user_scanner.core.helpers import set_proxy_manager
try:
    set_proxy_manager(proxies=[proxy]) if proxy else set_proxy_manager(None, None)
except Exception:
    logger.warning("proxy setup failed", exc_info=True)
```

### B-2 — `run_in_executor(None, …)` → 8-thread default executor instead of upstream's 250  ✅ **CONFIRMED (High)**

`:203` (username), `:282` (email), `:368` (phone, via `asyncio.to_thread`).

`loop.run_in_executor(None, …)` uses `loop._default_executor`, created lazily as `ThreadPoolExecutor()` → `max_workers = min(32, os.cpu_count()+4)` = **8** here. Upstream uses **250** (`orchestrator.py:28`) and — for the email path — explicitly installs a 250-worker default executor on the loop (`email_orchestrator.py:200,216,242`) precisely because its workers use `run_in_executor(None, …)`. The app's loops are created by the services, not by upstream, so the 250-worker executor is **never** installed.

Effect: the semaphore permits 50 concurrent username modules (`:150`) / 30 email modules (`:244`) / 100 phone modules (`:329`), but only **8** can actually be in flight. For 2,499 user modules that is a ~6× throughput loss on the primary scan and far worse on a cross-scan sweep (3 pivots × 2,499 modules).

**Fix:** mirror upstream — module-level `_shared_executor = ThreadPoolExecutor(max_workers=max(concurrency*2, 250))` in this file, or `loop.set_default_executor(ThreadPoolExecutor(max_workers=250))` at the start of each driver.

### B-3 — `break` out of `as_completed` without cancelling the remaining tasks  ✅ **CONFIRMED (High)**

`:168-170`, `:247-249`, `:332-334`

```python
for coro in asyncio.as_completed(tasks):
    if cancel_event.is_set():
        break
```

In CPython 3.14 `as_completed` returns `_AsCompletedIterator` (`asyncio/tasks.py`), whose `_handle_completion`/`_wait_for_one` contain **no cleanup path**: breaking out simply abandons the iterator. The `asyncio.create_task(...)` handles created at `:160-163`, `:245`, `:330` are **never cancelled** — they keep running, keep holding semaphore slots, and keep their thread-pool jobs queued. Worse, in 3.13+ plain-iterator mode `__next__` returns a *coroutine* (`_wait_for_one(resolve=True)`); the coroutine yielded in the iteration where `break` fires is never awaited → `RuntimeWarning: coroutine '_wait_for_one' was never awaited`.

The services then call `loop.close()` (`sherlock_service.py:270`, `email_service.py:412`, `phone_service.py:238`) with tasks still pending → `Task was destroyed but it is pending!`. `loop.close()` does call `executor.shutdown(wait=False)` (verified in 3.14 `base_events.py`), but `wait=False` means the **in-flight HTTP requests keep running in background threads** after the UI reports "cancelled".

**Fix:** cancel explicitly — keep the task list and, in a `finally`, `for t in tasks: t.cancel()` then `await asyncio.gather(*tasks, return_exceptions=True)`; and always `await` the yielded coroutine (or use `asyncio.wait(tasks, return_when=FIRST_COMPLETED)`).

### B-4 — Cross-scan hard-codes `scope=None` → site/category selections ignored, every pivot sweeps all 2,521 modules  ✅ **CONFIRMED (Critical)**

`:492`

```python
named = _named_targets(pivots, swept, checked, scan_cfg, None)
```

Upstream computes the scope first and threads it through every stage:

```
run_cross_scan (cross_scan.py:82)
  └─ scope = _scope(cross_configs, configs)              # cross_scan.py:94 → :187-207
     email_modules = _email_scope(cross_configs, configs) # cross_scan.py:95 → :210-251
  ├─ usernames sweep:  run_user_full(username, configs) if scope is None
  │                    else run_user_module(scope, username, configs)      # cross_scan.py:150-154
  ├─ named targets:    _named_targets(pivots, swept, checked, configs, scope) # cross_scan.py:157
  │                    → allowed = {m.__name__ for m in scope}                # cross_scan.py:438
  └─ email targets:    run_email_full_batch(...) if email_modules is None
                       else run_email_module_batch(email_modules, ...)       # cross_scan.py:168-172
```

The compat has **no `_scope` / `_email_scope` equivalent at all**. Consequences:

* `cross_config.modules` and `cross_config.categories` are **never read** anywhere in the file (grep-verified). Upstream's CLI populates both from `-m/-c` (`__main__.py:666-671`).
* `_named_targets(..., None)` → `allowed = None` (`cross_scan.py:438`) → the site filter is skipped entirely (`cross_scan.py:442-443`).
* The sweep at `:475-485` passes **`all_user_modules`** — the complete list — instead of the scoped set. Upstream would call `run_user_module(scope, …)` when a scope exists (`cross_scan.py:153`).
* The per-scan site selection (`state.selected_sites`, filtered in `sherlock_service.py:148`) is **not forwarded** into `run_cross_scan_async` at all, and the cross-scan's `run_username_scan` calls (`:475`, `:503`) pass no `selected` → `:143-144` filters nothing.

Net effect: with `depth=1, sweep=3` (the app default, `sherlock_service.py:228`) the cross-scan launches up to **3 × 2,499 = 7,497** module scans plus the named-target pass, against the *entire* module universe, even if the user selected 5 sites. With B-2 (8 workers) this is a multi-minute silent stall.

**Fix (call chain to change):**

1. `run_cross_scan_async` gains a `scope` parameter and computes it exactly like upstream:
   ```python
   from user_scanner.core.helpers import find_module, load_categories, load_modules
   def _scope(cross_config, no_nsfw):
       if cross_config.modules:
           return [m for n in cross_config.modules
                   for m in find_module(n.replace(".", "_"), is_email=False, no_nsfw=no_nsfw)]
       if cross_config.categories:
           paths = load_categories(False, no_nsfw)
           return [m for n in cross_config.categories if n in paths
                   for m in load_modules(paths[n])]
       return None
   ```
2. `:492` → `_named_targets(pivots, swept, checked, scan_cfg, scope)`.
3. `:475-485` → sweep `scope` (or `all_user_modules` when `scope is None`), and forward the caller's `selected` set so `:143-144` can filter.
4. Callers (`sherlock_service.py:224-229`, `email_service.py:375-380`) must populate `CrossScanConfig(modules=…, categories=…)` from `state.selected_sites` / the category selection — today they set neither.

### B-5 — Upstream cross-scan helpers `print()` to stdout; the compat never redirects them  ✅ **CONFIRMED (Medium-High)**

`:448` (`_sweep_targets`) and `:457` (`_email_targets`) call upstream functions that print unconditionally:

* `cross_scan.py:341-349` — “Username sweep off — checking only the sites pivots named.”
* `cross_scan.py:355-358` — “Not sweeping N username(s) … — raise --cross-sweep”
* `cross_scan.py:367-370` — “The -m/-c restriction names no email module, so no address is scanned.”
* `cross_scan.py:376-378` — “No sweep budget left for N address(es)”
* `cross_scan.py:384-388` — “Not scanning N address(es) …”

There is **no `contextlib.redirect_stdout` anywhere in this file** (grep-verified). The only stdout captures in the codebase are the Hudson wrappers (`sherlock_service.py:278-290`, `email_service.py:414-427`) — which cover `core.hudson`, not the cross-scan. The file's own docstring claims “stream progress via callbacks **instead of printing to stdout**” (`:10-11`); for the cross-scan path that claim is false — upstream's coloured `Fore.YELLOW` messages leak into the Flet process console on every round.

**Fix:** wrap the two calls, e.g. `with contextlib.redirect_stdout(io.StringIO()): usernames = _sweep_targets(pivots, for_usernames)`, and surface the captured text through `on_result`/logger instead.

### B-6 — The phone driver lives in this file (mixed responsibility); no progress heartbeat; ("error", …) tuples dropped  ✅ **CONFIRMED (Medium)**

`:299-378`. Findings:

* **Mixed responsibility:** `:52-58`, `:101-108`, `:299-378` are `phonsint`, a *different engine* with a *different* `Result` class, a *different* `get_site_name`/`is_loud`/`get_scan_func` (`phonsint/core/helpers.py:21,25,67`) and a **different tuple arity** — 5 elements here (`:322`, `:360`, `:378`) vs 4 for user/email (`:158`, `:195`, `:212`). `phone_service.py:179,182` unpacks 5 accordingly. The file's "one adapter" premise does not hold for phonsint: an upstream user-scanner upgrade does not cover it, and the two tuple protocols must be kept in sync by hand.
* **No progress heartbeat:** the phone driver reports only per-result; `phone_service.py:190-194` throttles notifications to 0.25 s, so a slow module produces no intermediate feedback. (With only 5 modules this is cosmetic, but the same driver shape is used for the 2,521-module user path where it is not.)
* **Dropped ("error", …) tuples:** `:360` emits `("error", category, site_name, Exception(...), phone_info)`; `phone_service.py:176` accepts only `("result","skipped")` → the tuple is discarded and `progress.checked_modules` never advances for it.
* `phone_info.is_valid` (`phonsint/core/parser.py:8`) is never surfaced to the caller: `run_phone_scan` returns `phone_info` (`:344`) but neither it nor `phone_service` checks the flag before launching modules.

### B-7 — ("error", …) tuples dropped by callers → progress counters stall  ⚠️ **PARTIALLY CONFIRMED (Medium)**

`:195`, `:274`, `:360` emit an `("error", …)` tuple; all three consumers discard it:

* `sherlock_service.py:186-187` → `if not item or item[0] != "result": return`
* `email_service.py:293-294` → `if not item or item[0] not in ("result", "skipped"): return`
* `phone_service.py:176` → `if not item or item[0] not in ("result", "skipped"): return`

**Mitigation found:** the `("error", …)` branch is only reached when `get_scan_func(module) is None` (`:194`, `:273`, `:359`). Measured: **0 of 2,521 user modules, 0 of 220 email modules and 0 of 5 phone modules lack a `validate_` function** → the branch is currently **unreachable** (dead defensive code). The `("skipped", …)` tuple *is* reachable for the email path (`LOUD_MODULES["email"]`, 53 entries) and is handled by `email_service.py:295-298` / `phone_service.py:178-180`; but `sherlock_service.py:186` drops it — harmless for the user path only because `LOUD_MODULES["user"]` is empty.

**The live counter-stall bug is different and bigger:** `sherlock_service.py:172` sets `total_sites = len(all_modules)` (2,499) while the compat filters to the user's `selected` set at `:143-144` **without reporting the filtered-out modules**. With a site selection active, `progress.checked_sites` can never reach `total_sites` → the progress bar never completes. See N-5.

### B-8 — Tolerant loader silently skips broken modules — how much does it hide?  ✅ **CONFIRMED, but currently hides nothing (Medium)**

`:61-83`. Measured on this install: **0 modules skipped** — the compat loads 2,499 user / 220 email / 5 phone modules, exactly matching upstream's `load_modules` count. So the tolerance machinery is not currently masking anything.

The real defect is **observability**:

* `:81-82` logs the skip count at **INFO** — invisible at the app's default log level, and never shown in the UI. A site that silently disappears from the scan list is invisible to the user.
* `:80` logs at WARNING per module, but the message is `skipped module %s: %s` with no category context (`:66` `skipped` list is built but only used for the count).
* The upstream `load_modules` (`helpers.py:503-516`) is `@lru_cache(maxsize=None)`; the compat **re-implements it without the cache** (see N-8) — so the compat pays the full import cost on *every* call, which is the opposite of the efficiency the upstream caching was designed to provide.
* `_load_modules_tolerant` skips every file starting with `__` (`:68-69`) whereas upstream skips only `__init__.py` (`helpers.py:507`) — currently equivalent (no `__`-prefixed non-`__init__` modules exist in the tree).

### B-9 — Polling-based cancellation is the only cancellation mechanism  ✅ **CONFIRMED (Medium)**

`:120,153,169,187,190,224,248,266,269,304,333,352,355,392,437,467,494,521` — cancellation is a `threading.Event` polled between module boundaries. There is no `asyncio` cancellation path: the checks happen only *before* a module starts and *between* `as_completed` iterations, so:

* a module already running cannot be interrupted (B-3), and
* the poll interval is the module's own runtime — with `module_timeout = timeout + 10` (`:197`, `:276`, `:364`) a cancel can take up to ~25 s to be observed on the username path.

The event is also *shared* with the services (`sherlock_service.py:150`, `email_service.py:290`), which additionally cancel loop tasks directly (`phone_service.py:250-256`) — two overlapping cancellation mechanisms with different semantics, only one of which the compat honours.

### B-10 — The "one file to touch" contract is violated  ✅ **CONFIRMED (Medium)**

`:3-5` claims “This is the ONLY module that imports user-scanner / phonsint internals.” Grep of `src/` shows **17 direct import sites outside this file**:

```
src/main.py:1071              from user_scanner.core.helpers import parse_email_domain_scopes
src/screens/settings_screen.py:666  from user_scanner.core.helpers import validate_proxies
src/services/cache_service.py:334   import user_scanner as _us
src/services/sherlock_service.py:101 from user_scanner.core.helpers import set_global_timeout
src/services/sherlock_service.py:223 from user_scanner.core.cross_scan import CrossScanConfig
src/services/sherlock_service.py:281 from user_scanner.core import hudson
src/services/sherlock_service.py:300-301 from user_scanner.core.result import Result, Status
src/services/phone_service.py:51      from phonsint.core.result import Status
src/screens/home_screen.py:555        from user_scanner.core.helpers import validate_proxies
src/services/email_service.py:31      from user_scanner.core.helpers import is_valid_email
src/services/email_service.py:113      from user_scanner.core.result import Status
src/services/email_service.py:255      from user_scanner.core.helpers import set_global_timeout
src/services/email_service.py:262      from user_scanner.core.helpers import set_proxy_manager
src/services/email_service.py:368      from user_scanner.core.cross_scan import CrossScanConfig
src/services/email_service.py:418      from user_scanner.core import hudson
```

The most damaging are `set_global_timeout` (`sherlock_service.py:101`, `email_service.py:255`) and `set_proxy_manager` (`email_service.py:262`) — **global mutable engine state set from outside the adapter**, i.e. exactly the state the compat itself also mutates at `:130-135`. Two owners for one global.

---

## 4) NEW bugs (severity-ordered)

### N-1 — **Critical** — Cross-scan scope: `cross_config.modules` / `cross_config.categories` are read nowhere, and the caller's site selection is not forwarded

Covered mechanically under B-4; listed separately because it is the highest-impact *new* finding (B-4 covers only the hard-coded `None`). Two independent leaks:

1. `run_cross_scan_async` never references `cross_config.modules` / `cross_config.categories` (grep-verified across the whole file). The two scoping knobs upstream exposes via `-m/-c` are inert.
2. The signature (`:386-398`) has **no `selected` parameter**, so `sherlock_service.py:148`'s `selected` set never reaches the sweep. `run_username_scan` supports a `selected` filter (`:125`, `:143-144`) but the cross-scan calls at `:475-485` and `:503-513` omit it.

**Impact:** a user who selects 5 sites still triggers ~7,500 module requests in the cross-scan round — a guaranteed multi-minute stall, with the UI showing a spinner and no explanation.

### N-2 — **High** — `usable_email_modules` is computed but has **no effect** on what gets scanned

`:450-457`

```python
usable_email_modules = [m[1] for m in all_email_modules]
if not allow_loud:
    usable_email_modules = [m for m in usable_email_modules
                             if not is_loud_user(get_site_name_user(m), is_email=True)]
to_scan = _email_targets(ranked, for_emails, usable_email_modules)
```

Upstream's `_email_targets` (`cross_scan.py:362-389`) uses its `modules` argument **only** for the emptiness check (`cross_scan.py:365-371`); the actual scanning is decided by `run_email_full_batch` vs `run_email_module_batch` (`cross_scan.py:168-172`). The compat passes `all_email_modules` to `run_email_scan` at `:529-538` — **always every email module** — so the computed list never narrows anything. The loud filter is also re-applied inside `run_email_scan` (`:236-238`), so the work at `:451-456` is duplicated and misleading: it *looks* like the email scope is restricted, but it is not.

Upstream's `email_modules` is `None` only when `configs.allow_loud` and no `-m/-c` restriction (`cross_scan.py:240-241`) — a distinction the compat has flattened.

### N-3 — **High** — `_named_targets` returns upstream-cached modules; the scan uses compat-loaded modules → two distinct module objects per site

`:492-496`. Upstream `_named_targets` resolves sites via `find_module(site, is_email=False, no_nsfw=…)` (`cross_scan.py:448`), which uses the **upstream `@lru_cache`d** `load_modules` (`helpers.py:503`). The compat's primary scan uses its own tolerant loader (`:61-83`). The same site therefore exists as two different `ModuleType` instances with separate module-level state, and enabling the cross-scan forces the app to import **all 2,499 modules twice** — once through `helpers.load_modules` (measured 5.3 s) and once through `_load_modules_tolerant` (measured 2.8 s). See also N-8.

### N-4 — **High** — The `timeout` parameter does not control HTTP timeouts

`:197`, `:276`, `:364` use `timeout` only for the **outer** `asyncio.wait_for`. The **per-request** timeout comes from `helpers.get_global_timeout()` inside `orchestrator.make_request` (`orchestrator.py:292-296`): `kwargs["timeout"] = global_timeout` if set, otherwise `5.0`. The compat never calls `set_global_timeout` (`helpers.py:457-459`), so the user's timeout setting reaches the HTTP layer only because the *services* happen to call `set_global_timeout` (`sherlock_service.py:101-104`, `email_service.py:255-257`) — outside the adapter (B-10) and, for the phone path, not at all. Consequence: the UI's timeout slider does not apply to HTTP requests when the compat is driven directly, and the two timeouts (`timeout` vs `timeout+10`) can disagree with the actual socket timeout.

### N-5 — **High** — Filtered-out modules are never reported → the progress bar can never complete

`:142-147`. When `selected` is active, the compat silently discards every non-selected module. The caller sets `total_sites = len(all_modules)` (`sherlock_service.py:163,172`) — the **unfiltered** count — and increments `checked_sites` only for `("result", …)` tuples (`sherlock_service.py:186-191`). The discarded modules are invisible to the progress model, so `checked_sites / total_sites` is permanently short and the UI's percentage never reaches 100 %. The same applies to `("skipped", …)` (dropped at `sherlock_service.py:186`) and to `("error", …)`.

**Fix:** emit a `("skipped", cat, name, None)` tuple for every module removed by the `selected` filter, and let the caller count it (email/phone callers already accept `"skipped"`).

### N-6 — **Medium-High** — `run_cross_scan_async` returns results that were already emitted, and the two channels can diverge

`:463-542`. The sweep/named/email collectors (`:471-473`, `:499-501`, `:525-527`) keep only `item[0] == "result"`, so `("skipped", …)` and `("error", …)` tuples are dropped **before** `_tag` (`:486`, `:514`, `:539`). The tagged results are then pushed to the outer `on_result` (`:489`, `:517`, `:542`) — so the caller sees them once — while `cross_results` (`:463,487,515,540`) accumulates the same objects. Both callers ignore the return value (`sherlock_service.py:231`, `email_service.py:384`), so today there is no double-count; but the API shape invites it, and the returned list contains *unfiltered* result sets (including `Status.AVAILABLE` and `Status.ERROR`) whereas `_apply_confidence` (`:548`, `:551`) only scores `is_found()` hits (`cross_scan.py:502`).

### N-7 — **Medium-High** — `getattr(r, "category", "General")` never yields the default

`:489`, `:517`, `:542`. `Result.category` is always *present* on the instance (`result.py:91` initialises it to `None`), so `getattr(r, "category", "General")` returns **`None`**, not `"General"`. The outer callback therefore receives `(“result”, None, None, r)` for any result whose category was not set — and `sherlock_service.py:188` unpacks `cat` and passes it to `_map_username_result(r, cat)` (`:190`), producing a `SiteResult` with a `None` category. The same applies to `site_name`. Use `r.category or "General"`.

### N-8 — **Medium** — The compat throws away upstream's `lru_cache` and re-imports every module on every call

`:61-83` vs `helpers.py:503-516`. `helpers.load_modules` is `@lru_cache(maxsize=None)`; `_load_modules_tolerant` has no cache, so every `load_user_modules()` / `load_email_modules()` / `load_phone_modules()` call re-executes 2,521 module files. Measured on this machine (warm `__pycache__`): **2.76 s** first call, **2.22 s** second call — i.e. ~2.5 s of pure import cost *per call, every time*, versus ~0 s for upstream's cached path.

The ~62 s figure from the swarm benchmark did **not** reproduce here (warm FS/`__pycache__`); the reproducible, actionable number is the **repeat** cost. It is paid at `sherlock_service.py:111/113` (on `force`/mode change), `email_service.py:174,197,218`, and — worst — in the cross-scan, where `sherlock_service.py:230` loads *all* email modules and `email_service.py:381` loads *all* user modules on top of the primary load (and N-3 adds the upstream cached loader on top of that).

### N-9 — **Medium** — `no_nsfw` is a dead parameter in `run_username_scan` and is forwarded to a function that ignores it

`:124` declares `no_nsfw: bool = False`; the body never reads it (the NSFW filter is applied at *load* time by `load_categories`, `helpers.py:531-532`). `:483` and `:511` then forward `no_nsfw=no_nsfw` into `run_username_scan`, where it lands in a dead parameter. The `no_nsfw` argument of `run_cross_scan_async` (`:396`) is therefore only meaningful for `scan_cfg` (`:430`) — and `scan_cfg` is used **only** by `_named_targets` (`:492`) for its `no_nsfw` lookup (`cross_scan.py:448`). Dead parameters invite the belief that a scan can be filtered at run time; it cannot.

### N-10 — **Medium** — `budget` is decremented after it has already been spent, and `_split_budget` is called with a stale `sweepable`

`:446-458`

```python
sweepable = len(rank_usernames(pivots))
for_usernames, for_emails = _split_budget(budget, sweepable, len(ranked))
usernames = _sweep_targets(pivots, for_usernames)
```

* `rank_usernames(pivots)` is computed twice per round — once here (`:446`) and again inside `_sweep_targets` (`cross_scan.py:334`).
* Upstream computes `sweepable = 0 if scope is not None and not scope else len(rank_usernames(pivots))` (`cross_scan.py:136`). The compat omits the scope guard; once N-1 is fixed and a scope exists, this line **must** be updated in lockstep or the budget split silently mis-allocates.
* `budget -= len(usernames) + len(to_scan)` (`:458`) can drive `budget` negative; `_split_budget` clamps at `<= 0` (`cross_scan.py:326-327`) so behaviour matches upstream, but the negative value is then re-tested by `_sweep_targets`/`_email_targets` to decide whether to print the “sweep off” notice — correct, but only by accident of upstream's clamping.

### N-11 — **Medium** — `_run_one_phone` loses the exception type and can produce an empty error reason

`:362-376`

* `:362-363` — `inspect.signature(func)` then `next(iter(sig.parameters.values()))` raises `StopIteration` for a zero-argument `validate_`; the `except Exception` at `:375` catches it and produces `PResult.error(str(exc))` → `PResult.error("")` — an error with an **empty reason** that renders as a blank line in the UI.
* `:376` — `PResult.error(str(exc))` discards the exception object, so `Result.get_reason()` (`phonsint/core/result.py`) cannot render the `"Type: message"` form that the username (`:208`) and email (`:287`) paths produce via `USResult.error(exc)`. The three drivers therefore report errors in three different formats.

### N-12 — **Medium** — `run_username_scan` returns `None` in every path, so the caller cannot distinguish “nothing matched” from “finished”

`:146-147`, `:165-166`, `:179` — no summary object is produced. `sherlock_service.py:167` fabricates a `SearchProgress` from `len(all_modules)` when the return is `None`. Combined with N-5 the caller has no way to learn how many modules were filtered, skipped or errored.

### N-13 — **Low-Medium** — Duplicate work per module and per round

* `get_site_name(mod)` is called three times per module: `:143` (filter), `:155` (loud check), `:192` (inside the worker).
* `rank_usernames(pivots)` twice per round (`:446` + `cross_scan.py:334`).
* `_run_one_user` re-imports `get_scan_func`/`get_site_name`/`USResult` on every invocation (`:184-185`) — a `sys.modules` dict lookup per module × 2,499 modules; same at `:263-264`, `:349-350`. Function-local imports save import time but pay a lookup per call.

### N-14 — **Low-Medium** — The cross-scan’s `initial_results` are the *raw* primary results, so confidence is computed over a differently-filtered population than upstream

`:426`, `:548`, `:551`. Upstream passes the *merged* `results` list (`cross_scan.py:179,182`) — i.e. the primary results **plus** every previous round’s cross results — to `_apply_confidence`. The compat passes `initial_results` (the primary results only) at both call sites, while `cross_results` (the accumulated rounds) is passed as the *second* argument. Upstream's `_apply_confidence(prior=results, cross_results=…, …)` (`cross_scan.py:179`) therefore uses a `prior` that already contains the earlier rounds' hits when computing `anchors` (`cross_scan.py:503-507`), whereas the compat's `prior` never does. The anchor set — and hence every `Confidence` rating — can differ from upstream.

### N-15 — **Low** — `allow_loud` semantics differ from upstream for the cross-scan's email side

`:451-456`. Upstream's `_email_scope` (`cross_scan.py:240-251`) returns `None` (= all modules, *including* loud ones) only when `configs.allow_loud` is true; otherwise it returns the loud-filtered list. The compat's `usable_email_modules` is always a concrete list, so the "all modules" case is unrepresentable — and, per N-2, the filtered list is never used anyway. `run_email_scan`'s own loud gate (`:236-238`) supplies the actual behaviour, so the result is correct by accident, but the two layers disagree in principle.

### N-16 — **Low** — Dead code inside the file

* `:91-93` `get_scan_func_user` — **no caller anywhere** (grep-verified across `src/`).
* `:106-108` `get_scan_func_phone` — **no caller anywhere**.
* `:194-195`, `:273-274`, `:359-360` — the `("error", …)` branches are unreachable with the current module set (measured 0 modules without `validate_`).
* `:124` `no_nsfw` — never read (N-9).
* `:33-58` `load_email_modules` / `load_phone_modules` are used, but `load_user_modules`’s `no_nsfw` default (`False`) is never exercised — every caller passes it explicitly.

### N-17 — **Low** — The module loader bypasses `sys.modules` registration

`:71-76`. `importlib.util.module_from_spec` + `exec_module` (without inserting into `sys.modules`) creates a *fresh* module object on every load, so module-level state (connection pools, `functools.lru_cache`s declared inside modules, `httpx.Client` globals) is discarded and rebuilt on each call. Upstream's `load_modules` has the same property, but upstream never re-runs it (lru_cache). Combined with N-8, every scan rebuilds all module state from scratch.

### N-18 — **Low** — `except Exception: pass` around the proxy setup hides misconfiguration (see B-1) and around the whole `set_proxy_manager` call the log has no context.

---

## 5) Improvements (ordered)

**P0 — correctness / user-visible stalls**

1. **Restore the cross-scan scope end-to-end** (N-1, B-4): add `scope` to `run_cross_scan_async`, compute it like `cross_scan.py:187-207`, pass it to `_named_targets` (`:492`), sweep the scoped module set (`:475`), and forward the caller's `selected` set. Populate `CrossScanConfig(modules=…, categories=…)` in `sherlock_service.py:224` / `email_service.py:375`.
2. **Install a 250-worker executor** (B-2): module-level `_shared_executor = ThreadPoolExecutor(max_workers=max(concurrency*2, 250))` (mirroring `orchestrator.py:28`) and use it at `:203`, `:282`; or `loop.set_default_executor(ThreadPoolExecutor(max_workers=250))` at the top of each driver (mirroring `email_orchestrator.py:200`).
3. **Fix the proxy reset** (B-1): always call `set_proxy_manager(...)`; `set_proxy_manager(None, None)` when there is no proxy; log failures instead of `pass`.
4. **Cancel properly** (B-3): keep the task list; on cancel, `task.cancel()` + `await asyncio.gather(*tasks, return_exceptions=True)`; always await the coroutine yielded by `as_completed` (or switch to `asyncio.wait(..., return_when=FIRST_COMPLETED)`); add a `finally` that closes the driver deterministically.
5. **Report every module to the caller** (N-5): emit `("skipped", …)` for loud, filtered and error modules so `checked_sites` can reach `total_sites`.
6. **Silence and surface upstream's prints** (B-5): `contextlib.redirect_stdout` around `_sweep_targets` (`:448`) and `_email_targets` (`:457`); route the text to `logger.info` or the UI.

**P1 — throughput & lifecycle**

7. **Cache the module list** (N-8): memoize `load_user_modules` / `load_email_modules` / `load_phone_modules` on `(no_nsfw)`, and reuse upstream's `helpers.load_modules` where the tolerant behaviour is not needed — or wrap upstream's `load_modules` in the per-file try/except instead of re-implementing it, keeping its `lru_cache`.
8. **Stop double-loading** (N-3): make the cross-scan use the *same* module objects the primary scan used (pass a `scope` built from the compat's own module list rather than from upstream's `find_module`).
9. **Honour `set_global_timeout` inside the adapter** (N-4): call `set_global_timeout(timeout)` in `run_username_scan` / `run_email_scan` / `run_phone_scan` so the HTTP timeout follows the UI setting regardless of the caller, and remove the duplicated calls at `sherlock_service.py:101` / `email_service.py:255` (B-10).
10. **Add a heartbeat**: emit a periodic `("progress", …)` / on_progress tick from the drivers so a long scan shows activity even between results (relevant to the phone driver, B-6).
11. **Bound the sweep cost**: even with a scope, cap the cross-scan's total module-executions and expose the cap to the user (upstream's `sweep` budget counts *targets*, not module-executions — `budget` at `:419` is a target count, while each target costs 2,499 module runs).

**P2 — API hygiene**

12. **Unify the result protocol** (B-6): one tuple shape for all three engines (e.g. a small dataclass `ScanEvent(kind, category, site_name, result, meta)`) so the callers stop special-casing arity.
13. **Split the file**: `user_scanner_compat.py` (user + email) vs `phonsint_compat.py` (phone). The current layout makes the “one adapter” claim false by construction.
14. **Stop using upstream private symbols** (`:400-414`): `cross_scan` exposes no public helper API, so either wrap them behind local functions with a single import site, or re-implement the (small) pivot/budget logic locally against the **public** `pivots` / `confidence` APIs (`rank_usernames`, `select_pivots`, `build_anchors`, `score`) and keep the upstream private imports to exactly one place.
15. **Delete the dead code** (N-16): `get_scan_func_user` (`:91-93`), `get_scan_func_phone` (`:106-108`), the unreachable `("error", …)` branches (or keep them but make the callers accept `"error"`), and the `no_nsfw` parameter (`:124`) — or actually implement run-time NSFW filtering.
16. **Make the tolerant loader observable** (B-8): log skips at WARNING with the category, and surface the skip count to the UI (e.g. “12 sites unavailable in this build”).
17. **Fix the small correctness nits** (N-7, N-10, N-11, N-13): `r.category or "General"`, drop the duplicate `rank_usernames`, preserve the exception object in the phone error path, and use `finditer`-safe signature inspection for zero-arg validators.

---

## 6) Verdict

**Do not ship as-is.** The file is internally consistent and, remarkably, **hallucinates nothing**: every symbol it touches exists in `user-scanner 1.5.2.3` / `phonsint 0.1.0` with a matching signature, `ScanConfig` is constructed with the right five fields, `Result.update` is called with legal field names, and the phonsint port at `:362-363` is a faithful copy of upstream `phonsint/core/orchestrator.py:52-53`. Its problem is not invented API — it is **that it re-implements the engine instead of adapting it**, and therefore silently drops the parts of upstream that carry the performance and scoping guarantees.

Severity summary:

* **Critical (1):** the cross-scan ignores every scope — `cross_config.modules`, `cross_config.categories` and the caller's site selection — and sweeps all 2,499 modules per pivot (N-1 / B-4).
* **High (4):** 8-thread default executor instead of upstream's 250 (B-2); orphaned tasks and un-awaited coroutines on cancel (B-3); stale global proxy leak (B-1); progress counters that can never reach `total_sites` (N-5).
* **Medium-High (2):** stdout pollution from upstream's cross-scan printers (B-5); the email-side scope is a no-op (N-2).
* **Medium (5):** dropped `("error", …)` tuples (B-7, currently unreachable); no run-time timeout plumbing (N-4); dead `no_nsfw` parameter (N-9); uncached module re-import (N-8); double module loading (N-3).
* **Low (6):** dead helpers, duplicate work, `getattr` default never firing, exception-type loss, `sys.modules` bypass.

The single most valuable change is to **stop re-implementing**: this file should call `user_scanner.core.orchestrator.run_user_full` / `run_user_module`, `user_scanner.core.email_orchestrator.run_email_full_batch` / `run_email_module_batch` and `user_scanner.core.cross_scan.run_cross_scan` (with their stdout redirected), and keep only the app-specific concerns — module loading, callback-based progress, cancellation and the proxy/timeout globals — in the adapter. That single change resolves B-2, B-4, B-5, B-8, N-1, N-2, N-3, N-8 and N-14 at once, and removes the coupling to twelve upstream **private** functions.

**Contract status:** the “only module that imports user-scanner internals” claim at `:3-5` is **false** — 17 direct import sites exist outside this file, including two owners of the same global engine state (`set_global_timeout`, `set_proxy_manager`).
