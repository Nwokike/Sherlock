# phonsint 0.1.0 Dependency Reference & Architectural Study

**Target Package:** `phonsint` v0.1.0  
**Environment Path:** `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/phonsint`  
**Distribution Metadata:** `phonsint-0.1.0.dist-info`  
**Target Document:** `/home/maikel/.zcode/workspace/default/Sherlock-V2/docs/reference/dep-phonsint.md`  

---

## 1. Executive Summary

`phonsint` (version 0.1.0) is a Python-based silent phone reconnaissance and identity footprinting suite installed in Sherlock-V2's virtual environment. It provides automated OSINT capabilities to determine whether a target phone number is registered across diverse web platforms (authentication providers, CRM systems, e-commerce, and social networks) without triggering one-time passwords (OTP), SMS alerts, voice calls, or direct notifications to the target device.

The package is architected around:
1. An E.164 phone number parser and normalization engine (`phonsint.core.parser`).
2. An async-first orchestrator with concurrent worker management (`phonsint.core.orchestrator`).
3. A structured result and reporting schema (`phonsint.core.result`).
4. A TLS/browser-impersonating HTTP client based on `curl_cffi` (`phonsint.core.impersonate`).
5. A pluggable category/module directory structure (`phonsint.modules.*`).

---

## 2. Package Layout & Directory Structure

```
phonsint/
├── __init__.py                     # Package entry point; defines __version__ (0.1.0)
├── __main__.py                     # CLI entry point (argparse, rich console, exporter)
├── core/
│   ├── __init__.py                 # Core package docstring (empty __all__)
│   ├── helpers.py                  # ScanConfig, module/category loaders, loud-check helpers
│   ├── impersonate.py              # Browser TLS fingerprint impersonation engine (curl_cffi)
│   ├── orchestrator.py             # Asynchronous scan orchestrator & worker queue
│   ├── parser.py                   # E.164 & national phone number normalization (phonenumbers)
│   └── result.py                   # Status enum, Result model, serialization & styling
└── modules/
    ├── __init__.py                 # Modules package docstring
    ├── auth/
    │   ├── __init__.py
    │   └── microsoft.py            # Microsoft Live OAuth credential type check
    ├── crm/
    │   ├── __init__.py
    │   └── zoho.py                 # Zoho Accounts cross-DC lookup
    ├── shopping/
    │   ├── __init__.py
    │   └── amazon.py               # Amazon OpenID sign-in state evaluation
    └── social/
        ├── __init__.py
        ├── facebook.py             # Facebook CAA GraphQL search & recovery enumeration
        └── instagram.py            # Instagram CAA GraphQL search & LOX PoW timelock solver
```

---

## 3. Package Exports & Public API

- **`phonsint/__init__.py:1-6`**:
  ```python
  """
  phonsint - Advanced Silent Phone Reconnaissance & Identity Footprinting Suite
  """

  __version__ = "0.1.0"
  ```
  - **No root-level re-exports:** The package does **not** expose `run_scan`, `PhoneInfo`, `Result`, or `ScanConfig` at the root `phonsint` namespace.
  - **No `__all__` list:** There is no module-level `__all__` in `__init__.py` or `core/__init__.py`.
  - **Integration requirement for Sherlock-V2:** Any consuming service or adapter must explicitly import from the subpackages:
    - `from phonsint.core.parser import PhoneInfo, parse_phone_number`
    - `from phonsint.core.orchestrator import run_scan, run_scan_async`
    - `from phonsint.core.helpers import ScanConfig, load_categories, load_modules`
    - `from phonsint.core.result import Result, Status`
    - `from phonsint.core.impersonate import set_global_timeout, set_global_proxy`

---

## 4. Phone Number Parser (`phonsint/core/parser.py`)

The parsing engine relies on Google's `phonenumbers` library to parse, validate, and normalize telephone inputs into standardized E.164 and localized forms.

### 4.1 Data Model: `PhoneInfo`
**File & Line:** `phonsint/core/parser.py:6-17`

```python
@dataclass(frozen=True)
class PhoneInfo:
    """Represents a validated and normalized phone number for platform checks."""
    raw_input: str
    is_valid: bool
    e164: str
    international_format: str
    national_format: str
    country_code: int
    national_number: int
    region_code: str
```

