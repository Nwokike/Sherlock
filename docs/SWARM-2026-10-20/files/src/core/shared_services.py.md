# Audit — `src/core/shared_services.py`

**Auditor:** file-audit subagent · **Date:** 2026-10-22 · **Read-only:** no source file modified.
**Truth source:** `.venv\Lib\site-packages\flet` — **flet `1.0.4`** (`flet/version.py:16`), Python **3.14.7** (`.venv/pyvenv.cfg`).

---

## 1) File role

`src/core/shared_services.py` (99 lines) is the project's **shared flet `Service` registry**. It exports 5 public symbols:

```
mount_shared_services(page) -> None          # construct one of each, stash on the page
shared_haptics(page=None)    -> ft.HapticFeedback
shared_clipboard(page=None)  -> ft.Clipboard
shared_share(page=None)      -> ft.Share
shared_url_launcher(page=None)-> ft.UrlLauncher
```

The four services are the *transient, stateless* flet services — the ones a UI tends to construct inline per user action (haptic tick on every tap, clipboard write, share sheet, launch URL). All four are **stateless and carry no event handlers** (verified: `grep "    on_[a-z_]*:" flet/controls/services/{clipboard,share,url_launcher,haptic_feedback}.py` → **no matches** for any of the four; contrast `Connectivity.on_change` at `connectivity.py:63`).

Intent per the module docstring (`:1-14`): construct each service **once** per page and reuse it, so that per-click construction does not pile up duplicate service registrations in the page's service registry.

Call site: `src/main.py:506` — `mount_shared_services(self.page)` inside `AppController.init()`.

The module is small and API-clean (no hallucinated flet symbols), but **its central explanatory model is wrong for flet 1.0.4**, and the mount/lookup pair has a real correctness defect. Details below.

---

## 2) API verification (against installed flet 1.0.4)

### 2.1 The registration model — the ad_service agent's correction is the accurate one

The comment under audit at `src/core/shared_services.py:35-38`:

> *"Construction self-registers through `page._services` (see flet `controls/services/service.py`); the explicit `services.append` mirrors the existing FilePicker/Connectivity pattern in `AppController.init`."*

**Verified truth in installed flet 1.0.4:**

| Fact | Installed source | Verdict |
|---|---|---|
| Registration happens **in `Service.__post_init__`** | `flet/controls/services/service.py:39-54` — `super().__post_init__(ref)` then `page = context.page; page._services.register_service(self)` | ✅ **ad_service agent is right** |
| The registry is `page._services` | `flet/controls/page.py:714` — `_services: ServiceRegistry = field(default_factory=ServiceRegistry)`; `ServiceRegistry` is `@control("ServiceRegistry")` (`:92`) with `_services: list[Service]` (`:102`) | ✅ file's comment is right *about the registry* |
| `register_service` appends with **no dedup** and pushes a wire update | `page.py:120-152` — `self._services.append(service)`, then `self.__internal_update()` | ✅ file's comment is right |
| **`page.services` is NOT the registry** | `flet/controls/base_page.py:822-832` — `BasePage.services` is a property returning `self.__root_view().services`, i.e. the **root View's** list | ✅ **ad_service agent is right** |
| That View list is **never serialized** | `flet/controls/core/view.py:144` — `services: list[Service] = field(default_factory=list, metadata={"skip": True})`. `skip` fields are excluded from traversal/patching (`object_patch.py:1660`, `:1714`) and from live-control lookup (`session.py:381`) | ✅ **ad_service agent is right** — and this is the load-bearing fact |
| The live path is `Page._services` → `ServiceRegistry._services` | `Page._services` metadata `{}` (not skipped) and `ServiceRegistry._services` metadata `{}` (not skipped) → both serialized; each service in that list gets `_parent` set to the registry, so `service.page` resolves through registry → Page (`base_control.py:299-315`) | ✅ |

**Conclusion:** the file's comment is **half right**. "Construction self-registers through `page._services`" is accurate *as a description of the mechanism*, but the file then treats `page.services` as if it were that registry (`:57-58`), and it never mentions the two facts that actually decide behaviour: (a) the target page is `ft.context.page`, not the `page` argument; (b) `page.services` is a `skip: True` View list that only holds a **Python-side strong reference** — it puts nothing on the wire.

