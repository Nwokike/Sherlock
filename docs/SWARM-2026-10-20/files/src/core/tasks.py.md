# Audit — `src/core/tasks.py`

**File:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/core/tasks.py` (32 lines)
**Scope:** this file only. All API claims verified against installed `flet 1.0.4` (`.venv\Lib\site-packages\flet`) and CPython 3.14.7.
**Mode:** read-only — nothing was modified.

---

## 1) File role

`src/core/tasks.py` is the repo's single background-task spawn helper. It is the "fire-and-forget" primitive used by **12 consumer modules across 96 call sites**:

| Module | `spawn()` call sites |
|---|---|
| `src/screens/settings_screen.py` | 44 (385, 397, 398, 400, 407, 409, 413, 415, 425, 427, 451, 473, 483, 488, 493, 497, 507, 518, 523, 561, 565, 569, 573, 577, 586, 590, 594, 598, 602, 606, 610, 614, 618, 622, 626, 630, 634, 641, 683, 1483, 1687, 1746) |
| `src/screens/home_screen.py` | 10 (423, 441, 505, 659, 674, 747, 773, 793, 894, 908) |
| `src/main.py` | 8 (312, 337, 403, 970, 1245, 1268, 1633, 2114) |
| `src/app_shell.py` | 8 (149, 194, 200, 235, 471, 604, 621, 624) |
| `src/components/profile_detail_dialog.py` | 7 (117, 126, 449, 462, 581, 1069, 1084) |
| `src/screens/results_screen.py` | 6 (360, 368, 370, 372, 383, 413) |
| `src/screens/history_screen.py` | 4 (125, 155, 219, 410) |
| `src/screens/onboarding_screen.py` | 3 (139, 144, 150) |
| `src/screens/sites_screen.py` | 3 (272, 656, 742) |
| `src/hooks/use_debounce.py` | 1 (32) |
| `src/components/app_header.py` | 1 (151) |
| `src/services/http_client.py` | 1 (97) |

Its job (per its own docstring, `tasks.py:1-6`) is to replace bare `asyncio.create_task()` with something that (a) does not silently swallow exceptions and (b) satisfies RUF006. It is *not* a wrapper around flet's task API — it builds its own asyncio-level mechanism (see §2).

The repo does **not** have a single consistent pattern. `src/main.py:1190-1277` keeps its own `pending_tasks: set[asyncio.Task]`, `src/services/user_scanner_compat.py:163,245,330` still uses bare `asyncio.create_task`, and `src/services/email_service.py:405-436` / `src/services/phone_service.py:227-247` maintain private `_tasks` lists — four coexisting task-management schemes, of which this file is one.

---

## 2) Mechanism verification

Core function, verbatim (`src/core/tasks.py:18-31`):

```python
def spawn(coro: Coroutine[Any, Any, Any], name: str = "bg-task") -> asyncio.Task:
    """Create a tracked background task; log failures instead of dropping them."""
    task = asyncio.create_task(coro, name=name)

    def _done(t: asyncio.Task) -> None:
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.warning("Background task %r failed: %s", name, exc)

    task.add_done_callback(_done)
    return task
```

**What it actually does**

1. `tasks.py:20` — `asyncio.create_task(coro, name=name)`. This is a **loop-local, thread-local** operation: it requires a *running event loop in the current thread* and binds the coroutine to that loop. Python's own docs for `asyncio.create_task` warn: *"Save a reference to the result of this function, to avoid a task disappearing mid-execution."*
2. `tasks.py:22-28` — a done-callback calls `t.exception()`, which **retrieves** the exception, so asyncio's "Task exception was never retrieved" warning never fires. This part of the design works as advertised.
3. `tasks.py:30` — `task.add_done_callback(_done)`; the callback holds a reference to the closure, and the closure holds `name`.
4. `tasks.py:31` — the `Task` is **returned**, not retained. There is no module-level registry, no set, no cancel hook.

**It does NOT wrap flet's mechanism.** flet 1.0.4 `controls/page.py:929-962`:

```python
def run_task(self, handler, *args, **kwargs) -> Future[RetT]:
    _context_page.set(self)
    if not inspect.iscoroutinefunction(handler):
        raise TypeError("handler must be a coroutine function")
    future = asyncio.run_coroutine_threadsafe(
        handler(*args, **kwargs), self.session.connection.loop
    )
    def _on_completion(f):
        try:
            exception = f.exception()
            if exception:
                raise exception
        except CancelledError:
            pass
    future.add_done_callback(_on_completion)
    return future