- **Immutability:** Decorated with `@dataclass(frozen=True)`, ensuring thread-safety across concurrent async tasks.
- **Key attributes:**
  - `e164`: Fully-qualified E.164 formatted string (e.g., `"+14155552671"`). Used as the primary lookup key across platform modules.
  - `country_code`: Integer country calling code (e.g., `1`, `44`, `91`).
  - `national_number`: Integer local subscriber number (e.g., `4155552671`). Required by services like Zoho that separate country code from subscriber digits (`{info.country_code}-{info.national_number}`).
  - `region_code`: ISO 3166-1 two-letter alpha country code (e.g., `"US"`, `"GB"`).
  - `is_valid`: Boolean flag indicating whether the number is valid and allocated per ITU-T standards.

### 4.2 Parsing Routine: `parse_phone_number`
**File & Line:** `phonsint/core/parser.py:19-61`

- **Signature:** `parse_phone_number(raw: str, default_region: Optional[str] = None) -> PhoneInfo`
- **Fallback Logic (`parser.py:23-41`):**
  1. Strips leading/trailing whitespace.
  2. If the input does not start with `+` and no `default_region` is supplied, it prefixes `+` as an initial probe.
  3. If parsing fails with `phonenumbers.NumberParseException`, it performs a second attempt using `"US"` as the fallback region.
  4. If parsing fails completely, it returns a non-throwing fallback `PhoneInfo` instance with `is_valid=False`, zeroed numeric fields (`country_code=0`, `national_number=0`), and empty `region_code=""`.
- **Normalization (`parser.py:43-60`):**
  Extracts E.164, international, and national formats using `phonenumbers.PhoneNumberFormat` enums.

---

## 5. Result Model & Status (`phonsint/core/result.py`)

`phonsint` encapsulates module execution outcomes in a structured `Result` object.

### 5.1 Status Enum
**File & Line:** `phonsint/core/result.py:62-77`

```python
class Status(Enum):
    TAKEN = 0        # Target phone number is registered / found on platform
    AVAILABLE = 1    # Phone number is not registered / available
    ERROR = 2        # Execution error, captcha, network failure, or API drift
    SKIPPED = 3      # Skipped (e.g. loud module skipped under silent mode)
```

- **`to_label()` (`result.py:68-74`):**
  - `Status.TAKEN` -> `"Registered"`
  - `Status.AVAILABLE` -> `"Not Registered"`
  - `Status.ERROR` -> `"Error"`
  - `Status.SKIPPED` -> `"Skipped"`

### 5.2 Result Class
**File & Line:** `phonsint/core/result.py:79-277`

- **Fields (`result.py:80-89`):**
  - `status: Status`
  - `reason: str | Exception | None`
  - `phone: Optional[str]`
  - `site_name: Optional[str]`
  - `category: Optional[str]`
  - `url: str`
  - `extra: Dict[str, str | bool | int]` (enriched metadata, e.g., display names, masked emails, datacenters)
  - `media: Dict[str, str]` (profile avatar URLs, icons)

- **Sanitization & Updating (`result.py:91-120`):**
  - `update(**kwargs)`: Dynamically assigns `phone`, `site_name`, `category`, `url`, and `reason`.
  - Keys in `extra` are normalized: trimmed, stripped of trailing colons, converted to lowercase, with spaces replaced by underscores (`result.py:104`).
  - Values in `extra` are coerced to strings unless they are already `bool` or `int` (`result.py:108-111`).
  - Values in `media` are trimmed and lowercased keys (`result.py:113-118`).

- **Convenience Constructors (`result.py:121-144`):**
  - `Result.taken(reason=None, **kwargs)`
  - `Result.available(reason=None, **kwargs)`
  - `Result.error(reason=None, **kwargs)`
  - `Result.skipped(reason=None, **kwargs)`
  - `Result.from_number(i: int, reason=None)`

- **Exception Humanization (`result.py:45-60`):**
  Transforms low-level socket/network error codes (`10054`, `11001`, `errno 7`, `errno 101`, `curl: (28)`) into human-readable descriptions (e.g., `"Connection closed by remote server"`, `"No internet connection or DNS failure"`).

- **Security: CSV Formula Injection Mitigation (`result.py:23-31`, `result.py:196`):**
  The helper `_neutralize_csv_cell` detects leading formula trigger characters (`=`, `+`, `-`, `@`, `\t`, `\r`, `\n`) and prefixes them with a single quote (`'`) before serializing via `to_csv()`.

