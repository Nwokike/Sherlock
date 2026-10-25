# pytest 9.1.1 — Dependency Audit & Test-Suite Quality Report

**Scope:** the installed `pytest` 9.1.1 (plus `pytest-timeout` 2.4.0) in `.venv`, and the quality/coverage
of `tests/` as it stands in Sherlock V3.
**Ground rule honoured:** every claim below was re-derived from the installed package
(`.venv/Lib/site-packages/pytest`, `_pytest`, `pytest_timeout.py`) and from real runs. `docs/reference/dep-pytest-stack.md`
was read as background only; where it drifts, the installed copy wins (drift is called out).
**Constraint:** nothing in `src/` or `tests/` was modified. Probe files were written to a temp dir outside the repo
(`%TEMP%/pytest_probe`) and run with `-c pyproject.toml`.

---

## 1) Installed verification

### 1.1 Versions (all from the venv, not from `uv.lock`)

| Package | Installed | Notes |
|---|---|---|
| `pytest` | **9.1.1** | `pytest-9.1.1.dist-info` present; `python -m pytest --version` → `pytest 9.1.1` |
| `pluggy` | 1.7.0 | plugin engine (hook dispatch) |
| `iniconfig` | 2.3.1 | INI parser used for `pyproject.toml` |
| `packaging` | 26.3 | version/requirement parsing |
| `pygments` | 2.21.0 | traceback/assertion colouring |
| `colorama` | 0.4.6 | Windows ANSI (required by pytest on `sys_platform == "win32"`) |
| `pytest-timeout` | 2.4.0 | single-module plugin `pytest_timeout.py` |
| `exceptiongroup` | **not installed** | not needed — `Requires-Python: >=3.10`, venv is Python **3.14.7** |
| `pytest-asyncio` | **NOT INSTALLED** | see §3.3 — this is the single most important config finding |
| `pytest-cov` / `coverage` | **NOT INSTALLED** | no coverage measurement is possible in this venv |
| `pytest-randomly` / `xdist` / `rerunfailures` / `mock` | not installed | test order is deterministic; no parallelism |

`pytest-9.1.1.dist-info/METADATA` requires: `colorama>=0.4` (win32), `exceptiongroup>=1` (<3.11), `iniconfig>=1.0.1`,
`packaging>=22`, `pluggy>=1.5,<2`, `pygments>=2.7.2`, `tomli>=1` (<3.11). All satisfied except the two
`python_version < "3.11"` extras, which do not apply at 3.14.7.

### 1.2 Plugins auto-loaded in this project

```
plugins: anyio-4.15.1, flet-1.0.4, timeout-2.4.0
timeout: 60.0s
timeout method: thread
timeout func_only: False
```
`anyio` and `flet` register pytest plugins as a side effect of being importable. `anyio` is a transitive of
`httpx` and ships a real pytest plugin — this matters in §3.3.

### 1.3 Config activation

`pyproject.toml` is picked up correctly — `rootdir: /home/maikel/.zcode/workspace/default/Sherlock-V3`,
`configfile: pyproject.toml`. `pythonpath = ["src"]` resolves and `import main` works from `tests/`.

**Drift vs. the V2 background doc** (`docs/reference/dep-pytest-stack.md`): it states pytest 9.1.1 and
pytest-timeout 2.4.0 — both **confirmed correct**. It does not mention that `pytest-asyncio` is absent,
and it predates the `reportlab` removal, so its "original Sherlock project" export/test narrative no longer
reflects this venv.

---

## 2) Real suite run results

### 2.1 Collection

```
$ .venv/Scripts/python.exe -m pytest --collect-only -q
tests/test_compat_loader.py: 6
tests/test_cross_scan.py: 8
tests/test_imports.py: 5
tests/test_phone_mode_parity.py: 6
tests/test_services.py: 7
tests/test_services_all_modes.py: 9
tests/test_sites_catalog.py: 5
tests/test_storage_resilience.py: 5
```
**51 tests, 8 files, 0 collection errors, 0 config errors.** (pytest 9 `-q --collect-only` prints per-file counts.)

### 2.2 Full run — PASS

