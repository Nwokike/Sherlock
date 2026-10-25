# Dependency Reference: `ruff` (0.17.1)

> **Package:** `ruff`  
> **Installed Version:** `0.17.1`  
> **Executable Binary:** `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Scripts/ruff.exe`  
> **Python Package Location:** `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/ruff`  
> **Dist-Info Directory:** `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/ruff-0.17.1.dist-info`  
> **Sherlock-V2 Dependency:** `/home/maikel/.zcode/workspace/default/Sherlock-V2/pyproject.toml:24` (`ruff>=0.17.1`)  
> **Original Sherlock Reference:** `/home/maikel/.zcode/workspace/default/Sherlock/pyproject.toml:95, 98-125` (`ruff>=0.15.14`)  
> **Original Sherlock CI Gate:** `/home/maikel/.zcode/workspace/default/Sherlock/.github/workflows/build-all.yml:110-111`  

---

## 1. Package Metadata & Architecture

### 1.1 Overview
`ruff` is an extremely fast Python linter and code formatter written in Rust by Astral Software Inc. It reimplements dozens of upstream Python linting suites (Flake8, Pyflakes, pycodestyle, isort, pydocstyle, pyupgrade, bandit, flake8-bugbear, tryceratops, etc.) as an integrated native AST analysis engine.

- **PyPI Package:** `ruff`
- **Installed Version:** `0.17.1` (`METADATA:3`)
- **Author:** Astral Software Inc. (`METADATA:26`)
- **License:** MIT (`METADATA:27`, `licenses/LICENSE`)
- **Python Compatibility:** `>=3.7` (`METADATA:28`), with official classifiers spanning Python 3.7 through 3.15 (`METADATA:9-17`).
- **Target Runtime in Sherlock-V2:** Python `3.14` (`Sherlock-V2/.python-version:1`, `Sherlock-V2/pyproject.toml:6`).

### 1.2 Binary Distribution & Python Wrapper Structure
The Python distribution is a thin bootstrap wrapper around a pre-compiled Rust binary:

1. **Native Binary:**
   - Path: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Scripts/ruff.exe`
   - Wheel tag: `py3-none-win_amd64.whl` (size ~10.1 MB, SHA-256 `5df76f16580fab58d0f6c98a3ac254a4abceb7b2489b8b678335869cff77b3d7`).
2. **Package Entrypoint (`ruff/__init__.py:1-6`):**
   ```python
   from __future__ import annotations
   from ._find_ruff import find_ruff_bin

   __all__ = ["find_ruff_bin"]
   ```
3. **Execution Dispatcher (`ruff/__main__.py:9-24`):**
   - On Windows (`sys.platform == "win32"`), executes `subprocess.run([find_ruff_bin(), *sys.argv[1:]], check=False)` to catch `KeyboardInterrupt` gracefully (`__main__.py:12-21`).
   - On POSIX platforms, delegates via `os.execvp(ruff, [ruff, *sys.argv[1:]])` (`__main__.py:23`).
4. **Binary Resolution (`ruff/_find_ruff.py:11-56`):**
   Searches for `ruff.exe` across:
   - `sysconfig.get_path("scripts")`
   - `sysconfig.get_path("scripts", vars={"base": sys.base_prefix})`
   - Platform prefix directories (e.g. `<prefix>/Lib/site-packages/ruff/../../Scripts` on Windows)
   - User scheme directories (e.g. `nt_user` / `posix_user`).

---

## 2. Linter Engine & Rule System

Ruff 0.17.1 natively evaluates lint rules in parallel using a unified AST parser, providing speed improvements of 10-100x over traditional multi-tool python linter chains.

### 2.1 Core CLI Commands & Flags
- **Lint Execution:**
  - `ruff check .`: Check files in current project for rule violations.
  - `ruff check . --statistics`: Count and display violations grouped by rule code.
  - `ruff check . --fix`: Automatically apply safe fixes where available.
  - `ruff check . --fix --unsafe-fixes`: Apply all fixes, including potentially behavior-altering fixes.
  - `ruff check . --diff`: Show preview of automated fixes as a diff without modifying files.
  - `ruff check --show-settings <file>`: Inspect resolved configuration, cache paths, and rule lists.
- **Rule Inspection:**
  - `ruff rule <CODE>`: Output detailed Markdown documentation and examples for a rule (e.g., `ruff rule S101`).
  - `ruff linter`: Print all supported upstream linters and their code prefixes.

### 2.2 Rule Prefixes Selected in Sherlock
The original Sherlock project activates 21 upstream rule domains in `pyproject.toml:99-102`:

| Prefix | Upstream Linter | Core Purpose & Scope |
| :--- | :--- | :--- |
| **`E`** | `pycodestyle` (errors) | Syntax errors, indentation, whitespace, and structural errors. |
| **`F`** | `Pyflakes` | Logical errors, undefined names, unused variables, and unused imports. |
| **`W`** | `pycodestyle` (warnings) | Formatting warnings (tab characters, trailing whitespace). |
| **`UP`** | `pyupgrade` | Syntax modernization (e.g. modern union syntax `A \| B`, f-string cleanups). |
| **`B`** | `flake8-bugbear` | Detection of common bug patterns, mutable default parameters, and design flaws. |
| **`Q`** | `flake8-quotes` | Enforces string literal quote consistency. |
| **`C4`** | `flake8-comprehensions` | Replaces redundant `list()`, `dict()`, or `set()` generator wrappers with comprehension syntax. |
| **`PERF`** | `Perflint` | Identifies Python performance anti-patterns (e.g., list allocations in loops). |
| **`ERA`** | `eradicate` | Scans for and bans dead/commented-out code blocks. |
| **`I`** | `isort` | Automatic import sorting, grouping (standard library, third-party, local), and formatting. |
| **`T20`** | `flake8-print` | Flags `print()` (`T201`) and `pprint()` (`T203`) to ensure production code uses logging services. |
| **`DTZ`** | `flake8-datetimez` | Requires timezone-aware datetimes; forbids naive `datetime.now()` without tz. |
| **`RUF`** | `Ruff` (internal) | Ruff-specific optimizations, unused `# noqa` directive detection, and ambiguous unicode checks. |
| **`S`** | `flake8-bandit` | Static security scanner (detects insecure hashes, `eval()`, weak ciphers, and hardcoded keys). |
| **`TRY`** | `tryceratops` | Audits `try`/`except` block organization and prevents exception anti-patterns. |
| **`BLE`** | `flake8-blind-except` | Flags catching unqualified `Exception` (`BLE001`). |
| **`EM`** | `flake8-errmsg` | Governs exception error message construction (f-strings vs exception classes). |
| **`A`** | `flake8-builtins` | Prevents shadowing of standard Python builtins in variables, functions, and parameters. |
| **`SIM`** | `flake8-simplify` | Streamlines control flow, nested if statements, and redundant expressions. |
| **`RET`** | `flake8-return` | Enforces consistent return statement structures. |
| **`RSE`** | `flake8-raise` | Enforces clean `raise` syntax (e.g., removing unnecessary parentheses from exception classes). |

---

## 3. Code Formatter Engine (`ruff format`)

Ruff 0.17.1 includes a built-in code formatter designed as a drop-in replacement for `Black`. It formats Python source code with strict consistency and zero external dependencies.

### 3.1 Formatter Configuration Options
Configurable in `pyproject.toml` under `[tool.ruff.format]`:

- **`line-length` (Default: `88`):** Maximum column target for line wrapping (standard Black default).
- **`indent-style` (Default: `"space"`):** Choice of `"space"` or `"tab"`.
- **`indent-width` (Default: `4`):** Number of spaces per indentation level.
- **`quote-style` (Default: `"double"`):** Preferred quote style (`"double"`, `"single"`, or `"preserve"`).
- **`nested-string-quote-style` (Default: `"double"`):** Quote style for triple-quoted strings or inner strings.
- **`skip-magic-trailing-comma` (Default: `false`):** When `false`, a trailing comma forces a multi-line wrap (Black style).
- **`line-ending` (Default: `"auto"`):** Normalizes line endings (`"lf"`, `"crlf"`, `"cr"`, or `"native"`).
- **`docstring-code-format` (Default: `false`):** Formats Python code snippets embedded inside docstrings when enabled.

### 3.2 Formatter CLI Usage
- **Format codebase:** `ruff format .`
- **Check format status (CI gate):** `ruff format --check .` (returns non-zero exit code if unformatted files exist).
- **Format diff inspection:** `ruff format --diff .`

### 3.3 Formatter Interaction with Linter Rules
- **Line Length (`E501`):** Ruff recommends disabling `E501` (`pycodestyle` line length) when using `ruff format`, because the formatter automatically breaks long expressions where possible, while comments, long regexes, and URLs cannot always be wrapped cleanly without harming readability.
- **Import Sorting (`I` / `isort`):** Import sorting is handled by `ruff check --select I --fix`, which coordinates seamlessly with `ruff format`.

