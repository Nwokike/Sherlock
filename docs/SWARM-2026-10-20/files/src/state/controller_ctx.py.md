# SWARM Audit — `src/state/controller_ctx.py` (+ `src/state/app_state.py`)

Unit under audit: the two context-provider modules.
Ground truth: installed **flet 1.0.4** at `.venv\Lib\site-packages\flet`.
Read-only audit — no files were modified.

---

## 1) File roles

### `src/state/app_state.py` (9 lines)

A one-line context adapter over the observable application state:

- `app_state.py:5` — `from core.state import state` (the module-level singleton created at `src/core/state.py:240`: `state = AppState()`).
- `app_state.py:7` — `AppStateCtx = ft.create_context(state)`.
- `app_state.py:9` — `__all__ = ["AppStateCtx", "state"]`.

Consumers (all via `ft.use_context(AppStateCtx)`, never as a provider):

| Consumer | Line |
|---|---|
| `src/app_shell.py` | 722 |
| `src/screens/home_screen.py` | 362 |
| `src/screens/results_screen.py` | 300 |
| `src/screens/sites_screen.py` | 193 |
| `src/screens/settings_screen.py` | 291 |
| `src/screens/history_screen.py` | 96 |
| `src/screens/onboarding_screen.py` | 111 |

**Verified: no provider for `AppStateCtx` exists anywhere.** `grep -rn "AppStateCtx(" src/ tests/` returns nothing — the only creation site is `app_state.py:7`. So the context is *never mounted*; every consumer resolves the `default_value`, which is the global `state` singleton (empirically confirmed: `AppStateCtx.default_value is state` → `True`).

### `src/state/controller_ctx.py` (86 lines)

The callback-injection bus for the component tree.

- `controller_ctx.py:45-81` — `@dataclass class ControllerMethods`: 22 callable fields, every one with a no-op default.
- `controller_ctx.py:20-42` — five named async/sync no-op helpers + one inline lambda default.
- `controller_ctx.py:84` — `ControllerMethodsCtx = ft.create_context(ControllerMethods())` → a **module-level mutable singleton** used as the default.
- `controller_ctx.py:1-12` — docstring describing the two-phase wiring (AppController builds → AppShell mutates in place).

Provider site (the premise is correct, but the file is `main.py`, not `app_shell.py`):

- `src/main.py:546-560` — AppController constructs `methods = ControllerMethods(...)` and stores it at `main.py:561` (`self._controller_methods`).
- `src/main.py:588` — `self.page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))` — **the only mount point**.

Mutation site (AppShell, during its render):

- `src/app_shell.py:721` — `controller = ft.use_context(ControllerMethodsCtx)` (resolves to the *same* instance `main.py` built, because `AppShell` is constructed inside the provider callback — see §2.4).
- `src/app_shell.py:725-730` — `show_results`, `show_sites`, `go_home`, `back`, `open_sheet`, `close_dialog`.
- `src/app_shell.py:743` — `handle_system_back`.
- `src/app_shell.py:753-754` — `show_settings`, `show_history`.

---

## 2) flet context API verification (installed 1.0.4)

Source of truth: `.venv\Lib\site-packages\flet\components\hooks\use_context.py`, `.venv\Lib\site-packages\flet\components\component.py`, `.venv\Lib\site-packages\flet\components\observable.py`.

### 2.1 `ft.create_context` — VALID, no hallucination

`use_context.py:52-79`. Signature `create_context(default_value: T) -> ContextProvider[T]`. It returns a closure `provider(value, callback)` with attributes `default_value` and `_key` (a unique `object()`).

- `ft.create_context` is exported at `flet\__init__.py:20` / `:1247` → `app_state.py:7` and `controller_ctx.py:84` are legal.
- The provider call arity is `provider(value, callback)` (`use_context.py:62-64`), which matches `main.py:588`: `ControllerMethodsCtx(methods, lambda: AppShell())`. ✓

### 2.2 `ft.use_context` — VALID, and the failure modes are *not* what the code assumes

`use_context.py:82-113`. Actual semantics:

1. `current_component()` + `component.use_hook(...)` → **calling `use_context` outside a component raises `RuntimeError`** (empirically: `RuntimeError: No current renderer is set. Call via Renderer.render(...) or Renderer.with_context(...)`). Not an `AttributeError`.
2. It walks the **component parent chain** for `context._key` (`use_context.py:98-104`): `comp = component; while comp: if context._key in comp._contexts: ...; comp = comp._parent_component()`.
3. **If no provider is found it returns `context.default_value` — no error is raised** (`use_context.py:96-97`). This is the single most important fact for this audit: *"missing provider"* is silent, not fatal.
4. `use_context.py:109-110` — `if isinstance(value, Observable): component._attach_observable_subscription(value)`. **This is the entire functional value of `AppStateCtx`.** `state` is `AppState` decorated with `@ft.observable` (`src/core/state.py:12-13`), and `isinstance(state, ft.Observable)` was empirically confirmed `True`, so every `use_context(AppStateCtx)` caller does get a reactive subscription to the global state.

**Answer to the audit question "does the provider/consumer pattern hold?"** — The *consumer* half is correct and load-bearing (it is how the screens re-render on state changes). The *provider* half is vestigial: nothing ever provides `AppStateCtx`, so the context provides zero scoping; `default_value` is the global singleton and every consumer resolves it. `use_context(AppStateCtx)` is effectively "subscribe to the global observable".

### 2.3 `ControllerMethods` is NOT observable

`ControllerMethods` is a plain `@dataclass` (`controller_ctx.py:45`), so `isinstance(value, Observable)` is `False` for the controller context → **no subscription is attached**. Mutating `controller.show_results` at `app_shell.py:725` does **not** schedule a re-render of any consumer. This is currently harmless only because the mutations happen inside AppShell's own render and the closures are re-assigned on every AppShell render.

### 2.4 Context propagation mechanics (why the wiring works at all)

`component.py:517` — `c._contexts = self._snapshot_contexts()` is executed when a component wrapper is **constructed**, snapshotting the renderer's context stack (`component.py:444-453`). The provider pushes/pops around the callback (`use_context.py:66-73`), so:

- `AppShell()` is constructed **inside** the provider callback → `AppShell._contexts` contains `methods` → `app_shell.py:721` resolves the provider instance, and its mutations land on the very object `main.py:561` holds. ✓
- The screens are constructed later, during AppShell's render, when the provider has already popped → their own `_contexts` is empty → they find the value by walking up to `AppShell` (`use_context.py:100-104`). ✓
- **Corollary:** a screen rendered *outside* the AppShell subtree would silently fall back to the default singleton (§2.2 item 3) — i.e. all no-ops.

### 2.5 Dataclass-with-function-default semantics — checked, no bug

`controller_ctx.py:66` uses `lambda _q, _m: False` as a field default. Dataclasses assign defaults into the instance `__dict__` in the generated `__init__`, so the lambda is **not** bound as a method. Empirically verified: `ControllerMethods().open_cached_result.__self__` is `None` and the repr is `<function ControllerMethods.<lambda> ...>`. Calling `controller.open_cached_result(q, m)` returns `False` as intended. The same holds for `_noop_async`/`_noop_search`/etc. — no hidden `self` binding anywhere.

### 2.6 Verified non-hallucinations

`ft.create_context`, `ft.use_context`, `ft.observable` are all present in `flet\__init__.py` (`:20, :21, :1256`) and behave as documented above. `import flet as ft` + `ft.create_context(state)` (`app_state.py:3,7`) and `ft.create_context(ControllerMethods())` (`controller_ctx.py:17,84`) are both correct usage of the installed API. **No hallucinated APIs in either file.**

---

## 3) Callable census — provided vs consumed

`ControllerMethods` has **22 fields**. Full matrix (decl = `controller_ctx.py` line; populated = where the real callable is bound; consumed = read through the context):