The ad_service agent's correction is **confirmed on both counts** and should be adopted verbatim.

### 2.2 Keep-alive via `sys.getrefcount` — confirmed, with a Python-version dependency

`page.py:228-247` `unregister_services()`:

```python
min_refs = 3 if sys.version_info >= (3, 14) else 4
self._services = [service for service in self._services
                  if sys.getrefcount(service) > min_refs]
```

Called after **every event**: `flet/messaging/session.py:566-570` (`after_event` → `self.page._services.unregister_services()`).

Measured in the installed venv (Python 3.14.7): a service referenced **only** by the registry has `getrefcount == 3` at the moment of the test → `3 > 3` is false → **pruned**. One external strong reference → 4 → kept.

**This is the mechanism the whole module depends on**, and it has a portability landmine (see BUG‑4).

### 2.3 Symbol-by-symbol check

| Line | Usage | Installed truth | Verdict |
|---|---|---|---|
| `:20` | `import flet as ft` | flet 1.0.4 | OK |
| `:32` | `page: ft.Page` | `ft.Page` exported (`flet/__init__.py`) | OK |
| `:41` | `ft.HapticFeedback` | `services/haptic_feedback.py`, `@control("HapticFeedback")`, subclasses `Service` | OK |
| `:42` | `ft.Clipboard` | `services/clipboard.py`, `@control("Clipboard")` | OK |
| `:43` | `ft.Share` | `services/share.py`, `@control("Share")` | OK |
| `:44` | `ft.UrlLauncher` | `services/url_launcher.py`, `@control("UrlLauncher")` | OK |
| `:52` | `factory()` — construct with no args | All four construct cleanly with no args (verified in venv) | OK |
| `:57-58` | `page.services` / `instance not in page.services` | `BasePage.services` → root **View** list, `skip: True`; `in` uses dataclass `__eq__` | ⚠️ **BUG‑3, BUG‑8** |
| `:66` | `from flet import context` | `flet.context` is the `Context` singleton (`flet/__init__.py:1245`); `context.page` raises `RuntimeError` when no page | OK (see BUG‑5 for the over-broad `except`) |
| `:82-99` | return annotations `ft.HapticFeedback` etc. | all four are `Service` subclasses | OK |

**No hallucinated flet API in this file.** Every symbol exists in installed flet 1.0.4 with the expected shape.

### 2.4 Refuted hypotheses (checked so they are not re-reported)

- ❌ *"`page.services` is where services are registered in flet 1.0.4"* — **false**. It is the root View's `skip: True` list (`base_page.py:822-832` → `core/view.py:144`). The registry is `page._services` (`page.py:714`).
- ❌ *"Handlers must be assigned in `init()` before construction, so `mount_shared_services` would be too late"* (`Service` docstring, `service.py:16-20`) — **does not apply to this file.** None of the four mounted services has an event handler (§1). The pattern *is* violated by a **consumer** — `src/main.py:499-501` sets `self.connectivity.on_change = ...` **after** `ft.Connectivity()` construction — but that is `Connectivity`, outside this file's four.
- ⚠️ *"`instance not in page.services` is an idempotency check"* — it is not. It is a **value-equality** membership test over a list that this module and `src/main.py` both write to, and the four classes compare equal to themselves (BUG‑3).
- ⚠️ *"Services accumulate forever in the registry"* — **false for 1.0.4**: the registry self-prunes unreferenced services after every event (§2.2). See BUG‑4.

---

## 3) Call census

`mount_shared_services` — **1 call site**

| Call site | Notes |
|---|---|
| `src/main.py:506` | inside `AppController.init()`; runs once per session (page is created per session) |

`shared_*` getters — **18 call sites across 8 modules**

| Getter | Call sites |
|---|---|
| `shared_haptics` | `src/app_shell.py:147-149`, `:198-200`; `src/screens/results_screen.py:381-383`, `:411-413`; `src/screens/home_screen.py:657-659`; `src/screens/onboarding_screen.py:137-139` |
| `shared_clipboard` | `src/app_shell.py:179-181` (explicit page); `src/main.py:303-305` (`self.page`); `src/components/profile_detail_dialog.py:179-181` (explicit page); `src/screens/settings_screen.py:1575-1577` (explicit page); `src/screens/home_screen.py:736-738` (**no page**) |
| `shared_share` | `src/app_shell.py:228-230` (**no page**) |
| `shared_url_launcher` | `src/components/profile_detail_dialog.py:167-169`, `:215-217`, `:499-501` (explicit page); `src/components/update_dialog.py:37-39` (explicit page); `src/screens/results_screen.py:350-353` (**no page**) |