```
$ .venv/Scripts/python.exe -m pytest            # bare: addopts give verbosity -1
...................................................                      [100%]
51 passed in 30.45s
```
Exit code **0**. Per-file breakdown (from a run with `addopts` cleared):
```
tests\test_compat_loader.py ......       [ 11%]
tests\test_cross_scan.py ........        [ 27%]
tests\test_imports.py .....              [ 37%]
tests\test_phone_mode_parity.py ......   [ 49%]
tests\test_services.py .......           [ 62%]
tests\test_services_all_modes.py .........[ 80%]
tests\test_sites_catalog.py .....        [ 90%]
tests\test_storage_resilience.py .....   [100%]
============================= 51 passed in 31.12s =============================
```

**0 failed, 0 errors, 0 skipped, 0 xfailed, 0 warnings** (no "warnings summary" section was emitted —
the suite is warning-clean today). No config errors, no collection errors.

### 2.3 The `-q` double-flag trap (important for CI logs)

`addopts = ["-ra", "-q"]` **already** applies one `-q`. Invoking `pytest -q` applies a second one, so the
effective verbosity is **−2**, and pytest 9's `summary_stats()` bails out early:

```python
# _pytest/terminal.py:1252
def summary_stats(self) -> None:
    if self.verbosity < -1:
        return
```

Measured, same suite, same code state:

| Command | Effective verbosity | Output tail |
|---|---|---|
| `pytest` (bare) | −1 | `51 passed in 30.45s` |
| `pytest -q` | **−2** | `...................................................  [100%]` — **no count line at all** |
| `pytest -qq` | −3 | same — no count line |
| `pytest -q -v` | 0 | `51 passed in 36.27s` |

Verified root cause by introspection: `config.option.verbose == -3` when `addopts` supplies one `-q` and the CLI
supplies two more. **Consequence:** the natural CI invocation `pytest -q` produces a log with dots and an exit
code but *no* "N passed" summary. Failures are still visible (`-ra` drives the short summary and is not
verbosity-gated), so this is a readability/CI-parsing hazard, not a correctness one.
**Fix (one line, no behaviour change):** remove `-q` from `addopts` and let the caller choose verbosity —
then `pytest` and `pytest -q` both print the count line.

---

## 3) Config correctness findings

`[tool.pytest.ini_options]` (pyproject.toml lines 68–78) as installed:

```toml
pythonpath = ["src"]
addopts = ["-ra", "-q"]
timeout = 60
strict_markers = true
strict_config = true
markers = [
    "live: hits the real network (run explicitly with -m live; CI uses -m 'not live')",
    "asyncio: run the test in an asyncio event loop",
]
```

### 3.1 What is registered and what is missing

| Key | Status | Evidence |
|---|---|---|
| `pythonpath` | ✅ core pytest ini (≥7.0) | `import main` resolves from `tests/` |
| `addopts` | ⚠️ works, but `-q` double-counts (§2.3) | measured verbosity table above |
| `timeout` | ✅ **only valid because pytest-timeout is installed** | see §3.2 |
| `strict_markers` | ✅ enforced | see §3.4 |
| `strict_config` | ✅ enforced | see §3.2 |
| `markers` | ✅ `live` + `asyncio` registered | §3.4, §3.5 |
| **`filterwarnings`** | ❌ **ABSENT** | §3.6 |
| `testpaths` | ❌ absent (collection is by rootdir scan) | minor |
| `asyncio_mode` / `anyio_mode` | n/a — no async plugin configured | §3.5 |

### 3.2 `timeout = 60` — correct, but tightly coupled to the plugin

`timeout` is **not** a core pytest option; it is contributed by `pytest-timeout` 2.4.0. Under `strict_config = true`
the dependency is enforced hard — with the plugin disabled:

```
$ .venv/Scripts/python.exe -m pytest -p no:timeout --collect-only -q
ERROR: Unknown config option: timeout
... (collection still lists 51 tests)
EXIT=4                      # UsageError
```

So `pytest-timeout` **must** stay in the `dev` dependency-group; if it is ever dropped, the whole suite stops
with exit 4 rather than silently losing the timeout. That is the desired behaviour and is worth keeping.

Live verification that the timeout is armed (probe file outside the repo, `-o timeout=1`, `time.sleep(3)`):
the run aborted with the `+++++++ Timeout +++++++` banner — the plugin is genuinely active.