---

## 4. Original Sherlock Ruff Configuration Analysis

Original Sherlock's configuration is located in `Sherlock/pyproject.toml:98-125`.

### 4.1 Verbatim Configuration (`Sherlock/pyproject.toml:98-125`)
```toml
[tool.ruff.lint]
select = [
    "E", "F", "W", "UP", "B", "Q", "C4", "PERF", "ERA", "I", "T20", "DTZ", "RUF",
    "S", "TRY", "BLE", "EM", "A", "SIM", "RET", "RSE",
]
ignore = [
    "E501",
    # Message-string style: this app raises with inline human messages on
    # purpose (owner rule: visible, specific errors); classes-per-message
    # would be churn with no behavioral gain.
    "EM101", "EM102", "EM103", "TRY003",
    # Wide-except + log (BLE001) and silent best-effort no-ops (S110,
    # SIM105) are the documented owner pattern across services/UI: cleanup,
    # restore, and persist paths intentionally pass on failure while every
    # load-bearing path logs. Narrowing 200+ sites is regression churn.
    "BLE001", "S110", "SIM105",
    # TRY300/TRY301 are style-only reshuffles inside engine hot paths
    # (email/sherlock) — churn risk with zero behavioral gain.
    "TRY300", "TRY301",
]

[tool.ruff.lint.per-file-ignores]
# Tests assert by design (pytest); S105 is a storage-KEY name, not a secret.
"tests/**" = ["S101"]
# `id` mirrors the flet_notifications.show/cancel signature it stands in
# for; renaming it would hide the correspondence.
"src/services/scan_notify.py" = ["A002"]
```

### 4.2 Architectural Justification of Ignored Rules (Citing File:Line)

#### 1. Line Length Ignored (`pyproject.toml:104`)
- **`E501`:** Ignored to allow long inline strings, structured error messages, regex patterns, and network URLs without artificial line breaks. Formatting is maintained by `ruff format`.

#### 2. Exception Message Strings (`pyproject.toml:105-108`)
- **Rules:** `EM101`, `EM102`, `EM103`, `TRY003`
- **Owner Rationale:**
  > *"Message-string style: this app raises with inline human messages on purpose (owner rule: visible, specific errors); classes-per-message would be churn with no behavioral gain."* (`pyproject.toml:105-107`)
- **Technical Context:**
  - `EM101`: Exception must not use a string literal, assign to variable first.
  - `EM102`: Exception must not use an f-string literal, assign to variable first.
  - `EM103`: Exception must not use a `.format()` string.
  - `TRY003`: Avoid specifying long messages outside the exception class.
  Sherlock intentionally constructs descriptive human-facing exception messages at the call site (e.g., `raise ValueError(f"Unknown target network: {network}")`).

#### 3. Wide Exception Handling & Silent Best-Effort Cleanup (`pyproject.toml:109-113`)
- **Rules:** `BLE001`, `S110`, `SIM105`
- **Owner Rationale:**
  > *"Wide-except + log (BLE001) and silent best-effort no-ops (S110, SIM105) are the documented owner pattern across services/UI: cleanup, restore, and persist paths intentionally pass on failure while every load-bearing path logs. Narrowing 200+ sites is regression churn."* (`pyproject.toml:109-112`)
- **Technical Context:**
  - `BLE001`: Do not catch blind exception `Exception`.
  - `S110`: `try`-`except`-`pass` detected, consider logging the exception.
  - `SIM105`: Use `contextlib.suppress(...)` instead of `try`-`except`-`pass`.
  In GUI services and network workers, non-critical teardown, local cache flushes, and background widget updates must not crash the UI loop when an unexpected network or OS glitch occurs. Critical paths log, while peripheral cleanup intentionally passes.

#### 4. Try/Else Flow Control (`pyproject.toml:114-116`)
- **Rules:** `TRY300`, `TRY301`
- **Owner Rationale:**
  > *"TRY300/TRY301 are style-only reshuffles inside engine hot paths (email/sherlock) — churn risk with zero behavioral gain."* (`pyproject.toml:114-115`)
- **Technical Context:**
  - `TRY300`: Consider moving this statement to an `else` block.
  - `TRY301`: Abstract `raise` to an inner function.
  These rules enforce stylistic restructuring that does not alter semantics but introduces churn and potential regression risks in performance-sensitive scan routines.

