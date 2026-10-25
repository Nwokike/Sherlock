# Audit — `src/core/actions.py`

**Auditor:** file-audit subagent · **Date:** 2026-10-22 · **Read-only:** no source file modified (only this report written).
**Truth source:** `.venv\Lib\site-packages\flet` — **flet `1.0.4`**, Python **3.14.7** (`.venv/pyvenv.cfg`).

---

## 1) File role

`src/core/actions.py` (29 lines) is a **one-function adapter** between Sherlock and flet's *client-action* mechanism. It exports exactly **one** public symbol:

```
open_url_action(url: str) -> ft.OpenUrl | None
```

Purpose (docstring `:1-13`): build an `ft.OpenUrl` client action bound to the live page, so the URL opens **on the client inside the user's gesture** (bypassing browser popup blockers). When there is no live page context, return `None` so the caller falls back to the slower Python `UrlLauncher` round-trip.

The contract is a **sentinel contract**: `None` means "no action", and every caller switches its entire `on_click` handler on that truthiness. That single fact drives most of the findings below.

**Dependency direction:** `core.actions` → `flet` only. No imports from `core.*`, no cycles. The deferred `from core.actions import open_url_action` inside functions at the call sites is a caller-side choice, not this file's concern.

---

## 2) API verification (against installed flet 1.0.4)

### 2.1 `ft.OpenUrl` is real and correctly used — **no hallucination**

| Fact | Installed source | Verdict |
|---|---|---|
| `ft.OpenUrl` exists | `flet/controls/services/url_launcher.py:188` — `@dataclass class OpenUrl(ClientAction)`; exported in that module's `__all__` (`:10-16`) and re-exported top-level (`hasattr(ft,'OpenUrl')` → `True`) | ✅ |
| `OpenUrl` is a **dataclass** with `url: str = action_field()` and `target: Optional[...] = action_field(None)` | `url_launcher.py:205`, `:210` | ✅ |
| `ft.OpenUrl(url)` positional binds `url` correctly | `url_launcher.py:205` — first field | ✅ |
| Construction binds to the page's service | `url_launcher.py:217-222` — `__post_init__` → `self._bind(shared_service(UrlLauncher), "launch_url", {"url": Url(url=self.url, target=self.target)})` | ✅ |
| Outside a page context it raises **`RuntimeError`** | `flet/controls/client_action.py:36` → `context.page` → `flet/controls/context.py:62-68` — *"The context is not associated with any page. Make sure you are accessing ft.context.page inside a Flet app callback."* | ✅ **docstring `:4-5` is accurate** |

**Live confirmation (no page context):**
```
NO-PAGE raised: RuntimeError | The context is not associated with any page. ...
```

### 2.2 The shared_services agent's claim is **REFUTED**

> Claim (from the shared_services agent): `ft.OpenUrl` at `:25` "uses flet's own `shared_service()` for `ft.OpenUrl`, which registers a **SECOND UrlLauncher per call** (not the shared_services singleton)."

**Measured against installed flet 1.0.4 with a real `ft.Page` and the context var set:**

```
service_ids: 9 9
same _service object: True
registered services: 1 ['UrlLauncher']
shared_service() is a1._service: True
helper in page -> OpenUrl svc_id 9
registered after helper: 1
```

**The claim is false.** flet's `shared_service()` (`client_action.py:24-42`) is a **per-page singleton cache**:

```python
_shared_services: "WeakKeyDictionary[Any, dict[type, Service]]" = WeakKeyDictionary()
...
page = context.page
services = _shared_services.setdefault(page, {})
service = services.get(service_type)
if service is None:
    service = service_type()
    services[service_type] = service
return service
```

Repeated `ft.OpenUrl(...)` constructions on the same page reuse **one** `UrlLauncher` instance with **one** `service_id`, and register **one** service on the page. `open_url_action` (`actions.py:25`) adds **zero** extra services beyond that single shared one. The `client_action.py:31-34` docstring states the intent explicitly: *"Instantiating a service per action would register a service per action with the client for no benefit."*

**No fix is needed for the alleged per-call duplication. This finding should not be actioned.**

### 2.3 A *real* duplicate `UrlLauncher` exists — but it is cross-file, and `actions.py` is the second registrant

