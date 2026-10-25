# user-scanner 1.5.2.3 Dependency Reference & Architectural Study

**Target Package:** `user-scanner` v1.5.2.3  
**Environment Path:** `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/user_scanner`  
**Distribution Metadata:** `user_scanner-1.5.2.3.dist-info`  
**Target Document:** `/home/maikel/.zcode/workspace/default/Sherlock-V2/docs/reference/dep-user-scanner.md`  

---

## 1. Executive Summary

`user-scanner` (version 1.5.2.3) is the primary OSINT reconnaissance engine bundled within Sherlock-V2. It delivers dual-vector intelligence gathering across both usernames and email addresses:
1. **Username Reconnaissance (`user_scan`):** Scans up to 2,521 site modules across 17 distinct functional categories to detect profile registration, extract metadata (bio, full names, external social links, avatars), and generate permalinks.
2. **Email Reconnaissance (`email_scan`):** Probes 220 web endpoints across 20 categories to evaluate whether an email address is registered, using signup validation endpoints, password-reset form hints, and TLS-fingerprinted browser impersonation (`curl_cffi`).
3. **Recursive Cross-Scan Engine (`core/cross_scan.py`):** Automatically mines extracted profile metadata for secondary handles, verified external links, and email addresses, iteratively initiating second-pass sweeps and scoring identity confidence (`CONFIRMED`, `LIKELY`, `CANDIDATE`, `CONFLICTING`).
4. **Infostealer Threat Intelligence (`core/hudson.py`):** Directly queries Hudson Rock's Cavalier API to detect compromised credentials originating from infostealer trojans (RedLine, Lumma, Raccoon, etc.).
5. **Permutation & Pattern Engine (`core/patterns.py`):** Expands bracketed handle syntax (e.g. `john[0-9]{1-2}`) using reservoir sampling for randomized target scanning.
6. **Model Context Protocol (MCP) Service (`mcp/server.py`):** Exposes JSON-RPC endpoints for AI agent tool calling (`scan_username`, `scan_email`, `list_available_modules`).

---

## 2. Package Layout & Directory Architecture

Relative to site-packages root (`user_scanner/`):

```
user_scanner/
├── __init__.py                     # Empty package marker (0 bytes)
├── __main__.py                     # CLI entry point (argparse, rich console, exporter)
├── config.json                     # Persistent runtime settings (updates, prompts)
├── version.json                    # Package version specifier ("1.5.2.3", "pypi")
├── cli/
│   ├── __init__.py                 # Empty package marker
│   ├── banner.py                   # Terminal ASCII banner & sponsor attribution
│   └── tips.py                     # Operational guidance (WAF/proxy tips, remediation)
├── core/
│   ├── __init__.py                 # Empty package marker
│   ├── confidence.py               # Cross-scan identity anchor scoring & classification
│   ├── cross_scan.py               # Multi-round recursive OSINT pivoting engine
│   ├── email_orchestrator.py       # Asynchronous email scan batch runner & httpx patcher
│   ├── engine.py                   # Pure async programmatic engine API (check, check_all)
│   ├── formatter.py                # Data format converters (JSON, CSV, PDF)
│   ├── helpers.py                  # Module discovery, loaders, ScanConfig, ProxyManager
│   ├── hudson.py                   # Hudson Rock infostealer intelligence API client
│   ├── impersonate.py              # Browser TLS fingerprint impersonation (curl_cffi)
│   ├── loud_prompt.py              # Interactive confirmation for alert-triggering modules
│   ├── nextjs.py                   # App Router flight chunk & Pages Router data extractors
│   ├── orchestrator.py             # Username batch runner, threadpool, rich Progress UI
│   ├── patterns.py                 # Lexer, AST, and combinatorial pattern expansion
│   ├── pdf_generator.py            # ReportLab dossier generator with SSRF guardrails
│   ├── pivots.py                   # Metadata extraction for usernames, emails, and links
│   ├── result.py                   # Status enum, Result model, CSV sanitization, styling
│   └── version.py                  # PyPI and local version resolution helpers
├── email_scan/                     # 220 email verification modules (20 categories)
│   ├── __init__.py
│   ├── adult/ (17 modules)         ├── community/ (5 modules)      ├── creator/ (13 modules)
│   ├── crm/ (4 modules)            ├── dating/ (11 modules)        ├── dev/ (21 modules)
│   ├── entertainment/ (13 modules) ├── fitness/ (5 modules)        ├── gaming/ (5 modules)
│   ├── hosting/ (2 modules)        ├── jobs/ (14 modules)          ├── learning/ (29 modules)
│   ├── music/ (5 modules)          ├── news/ (8 modules)           ├── other/ (14 modules)
│   ├── shopping/ (18 modules)      ├── social/ (18 modules)        ├── sports/ (7 modules)
│   ├── travel/ (4 modules)         └── women_health/ (7 modules)
├── user_scan/                      # 2,521 username modules (17 categories)
│   ├── adult/ (22 modules)         ├── community/ (576 modules)    ├── creative/ (144 modules)
│   ├── creator/ (41 modules)       ├── dating/ (8 modules)         ├── dev/ (455 modules)
│   ├── donation/ (7 modules)       ├── email/ (1 module)           ├── entertainment/ (108 modules)
│   ├── finance/ (151 modules)      ├── gaming/ (198 modules)       ├── learning/ (267 modules)
│   ├── music/ (125 modules)        ├── other/ (79 modules)         ├── political/ (4 modules)
│   ├── shopping/ (56 modules)      └── social/ (279 modules)
├── mcp/                            # Model Context Protocol server implementation
│   ├── __init__.py
│   ├── handlers.py                 # Tool execution handlers & scan serialization lock
│   ├── schemas.py                  # FastMCP Tool schema definitions
│   └── server.py                   # Stdio JSON-RPC server entry point
└── utils/                          # Maintenance & updater utilities
    ├── __init__.py
    ├── update.py                   # Subprocess-driven pip self-updater
    └── updater_logic.py            # Non-blocking PyPI version polling logic
```