### 4.3 Per-File Ignores (`pyproject.toml:119-125`)
- **`"tests/**" = ["S101"]` (`pyproject.toml:120-121`):**
  - `S101`: Use of `assert` detected. In `pytest`, `assert` statements are the idiomatic mechanism for test validations. Bandit flags `assert` because Python's `-O` flag strips asserts, but test suites are run under standard test runners where asserts are necessary.
- **`"src/services/scan_notify.py" = ["A002"]` (`pyproject.toml:122-124`):**
  - `A002`: Function argument `id` shadows Python builtin `id`.
  - The argument `id` was retained to directly mirror the parameter name of `flet_notifications.show(id=...)` and `flet_notifications.cancel(id=...)`.

### 4.4 CI Integration in Sherlock (`Sherlock/.github/workflows/build-all.yml:110-111`)
In Sherlock's multi-platform CI quality gate:
```yaml
      - name: Lint (ruff)
        run: uv run ruff check . --statistics
```
The quality job runs before any artifact build (Android APK/AAB, Windows installer, Linux deb/rpm). A single lint failure halts the pipeline.

---

## 5. Configuration Mirroring Specification for Sherlock-V2

### 5.1 Sherlock-V2 Current State
In `/home/maikel/.zcode/workspace/default/Sherlock-V2/pyproject.toml:22-25`:
```toml
[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "ruff>=0.17.1",
]
```
Currently, `Sherlock-V2/pyproject.toml` has pinned `ruff>=0.17.1` in the dev dependency group, but the `[tool.ruff.lint]` table has not yet been populated.

### 5.2 Target `pyproject.toml` Configuration for Sherlock-V2
To preserve full architectural consistency, code hygiene standards, and owner conventions from Sherlock, Sherlock-V2 should adopt the following configuration in `Sherlock-V2/pyproject.toml`:

```toml
[tool.ruff]
target-version = "py314"

[tool.ruff.lint]
select = [
    "E", "F", "W", "UP", "B", "Q", "C4", "PERF", "ERA", "I", "T20", "DTZ", "RUF",
    "S", "TRY", "BLE", "EM", "A", "SIM", "RET", "RSE",
]
ignore = [
    "E501",
    # Message-string style: this app raises with inline human messages on
    # purpose (owner rule: visible, specific errors); classes-per-message
    # would be churn with no behavioral gain.
    "EM101", "EM102", "EM103", "TRY003",
    # Wide-except + log (BLE001) and silent best-effort no-ops (S110,
    # SIM105) are the documented owner pattern across services/UI: cleanup,
    # restore, and persist paths intentionally pass on failure while every
    # load-bearing path logs. Narrowing 200+ sites is regression churn.
    "BLE001", "S110", "SIM105",
    # TRY300/TRY301 are style-only reshuffles inside engine hot paths
    # (email/sherlock) — churn risk with zero behavioral gain.
    "TRY300", "TRY301",
]

[tool.ruff.lint.per-file-ignores]
# Tests assert by design (pytest); S105 is a storage-KEY name, not a secret.
"tests/**" = ["S101"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "auto"
```

### 5.3 Sherlock-V2 Implementation Notes
1. **Target Version:** Set `target-version = "py314"` matching `Sherlock-V2`'s Python 3.14 baseline (`requires-python = ">=3.14"` at `pyproject.toml:6`). Ruff 0.17.1 fully supports `py314` syntax upgrades and optimizations.
2. **`T20` (flake8-print) Enforcement:**
   Sherlock-V2's placeholder `src/sherlock_v2/__init__.py:2` currently contains `print("Hello from sherlock-v2!")`, which triggers `T201 (print)`. All production code in Sherlock-V2 must use structured logging services instead of raw `print` calls once the lint config is active.
3. **Per-File Ignores Adaptation:**
   - `"tests/**" = ["S101"]` must be mirrored immediately for pytest suite compatibility.
   - The `"src/services/scan_notify.py" = ["A002"]` ignore from original Sherlock was specific to the notification service wrapping `flet_notifications`. If Sherlock-V2 adopts a different notification or scanning abstraction, file-specific ignores should only be added for documented foreign API parameter matching.
4. **CI Workflow Parity:**
   Sherlock-V2's CI configuration should execute:
   ```bash
   uv run ruff check . --statistics
   uv run ruff format --check .
   ```
   to enforce both lint rules and format standards before running tests.