- **Filtering & Visibility Methods:**
  - `is_found() -> bool` (`result.py:261-263`): Returns `True` iff `status == Status.TAKEN`.
  - `is_visible(configs: Optional[ScanConfig] = None) -> bool` (`result.py:265-270`):
    If `configs.show_all` is `True`, returns all results; otherwise, returns only `Status.TAKEN` and `Status.SKIPPED`.
  - `show(configs: Optional[ScanConfig] = None) -> Result` (`result.py:271-276`): Prints console output if visible, returning `self`.

---

## 6. Helpers & Configuration (`phonsint/core/helpers.py`)

### 6.1 `ScanConfig` Dataclass
**File & Line:** `phonsint/core/helpers.py:12-19`

```python
@dataclass(frozen=True)
class ScanConfig:
    allow_loud: bool = False
    show_all: bool = False
    verbose: bool = False
    timeout: Optional[float] = None
    concurrency: int = 15
```

- **Fields:**
  - `allow_loud`: Permits execution of modules that could alert the target (defaults to `False`).
  - `show_all`: If `True`, console output includes `Not Registered` (AVAILABLE) and `Error` results.
  - `verbose`: Prints diagnostic URLs and request targets.
  - `timeout`: Per-module timeout in seconds (defaults to `None`, falling back to 15.0s in orchestrator).
  - `concurrency`: Concurrency semaphore limit (defaults to `15`).

### 6.2 Category & Module Discovery
- **`load_categories() -> Dict[str, Path]` (`helpers.py:37-47`):**
  Scans the `phonsint/modules/` directory, resolving subfolders that do not begin with `__`.
- **`load_modules(category_path: Path) -> List[ModuleType]` (`helpers.py:50-64`):**
  Iterates over `.py` files in a given category folder using `importlib.util.spec_from_file_location`.
- **`get_scan_func(module: ModuleType) -> Optional[Callable[..., Any]]` (`helpers.py:67-74`):**
  Finds any module attribute beginning with `validate_` that is either a standard function or coroutine function.
- **`get_site_name(module: ModuleType) -> str` (`helpers.py:25-27`):**
  Derives a display name from the module's file stem (e.g., `"microsoft"` -> `"Microsoft"`).
- **`find_category(module: ModuleType) -> str` (`helpers.py:30-34`):**
  Extracts the category name from `module.__name__` (e.g., `phonsint.modules.auth.microsoft` -> `"Auth"`).

### 6.3 Critical Adapter Note: Exception Swallowing in `load_modules`
**File & Line:** `phonsint/core/helpers.py:59-63`

```python
try:
    spec.loader.exec_module(module)
    modules.append(module)
except Exception:
    continue
```

> **IMPORTANT FOR SHERLOCK-V2 ADAPTER:**  
> `load_modules` wraps module execution in a bare `except Exception: continue`. If any scan module or custom adapter contains an `ImportError`, syntax error, missing dependency, or throws an unhandled error at import time, **the module is silently skipped with zero logging or warnings**.
> When writing custom modules or dynamic adapters for Sherlock-V2, verify imports ahead of time or test modules in isolation to ensure they are not silently dropped.

---

## 7. Orchestration & Concurrency Engine (`phonsint/core/orchestrator.py`)

The orchestrator manages parallel execution across categories and modules using `asyncio`.

### 7.1 Async Worker: `_async_worker`
**File & Line:** `phonsint/core/orchestrator.py:21-70`

- **Signature:**
  ```python
  async def _async_worker(
      module: ModuleType,
      phone_info: PhoneInfo,
      sem: asyncio.Semaphore,
      configs: ScanConfig,
      cat_override: Optional[str] = None,
      on_start: Optional[Callable[[str], None]] = None,
  ) -> Result
  ```