**Two operational caveats that matter for the known bugs:**
- On Windows there is no `SIGALRM`, so pytest-timeout selects `timeout method: thread`. That implementation
  (`pytest_timeout.py:505-542`) **dumps every thread's stack and calls `os._exit(1)`** — it kills the *entire
  pytest process*, not just the offending test. A hanging test therefore aborts the whole suite with no
  per-test report.
- `timeout func_only: False` (default) → the 60 s budget covers setup + call + teardown of each test.
- The suite currently takes ~30 s wall-clock, dominated by the 2 521-module loader tests — i.e. the budget is
  ~2× the whole-suite cost, so the timeout is a hang-detector, not a perf gate.

### 3.3 ⚠️ The `asyncio` marker is a **latent landmine** — pytest-asyncio is NOT installed

Facts:
- `ls .venv/Lib/site-packages | grep -i asyncio` → **nothing**. `importlib.metadata` lists only
  `pytest 9.1.1` and `pytest-timeout 2.4.0`. **pytest-asyncio is absent.**
- The `asyncio` marker *is* registered in `pyproject.toml`, so `strict_markers` will **not** complain about it.
- **No test in the repo uses any pytest marker at all** (`grep -rn "pytest.mark" tests/` → zero hits), so the
  suite is green today.

What happens the moment someone writes the obvious test (probe executed, marker registered, plugin absent):

```
$ pytest -c pyproject.toml <probe>/test_asyncio_probe.py
collected 1 item
. F                                                                      [100%]
================================== FAILURES ===================================
______________________________ test_async_marked ______________________________
async def functions are not natively supported.
You need to install a suitable plugin for your async framework, for example:
  - anyio
  - pytest-asyncio
  - pytest-tornasync
  - pytest-trio
  - pytest-twisted
=========================== short test summary info ============================
FAILED ::test_async_marked - Failed: async def functions are not natively sup...
============================== 1 failed in 5.95s ===============================
```

So the answer to the task's question is: **it does not error at collection (strict_markers is satisfied by the
ini registration) — it FAILS AT RUNTIME with "async def functions are not natively supported"**, and the
failure text points at dependencies rather than at the real cause (the marker is a no-op because the plugin is
missing). That is the worst failure mode for a marker: it looks like a missing package, and the marker
registration actively hides the configuration error.

**Note the irony:** `anyio 4.15.1` **is** installed and **does** register a pytest plugin (visible in the
plugin list). `@pytest.mark.anyio` async tests would work today with zero new dependencies. Two clean options:
1. install `pytest-asyncio` in the dev group (and keep the `asyncio` marker, optionally `asyncio_mode = "auto"`), or
2. delete the `asyncio` marker registration and use anyio's marker (anyio is already a transitive of httpx).

Either way, **the current `asyncio` marker registration buys nothing and hides a real dependency gap.**

### 3.4 `strict_markers` — enforced, but the `live` marker is decorative

Probe with an unregistered marker:
```
'bogus_marker' not found in `markers` configuration option
Interrupted: 1 error during collection
```
(strict_markers aborts the **whole collection**, not just that file — a single typo in a marker name takes the
entire suite down. Worth knowing when authoring new tests.)

The `live` marker, however, is used by **zero** tests:
- `pytest -m live --collect-only` → 0 tests → **exit code 5** (`NO_TESTS_COLLECTED`).
- `pytest -m "not live" --collect-only` → all 51 tests.
The marker's own description says *"CI uses -m 'not live'"* — but **this repository has no CI configuration at
all** (no `.github/`, no other CI config directory). The documented CI contract does not exist, and the entire
network-touching path of the app is untested. The marker is a placeholder that has never been exercised.

### 3.5 `strict_config` — verified working

`strict_config = true` is on and only accepts known keys. Verified by deliberately breaking it (§3.2 →
"ERROR: Unknown config option: timeout", exit 4). The current key set is clean — no typos, no
plugin-less options.

### 3.6 ⚠️ `filterwarnings` is absent — no warning policy at all

There is **no `filterwarnings` key** in `[tool.pytest.ini_options]`. Note this is *not* a `strict_config` error —
`strict_config` rejects *unknown* keys, not *missing* ones — so the config is technically valid. But the
consequence is that:

- warnings are never escalated to errors (`filterwarnings = ["error"]` absent),
- warnings are never pinned/ignored, so a new `DeprecationWarning` from flet 1.0.4 or Python 3.14 will appear
  as noise in the log and then be silently ignored forever.