| # | Field | Decl | Default | Populated by | Consumed at | Status |
|---|---|---|---|---|---|---|
| 1 | `refresh_sites` | 55 | `_noop_async` | `main.py:545` | `home_screen.py:454,500,501,514`; `settings_screen.py:399,400,408,409,414,415,426,427,568,569`; `sites_screen.py:655,656` | OK |
| 2 | `start_search` | 56 | `_noop_search` | `main.py:546` | `history_screen.py:217`; `home_screen.py:672,771`; `results_screen.py:372` | OK |
| 3 | `cancel_search` | 57 | `_noop_sync` | `main.py:547` | `results_screen.py:912` | OK |
| 4 | `start_email_search` | 58 | `_noop_search` | `main.py:548` | `history_screen.py:215`; `home_screen.py:668,769`; `results_screen.py:368` | OK |
| 5 | `cancel_email_search` | 59 | `_noop_sync` | `main.py:549` | `results_screen.py:712` | OK |
| 6 | `start_phone_search` | 60 | `_noop_search` | `main.py:550` | `home_screen.py:670`; `results_screen.py:370` | OK |
| 7 | `cancel_phone_search` | 61 | `_noop_sync` | `main.py:553` | **none** | **DEAD** |
| 8 | `save_selected_sites` | 62 | `_noop_save_sites` | `main.py:551` | `sites_screen.py:264` | OK |
| 9 | `check_for_updates` | 63 | `_noop_async` | `main.py:555` | **none** (main.py:535 calls `self.check_for_updates` directly) | **DEAD** |
| 10 | `open_update_dialog` | 64 | `_noop_sync` | `main.py:556` | **none** (main.py:2306 calls `self.open_update_dialog()` directly) | **DEAD** |
| 11 | `set_onboarding_done` | 65 | `_noop_async` | `main.py:557` | `onboarding_screen.py:122,123` | OK |
| 12 | `open_cached_result` | 66 | `lambda _q,_m: False` | `main.py:558` | `history_screen.py:198`; `home_screen.py:761` | OK |
| 13 | `show_results` | 69 | `_noop_sync` | `app_shell.py:725` | `history_screen.py:211`; `home_screen.py:666,765`; `app_shell.py:605,622,625` | OK |
| 14 | `show_sites` | 70 | `_noop_sync` | `app_shell.py:726` | `home_screen.py:1263` | OK |
| 15 | `show_settings` | 71 | `_noop_sync` | `app_shell.py:753` | `history_screen.py:446`; `home_screen.py:986` | OK |
| 16 | `show_history` | 72 | `_noop_sync` | `app_shell.py:754` | `home_screen.py:1356` | OK |
| 17 | `go_home` | 73 | `_noop_sync` | `app_shell.py:727` | `app_shell.py:672` | OK (internal only) |
| 18 | `back` | 74 | `_noop_sync` | `app_shell.py:728` | `app_shell.py:689,739` | OK (internal only) |
| 19 | `open_sheet` | 77 | `_noop_dialog` | `app_shell.py:729` | `app_shell.py:580` only | Internal-only via context |
| 20 | `close_dialog` | 78 | `_noop_sync` | `app_shell.py:730` | `app_shell.py:248,502` only | Internal-only via context |
| 21 | `run_db_health` | 79 | `_noop_health` | `main.py:559` | `settings_screen.py:534,544` | OK — **mis-grouped** (see B4) |
| 22 | `handle_system_back` | 81 | `_noop_sync` | `app_shell.py:743` | `main.py:574,625` (via the instance, not `use_context`) | OK |

