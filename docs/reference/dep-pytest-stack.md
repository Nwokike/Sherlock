# Pytest 9.1.1 & Testing Stack Dependency Study & Architecture Reference

## Executive Summary

`pytest` is the industry-standard testing framework for Python, providing declarative test discovery, rich assertion introspection via AST rewriting, modular dependency-injected fixtures, parameter multiplication, and an extensible plugin architecture. In **Sherlock-V2**, pytest is installed as version **9.1.1** within the virtual environment at `.venv\Lib\site-packages\pytest` and `_pytest`.

Pytest does not operate in isolation; it is built upon a tightly coordinated ecosystem of four core micro-dependencies, plus Windows-specific terminal helpers:
1. **`iniconfig` (2.3.1)**: High-speed, zero-dependency parser for INI-style configuration files, section tracking, and line-numbered syntax diagnostics.
2. **`packaging` (26.3)**: PyPA core library for PEP 440 version parsing, PEP 508 dependency specification validation, and plugin environment constraints.
3. **`pluggy` (1.7.0)**: The hook calling and plugin management engine originated by the pytest team, facilitating 1:N fan-out hook dispatch, hook wrappers, and priority chains.
4. **`pygments` (2.21.0)**: Syntax highlighting engine used by pytest's terminal reporter to colorize Python code tracebacks and assertion comparison diffs.
5. **`colorama` (0.4.6)**: Windows ANSI terminal emulation layer ensuring colored test reporting across legacy and modern Windows consoles (`sys_platform == "win32"`).

In addition to the core test runner, this reference analyzes the test timeout engine (`pytest-timeout` 2.4.0) used in the original Sherlock project to enforce a hard 60-second ceiling per test. This reference documents the internal execution mechanics of pytest 9.1.1, its markers, fixtures, and parametrization subsystems, the micro-dependencies, the original Sherlock test configuration (`pyproject.toml`), and the exact mirroring strategy required for Sherlock-V2.

---

## 1. Package Information & Dependency Topology

### 1.1 Installed Packages Summary

| Package | Version | Location | Metadata Citation | Primary Role |
| :--- | :--- | :--- | :--- | :--- |
| **`pytest`** | `9.1.1` | `.venv\Lib\site-packages\pytest`, `_pytest` | `pytest-9.1.1.dist-info\METADATA:1-48` | Core test runner, AST assertion rewriter, collection engine |
| **`iniconfig`** | `2.3.1` | `.venv\Lib\site-packages\iniconfig` | `iniconfig-2.3.1.dist-info\METADATA:1-25` | Minimalist INI configuration parser with line-number tracking |
| **`packaging`** | `26.3` | `.venv\Lib\site-packages\packaging` | `packaging-26.3.dist-info\METADATA:1-30` | PEP 440 / PEP 508 version checking and plugin requirement validation |
| **`pluggy`** | `1.7.0` | `.venv\Lib\site-packages\pluggy` | `pluggy-1.7.0.dist-info\METADATA:1-35` | Hook specification and implementation dispatcher (1:N hook calling) |
| **`pygments`** | `2.21.0` | `.venv\Lib\site-packages\pygments` | `pygments-2.21.0.dist-info\METADATA:1-39` | Syntax highlighting for code tracebacks and assertion diffs |
| **`colorama`** | `0.4.6` | `.venv\Lib\site-packages\colorama` | `colorama-0.4.6.dist-info\METADATA:1-25` | Win32 console ANSI escape sequence translation |
| **`pytest-timeout`** | `2.4.0` | In Sherlock root `.venv`; required in Sherlock-V2 | `pytest_timeout-2.4.0.dist-info\METADATA:1-34` | Thread/signal watchdog timer aborting hung test executions |

### 1.2 Dependency Graph & Python Compatibility

According to `pytest-9.1.1.dist-info\METADATA:30-39`, pytest mandates:
- **Python Compatibility**: `>=3.10` up to `3.15` (explicitly classified for Python 3.14 free-threading, see `METADATA:25-26`).
- **Direct Runtime Dependencies**:
  ```text
  iniconfig>=1.0.1
  packaging>=22
  pluggy<2,>=1.5
  pygments>=2.7.2
  colorama>=0.4; sys_platform == "win32"
  exceptiongroup>=1; python_version < "3.11"
  tomli>=1; python_version < "3.11"
  ```
Because Sherlock-V2 targets Python `>=3.14` (`pyproject.toml:6`), `exceptiongroup` and `tomli` are unnecessary as native `BaseExceptionGroup` (PEP 654) and `tomllib` (PEP 680) are standard library built-ins.

### 1.3 Subsystem Directory Layout