Census observations:

1. **Two access styles coexist.** 13 sites pass an explicit page; **5 sites call with no argument** (`home_screen.py:738`, `app_shell.py:230`, `results_screen.py:353`, and the no-arg `shared_haptics()` at `app_shell.py:149`/`:200`, `home_screen.py:659`, `onboarding_screen.py:139`, `results_screen.py:381`/`:411` are page-less). The no-arg form resolves through `ft.context.page` (§2.1) — see BUG‑1/BUG‑2: the no-arg form is the one that silently degrades when the mount did not happen on the page that `context.page` points at.
2. **The mount is per-session, and `AppController.init()` runs once per session** — so the page-attribute stash is correctly per-page. No cross-session leakage through this module's own state.
3. **The mounted instances are not the ones flet's own client actions use.** `src/core/actions.py:25` builds `ft.OpenUrl(url)`, whose `__post_init__` calls flet's own per-page cache `shared_service(UrlLauncher)` (`flet/controls/client_action.py:24-42`) → that constructs and registers a **second `UrlLauncher`** on the same page. Used at `profile_detail_dialog.py:228`/`:511` and `update_dialog.py:90`/`:103`/`:117`. The module therefore does **not** actually achieve single-instance-per-page for `UrlLauncher` (see Improvements #6).
4. **A consumer uses a method that does not exist.** `src/main.py:305` — `await shared_clipboard(self.page).set_text(line)`. flet 1.0.4's `Clipboard` exposes `set`, `get`, `set_image`, `get_image`, `set_files`, `get_files` — **there is no `set_text`** (verified: `hasattr(ft.Clipboard, "set_text") → False`). The call raises `AttributeError`, swallowed by the surrounding `except Exception` at `src/main.py:308` → the "Scan summary copied" snack never appears and only a `logger.warning("Scan summary copy failed: %s", exc)` is emitted. Every other clipboard site uses the correct `set()`/`get()`. (Consumer bug, surfaced by this module's API surface — reported here because the module is the thing the consumer is calling.)

---

## 4) NEW bugs

### BUG‑1 (HIGH, latent in-repo / real as a contract) — `mount_shared_services(page)` mounts onto `ft.context.page`, not onto the `page` argument
`src/core/shared_services.py:32`, `:52`

`Service.__post_init__` resolves the target page from the ambient context, not from any argument (`service.py:50-54`):

```python
try:
    page = context.page
except RuntimeError:
    return
page._services.register_service(self)
```

`mount_shared_services(page)` never checks that `page is ft.context.page`. The `page` argument is used **only** for the `page.services` append (`:57-58`) and the attribute stash (`:61`). The instance that `factory()` produced was registered on the **context** page.

Two failure modes:

- **Wrong page.** If the passed page is not the context page, the service is registered on the context page's registry while being stashed on the passed page. `shared_*(passed_page)` then returns a service whose `_parent` chain points at a *different* page → `await svc.set(...)` (`base_control.py:447-467`) invokes the method on the wrong session.
- **Dead service.** If there is no context page at all (unit-test harness, early init, or a call from a non-Flet context), `Service.__post_init__` swallows the `RuntimeError` (`service.py:51-53`) and the service is **never registered and never given a `_parent`**. The `page.services.append()` at `:58` does **not** rescue it: `View.services` is `skip: True`, so the child is never traversed and never parented (`object_patch.py:1660`/`:1714`). Any method call then dies with `RuntimeError: Clipboard(N) Control must be added to the page first` (`base_control.py:461-464` via the parent walk at `:299-315`).

The in-repo call site (`src/main.py:506`, inside `main(page)` → `AppController.init()`) currently runs with `_context_page` set to the same page (`flet/app.py:365`), so this is **latent here** — but the function's public contract is wrong, and a future call from a different page, a background thread, or a test would break silently.

