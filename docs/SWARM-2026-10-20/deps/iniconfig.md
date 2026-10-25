# Dependency Audit: `iniconfig` 2.3.1

**Scope:** transitive dependency of `pytest` only (dev dependency-group). Never used by app code.
**Verdict: N/A — dev-only, no app role; removal is not actionable without removing pytest.**

## 1) Installed verification

- Installed at `.venv/Lib/site-packages/iniconfig/` — package dir containing `__init__.py`, `_parse.py`,
  `_version.py`, `exceptions.py`, `py.typed` (typed, pure-Python, zero runtime deps).
- Version string: `.venv/Lib/site-packages/iniconfig/_version.py:22` → `__version__ = version = '2.3.1'`.
  Matches `.venv/Lib/site-packages/iniconfig-2.3.1.dist-info/METADATA:3` → `Version: 2.3.1`.
- `iniconfig-2.3.1.dist-info/METADATA:22` → `Requires-Python: >=3.10`; **no `Requires-Dist` at all** — the
  package is fully self-contained and pulls in nothing further.
- Lockfile entry `uv.lock:237-242`: `name = "iniconfig"`, `version = "2.3.1"`, registry source, universal
  `iniconfig-2.3.1-py3-none-any.whl` (sha256 `9121e2c1…`).
- Dependency chain: `pyproject.toml:79-84` `[dependency-groups] dev = ["pytest>=9.1.1", "pytest-timeout>=2.4",
  "ruff>=0.17.1"]` → `pytest` 9.1.1 (`uv.lock:390-401`) with `{ name = "iniconfig" }` at `uv.lock:396`.
  pytest's own metadata agrees: `.venv/Lib/site-packages/pytest-*.dist-info/METADATA:35` →
  `Requires-Dist: iniconfig>=1.0.1`.

## 2) Sole importer in this venv

- Grepping all of `.venv/Lib/site-packages/**/*.py` for `iniconfig` returns exactly **three** files, all
  inside pytest: `_pytest/config/findpaths.py:13`, `_pytest/legacypath.py:14`, `_pytest/pytester.py:39-40`.
  **No other installed package imports iniconfig** (it is a leaf: nothing imports *it*).
- `_pytest/config/findpaths.py:13` → `import iniconfig`; used via the helper
  `findpaths.py:46-55` `_parse_ini_config(path) -> iniconfig.IniConfig`, which is called from
  `findpaths.py:67` (`.ini` files) and `findpaths.py:81` (`.cfg` files) only.
- `_pytest/legacypath.py:14` → `from iniconfig import SectionWrapper`, consumed once at
  `legacypath.py:115` `getinicfg(self, source)` — the legacy `type = path` / `py` ini-option resolver.
  The project's config defines no `py` option, so this path is unreachable for this repo.
- `_pytest/pytester.py:39-40` → `from iniconfig import IniConfig, SectionWrapper`, used only by the
  optional `pytester` plugin. The project never enables it (`pyproject.toml:70` `addopts = ["-ra", "-q"]`;
  no `-p pytester`), and no `pytester` reference exists in `pyproject.toml` or `src/`.

### pyproject.toml is parsed by tomllib, not iniconfig

- `findpaths.py:96-106`: any `.toml` config takes the TOML branch — `import tomllib` (Python ≥3.11,
  line 98; `tomli` fallback, line 100) then `tomllib.loads(toml_text)` at line 104. **No iniconfig
  involvement.**
- `findpaths.py:120-153` handles `pyproject.toml`: reads `tool.pytest` (line 122), splits
  `ini_options` (line 127), and for ini-mode values converts scalars to `str` via `make_scalar`
  (lines 147-152), tagging the result `mode="ini"`.
- The project's config lives at `pyproject.toml:68` → `[tool.pytest.ini_options]` (`pythonpath = ["src"]`,
  `addopts = ["-ra", "-q"]`, `timeout = 60`, `strict_markers = true`, `strict_config = true`,
  `markers = [...]`). That is the **TOML branch** (`findpaths.py:144-153`), i.e. parsed by `tomllib`.
- iniconfig is only reached for legacy INI-family files: `pytest.ini` / `tox.ini` (`.ini` suffix,
  `findpaths.py:66-77`, section `[pytest]`) and `setup.cfg` (`.cfg` suffix, `findpaths.py:80-91`, section
  `[tool:pytest]`). **None of these exist in the repo root** — no `pytest.ini`, `setup.cfg`, `tox.ini`,
  `pytest.toml` or `.pytest.toml`. So for this project the iniconfig code path is never executed at all.

## 3) App usage: none

- Grep of the whole project tree (excluding `.venv/`) for `iniconfig` returns matches **only in
  `uv.lock`** (`uv.lock:237`, `:240`, `:242`, `:396`). No `.py` source file imports it; `src/` and `tests/`
  are clean.
- `pyproject.toml` declares no direct dependency on iniconfig — it is reachable solely through the `dev`
  dependency-group's `pytest`.
- The app should never import `iniconfig`: it is an INI-only parser, the app's config is TOML
  (`[tool.pytest.ini_options]`), and app runtime configuration is handled elsewhere.

## 4) Verdict (N/A)

**`iniconfig` has no role in Sherlock-V3 outside the test toolchain.** It is a hard, declared dependency of
pytest (`Requires-Dist: iniconfig>=1.0.1`), and pytest itself is dev-group-only. Even more to the point,
the project's pytest configuration is `[tool.pytest.ini_options]` in `pyproject.toml`, which the installed
pytest parses with `tomllib` (`findpaths.py:96-106`, `:144-153`) — iniconfig is only consulted for legacy
`pytest.ini` / `tox.ini` / `setup.cfg` files, none of which this repo has. The package is a typed, zero-
dependency leaf, so it adds no transitive surface either. **Verdict: N/A — no action. Dev-only, no app role,
and removal is not possible without removing pytest.** Keep iniconfig out of app code.