```

Differences that matter:

| aspect | flet `page.run_task` | this file's `spawn()` |
|---|---|---|
| thread safety | `run_coroutine_threadsafe` onto `session.connection.loop` → **safe from any thread** | `asyncio.create_task` → **raises `RuntimeError: no running event loop` off-loop** |
| failure surfacing | re-raises inside the callback → asyncio's exception handler logs it **with traceback** | `logger.warning(..., exc)` → **no traceback** |
| handle type | `concurrent.futures.Future` | `asyncio.Task` (cancellable via `.cancel()`) |
| page context | explicitly sets `_context_page` contextvar | inherits the dispatch context via `create_task`'s context copy (works) |

**Thread/loop reality in this stack (verified, not assumed):**
- The app runs under a single loop: `flet/app.py:133` `asyncio.run(run_async(...))`; `flet/app.py:416` `loop=asyncio.get_running_loop()`.
- Event handlers are invoked **inline on that loop thread**: `flet/controls/base_control.py:546-551` — the sync-handler branch literally calls `event_handler(e)`; there is no executor hop.
- The `ThreadPoolExecutor` created at `flet/app.py:413` is used only for pubsub (`flet/pubsub/pubsub_hub.py:279`) and `page.run_thread` (`flet/controls/page.py:998-1008`) — **not** for `on_click` handlers.

⇒ **Today, all 96 call sites are on-loop and `spawn()` is correct.** Consequently `spawn()` introduces **no** worker-thread UI-update hazard. But it is fragile: it has zero tolerance for being reached from a thread, and the repo is full of `asyncio.to_thread` call sites (see B1).

---

## 3) Call census

- **96** `spawn()` call sites in **12** modules (`src/core/tasks.py` excluded).
- **`name=` passed at only 3 sites**: `src/hooks/use_debounce.py:32` (`"debounce"`), `src/screens/history_screen.py:125,155,219,410` (`"history-*"`), `src/screens/sites_screen.py:272` (`"sites-persist"`), `src/services/http_client.py:97` (`"httpx-aclose"`). All other ~90 sites use the default `"bg-task"`.
- **The returned Task is stored at only 5 sites**:
  - `src/main.py:403` `self._render_flush_task = spawn(self._render_flusher())`
  - `src/main.py:970` `self._enrich_worker_task = spawn(self._drain_enrich_queue())`
  - `src/main.py:1268` `t = spawn(_enrich_single(url))` (local, appended to a local `pending_tasks` set)
  - `src/hooks/use_debounce.py:32` `timer.current = spawn(...)` (cancelled on the next keystroke)
  - `src/screens/sites_screen.py:272` `_persist_task.current = spawn(...)`
- **91 sites discard the handle** → the task is uncancellable and unobservable for the rest of its life.
- **Call-site shapes**: nearly all are `spawn(<async fn>())` inside a *synchronous* flet handler (`on_click=lambda e: spawn(...)`) — e.g. `src/screens/settings_screen.py:385,1483,1687,1746`, `src/screens/home_screen.py:894,908`. The handler returns immediately, so the coroutine runs after the handler's auto-update cycle has already closed (B5).

---

## 4) Bugs (severity-ordered)

### B1 — HIGH · `spawn()` is hard-bound to the calling thread's loop; off-loop calls raise synchronously and leak the coroutine
`src/core/tasks.py:20`

`asyncio.create_task` requires a running loop **in the current thread**. flet's own equivalent deliberately does not (`flet/controls/page.py:943-945`, `asyncio.run_coroutine_threadsafe(..., self.session.connection.loop)`), precisely so it can be called from any thread.

If a `spawn()` call is ever reached from a worker thread — `asyncio.to_thread` (used at `src/main.py:1119,1575`, `src/app_shell.py:441`, `src/screens/home_screen.py:556,587`, `src/screens/settings_screen.py:668`, `src/services/email_service.py:321`, `src/services/storage_service.py:335`, `src/services/phone_service.py:197`, `src/services/sherlock_service.py:154`, `src/services/user_scanner_compat.py:368`), `page.run_thread`, a `threading.Thread`, or a callback fired by a sync HTTP library — then:
- `asyncio.create_task` raises `RuntimeError: no running event loop` **synchronously inside the caller** (i.e. inside the flet handler), and
- the coroutine object is never awaited → `RuntimeWarning: coroutine '_foo' was never awaited` and a silently dropped job.

The team already knows this hazard: `src/services/http_client.py:88-97` explicitly probes `asyncio.get_running_loop()` **before** calling `spawn()`, with the comment "Shared httpx client swapped with no running loop — relying on GC". `spawn()` itself provides no such guard, so any other call site that crosses a thread boundary will crash rather than degrade.

### B2 — MEDIUM-HIGH · "Tracked" is a fiction: no registry, no strong reference, no cancellation path
`src/core/tasks.py:1-6`, `:18-31`

The module docstring claims *"Tracked background tasks"* and the function docstring claims *"Create a tracked background task"*, but nothing is tracked: there is no module-level set, no `cancel_all()`, no shutdown hook, and `spawn()` keeps no reference of its own. It merely *returns* the task and depends on the caller to store it — which 91 of 96 sites do not do. Consequences:

- **No cancellation at shutdown.** Nothing cancels the ~91 untracked tasks when the page closes; a task that outlives its session keeps the loop alive and can still touch a dead session/controls.
- **Documented GC hazard.** `asyncio.create_task`'s contract is "save a reference … to avoid a task disappearing mid-execution". The helper launders that obligation onto callers and the callers ignore it.
- The 5 sites that *do* keep the handle are exactly the singleton/long-lived cases that genuinely need it (render flusher, enrich worker, debounce timer, sites persist, per-item enrich) — but there is no `spawn(..., replace=old)` primitive, so each site re-implements the "cancel the old one" dance by hand (`src/hooks/use_debounce.py:26-30`, `src/screens/sites_screen.py:270-272`).

### B3 — MEDIUM · The traceback — the only actionable part of a background failure — is discarded
`src/core/tasks.py:28`

```python
logger.warning("Background task %r failed: %s", name, exc)
```

`%s` stringifies the exception object: for `Exception("boom")` the log line is `boom` with **no stack, no cause, no frames**. flet's `run_task` does better by re-raising inside its done-callback (`flet/controls/page.py:950-962`) so the traceback reaches asyncio's exception handler. For a fire-and-forget job the traceback *is* the diagnosis; this helper throws it away.

### B4 — MEDIUM · ~90 failures are logged under the same opaque name `"bg-task"`
`src/core/tasks.py:18`

Only 3 of 96 call sites pass `name=`; the rest inherit `"bg-task"`. A production log therefore reads `Background task 'bg-task' failed: <exc>` — you cannot tell *which* of the 96 jobs failed. The same opaque string is passed to `asyncio.create_task(..., name=name)` (`tasks.py:20`), so even an `asyncio.all_tasks()` dump or a debugger task list shows 90 identically-named tasks.

### B5 — MEDIUM · Spawned tasks run outside flet's auto-update lifecycle; UI mutations inside them are silently not pushed
`src/core/tasks.py:20` (interaction with `flet/messaging/session.py:565-587`)

flet performs auto-update in `Session.after_event` → `__auto_update` (`flet/messaging/session.py:565-587`), which runs **only at the end of an event dispatch** (`flet/controls/base_control.py:556`). A task started by `spawn()` begins after the handler returned, i.e. outside that lifecycle. Any *direct* control mutation inside such a task (`ctrl.text = ...`) therefore requires an explicit `page.update()` / `ctrl.update()` to reach the client; there is no "task ended → re-flush" hook.

The repo compensates ad hoc — `page.update()` at `src/main.py:614,1450,1724,1860,2308`, `src/app_shell.py:774,783,826,832`, `src/components/app_header.py:153`, `src/screens/settings_screen.py:331,436` — but nothing in `tasks.py` expresses or enforces the contract. Concrete symptom risk: `src/screens/history_screen.py:106-124` mutates the shared `state.history` list from inside a spawned task and never calls `page.update()`; the new entries reach the screen only when some later event happens to trigger a re-render.

### B6 — MEDIUM · Inner `except Exception: pass` defeats the module's core promise
`src/core/tasks.py:1-5` vs `src/screens/history_screen.py:121-122`

The harvesting in `tasks.py:22-28` can only report exceptions that reach it. `src/screens/history_screen.py:121-122` swallows everything with `except Exception: pass`, so the "without losing exceptions" guarantee is really only "exceptions that nobody else caught". The docstring overstates the contract.

### B7 — LOW-MEDIUM · Cancellation is indistinguishable from success
`src/core/tasks.py:25-26`

`except asyncio.CancelledError: return` silently drops the cancellation. Cancellation is a *normal, expected* outcome here — `src/hooks/use_debounce.py:26-30` cancels the previous debounce task on every keystroke — yet it is invisible in the log, so "cancelled on purpose" cannot be told apart from "cancelled by loop shutdown" or "cancelled by an error path".

### B8 — LOW · No guard for "no running loop" → the coroutine object leaks
`src/core/tasks.py:18-20`

If `spawn()` is called with no running loop (or after the loop closed), `asyncio.create_task` raises and the coroutine is left un-awaited → `RuntimeWarning: coroutine ... was never awaited` at GC time. A `try/except RuntimeError` that calls `coro.close()` and logs would both surface the failure and silence the warning.

### B9 — LOW · Narrow type annotation, no runtime validation
`src/core/tasks.py:18`

`Coroutine[Any, Any, Any]` is accurate for `asyncio.create_task` (which rejects `Task`/`Future` inputs with `TypeError`), but there is no `Awaitable` support and no runtime check — passing a Future produces a confusing `TypeError` from inside asyncio rather than a clear message from `spawn()`.

### B10 — LOW · The RUF006 claim is half-true: the lint signal was silenced, not the hazard fixed
`src/core/tasks.py:3-4`

RUF006 ("store a reference to the return value of `asyncio.create_task`") fires on the *call site* of `asyncio.create_task`. By hiding the call behind a wrapper, `spawn()` stops ruff from flagging the 96 call sites — but the underlying hazard (dropping the reference) still exists at 91 of them (B2). Meanwhile the repo still contains bare `asyncio.create_task` outside this helper (`src/services/user_scanner_compat.py:163,245,330`), so adoption is partial and the "every bare create_task" premise is not true of the codebase.

### Dead-code / drift summary
No unreachable statements, but three pieces of **drift**: the module name and both docstrings promise *tracking* that does not exist (B2); the RUF006 rationale no longer describes the repo (B10); and `name` is used only for the task label and the log line — with no registry keyed by it, the parameter cannot be used for lookup or cancellation, which is the one thing a "tracked" API would want it for.

---

## 5) Improvements (concrete)

**I1 — Bind a loop and make off-loop calls safe (fixes B1).** Give the module an explicit loop binding and dispatch cross-thread calls the way flet does:

```python
_LOOP: asyncio.AbstractEventLoop | None = None