### Module Count Verification
- **Total `user_scan` modules:** 2,521 executable Python modules across 17 folders.
- **Total `email_scan` modules:** 220 executable Python modules across 20 folders.
- **Total scanning vectors:** 2,741 site targets.

---

## 3. Public Engine API (`user_scanner/core/engine.py`)

The `engine.py` module exposes a lightweight, async-native interface decoupled from terminal progress bars or CLI argument parsing.

```python
# Citation: user_scanner/core/engine.py:10-71
_shared_executor = concurrent.futures.ThreadPoolExecutor(max_workers=60)

async def check(module: ModuleType, target: str) -> Result: ...
async def check_category(category_name: str, target: str, is_email: bool = True) -> List[Result]: ...
async def check_all(target: str, is_email: bool = True) -> List[Result]: ...
```

### 3.1 `engine.check(module: ModuleType, target: str) -> Result`
- **File & Line:** `user_scanner/core/engine.py:12-43`
- **Mechanism:**
  1. Derives the validation function name dynamically: `func_name = f"validate_{module.__name__.split('.')[-1]}"`.
  2. Inspects module path (`getattr(module, "__file__", "")`) to determine if `is_email = "email_scan" in module_path`.
  3. Derives `site_label` via `get_site_name(module)` and `category` via `find_category(module)`.
  4. Dispatches the callable:
     - If `inspect.iscoroutinefunction(func)`: directly awaited (`await func(target)`).
     - If synchronous: offloaded to threadpool via `loop.run_in_executor(_shared_executor, func, target)`.
  5. Catches any unhandled exception and wraps it in `Result.error(e)`.
  6. Enriches the returned `Result` via `.update(site_name=..., username=target, category=..., is_email=...)`.
- **Architectural Caveat:** `engine.check()` does **not** evaluate `ScanConfig`, does **not** respect `allow_loud`, does **not** filter `no_nsfw`, and does **not** enforce per-module timeouts.

### 3.2 `engine.check_category(category_name: str, target: str, is_email: bool = True) -> List[Result]`
- **File & Line:** `user_scanner/core/engine.py:45-57`
- **Mechanism:**
  1. Resolves category path via `load_categories(is_email=is_email)`.
  2. Raises `ValueError(f"Category '{category_name}' not found in {mode}")` if unresolved.
  3. Loads all category modules via `load_modules(cat_path)`.
  4. Concurrently executes all modules using `asyncio.gather(*[check(m, target) for m in modules])`.
- **Warning:** `is_email` defaults to `True`. Furthermore, `asyncio.gather` executes without a semaphore; large categories (such as `community` with 576 modules) spawn hundreds of concurrent coroutines simultaneously.

### 3.3 `engine.check_all(target: str, is_email: bool = True) -> List[Result]`
- **File & Line:** `user_scanner/core/engine.py:59-71`
- **Mechanism:**
  Loads all categories and flattens nested results across `check_category()`. Spawns unbounded concurrent tasks across all modules in the vector.

---

## 4. Orchestrator Functions & Execution Architecture

The orchestrators manage real-world scan operational constraints: global concurrency limits, worker threadpools, rich terminal UI, module execution timeouts, and loud module skipping.

### 4.1 Username Orchestrator (`user_scanner/core/orchestrator.py`)
- **Default Concurrency:** `MAX_CONCURRENT_REQUESTS = 60` (`orchestrator.py:27`).
- **Worker ThreadPool:** `_shared_executor = concurrent.futures.ThreadPoolExecutor(max_workers=max(MAX_CONCURRENT_REQUESTS * 2, 250))` (`orchestrator.py:28`).
- **Concurrency Mutation:** `set_concurrency(val: int)` (`orchestrator.py:30-35`) updates the global limit and re-allocates the thread pool.

#### Synchronous Entry Points:
1. **`run_user_module(module: Union[ModuleType, List[ModuleType]], username: str, configs: ScanConfig) -> List[Result]`** (`orchestrator.py:165-170`):
   Runs one or more specific modules for a target handle via `asyncio.run()`.