**Fix:** make the target explicit and assert it, e.g.

```python
if ft.context.page is not page:      # ft.context.page raises RuntimeError outside a session
    raise RuntimeError("mount_shared_services must be called with ft.context.page")
```

or register explicitly against the page you were handed instead of relying on the ambient context.

---

### BUG‑2 (MEDIUM) — the fallback path returns a service that is either **dead** or a **per-call duplicate**, contradicting the module's stated purpose
`src/core/shared_services.py:73-79`, and the promise at `:11-13`

```python
def _shared(page, key, factory):
    resolved = page if page is not None else _current_page()
    if resolved is not None:
        instance = getattr(resolved, _ATTR_NAMES[key], None)
        if instance is not None:
            return instance
    return factory()
```

The fallback is reached whenever the resolved page has no stashed attribute — i.e. **the mount did not happen on that page**. Two distinct bad outcomes:

- **No context page** → `factory()` returns an unregistered, parentless service (§2.1 / BUG‑1). Every method call raises `RuntimeError: ... Control must be added to the page first`. The docstring at `:12-13` promises *"falling back to inline construction otherwise (test harness without a live page, or callers that run before init). Fallback preserves today's behavior exactly."* — "exactly" is wrong: the old inline behaviour produced a *registered* service whenever a page context existed, whereas this fallback produces an unregistered one.
- **Context page exists but is a different page** → `factory()` constructs a service which **auto-registers on the context page's registry** (`service.py:54`). Because the fallback never stashes the instance, **every call creates and registers a new service** — precisely the per-call accumulation the module was written to prevent, and the registry then prunes it again on the next event (§2.2). Net: churn, not a leak, but the opposite of the module's intent, and it silently returns *different objects* on consecutive calls.

**Fix:** the fallback should be explicit about failure rather than silently returning a non-functional or duplicating object — e.g. raise a clear error, or cache the fallback instance on the resolved page so the "one per page" invariant holds even when the mount was skipped.

---

### BUG‑3 (MEDIUM) — `instance not in page.services` is a **value-equality** test, not an identity test
`src/core/shared_services.py:57`

`Service` subclasses are dataclasses (`@dataclass(kw_only=True)` on `BaseControl`, `base_control.py:186`; `@control(...)` re-applies dataclass behaviour), so `__eq__` compares **field values**. `_i` is `compare=False` (`base_control.py:212`) and none of the four services declares a field of its own, so **any two instances of the same service class compare equal**. Verified in the venv:

```
Clipboard() == Clipboard()          -> True
Clipboard() in [Clipboard()]         -> True
HapticFeedback() == HapticFeedback()-> True
```

Consequence: if a same-type service is already in the root View's list, the append at `:58` is **silently skipped** — even though the instance being appended is a different object. Today only `FilePicker` and `Connectivity` are in that list (`src/main.py:492`, `:501`), so the check happens to evaluate `True` and the bug is dormant; it becomes live the moment anyone appends a `Clipboard`/`Share`/`UrlLauncher`/`HapticFeedback` to `page.services`.

Also, the check is not an idempotency guard at all (the real one is `getattr(page, attr, None)` at `:48-50`).

**Fix:** `if not any(s is instance for s in page.services):` — or drop the membership test entirely, since `:48-50` already provides idempotency and the View list is not the registry.

---

### BUG‑4 (MEDIUM) — the module's stated premise is inaccurate for 1.0.4, and the keep-alive it relies on is Python-version-dependent
`src/core/shared_services.py:3-6` (docstring) and `:57-61`

The docstring says:

> *"Every `Service` construction registers a new entry on the page (`page._services.register_service` appends + pushes a wire update, no dedup). Constructing `HapticFeedback`/`Clipboard`/`Share`/`UrlLauncher` inline per-click therefore accumulates duplicate services over a long session."*

The first sentence is **accurate** (`page.py:120-152`). The second is **not** for flet 1.0.4: `session.py:566-570` calls `page._services.unregister_services()` after **every event**, and `page.py:236-243` prunes any service whose `sys.getrefcount` is not above the threshold. A service referenced only by the registry is pruned. So inline per-click construction does **not** accumulate — it produces a **register → prune churn pair** (two wire updates per click) instead. The module's justification is built on a pre-1.0 model.