```text
.venv\Lib\site-packages\
├── _pytest/
│   ├── config/              # CLI parsing, config file detection, plugin discovery
│   │   ├── findpaths.py     # TOML / INI locator and configuration dictionary loader
│   │   ├── argparsing.py    # Command-line and INI option definition engine
│   │   └── __init__.py      # Config object, PytestPluginManager, strictness hooks
│   ├── mark/                # Test markers and parametrization data structures
│   │   ├── structures.py    # Mark, MarkDecorator, MarkGenerator, ParameterSet
│   │   └── expression.py    # Boolean expression parser for `-m "mark expression"`
│   ├── fixtures.py          # Dependency injection container, FixtureDef, scopes, teardown
│   ├── python.py            # Test collection, Metafunc, function invocation
│   ├── warnings.py          # Warning capture, filter application, promotion to errors
│   ├── assertion/           # AST rewrite transformer (rewrite.py, util.py)
│   └── _io/
│       └── terminalwriter.py# Color terminal output with Pygments highlighting integration
├── iniconfig/               # INI parsing engine (_parse.py, exceptions.py)
├── packaging/               # Version, specifiers, requirements, markers, tags
├── pluggy/                  # PluginManager, HookCaller, HookImpl, execution loop
├── pygments/                # Lexers (PythonLexer, DiffLexer) and TerminalFormatter
└── pytest/                  # Top-level namespace exports (__init__.py)
```

---

## 2. Pytest Core Architecture & Lifecycle

Pytest structures test execution as a linear progression of phases managed by hook calls through `pluggy`:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Initializing │ ──> │  Collection  │ ──> │ Running Test │ ──> │  Reporting   │
│ (Config/Hook)│     │  (Discovery) │     │  (Protocol)  │     │  (Terminal)  │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### 2.1 Configuration & Discovery Engine
1. **Root Directory & Config Discovery**:
   - Handled in `_pytest\config\findpaths.py:158-203` (`locate_config`).
   - Pytest searches ancestor directories for configuration candidates in strict precedence order (`:166-174`):
     1. `pytest.toml` / `.pytest.toml`
     2. `pytest.ini` / `.pytest.ini`
     3. `pyproject.toml`
     4. `tox.ini`
     5. `setup.cfg`
2. **INI vs TOML Parsing Modes**:
   - In `_pytest\config\findpaths.py:120-155`: When reading `pyproject.toml`, pytest distinguishes between `[tool.pytest]` (native TOML types) and `[tool.pytest.ini_options]` (legacy string/list INI format).
   - If both tables exist, pytest raises `UsageError` (`:129-135`).
   - Under `[tool.pytest.ini_options]`, non-list scalar values are stringified via `make_scalar` (`:147-153`) to integrate seamlessly with the INI parser type converters.
3. **`pythonpath` Configuration Hook**:
   - Defined in `_pytest\config\__init__.py:1549-1551`:
     ```python
     self._parser.addini(
         "pythonpath", type="paths", help="Add paths to sys.path", default=[]
     )
     ```
   - In `Config._configure_python_path()` (`_pytest\config\__init__.py:1718-1725`), each path listed in `pythonpath` is converted to an absolute path and prepended to `sys.path[0]`. This allows tests in `tests/` to import `sherlock_v2` directly from `src/` without requiring an editable pip installation.

### 2.2 Strictness Enforcement Engine
Pytest 9.1.1 provides three interdependent strictness controls defined in `_pytest\main.py:76-120`:
1. **`strict_config`** (`_pytest\main.py:97-104`):
   - When enabled via CLI `--strict-config` or INI `strict_config = true`, unknown configuration options in `pyproject.toml` raise a fatal `UsageError` instead of issuing a `PytestConfigWarning` (`_pytest\config\__init__.py:1462-1465, 1499-1506`).
2. **`strict_markers`** (`_pytest\main.py:105-112`):
   - When enabled, any marker applied to a test that has not been explicitly declared in `markers` raises a fatal error via `fail(..., pytrace=False)` (`_pytest\mark\structures.py:619-626`).
3. **`strict`** (`_pytest\main.py:113-119`):
   - Master switch enabling `strict_config`, `strict_markers`, `strict_xfail`, and `strict_parametrization_ids`.

---

## 3. Markers Subsystem (`pytest.mark`)

### 3.1 Class Architecture & Registry

The markers system is implemented in `_pytest\mark\structures.py`:

```
               ┌─────────────────────┐
               │    MarkGenerator    │  <-- Exposed as singleton `pytest.mark`
               └──────────┬──────────┘
                          │ creates / caches
                          ▼
               ┌─────────────────────┐
               │    MarkDecorator    │  <-- Callable decorator applied to test items
               └──────────┬──────────┘
                          │ wraps
                          ▼
               ┌─────────────────────┐
               │        Mark         │  <-- Frozen dataclass (name, args, kwargs)
               └─────────────────────┘
```