- **Execution Flow:**
  1. **Concurrency Gate (`orchestrator.py:29`):** Bounded by `async with sem:`.
  2. **Callback (`orchestrator.py:31-32`):** Fires `on_start(site_name)` to notify progress bars or listeners.
  3. **Function Discovery (`orchestrator.py:34`):** Retrieves scan function via `get_scan_func(module)`. If missing, returns `Result.error("{site_name} has no validate_ function")`.
  4. **Loud Module Gate (`orchestrator.py:46-47`):**
     ```python
     if not configs.allow_loud and is_loud(site_name):
         return Result.skipped(reason="Loud module skipped (use --allow-loud)", **params)
     ```
  5. **Timeout Calculation (`orchestrator.py:50`):**
     `timeout_val = (configs.timeout or 15.0) + 5.0`
     *(Adds a 5.0-second buffer over the configured timeout).*
  6. **Dynamic Signature Inspection (`orchestrator.py:52-53`):**
     ```python
     sig = inspect.signature(func)
     arg = (
         phone_info 
         if len(sig.parameters) == 1 and next(iter(sig.parameters.values())).name in ("phone_info", "info") 
         else phone_info.e164
     )
     ```
     If the module function declares a single parameter named `info` or `phone_info`, the worker passes the full `PhoneInfo` dataclass; otherwise, it passes the raw `phone_info.e164` string.
  7. **Coro vs Sync Dispatch (`orchestrator.py:55-58`):**
     - If `inspect.iscoroutinefunction(func)`: calls `await asyncio.wait_for(func(arg), timeout=timeout_val)`.
     - If synchronous: dispatches via `await asyncio.wait_for(asyncio.to_thread(func, arg), timeout=timeout_val)`.
  8. **Exception Handling (`orchestrator.py:64-67`):**
     - `asyncio.TimeoutError` -> returns `Result.error("Timed out after {timeout_val}s")`.
     - `Exception` -> returns `Result.error(str(e))`.

### 7.2 Main Async Orchestrator: `run_scan_async`
**File & Line:** `phonsint/core/orchestrator.py:72-168`

- Discovers categories via `load_categories()`.
- Filters categories and modules based on `category_filter` and `module_filter` strings (comma-delimited).
- Spawns tasks per module wrapped in `_async_worker`.
- Integrates with `rich.progress.Progress` for transient progress reporting (`orchestrator.py:116-128`).
- Uses `asyncio.as_completed(tasks)` to yield and print results as they arrive (`orchestrator.py:156-165`).

### 7.3 Synchronous Entry Point: `run_scan`
**File & Line:** `phonsint/core/orchestrator.py:170-177`

```python
def run_scan(
    phone_info: PhoneInfo,
    configs: ScanConfig,
    category_filter: Optional[str] = None,
    module_filter: Optional[str] = None,
) -> List[Result]:
    return asyncio.run(run_scan_async(phone_info, configs, category_filter, module_filter))
```

---

## 8. Impersonation & HTTP Transport (`phonsint/core/impersonate.py`)

`phonsint` avoids standard Python `requests` or `httpx` to bypass bot-detection, Cloudflare, Akamai, and AWS WAFs by using `curl_cffi` to mimic real browser TLS fingerprints and HTTP/2 settings.

- **Impersonation Target (`impersonate.py:6`):** Defaults to `impersonate="chrome"` (or `"chrome120"` in specific modules like Zoho).
- **Session Pooling (`impersonate.py:9-12`, `35-65`):**
  - Manages a thread-safe cache `_sessions: dict[tuple, cffi.Session]` keyed by `(impersonate, proxy)`.
  - Supports optional URL warmup via `_warmed: set[tuple]` to pre-establish cookies and TLS sessions.
- **Global Settings (`impersonate.py:17-33`):**
  - `set_global_timeout(val: Optional[float])` / `get_global_timeout() -> float` (default `15.0`)
  - `set_global_proxy(val: Optional[str])` / `get_global_proxy() -> Optional[str]`
- **Request Functions:**
  - `impersonate_request(url, method="GET", warmup_url=None, impersonate=DEFAULT_IMPERSONATE, **kwargs)` (`impersonate.py:68-80`): Synchronous call; sets `allow_redirects=False` by default.
  - `impersonate_request_async(...)` (`impersonate.py:82-97`): Asynchronous wrapper utilizing `asyncio.to_thread`.

---

## 9. Inventory of Modules & Reconnaissance Mechanisms

`phonsint` 0.1.0 ships with **5 scan modules** across **4 categories**:

