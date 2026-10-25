# anyio 4.15.1 — Dependency Audit (Sherlock-V3)

**Question:** should Sherlock-V3's scan-worker architecture use `anyio`?
**Answer:** No direct dependency. It is a healthy transitive of `httpx` and should stay that way.
AnyIO's structured-concurrency primitives *do* solve real bugs in this app — but the fix is
`asyncio.TaskGroup` + `asyncio.timeout` (stdlib, zero new deps), not an anyio port. `BlockingPortal`
should be **retired**, not ported from the V2 blueprint.

---

## 1. Installed verification (venv = source of truth)

Location: `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/anyio`
Version: `anyio-4.15.1.dist-info\METADATA:3` → `Version: 4.15.1`.
Note: `anyio.__version__` **does not exist** in 4.15.1 (no `__version__` in `anyio\__init__.py` either) — version lives only in dist-info.
`anyio\__init__.py:5` `from ._lazyimport import (` installs a lazy importer; 104 `X as X` re-export lines follow (V2 doc's `__init__.py:11-155` shape still accurate).

**Real import test** (`.venv\Scripts\python.exe`, executed against installed source):

| Symbol | Importable? | Defined at |
|---|---|---|
| `anyio.create_task_group` | YES (function) | `anyio\_core\_tasks.py:238` (re-export `__init__.py:101`) |
| `anyio.CancelScope` | YES (type) | `anyio\_core\_tasks.py:43` (`__init__.py:99`) |
| `anyio.fail_after` | YES (function) | `anyio\_core\_tasks.py:159` |
| `anyio.move_on_after` | YES (function) | `anyio\_core\_tasks.py:201` |
| `anyio.CapacityLimiter` | YES (type) | `anyio\_core\_synchronization.py:534` (`__init__.py:85`) |
| `anyio.Semaphore` | YES (type) | `anyio\_core\_synchronization.py:388` |
| `anyio.create_memory_object_stream` | YES (type — **class**, not function, in 4.15) | `anyio\_core\_streams.py:16` |
| `anyio.to_thread.run_sync` | YES | `anyio\to_thread.py:27` |
| `anyio.to_thread.current_default_thread_limiter` | YES | `anyio\to_thread.py:70` |
| `anyio.from_thread.BlockingPortal` | YES — **not** top-level | `anyio\from_thread.py:187` |
| `anyio.from_thread.start_blocking_portal` | YES — same, submodule import | `anyio\from_thread.py:506` |
| `anyio.run` / `sleep` / `Event` / `Lock` | YES | — |

`getattr(anyio, "BlockingPortal")` and `getattr(anyio, "start_blocking_portal")` **FAIL** — the V2 doc's "anyio exports BlockingPortal" is misleading; they live in `anyio.from_thread` (`__all__` = `BlockingPortal, BlockingPortalProvider, check_cancelled, run, run_sync, start_blocking_portal`).

**Functional smoke test — all PASSED in-venv:** `create_task_group` + `CapacityLimiter(4)` ran 20 tasks; `tg.cancel_scope.cancel()` aborted an in-flight `sleep(30)` in 0.06 s; `to_thread.run_sync` → `42`; `fail_after(0.1)` raised `TimeoutError`; `create_memory_object_stream` send/receive worked; `anyio.run(main)` worked (asyncio backend, no trio installed); `start_blocking_portal()` + `portal.call(...)` worked. **Every primitive is functional.**

**Transitive status — `uv.lock`:**
- `uv.lock:6-7` → `anyio 4.15.1` (pinned). `uv.lock:203` `{ name = "anyio" }` appears **exactly once**, under `httpx`.
- `httpcore 1.0.9` (`uv.lock:186-192`) deps = `certifi`, `h11` only → **httpcore no longer pulls anyio** (V2 doc's "via httpx and httpcore" is half-stale; httpx only now).
- `flet 1.0.4` (`uv.lock:128-136`) deps = `httpx`, `msgpack`, `oauthlib`, `repath` → no direct anyio.
- `src/`, `tests/`, `pyproject.toml` → **zero** `anyio` references. **App does NOT import anyio directly.** Confirmed.

**Flet 1.0.4 does not use anyio:** `grep -rn "anyio" .venv/Lib/site-packages/flet/ --include=*.py` → **0 hits**. Flet is pure **asyncio**:
`flet\controls\page.py:929` `run_task` → `asyncio.run_coroutine_threadsafe(handler, self.session.connection.loop)`;
`flet\controls\page.py:991` `run_thread` → `loop.run_in_executor(self.executor, ...)`;
`flet\app.py:133` `asyncio.run(...)`; `flet\app.py:240,520` `asyncio.get_running_loop()`.
⇒ Flet owns the page's asyncio loop; anyio is *compatible* with it but gains nothing, and a `BlockingPortal` would add a **second** loop — the exact nesting the app already suffers from.

---

## 2. App's current asyncio/thread architecture (file:line facts)

**Shape:** Flet asyncio main loop → `await service.search(...)` → `asyncio.to_thread(...)` → worker thread spins up **its own** `asyncio.new_event_loop()` → `run_until_complete(...)` → N module tasks.

**`src/services/sherlock_service.py`**
- `:92` `self._thread_cancel = threading.Event()` — the only cancel channel.
- `:150` `self._thread_cancel.clear()` — reset at the start of every scan.
- `:154-156` `await asyncio.to_thread(self._run_worker, ...)` — flet-loop → worker-thread hop.
- `:157-159` `except asyncio.CancelledError: self._thread_cancel.set()` — cancelling the awaiter does **not** stop the thread.
- `:260-263` `_run_worker`: `new_event_loop()` → `set_event_loop(loop)` → `run_until_complete(self._run(...))` — thread-local loop nested inside `to_thread`.
- `:271` `loop.close()` in `finally` — closed while tasks may still be pending.
- `:292-293` `cancel()` → `self._thread_cancel.set()`. **Nothing else** — no task cancellation, no loop ref, no reach into in-flight module calls.

**`src/services/user_scanner_compat.py`**
- `:150` `sem = asyncio.Semaphore(max(1, min(200, concurrency)))`; `:160-163` `asyncio.create_task(_run_one_user(...))` per module.
- `:168-170` `for coro in asyncio.as_completed(tasks): if cancel_event.is_set(): break` — on cancel the loop **breaks out and leaves every created task pending** (never cancelled).
- `:199` `await asyncio.wait_for(func(username), timeout=module_timeout)`; `:201-203` `loop.run_in_executor(None, func, username)` — default executor (`min(32, cpu+4)` workers) inside `wait_for`.
- `:244-248` identical pattern for email (semaphore capped at 30); `:278-281` same executor use.

**`src/services/email_service.py`**
- `:165-168` `_thread_cancel`, `_worker_loop`, `_tasks: list[Any] = []`.
- `:234` `self._tasks.clear()` — **`_tasks` is never populated anywhere** (only `.clear()` at `:234`, `:411`).
- `:317-319` `worker_loop = asyncio.new_event_loop()`; `asyncio.set_event_loop(worker_loop)`; `self._worker_loop = worker_loop` — created **on the flet main thread** and **never run**.
- `:321-323` `await asyncio.to_thread(self._run_worker, ...)`; the real work runs in `_run_worker`'s **own** second loop (`:346-347`) ⇒ `self._worker_loop` points at a dead loop.
- `:337-340` `asyncio.set_event_loop(None)`; `worker_loop.close()` — clobbers the **Flet main thread's** current-loop pointer to `None` instead of restoring it.
- `:429-445` `cancel()`: `if loop is not None and loop.is_running():` → **always False** ⇒ `:435-441` `call_soon_threadsafe(_cancel_all)` is **dead code**, and would be a no-op anyway (`_tasks` empty).

**`src/services/phone_service.py`** — same pattern: `:197` `to_thread`, `:214` `new_event_loop`, `:218` `run_until_complete`, `:232` `gather`.

**`src/main.py`** — `:1003` `await self.sherlock_service.search(...)`, `:1530` `await self.email_service.search(...)` (on the Flet loop); `:202-206` `_kill_all_activity` calls `sherlock_service.cancel()` / `email_service.cancel()` ⇒ the kill path reduces to "set a threading.Event"; `:1421-1435` `_cancel_task_threadsafe` cancels the awaiter, which per above does not reach the worker thread. `:125-127` documents that `page.run_task` cannot be used off the main loop (confirmed by `flet/controls/page.py:929`) — Flet offers no structured-concurrency helper.

### Concrete weaknesses (evidence-backed)
- **W1 — Cancel never reaches in-flight module calls.** `sherlock_service.py:292-293` only sets an event; `user_scanner_compat.py:199/201-203` are already awaiting and have no cancellation hook. The event is polled only at task creation (`:153`) and task entry (`:187`/`:190`). A cancelled scan keeps every check running until `module_timeout` (= `timeout + 10`).
- **W2 — Orphaned tasks + `loop.close()` on a live loop.** `user_scanner_compat.py:168-170` breaks out of `as_completed` without cancelling its tasks; `_run` returns; `sherlock_service.py:271` `loop.close()` runs with N pending tasks ⇒ "Task was destroyed but it is pending!" + abandoned executor threads.
- **W3 — `threading.Event.clear()` cross-generation race.** `sherlock_service.py:150` clears the event at the start of a new scan; the previous worker thread is still alive (W1/W2), so `clear()` **un-cancels the old scan**. Two generations then share one Event and one `state.search_targets` list ⇒ the old scan's ticks can land in the new scan's results.
- **W4 — Nested thread+loop, cancelled only at the outer layer.** `await asyncio.to_thread(...)` (`sherlock_service.py:154`) cannot be interrupted: cancelling the awaiter raises `CancelledError` in the caller while the thread runs to completion.
- **W5 — Dead cancel path in EmailService.** `email_service.py:434` `loop.is_running()` always False ⇒ `:435-441` never executes; `_tasks` (`:168`) never populated ⇒ even if it did, it would cancel nothing.
- **W6 — Default executor + thread leak.** `user_scanner_compat.py:202` `run_in_executor(None, ...)` shares the loop's default 32-thread pool; `wait_for` cancelling the future does **not** stop the thread ⇒ timed-out module calls leak a thread and its socket.
- **W7 — Main-thread event-loop pointer clobbered.** `email_service.py:318` `set_event_loop(worker_loop)` and `:337` `set_event_loop(None)` replace Flet's main-thread current-loop with a never-running loop, then `None`.
- **W8 — No Flet-native alternative.** `page.run_task` is `run_coroutine_threadsafe` onto `session.connection.loop` (`flet/controls/page.py:929`) — it cannot host the scan and offers no cancel scope.

---

## 3. AnyIO opportunities mapped to weaknesses (priority-ordered)

| # | Weakness | AnyIO primitive | Would it fix it? | Priority |
|---|---|---|---|---|
| P1 | W1, W2, W3 (cancel not delivered, orphan tasks) | `create_task_group()` + `CancelScope` (`_core\_tasks.py:238,43`) | **YES.** A task group owns its children: `tg.cancel_scope.cancel()` cancels *in-flight* awaits; leaving the `async with` awaits every child. Turns "poll a `threading.Event`" into real structured cancellation. | **HIGH** |
| P2 | W1 (per-module timeout) | `fail_after` / `move_on_after` (`_core\_tasks.py:159,201`) | **YES**, and cheaper than `asyncio.wait_for`; the scope also unwinds the `async with sem`. | HIGH |
| P3 | W6 (default executor, thread leak) | `to_thread.run_sync` (`to_thread.py:27`) + `CapacityLimiter` (`_core\_synchronization.py:534`) | **PARTLY.** anyio's `to_thread` uses a dedicated sized limiter (default 40) — but a cancelled `to_thread` call abandons the thread exactly like `run_in_executor`; anyio cannot kill a thread either. Gain = bounded, named pool instead of the shared default executor. | MEDIUM |
| P4 | W3 (cross-generation race) | per-generation task group + `CapacityLimiter` | **YES** — each scan owns its own group/cancel scope; a new scan cancels the old scope instead of flipping a shared flag. No shared Event to `clear()`. | MEDIUM |
| P5 | W2 (progress fan-in) | `create_memory_object_stream` (`_core\_streams.py:16`) | **NO real gain** — `asyncio.as_completed` already does this; a memory stream is just a slower `asyncio.Queue`. | LOW |
| P6 | W4/W5/W7 (nested loops, dead cancel path) | `start_blocking_portal` / `BlockingPortal` (`from_thread.py:187,506`) | **NO — actively harmful.** Flet already owns the asyncio loop; a BlockingPortal adds a *second* loop + thread-of-control, re-creating W4 instead of fixing it. | **REJECT** |

**Change sketch (anyio flavour, if the team insists):**
- `sherlock_service.py:154-156` → `await anyio.to_thread.run_sync(self._run_worker_sync, ...)` **only after** `_run_worker` is reduced to a plain sync function; better, delete the thread hop and run the scan coroutine on Flet's loop.
- `user_scanner_compat.py:160-170` (and `:244-253`) → `async with anyio.create_task_group() as tg:` + `tg.start_soon(_run_one_user, mod, username, cat, limiter, timeout)`; results via `create_memory_object_stream` or a per-task callback.
- `user_scanner_compat.py:199-203` → `with anyio.fail_after(module_timeout):` around `await anyio.to_thread.run_sync(func, username)` under a shared `anyio.CapacityLimiter(concurrency)`.
- `sherlock_service.py:292-293` `cancel()` → `self._cancel_scope.cancel()` (a `CancelScope` captured when the scan's group started). **Biggest behavioural upgrade: cancel becomes immediate for in-flight awaits.**
- `email_service.py:317-319,337-340` → delete the phantom `worker_loop` + the `set_event_loop` calls; `:434` then has no phantom to test.

**But every one of these is achievable with zero new dependencies.** The venv is Python 3.14 (`cp314` in site-packages) ⇒ `asyncio.TaskGroup` (3.11+), `asyncio.timeout()`, `asyncio.to_thread` all exist. `asyncio.TaskGroup` gives the same child-cancellation/structured-exit semantics as anyio's group; `asyncio.timeout()` replaces `fail_after`. anyio would add a dependency, a second abstraction over the loop Flet already owns, and no capability the app lacks.

---

## 4. Recommended minimal change

**Do not add `anyio` to `pyproject.toml`. Do not introduce `BlockingPortal`.** Dependency-free change set (stdlib `asyncio` only):

1. **Delete the second event loop.** `sherlock_service.py:260-271`, `email_service.py:317-319/337-340/346-347`, `phone_service.py:214-232` → run the scan coroutine **on Flet's existing loop** instead of `to_thread` → `new_event_loop` → `run_until_complete`. The scan is I/O-bound; it needs no private loop. Removes W4, W7, and the whole thread hop.
2. **Use `asyncio.TaskGroup`.** Replace the `create_task` list + `as_completed` in `user_scanner_compat.py:160-170` and `:244-253` with `async with asyncio.TaskGroup() as tg:` + `tg.create_task(...)`. Exiting the group cancels and awaits every child ⇒ fixes W1, W2.
3. **Per-scan cancellation.** Replace the shared `threading.Event` (`sherlock_service.py:92`, `email_service.py:165`) with a stored `asyncio.Task` that `cancel()` cancels directly (or a per-scan `asyncio.Event`) ⇒ fixes W3, W5, makes cancel immediate.
4. **Own the thread pool.** Replace `loop.run_in_executor(None, ...)` (`user_scanner_compat.py:202,281`) with a dedicated `ThreadPoolExecutor(max_workers=concurrency)` owned by the service, or `asyncio.to_thread` under a `threading.Semaphore` ⇒ mitigates W6.
5. **`asyncio.timeout(module_timeout)`** (`user_scanner_compat.py:199,278`) instead of `asyncio.wait_for` — same semantics, cheaper, composes with TaskGroup cancellation.

If the team later wants trio portability or anyio's `TaskHandle` API, anyio is already installed transitively via httpx and can be added with no install risk — but write the code against stdlib `asyncio` so the choice stays reversible.

**V2 doc correction:** `docs/reference/dep-anyio.md` claims anyio arrives "via httpx and httpcore"; per `uv.lock:186-192` httpcore 1.0.9 no longer depends on anyio (httpx only). It also implies `BlockingPortal` is a top-level anyio export; it is `anyio.from_thread.BlockingPortal` (`anyio\from_thread.py:187`). The V2 BlockingPortal blueprint should be **retired, not ported**.

---

## 5. Verdict

# ISSUES FOUND

- **The dependency itself is fine.** `anyio 4.15.1` is correctly installed, fully functional, and reachable — every audited primitive imports *and* runs. It is a legitimate transitive of `httpx` (`uv.lock:203`); httpcore no longer depends on it (V2 doc half-stale). Flet 1.0.4 does **not** use anyio (0 grep hits) — it is pure asyncio, so there is no "flet already runs anyio" argument.
- **The issues are in the app's architecture; anyio is only one possible remedy.** Eight weaknesses (W1-W8) confirmed with file:line evidence — worst are: cancel never reaches in-flight module calls (`sherlock_service.py:292-293`); orphaned tasks closed with a live loop (`user_scanner_compat.py:168-170` → `sherlock_service.py:271`); the `clear()` cross-generation race (`sherlock_service.py:150`); a fully dead email cancel path (`email_service.py:434` + never-populated `_tasks` at `:168`).
- **Recommendation: no direct `anyio` dependency, no `BlockingPortal`.** Fix W1-W8 with stdlib `asyncio.TaskGroup` + `asyncio.timeout` + one shared loop — every benefit anyio would give here, at zero dependency cost and without a second event loop next to Flet's. Copy anyio's *design* (task group, cancel scope, fail_after), not the package.