- **`Mark`** (`_pytest\mark\structures.py:247-313`): A frozen dataclass storing immutable marker metadata:
  ```python
  @final
  @dataclasses.dataclass(frozen=True)
  class Mark:
      name: str
      args: tuple[Any, ...]
      kwargs: Mapping[str, Any]
      _param_ids_from: Mark | None = dataclasses.field(default=None, repr=False)
      _param_ids_generated: Sequence[str] | None = dataclasses.field(default=None, repr=False)
  ```
  The method `combined_with(other)` (`:287-313`) allows merging stacked markers with matching names by concatenating `args` and updating `kwargs`.
- **`MarkDecorator`** (`_pytest\mark\structures.py:321-418`): Decorator wrapper. When invoked on a function or class:
  - If applied to a test function or class (`:406-417`), it invokes `store_mark(obj, self.mark)` (`:481-499`), appending the mark to `obj.pytestmark`.
  - If called with arguments (e.g. `@pytest.mark.timeout(60)`), it returns a new `MarkDecorator` via `with_args(*args, **kwargs)` (`:384-392`).
- **`MarkGenerator`** (`_pytest\mark\structures.py:564-639`): Factory exposed as the `pytest.mark` singleton (`MARK_GEN = MarkGenerator(_ispytest=True)` at `:639`).
  - Dynamic lookup via `__getattr__(self, name: str)` (`:594-638`):
    1. Validates that marker name does not start with an underscore (`:596-597`).
    2. Lazily synchronizes known markers from `self._config.getini("markers")` (`:603-609`).
    3. Detects common misspellings of `parametrize` (`parameterize`, `parametrise`, `parameterise`) and halts immediately with an explanatory error message (`:614-617`).
    4. If the marker is unregistered and `strict_markers` is active (`:619-626`), it fails immediately:
       ```python
       strict_markers = self._config.getini("strict_markers")
       if strict_markers is None:
           strict_markers = self._config.getini("strict")
       if strict_markers:
           fail(
               f"{name!r} not found in `markers` configuration option",
               pytrace=False,
           )
       ```
    5. If `strict_markers` is inactive, emits `PytestUnknownMarkWarning` (`:628-634`).

### 3.2 Built-in Markers

Pytest defines standard typing and implementations for built-in markers (`_pytest\mark\structures.py:503-560`):
- **`@pytest.mark.skip(reason=...)`**: Unconditionally skips execution of the marked test during the runtest phase.
- **`@pytest.mark.skipif(condition, reason=...)`**: Evaluates `condition` (boolean or expression string). If true, skips test.
- **`@pytest.mark.xfail(condition=True, reason=..., raises=..., strict=...)`**: Marks test as expected to fail. If `strict=True`, an unexpected pass converts to a test suite failure (`XPASS`).
- **`@pytest.mark.usefixtures("fixture1", "fixture2")`**: Injects fixtures by name into test execution without passing their return values as function arguments.
- **`@pytest.mark.filterwarnings("action:message:category:module:line")`**: Appends warning filters scoped specifically to the marked test or class (`_pytest\warnings.py:49-55`).
- **`@pytest.mark.parametrize(...)`**: Test multiplication engine.

---

## 4. Fixtures Architecture & Execution Engine

Pytest fixtures implement an inversion-of-control (IoC) dependency injection container with deterministic scoping, caching, and teardown.

### 4.1 Decorator & Definition Model

The fixture factory is implemented in `_pytest\fixtures.py`:
- **`@pytest.fixture`** (`_pytest\fixtures.py:1458-1510`):
  ```python
  def fixture(
      fixture_function: FixtureFunction | None = None,
      *,
      scope: ScopeName | Callable[[str, Config], ScopeName] = "function",
      params: Iterable[object] | None = None,
      autouse: bool = False,
      ids: Sequence[object | None] | Callable[[Any], object | None] | None = None,
      name: str | None = None,
  ) -> FixtureFunctionMarker | FixtureFunctionDefinition:
  ```
- **Direct Calling Prohibition** (`_pytest\fixtures.py:1421-1429`):
  Attempting to call a fixture function directly from test code raises a fatal error:
  ```python
  def __call__(self, *args: Any, **kwds: Any) -> Any:
      message = (
          f'Fixture "{self.name}" called directly. Fixtures are not meant to be called directly,\n'
          "but are created automatically when test functions request them as parameters.\n"
      )
      fail(message, pytrace=False)
  ```
- **Prohibition on Fixture Marking** (`_pytest\fixtures.py:1364-1368`):
  Applying `@pytest.mark.*` directly to a `@pytest.fixture` function is rejected with `fail("Marks cannot be applied to fixtures.")`.

### 4.2 Scopes & Lifecycle Hierarchy