2. **`run_user_category(category_path: Path, username: str, configs: ScanConfig) -> List[Result]`** (`orchestrator.py:172-192`):
   Runs all modules within a specific category folder via `asyncio.run()`.
3. **`run_user_full(username: str, configs: ScanConfig) -> List[Result]`** (`orchestrator.py:259-261`):
   Runs all non-NSFW categories (or all categories if `no_nsfw=False`) across all 2,521 modules via `asyncio.run()`.

#### Worker Lifecycle (`orchestrator.py:37-81`):
- Wraps execution inside an `asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)`.
- Checks loud status: `if not configs.allow_loud and is_loud(site_name): return Result.skipped().update(...)`.
- Calculates module timeout: `module_timeout = (get_global_timeout() or 15.0) + 10.0` (default: 25.0s).
- Enforces timeout via `asyncio.wait_for(...)`. If exceeded, catches `asyncio.TimeoutError` and returns `Result.error("Module execution timed out after {module_timeout}s")`.

#### HTTP Helper Utilities:
- **`make_request(url: str, **kwargs) -> httpx.Response`** (`orchestrator.py:279-317`):
  Pre-populates browser headers (Chrome 141 on Linux), defaults timeout to `get_global_timeout()` or `5.0s`, extracts proxies via `get_proxy()`, and retrieves or initializes a persistent `httpx.Client` instance from `_clients` cache (`orchestrator.py:267-276`).
- **`generic_validate(url: str, func: Callable[[httpx.Response], Result], **kwargs) -> Result`** (`orchestrator.py:319-335`):
  Executes `make_request`, delegates response analysis to `func`, and assigns `url=display_url`.
- **`status_validate(url: str, available: int | List[int], taken: int | List[int], **kwargs) -> Result`** (`orchestrator.py:337-365`):
  Matches `response.status_code` against `available` vs `taken` lists, returning `Result.available()` or `Result.taken()`.

### 4.2 Email Orchestrator (`user_scanner/core/email_orchestrator.py`)
- **Default Concurrency:** `MAX_CONCURRENT_REQUESTS = 25` (`email_orchestrator.py:56`).
- **Global `httpx` Monkeypatching (`email_orchestrator.py:23-53`):**
  Upon module import, `email_orchestrator` globally patches `httpx.AsyncClient.__init__` and `httpx.Client.__init__` to automatically inject `get_proxy()` and `get_global_timeout()`.
- **Synchronous Entry Points:**
  - `run_email_module_batch(...) -> List[Result]` (`email_orchestrator.py:206-209`)
  - `run_email_category_batch(...) -> List[Result]` (`email_orchestrator.py:233-237`)
  - `run_email_full_batch(...) -> List[Result]` (`email_orchestrator.py:314-316`)

---

## 5. Core Helpers & Configuration Models (`user_scanner/core/helpers.py`)

### 5.1 `ScanConfig` Model
**File & Line:** `user_scanner/core/helpers.py:448-453`

```python
@dataclass(frozen=True)
class ScanConfig:
    allow_loud: bool = False
    no_nsfw: bool = False
    show_all: bool = False
    verbose: bool = False
    timeout: Optional[float] = None
```

- **`allow_loud`:** When `False`, modules known to notify the target (password resets, OTP triggers) are bypassed and return `Status.SKIPPED`. When `True`, they execute normally.
- **`no_nsfw`:** When `True`, excludes the `adult/` category from category loading.
- **`show_all`:** When `False`, console rendering filters out `Status.AVAILABLE` (Not Found) and `Status.ERROR`. When `True`, all verdicts are shown.
- **`verbose`:** When `True`, displays URLs in console outputs.
- **`timeout`:** Overrides request timeouts across HTTP clients.

### 5.2 Category & Module Loaders
- **`load_categories(is_email: bool = False, no_nsfw: bool = False) -> Dict[str, Path]`** (`helpers.py:519-536`):
  Scans `email_scan/` or `user_scan/`. Cached via `@functools.lru_cache(maxsize=None)`. If `no_nsfw=True`, skips subfolder named `"adult"`.
- **`load_modules(category_path: Path) -> List[ModuleType]`** (`helpers.py:503-517`):
  Iterates over `*.py` files (ignoring `__init__.py`) using `importlib.util.spec_from_file_location` and `spec.loader.exec_module(module)`. Cached via `@functools.lru_cache(maxsize=None)`.
- **`find_category(module: ModuleType) -> str | None`** (`helpers.py:565-575`):
  Resolves the capitalized parent directory name of a module's `__file__`.
- **`find_module(name: str, is_email: bool = False, no_nsfw: bool = False) -> List[ModuleType]`** (`helpers.py:554-563`):
  Performs a case-insensitive search across all loaded categories for a matching module name.

### 5.3 Site Metadata & Loud Filter
- **`get_site_name(module) -> str`** (`helpers.py:496-501`):
  Extracts the file stem, capitalizes it, replaces underscores with dots, and maps `"X"` to `"X (Twitter)"`.
- **`get_scan_func(module) -> Optional[Callable[[str], Any]]`** (`helpers.py:543-552`):
  Inspects the module for any attribute prefixed with `validate_` that is a function or coroutine.
