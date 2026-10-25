# Audit — `src/hooks/use_debounce.py`

**Audited file:** `src/hooks/use_debounce.py` (41 lines)
**Ground truth:** installed `flet 1.0.4` at `.venv/Lib/site-packages/flet`
**Audit date:** 2026-10-22
**Mode:** read-only (no files modified)

---

## 1. File role

A custom Flet hook that debounces a value across re-renders of a function component.

Public API (single export):

```python
def use_debounce(value, delay_ms: int = 250):   # -> debounced value
```

Mechanism: `ft.use_state` holds the debounced value, `ft.use_ref` holds the pending
`asyncio.Task`, and `ft.use_effect(..., [value], cleanup=...)` reschedules a
`asyncio.sleep(delay_ms/1000)` task on every change of `value`; the task calls the
`use_state` setter when the delay elapses. Trailing-edge only. The pending task is
cancelled by the effect cleanup (which fires both on dep change and on unmount).

`core.tasks.spawn` (imported at line 14) is a thin `asyncio.create_task` wrapper that
attaches a done-callback logging failures at WARNING level
(`src/core/tasks.py`).

The file is importable as `from hooks.use_debounce import use_debounce` because the
project root for runtime imports is `src` (`[tool.flet.app] path = "src"`,
`[tool.pytest.ini_options] pythonpath = ["src"]`).

---

## 2. flet hooks API verification

Every flet API used by this file was read from the installed source. **No hallucinated
APIs, no wrong signatures, no misuse of the hook rules.** Detailed below.

| Used at | API | Installed source | Verdict |
|---|---|---|---|
| `:20` | `ft.use_state(value)` | `.venv/Lib/site-packages/flet/components/hooks/use_state.py:47` | CORRECT — returns `(value, setter)`; setter does a shallow `!=` guard then `hook.component._schedule_update()` (`use_state.py:100-108`). |
| `:21` | `ft.use_ref(None)` | `flet/components/hooks/use_ref.py:51` | CORRECT — returns a `MutableRef` with a `current` slot (`use_ref.py:17-22`). `None` is not callable, so it is stored verbatim. |
| `:39` | `ft.use_effect(setup, [value], cleanup=...)` | `flet/components/hooks/use_effect.py:48` | CORRECT — the `cleanup` keyword exists and is honoured. |

Lifecycle semantics verified (these are the ones that actually decide whether the hook
is correct):

1. **Cleanup runs before the next setup.** `Component._run_render_effects`
   (`flet/components/component.py:336-346`) enqueues the cleanup *then* the setup, and
   the session drains `__pending_effects` FIFO
   (`flet/messaging/session.py:723-745`). So "cancel old timer → schedule new timer"
   ordering is preserved. **Correct.**
2. **The setup closure is always the newest render's closure.** `use_effect` replaces
   `hook.setup`/`hook.cleanup` on *every* render (`use_effect.py:73-75`), and the
   scheduler invokes `hook.setup()` **at execution time**, not at schedule time
   (`session.py`, effect runner: `res = hook.setup()`). Therefore the `value` captured
   inside `_cancel_and_schedule` / `_after_delay` is the **latest** rendered value — the
   classic stale-closure trap is **not** present here. This is the single most important
   non-bug in the file and it was confirmed rather than assumed.
3. **flet will not clobber the `cleanup=` callback.** The scheduler does
   `res = hook.setup()` and then `if callable(res): hook.cleanup = res`
   (`session.py`, effect runner). `_cancel_and_schedule` returns `None`, so the
   explicitly-registered `_cleanup` survives. Had the setup returned a callable, the
   unmount cancellation would have been silently replaced. **Currently correct, but only
   by accident of the return value** (see Improvement I-6).
4. **Unmount cleanup actually fires.** `Component.will_unmount` →
   `_run_unmount_effects` (`component.py:370-378`) → `session.schedule_effect`, and
   `schedule_effect` deliberately holds a **strong** reference to the hook so the
   cleanup is not dropped when `_state.hooks.clear()` runs (`session.py:676-691`).
   **Correct** — the pending timer is cancelled on unmount.
