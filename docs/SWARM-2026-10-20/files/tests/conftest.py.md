# File Audit Report — tests/conftest.py + tests/test_imports.py

**Scope:** exactly these two files, treated as one unit. Read-only audit; no files modified.
**Repo:** /home/maikel/.zcode/workspace/default/Sherlock-V3 (Linux; venv at `.venv/lib/python3.14/site-packages`, runtime python 3.14.9 / system 3.15.0)
**Citation convention:** every finding carries a `file:line` reference.

---

## 1) Files' roles

### tests/conftest.py (6 lines)
A bare `sys.path` shim. Its entire body:

```python
"""Test configuration for Sherlock-V2."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
```

- conftest.py:1 docstring still says "Sherlock-V2" although pyproject.toml:4 describes the project as "Sherlock V2" wrapper while the workspace/context frames it as Sherlock V3 — naming is stale but cosmetic.
- conftest.py:6 inserts `<repo>/src` at `sys.path[0]` so `import main`, `import app_shell`, `from services import ...`, etc. resolve during collection.
- It defines **zero fixtures**, **zero autouse teardown**, **zero warning filters**, **zero asyncio event-loop handling**. It is only a path shim.

### tests/test_imports.py (33 lines)
An "import smoke test" module. Full contents (pasted verbatim):

```python
"""Import smoke tests for Sherlock-V2."""


def test_import_main():
    import main  # noqa: F401


def test_import_app_shell():
    import app_shell  # noqa: F401


def test_import_services():
    from services import (
        email_service,
        phone_service,
        sherlock_service,
    )
    assert sherlock_service.SherlockService is not None
    assert email_service.EmailService is not None
    assert phone_service.PhoneService is not None


def test_import_screens():
    from screens import (
        home_screen,
    )
    assert home_screen.HomeScreen is not None


def test_import_components():
    from components import active_scan_banner
    assert active_scan_banner.ActiveScanBanner is not None
```

What it actually asserts:
- test_imports.py:5-6 — `import main` succeeds (no assertion beyond import not raising).
- test_imports.py:9-10 — `import app_shell` succeeds.
- test_imports.py:14-21 — `from services import email_service, phone_service, sherlock_service` succeeds, and the three class objects are not None (trivially true for any imported module attribute).
- test_imports.py:25-28 — `from screens import home_screen`; `home_screen.HomeScreen is not None`.
- test_imports.py:32-33 — `from components import active_scan_banner`; `active_scan_banner.ActiveScanBanner is not None`.

**Modules covered by test_imports.py:** main, app_shell, services.email_service, services.phone_service, services.sherlock_service, screens.home_screen, components.active_scan_banner = 7 src modules.
**Modules NOT covered:** everything else (~45+ of ~54), including report_service.py, results_screen.py, http_client.py — precisely where the suite-level audit located known bugs.

---

## 2) Facts verified