The suite currently emits **0 warnings**, so adding a policy today is a free hardening step:

```toml
filterwarnings = ["error", "default::DeprecationWarning:flet.*"]
```
(verify the module regex against the actual warning origins before turning `error` on globally).

### 3.7 Minor hygiene

- `tests/conftest.py` does `sys.path.insert(0, .../src)` while `pythonpath = ["src"]` already does the same job.
  Harmless duplication; the conftest version is what actually guarantees `import main` when pytest is invoked
  from an unexpected rootdir.
- **`.pytest_cache/` is not in `.gitignore`** (which only lists `__pycache__/`, `*.py[oc]`, `build/`, `dist/`,
  `wheels/`, `*.egg-info`, `.venv`). The cache directory already exists at the repo root; since every file in
  this repo is currently untracked, a `git add .` would commit it.
- No `testpaths = ["tests"]` → collection scans the whole rootdir. Deterministic today (only `tests/` contains
  `test_*.py`), but explicit is safer.
- No `--maxfail`; no `-p no:cacheprovider`; no coverage plugin.

---

## 4) Coverage gaps mapped to known bugs

### 4.1 Coverage reality check — what the 51 tests actually assert

| File | Tests | Asserts | Existence-style asserts (`is not None` / `callable` / `hasattr`) | What it really covers |
|---|---|---|---|---|
| `test_imports.py` | 5 | 5 | **5 (100 %)** | Pure import smoke: `main`, `app_shell`, 3 services, `screens.home_screen`, `components.active_scan_banner`. No behaviour at all. |
| `test_compat_loader.py` | 6 | 10 | 3 | The **best** file in the suite: `load_user_modules() > 2000`, `load_email_modules() > 100`, `load_phone_modules() == 5` with the category set `{auth, crm, shopping, social}`, the tolerant loader skipping a module that raises on import, driver callables, `PhoneService.cancel()` returning `None`. |
| `test_cross_scan.py` | 8 | 13 | 1 | ⚠️ Tests **upstream `user_scanner` privates** (`_split_budget`, `_sweep_targets`, `rank_usernames`, `CrossScanConfig`) — not the app's wrapper. `run_cross_scan_async` is only checked for `callable`. A wrapper regression (the app's own cross-scan glue) is invisible, and the test is coupled to upstream *private* API that can change on any user-scanner bump. |
| `test_services.py` | 7 | 12 | 2 | `is_available` flags for 3 services, `validate_email`, `parse_usernames`, `load_sites()` for username/phone. Two tests are **misnamed** (`test_sherlock_search_returns_progress`, `test_phone_search_returns_progress`) — they call `load_sites()`, no search is performed. |
| `test_services_all_modes.py` | 9 | 15 | 4 | Mode catalogs (`>2000`, `100<total<500`, `==5`), loud-module filtering, `PhoneResult`/`SiteResult` dataclasses, `callable(SherlockService.run_hudson)` / `callable(EmailService.run_hudson)` (**existence only**), `hasattr(svc, "_run")`. |
| `test_sites_catalog.py` | 5 | 7 | 0 | Mode-aware catalog switching into `core.state` (`sites_total`, `sites_cache`, `sites_tag_index`), `MODE_PHONE == "phone"`, `state.selected_sites == []`. |
| `test_storage_resilience.py` | 5 | 7 | 0 | **Genuinely good**: singleton sharing, snapshot persistence, set/flush/reload round-trip, retry-on-`PermissionError` (asserts ≥3 `os.replace` attempts), and give-up-after-max-retries. This is the one file that would actually catch a real regression. |
| `test_phone_mode_parity.py` | 6 | 10 | 2 | `state.phone_results` / `phone_results_address` / `phone_found_count` lifecycle, `reset_search()` clearing, `PhoneResult` mapping, `hasattr(svc, "_worker_loop")`, `MODE_PHONE == "phone"`. |

**Import-graph reality check** (measured with a `pytest_sessionfinish` hook that diffs `sys.modules` against the
`src/` tree):