- **`LOUD_MODULES` & `is_loud(name: str, is_email: bool = False) -> bool`** (`helpers.py:27-84, 538-541`):
  Maintains a registry of 53 email verification modules that send user-facing alerts (e.g. Netflix, LeetCode, Medium, Ravelry, Flipkart). `LOUD_MODULES["user"]` is currently empty (`[]`).

### 5.4 Proxy Management
**File & Line:** `user_scanner/core/helpers.py:608-701`

- **`ProxyManager`:** Thread-safe round-robin proxy rotator.
  - Initialized with a file path (`proxy_file`) or list of strings (`proxies`).
  - Normalizes proxy strings: if missing an explicit protocol (e.g. `127.0.0.1:8080`), automatically prepends `http://`. Explicit schemes (`socks5://`, `socks5h://`, `http://`, `https://`) are preserved.
  - `get_next_proxy()`: Thread-safe round-robin access using an internal `threading.Lock`.
  - `get_random_proxy()`: Returns a random proxy from the loaded list.
  - `count()`: Returns total loaded proxies.
- **Global Handlers:**
  - `set_proxy_manager(proxy_file=None, proxies=None)`: Configures the module-level `_proxy_manager`.
  - `get_proxy() -> Optional[str]`: Retrieves the next rotating proxy.
  - `get_proxy_count() -> int`: Returns active proxy pool size.
- **`validate_proxies(proxy_list: List[str], timeout: int = 5, max_workers: int = 50) -> List[str]`** (`helpers.py:603-606`):
  Asynchronously tests a batch of proxies against `http://gstatic.com/generate_204` using an `asyncio.Semaphore(max_workers)`. Returns only working proxies.

### 5.5 Email Domain Scopes
**File & Line:** `user_scanner/core/helpers.py:86-442, 474-494`

- **`EMAIL_DOMAIN_SCOPES`:** Mapping of 26 geographic and regional scopes to tuples of email domains.
  - `global`: 31 major providers (`gmail.com`, `outlook.com`, `proton.me`, `icloud.com`, `yahoo.com`, `zoho.com`, `tuta.com`, etc.).
  - Country-specific scopes: `usa`, `canada`, `uk`, `ireland`, `germany`, `austria`, `switzerland`, `france`, `belgium`, `netherlands`, `italy`, `spain`, `portugal`, `poland`, `czechia`, `slovakia`, `hungary`, `romania`, `greece`, `turkey`, `nordics`, `russia`, `estonia`, `latvia`, `lithuania`, `ukraine`, `belarus`, `china`, `japan`, `korea`, `india`, `australia`, `new_zealand`, `brazil`, `mexico`, `argentina`, `chile`, `colombia`, `south_africa`, `israel`.
- **`parse_email_domain_scopes(value: str) -> tuple[str, ...]`:**
  Parses comma-separated scope arguments (e.g. `"global,germany"` or `"all"`), validates names, and returns a deduplicated tuple of domain strings.

### 5.6 Global Timeout & Settings
- **`set_global_timeout(timeout: Optional[float])` / `get_global_timeout() -> Optional[float]`** (`helpers.py:457-463`):
  Thread-shared variable controlling request timeouts across `make_request`, `orchestrator`, and `impersonate`.
- **`load_config(path=None)` / `save_config_value(key, value, path=None)`** (`helpers.py:723-765`):
  Reads and writes persistent JSON configuration from `user_scanner/config.json` (or `USER_SCANNER_CONFIG` environment variable). Defaults:
  ```json
  {
    "auto_update_status": true,
    "auto_hudson_prompt": true,
    "auto_loud_single_module_prompt": true
  }
  ```

---

## 6. Result Model & Data Structures (`user_scanner/core/result.py`)

### 6.1 Status Enum
**File & Line:** `user_scanner/core/result.py:68-85`

```python
class Status(Enum):
    TAKEN = 0        # Target found / registered on site
    AVAILABLE = 1    # Target available / not registered
    ERROR = 2        # Network, WAF, bot wall, or parser error
    SKIPPED = 3      # Bypassed (e.g. loud module under silent mode)
```

- **`to_label(is_email=False)`:**
  - `Status.ERROR` -> `"Error"`
  - `Status.SKIPPED` -> `"Skipped"`
  - `is_email=True`: `TAKEN` -> `"Registered"`, `AVAILABLE` -> `"Not Registered"`
  - `is_email=False`: `TAKEN` -> `"Found"`, `AVAILABLE` -> `"Not Found"`

### 6.2 Result Class Architecture
**File & Line:** `user_scanner/core/result.py:87-305`

#### Properties:
- `status: Status`
- `reason: str | Exception | None`
- `username: Optional[str]` (holds either username or email target)
- `site_name: Optional[str]`
- `category: Optional[str]`
- `url: str` (target profile URL)
- `extra: dict[str, str | bool | int]` (structured metadata: bios, names, external links)
- `media: dict[str, str]` (profile images, avatars, snapcodes)
- `is_email: bool`