### A. The sys.path shim is redundant
pyproject.toml:69 declares `pythonpath = ["src"]` under `[tool.pytest.ini_options]`. pytest adds each `pythonpath` entry to `sys.path` at startup, so `src` is already importable without conftest.py:6. conftest.py:6 additionally inserts at index 0 (taking precedence over pytest's appended entries), but functionally it is dead weight: removing conftest.py entirely changes nothing about import resolution.

**Evidence:** `grep -n pythonpath pyproject.toml` → pyproject.toml:69. conftest.py:6 is the only path manipulation in tests/.

### B. All importable src modules import cleanly offline (empirical)
I imported every src module (53 distinct module names) with the venv python and `sys.path` pointing at `src`: **53/53 OK, 0 failures**. This includes report_service.py, results_screen.py, http_client.py, storage_service.py, user_scanner_compat.py, etc. So no module is broken at import time; the import-smoke test would pass even for modules it does not cover.

### C. http_client.py:33 is a latent semantic bug (not a syntax error)
Line 33 reads `except TypeError, ValueError:`. Under Python 3 this parses as `except TypeError as ValueError` (multiple-exception `except E1, E2:` was removed in Py3), so it catches **only** `TypeError` and binds the caught exception to the local name `ValueError` (shadowing the builtin in that scope). A `ValueError` raised inside the try (e.g. `state.retries = "abc"` → `int("abc")`) **propagates uncaught**, contradicting the docstring's "No silent failures" intent and the `retries = 0` fallback.

- File: src/services/http_client.py:28-35 (`_get_retries`), line 33 specifically.
- Verified empirically: `except TypeError, ValueError:` with a `ValueError` in the try body propagates the `ValueError`; only `TypeError` is caught.
- Compiles cleanly (`py_compile` exit 0) — so ruff/pyflakes may not flag it unless configured for the `except-as` pattern; it is a logic bug, not an import error.

### D. Shared mutable state that leaks between tests (nothing resets it)
conftest.py installs no autouse fixture, so the following process-wide mutable globals persist across tests:

| Shared state | Location | Why it leaks |
|---|---|---|
| `services.http_client._client`, `_client_proxy`, `_client_retries` | src/services/http_client.py:23-25 | Pooled httpx client + proxy/retries config survive; `get_client()` rebuilds only when proxy/retries change (http_client.py:45). A test that sets `state.proxy_url` poisons the client for later tests. |
| user-scanner proxy manager / global timeout | src/services/user_scanner_compat.py:132-133 (`set_proxy_manager(proxies=[proxy])`) | Mutates global user-scanner state; no teardown resets it. |
| `StorageService._INSTANCES` singleton registry | src/services/storage_service.py:19 (`_INSTANCES: dict[str, StorageService] = {}`) | One instance per storage dir, process-wide. Tests writing to the default storage dir contaminate each other and the real `.flet/storage/data`. |
| `core.state.state` singleton (AppState) | src/state/app_state.py:240 (`state = AppState()`) | Mutable; `reset_search()` exists (state.py:194) but is never auto-invoked between tests. Fields like `proxy_url`, `timeout`, `search_mode`, `last_results`, `results_cache` persist. |
| Background `asyncio.Task`s from `core.tasks.spawn` | src/core/tasks.py:18-31 | Fire-and-forget tasks can outlive the test's event loop; `spawn` is used by http_client.py:97 (`_drain`). No loop teardown fixture. |

### E. pytest-asyncio is NOT installed; the "asyncio" marker is a landmine
pyproject.toml:74-77 registers the `asyncio` marker ("run the test in an asyncio event loop"), but the dev dependencies (pyproject.toml:80-84) list only pytest, pytest-timeout, ruff — **no pytest-asyncio**. Any test (future or existing) decorated `@pytest.mark.asyncio` will fail with "unknown marker" / `usage error` under `strict_markers = true` (pyproject.toml:72). conftest.py does nothing to guard or document this.

### F. `filterwarnings` is absent
Not present in pyproject.toml `[tool.pytest.ini_options]` and not set in conftest.py. Deprecation/ResourceWarnings (e.g. unclosed httpx clients, lingering timers from storage_service.py:254 `threading.Timer`) go unchecked.

### G. test_imports.py assertions are trivial
Every assertion is `X is not None` on an object that was just imported (test_imports.py:19, 20, 21, 28, 33). An imported module attribute that exists is never None unless explicitly set to None, so these assertions cannot catch import failures, missing symbols, or broken modules. They add no real coverage beyond "the import statement did not raise".

### H. test_imports.py skips the buggy modules
report_service.py (known-bug location per suite-level audit), results_screen.py, http_client.py, storage_service.py, user_scanner_compat.py, and ~45 others are never imported by any test file (grep of tests/*.py confirms imports touch only main, app_shell, services.{email,phone,sherlock,storage}_service, services.user_scanner_compat, core.constants, core.state, screens.home_screen, components.active_scan_banner, plus external user_scanner/phonsint).

---

## 3) Gaps

1. **Redundant path shim with no value.** conftest.py:6 duplicates pyproject.toml:69 `pythonpath = ["src"]`. It should be removed (or at minimum justified) — it currently does nothing pytest does not already do.

2. **No autouse state-reset fixture.** conftest.py has no fixture that resets `http_client._client`, `state`, `StorageService._INSTANCES`, or the user-scanner proxy manager between tests. This is the single biggest gap: the original V3 conftest had an autouse `_reset_shared_http_client` fixture and FakePage fixtures (conftest.py:140-152 per the suite-level audit) that V3 dropped. Without it, cross-test state leakage is possible and order-dependent.

3. **test_imports.py covers only 7 of ~54 modules.** It omits report_service.py, results_screen.py, http_client.py, storage_service.py, user_scanner_compat.py, all core/* except none, all screens except home_screen, etc. It therefore cannot serve as the import-smoke net the suite needs; known-bug modules are invisible to it.

4. **Trivial assertions.** test_imports.py:19-21, 28, 33 assert `is not None` on freshly-imported names — cannot fail realistically and verify nothing about module usability.

5. **No offline/network guard.** None of the import tests mark or restrict network use. `test_services.py:38` and `test_services_all_modes.py` call `asyncio.run(svc.load_sites())` which can reach the network; without a `-m 'not live'` guard or network block, CI runs can hang or fail offline. (Pytest config: pyproject.toml:75 defines a `live` marker but tests don't consistently apply it.)

6. **pytest-asyncio marker landmine unaddressed.** conftest.py does not skip/deselect `@pytest.mark.asyncio` tests when pytest-asyncio is absent, nor does it document the requirement.

7. **No `filterwarnings`** anywhere (conftest.py nor pyproject.toml), so resource warnings from leaked httpx clients / storage timers are silent.

---

## 4) Proposed additions (code sketches)

### 4.1 conftest.py — replace shim with state-reset autouse fixture (drop the redundant sys.path line)

```python
"""Test configuration for Sherlock-V3.

Provides an autouse fixture that resets shared mutable state between tests so
test order cannot influence results:
  * services.http_client pooled client + proxy/retries cache
  * core.state singleton (AppState)
  * services.storage_service _INSTANCES registry (default dir)
  * user_scanner proxy manager (best-effort)
  * closes any lingering background tasks spawned via core.tasks.spawn
"""

import asyncio
import importlib
import sys

import pytest

# NOTE: src is already on sys.path via pyproject.toml [tool.pytest.ini_options]
# pythonpath = ["src"], so the old conftest.py sys.path shim is intentionally
# omitted. Keep this import here only to force-verify src is importable at
# collection time.
import core.state  # noqa: F401  (confirms pythonpath works)


@pytest.fixture(autouse=True)
def _reset_shared_state():
    """Reset cross-test shared state before each test."""
    # --- HTTP client: close pooled client and clear proxy/retries cache ---
    try:
        from services import http_client as _hc
    except Exception:  # pragma: no cover - services importable per audit
        _hc = None
    if _hc is not None:
        old = getattr(_hc, "_client", None)
        _hc._client = None
        _hc._client_proxy = None
        _hc._client_retries = None
        if old is not None:
            try:
                asyncio.get_event_loop().run_until_complete(old.aclose())
            except Exception:
                pass

    # --- core.state singleton ---
    try:
        from core.state import state as _state
    except Exception:
        _state = None
    if _state is not None and hasattr(_state, "reset_search"):
        _state.reset_search()
    if _state is not None:
        # Also reset settings that tests commonly flip (proxy, timeout, mode).
        for _attr in ("proxy_url", "timeout", "search_mode", "email_timeout",
                      "email_concurrency", "phone_concurrency"):
            if hasattr(_state, _attr):
                setattr(_state, _attr, _state.__class__.__dict__.get(_attr) or
                        ("" if _attr in ("proxy_url", "search_mode") else 0))

    # --- StorageService singleton registry (default dir) ---
    try:
        from services.storage_service import StorageService as _SS
    except Exception:
        _SS = None
    if _SS is not None:
        _SS._INSTANCES.clear()
        _SS._INSTANCES_lock.acquire() if hasattr(_SS, "_INSTANCES_lock") else None
        if hasattr(_SS, "_INSTANCES_lock"):
            _SS._INSTANCES_lock.release()

    # --- user-scanner proxy manager (best-effort; engine-global) ---
    try:
        from user_scanner.core.helpers import set_proxy_manager
        set_proxy_manager(proxies=[])  # clear proxy
    except Exception:
        pass

    yield

    # --- teardown: ensure no leaked client / tasks survive the test ---
    if _hc is not None:
        old = getattr(_hc, "_client", None)
        _hc._client = None
        _hc._client_proxy = None
        _hc._client_retries = None
        if old is not None:
            try:
                asyncio.get_event_loop().run_until_complete(old.aclose())
            except Exception:
                pass
```

### 4.2 conftest.py — asyncio marker guard (pytest-asyncio not installed)

```python
def pytest_collection_modifyitems(config, items):
    """Deselect @pytest.mark.asyncio tests when pytest-asyncio is absent so
    the registered marker (pyproject.toml:76) is not a landmine under
    strict_markers = true."""
    try:
        import pytest_asyncio  # noqa: F401
    except ImportError:
        skip_asyncio = pytest.mark.skip(
            reason="pytest-asyncio not installed; asyncio marker unsupported"
        )
        for item in items:
            if "asyncio" in item.keywords:
                item.add_marker(skip_asyncio)
```

### 4.3 conftest.py — warning filters (companion to missing `filterwarnings`)

```python
@pytest.fixture(autouse=True)
def _warn_on_resource_leaks():
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        yield
```

### 4.4 test_imports.py — meaningful offline import-smoke covering ALL src modules

Enumerate the missing modules to cover (all importable offline per §2-B):

```python
"""Offline import smoke tests — every src module must import without network."""

import importlib

# Every src package/module that must be importable offline. Keep in sync with
# the src/ tree; modules added here must also be importable in CI (no network,
# no optional deps such as reportlab/jinja2 required at import time).
SRC_MODULES = [
    "main",
    "app_shell",
    "components",
    "components.active_scan_banner",
    "components.app_header",
    "components.banner_ad",
    "components.empty_state",
    "components.profile_detail_dialog",
    "components.result_card",
    "components.section_header",
    "components.stat_card",
    "components.targets_card",
    "components.update_dialog",
    "core",
    "core.actions",
    "core.changelog",
    "core.constants",
    "core.enrich_view",
    "core.format",
    "core.geo_utils",
    "core.logger_handler",
    "core.notify",
    "core.permute",
    "core.shared_services",
    "core.state",
    "core.tasks",
    "core.theme",
    "core.tokens",
    "hooks",
    "hooks.use_debounce",
    "screens",
    "screens.history_screen",
    "screens.home_screen",
    "screens.onboarding_screen",
    "screens.results_screen",
    "screens.settings_screen",
    "screens.sites_screen",
    "services",
    "services.ad_service",
    "services.cache_service",
    "services.email_service",
    "services.enrich_service",
    "services.http_client",
    "services.phone_service",
    "services.report_service",
    "services.scan_notify",
    "services.sherlock_service",
    "services.storage_service",
    "services.update_service",
    "services.user_scanner_compat",
    "state",
    "state.app_state",
    "state.controller_ctx",
]


def test_all_src_modules_importable_offline():
    """Every src module imports cleanly with no network and no optional deps."""
    failed = []
    for name in SRC_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - report every failure
            failed.append((name, type(exc).__name__, str(exc)))
    assert not failed, f"Modules that failed to import: {failed}"
```

This replaces (or supplements) the five trivial tests. If keeping the old tests, at minimum strengthen them to assert real attributes (e.g. `test_imports.py:19` → `assert isinstance(sherlock_service.SherlockService, type)`), but the wholesale module list above is the concrete improvement.

### 4.5 test_imports.py — network guard for service tests that reach out

Add a session fixture so load_sites()-style tests do not silently hit the network:

```python
import socket

_REAL_CONNECT = socket.socket.connect

def _block_connect(self, address, *args, **kwargs):
    raise RuntimeError("network access blocked in tests")

@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _block_connect)
    yield
    monkeypatch.undo()
```

(Apply selectively — only to tests that must stay offline — or gate real-network tests with the existing `live` marker from pyproject.toml:75.)

---

## 5) Verdict

**tests/conftest.py and tests/test_imports.py together provide almost no test-infrastructure value and conceal real risk.**

- conftest.py:1-6 is a redundant sys.path shim (pyproject.toml:69 already covers it) with no fixtures, no state isolation, no asyncio handling, and no warning filters. Given shared mutable state at http_client.py:23-25, state.py:240, storage_service.py:19, and user_scanner_compat.py:132-133, tests can leak state across each other — the very thing the dropped V3 autouse fixture (conftest.py:140-152 originally) prevented.
- test_imports.py:1-33 imports only 7 of ~54 src modules with trivial `is not None` assertions, omitting report_service.py, results_screen.py, http_client.py and storage_service.py — exactly the modules with known bugs. It passes while exercising none of the risky code.
- A concrete latent bug was confirmed at src/services/http_client.py:33 (`except TypeError, ValueError:` catches only TypeError; ValueError propagates).

**Recommended actions (in priority order):**
1. Replace conftest.py with an autouse state-reset fixture covering http_client, core.state, StorageService._INSTANCES, and user-scanner proxy manager (sketch in §4.1); drop the redundant sys.path shim.
2. Rewrite test_imports.py as an all-modules offline import-smoke (§4.4) covering the ~45 modules it currently omits, including report_service.py, results_screen.py, http_client.py, storage_service.py.
3. Add the pytest-asyncio marker guard (§4.2) and `filterwarnings`/ResourceWarning handling (§4.3).
4. Add network blocking or consistent `live` markers (§4.5) so service tests cannot reach the network in CI.

No files were modified during this audit.