```
SRC_PY_FILES=54  IMPORTED=34  NEVER_IMPORTED=20
```
Never imported by the whole suite:
`__init__.py`, `components/empty_state.py`, `components/profile_detail_dialog.py`, `components/result_card.py`,
`components/section_header.py`, `components/stat_card.py`, `core/actions.py`, `core/enrich_view.py`,
`core/geo_utils.py`, `core/permute.py`, `hooks/__init__.py`, `hooks/use_debounce.py`,
`screens/history_screen.py`, `screens/onboarding_screen.py`, **`screens/results_screen.py`**,
`screens/settings_screen.py`, `screens/sites_screen.py`, `services/cache_service.py`,
**`services/http_client.py`**, **`services/report_service.py`**.

**37 % of the application source is never even imported by the test suite**, and the three files that never
imported — `screens/results_screen.py`, `services/report_service.py`, `services/http_client.py` — are precisely
the three that carry the known bugs below.

### 4.2 Gap → known bug mapping

#### GAP 1 — phone results `AttributeError` (CRITICAL, uncovered)
- **Bug:** `deps/phonsint.md` B1 — `src/screens/results_screen.py:475-476` reads
  `active_progress.rate_limited` and `active_progress.unavailable`, but `PhoneSearchProgress`
  (`src/services/phone_service.py:39-47`) defines only `phone, total_modules, checked_modules, found,
  not_found, errors, is_running, is_cancelled` →
  `AttributeError: 'PhoneSearchProgress' object has no attribute 'rate_limited'` on **every live phone scan**
  that opens the Results tab (the error is downgraded to a snackbar by `main.py:2322 on_error`, so it fails
  silently).
- **Why the suite misses it:** `screens/results_screen.py` is **never imported** by any test. The two phone tests
  only touch the *post-scan* list (`state.phone_results`) and the `PhoneResult` dataclass — neither the
  `PhoneSearchProgress` shape nor the screen's consumption of it.
- **The near-miss:** `test_phone_mode_parity.py::test_phone_snapshot_row_shape_matches_email_card_contract`
  looks like the test that should have caught a shape drift, but it **builds the expected row dict as a literal
  inside the test** and asserts on its own keys. It never calls app code that produces a row, so it can never
  fail for a shape mismatch. It is a self-fulfilling assertion.
- **Cheap regression test that would have caught it (≈6 lines):** assert the field-name sets consumed by the
  results screen are a subset of the dataclass fields, e.g. compare
  `{f.name for f in dataclasses.fields(PhoneSearchProgress)}` against
  `{"rate_limited", "unavailable", "found", "not_found", "total_modules", "checked_modules"}`.
  (Do **not** fix the app here — mapping only.)

#### GAP 2 — Hudson prompt deadlock (uncovered)
- **Bug:** `deps/user-scanner.md` B1 / `deps/colorama.md` — `user_scanner/core/hudson.py:36` calls `input()`
  inside `check_hudson_permission()` with **no `sys.stdin.isatty()` guard** (unlike `core/loud_prompt.py:33`),
  and `config.json` ships `auto_hudson_prompt: true`. With stdin closed it raises `EOFError` (swallowed at
  `sherlock_service.py:288` / `email_service.py:423` → snackbar "Hudson check failed: EOF when reading a line");
  on a TTY it **blocks the worker thread forever**, and because `sherlock_service.py:285` /
  `email_service.py:419` redirect stdout into a `StringIO`, the prompt text is swallowed so the user never
  sees the question. The feature is 100 % dead either way. (`deps/colorama.md` adds a second, cosmetic defect on
  the same path: upstream ANSI escapes are returned verbatim into the SnackBar.)
- **Why the suite misses it:** the only Hudson test is
  `test_services_all_modes.py::test_hudson_methods_exist` → `assert callable(SherlockService.run_hudson)` /
  `callable(EmailService.run_hudson)`. It never *invokes* them, so neither the `EOFError` path nor the
  blocking path is exercised, and the ANSI-leak path is not exercised either.
- **Test-design trap for whoever fixes this:** on Windows, pytest-timeout's `thread` method responds to a hang by
  `os._exit(1)` (§3.2) — a Hudson test that blocks on `input()` would **kill the whole pytest run**, not fail one
  test. Any Hudson test must neutralise the prompt first (patch `builtins.input` / `sys.stdin`, and/or force
  `auto_hudson_prompt=False`) *before* the engine call, or it must run with a redirected stdin.