Fixtures are scoped to specific node lifetimes (`_pytest\scope.py`):
1. **`function`** (default): Created anew for every single test invocation.
2. **`class`**: Created once per test class instance; shared among all test methods.
3. **`module`**: Created once per test file (`test_*.py`).
4. **`package`**: Created once per test package directory containing `__init__.py`.
5. **`session`**: Created once at test session startup and persists until the entire test suite completes.
6. **Dynamic Scopes**: `scope` can be passed as a callable `(fixture_name, config) -> ScopeName` (`_pytest\fixtures.py:1110-1115`), allowing test CLI flags (e.g. `--use-cluster`) to alter fixture reuse boundaries at runtime.

### 4.3 Execution, Caching, and Teardown Mechanics

- **Evaluation & Cache Hit Check** (`_pytest\fixtures.py:1171-1234`, `FixtureDef.execute()`):
  When a fixture is requested:
  1. Checks if `self.cached_result` is already present (`:1190-1206`). If the `cache_key(request)` matches the cached key, it returns the cached instance or re-raises any cached exception without re-executing the factory function.
  2. If the cache key differs (e.g. Due to parametrization), it invokes `self.finish(request)` (`:1209`) to cleanly tear down the previous instance before creating a new one.
- **Teardown via Generators (`yield`)**:
  - In a generator fixture (`_pytest\fixtures.py:1010-1065`):
    ```python
    @pytest.fixture
    def client_session():
        client = HttpClient()
        yield client
        client.close()  # Executed during teardown
    ```
    Code preceding the `yield` runs during test setup; code following `yield` runs during test teardown. The fixture factory must yield exactly once.
- **Teardown via `addfinalizer`** (`_pytest\fixtures.py:1143-1145`):
  Arbitrary teardown callbacks can be registered via `request.addfinalizer(callback)`.
- **LIFO Finalizer Execution & Exception Gathering** (`_pytest\fixtures.py:1146-1170`):
  During `finish()`:
  - Finalizers are popped and executed in Last-In-First-Out (LIFO) order (`:1153-1158`).
  - If multiple finalizers raise exceptions, pytest does not discard secondary errors; it aggregates them into a `BaseExceptionGroup("errors while tearing down fixture ...", exceptions[::-1])` (`:1168-1170`).

### 4.4 Autouse Fixtures

When `autouse=True` (`_pytest\fixtures.py:1499-1502`), the fixture is automatically activated for all test items within its visible scope without requiring explicit declaration in the test function signature.
- **Crucial Sherlock Pattern**: In original Sherlock (`tests/conftest.py:140-152`), an autouse fixture is employed to reset shared state between tests:
  ```python
  @pytest.fixture(autouse=True)
  def _reset_shared_http_client():
      """Fresh shared httpx client per test — its proxy-keyed cache would
      otherwise leak a (possibly monkeypatched-away) client across tests."""
      import services.http_client as http_client
      http_client._client = None
      http_client._client_proxy = None
      http_client._client_retries = None
      yield
      http_client._client = None
      http_client._client_proxy = None
      http_client._client_retries = None
  ```

---

## 5. Parametrization Subsystem (`@pytest.mark.parametrize`)

Parametrization enables data-driven testing by multiplying a single test function into multiple distinct test invocations across specified datasets.

### 5.1 ParameterSet Data Structure

Implemented in `_pytest\mark\structures.py:80-244`:
```python
class ParameterSet(NamedTuple):
    values: Sequence[object | NotSetType]
    marks: Collection[MarkDecorator | Mark]
    id: str | _HiddenParam | None
```
- **`pytest.param(*values, marks=(), id=None)`** (`_pytest\mark\structures.py:113-135`): Constructs an explicit `ParameterSet`, attaching individual markers (such as `pytest.mark.xfail`) or custom test IDs to a single parameter tuple.
- **`pytest.HIDDEN_PARAM`** (`_pytest\mark\structures.py:45-51`): A sentinel enum token allowing a parameter set to be omitted from the test name output (`versionadded:: 8.4`).

### 5.2 Test Expansion in `Metafunc.parametrize`

The collection-time expansion takes place in `_pytest\python.py:1231-1385`:
1. **Argument Parsing & Validation** (`:1316-1329`):
   - `argnames` can be provided as a comma-separated string (`"input, expected"`) or a sequence of strings (`["input", "expected"]`).
   - The name `"request"` is strictly reserved and cannot be parametrized (`:1325-1329`).
2. **Cartesian Product**:
   If a test function is decorated with multiple `@pytest.mark.parametrize` statements, pytest computes the Cartesian product of the parameters:
   ```python
   @pytest.mark.parametrize("x", [1, 2])
   @pytest.mark.parametrize("y", ["a", "b"])
   def test_combination(x, y):
       pass
   # Produces 4 tests: test_combination[a-1], test_combination[a-2], test_combination[b-1], test_combination[b-2]
   ```