`src/core/shared_services.py:40-58` (`mount_shared_services`) constructs its **own** `ft.UrlLauncher()` and stashes it as `page.shared_url_launcher`. flet's `shared_service()` cache is a **separate registry** from the project's `shared_url_launcher` attribute. On a page where `mount_shared_services(page)` has run (called from `src/main.py:506` per the sibling audit) **and** an `ft.OpenUrl` is constructed, the page ends up with **two** `UrlLauncher` service instances registered — one per lifecycle.

- Not a defect *in* `actions.py`; the file neither causes nor documents it.
- Consequence for this file's callers: the client-side path (`ft.OpenUrl`) and the Python fallback path (`core.shared_services.shared_url_launcher(page).launch_url(...)`, used at `src/components/profile_detail_dialog.py:216`) drive **two different** service instances. The fallback still works; the duplication is wire-level noise, not a functional break.
- Worth one cross-file note to the shared_services owner.

### 2.4 `open_url_action` is not a pure factory — it mutates the page

`actions.py:25` → `shared_service(UrlLauncher)` → on first use `service_type()` → `Service.__post_init__` (`flet/controls/services/service.py:39-54`) → `page._services.register_service(self)`.

So calling `open_url_action()` **registers a `UrlLauncher` service on the page** as a side effect, even if the returned action is never rendered (e.g. the caller takes a different branch). Verified non-leaking (`registered after helper: 1` — the per-page cache prevents accumulation), but the side effect is undocumented at `actions.py:20-29`.

Related: the action pins `service_id` at **construction** time (`client_action.py:115-118`). An `OpenUrl` built under page A and attached to a control on page B would address page A's service. Not reachable in the current callers (each builds and renders in the same page context), but it is a latent trap for future reuse of a cached action.

### 2.5 `except RuntimeError, AttributeError:` — PEP 758, legal here

`actions.py:26` uses the **unparenthesized multi-exception** form.