The flip side is the real hazard: **the mounted services survive only because two external strong references exist** — the `setattr(page, attr, instance)` at `:61` *and* the `page.services.append(instance)` at `:58`. `page.py:238` sets `min_refs = 3 if sys.version_info >= (3, 14) else 4`:

- On **Python 3.14+** (this venv): one external reference is enough (refcount 4 > 3). Both references are effectively redundant.
- On **Python ≤ 3.13**: `min_refs = 4`, so one external reference gives refcount 4 → `4 > 4` is false → **pruned**; two external references give 5 → kept.

So the seemingly redundant `page.services.append` at `:58` is **load-bearing on Python ≤ 3.13**, and any future "cleanup" that removes it (or that removes the `setattr`, or that swaps `setattr` for a `WeakKeyDictionary`) will **silently break the shared services on Python 3.13 and earlier** — they would be pruned from the registry after the first event and every call would fail with an unknown-service error.

**Fix:** do not rely on an implicit refcount heuristic. Either (a) document the dual-reference requirement explicitly and add a comment on `:58`, or (b) hold the services in a `WeakKeyDictionary` keyed by page — but note that a `WeakKeyDictionary` value holds the service strongly, giving exactly one external reference, which is **not** enough on Python ≤ 3.13. The robust option is to keep both references and comment why.

---

### BUG‑5 (LOW/MEDIUM) — broad `except Exception` + `logger.debug` turns a failed mount into a silent per-call factory
`src/core/shared_services.py:51-60`, `:65-70`

```python
except Exception as exc:
    logger.debug("Shared service %s unavailable: %s", key, exc)
    continue
...
except Exception as exc:
    logger.debug("Shared service %s mount skipped: %s", key, exc)
...
except Exception:
    return None
```

Three problems:

1. **Invisible.** The repo's root logger runs at `INFO` (`src/main.py:2397` `logging.basicConfig(level=logging.INFO)`), so `logger.debug` is **never shown** — neither in the terminal nor in the in-app terminal. A service that failed to mount is indistinguishable from one that mounted.
2. **Degradation is silent and self-amplifying.** If `ft.Share()` (or any factory) raises, the mount skips it; every later `shared_share()` then takes the `_shared` fallback (`:79`) and returns a **different, unregistered** service each time (BUG‑2). The user sees a share sheet that never opens, with no diagnostic.
3. **Over-broad catches.** `ft.context.page` raises `RuntimeError` specifically (`context.py:62-72`); `BasePage.services` raises `RuntimeError("views list is empty.")` (`base_page.py:300-301`). Catching `Exception` also swallows genuine programming errors (e.g. a renamed flet symbol) as "service unavailable".

**Fix:** catch `RuntimeError` specifically, log at `warning` with `exc_info=True`, and make the failure visible to the user path (or fail loudly).

---

### BUG‑6 (LOW) — logger name breaks the repo's convention and the in-app log pipeline
`src/core/shared_services.py:22`

```python
logger = logging.getLogger("SharedServices")
```

Every other module in `src/core/` uses `logging.getLogger(__name__)` — `core/notify.py:15`, `core/tasks.py:15`, `core/geo_utils.py:9`. `src/core/logger_handler.py` filters and mutes loggers **by name** (`logger_handler.py:99-112` walks a name list and calls `logging.getLogger(name).setLevel(...)`), so a hand-written name is neither captured by the repo's conventions nor silenceable through the existing mechanism.

**Fix:** `logger = logging.getLogger(__name__)`.

---

### BUG‑7 (LOW) — stale flet version in the module docstring
`src/core/shared_services.py:1`

> `"""Shared page services — mount once, reuse everywhere (flet 1.0.1).`

Installed flet is **1.0.4** (`flet/version.py:16`). Confirmed stale (the known-context flag is accurate). The same docstring also cites `page._services.register_service` (`:4`) in a way that reads as if it were the only registration path — §2.1 shows there are two distinct containers and only one of them is live.

---

### BUG‑8 (LOW) — the mount's explanatory comment points at the wrong container
`src/core/shared_services.py:35-38`