3. **Indirect Parametrization (`indirect=True`)** (`:1275-1282, 1354-1362`):
   When `indirect` is set to `True` (or a list of argument names), the parameter value is not passed directly to the test function. Instead, it is routed as `request.param` to a fixture sharing the argument name. This enables lazy resource initialization during the test setup phase rather than at collection time.
4. **Empty Parameter Sets Handling** (`_pytest\mark\structures.py:57-78`):
   Configured via INI option `empty_parameter_set_mark`:
   - `"skip"` (default): Skips the test if the parameter list is empty.
   - `"xfail"`: Treats empty parameters as an expected failure.
   - `"fail_at_collect"`: Raises a fatal `Collector.CollectError` during test collection.

---

## 6. Test Timeout Engine (`pytest-timeout` 2.4.0)

In both Sherlock and Sherlock-V2, hanging tests (caused by unmocked socket calls, background worker deadlocks, or unresponsive event loops) present a major risk to CI pipelines and developer workflows. The `pytest-timeout` plugin resolves this by enforcing a hard watchdog timer.

### 6.1 Plugin Architecture & Hooks

Implemented in `.venv\Lib\site-packages\pytest_timeout.py`:
- **Option Registration** (`pytest_timeout.py:63-109`, `pytest_addoption`):
  - CLI: `--timeout <SECONDS>`, `--timeout-method <signal|thread>`, `--session-timeout <SECONDS>`.
  - INI options:
    - `timeout`: Global per-test timeout ceiling in seconds.
    - `timeout_method`: Execution mechanism (`signal` or `thread`).
    - `timeout_func_only`: If `True`, measures only the test function body, excluding fixture setup and teardown.
    - `session_timeout`: Maximum duration for the entire test session.
- **Marker Registration** (`pytest_timeout.py:140-156`, `pytest_configure`):
  Registers marker:
  ```python
  @pytest.mark.timeout(timeout, method=None, func_only=False, disable_debugger_detection=False)
  ```
- **Protocol Interception** (`pytest_timeout.py:178-200`, `pytest_runtest_protocol`):
  Wraps the entire test execution lifecycle (setup, call, teardown) when `func_only=False`:
  ```python
  @pytest.hookimpl(hookwrapper=True)
  def pytest_runtest_protocol(item):
      hooks = item.config.pluginmanager.hook
      settings = _get_item_settings(item)
      is_timeout = settings.timeout is not None and settings.timeout > 0
      if is_timeout and settings.func_only is False:
          hooks.pytest_timeout_set_timer(item=item, settings=settings)
      yield
      if is_timeout and settings.func_only is False:
          hooks.pytest_timeout_cancel_timer(item=item)
  ```

### 6.2 Execution Mechanisms: Signal vs Thread

The plugin implements two distinct watchdog strategies (`pytest_timeout.py:26-30, 303-337`):

```
Platform Check: hasattr(signal, "SIGALRM")
       │
       ├── POSIX (Linux / macOS) ──> Default method: "signal"
       │                             Uses: signal.setitimer(ITIMER_REAL, timeout)
       │                             Action: Raises AssertionError via timeout_sigalrm()
       │
       └── Windows / Non-Main-Thread ──> Default method: "thread"
                                     Uses: threading.Timer(timeout, timeout_timer)
                                     Action: Dumps stack traces, calls os._exit(1)
```

1. **`signal` Method (POSIX only)**:
   - Available only when `hasattr(signal, "SIGALRM")` is `True` (`:26`).
   - Uses OS-level `signal.setitimer(signal.ITIMER_REAL, settings.timeout)` (`:325`).
   - On timeout (`timeout_sigalrm`, `:485-503`), dumps stack traces to stderr and raises an `AssertionError` via `pytest.fail()`. This allows remaining tests in the suite to continue executing.
2. **`thread` Method (Windows default & fallback)**:
   - On Windows, `signal.SIGALRM` does not exist (`HAVE_SIGALRM == False`). The default method is permanently `"thread"` (`:29-30`).
   - Spawns a background daemon timer:
     ```python
     timer = threading.Timer(settings.timeout, timeout_timer, (item, settings))
     timer.name = "%s %s" % (__name__, item.nodeid)
     timer.start()
     ```
   - **Critical Windows Behavior on Expiry** (`timeout_timer`, `:505-543`):
     When a hanging test breaches the timeout:
     1. Suspends capture manager to ensure terminal visibility (`:517`).
     2. Flushes captured stdout, stderr, and logging handlers (`:523-533`).
     3. Calls `dump_stacks(terminal)` (`:545-559`), iterating over `sys._current_frames()` to format and print stack traces for **every live thread** in the Python process.
     4. Calls `os._exit(1)` (`:542`).
     *Architectural Note*: Because standard Python threads cannot be asynchronously terminated or interrupted without OS signals, `pytest-timeout` intentionally invokes `os._exit(1)` on Windows. This immediately terminates the process, preventing CI jobs from freezing indefinitely on hung worker threads.