#### Factory Classmethods (`result.py:128-150`):
- `Result.taken(reason=None, **kwargs)`
- `Result.available(reason=None, **kwargs)`
- `Result.error(reason=None, **kwargs)`
- `Result.skipped(reason=None, **kwargs)`
- `Result.from_number(i: int, reason=None)`

#### Fluent Mutation (`update(**kwargs)` - `result.py:100-126`):
Updates attributes dynamically. Sanitizes keys in `extra`:
- Strips whitespace and trailing colons (`:`).
- Replaces spaces with underscores (`_`).
- Converts keys to lowercase.
- Discards empty strings or `None` values.
- Casts values to `bool`, `int`, or `str`.

#### Serialization & Conversions:
- **`as_dict() -> dict`** (`result.py:171-183`):
  Returns dictionary representation including `["status", "reason", "username", "site_name", "category", "url", "extra", "media", "is_email"]`.
- **`to_dict() -> dict`** (`result.py:184-192`):
  Prepares clean export dictionary: if `is_email` is True, pops `"username"` and stores as `"email"`; removes `"is_email"`.
- **`to_json() -> str`** (`result.py:196-198`):
  Serializes `to_dict()` with `indent=4`.
- **`to_csv() -> str`** (`result.py:200-224`):
  Flattens `extra` and `media` dictionaries into key-value semicolon-delimited strings (`"k1: v1; k2: v2"`).
  **Formula Injection Protection (`_neutralize_csv_cell` - `result.py:26-34`):**
  If a value starts with formula trigger characters (`=`, `+`, `-`, `@`, `\t`, `\r`, `\n`), it is prepended with a single quote (`'`) to neutralize CSV injection vulnerabilities in Excel/LibreOffice.

#### UI & Presentation Methods:
- **`is_found() -> bool`** (`result.py:287-290`): Returns `self.status == Status.TAKEN`.
- **`is_visible(configs: ScanConfig | None = None) -> bool`** (`result.py:291-297`):
  Returns `True` if `configs.show_all` is enabled; otherwise returns `True` only for `Status.TAKEN` and `Status.SKIPPED`.
- **`get_reason() -> str`** (`result.py:158-170`):
  Translates exceptions via `humanize_exception()` (`result.py:48-66`), converting socket codes (`10054`, `11001`, `errno 7`, `errno 101`, `curl (28)`) into human-readable network diagnostics.
- **`get_console_output(configs: ScanConfig | None = None) -> str`** (`result.py:254-286`):
  Renders formatted tree branch structures (`├──`, `└──`) for enriched `extra` and `media` metadata with ANSI coloring.
- **`show(configs: ScanConfig) -> self`** (`result.py:298-305`):
  Prints output if `is_visible(configs)` is True.

---

## 7. Advanced Scanning Features

### 7.1 Cross-Scan & Recursive Pivoting
**Files:** `user_scanner/core/cross_scan.py`, `pivots.py`, `confidence.py`

Cross-scan conducts a multi-round secondary investigation by parsing profile metadata returned during pass 1:

```
Pass 1 Results (Email/User)
       │
       ▼
Extract Pivots (core/pivots.py) ──► Usernames, Handles, Bio Links, Emails
       │
       ▼
Filter & Select (CrossScanConfig) ──► Links (all/verified/none), Emails (all/verified/none)
       │
       ▼
Budget Splitter (_split_budget) ──► Allocates Sweep Budget (default 3) between Users & Emails
       │
       ▼
Pass 2 Execution ────────────────► Sweeps unlinked handles across full engine;
       │                           Scans linked handles directly against named sites
       │
       ▼
Confidence Scoring (confidence.py) ──► Builds Identity Anchors & scores each hit
```

#### Configuration (`CrossScanConfig` - `cross_scan.py:60-80`):
- `links`: `"all"` (any URL in bio/extra), `"verified"` (platform-proven OAuth connections via `VERIFIED_KEYS`), `"none"`.
- `emails`: `"verified"` (addresses explicitly found in email fields), `"all"` (includes scraping bio text), `"none"`.
- `depth`: Number of recursive link-following rounds (default `1`).
- `sweep`: Maximum target quota swept across all modules (default `3`). Targets beyond budget are evaluated only on sites explicitly named by a link pivot.
- `modules` / `categories`: Inherited restrictions from CLI flags (`-m` / `-c`).

#### Identity Confidence Levels (`confidence.py:60-86`):
1. **`CONFIRMED`:** A profile link explicitly named this exact platform and handle.
2. **`LIKELY`:** Metadata on the discovered profile matches confirmed anchors (e.g. matching real name, domain, or mutual backlink).
3. **`CANDIDATE`:** Handle is taken, but no corroborating metadata links it to the subject (potential handle collision).
4. **`CONFLICTING`:** Profile contains an explicit real name that directly contradicts the confirmed anchor identity.

### 7.2 Hudson Rock Infostealer Intelligence (`user_scanner/core/hudson.py`)
- **API Endpoint:** `https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-username` or `search-by-email`.
- **Interactive Permission Check (`check_hudson_permission` - `hudson.py:22-48`):**
  Warns the operator that the target identifier will be transmitted to a third-party intelligence provider. Allows saving a permanent preference (`"d"` -> updates `auto_hudson_prompt: false` in `config.json`).