#### GAP 3 — proxy staleness (uncovered)
- **Bug:** `deps/socksio.md` §3.5 (A) and `deps/httpx.md:331` — both `set_proxy_manager` call sites are guarded by
  `if proxy:` (`src/services/user_scanner_compat.py:130`, `src/services/email_service.py:263`), but
  `set_proxy_manager` only clears the global when called **with no arguments**
  (`user_scanner/core/helpers.py:683-686`). The app therefore never clears it: after the user clears the proxy
  in Settings, user-scanner keeps tunnelling through the **old** SOCKS proxy while the app's own httpx client
  (`src/services/http_client.py:43-48`) has already reverted to direct. The two legs of the app disagree about
  whether traffic is proxied. (`deps/httpx.md` adds: the app's "direct" transport can be re-routed through the
  engine's stale manager proxy when the app proxy is empty.) Related dead code: the proxy **file** is validated
  in Settings but never passed to `set_proxy_manager` → `ProxyManager._load_proxies` and the round-robin rotation
  are dead from the app's point of view.
- **Why the suite misses it:** `grep -rn "proxy" tests/` → **zero hits**. No test exercises the proxy branch of
  the compat driver or of `EmailService`; `services/http_client.py` (the other half of the disagreement) is never
  imported by the suite.
- **Cheap regression test:** monkeypatch `user_scanner.core.helpers.set_proxy_manager`, drive the compat layer
  with `proxy=""` and assert it was called with **no arguments** (i.e. the manager is cleared). Today it would
  fail — which is the point.

#### GAP 4 — export path broken since `reportlab` was removed (uncovered)
- **Bug:** `reportlab`, `pillow`, `svglib` were removed from `pyproject.toml` (swarm README). `src/services/report_service.py`
  still imports them: `from reportlab.lib import colors as rl_colors` etc. inside a `try/except`
  (`report_service.py:23-27`) → `_RL_AVAILABLE = False`; `report_service.py:573` raises
  `RuntimeError("reportlab unavailable — PDF palette requires reportlab")`; and `generate_html_report` /
  `generate_email_html_report` `return None` because **`jinja2` is also absent** (`report_service.py:338-340`,
  `:498-500` — flagged in `deps/markdown-it-py.md`). `reportlab` and `jinja2` are both confirmed **not installed**
  in this venv. Per the swarm README this is *intentionally* broken pending the V3 export rework — the audit
  must flag, not patch.
- **Why the suite misses it:** `services/report_service.py` is **never imported** by any test. Nothing asserts
  that export raises a clear, actionable error, so the app ships a dead export path behind a fully green suite.
  `deps/markdown-it-py.md` also notes the HTML export tiles in `app_shell.py` are effectively dead paths.
- **Recommended (when the export rework lands):** a test that imports `report_service` and asserts the *documented*
  failure mode (raise-or-`None`, not `ImportError` leaking from a module-level import), plus a round-trip test of
  the CSV/JSON exporters that need no third-party dependency.

#### GAP 5 — additional untested critical paths (not on the known-bug list, found by this audit)
- `core/permute.py` — **never imported**. Username permutation is a headline feature of the wrapped engine and has
  zero coverage.
- `core/geo_utils.py`, `core/geo` enrichment, `core/enrich_view.py`, `core/actions.py`, `hooks/use_debounce.py` —
  never imported.
- `screens/history_screen.py`, `screens/settings_screen.py`, `screens/sites_screen.py`, `screens/onboarding_screen.py`,
  `components/result_card.py`, `components/profile_detail_dialog.py`, `components/stat_card.py` — never imported.
  The history screen is the persistence path the storage tests write to but nothing reads back through the UI.
- `services/cache_service.py`, `services/update_service.py`, `services/ad_service.py`, `services/enrich_service.py`,
  `services/scan_notify.py` — imported transitively via `import main`, but **no test exercises their logic**;
  they only get "imported", which the import-smoke test mistakes for coverage.
- No test drives the app's own `run_cross_scan_async` wrapper (GAP in §4.1) — `test_cross_scan.py` tests upstream
  privates instead. The app's cross-scan glue (budget splitting, proxy injection, cancel-event propagation,
  confidence mapping into `SiteResult.badge`) is untested.
- `test_cross_scan.py` imports upstream **private** symbols (`_split_budget`, `_sweep_targets`) — any user-scanner
  release that renames them breaks the suite for reasons unrelated to this app.