def bind_loop(loop: asyncio.AbstractEventLoop | None = None) -> None:
    """Bind the loop that owns spawned tasks (call once at app start)."""
    global _LOOP
    _LOOP = loop or asyncio.get_running_loop()

def spawn(coro, name="bg-task") -> asyncio.Task:
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        coro.close()
        logger.warning("spawn(%r): no running loop; task dropped", name)
        return None  # or raise a typed error
    if _LOOP is not None and running is not _LOOP:
        # off-loop caller: hand the coroutine to the owning loop
        return asyncio.run_coroutine_threadsafe(coro, _LOOP)  # note: returns a Future
    ...
```
At minimum, mirror `src/services/http_client.py:88-96`'s existing probe inside `spawn()` so the guard lives in one place.

**I2 — Make the tracking real (fixes B2).** Module-level registry + shutdown hook:

```python
_TASKS: set[asyncio.Task] = set()

def spawn(coro, name="bg-task"):
    ...
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)   # never leaks the set
    ...

def cancel_all() -> None:
    for t in list(_TASKS):
        t.cancel()
```
Wire `cancel_all()` into `page.on_close` (alongside the existing `close_client()` hook in `src/services/http_client.py`) so no task outlives its session. Keeping the reference inside the module also structurally removes the CPython GC hazard regardless of what callers do.

**I3 — Log the traceback (fixes B3).** One-line change with the largest diagnostic payoff:

```python
logger.warning("Background task %r failed", name, exc_info=exc)
```
(`exc_info=exc` — the exception object — is accepted by `logging` and renders the full traceback.)

**I4 — Derive a meaningful default name (fixes B4).** The coroutine already carries a useful name:

```python
name = name or getattr(coro, "__qualname__", "bg-task")
```
`__qualname__` turns 90 anonymous `"bg-task"` log lines into `Background task 'Screens.settings_screen._persist' failed: …` at zero call-site cost. Also pass it through to `asyncio.create_task(..., name=name)` (already done at `tasks.py:20`).

**I5 — Add a `spawn_replace(old)` / `cancel(old)` helper (fixes B2's singleton cases).** The hand-rolled "cancel the previous, then spawn" pattern appears at `src/hooks/use_debounce.py:26-32` and `src/screens/sites_screen.py:270-272`; a helper would make it the default and prevent double-running workers (e.g. two render flushers, `src/main.py:403`).

**I6 — Support cancellation observability (fixes B7).** `logger.debug("Background task %r cancelled", name)` in the `CancelledError` branch, so deliberate cancels are distinguishable from failures.

**I7 — Document/enforce the UI-update contract (fixes B5).** Either (a) have `spawn()` accept `updates_ui: bool` and, on completion, call `page.update()` when the task mutated controls, or (b) state the rule in the docstring: *"tasks run outside flet's auto-update cycle — call `page.update()` explicitly after mutating controls"*. Option (b) is a two-line change; option (a) removes a whole class of silent-staleness bugs.

**I8 — Offer an error hook so callers can react (fixes B6's contract gap).** `spawn(coro, name=..., on_error=callable)` — e.g. `src/screens/settings_screen.py` could surface a failed preference persist instead of only writing a log line.

**I9 — Add unit tests** (the repo has a `tests/` directory): (i) a failing coroutine produces a log record containing the traceback; (ii) a cancelled coroutine produces no warning-level record; (iii) `spawn()` called with no running loop does not raise `RuntimeError` and does not emit "never awaited"; (iv) `cancel_all()` cancels everything registered.

**I10 — Make adoption complete.** Route the remaining bare `asyncio.create_task` sites (`src/services/user_scanner_compat.py:163,245,330`) and the hand-rolled `pending_tasks` set (`src/main.py:1190-1277`) through this module, or explicitly document why they are exempt (they *do* await their tasks, so `spawn()` is the wrong tool there — but the two should then be unified deliberately, not accidentally).

---

## 6) Verdict

**No hallucinated APIs.** Every call in the file exists in the installed stack: `asyncio.create_task(coro, name=...)`, `Task.exception()`, `Task.add_done_callback()`, `asyncio.CancelledError` (CPython 3.14.7; `CancelledError` is a `BaseException`, correctly caught). The file also does **not** misuse flet's API — it simply does not use it, which is the point of §2: `spawn()` is a *loop-local* mechanism, whereas flet's `page.run_task` (`flet/controls/page.py:929-962`) is a *thread-safe* mechanism. The brief's suspicion — that this file "wraps flet's mechanism" — is **not** borne out: it does not, and it is not equivalent to it.

**What is right:** the file is small, correct for the on-loop case, and its exception-retrieval fix (preventing asyncio's "Task exception was never retrieved") is genuine and works. Because flet invokes sync handlers inline on the app's loop thread (`flet/controls/base_control.py:546-551`), all 96 current call sites are on-loop, so `spawn()` introduces **no** worker-thread UI-update hazard today.

**What is wrong, in priority order:**
1. **B1** — no thread/loop guard: one call site reached from a worker thread raises `RuntimeError` synchronously and drops the job (the repo already hand-rolls this guard at `src/services/http_client.py:88-96`).
2. **B3 + B4** — the diagnostics are effectively unusable: no traceback, and ~90 of 96 failures are indistinguishable under the name `"bg-task"`.
3. **B2** — "tracked" tasks are not tracked: no registry, no strong reference, no cancellation at shutdown, 91 of 96 handles discarded.
4. **B5** — spawned tasks sit outside flet's auto-update lifecycle (`flet/messaging/session.py:565-587`); UI mutations inside them are not flushed unless `page.update()` is called explicitly, and nothing in this file says so.
5. **B6/B7/B8/B10** — contract drift: docstring overstates the guarantee, cancellation is invisible, no coroutine-leak guard, and the RUF006 rationale no longer matches the codebase.

**Recommendation:** keep the module and keep it as *the* single spawn helper (the alternative — four coexisting schemes across `src/main.py:1190+`, `src/services/user_scanner_compat.py`, `src/services/email_service.py`, `src/services/phone_service.py` — is worse), but land I1–I4 (loop guard/binding, registry + `cancel_all()`, `exc_info=exc`, `__qualname__`-derived default name). Those four changes are small, local to this file, and convert it from "fire-and-forget with a log line" into something that matches its own docstring. Until then, treat `spawn()` as **on-loop only, uncancellable, and diagnostically weak**, and prefer `page.run_task` for anything originating off the UI thread.