5. **The hook's own `cancel()` does not know about our task.** `EffectHook.cancel()`
   (`use_effect.py:33-39`) only cancels flet's `_setup_task`/`_cleanup_task`; the
   `spawn()`-created debounce task is invisible to it, so cancellation must be done by
   the hook itself — which line 24-26 and 34-37 do. **Correct.**
6. **Writing state after unmount is safe.** `Component._schedule_update`
   (`component.py:207-220`) returns early when `not self._state.mounted`, so even if the
   timer fires in the window between unmount and cleanup execution, no zombie update is
   pushed. **Correct.**
7. **Dependency comparison.** `hook.deps != hook.prev_deps` (`component.py:338-342`) is a
   plain list comparison (element-wise `==`), *not* `shallow_compare_args`. For `str`
   values this is identical to the shallow comparison used by `use_memo`; for mutable
   values it is not (see Bug B-6).

---

## 3. Call census

Two call sites, both inside `@ft.component` function bodies, both calling the hook
**unconditionally at the top level of the component body** (verified: `ResultsScreen`
has no early `return` between its component decorator at `results_screen.py:298` and
the hook call at `:328`, so flet's positional hook-slot ordering is not corrupted).

| Call site | Component | Value debounced | Delay | Downstream effect |
|---|---|---|---|---|
| `src/screens/sites_screen.py:152` | `SitesSearchBar` (`@ft.component` at `sites_screen.py:144`) | `raw` — the local `TextField` value | 200 ms | Propagated up via `ft.use_effect(lambda: on_debounced(debounced), [debounced])` (`sites_screen.py:153`) → `set_debounced_query` in `SitesScreen`; wired at `sites_screen.py:529` (`on_debounced=set_debounced_query`). Feeds the 5,200-row filtered-names memo (`sites_screen.py:416, 441`). |
| `src/screens/results_screen.py:328` | `ResultsScreen` (`@ft.component` at `results_screen.py:298`) | `filter_query` — raw filter `TextField` state (`:327`) | 250 ms | Drives the result filter/memo (`results_screen.py:437, 441, 605-610, 771-814`). |

Supporting notes:

- Imports are `from hooks.use_debounce import use_debounce` (`sites_screen.py:23`,
  `results_screen.py:28`) — consistent with `src` as the import root.
- `storage_service.py` mentions "debounce" (`storage_service.py:70, 272`) but that is an
  **unrelated** file-level debounce of `os.replace` writes; it does not use this hook.
- **No test in `tests/` references `use_debounce`** (grep over the whole repo found zero
  test hits). The hook is entirely untested.
- The module docstring's "Mirrors KTV's use_debounce exactly" is **consistent with repo
  conventions** — "KTV" is the external KTV-Player project referenced in
  `src/app_shell.py:3`, `src/components/app_header.py:32`, `src/core/logger_handler.py:3`
  — but the referenced implementation is not vendored, so the claim is unverifiable
  in-repo (see B-8).

---

## 4. Bugs (severity-ordered)

### B-1 — HIGH · Stale value can be committed after it has been superseded (stale-commit race)

`src/hooks/use_debounce.py:28-32`, `:39`

The trailing timer is cancelled only by the effect **cleanup**, and the cleanup is
*deferred through the session scheduler* (`session.schedule_effect` → drained by
`__updates_scheduler`), while the timer itself lives on the event loop's own timer heap.
If the loop is congested for longer than `delay_ms` between the keystroke and the
scheduler drain, the old timer fires first and commits a **superseded** value:

```
t0  value "a"  -> render -> queue(cleanup, setup) -> setup spawns T_a (fires at t0+200ms)
t1  value "ab" -> render -> queue(cleanup, setup)   (queue drains late: loop busy)
t2  T_a fires   -> set_debounced("a")   <-- stale commit, value was already "ab"
t3  queue drains -> cleanup cancels T_a (already fired) -> setup spawns T_ab
t4  T_ab fires  -> set_debounced("ab")
```

This codebase is a textbook trigger for it: `sites_screen.py:145-148` documents that the
search bar exists so "keystrokes don't rebuild the 5,200-row list", and
`results_screen.py:335-338` documents a 2 Hz progress tick that was causing a
`RangeError` storm. A congested loop is the normal state here, not the exception. The
visible symptom is an extra full 5,200-row rebuild plus a flash of the *old* filter
result — exactly the cost the hook exists to prevent.

The correctness of the *final* value is preserved (the last timer always wins), so this
is a transient-staleness bug, not a lost-update bug.

Fix direction: stamp each scheduled timer with a monotonically increasing sequence
number held in the ref, and have `_after_delay` compare-and-skip before committing
(`if seq_ref.current != my_seq: return`). That removes the dependency on cleanup
ordering entirely.

### B-2 — HIGH · Write-back depends on an ambient ContextVar captured by the session scheduler, and its failure is silent

`src/hooks/use_debounce.py:30`, `:32`

`set_debounced` → `use_state`'s setter → `Component._schedule_update()` →
`context.page.session.schedule_update(self)` (`flet/components/component.py:220`).
`ft.context.page` is a ContextVar-backed property that **raises** when the var is unset:

```python
# flet/controls/context.py:61-68
page = _context_page.get()
if page is None:
    raise RuntimeError("The context is not associated with any page. ...")
```

The debounce task is created by `asyncio.create_task` inside the effect setup, and the
effect setup runs inside the session's `__updates_scheduler` task
(`session.py`, `start_updates_scheduler`, called from `flet/controls/page.py:810`).
`asyncio.create_task` **copies the current `contextvars` context**, so the timer task
inherits the context snapshot of the *scheduler task* — not the context of the render
that scheduled the effect. If that snapshot has no page bound (embedded/multi-session
host app, a page replaced after the scheduler started, or a scheduler started outside a
page context), `set_debounced` raises `RuntimeError` inside the timer task.
`core.tasks.spawn` catches it and downgrades it to
`logger.warning("Background task 'debounce' failed: ...")` — so **the debounced value
silently never updates and the search box stops filtering, with no UI error and only a
WARNING in the log.**

Fix direction: capture the page during render (where `ft.context.page` is guaranteed
valid) and pin it into the task. Python ≥ 3.14 is required by this project, so
`asyncio.create_task(coro, context=ctx)` with `ctx = contextvars.copy_context()`
captured at render time is available and makes the write-back deterministic.
`spawn()` in `src/core/tasks.py` would need a `context=` passthrough.

### B-3 — MEDIUM · A callable `value` is executed instead of debounced

`src/hooks/use_debounce.py:20`

`use_state` treats a callable initial value as a lazy factory
(`flet/components/hooks/use_state.py:66-70`: `initial() if callable(initial) else initial`).
`use_debounce` forwards the caller's `value` straight into `use_state`, so
`use_debounce(lambda: 1)` silently calls the lambda at mount and debounces the *result*
(`1`) instead of the callable. No current consumer passes a callable, but the hook
advertises no type constraint (see B-7) and the failure is silent and confusing.

Fix: `debounced, set_debounced = ft.use_state(lambda: value)` — the lambda is invoked
once at hook creation and yields `value` verbatim.

### B-4 — MEDIUM · `delay_ms` is not a dependency, so a changed delay is never applied

`src/hooks/use_debounce.py:39`

`ft.use_effect(_cancel_and_schedule, [value], cleanup=_cleanup)` — `delay_ms` is absent
from the deps. If a caller changes `delay_ms` while `value` is unchanged, the effect
does not re-run: the already-scheduled timer keeps the **old** delay, and the new delay
is only picked up the next time `value` changes. Both current call sites pass literals
(200 / 250) so this is latent, but it is a latent API bug, not a style issue.

Fix: `ft.use_effect(_cancel_and_schedule, [value, delay_ms], cleanup=_cleanup)`.

### B-5 — LOW-MEDIUM · Every mount spawns a pointless timer

`src/hooks/use_debounce.py:23-32`

flet runs **all** effect setups on mount regardless of deps
(`flet/components/component.py:312-322`, `_run_mount_effects`), so each mount of
`SitesSearchBar` / `ResultsScreen` spawns a `delay_ms` task whose only action is
`set_debounced(value)` with a value identical to the current state — a no-op because
`use_state`'s setter short-circuits on `new_value != hook.value`
(`flet/components/hooks/use_state.py:100`). Net effect: one wasted task + timer per
mount, and a false "pending" impression on `timer.current`.

Fix (safe only if the cancel happens first): in `_cancel_and_schedule`, cancel the
pending timer, then return early when `value == debounced`. **Order matters** — see
Improvement I-4; skipping the schedule without cancelling first would leave a stale
timer alive and re-introduce B-1.

### B-6 — LOW-MEDIUM · Mutated-in-place values are silently ignored

`src/hooks/use_debounce.py:17`, `:39`

The effect's dep check is a plain list `!=` (`component.py:338-342`), i.e. element-wise
`==`. If `value` is a `list`/`dict` mutated in place, the comparison sees the same
object and reports "unchanged", so the effect never re-runs and the debounce never
fires — the value is debounced to a *stale snapshot forever*, with no error. The hook
declares no type constraint (B-7), so nothing steers a caller away from this.

### B-7 — LOW · Missing type annotations on the public surface

`src/hooks/use_debounce.py:17`

`def use_debounce(value, delay_ms: int = 250):` — `value` has no annotation and the
function has no return annotation, even though the hook is string-only in practice and
B-6 is a real hazard for mutable inputs. `delay_ms` is annotated but has no lower bound
(negative values silently behave as `asyncio.sleep(0)`).

### B-8 — LOW · Dead default + unverifiable provenance

`src/hooks/use_debounce.py:3`, `:17`

- `delay_ms: int = 250` is never exercised: both call sites pass an explicit delay
  (`sites_screen.py:152` → 200, `results_screen.py:328` → 250), and the 250 default
  duplicates `results_screen.py`'s explicit value.
- "Mirrors KTV's use_debounce exactly" points at an external project that is not
  vendored in this repo (KTV-Player is referenced in `app_shell.py:3`,
  `components/app_header.py:32`, `core/logger_handler.py:3`). The convention is
  repo-wide, but the "exactly" claim cannot be checked here — and given B-1/B-2/B-3, it
  should not be assumed to hold.

### B-9 — LOW · `timer.current` is never reset to `None`

`src/hooks/use_debounce.py:34-37`

`_cleanup` cancels the pending task but leaves the cancelled `Task` object in the ref,
which keeps the task's captured closure (and therefore the last `value`) alive for the
lifetime of the component. Trivial memory-wise, but it also makes "is a timer pending?"
unanswerable from the ref.

### B-10 — LOW · Zero test coverage

No file under `tests/` references `use_debounce`. The whole file — including the
unmount-cancellation path that is easy to break — is untested.

### Timing / `time.monotonic` check (explicitly requested)

**No wall-clock arithmetic is used anywhere in this file**, so there is no
`time.time()`/clock-skew/NTP-jump bug to find. `asyncio.sleep` uses the event loop's
monotonic clock internally.

That said, there is a related accuracy issue: the debounce window is measured from
**when the timer task starts running**, not from when the value changed. Under loop
congestion (2 Hz progress ticks + 5,200-row rebuilds in this app) the effective window
becomes `delay_ms + stall`. If a hard bound is required, compute a deadline with
`time.monotonic()` at change time and sleep the remainder, optionally with a
`max_wait` cap (see I-2).

### Thread-safety check (explicitly requested)

Not applicable, and the code is safe on this axis: both the hook body (render) and the
effect setup (session scheduler) run on the event-loop thread, so `asyncio.create_task`
always has a running loop. The only edge is that `spawn()` would raise
`RuntimeError: no running event loop` if the hook were ever rendered outside a Flet
session (e.g. a direct unit-test call of the component function) — a testability note,
not a production bug.

---

## 5. Improvements

- **I-1 (fixes B-1) — sequence-number guard.** Keep a monotonically increasing counter in
  the ref; `_after_delay` captures its own number and returns early if it is no longer
  the current one. This makes the commit safe regardless of when the deferred cleanup
  runs, and costs one integer compare.
- **I-2 — support `leading` and `max_wait`.** A pure trailing edge means a user who
  types one character and stops waits the full delay for the filter; a leading edge
  (update immediately, then suppress until quiet) plus a `max_wait` cap covers the
  common "type fast then stop" case. Both are standard and cheap to add.
- **I-3 — expose `flush()` / `cancel()`.** A bare debounced value cannot be forced. Any
  future consumer that needs the value at submit time (a "Search" button) has no way to
  get it. A companion `use_debounce_ext` returning `(value, flush, cancel, pending)`
  would cover this without breaking the existing call sites.
- **I-4 — skip the mount no-op timer (order-sensitive).** Cancel first, then
  `if value == debounced: return`. Cancelling first is mandatory — returning early
  without cancelling would leave the previous timer alive and re-introduce B-1.
- **I-5 — pin the page into the task (fixes B-2).** Capture `contextvars.copy_context()`
  during render (where `ft.context.page` is valid) and schedule the timer with
  `asyncio.create_task(coro, context=ctx)`; this needs a `context=` passthrough on
  `src/core/tasks.py::spawn`. As a minimum, catch the failure around `set_debounced`
  and log it at ERROR level rather than letting `spawn` downgrade it to WARNING.
- **I-6 — make the cleanup contract explicit.** flet replaces the registered cleanup if
  the setup returns a callable (`session.py`: `if callable(res): hook.cleanup = res`).
  `_cancel_and_schedule` currently returns `None` by accident of falling off the end.
  Add an explicit `return None` plus a comment, so a future edit cannot silently
  disarm the unmount cancellation.
- **I-7 — annotate the API.** `value: str`, `delay_ms: int = 250`, `-> str`, and a
  `delay_ms >= 0` guard.
- **I-8 — add tests.** `flet.testing` is available in the installed package
  (`.venv/Lib/site-packages/flet/testing`). Minimum cases: trailing-edge timing,
  coalescing of rapid successive updates, cancellation on unmount (no state write after
  unmount), and the "value returns to the last committed value" case that B-1/B-5
  interact with.
- **I-9 — consider `use_debounce` vs. a `use_debounced_callback`.** Both consumers need
  "value after quiet period" — `sites_screen.py` uses the value + an effect,
  `results_screen.py` uses the value directly. A callback variant
  (`use_debounced_callback(fn, delay)`) would remove the extra `use_effect` at
  `sites_screen.py:153` and the double state hop.
- **I-10 — move the "is it pending / is it settled" question into the hook.** The ref
  already knows; exposing it (I-3) avoids each consumer re-deriving it.

---

## 6. Verdict

**The flet API usage is clean and correct.** Every hook (`use_state`, `use_ref`,
`use_effect` with `cleanup=`) exists in the installed flet 1.0.4 with the expected
signature, the hook-call ordering rules are respected, cleanup genuinely fires on
unmount, and — importantly — the "stale closure over `value`" bug that a naive reading
of this file would predict is **not** present, because flet re-reads `hook.setup` at
execution time. No hallucinated APIs, no invalid kwargs, no dead imports
(`asyncio` and `ft` are both used).

**The timing logic is correct but fragile.** Trailing-edge semantics, cancel-before-
reschedule ordering and the equality short-circuit in `use_state` all behave as
intended. The fragility is in the *scheduling substrate*: flet defers effect cleanup
through the session scheduler while the debounce timer lives on the loop's timer heap
(B-1), and the state write-back path resolves the page through an ambient ContextVar
that the spawned task merely inherits (B-2).

**Severity summary:** 2 high (B-1 stale-commit race, B-2 context-bound write-back with
silent failure), 2 medium (B-3 callable value, B-4 delay not a dependency), 5 low
(B-5 mount no-op timer, B-6 mutable values, B-7 annotations, B-8 dead default,
B-9 stale ref, B-10 no tests).

**Recommendation:** the file is safe to keep as-is for the two current consumers
(string values, literal delays), but B-1 and B-2 should be fixed before this hook is
used anywhere else — B-2 in particular fails *silently* (WARNING-level log only) and
would present as "the search box mysteriously stopped filtering". I-1 (sequence guard)
and I-5 (context pinning) together are a small, self-contained change to these 41 lines
that removes both high-severity findings.