The comment justifies the `services.append` at `:58` as *"mirrors the existing FilePicker/Connectivity pattern in `AppController.init`"*. That pattern (`src/main.py:492`, `:501`) exists, but in flet 1.0.4 it is **not** a registration step: `View.services` is `metadata={"skip": True}` (`core/view.py:144`) and never reaches the client. Both the FilePicker and the Connectivity land on the wire solely because their **construction** auto-registered them into `page._services`. The comment therefore teaches the wrong mental model to the next maintainer — and, per BUG‑4, the append's real (and version-critical) value is as a **keep-alive reference**, which the comment does not mention.

**Fix:** rewrite the comment to state the two real facts — construction registers into `ft.context.page._services`, and the extra Python references keep the instance alive against `unregister_services()`' refcount pruning.

---

## 5) Improvements (concrete, minimal)

**Dead code / unused exports**
- **No unused imports, no unused exports.** `logging` and `ft` are both used; all five public symbols have callers (§3); `_ATTR_NAMES`, `_current_page`, `_shared` are all used.
- `src/core/shared_services.py:57` — the `instance not in page.services` membership test is **effectively dead**: the list it scans is populated only with `FilePicker`/`Connectivity` (`src/main.py:492`, `:501`), never with one of the four service types, so the check is always `True`. It is also semantically wrong (BUG‑3). Delete it, or replace it with an identity test.
- `src/core/shared_services.py:56-60` — the `try/except` around `page.services.append` is near-dead: `BasePage.services` only raises when `page.views` is empty, and the app already guards that condition (`src/main.py:576`). It can be collapsed to a plain append, or dropped entirely.
- `src/core/shared_services.py:24-29` + `:40-45` — the four service kinds are enumerated **twice** (once as `_ATTR_NAMES` keys, once as the `specs` tuple). A single `dict[str, type[Service]]` drives both and removes the possibility of the two lists drifting apart.

**Fix list (ordered by value)**

1. **Fix the mount target (BUG‑1).** Assert `ft.context.page is page` inside `mount_shared_services`, or register explicitly against the handed-in page. Without this the module's contract is a lie and the no-arg getters (5 call sites) can return a service bound to the wrong page or no page at all.
2. **Make the failure mode honest (BUG‑2).** Replace the silent `factory()` fallback with either a raised error or a cached-per-page fallback that preserves the one-instance invariant.
3. **Fix the equality test (BUG‑3)** → `any(s is instance for s in page.services)`, or remove the test.
4. **Document the refcount keep-alive (BUG‑4)** — comment `:57-61` to state that **two** external references are required for survival on Python ≤ 3.13 (`page.py:238`), so the next cleanup does not break the services. Then correct the docstring at `:3-6`: in 1.0.4 inline construction *churns* (register → prune per event) rather than accumulating.
5. **Narrow the exception handling and raise the log level (BUG‑5)** — catch `RuntimeError`, log at `warning` with `exc_info=True`.
6. **Reconcile with flet's own per-page service cache.** flet already ships exactly this mechanism for client actions: `flet/controls/client_action.py:24-42` `shared_service(service_type)`, a `WeakKeyDictionary[page, dict[type, Service]]`. It is not exported at top level (`hasattr(ft, "shared_service") → False`) and is documented as *"Internal, but shared"*, so using it is a private-API dependency — but it is the only way to get a genuinely single instance per page **including** the ones flet's client actions create. Today `src/core/actions.py:25` (`ft.OpenUrl`) creates a **second** `UrlLauncher` on the page, so the app really does carry two. Either route `core/actions.py` through this module, or accept and document the duplication.
7. **Fix the logger name (BUG‑6)** → `logging.getLogger(__name__)`.
8. **Fix the version + registration comment (BUG‑7, BUG‑8)** → `flet 1.0.4`; describe `ft.context.page._services` as the registry and `page.services` as a `skip: True` View list.
9. **Fix the consumer bug surfaced by the census (§3.4)** — `src/main.py:305` calls `shared_clipboard(self.page).set_text(line)`; flet 1.0.4's `Clipboard` has no `set_text`. Use `.set(line)` like every other site.
10. **Optional: type the registry.** `_shared(page, key, factory)` has no annotation on `key`/`factory`; `factory: Callable[[], Service]` and `key: Literal["haptics","clipboard","share","url_launcher"]` would make the `_ATTR_NAMES`/`specs` drift impossible.

