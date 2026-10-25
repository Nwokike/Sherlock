# Dependency Audit: `typing-extensions`

**Package:** `typing-extensions` 4.16.0
**Verdict:** **N/A** for Sherlock-V3 application code (present transitively via `anyio`; must stay installed)

---

## 1) Installed verification

**Version — confirmed from the venv (the only source of truth):**
- `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/typing_extensions.py` (single-file module, no package dir)
- `...\site-packages\typing_extensions-4.16.0.dist-info\METADATA` → `Version: 4.16.0`, `Requires-Python: >=3.9`, classifier `Programming Language :: Python :: 3.14`
- Module has **no `__version__` attribute** (`grep __version__` → no hits); version lives only in the dist-info.

**Interpreter it runs against:**
- venv Python is **3.14.7**; stdlib `typing` resolves to
  `/home/maikel/AppData/Roaming/uv/python/cpython-3.14-windows-x86_64-none/Lib/typing.py`
- `pyproject.toml:6` → `requires-python = ">=3.14"`

**Why it is installed (dependency chain):**
- `anyio-4.15.1.dist-info\METADATA` → `Requires-Dist: typing_extensions>=4.16.0; python_version < "3.15"` ← **the binding pin** (3.14 satisfies `< "3.15"`)
- `flet-1.0.4.dist-info\METADATA:18` → `Requires-Dist: typing-extensions; python_version < "3.11"` → **inert on 3.14**
- `curl_cffi-0.16.3` requires it only under its `dev`/`test` extras → **inert at runtime**
- App-declared deps (`pyproject.toml:7-12`): `flet`, `flet-ads`, `user-scanner`, `phonsint` — **`typing-extensions` is not a direct dependency.**

**What TE exports that Python 3.14's `typing` lacks** (measured: 17 `te.__all__` names absent from `typing`):
`Buffer`, `Reader`, `Writer`, `deprecated`, `disjoint_base`, `Doc`, `Format`, `get_annotations`, `get_original_bases`, `IntVar`, `sentinel`, `Sentinel`, `runtime`, `TypeForm`, `type_repr`, `NoExtraItems`, `CapsuleType`
- Genuinely useful gaps: `Doc` (PEP 727), `sentinel`/`Sentinel` (PEP 661), `TypeForm` (PEP 747 preview), `disjoint_base`, `get_original_bases`, `get_annotations`, `IntVar`.
- `Buffer` → `typing_extensions.Buffer` is `collections.abc.Buffer` (PEP 688); note `typing.Buffer` does **not** exist in this 3.14.7 stdlib.
- `deprecated` → on this interpreter `typing_extensions.deprecated is warnings.deprecated` (source `typing_extensions.py:3015-3016`, branch `sys.version_info >= (3, 14, 1)`), so it adds nothing over `warnings.deprecated`.
- `runtime` → alias of `runtime_checkable` (`typing_extensions.py:960`).

**What TE merely re-exports (no value over stdlib on 3.14):** `Self` (`:2429-2430`), `override` (`:2972-2973`), `Unpack`, `TypeIs`, `ReadOnly`, `dataclass_transform`, `runtime_checkable`, `get_protocol_members`, `is_protocol`, `NoDefault`, `TypeVar`, `ParamSpec`, `Literal`, `Protocol`, `NamedTuple` — all verified **SAME-OBJ** as `typing.*`. `TypeVarTuple` and `TypeAliasType` are **DISTINCT** wrapper objects (TE subclasses to add PEP 696 defaults, `typing_extensions.py:2652-2670`) but stdlib 3.14 already supports `TypeVarTuple(default=...)`.

**Already in 3.14 stdlib `typing` (verified `hasattr`):** `Self`, `TypeVarTuple`, `Unpack`, `override`, `Protocol`, `TypedDict`, `NamedTuple`, `ClassVar`, `Literal`, `ParamSpec`, `TypeAlias`, `TypeGuard`, `Never`, `assert_type`, `dataclass_transform`, `TypeIs`, `ReadOnly`, `Concatenate`.
**Absent from stdlib `typing`:** `Buffer`, `Doc`, `TypeIsType`.

---

## 2) App typing-usage facts (file:line)

**`typing_extensions` is never imported by the app.** `grep -rn "typing_extensions" src/ tests/` → **0 matches (exit 1)**. A repo-wide scan (`--include=*.py`, excluding `.venv`) confirms it.

