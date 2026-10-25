# pytest-timeout — dependency audit (dev-group)

Audited: 2026-10-20 · Source of truth: the installed `.venv` (no PyPI/upstream docs used).

## 1) Installed verification

| Item | Value | Evidence |
|---|---|---|
| Module | `pytest_timeout.py`, 19081 B | `.venv/Lib/site-packages/pytest_timeout.py` |
| Version | **2.4.0** | `.venv/Lib/site-packages/pytest_timeout-2.4.0.dist-info/METADATA:3` (`Version: 2.4.0`); runtime `importlib.metadata.version('pytest-timeout')` → `2.4.0` |
| Autoload | `pytest11` entry point → `timeout = pytest_timeout` | `.venv/Lib/site-packages/pytest_timeout-2.4.0.dist-info/entry_points.txt` |
| Env | Python 3.14.7, pytest 9.1.1, pluggy 1.7.0 | pytest header (`plugins: anyio-4.15.1, flet-1.0.4, timeout-2.4.0`) |

**Ini options registered** (`pytest_timeout.py:99-108`) — all four named in the task plus one extra:

- `timeout` (`:99`) — seconds; 0/absent = no timeout
- `timeout_method` (`:100`) — `signal` | `thread`
- `timeout_func_only` (`:101`) — bool, default `False`
- `timeout_disable_debugger_detection` (`:102-105`) — bool, default `False`  ← extra, undeclared in project config
- `session_timeout` (`:108`) — whole-session cap, checked only *between* tests (`:195-198`)

CLI equivalents: `--timeout` (`:71`), `--timeout-method` (`:77`), deprecated `--timeout_method` (`:72-75`), `--timeout-disable-debugger-detection` (`:85`), `--session-timeout` (`:88-94`).

**Platform detection** (`pytest_timeout.py:26-30`):

```python
HAVE_SIGALRM = hasattr(signal, "SIGALRM")
if HAVE_SIGALRM: DEFAULT_METHOD = "signal"
else:             DEFAULT_METHOD = "thread"
```

Measured on this box (Windows 11 / AMD64): `hasattr(signal, "SIGALRM")` → **False** → `HAVE_SIGALRM=False`, `DEFAULT_METHOD="thread"`. Confirmed at runtime and in the pytest header (`timeout method: thread`). On Linux CI the same code path picks `signal`.

**Expiry behaviour — thread mode** (`pytest_timeout.py:505-542`, `timeout_timer`): suspends global capture, prints captured stdout/stderr/log, calls `dump_stacks(terminal)` (`:534`, dumps every thread except the timer), then in the `finally:` block flushes and calls **`os._exit(1)`** (`:542`).

Consequences on Windows: a timeout is a **hard process kill** — exit code 1, no pytest `FAILURES` summary, no JUnit XML (the report is written after the session that `os._exit` bypasses), no fixture teardown. The stack dump is the only forensic output. Note the debug guard (`:493`, `:511`): under a debugger (pydevd/bdb) the timeout is *suppressed* entirely — irrelevant in CI, but it means a local hanging test may appear to hang forever.

Also: `signal` method is silently downgraded to `thread` when not on the main thread (`:306-311`), so the project must **not** pin `timeout_method = "signal"` in config — `signal.SIGALRM` does not exist on Windows and would raise at `:324`.

## 2) Project integration (config + live run evidence)

Config (`pyproject.toml`):

- `:68` `[tool.pytest.ini_options]`, `:71` `timeout = 60`, `:73` `strict_config = true`
- `:81-82` dev group: `pytest>=9.1.1`, `pytest-timeout>=2.4` (2.4.0 installed satisfies it)
- No competing `pytest.ini` / `setup.cfg` / `tox.ini` in the repo root.
- `tests/conftest.py` sets no timeout; no `@pytest.mark.timeout` markers anywhere in `tests/` — the global ini value is the only timeout source.

**Live run 1 — collection (proves the ini key is registered; `strict_config=true` would hard-fail on an unregistered key):**

```
.venv/Scripts/python.exe -m pytest --collect-only -q
tests/test_compat_loader.py: 6      tests/test_services.py: 7
tests/test_cross_scan.py: 8         tests/test_services_all_modes.py: 9
tests/test_imports.py: 5            tests/test_sites_catalog.py: 5
tests/test_phone_mode_parity.py: 6  tests/test_storage_resilience.py: 5
real 0m20.149s      -> exit 0, 51 tests collected
```