### 6.3 Debugger Awareness

`pytest-timeout` incorporates built-in debugger detection (`pytest_timeout.py:262-298`, `is_debugging()`):
- Monitors `sys.gettrace()` for known debugger modules: `pdb`, `ipdb`, `pydevd` (used by VS Code and PyCharm), and `pydevd_frame_evaluator`.
- In Python 3.12+, checks `sys.monitoring.get_tool(sys.monitoring.DEBUGGER_ID)`.
- If an active debugging session is detected, timeouts are automatically suppressed so developers can inspect breakpoints without being terminated.

---

## 7. Micro-Dependencies Deep Dive & Roles

Pytest delegates specific infrastructure concerns to four dedicated micro-packages:

### 7.1 `iniconfig` 2.3.1 (INI Configuration Engine)
- **Role**: Lightweight INI parser engineered specifically for the pytest suite by Holger Krekel and Ronny Pfannschmidt.
- **Source Structure**: `iniconfig\__init__.py:1-180` and `iniconfig\_parse.py:1-160`.
- **Key Characteristics**:
  - Zero dependencies.
  - Maintains strict ordering of sections and key-value entries.
  - Preserves exact line numbers (`lineof(section, name)` at `__init__.py:180`) to provide precise diagnostic error locations.
  - Supports `#` and `;` comments everywhere, including inline comments (`_parse.py:100-115`).
  - Raises `iniconfig.ParseError` on duplicate sections or malformed syntax.
- **Pytest Integration**:
  In `_pytest\config\findpaths.py:46-56`, `_parse_ini_config()` wraps `iniconfig.IniConfig(str(path))`. It parses `pytest.ini`, `setup.cfg`, and `tox.ini`. When parsing `pyproject.toml`, pytest uses `tomllib`, but adapts the `[tool.pytest.ini_options]` table to conform to `iniconfig`'s string-based key-value conventions.

### 7.2 `packaging` 26.3 (Version & Specifier Engine)
- **Role**: The PyPA official reference implementation for Python packaging standards (PEP 440 versions, PEP 508 dependency specifications, PEP 345 environment markers).
- **Source Structure**:
  - `packaging\version.py`: `Version` class supporting strict PEP 440 comparison semantics (`26.3 > 9.1.1`, pre-releases, post-releases, dev-releases).
  - `packaging\requirements.py`: `Requirement` class parsing dependency strings (e.g. `"pytest-timeout>=2.4"`).
  - `packaging\specifiers.py`: `SpecifierSet` evaluation (`specifier.contains(version)`).
  - `packaging\markers.py`: Environment marker evaluator (`sys_platform == 'win32'`).
- **Pytest Integration Points**:
  - `_pytest\config\__init__.py:1466-1497` (`_validate_plugins`):
    ```python
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.version import Version
    ```
    Validates all plugins declared under the `required_plugins` INI setting against installed plugin distribution versions.
  - `_pytest\unittest.py:565-568`: Compares unittest runner versions for test suite compatibility.

### 7.3 `pluggy` 1.7.0 (Plugin & Hook Dispatch Engine)
- **Role**: The core extensibility kernel of pytest. Provides declarative hook specification (`@hookspec`), hook implementation (`@hookimpl`), and 1:N fan-out hook dispatching.
- **Source Structure**:
  - `pluggy\_manager.py:38-420`: `PluginManager` class maintaining plugin registries and hook relays.
  - `pluggy\_hooks.py:1-400`: `HookCaller`, `HookImpl`, `HookSpec`.
  - `pluggy\_caller.py:1-250`: Multicast hook execution loop.
- **Core Concepts & Mechanics**:
  - **`PytestPluginManager` Subclass**: In `_pytest\config\__init__.py:460-600`, pytest subclasses `pluggy.PluginManager` to incorporate conftest discovery, CLI option passing, and AST rewrite integration.
  - **Hook Calling Patterns**:
    - *1:N Multicast*: Dispatches hook calls to all registered implementations across all plugins.
    - *`firstresult=True`*: Terminates dispatch on the first non-`None` return value (e.g. `pytest_cmdline_parse`).
    - *Hook Wrappers (`hookwrapper=True` or `wrapper=True`)*: Generator-based hooks that yield control to inner implementations, resuming for post-execution inspection or modification of outcomes (e.g. `pytest_runtest_protocol`).

### 7.4 `pygments` 2.21.0 (Syntax Highlighting Engine)
- **Role**: Code syntax colorizer used by pytest's terminal reporter to generate legible terminal tracebacks and diffs.
- **Source Structure**:
  - `pygments\lexers\python.py`: `PythonLexer` tokenizing Python source code.
  - `pygments\lexers\diff.py`: `DiffLexer` tokenizing unified diff representations.
  - `pygments\formatters\terminal.py`: `TerminalFormatter` generating ANSI color sequences.