**Totals:** 19/22 consumed; **3 dead** (#7, #9, #10); 2 fields (`open_sheet`, `close_dialog`) are consumed only by `app_shell.py` itself — the same module that writes them — so routing them through the shared context object buys nothing.

### 3.1 Signature drift — NONE FOUND

Every provided callable matches its declared field type exactly (`src/main.py` definitions verified against `controller_ctx.py:55-81`):

| Field type declared | Provided callable (main.py) | Verdict |
|---|---|---|
| `Callable[[], Awaitable[None]]` | `async def _load_and_cache_sites(self) -> None` (`:851`) | ✓ |
| `Callable[[str], Awaitable[None]]` | `async def start_search(self, username: str) -> None` (`:883`) | ✓ |
| `Callable[[], None]` | `def cancel_search(self) -> None` (`:1437`) | ✓ |
| `Callable[[str], Awaitable[None]]` | `async def start_email_search(self, email: str) -> None` (`:1456`) | ✓ |
| `Callable[[], None]` | `def cancel_email_search(self) -> None` (`:1713`) | ✓ |
| `Callable[[str], Awaitable[None]]` | `async def start_phone_search(self, phone: str) -> None` (`:1728`) | ✓ |
| `Callable[[], None]` | `def cancel_phone_search(self) -> None` (`:1849`) | ✓ |
| `Callable[[list[str]], Awaitable[None]]` | `async def save_selected_sites(self, sites: list[str]) -> None` (`:1864`) | ✓ |
| `Callable[[], Awaitable[None]]` | `async def check_for_updates(self, notify_if_latest: bool = False) -> None` (`:2296`) | ✓ (extra param has a default) |
| `Callable[[], None]` | `def open_update_dialog(self) -> None` (`:2291`) | ✓ |
| `Callable[[], Awaitable[None]]` | `async def set_onboarding_done(self) -> None` (`:1881`) | ✓ |
| `Callable[[str, str], bool]` | `def open_cached_result(self, query: str, mode: str) -> bool` (`:1893`) | ✓ |
| `Callable[[], Awaitable[dict]]` | `async def run_db_health(self) -> dict` (`:2263`) | ✓ |

**One soft mismatch:** `refresh_sites` is `Callable[[], Awaitable[None]]` but main.py:540-543 may supply `lambda: asyncio.sleep(0)` — awaitable, so type-compatible, yet the coroutine is created eagerly and only harmless because every consumer awaits it.

---

## 4) Bugs (severity-ordered)

### B1 — HIGH · `controller_ctx.py:84` · The context default is a shared, mutable, module-level singleton

```python
ControllerMethodsCtx = ft.create_context(ControllerMethods())
```

`ControllerMethods()` is instantiated **once, at import time**, and becomes the `default_value` for every `use_context(ControllerMethodsCtx)` call that resolves no provider (flet `use_context.py:96-97`).

Combined with AppShell's in-place mutation (`app_shell.py:725-730, 743, 753-754`), any AppShell rendered *without* the provider — the exact scenario the module docstring advertises as supported ("even before the provider is mounted (e.g. inside unit tests that instantiate AppShell directly)", `controller_ctx.py:10-11`) — **mutates the global default object**. Consequences:

- `handle_system_back` (`app_shell.py:743`) closes over that instance's `active_view` / `set_active_view` / `state`; a second, provider-less AppShell **overwrites** the first's handler, so instance #1's screens would drive instance #2's view state (writing to a torn-down component).
- All other closures (`show_results`, `go_home`, …) are likewise replaced process-wide.
- Cross-test / cross-instance contamination, with no error raised anywhere.

Production is safe **only** because `main.py:588` always mounts the provider before `AppShell` renders. The safety is incidental, not enforced — nothing in `controller_ctx.py` or `app_shell.py` asserts that the resolved instance is the provider's instance.

**Fix:** stop using a mutable singleton as `default_value`. Either (a) `ControllerMethodsCtx = ft.create_context(None)` + an explicit `if controller is None: raise RuntimeError(...)` in `app_shell.py:721`; or (b) have `AppShell` detect `controller is ControllerMethodsCtx.default_value` and refuse to write globals (log + create a per-instance copy); or (c) make the provider mandatory in `main.py` and assert it.

### B2 — HIGH · `controller_ctx.py:55-81` · Silent no-op defaults mask every wiring failure

All 22 fields default to a no-op (`_noop_async`, `_noop_search`, `_noop_save_sites`, `_noop_sync`, `_noop_dialog`, `_noop_health`, `lambda _q,_m: False`).

**Answer to the audit question "what happens when a controller callable is missing?"**

| Situation | Actual behaviour |
|---|---|
| Field declared but not passed at construction (e.g. `check_for_updates` omitted) | The dataclass default is used → **silent no-op**, no log, no exception |
| Provider not mounted at all | `use_context` returns the module default singleton (§2.2) → **every** callback is a no-op → the UI is silently dead |
| Field not declared on the dataclass (typo, e.g. `controller.show_result`) | `AttributeError` — the *only* way to get one |

So: **never an `AttributeError` for a real field, never `None`** — the failure mode is "the button does nothing". Combined with B1, a mis-mounted provider degrades to an app that looks alive but is inert, with zero diagnostics.

**Fix:** make unwired-ness loud — a sentinel default that logs/raises with the field name (e.g. `def _unwired(name): def _f(*a, **k): logger.error("controller callback %s is not wired", name); return None`).

### B3 — MEDIUM · `controller_ctx.py:61, 63, 64` · Three dead fields (3/22 of the API surface)

`cancel_phone_search`, `check_for_updates`, `open_update_dialog` are bound in `main.py:553,555,556` but **never read through the context** — `main.py` calls the underlying controller methods directly (`main.py:535`, `:1849`, `:2291`, `:2306`). Notably `cancel_phone_search` has **no consumer anywhere in the tree**: `results_screen.py` cancels email (`:712`) and username (`:912`) scans but never a phone scan. Either the phone-scan cancel UI is missing or the field is vestigial — it is dead weight in the contract and in `__all__`'s implied API.

**Fix:** delete the three fields, or wire `cancel_phone_search` to a real "Cancel" affordance in `results_screen.py` and route the update flow through the context.

### B4 — MEDIUM · `controller_ctx.py:68` vs `:79` · `run_db_health` is filed under the wrong owner/comment

The block header at `controller_ctx.py:68` reads `# AppShell-populated (view-local, sync closures)`, but `run_db_health` sits inside that block (`:79`) while being **AppController-populated** (`main.py:559`) and **async** (`Callable[[], Awaitable[dict]]`, default `_noop_health` returning `{}`). The header also says "sync closures", which is false for this field. A maintainer following the section comments will mis-own or mis-type the callback.

**Fix:** move `run_db_health` up into the AppController block (`:54-66`) and correct the header wording.

### B5 — MEDIUM · `app_state.py:7` · `AppStateCtx` is never used as a provider — the context abstraction is vestigial

No call site invokes `AppStateCtx(value, callback)`; the only construction is `app_state.py:7`. Consequently:

- `use_context(AppStateCtx)` always resolves `default_value` = the global `state` singleton (verified `AppStateCtx.default_value is state`).
- The context scopes nothing. A reader auditing `app_state.py` reasonably expects a provider tree that does not exist; the module docstring ("component-facing adapter over the observable state", `app_state.py:1`) does not say the provider is unused.
- Footgun: the moment someone mounts a provider with a *different* `AppState` instance, only that subtree diverges while every other component silently keeps the global singleton — two state universes, no error.
- The whole mechanism's actual value is one line of flet internals (`use_context.py:109-110`): returning an `Observable` auto-attaches the reactive subscription. That is why this pattern works at all, and it is undocumented here.

**Fix:** either mount a real provider (`AppStateCtx(state, lambda: AppShell())` next to `main.py:588`) to make the design honest, or replace the context with a direct `from core.state import state` plus an explicit subscription helper — and document *why* the context exists if it stays.

### B6 — LOW · Truthiness guards on callable fields are unreachable dead code

A function object is always truthy, so every one of these can never fire:

- `src/screens/settings_screen.py:534` — `if not controller.run_db_health: return`
- `src/screens/history_screen.py:198` — `if controller.open_cached_result and controller.open_cached_result(query, mode)`
- `src/main.py:909`, `:1475`, `:1912`, `:2099` — `and self._controller_methods.show_results`
- `src/main.py:622-623` — `hasattr(self._controller_methods, "handle_system_back")` (the attribute always exists on the dataclass)

These are leftovers from a `None`-default design that the no-op defaults silently defeated (see B2). They give a false sense of safety and hide the fact that the "not wired" path is unreachable.

**Fix:** delete the guards, or make the defaults `None` so the guards become real.

### B7 — LOW · `controller_ctx.py:55` + `main.py:540-543` · `refresh_sites` can be permanently bound to a no-op coroutine

`main.py:540-543` selects between `self._load_and_cache_sites` and `lambda: asyncio.sleep(0)` using `self.sherlock_service.is_available`, evaluated **once** at construction time. If the sherlock engine becomes available later (service restart, retry, late init), the context field stays the no-op for the lifetime of the app and every "refresh sites" button silently does nothing. Also, `lambda: asyncio.sleep(0)` creates a coroutine eagerly — any caller that forgets to `await` it yields a "coroutine was never awaited" warning.

**Fix:** always provide `self._load_and_cache_sites` and let it no-op internally on the availability check, so the binding cannot go stale.

### B8 — LOW · `controller_ctx.py:66` · Unnamed lambda default + value that conflates "unwired" with "no result"

`open_cached_result` is the only field whose default is an inline `lambda _q, _m: False` rather than one of the named `_noop_*` helpers, and the only one that returns a meaningful-looking value. A `False` return is indistinguishable from "callback not wired" (B2), so a wiring regression in `open_cached_result` is invisible: history re-search simply falls through to a fresh scan instead of erroring.

**Fix:** use a named `_noop_open_cached` helper (consistency) and/or return a sentinel distinct from `False`.

### Non-bugs (checked and cleared)

- `lambda` default is not bound as a method (§2.5) — verified empirically.
- `ft.create_context` / `ft.use_context` / `ft.observable` usage — all valid against flet 1.0.4 (§2.6).
- `from core.state import state` (`app_state.py:5`) — absolute import, resolves to `src/core/state.py` under the same `src`-on-`sys.path` convention as `from state.app_state import ...` used everywhere else.
- `ControllerMethods` being a plain dataclass (not `@ft.observable`) is not a bug here — nothing requires the context value itself to be reactive (§2.3).
- No signature drift between provider and consumer (§3.1).

---

## 5) Improvements

**`controller_ctx.py`**

1. **Make "unwired" observable** (fixes B2, B6): replace the six no-op defaults with one factory that logs the field name (and optionally raises), and delete the now-provably-true truthiness guards at `settings_screen.py:534` and `history_screen.py:198`.
2. **Eliminate the shared singleton** (fixes B1): `ft.create_context(None)` + an explicit failure in `app_shell.py:721`, or per-instance copying; at minimum, assert in `app_shell.py` that the resolved instance is not `ControllerMethodsCtx.default_value`.
3. **Prune the dead surface** (fixes B3): remove `cancel_phone_search`, `check_for_updates`, `open_update_dialog` from the dataclass (and `main.py:553,555,556`), or wire them.
4. **Re-group the fields and fix the comments** (fixes B4): two clearly-labelled blocks — `AppController-populated (heavy/async/cache)` and `AppShell-populated (view-local, sync)` — with `run_db_health` in the first.
5. **Tighten `open_sheet`'s type**: `controller_ctx.py:77` declares `Callable[[object], None]`, which accepts literally anything; `Callable[[ft.Dialog], None]` (flet 1.0.4 `use_dialog` takes a `Dialog`) would catch wrong types at the type-checker level. Also annotate the untyped `_noop_dialog(_dialog)` param (`controller_ctx.py:36`) for consistency with `_noop_search(_username: str)` etc.
6. **Fix the docstring provenance** (`controller_ctx.py:3`): the provider expression quoted there lives at `src/main.py:588`, not in `app_shell.py` — an auditor reading only `app_shell.py` will never find it.
7. **Optional**: `@dataclass(eq=False)` — with `eq=True` (the default) two instances holding the same callables compare *equal*, and the auto-generated `__repr__` prints raw function addresses into logs. Identity semantics match flet's own `ComponentOwned` convention.

**`app_state.py`**

8. **Decide and document the provider story** (fixes B5): mount `AppStateCtx(state, …)` next to `main.py:588`, or drop the context in favour of a direct import plus an explicit subscribe. If it stays, the docstring should say: *"the provider is never mounted; `use_context` is used purely because it auto-subscribes to the `Observable` default value."*
9. **Drop the unused re-export**: `app_state.py:9` exports `state`, but no module imports `state` from `state.app_state` — every importer takes only `AppStateCtx` (`app_shell.py:17`, `screens/*.py`). Either remove `"state"` from `__all__` or make `state.app_state` the single canonical import path for the state singleton.
10. **Optional**: make `AppStateCtx` a module-private singleton with an explicit public alias so the "one context key" invariant is obvious.

---

## 6) Verdict

**API correctness: PASS.** Every flet API used in both files exists in the installed flet 1.0.4 (`create_context`, `use_context`, `observable`) and is used with the correct arity and semantics. No hallucinated APIs, no signature drift between the dataclass contract and the AppController's real method signatures, and the dataclass's function-valued defaults are provably not bound as methods.

**Design/behaviour: FAIL with 2 HIGH, 3 MEDIUM, 3 LOW findings.**

- `app_state.py` (9 lines) is **functionally correct but vestigial**: the context is never provided, so it scopes nothing and survives only because flet's `use_context` auto-subscribes to an `Observable` default value. The mechanism works; the abstraction and its docstring do not describe reality, and the `state` re-export is dead.
- `controller_ctx.py` (86 lines) is **correct on the happy path** (the provider/consumer wiring at `main.py:588` → `app_shell.py:721` genuinely resolves the same instance, and the closure-injection strategy works), but its **failure modes are silent** and its **default value is a process-wide mutable singleton** that AppShell writes into whenever the provider is absent — precisely the scenario the module docstring advertises as supported. On top of that, 3 of 22 fields are dead, one field is filed under the wrong owner/comment, and the guards that would have caught the failures are unreachable truthiness checks.

**Recommended order:** B1 + B2 (make the bus fail loudly and stop sharing a global mutable default) → B5 + B4 (make both modules describe what they actually do) → B3 (prune the dead contract) → B6/B7/B8 (cleanup).