**Live run 2 — verbose header (proves the value is not merely registered but *applied*):**

```
platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.7.0
configfile: pyproject.toml
plugins: anyio-4.15.1, flet-1.0.4, timeout-2.4.0
timeout: 60.0s
timeout method: thread
timeout func_only: False
```

`timeout: 60.0s` comes straight from `pyproject.toml:71` via `get_env_settings` (`:352-386`, precedence CLI → `PYTEST_TIMEOUT` env → ini).

**Live run 3 — fast test with override:**

```
.venv/Scripts/python.exe -m pytest tests/test_imports.py -q --timeout 60
.....                                                    [100%]
============================== 5 passed in 1.67s ==============================
```

All three green. Integration is sound.

## 3) Timing reality (measured)

Full suite, this machine: **51 passed in 31.05s** (pytest-reported), 45.4 s wall clock.

Slowest durations (`--durations=15`):

| Test | Duration |
|---|---|
| `tests/test_compat_loader.py::test_load_user_modules_returns_pairs` | **6.97 s** |
| `tests/test_sites_catalog.py::test_load_catalog_username` | 4.79 s |
| `tests/test_services_all_modes.py::test_sherlock_load_sites_populates_mode_catalog` | 4.19 s |
| `tests/test_services.py::test_sherlock_search_returns_progress` | 3.68 s |
| `tests/test_storage_resilience.py::test_write_snapshot_gives_up_after_max_retries` | 1.46 s |
| everything else | ≤ 0.47 s |

The 6.97 s outlier is the user-modules loader — the ~4 s `user_scanner` engine import from the swarm benchmarks lives inside it. Headroom vs. the 60 s ceiling: **60 / 6.97 ≈ 8.6x**.

Scope of the timer: with `timeout_func_only = False` (the default, and what the project inherits), the timer is armed in `pytest_runtest_protocol` (`:179-194`), so it covers **setup + call + teardown** of the test, not just the call. Measured setup cost is negligible (max 0.08 s), so this widens the protected surface slightly but does not change the verdict.

Risk of a test crossing 60 s on a slow machine:

- 2x slower → 13.9 s, 4x → 27.9 s, 6x → 41.8 s: comfortable.
- ~8x slower (heavy AV scanning, cold Windows filesystem, throttled CI runner) → ~55.7 s: *under* the ceiling but with < 10 % margin.
- >8.6x slower → the user-modules test is killed.

So: **only one test is at any real risk**, and only on a machine ~8x slower than this one. The other 50 tests are ≤ 4.8 s and would need a >12x slowdown to fail. The failure mode is ugly (whole-process `os._exit(1)`, no summary, no JUnit XML), so the mitigation is to keep the outlier fast rather than to raise the ceiling.

Note also that `session_timeout` is unset, so the **total** runtime of the suite is unbounded by this plugin — the 60 s value is per-test only, and the session-level cap is a separate knob nobody has turned on.

## 4) Verdict — **PERFECT** (with two advisory notes)

The dependency is correctly installed (2.4.0, autoloaded via `pytest11`), correctly registered (`timeout` at `pytest_timeout.py:99`), correctly wired (`pyproject.toml:71` → header `timeout: 60.0s`), and verifiably in force on this platform (Windows ⇒ `thread` method via `HAVE_SIGALRM=False`, `pytest_timeout.py:26-30`). All live checks passed. `strict_config = true` did not trip, which is the strongest available proof that the ini key is a real plugin option rather than a typo.

Advisory notes (no code changes required, and none were made):

1. **Do not add `timeout_method = "signal"` to `pyproject.toml`** — `SIGALRM` does not exist on Windows (`signal.signal` at `:324` would raise). Leaving it unset gives the best of both: `signal` (clean `pytest.fail`) on Linux CI, `thread` (hard `os._exit(1)`) on Windows.
2. **Consider `timeout = 90` if CI runners are routinely slower than ~6x this machine**, or narrow the risk by splitting `test_load_user_modules_returns_pairs` so the `user_scanner` engine import is cached by a session-scoped fixture. At 60 s the current suite has 8.6x headroom on its slowest test, which is comfortable for typical dev machines and ordinary CI.
3. Cosmetic: the plugin also exposes `timeout_disable_debugger_detection` (`:102-105`), undeclared in the project config. The default (`False`) is correct — it keeps the timeout active rather than silently disabling it under a debugger.