- **Telemetry Parsed:** Stealer family, date compromised, operating system, computer name, installed antivirus products, and sample top domain logins.

### 7.3 Combinatorial Permutation Engine (`user_scanner/core/patterns.py`)
- **Pattern Syntax:**
  - `[chars]`: Character sets (e.g. `[a-z]`, `[0-9]`, `[abc]`).
  - `[chars]{len}`: Length specifiers (e.g. `[0-9]{1-3}`, `[a-z]{0;2}`).
  - `\\[ \\] \\\\`: Escaped literal brackets.
- **Routines:**
  - `expand_patterns(input: str) -> Iterator[str]` (`patterns.py:178-193`): Generator yielding all combinations.
  - `expand_patterns_random(input: str, capacity: int = 1000) -> Iterator[str]` (`patterns.py:195-223`): Shuffled generator utilizing reservoir sampling to ensure uniform random expansion without loading millions of permutations into RAM.
  - `count_patterns(input: str) -> int` (`patterns.py:225-238`): $O(\text{blocks})$ mathematical calculation of total combinatorial permutations without instantiating them.

### 7.4 TLS Impersonation Engine (`user_scanner/core/impersonate.py`)
- Employs `curl_cffi` to mimic browser TLS fingerprints (JA3/JA4, HTTP/2 frames, ALPN), bypassing Cloudflare, DataDome, and Akamai bot protections.
- `impersonate_validate(url, func, warmup_url=None, impersonate="chrome", ...)` (`impersonate.py:19-42`):
  Executes requests via a persistent `cffi.Session`. If `warmup_url` is provided, fetches the root domain once to capture clearance cookies before hitting protected validation endpoints.
- `impersonate_request_async(...)` (`impersonate.py:75-94`): Runs synchronous `curl_cffi` requests inside `asyncio.to_thread` for async email modules.

---

## 8. Model Context Protocol (MCP) Server

**Entry Point:** `user-scanner-mcp` console script (`user_scanner/mcp/server.py:50-71`).  
**Optional Requirement:** `pip install user-scanner[mcp]` (`mcp>=1.2.0,<2`).

### 8.1 Transport & Safety Isolation
- Operates over Stdio JSON-RPC (`stdio_server`).
- **Stream Corruption Prevention (`server.py:17-23`, `handlers.py:133`):**
  Logging is forced to `sys.stderr`. During scan execution, `handlers.py` wraps calls in `contextlib.redirect_stdout(sys.stderr)` so terminal output from orchestrators does not corrupt the JSON-RPC stdout stream.
- **Global Concurrency Guard (`handlers.py:41`):**
  Uses `_scan_lock = asyncio.Lock()` to serialize scan tool calls, preventing parallel client requests from stomping global proxy, timeout, or concurrency settings.
- **Cancellation Shielding (`_run_in_thread` - `handlers.py:44-68`):**
  Uses `asyncio.shield` and thread-completion awaiting to ensure that if an MCP client cancels a request, the underlying worker thread cleans up gracefully before propagating `CancelledError`.

### 8.2 Exposed Tools (`mcp/schemas.py`)
1. **`scan_username`:** Scans a handle. Accepts `username`, `category`, `module`, `allow_loud`, `no_nsfw`, `proxies`, `timeout`, `concurrency`, and full cross-scan parameters.
2. **`scan_email`:** Scans an email address. Accepts identical scoping and configuration parameters.
3. **`list_available_modules`:** Enumerates all supported categories and modules for either username or email modes.

---

## 9. PDF Report Generator & Optional Dependencies

**Module:** `user_scanner/core/pdf_generator.py`  
**Optional Requirement:** `pip install user-scanner[pdf]` (`reportlab>=4.0.0`, `pillow>=10.0.0`, `svglib>=1.5.0`).  
Flags: `REPORTLAB_AVAILABLE`, `PIL_AVAILABLE`, `SVGLIB_AVAILABLE` (`pdf_generator.py:14-41`).

### 9.1 SSRF Security & Media Validation Guardrails
**File & Line:** `user_scanner/core/pdf_generator.py:69-127`

To prevent Server-Side Request Forgery (SSRF) when downloading avatars:
1. `is_safe_ip(ip)`: Inspects IP address objects. Rejects loopback (`127.0.0.0/8`, `::1`), private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local, reserved, multicast, and IPv4-mapped IPv6 addresses.
2. `is_safe_media_url(url)`:
   - Enforces `http` or `https` schemes.
   - Forbids `"localhost"` hostnames.
   - Resolves hostnames via `socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)`.
   - Iterates through **all** returned DNS records; if **any** associated IP fails `is_safe_ip()`, the entire request is rejected.
   - Follows a maximum of 5 redirects, validating target IPs at each redirection hop.

### 9.2 Image Processing Pipeline
- `fetch_and_resize_image(url)` (`pdf_generator.py:129-205`):
  - Converts SVGs to ReportLab vector drawings via `svglib.svg2rlg`.
  - Converts raster images to RGB, crops them to a centered 1:1 square aspect ratio, and resizes them down to max 600x600 via Pillow's `LANCZOS` resampler.
  - Re-encodes output as JPEG at 90% quality in memory.