- Brittle magic numbers tied to the vendored engine's catalogue size: `> 2000` username modules, `> 100` email
  modules, `100 < total < 500` email total, `== 5` phone modules. These will fail (or, worse, silently pass) on an
  engine upgrade; they should be asserted as *ranges derived from the engine*, not as constants.
- `test_sites_catalog.py::test_load_catalog_username` asserts `total == state.sites_total` — both sides come from
  the same `load_sites()` call, so it can only fail if the global is not written; near-tautological.
- Duplicate test: `test_phone_result_mapping_registered` exists **twice** — in `test_services_all_modes.py` and
  in `test_phone_mode_parity.py` — with the same body. Copy-paste, not independent coverage.
- No test for `cancel()` semantics beyond "returns `None`" (`test_compat_loader.py::test_cancel_event_stops_driver`
  never starts a scan, so the cancel path is not really exercised).

---

## 5) Verdict

### **ISSUES FOUND**

The installed stack is **healthy** — pytest 9.1.1 + pytest-timeout 2.4.0 are correctly installed, the
`[tool.pytest.ini_options]` block activates cleanly (no config errors, `strict_config`/`strict_markers` both
verified working), and the suite is **green: 51 passed in ~30 s, exit 0, 0 warnings**. The dependency itself is
not the problem.

The problems are in the **config's edges** and in **what the suite does not reach**:

**Config issues (4)**
1. **`asyncio` marker is registered but pytest-asyncio is NOT installed** → the first async test anyone writes
   fails at runtime with "async def functions are not natively supported" (verified), and the marker registration
   *hides* the missing-dependency signal from `strict_markers`. `anyio` 4.15.1 is already installed with a
   working pytest plugin. → install `pytest-asyncio`, or drop the marker and use `@pytest.mark.anyio`.
2. **`addopts` double-applies `-q`** → `pytest -q` suppresses the "51 passed" line entirely (pytest 9 skips
   `summary_stats()` below verbosity −1). CI logs will have no count line. → remove `-q` from `addopts`.
3. **No `filterwarnings`** → no warning policy at all; warnings are never escalated and never pinned. The suite
   is currently warning-clean, so adding a policy is free hardening.
4. **`live` marker is decorative** — zero tests use it, `-m live` yields exit code 5, and the CI workflow its
   description references **does not exist in this repo**. Also: `.pytest_cache/` is not in `.gitignore`.

**Coverage issues (5)**
5. **37 % of `src/` (20 of 54 modules) is never imported by the suite**, and the three never-imported modules are
   exactly the three that carry the known bugs: `screens/results_screen.py` (phone `AttributeError`),
   `services/report_service.py` (broken export path), `services/http_client.py` (proxy-staleness leg).
6. **All four known bugs are uncovered, and three of them are one-assertion-away from being caught:**
   phone `AttributeError` (a `dataclasses.fields` subset assertion would do it), Hudson deadlock (the only test
   is `callable(...)` — the call is never made), proxy staleness (`grep proxy tests/` → 0 hits), export path
   (`report_service` never imported).
7. **`test_phone_snapshot_row_shape_matches_email_card_contract` is a self-fulfilling test** — it asserts on a
   dict literal it builds itself, so it can never detect a shape drift.
8. **`test_cross_scan.py` tests the vendor, not the app** — upstream `user_scanner` privates
   (`_split_budget`, `_sweep_targets`) are asserted while the app's own `run_cross_scan_async` glue is only
   `callable`-checked; the coupling to upstream private API is also fragile.
9. **The only file with real regression value is `test_storage_resilience.py`** (5 tests, retry semantics, real
   monkeypatching). The rest of the suite is dominated by import smoke and existence checks (18 of 79 asserts are
   existence-style; `test_imports.py` is 100 % existence-style).

**Not a defect, but operationally important:** on Windows pytest-timeout runs in `thread` mode and responds to a
hang with `os._exit(1)` — it kills the whole pytest process. Any future test that can block (the Hudson
`input()` path is the obvious candidate) must neutralise the prompt first, or a single hang will take the whole
suite down instead of failing one test.

*(No app or test file was modified. Probe files were created only under `%TEMP%/pytest_probe` and run with
`-c pyproject.toml`; the repo working tree is unchanged by this audit.)*