**Verified-safe (no change needed)**
- All four service classes construct with no arguments and are valid `Service` subclasses.
- `from flet import context` / `ft.context.page` are correct for 1.0.4 (`flet/__init__.py:1245`); `context.page` raises `RuntimeError` outside a session, which `_current_page` handles.
- `setattr(page, "shared_haptics", instance)` is legal on the `Page` dataclass (`BaseControl` has no `__slots__` — verified `BaseControl.__slots__ is None`) and is Python-only state: it is not a dataclass field, so it is never serialized and never pollutes the wire.
- `from __future__ import annotations` is unnecessary on Python 3.14 but harmless.
- The four services carry **no event handlers**, so the `Service`-docstring rule "set handlers in `init()`" does not constrain this module (see §2.4).

---

## 6) Verdict

**Severity: MEDIUM. No hallucinated flet API, but the module's explanatory model is wrong for flet 1.0.4 and the mount/lookup pair has a real correctness defect.**

- ✅ **API-clean.** `ft.HapticFeedback`, `ft.Clipboard`, `ft.Share`, `ft.UrlLauncher`, `ft.Page`, `ft.context` all exist in installed flet **1.0.4** with the expected signatures; all four services construct with no arguments. No 0.x-only API, no invented methods.
- ✅ **The ad_service agent's registration-model correction is confirmed on both points:** registration happens in `Service.__post_init__` → `context.page._services.register_service(self)` (`service.py:39-54`), and `page.services` is the **root View's** `skip: True` list (`base_page.py:822-832` → `core/view.py:144`), not the registry. Keep-alive is `sys.getrefcount > min_refs` (`page.py:228-247`), with `min_refs = 3` on Python ≥ 3.14 and `4` on older interpreters.
- ❌ **Three real defects:** BUG‑1 (the mount targets `ft.context.page`, not the `page` argument → wrong-page or dead service), BUG‑2 (the fallback returns a dead or per-call-duplicate service, defeating the module's purpose), BUG‑3 (`not in page.services` is value equality, so a same-type service blocks the append).
- ⚠️ **The docstring's premise is stale (BUG‑4):** in flet 1.0.4 the registry *self-prunes* unreferenced services after every event, so inline construction churns rather than accumulates — and the mounted services survive only because of an **implicit, Python-version-dependent refcount threshold** that depends on the `page.services.append` at `:58` being kept.
- ⚠️ **The module does not achieve its headline goal for `UrlLauncher`:** flet's own `shared_service()` cache (used by `ft.OpenUrl` in `src/core/actions.py:25`) registers a second instance on the same page.
- 🧹 **Minor:** invisible `logger.debug` failure paths and over-broad `except Exception` (BUG‑5), non-conventional logger name (BUG‑6), stale `flet 1.0.1` version string (BUG‑7), a comment that teaches the wrong container (BUG‑8), and one consumer calling the non-existent `Clipboard.set_text` (`src/main.py:305`, §3.4).

**Recommendation:** fix the mount target (BUG‑1) and the fallback semantics (BUG‑2) — those two are the only ones that can produce a user-visible failure — then fix the equality test (BUG‑3), then correct the docstring/comment and the refcount keep-alive note (BUG‑4, BUG‑7, BUG‑8) so the next maintainer does not "clean up" the load-bearing append. No call-site changes are required in `src/` **except** the one-shot `Clipboard.set_text` → `set` fix at `src/main.py:305`.

**Files referenced**
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/core/shared_services.py`
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/services/service.py` (lines 11-54)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/page.py` (lines 92-152, 228-247, 714-730)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/base_page.py` (lines 282-302, 822-832)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/core/view.py` (line 144)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/base_control.py` (lines 186-282, 299-315, 447-467)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/client_action.py` (lines 10-42)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/context.py` (lines 47-72)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/object_patch.py` (lines 1660, 1714)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/messaging/session.py` (lines 555-571)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/app.py` (line 365)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/flet/controls/services/{clipboard,share,url_launcher,haptic_feedback,connectivity}.py`
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/main.py` (lines 305, 492, 499-506, 576, 2397)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/core/actions.py` (lines 20-28)
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/core/logger_handler.py` (lines 95-112)