- **Pytest Integration**:
  In `_pytest\_io\terminalwriter.py:208-259`:
  ```python
  def _highlight(self, source: str, lexer: Literal["diff", "python"] = "python") -> str:
      if not source or not self.hasmarkup or not self.code_highlight:
          return source
      pygments_lexer = self._get_pygments_lexer(lexer)
      pygments_formatter = self._get_pygments_formatter()
      return pygments.highlight(source, pygments_lexer, pygments_formatter)
  ```
  - Highlights failure locations in test source files using `PythonLexer()`.
  - Highlights assertion comparison diffs (`assert left == right`) using `DiffLexer()`.
  - Supports environment configuration overrides: `PYTEST_THEME` (custom pygments style) and `PYTEST_THEME_MODE` (`"dark"` or `"light"`).

---

## 8. Original Sherlock Pytest Configuration Analysis

In the original Sherlock codebase, testing configuration is centralized in `/home/maikel/.zcode/workspace/default/Sherlock/pyproject.toml:71-96`:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
addopts = ["-ra", "-q"]
# Hard per-test ceiling: a hang (network stub regression, worker deadlock)
# fails that test instead of stalling CI for the default 0 (no limit).
timeout = 60
strict_markers = true
strict_config = true
markers = [
    "live: hits the real network (run explicitly with -m live; CI uses -m 'not live')",
]
filterwarnings = [
    # Owner rule: NEVER suppress/ignore warnings. Any warning raised by OUR
    # code (module-scoped below) escalates to a hard error so it must be
    # fixed. Third-party warnings are left at default — they stay visible in
    # pytest's warnings summary on every run, never ignored, but cannot
    # brick the suite for code we don't own.
    "error:::^(services|screens|components|core|state|hooks|tests)(\\.|$)|^(app_shell|main)$",
]

[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "pytest-timeout>=2.4",
    "ruff>=0.15.14",
]
```

### 8.1 Setting-by-Setting Architectural Rationale

1. **`pythonpath = ["src"]` (`:72`)**:
   - Informs pytest's path configuration hook (`_pytest\config\__init__.py:1550`) to insert the `src/` directory at index 0 of `sys.path`.
   - Allows all test modules in `tests/` to import application modules (e.g. `import services.http_client` or `import sherlock_v2`) without installing the package in editable mode.
2. **`addopts = ["-ra", "-q"]` (`:73`)**:
   - `-ra`: Directs the terminal reporter to print a concise extra summary breakdown for all non-passing outcomes: `r`eport `a`ll except passed (failures, errors, skips, xfails, xpasses).
   - `-q`: Quiet mode; suppresses verbose boilerplate, displaying compact dot progress and the failure summary.
3. **`timeout = 60` (`:76`)**:
   - Enforces a 60-second execution ceiling per test item via `pytest-timeout`.
   - Guards CI against infinite loops, unmocked socket calls, deadlocks in thread pools, and hanging async tasks.
4. **`strict_markers = true` (`:77`)**:
   - Enforces zero tolerance for unregistered markers (`_pytest\mark\structures.py:619-626`).
   - Prevents silent test filtering bugs caused by typos (e.g. `@pytest.mark.livee` would silently run during offline CI rather than being selected or rejected).
5. **`strict_config = true` (`:78`)**:
   - Enforces strict validation of all entries in `pyproject.toml` (`_pytest\config\__init__.py:1499-1506`).
   - If a setting is misspelled or a plugin registering an ini option is missing, pytest immediately halts with `UsageError`.
6. **`markers = ["live: ..."]` (`:79-81`)**:
   - Declares the `live` marker.
   - Enables test suite bifurcation:
     - CI runs: `pytest -m "not live"` (runs 100% offline unit/mock tests in seconds).
     - Explicit live runs: `pytest -m live` (runs integration tests touching external network services).
7. **`filterwarnings` Zero-Suppression Owner Rule (`:82-89`)**:
   - Syntax: `action:message:category:module:line` parsed in `_pytest\config\__init__.py:2122-2180`.
   - Filter regex: `"error:::^(services|screens|components|core|state|hooks|tests)(\\.|$)|^(app_shell|main)$"`
   - **Architectural Policy**:
     - Any warning originating from internal project modules escalates immediately to a fatal test error (`error`).
     - Warnings from third-party vendor libraries (`urllib3`, `flet`, `httpx`, etc.) are left at default (`default`), remaining visible in pytest's terminal summary without breaking the test suite.

### 8.2 Conftest Fixture Patterns in Original Sherlock

In `tests/conftest.py`, Sherlock demonstrates two key architectural fixture patterns:
1. **Mock UI Isolation (`FakePage` & `FakeClientStorage`, `:11-138`)**:
   - Fully mocks Flet's UI runtime (`ft.Page` and `page.client_storage`) for lightning-fast headless unit testing without spawning Flutter engine instances or GUI windows.
2. **State Leak Guard (`_reset_shared_http_client`, `:140-152`)**:
   - An `autouse=True` fixture that cleans HTTP client singletons before and after every test, preventing leaked sockets or monkeypatched headers from contaminating subsequent test cases.

---

## 9. Sherlock-V2 Mirroring Strategy & Blueprint

To maintain identical testing rigor, Sherlock-V2 must replicate the original configuration while updating module patterns to reflect its updated directory structure.

### 9.1 Required `pyproject.toml` Configuration for Sherlock-V2

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
addopts = ["-ra", "-q"]
# Hard per-test ceiling: a hang (network stub regression, worker deadlock)
# fails that test instead of stalling CI for the default 0 (no limit).
timeout = 60
strict_markers = true
strict_config = true
markers = [
    "live: hits the real network (run explicitly with -m live; CI uses -m 'not live')",
]
filterwarnings = [
    # Owner rule: NEVER suppress/ignore warnings. Any warning raised by OUR
    # code (module-scoped below) escalates to a hard error so it must be
    # fixed. Third-party warnings are left at default — they stay visible in
    # pytest's warnings summary on every run, never ignored, but cannot
    # brick the suite for code we don't own.
    "error:::^(sherlock_v2|services|screens|components|core|state|hooks|tests)(\\.|$)|^(app_shell|main)$",
]

[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "pytest-timeout>=2.4",
    "ruff>=0.17.1",
]
```