- **Not a syntax error for this project**: PEP 758 (Python 3.14+) allows `except A, B:` without parentheses. `pyproject.toml` pins `requires-python = ">=3.14"`; the venv is 3.14.7; `.venv/Scripts/python.exe -m py_compile src/core/actions.py` → exit **0**.
- **Ruff is clean**: `ruff check src/core/actions.py` → *"All checks passed!"*; `ruff format --diff` → *"1 file already formatted"*. (Ruff's `E`/`UP`/`B`/`BLE`/`TRY` selections do not flag this form.)
- **Portability landmine**: the identical source is a `SyntaxError` on Python ≤ 3.13. Harmless while the floor is 3.14, but it is a non-obvious constraint. Fixing B2 below (narrowing the `except`) removes the landmine for free.

---

## 3) Call census

**Public surface:** one symbol, `open_url_action`. There is **no `__all__`**, so the module also exports the imported name `ft` (and `annotations`) into `core.actions`' namespace — cosmetic, but an `__all__` would make the surface explicit.

**Call sites — 4 import statements, 5 call expressions, all live:**

| # | Call site | Imported at | Called at | URL argument |
|---|---|---|---|---|
| 1 | `src/components/update_dialog.py` | `:87` | `:90` | `PLAY_STORE_URL` (Android branch) |
| 2 | `src/components/update_dialog.py` | `:87` | `:103` | `github_url` (Android "Direct APK") |
| 3 | `src/components/update_dialog.py` | `:87` | `:117` | `github_url` (non-Android "Download from GitHub") |
| 4 | `src/components/profile_detail_dialog.py` | `:226` | `:228` | `platform_url` (platform card) |
| 5 | `src/components/profile_detail_dialog.py` | `:509` | `:511` | `profile_url` (e-mail dossier) |

**Doc-comment reference only:** `src/components/update_dialog.py:52`.

**Test coverage: ZERO.** `grep -rn "core.actions\|actions" tests/` → **no matches** anywhere under `tests/`. The module's stated raison d'être (docstring `:5` — *"raise RuntimeError outside a running Flet app — e.g. in the unit-test harness"*) is not exercised by any test, and the fallback contract it exists to provide is unpinned.

**The caller idiom is identical at every site** (e.g. `update_dialog.py:92-100`):

```python
play_action = open_url_action(PLAY_STORE_URL)
ft.FilledButton(
    ...,
    action=play_action,
    on_click=((lambda e: page.pop_dialog()) if play_action
              else lambda e, u=PLAY_STORE_URL: _pop_and_launch(page, u)),
)
```

Two consequences that the audit turns on:
- `action=None` is passed to `ft.Button(action=None)` when the helper returns `None` — legal, and the button still works via `on_click`.
- The **entire user-visible behaviour** (instant client-side open vs. Python round-trip open) is switched by the truthiness of the helper's return value. A `None` caused by a *failure* is therefore indistinguishable from a `None` caused by *no context* — for the caller and for the user.

---

## 4) Bugs (severity-ordered)

### B1 — HIGH · Silent masking of genuine failures (`actions.py:26`)

The `except RuntimeError` arm is **not** limited to the page-context `RuntimeError` that the docstring promises to catch. It swallows **any** `RuntimeError` raised anywhere in `ft.OpenUrl(...)` construction, including a failed `page._services.register_service(self)` — whose `__internal_update()` path re-raises after restoring state (`flet/controls/page.py:142-152`).

**Proved live** (monkeypatched `register_service` on a real page, then called `open_url_action`):

```
RuntimeError -> helper returned None (SILENTLY SWALLOWED)
AttributeError -> helper returned None (SILENTLY SWALLOWED)
TypeError -> PROPAGATED TypeError bad type
```

So a real service-registration failure makes the app **silently degrade** from "instant client-side open" to "Python round-trip open", with **no log line, no snackbar, and no exception**. The user gets a slower, popup-blockable open; the developer gets nothing.

This directly contradicts the file's own docstring at `:11-12`:

> *"Only the specific page-context RuntimeError is caught — real problems stay loud (owner rule: no swallowing)."*

**The code does not do what the docstring says.** The docstring is the specification, and the implementation violates it.

### B2 — MEDIUM · Dead and hazardous `AttributeError` arm (`actions.py:26`)

In flet 1.0.4 there is **no** reachable path in `ft.OpenUrl(url)` → `shared_service(UrlLauncher)` → `Service.__post_init__` → `register_service` that raises `AttributeError`; the context failure raises `RuntimeError` (`context.py:64`). The arm is therefore **effectively unreachable dead code** — while being the broadest net in the function. Its only effect today is to mask any attribute-lookup defect introduced by a future flet release, converting a loud crash into a silent UX downgrade (per B1's proof). **Delete it.**

### B3 — MEDIUM · Undocumented side effect on the page (`actions.py:25`)

`open_url_action()` registers a `UrlLauncher` service on the page as a side effect of construction (§2.4), and pins `service_id` to the constructing page. The docstring describes a pure "builder"; the implementation mutates page state. Not a leak (verified: one service total), but it should be documented, and callers must not cache an action across pages.

### B4 — LOW · No diagnostics anywhere in the module (`actions.py:1-29`)

No `logging` import, no logger, no log emission — while the sibling module `src/core/shared_services.py:22` establishes the house pattern (`logger = logging.getLogger("SharedServices")`, used at `:53-55` and `:59-60` for exactly this class of swallowed failure). A swallowed exception should leave a trace.

### B5 — LOW · Weak input validation (`actions.py:22`)

`if not url: return None` accepts whitespace-only strings (`"   "`), producing an action that opens an invalid URL client-side, while the fallback path for the same input would surface an error snackbar — **the two paths disagree about bad input**. `None` is also accepted silently despite the `url: str` annotation.

### B6 — LOW · Web `target` never set (`actions.py:25`)

`ft.OpenUrl(url)` is constructed with no `target`, which defaults to `None` (`url_launcher.py:210`); the field is documented as *"Web-only; ignored on other platforms"* (`url_launcher.py:214`). On a web build, a link with no target defaults to the **same browsing context**, i.e. the Flet SPA navigates away to the external URL. The caller pops the dialog in `on_click`, so the user is left on the external site with the app gone. `ft.UrlTarget.BLANK` (`flet/controls/types.py:127`) is the new-tab choice.

**Caveat — partially unverified:** the flet Dart client source is **not** shipped in `.venv\Lib\site-packages\flutter` (only `flet_ads` is present there), so the exact web mapping could not be confirmed against installed deps. Flagged for a real-browser check **if this project ships a web build**; impact is nil for the Android/desktop targets that `pyproject.toml` configures.

### B7 — LOW · `from __future__ import annotations` is redundant (`actions.py:15`)

Harmless and defensively fine, but on Python 3.14 `ft.OpenUrl | None` is valid at runtime anyway (`ft.OpenUrl` is a real class, PEP 604 since 3.10). Not a bug — noted for completeness.

### Dead-code census (explicit)

- No unreachable statements, no unused imports, no unused locals in the file. `ft` is used at `:20` and `:25`; `annotations` is consumed by the `:20` annotation.
- The **only** dead path is the `AttributeError` arm of `:26` (B2).
- The `except RuntimeError` arm is **not** dead, but it is **over-broad** (B1).

---

## 5) Verdict

**Functionally sound, no hallucinated API, but with one real correctness defect and one real dead branch.**

- ✅ **No hallucinated flet API.** `ft.OpenUrl` exists in flet 1.0.4 (`url_launcher.py:188`), is exported top-level, and `ft.OpenUrl(url)` uses its first positional field correctly. The docstring's mechanism description (`shared_service()` → `ft.context.page` → `RuntimeError`) is **accurate**.
- ❌ **The shared_services agent's "second UrlLauncher per call" claim is refuted** by live measurement against installed flet: `service_ids: 9 9`, `same _service object: True`, `registered services: 1`. flet's `shared_service()` is a per-page singleton cache (`client_action.py:13-42`). **Do not "fix" this.**
- ⚠️ **A different duplicate `UrlLauncher` does exist** — the project's `core.shared_services.shared_url_launcher` vs flet's `shared_service` cache are two independent lifecycles on the same page. Cross-file note for the `shared_services` owner; not an `actions.py` defect.
- 🔴 **B1 is the finding that matters**: the broad `except RuntimeError` silently converts real failures into a silent UX downgrade, directly contradicting the file's own "no swallowing" docstring at `:11-12`. Combined with **B2** (unreachable `AttributeError` arm), the `except` clause is both too wide and partly dead.
- ⚠️ **Zero test coverage** for a module whose entire purpose is to define a fallback contract, with 5 live call sites depending on the `None` sentinel's meaning.

### Recommended concrete changes (all in this one file)

1. **Make the docstring true — pre-check the page instead of catching broad exceptions.** This is the single highest-value change (~4 lines) and removes B1, B2, B6/PEP-758 landmine in one stroke:

   ```python
   try:
       ft.context.page          # raises RuntimeError only when there is no live app
   except RuntimeError:
       return None
   return ft.OpenUrl(url)       # any real failure now propagates loudly
   ```

   (Caveat: `ft.context.page` raising is the *only* intended fallback trigger; if the project later wants a fallback for "service registration failed", that must be a **separate, explicit, logged** decision — not a side effect of a broad `except`.)

2. **Add a module logger** and log any deliberately swallowed condition at `warning`/`debug`, matching `src/core/shared_services.py:22`:
   ```python
   logger = logging.getLogger("Core.Actions")
   ```

3. **Add `__all__ = ["open_url_action"]`** to make the public surface explicit and stop `ft` leaking into `core.actions`' namespace.

4. **Normalise the URL**: `url = (url or "").strip()` before the emptiness check, so both the action path and the fallback path agree on what "no URL" means (B5).

5. **Add tests** (none exist) that pin the contract:
   - no page context → `open_url_action("https://example.com") is None`;
   - with a page context → returns an `ft.OpenUrl` whose `service_id == shared_service(UrlLauncher)._i`;
   - **regression guard**: `len(page._services._services)` stays `1` after N calls — this is the test that would have caught (and permanently refuted) the shared_services agent's claim.

6. **Consider `target=ft.UrlTarget.BLANK`** if a web build is shipped (B6), after confirming the Dart-side mapping.

**Not recommended:** broadening the `except`, keeping the `AttributeError` arm, or "fixing" the alleged per-call `UrlLauncher` duplication — all three are either wrong or actively harmful.