- `download_images_parallel(items)` (`pdf_generator.py:207-244`):
  - Executes parallel media downloads across up to 10 worker threads.

---

## 10. Performance Analysis, Import Costs & Error Resilience

### 10.1 Micro-Benchmark Telemetry
Benchmarked on Windows 11 x64 within the Sherlock-V2 virtual environment:

| Operation | Wall Time | Notes |
| :--- | :--- | :--- |
| `import user_scanner` | **10.1 ms** | Package root `__init__.py` is completely empty. |
| `from user_scanner.core import engine` | **3,966.6 ms** | Heavy initial cost: loads `curl_cffi`, `httpx`, and `rich`. |
| `from user_scanner.core import orchestrator` | **1,828.5 ms** | Threadpool initialization and Rich progress setup. |
| `load_categories(is_email=False)` | **54.3 ms** | Filesystem folder discovery (`iterdir()`). |
| `load_modules()`: **All User Categories** | **62,456.2 ms (~62.5s)** | Dynamically compiles 2,521 individual Python AST modules. |
| `load_modules()`: **All Email Categories** | **12,170.8 ms (~12.2s)** | Dynamically compiles 220 individual Python AST modules. |
| Second call to `load_modules()` | **< 0.05 ms** | Instantaneous cache hit via `@functools.lru_cache`. |

### 10.2 Catastrophic Failure Mode in `load_modules`
**File & Line:** `user_scanner/core/helpers.py:503-517`

```python
@functools.lru_cache(maxsize=None)
def load_modules(category_path: Path) -> List[ModuleType]:
    modules = []
    for file in category_path.glob("*.py"):
        if file.name == "__init__.py":
            continue
        spec = importlib.util.spec_from_file_location(file.stem, str(file))
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # <--- CRITICAL HAZARD: NO TRY-EXCEPT BLOCK

        modules.append(module)
    return modules
```

#### The Vulnerability:
There is no exception handling around `spec.loader.exec_module(module)`.
1. **Single-Point-of-Failure:** If a single module file in a directory contains a syntax error, an import error (such as a missing optional third-party library), or raises any exception at module level, **the entire category loading sequence crashes**.
2. **LRU Cache Invalidation:** Because the function raises an exception before returning, `functools.lru_cache` **does not store the partial result**. Every subsequent call will re-trigger the entire file loading loop and fail repeatedly.

---

## 11. Flet GUI Wrapper Architecture & Integration Blueprint

When integrating `user-scanner` into Sherlock-V2's Flet desktop interface, the following architectural challenges and solutions must be addressed:

### 11.1 Progress Hook Limitations & Custom Worker Architecture
- **Problem:** The built-in orchestrators (`orchestrator.py` and `email_orchestrator.py`) do not expose programmatic progress callbacks. Their progress tracking is tightly coupled to `rich.progress.Progress`, which prints terminal ANSI sequences directly to `sys.stdout`.
- **Solution for Sherlock-V2:**
  Do **not** invoke `run_user_full()` or `run_email_full_batch()` directly inside the GUI. Instead, implement a custom UI scan worker using `engine.check(module, target)`:
  ```python
  # Recommended Flet Integration Pattern
  async def run_flet_scan(modules: list, target: str, on_progress, on_result):
      sem = asyncio.Semaphore(user_concurrency)
      total = len(modules)
      completed = 0
      
      async def _worker(mod):
          nonlocal completed
          async with sem:
              site_name = get_site_name(mod)
              on_progress(completed, total, site_name)
              # Explicitly handle loud skipping
              if not allow_loud and is_loud(site_name):
                  res = Result.skipped().update(site_name=site_name, username=target)
              else:
                  res = await engine.check(mod, target)
              completed += 1
              on_result(res)
              on_progress(completed, total, site_name)
              
      await asyncio.gather(*[_worker(m) for m in modules])
  ```

### 11.2 Cancellation Mechanics
- **Problem:** `run_user_full` and `run_email_full_batch` are synchronous functions wrapping `asyncio.run()`. Once initiated on a background thread, they cannot be cleanly interrupted from the outside; `_async_worker` lacks any cancellation token or event check.
- **Solution for Sherlock-V2:**
  Using an async worker loop based on `engine.check` allows binding tasks to an `asyncio.TaskGroup` or tracking task references. When the user clicks "Cancel" in Flet, calling `task.cancel()` across pending module checks immediately cancels remaining network requests.

### 11.3 Concurrency & Global State Bleed
- **Problem:**
  - `orchestrator.MAX_CONCURRENT_REQUESTS = 60` and `email_orchestrator.MAX_CONCURRENT_REQUESTS = 25` are module-level globals.
  - `helpers._global_timeout` and `helpers._proxy_manager` are process-wide globals.
  - `email_orchestrator` permanently monkeypatches `httpx.Client` and `httpx.AsyncClient` upon import.