Complete set of `typing` imports across 63 `src/*.py` + 9 `tests/*.py` files — only 10 lines, all stdlib:

| File:line | Import | Notes |
|---|---|---|
| `src\main.py:22` | `Any` | `self._pending_progress: Any \| None` (`:154`) |
| `src\core\logger_handler.py:10` | `ClassVar` | `_logs: ClassVar[collections.deque[str]]` (`:24`) |
| `src\core\tasks.py:13` | `Any` | `Coroutine[Any, Any, Any]` (`:18`) |
| `src\services\cache_service.py:38` | `Any` | many `Any` payloads |
| `src\services\enrich_service.py:9` | `Any` | |
| `src\services\phone_service.py:15` | `Any` | |
| `src\services\email_service.py:16` | `Any` | |
| `src\services\user_scanner_compat.py:23` | `Any` | |
| `src\services\sherlock_service.py:16` | `Any` | |
| `src\screens\results_screen.py:15` | `NamedTuple` | `class _UsernameViewData(NamedTuple)` (`:35`) |

**Absent from the app entirely:** `Protocol`, `TypedDict`, `Self`, `override`, `TypeVar`, `ParamSpec`, `Generic`, `Literal`, `Final`, `cast`, `TYPE_CHECKING`, `TypeAlias`, `runtime_checkable`, `get_origin`/`get_args`.
**No hand-rolled reimplementations:** zero `Protocol` subclasses, zero `__init_subclass__`/`__class_getitem__`/`ABCMeta`/`abstractmethod` constructs in `src/`; no `types.py`/`protocols.py`/`models.py` module.
**No obsolete typing patterns:** no `typing.List`/`Dict`/`Tuple`/`Optional`/`Type` legacy aliases (the one grep hit on `results_screen.py:15` is `NamedTuple`, a false positive); `from __future__ import annotations` appears in ~36 files and is valid/redundant-but-harmless on 3.14.

**Conclusion:** every typing construct the app uses (`Any`, `ClassVar`, `NamedTuple`) is native to Python 3.14 stdlib `typing`. There is **nothing** `typing_extensions` provides that the app is currently hand-rolling, and nothing the app imports from it.

---

## 3) Any small improvements

Neither requires `typing_extensions`; both use stdlib 3.14 features. **No app files were modified.**

1. **`src\core\logger_handler.py:34`** — `MemoryLogHandler.emit` overrides `logging.Handler.emit` without a marker. Stdlib `typing.override` (3.12+, and `typing_extensions.override` is the *same object*) would catch signature drift:
   ```python
   from typing import override
   @override
   def emit(self, record: logging.LogRecord) -> None:
   ```
   This is the only override site in the app, so the payoff is small.
2. **`src\screens\results_screen.py:35-47`** — `_UsernameViewData` declares bare `found: list`, `not_found: list`, `errors: list`. Parameterising them (`list[str]` / `list[Any]`) would give the render path real type information; a `NamedTuple` is the right choice here and needs no backport.
3. **Not worth doing:** adopting `typing_extensions` in app code would be a downgrade on 3.14 — every relevant symbol (`Self`, `override`, `TypeVarTuple`, `Unpack`, `TypeIs`, `ReadOnly`, `dataclass_transform`) is already in stdlib `typing` and TE's `TypeVarTuple` is a distinct wrapper object rather than the stdlib one.

---

## 4) Verdict

**N/A** — Sherlock-V3 application code should **not** use `typing-extensions`:

- The app never imports it (0 hits in `src/` + `tests/`).
- It targets `requires-python = ">=3.14"` (`pyproject.toml:6`) and runs on 3.14.7, where the stdlib `typing` module already provides `Self`, `TypeVarTuple`, `Unpack`, `override`, `Protocol`, `TypedDict`, `TypeIs`, `ReadOnly` and the rest.
- Its only genuine use would be for PEP 727 `Doc`, PEP 661 `sentinel`, PEP 747 `TypeForm` or `disjoint_base` — none of which the app needs.
- **Do not remove it from the venv:** `anyio` 4.15.1 pins `typing_extensions>=4.16.0` for `python_version < "3.15"`, and 3.14 satisfies that marker, so it is a hard transitive runtime requirement of the Flet/anyio stack.
- Optional, non-blocking polish only: add `@override` at `src\core\logger_handler.py:34` and parameterise the `list` fields at `src\screens\results_screen.py:45-47`.