| Category | Module | Function Signature | Protocol / Method | Target / Endpoints | Enriched Metadata (`extra` / `media`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`auth`** | `microsoft.py` | `validate_microsoft(info: PhoneInfo) -> Result` (`auth/microsoft.py:57`) | HTTPS POST (OAuth) | `login.live.com/GetCredentialType.srf` | `display_name` |
| **`crm`** | `zoho.py` | `validate_zoho(info: PhoneInfo) -> Result` (`crm/zoho.py:14`) | HTTPS POST (CSRF/API) | `accounts.zoho.com/signin/v2/lookup/{phone}` | `user_id`, `allowed_modes`, `datacenter`, `status` |
| **`shopping`** | `amazon.py` | `validate_amazon(info: PhoneInfo) -> Result` (`shopping/amazon.py:26`) | HTTPS POST (OpenID Form) | `amazon.com/ap/signin` | None |
| **`social`** | `facebook.py` | `validate_facebook(info: PhoneInfo) -> Result` (`social/facebook.py:25`) | HTTPS POST (GraphQL CAA) | `facebook.com/api/graphql/` (`CAAFBAccountSearchViewQuery`) | `name`, `email` (masked), `matched_accounts`, `profiles`, `avatar` |
| **`social`** | `instagram.py` | `validate_instagram(info: PhoneInfo) -> Result` (`social/instagram.py:31`) | HTTPS POST (GraphQL CAA) | `instagram.com/api/graphql` (`CAAIGAccountSearchViewQuery`) | `name`, `recovery_method`, `avatar` |

### Detailed Module Mechanics:
1. **Microsoft (`phonsint/modules/auth/microsoft.py`):**
   - Fetches Live OAuth login page to extract `sUnauthSessionID`, `sFTTag`, and flow token via `_extract_server_data` (`microsoft.py:19-54`).
   - Issues a JSON POST to `GetCredentialType.srf` with `{"checkPhones": True, "username": phone_target}` (`microsoft.py:85-105`).
   - Evaluates `IfExistsResult`: `0` indicates account exists (`Status.TAKEN`, extracting `display_name` if present); `1` indicates account does not exist (`Status.AVAILABLE`) (`microsoft.py:119-128`).
2. **Zoho (`phonsint/modules/crm/zoho.py`):**
   - Formats phone as `{country_code}-{national_number}` (`zoho.py:19`).
   - Obtains `iamcsr` cookie from `accounts.zoho.com/signin` and posts to `/signin/v2/lookup/{target}` (`zoho.py:35-55`).
   - Handles multi-datacenter routing: if `User exists in another DC` (U400), follows `redirect_uri` to query foreign datacenters (e.g. `accounts.zoho.in`, `accounts.zoho.eu`) to extract the account's internal `user_id` (`zoho.py:82-112`).
   - Detects inactive or spam-flagged accounts (U409) (`zoho.py:114-116`).
3. **Amazon (`phonsint/modules/shopping/amazon.py`):**
   - Retrieves sign-in page, parses hidden inputs, extracts dynamic login field name (`ap_email_login`) (`amazon.py:30-62`).
   - Submits form data with phone target. Inspects response for `"Looks like you're new to Amazon"` (`Status.AVAILABLE`) vs password input / CVF verification challenge (`Status.TAKEN`) (`amazon.py:80-87`).
4. **Facebook (`phonsint/modules/social/facebook.py`):**
   - Harvests `lsd` and `jazoest` tokens from `facebook.com/login/identify/` (`facebook.py:28-70`).
   - Queries Meta CAA Account Search GraphQL (`doc_id: 28496659306608697`) (`facebook.py:71-109`).
   - If found, parses profile name and avatar picture (`facebook.py:137-146`).
   - **Enrichment:** Simulates CAA Account Selection mutation (`doc_id: 9730637087034984`) to retrieve the password reset initiate page, extracting masked email addresses (e.g. `j*****e@gmail.com`) via regex without sending verification codes (`facebook.py:155-231`).
5. **Instagram (`phonsint/modules/social/instagram.py`):**
   - Obtains CSRF and LSD tokens from `instagram.com` (`instagram.py:34-64`).
   - Requests `ScriptedTimelockChallengeQuery` from Meta CAA (`doc_id: 27729863049988601`) (`instagram.py:78-107`).
   - **LOX Client-Side Timelock Solver (`instagram.py:21-28`, `121-129`):** Solves Meta's client-side proof-of-work puzzle via repeated modular squaring:
     $$val = (base^{2^{iterations}}) \pmod{modulus}$$
   - Submits solved PoW token in `CAAIGAccountSearchViewQuery` (`doc_id: 36716895674620546`) (`instagram.py:131-178`).
   - If contact recovery points exist (`len(contact_points) > 0`), marks account `TAKEN`, extracting recovery methods (e.g., `"Send an SMS"`, `"Send an email"`) and profile metadata (`instagram.py:204-222`).

---

## 10. Loud Modules & The Silent-by-Default Guarantee

### 10.1 Loud Modules Definition
**File & Line:** `phonsint/core/helpers.py:9`

```python
# List of modules that could potentially alert the target via SMS or phone call
LOUD_MODULES: List[str] = []
```
- In `phonsint` v0.1.0, `LOUD_MODULES` is initialized as an **empty list**.
- `is_loud(site_name: str) -> bool` (`helpers.py:21-22`):
  ```python
  def is_loud(site_name: str) -> bool:
      return site_name.lower() in LOUD_MODULES
  ```
  Returns `False` for all current 5 modules.

### 10.2 Silent-by-Default Guarantee
- **Passive Enumeration Design:** All 5 modules in 0.1.0 interact solely with pre-authentication, account-recovery search, or credential-type resolution endpoints.
- **No Direct Dispatch:** No module submits final OTP dispatch forms or password reset trigger buttons that send SMS/voice notifications.
- **Gate Enforcement (`orchestrator.py:46-47`):**
  If any module is added to `LOUD_MODULES` in future updates or extensions, `_async_worker` will automatically skip it with `Status.SKIPPED` unless `ScanConfig(allow_loud=True)` is explicitly provided.
- **Default Skip Reason (`result.py:152-153`):**
  When a result is marked `Status.SKIPPED` without an explicit reason, `get_reason()` defaults to `"Skipped because it may alert the target"`.

---

## 11. Architectural Comparison: `phonsint` vs `user_scanner`

Sherlock-V2 incorporates `user-scanner` (`>=1.5.2.3`). Below is an in-depth comparative analysis highlighting architectural and behavioral divergences:

| Architectural Dimension | `phonsint` (v0.1.0) | `user_scanner` (v1.5.2.3) | Critical Considerations for Adapter |
| :--- | :--- | :--- | :--- |
| **Primary Target Entity** | Phone Number (ITU E.164 string & `PhoneInfo` dataclass) | Username string or Email string | `phonsint` requires phone parsing & E.164 normalization before execution. |
| **`ScanConfig` Definition** | `allow_loud: bool`<br>`show_all: bool`<br>`verbose: bool`<br>`timeout: Optional[float]`<br>`concurrency: int = 15`<br>(`phonsint/core/helpers.py:13-19`) | `allow_loud: bool`<br>`no_nsfw: bool`<br>`show_all: bool`<br>`verbose: bool`<br>`timeout: Optional[float]`<br>(`user_scanner/core/helpers.py:448-453`) | `phonsint` contains `concurrency`, but lacks `no_nsfw`. `user_scanner` contains `no_nsfw`, but lacks `concurrency` on `ScanConfig`. |
| **Timeout Handling** | `timeout_val = (configs.timeout or 15.0) + 5.0` used in `asyncio.wait_for(...)` (`phonsint/core/orchestrator.py:50`). | `module_timeout = (get_global_timeout() or 15.0) + 10.0` (`user_scanner/core/orchestrator.py:66`). | **Timeout divergence:** `user_scanner` ignores `configs.timeout` in `_async_worker` and relies on `get_global_timeout()`. In `phonsint`, `configs.timeout` is read directly by `_async_worker`. However, `impersonate.py`'s internal session timeout uses a separate `_global_timeout`! |
| **Concurrency Architecture** | Instance-level `asyncio.Semaphore(configs.concurrency)` per scan (`phonsint/core/orchestrator.py:112`). Default: `15`. | Module-level global `MAX_CONCURRENT_REQUESTS = 60` and shared `ThreadPoolExecutor(max_workers=...)` (`user_scanner/core/orchestrator.py:27-35`). | `phonsint` encapsulates concurrency within each scan invocation; `user_scanner` modifies global state (`set_concurrency`). |
| **Module Loader Exception Safety** | `try: exec_module() except Exception: continue` (`phonsint/core/helpers.py:59-63`). **Silent swallow.** | No `try/except` around `exec_module()` (`user_scanner/core/helpers.py:513`). Exceptions propagate immediately. | `phonsint` will silently ignore any broken module file, making debugging silent failures critical. |
| **Module Loading Cache** | No caching. Discovers and executes files on each call (`phonsint/core/helpers.py:50`). | Uses `@functools.lru_cache(maxsize=None)` on `load_modules` and `load_categories` (`user_scanner/core/helpers.py:503, 520`). | `phonsint` modules reload on every scan invocation. |
| **Scan Function Signature Detection** | Inspects parameter names (`"phone_info"`, `"info"` vs E.164 string) (`phonsint/core/orchestrator.py:52-53`). | Fixed single argument (`username: str` or `email: str`). | `phonsint` modules can accept either full `PhoneInfo` or a raw string. |
| **Execution Paradigm** | Async-first (`async def`), with sync fallback via `asyncio.to_thread` (`phonsint/core/orchestrator.py:55-58`). | Hybrid: Coroutines awaited directly; sync functions run on `_shared_executor` thread pool (`user_scanner/core/orchestrator.py:67-74`). | All 5 built-in `phonsint` modules are native async coroutines. |
| **`Result` Model Identifier** | `self.phone: Optional[str]` (`phonsint/core/result.py:83`). | `self.username: Optional[str]` and `self.is_email: bool` (`user_scanner/core/result.py:91, 97`). | Field names differ (`phone` vs `username`). |
| **`Status.to_label()`** | Fixed labels: `"Registered"` / `"Not Registered"` (`phonsint/core/result.py:73`). | Parameterized: `to_label(is_email=False)` -> `"Found"` / `"Not Found"`; `is_email=True` -> `"Registered"` / `"Not Registered"` (`user_scanner/core/result.py:74-81`). | Display labels align with account ownership rather than username availability. |
| **Loud Module Tracking** | `LOUD_MODULES: List[str] = []` (`phonsint/core/helpers.py:9`). | `LOUD_MODULES: Dict[str, List[str]]` with `"user"` and `"email"` keys (`user_scanner/core/helpers.py:27-84`). | `phonsint` tracks a flat list of site names. |
| **HTTP Transport Engine** | `curl_cffi` session pool with TLS fingerprint impersonation (`phonsint/core/impersonate.py:4-49`). | Standard `httpx` client / requests, with custom Hudson/NextJS helpers. | `phonsint` is specifically optimized to avoid browser-fingerprint blocks. |

---

## 12. Implications & Implementation Guidelines for Sherlock-V2 Adapter

When constructing the Sherlock-V2 adapter layer for `phonsint`, the following technical constraints must be observed:

1. **Subpackage Imports Only:**  
   Because `phonsint/__init__.py` does not re-export core classes, the adapter must import from specific submodules (`phonsint.core.parser`, `phonsint.core.orchestrator`, `phonsint.core.helpers`, `phonsint.core.result`).
2. **Phone Number Sanitization & Pre-validation:**  
   Calls should always pass the target through `parse_phone_number(raw, default_region)` before passing to `run_scan` or `run_scan_async`. Check `phone_info.is_valid` to warn users if the input violates E.164 allocation rules.
3. **Module Loading Diagnostics:**  
   Because `phonsint.core.helpers.load_modules` silently catches and drops modules that fail to import (`helpers.py:62-63`), the Sherlock-V2 test suite must contain an explicit smoke test that asserts all expected modules are discovered:
   ```python
   categories = load_categories()
   assert "auth" in categories and "social" in categories
   all_mods = [m.__name__.split(".")[-1] for cat in categories.values() for m in load_modules(cat)]
   assert {"microsoft", "zoho", "amazon", "facebook", "instagram"}.issubset(set(all_mods))
   ```
4. **Timeout Synchronization:**  
   If configuring a custom timeout on `ScanConfig(timeout=X)`, the adapter should also call `phonsint.core.impersonate.set_global_timeout(X)` to ensure the underlying `curl_cffi` sessions respect the requested timeout rather than defaulting to `15.0s`.
5. **Proxy Configuration:**  
   If Sherlock-V2 uses outbound proxies (HTTP/SOCKS5), configure `phonsint.core.impersonate.set_global_proxy(proxy_url)` prior to initiating scans.
6. **Unified Result Mapping:**  
   To harmonize with `user_scanner`'s result structures in Sherlock-V2, map:
   - `phonsint.Result.phone` -> Unified target entity
   - `phonsint.Result.status == Status.TAKEN` -> Registered / Positive identification
   - `phonsint.Result.extra` & `media` -> Enriched OSINT profile attributes (masked emails, display names, profile avatars)

---
*Document generated for Sherlock-V2 Reference Architecture.*  
*Source inspection: `phonsint 0.1.0` in `Sherlock-V2\.venv\Lib\site-packages\phonsint`.*