- **Solution for Sherlock-V2:**
  Multi-tab or concurrent target scanning in Flet will cross-contaminate settings unless requests are either serialized (as done in `mcp/handlers.py` via `_scan_lock`) or executed within isolated worker subprocesses.

### 11.4 Mitigating 60-Second Module Compilation Startup
- **Problem:** Calling `load_modules()` on the full 2,521 `user_scan` modules freezes execution for over 60 seconds on first run.
- **Solution for Sherlock-V2:**
  Implement background pre-warming at application startup:
  1. Show a splash screen or background status indicator ("Pre-warming OSINT vector cache...").
  2. Spawn a background thread that executes `load_categories(False)` and iterates through categories calling `load_modules(cat_path)` before the user triggers their first scan. Subsequent scans will hit the LRU cache instantly (<1 ms).

---

## 12. Verification Checklist & Site-Packages Citations

| Subsystem | Module File | Key Lines | Function / Symbol |
| :--- | :--- | :--- | :--- |
| **Engine API** | `core/engine.py` | 12-43 | `async def check(module, target)` |
| | `core/engine.py` | 45-57 | `async def check_category(...)` |
| | `core/engine.py` | 59-71 | `async def check_all(...)` |
| **User Orchestrator**| `core/orchestrator.py` | 27-35 | `MAX_CONCURRENT_REQUESTS`, `set_concurrency` |
| | `core/orchestrator.py` | 37-81 | `_async_worker` (loud check, timeout, retry) |
| | `core/orchestrator.py` | 83-163 | `_run_batch` (rich Progress bar, streaming) |
| | `core/orchestrator.py` | 165-261 | `run_user_module`, `run_user_category`, `run_user_full` |
| | `core/orchestrator.py` | 279-365 | `make_request`, `generic_validate`, `status_validate` |
| **Email Orchestrator**| `core/email_orchestrator.py`| 23-53 | Monkeypatched `httpx.Client` / `AsyncClient` |
| | `core/email_orchestrator.py`| 56-63 | `MAX_CONCURRENT_REQUESTS = 25`, `set_concurrency` |
| | `core/email_orchestrator.py`| 206-316 | `run_email_module_batch`, `run_email_full_batch` |
| **Helpers & Config** | `core/helpers.py` | 27-84 | `LOUD_MODULES` (53 sites) |
| | `core/helpers.py` | 86-442 | `EMAIL_DOMAIN_SCOPES` (26 regions) |
| | `core/helpers.py` | 448-453 | `ScanConfig` dataclass |
| | `core/helpers.py` | 474-494 | `parse_email_domain_scopes()` |
| | `core/helpers.py` | 503-517 | `load_modules()` (lru_cache, importlib loader) |
| | `core/helpers.py` | 519-536 | `load_categories()` (no_nsfw folder filter) |
| | `core/helpers.py` | 608-674 | `ProxyManager` (round-robin, scheme normalize) |
| | `core/helpers.py` | 680-701 | `set_proxy_manager`, `get_proxy`, `get_proxy_count` |
| **Result Model** | `core/result.py` | 26-34 | `_neutralize_csv_cell()` (CSV injection guard) |
| | `core/result.py` | 68-85 | `Status(Enum)` (TAKEN, AVAILABLE, ERROR, SKIPPED)|
| | `core/result.py` | 100-126 | `Result.update()` (extra & media sanitization) |
| | `core/result.py` | 184-224 | `to_dict()`, `to_json()`, `to_csv()` |
| | `core/result.py` | 254-286 | `get_console_output()` (Unicode tree formatter) |
| **Cross-Scan** | `core/cross_scan.py` | 60-80 | `CrossScanConfig` dataclass |
| | `core/cross_scan.py` | 82-185 | `run_cross_scan()` multi-round coordinator |
| | `core/confidence.py` | 60-86 | `Confidence(Enum)` (CONFIRMED, LIKELY, etc.) |
| | `core/pivots.py` | 25-88 | Pivot key registries (`HANDLE_KEYS`, `EMAIL_KEYS`)|
| **Hudson Rock** | `core/hudson.py` | 22-48 | `check_hudson_permission()` disclaimer & prompt |
| | `core/hudson.py` | 49-106 | `run_hudson_scan()` Cavalier API consumer |
| **Permutations** | `core/patterns.py` | 178-223 | `expand_patterns()`, `expand_patterns_random()` |
| | `core/patterns.py` | 225-238 | `count_patterns()` combinatorial calculator |
| **TLS Impersonation**| `core/impersonate.py` | 19-42 | `impersonate_validate()` (curl_cffi sessions) |
| **MCP Server** | `mcp/server.py` | 50-71 | `main()` stdio server entry point |
| | `mcp/handlers.py` | 40-68 | `_scan_lock` serialization & cancel shielding |
| | `mcp/schemas.py` | 5-188 | FastMCP tool definitions |
| **PDF Generator** | `core/pdf_generator.py` | 69-127 | `is_safe_ip()`, `is_safe_media_url()` (SSRF defense)|
| | `core/pdf_generator.py` | 246-359 | `generate_pdf_report()` |
