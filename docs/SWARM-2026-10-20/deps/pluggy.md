# pluggy 1.7.0 — dependency audit

**Scope:** transitive via pytest only. App never imports it. Verdict: **N/A** (test tooling).

## 1) Installed verification

- Version confirmed two ways: `pluggy/__init__.py:32-38` resolves `__version__` lazily via
  `importlib.metadata.version("pluggy")`; `pluggy-1.7.0.dist-info/METADATA:2-4` reads
  `Name: pluggy` / `Version: 1.7.0` / `Summary: plugin and hook calling mechanisms for python`
  (`License: MIT` at :7, `Requires-Python: >=3.10` at :32).
- Install is pure-Python, uv-managed: `pluggy-1.7.0.dist-info/RECORD:8-20` lists 12 `.py`
  modules + `py.typed`; `INSTALLER` and `REQUESTED` present; no compiled artifacts.
- Public API surface `pluggy/__init__.py:1-16` (`__all__`): `HookCallError`, `HookCaller`,
  `HookImpl`, `HookRelay`, `HookimplMarker`, `HookimplOpts`, `HookspecMarker`, `HookspecOpts`,
  `PluggyTeardownRaisedWarning`, `PluggyWarning`, `PluginManager`, `PluginValidationError`,
  `Result`, `__version__`.
- Hooksystem basics are all present and reachable:
  - `HookspecMarker` — defined `pluggy/_decorators.py:30`, re-exported `pluggy/_hooks.py:22`
  - `HookimplMarker` — defined `pluggy/_decorators.py:117`, re-exported `pluggy/_hooks.py:20`
  - `PluginManager` — defined `pluggy/_manager.py:141`, exported `pluggy/__init__.py:24`
  - `PluginManager` API: `register` (`_manager.py:185`), `add_hookspecs` (`:344`),
    `check_pending` (`:481`), `load_setuptools_entrypoints` (`:497`)
  - `pluggy/_hooks.py:29-47` is a re-export facade; real code lives in `_caller.py`
    (`HookCaller`/`HookRelay`/`_HookExec`), `_impl.py` (`HookImpl`/`_Plugin`), `_config.py`
    (`HookimplOpts`/`HookspecOpts`).

## 2) Consumers + this project's conftest facts

- **Sole consumer in the venv is `_pytest`.** Repo-wide grep of
  `.venv/Lib/site-packages/**/*.py` for `import pluggy` / `from pluggy` returns matches in
  `_pytest` only: `_pytest/config/__init__.py:42-46` (HookimplMarker, HookimplOpts,
  HookspecMarker, HookspecOpts, PluginManager), `_pytest/hookspec.py:14` (HookspecMarker),
  plus plain `import pluggy` at `_pytest/_code/code.py:34`, `_pytest/main.py:25`,
  `_pytest/nodes.py:22`, `_pytest/subtests.py:19`, `_pytest/terminal.py:32`.
  pytest subclasses it at `_pytest/config/__init__.py:460` (`class PytestPluginManager(PluginManager)`).
- **No other consumer.** The only dist-info METADATA files in the venv mentioning pluggy are
  pluggy's own and `pytest-9.1.1.dist-info/METADATA:37` (`Requires-Dist: pluggy<2,>=1.5`).
  **briefcase is not installed in this venv** (no `briefcase*` in site-packages), so it is not a
  consumer. `pytest_timeout` 2.4.0 is installed but does not import pluggy.
- **Project's own tests define no plugins/hooks.** Grep of `tests/` and `src/` for
  `hookimpl|hookspec|pytest_configure|pytest_addoption|pytest_plugins|PluginManager|import pluggy`
  → **zero matches**. The 8 test modules (`test_compat_loader`, `test_cross_scan`, `test_imports`,
  `test_phone_mode_parity`, `test_services`, `test_services_all_modes`, `test_sites_catalog`,
  `test_storage_resilience`) are plain pytest functions.
- **`tests/conftest.py` is 6 lines and does only a sys.path shim** — docstring
  `"Test configuration for Sherlock-V2."` (:1), `import sys` (:3), `from pathlib import Path` (:4),
  `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))` (:6). No fixtures,
  no hooks, no `pytest_plugins`, no plugin registration. It is the **only** conftest.py in the
  repo (excluding `.venv`).
- Pytest is configured via `pyproject.toml:68-77` (`pythonpath = ["src"]`, `addopts = ["-ra","-q"]`,
  `timeout = 60`, `strict_markers`, `strict_config`, custom markers `live`/`asyncio`);
  dev group `pyproject.toml:79-83` pins `pytest>=9.1.1`, `pytest-timeout>=2.4`, `ruff>=0.17.1`.

## 3) App usage: none

- `src/` (assets, components, core, hooks, screens, services, state) contains **no pluggy import**
  (grep clean). `src/hooks/` is the app's own UI/event-hook directory — unrelated naming.
- Repo-wide grep for `pluggy` outside `.venv/` hits **documentation only**:
  `docs/reference/dep-pytest-stack.md`, `docs/reference/README.md`,
  `docs/SWARM-2026-10-20/dependency-tree.md`. No code references.
- pluggy is thus a **test-runtime-only** dependency: it loads inside pytest's plugin manager to
  dispatch pytest's own hook phases. It is never on the app's import path and never ships.

## 4) Verdict: N/A

- **App runtime impact: none.** No app import, no runtime dependency, nothing to stub, mock, or
  vendor. Safe to leave as a pure pytest transitive.
- **Only if the project ever defines its own pytest plugin** (i.e. starts using
  `pytest_configure` / `@pytest.hookimpl` / a `pytest_plugins` entry) would pluggy become a
  direct concern. Today it does not.
- No action required; no app files modified.