### 9.2 Critical Gap Analysis: `pytest-timeout` in Sherlock-V2

- **The Issue**: Sherlock-V2's current `pyproject.toml:22-25` declares only:
  ```toml
  [dependency-groups]
  dev = [
      "pytest>=9.1.1",
      "ruff>=0.17.1",
  ]
  ```
- **Consequence of `strict_config = true`**:
  If `timeout = 60` is added to `[tool.pytest.ini_options]` while `pytest-timeout` is missing from the virtual environment, running `pytest` will fail immediately with:
  ```text
  UsageError: Unknown config option: timeout
  ```
  This occurs because `strict_config = true` validates all keys against known ini options (`_pytest\config\__init__.py:1463`), and the `timeout` option is only registered when `pytest_timeout.py:99` executes `parser.addini("timeout", ...)`.
- **Resolution**:
  `pytest-timeout>=2.4` must be added to Sherlock-V2's `dev` dependency group and installed in `.venv`.

### 9.3 Test Suite Architecture Blueprint

When implementing tests for Sherlock-V2:
1. **Directory Layout**:
   ```text
   Sherlock-V2/
   ├── src/
   │   └── sherlock_v2/
   └── tests/
       ├── __init__.py
       ├── conftest.py               # Shared FakePage and HTTP reset fixtures
       ├── test_smoke.py             # Basic import and initialization checks
       ├── test_scanner.py           # User scanner / phonsint tests (mocked offline)
       └── test_live_network.py      # Marked with @pytest.mark.live
   ```
2. **Conftest Implementation**:
   Replicate `FakePage` and `FakeClientStorage` to enable headless UI validation.
   Replicate `_reset_shared_http_client` (or equivalent HTTP client reset fixture) to ensure isolated connection pools.
3. **Execution Commands**:
   - Local rapid test: `pytest` (runs all unit tests with `-ra -q`).
   - CI offline verification: `pytest -m "not live"`.
   - CI integration verification: `pytest -m live`.
   - Targeted timeout override: `@pytest.mark.timeout(10)` on fast tests or `@pytest.mark.timeout(120)` on heavy multi-site scans.

---

## 10. Summary Verification Checklist

| Architectural Requirement | Original Sherlock | Sherlock-V2 Target | Verification / Status |
| :--- | :--- | :--- | :--- |
| **Pytest Version** | `9.1.1` | `9.1.1` | Verified in `.venv\Lib\site-packages\pytest-9.1.1.dist-info` |
| **Source Import Path** | `pythonpath = ["src"]` | `pythonpath = ["src"]` | Resolves `src/sherlock_v2` without editable install |
| **Timeout Watchdog** | `timeout = 60` (`pytest-timeout`) | `timeout = 60` (`pytest-timeout>=2.4`) | Needs `pytest-timeout` added to `dev` dependency group |
| **Marker Strictness** | `strict_markers = true` | `strict_markers = true` | Eliminates typo-induced test filter bypasses |
| **Config Strictness** | `strict_config = true` | `strict_config = true` | Prevents undetected configuration errors |
| **Network Bifurcation** | `live` marker declared | `live` marker declared | Permits `-m 'not live'` fast offline CI runs |
| **Warning Policy** | Module-scoped `error` filter | Scoped `error` filter including `sherlock_v2` | Escalates internal warnings; tolerates vendor noise |
