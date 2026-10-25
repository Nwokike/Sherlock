# Dependency Reference: `curl-cffi` (0.16.3)

Comprehensive technical documentation for `curl-cffi` as vendored/installed in Sherlock-V2's virtual environment (`.venv/Lib/site-packages/curl_cffi`).

---

## 1. Version & Build Architecture

### 1.1 Installed Versions & Runtime Identification
- **Package Name**: `curl-cffi`
- **Installed Version**: `0.16.3` (resolved in `/home/maikel/.zcode/workspace/default/Sherlock-V2/uv.lock:103-125` and `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/curl_cffi-0.16.3.dist-info`)
- **Version Resolution Implementation**:
  - `curl_cffi/__version__.py:5`: `__version__ = metadata.version("curl_cffi")`
  - `curl_cffi/__version__.py:8-15`: Resolves the libcurl binary string without creating an active handle at import time:
    ```python
    def _resolve_curl_version() -> str:
        from ._wrapper import ffi, lib
        return ffi.string(lib.curl_version()).decode()

    __curl_version__ = _resolve_curl_version()
    ```
- **Underlying libcurl Engine**:
  ```text
  libcurl/8.21.0-IMPERSONATE BoringSSL zlib/1.3.1 brotli/1.2.0 zstd/1.5.7 WinIDN nghttp2/1.63.0 ngtcp2/1.20.0 nghttp3/1.15.0
  ```
- **Binary Architecture**:
  - Compiled with Google's **BoringSSL** (enabling client-hello extension ordering, GREASE, custom ciphers, and pseudo-header control).
  - Multi-protocol transport: HTTP/1.1, HTTP/2 (via `nghttp2/1.63.0`), HTTP/3 / QUIC (via `ngtcp2/1.20.0` and `nghttp3/1.15.0`).
  - Compression codecs: `zlib/1.3.1`, `brotli/1.2.0`, `zstd/1.5.7`.
  - CFFI dynamic link library: `curl_cffi/_wrapper.pyd` on Windows AMD64 (`curl_cffi/curl.py:17`).

---

## 2. Browser Impersonation (Chrome & Safari Profiles)

`curl-cffi` emulates exact browser network signatures (TLS ClientHello, HTTP/2 SETTINGS frames, pseudo-header order, and default request headers).

### 2.1 Profile Catalog & Default Aliases
Impersonation profiles are declared in `curl_cffi/requests/impersonate.py:8-126`:

| Browser Family | Default Alias (`impersonate.py:81-89`) | Canonical Target (`impersonate.py:92-102`) | Available Target Versions (`impersonate.py:8-78`) |
| :--- | :--- | :--- | :--- |
| **Chrome (Desktop)** | `"chrome"` | `"chrome150"` | `chrome99`, `chrome100`, `chrome101`, `chrome104`, `chrome107`, `chrome110`, `chrome116`, `chrome119`, `chrome120`, `chrome123`, `chrome124`, `chrome131`, `chrome133a`, `chrome136`, `chrome142`, `chrome145`, `chrome146`, `chrome150` |
| **Chrome (Android)** | `"chrome_android"` | `"chrome131_android"` | `chrome99_android`, `chrome131_android` |
| **Edge** | `"edge"` | `"edge101"` | `edge99`, `edge101` |
| **Safari (macOS)** | `"safari"` | `"safari2601"` | `safari153`, `safari155`, `safari170`, `safari180`, `safari184`, `safari260`, `safari2601` |
| **Safari (iOS)** | `"safari_ios"` | `"safari260_ios"` | `safari172_ios`, `safari180_ios`, `safari184_ios`, `safari260_ios` |
| **Safari (Beta)** | `"safari_beta"`, `"safari_ios_beta"` | `"safari2601"`, `"safari260_ios"` | Targets latest stable macOS / iOS Safari profiles |
| **Firefox** | `"firefox"` | `"firefox147"` | `firefox133`, `firefox135`, `firefox144`, `firefox147` |
| **Tor Browser** | `"tor"` | `"tor145"` | `tor145` |

*Deprecated Aliases*: `safari15_3`, `safari15_5`, `safari17_0`, `safari17_2_ios`, `safari18_0`, `safari18_0_ios` remain accepted for backward compatibility (`impersonate.py:61-68`, `curl_cffi/requests/utils.py:388-396`).

### 2.2 Profile Resolution & Execution Path
1. **Target Normalization**: `resolve_latest_browser_type(target)` (`impersonate.py:105-126`) maps human aliases (e.g., `"chrome"`, `"safari"`) to exact versioned presets.
2. **Native C Execution**:
   - For targets compiled into the libcurl binary (`NATIVE_TARGET_NAMES` in `utils.py:386-396`), `curl_cffi` invokes `curl.impersonate(normalized, default_headers=default_headers)` (`curl_cffi/curl.py:546-560`), which delegates directly to `lib.curl_easy_impersonate(self._curl, target.encode(), int(default_headers))` (`curl.py:558-560`).
3. **Custom / Remote Fingerprint Execution**:
   - For targets not in the native compile set, `_apply_fingerprint()` (`utils.py:419-587`) loads dynamic profiles from `FingerprintManager` (`curl_cffi/fingerprints.py:446-682`) and configures options via individual `c.setopt(...)` calls.
4. **Header Insertion & Preservation**:
   - When `default_headers=True` (`utils.py:555-569`), browser headers from the profile (e.g. `User-Agent`, `Accept`, `Accept-Language`, `sec-ch-ua`) are injected unless already present in user-provided headers (`utils.py:558-560`). User-supplied headers always take precedence over impersonation defaults.
   - Profile-dictated header ordering is enforced via `CurlOpt.HTTPHEADER_ORDER` (`utils.py:511`).

---

## 3. Session API

`curl-cffi` provides both synchronous (`Session`) and asynchronous (`AsyncSession`) wrappers over libcurl easy and multi handles (`curl_cffi/requests/session.py`).

### 3.1 Class Hierarchy & Architecture
- **`BaseSession[R]`** (`session.py:219-480`):
  - Base class providing configuration storage (`headers`, `cookies`, `auth`, `proxies`, `verify`, `timeout`, `impersonate`, `ja3`, `akamai`, `retry`).
  - Response parsing engine (`_parse_response`, `session.py:315-440`): parses raw headers into `Headers`, reads redirect histories via `CurlInfo.REDIRECT_HISTORY` (`session.py:363`), synchronizes cookies via `CurlInfo.COOKIECHANGES` (`session.py:413`), and populates network timing (`CurlInfo.TOTAL_TIME`, `session.py:421`).
  - Retry strategy backoff calculation (`_retry_delay`, `session.py:461-469`).
- **`Session(BaseSession[R])`** (`session.py:481-971`):
  - Thread-safe by default through `use_thread_local_curl=True` (`session.py:489, 553-577`). Each thread calling a shared `Session` instance accesses an independent `Curl` easy handle via `threading.local()` (`session.py:554, 574`), preventing race conditions while sharing session state (such as cookies).
  - Context manager support (`__enter__` / `__exit__`, `session.py:585-589`).
  - Underlying handle closing: `session.close()` (`session.py:591-595`).

### 3.2 Request Lifecycle & Options Inheritance
Calls to `session.get()`, `session.post()`, or `session.request()` (`session.py:850-944`) flow through:
1. `_check_session_closed()` (`session.py:891`).
2. Body position capture via `_capture_body_position()` (`session.py:894`) to allow body rewinding on retry or redirect (`session.py:898`).
3. Single execution attempt via `_request_once()` (`session.py:664-849`).
4. `set_curl_options()` (`utils.py:589-995`): merges session defaults with per-request parameters (URL parameters, headers, cookies, timeouts, proxies, TLS settings).
5. Execution:
   - Non-streaming: `c.perform()` (`session.py:827`).
   - Streaming: clones handle via `c.duphandle()`, delegates transfer to background thread via `ThreadPoolExecutor` (`session.py:773-790`), and yields chunks via thread-safe queue (`session.py:799-813`).
6. Upkeep: `session.upkeep()` (`session.py:661-662`) calls `curl.upkeep()` (`curl_easy_upkeep`) to send HTTP/2 PING frames and keep pooled connections alive.

---

## 4. Asynchronous Usage (`AsyncSession` & `AsyncCurl`)

### 4.1 Async Architecture (`session.py:973-1650`)
- **`AsyncSession` Initialization**:
  - Manages a pool of reusable `Curl` easy handles stored in an `asyncio.LifoQueue[Curl | None]` (`session.py:1069-1075`), sized by `max_clients` (default: 10).
  - Leases handles via `pop_curl()` (`session.py:1076-1080`) and releases them via `push_curl()` / `release_curl()` (`session.py:1082-1085, 1136-1144`).
- **Transfer Dispatcher**:
  - Powered by `AsyncCurl` (`curl_cffi/aio.py:171-332`), which wraps a `curl_multi` handle (`lib.curl_multi_init()`, `aio.py:181`).
  - Implements libcurl's event-driven socket action model:
    - `CURLMOPT_TIMERFUNCTION` (`aio.py:117-138`): sets an asyncio timer (`loop.call_later`) that triggers `process_data()`.
    - `CURLMOPT_SOCKETFUNCTION` (`aio.py:141-169`): registers socket file descriptors with asyncio loop readers (`loop.add_reader`) and writers (`loop.add_writer`).
  - Requests are queued onto the multi-handle via `acurl.add_handle(curl)` (`session.py:1511`), awaiting completion without blocking the main event loop.

### 4.2 Windows Proactor Loop Compatibility Trap
- On Windows systems, Python's default `asyncio.ProactorEventLoop` does not implement `add_reader()` and `add_writer()`.
- `curl-cffi` addresses this transparently in `curl_cffi/aio.py:15-64`:
  - When running under `ProactorEventLoop`, `get_selector()` detects the incompatibility and wraps the loop with `AddThreadSelectorEventLoop` (`curl_cffi/_asyncio_selector.py`).
  - It emits `PROACTOR_WARNING` (`aio.py:18-23`), advising:
    ```python
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    ```
- When using `AsyncSession` on Windows, setting `WindowsSelectorEventLoopPolicy` avoids auxiliary selector thread overhead.

---

## 5. Proxies & IP Isolation

### 5.1 Protocol Support & Configuration
`curl-cffi` supports standard proxy schemes: `http://`, `https://`, `socks5://`, and `socks5h://` (`curl_cffi/requests/utils.py:848-886`).
- **Specification Formats**:
  ```python
  # Per-session:
  s = Session(proxy="http://user:pass@127.0.0.1:8080")
  # Or via mapping:
  s = Session(proxies={"http": "http://127.0.0.1:8080", "https": "socks5h://127.0.0.1:1080"})
  ```
- **SOCKS5 vs SOCKS5H**:
  - `socks5://`: DNS queries resolved by the local client.
  - `socks5h://`: DNS queries passed through the proxy for remote resolution (prevents DNS leakage).

### 5.2 Anti-Leak Isolation & Tunneling Flags
- **Credential & Connection Isolation**:
  - In `curl_cffi/requests/utils.py:852`, whenever a proxy is configured, `curl-cffi` sets:
    ```python
    c.setopt(CurlOpt.PROXY_CREDENTIAL_NO_REUSE, 1)
    ```
  - **Security Benefit**: Ensures new TCP/TLS connections are established when proxy credentials change and forces TLS session cache segregation per proxy address so requests do not leak previous TLS session tickets or client identifiers across rotating IPs.
- **HTTP Proxy Tunneling**:
  - For HTTPS targets over HTTP proxies, `c.setopt(CurlOpt.HTTPPROXYTUNNEL, 1)` is enabled (`utils.py:879`), sending an `HTTP CONNECT` tunnel request to establish end-to-end TLS encryption with the target host.
  - Setting `https://` proxy for HTTP tunnels triggers a warning (`utils.py:870-876`) to prevent misconfigured nested TLS tunnels.

---

## 6. Cookies & Bot-Wall Warmup Patterns

### 6.1 CookieJar Architecture & Synchronization
- **Cookie Container**: `Cookies` class (`curl_cffi/requests/cookies.py:131-300`) implements `MutableMapping` backed by Python standard library `http.cookiejar.CookieJar`.
- **Conversion to Netscape Format**:
  - `CurlMorsel` (`cookies.py:26-100`) parses and dumps tab-separated Netscape cookie lines:
    ```text
    domain  subdomains  path  secure  expires  name  value
    ```
- **Transmission to libcurl**:
  - Before a transfer, `set_curl_options()` initializes the libcurl cookie engine via `c.setopt(CurlOpt.COOKIEFILE, b"")` and clears obsolete cookies via `c.setopt(CurlOpt.COOKIELIST, "ALL")` (`utils.py:771-772`).
  - Active cookies from the jar are injected via `c.setopt(CurlOpt.COOKIELIST, morsel.to_curl_format())` (`utils.py:778, 782`).
- **Two-Way Synchronization**:
  - Responses parse cookies from `Set-Cookie` headers into `response.cookies` (`session.py:393-408`).
  - Crucially, `session.py:413-414` inspects `CurlInfo.COOKIECHANGES` from libcurl to capture intermediate cookie changes across redirect chains, updating the session jar via `self._cookies.update_cookies_from_curl_changes(changes)` (`cookies.py:221-234`).

### 6.2 Bot-Wall Warmup Clearance Pattern
Antidetect mechanisms (such as DataDome, Cloudflare Turnstile, Akamai Bot Manager) reject immediate direct requests to internal API endpoints when no valid clearance cookie exists:
1. **Warmup Request**: A request is first directed to an entry URL (e.g., website root or registration page).
2. **Clearance Extraction**: Even if the warmup request returns `403 Forbidden` or presents a challenge page, the response delivers anti-bot cookies (e.g. `datadome=...`, `cf_clearance=...`).
3. **Session Persistence**: Because the `Session` updates its `Cookies` jar on every response (`session.py:414`), these clearance cookies persist automatically.
4. **Subsequent Calls**: Target endpoints inherit the clearance cookies from the same session without re-triggering the TLS/header inspection filter.

---

## 7. TLS / JA3 / HTTP/2 & HTTP/3 Fingerprinting

### 7.1 JA3 Fingerprinting
`set_ja3_options()` (`curl_cffi/requests/utils.py:256-297`) parses standard JA3 fingerprint strings:
```text
SSLVersion,Ciphers,Extensions,EllipticCurves,EllipticCurvePointFormats
```
- **`SSLVersion`**: Mapped using `TLS_VERSION_MAP` (`impersonate.py:216-220`), e.g., `0x0303` (771) -> `CurlSslVersion.TLSv1_2`.
- **`Ciphers`**: Mapped from decimal cipher IDs to BoringSSL strings via `TLS_CIPHER_NAME_MAP` (`impersonate.py:227-265`) and applied via `CurlOpt.SSL_CIPHER_LIST` (`utils.py:274`).
- **`Extensions`**: Strips padding extension `21` (`utils.py:276-284`) and sets explicit extension ordering via `CurlOpt.TLS_EXTENSION_ORDER` (`utils.py:286`).
- **`EllipticCurves`**: Mapped via `TLS_EC_CURVES_MAP` (`impersonate.py:378-389`), e.g. `29` -> `X25519`, `4588` -> `X25519MLKEM768`, applied via `CurlOpt.SSL_EC_CURVES` (`utils.py:294`).

### 7.2 Akamai HTTP/2 Fingerprinting
`set_akamai_options()` (`curl_cffi/requests/utils.py:299-320`) enforces HTTP/2 fingerprint matching:
```text
SETTINGS|WINDOW_UPDATE|STREAMS|HEADER_ORDER
```
- `CurlOpt.HTTP_VERSION` -> `CurlHttpVersion.V2_0` (`utils.py:308`).
- `CurlOpt.HTTP2_SETTINGS` (`utils.py:310`).
- `CurlOpt.HTTP2_WINDOW_UPDATE` (`utils.py:311`).
- `CurlOpt.HTTP2_STREAMS` (`utils.py:314`).
- `CurlOpt.HTTP2_PSEUDO_HEADERS_ORDER` (`utils.py:318`): accepts e.g. `"m,a,s,p"` and formats to `"masp"` (order of `:method`, `:authority`, `:scheme`, `:path`).

### 7.3 Perk HTTP/3 & QUIC Fingerprinting
`set_perk_options()` (`curl_cffi/requests/utils.py:321-332`):
- `CurlOpt.HTTP3_SETTINGS` (`utils.py:324`).
- `CurlOpt.HTTP3_PSEUDO_HEADERS_ORDER` (`utils.py:328`).
- `CurlOpt.QUIC_TRANSPORT_PARAMETERS` (`utils.py:330`).

### 7.4 Extra Fingerprints & Modern TLS Options
Configured via `ExtraFingerprints` (`impersonate.py:177-195`) and `set_extra_fp()` (`utils.py:333-365`):
- **GREASE**: `CurlOpt.TLS_GREASE` (emulates Chrome/Safari random extension/cipher injection).
- **ALPS**: `CurlOpt.SSL_ENABLE_ALPS` & `CurlOpt.TLS_USE_NEW_ALPS_CODEPOINT` (Application-Layer Protocol Settings).
- **Extension Permutation**: `CurlOpt.SSL_PERMUTE_EXTENSIONS`.
- **Cert Compression**: `CurlOpt.SSL_CERT_COMPRESSION` (`"zlib"` or `"brotli"`).
- **Cookie Splitting**: `CurlOpt.SPLIT_COOKIES`.
- **Form Boundary**: `CurlOpt.FORM_BOUNDARY`.

---

## 8. Exception Hierarchy

Exception definitions live in `curl_cffi/requests/exceptions.py:13-156` and `curl_cffi/curl.py:52-60`:

```text
Exception
└── CurlError (curl.py:52) [stores .code: CurlECode]
    └── RequestException (exceptions.py:13) [stores .response]
        ├── CookieConflict (exceptions.py:28)
        ├── SessionClosed (exceptions.py:32)
        ├── ImpersonateError (exceptions.py:36)
        ├── UnrewindableBodyError (exceptions.py:149)
        ├── InterfaceError (exceptions.py:153)
        ├── TooManyRedirects (exceptions.py:102)
        ├── InvalidURL (exceptions.py:115)
        │   └── InvalidProxyURL (exceptions.py:125)
        ├── InvalidSchema (exceptions.py:111)
        ├── Timeout (exceptions.py:78)
        ├── ProxyError (exceptions.py:66)
        ├── HTTPError (exceptions.py:50)
        │   └── IncompleteRead (exceptions.py:54)
        └── ConnectionError (exceptions.py:58)
            ├── DNSError (exceptions.py:62)
            └── SSLError (exceptions.py:70)
                └── CertificateVerifyError (exceptions.py:74)
```

### Error Code Mapping (`code2error`)
The mapping table `CODE2ERROR` (`exceptions.py:176-220`) translates raw `CurlECode` return codes to high-level exception classes:
- `CurlECode.OPERATION_TIMEDOUT` -> `Timeout`
- `CurlECode.COULDNT_RESOLVE_PROXY`, `CurlECode.PROXY` -> `ProxyError`
- `CurlECode.COULDNT_RESOLVE_HOST` -> `DNSError`
- `CurlECode.COULDNT_CONNECT`, `CurlECode.QUIC_CONNECT_ERROR`, `CurlECode.GOT_NOTHING` -> `ConnectionError`
- `CurlECode.SSL_CONNECT_ERROR`, `CurlECode.SSL_CIPHER`, `CurlECode.SSL_CACERT_BADFILE` -> `SSLError`
- `CurlECode.PEER_FAILED_VERIFICATION` -> `CertificateVerifyError`
- `CurlECode.TOO_MANY_REDIRECTS` -> `TooManyRedirects`
- Specialized resolution helper (`exceptions.py:224-228`):
  ```python
  def code2error(code: Union[CurlECode, Literal[0]], msg: str):
      if code == CurlECode.RECV_ERROR and "CONNECT" in msg:
          return ProxyError
      return CODE2ERROR.get(code, RequestException)
  ```

---

## 9. How `user-scanner` Impersonate Module Uses `curl-cffi`

Source file: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/user_scanner/core/impersonate.py`

### 9.1 Global State & Session Caching
`user_scanner.core.impersonate` implements a thread-safe, warmed session cache to reuse TCP connections and clearance cookies across scanning modules:
```python
# impersonate.py:10-16
DEFAULT_IMPERSONATE = "chrome"
DEFAULT_TIMEOUT = 15.0

_sessions: dict[tuple, cffi.Session] = {}
_key_locks: dict[tuple, threading.Lock] = {}
_warmed: set[tuple] = set()
_lock = threading.Lock()
```

### 9.2 `_get_warm_session` Implementation (`impersonate.py:96-126`)
```python
def _get_warm_session(
    impersonate: str, proxy: Optional[str], warmup_url: Optional[str]
) -> cffi.Session:
    key = (impersonate, proxy)
    warmup_key = (*key, warmup_url)
    with _lock:
        session = _sessions.get(key)
        if session is None:
            session = cffi.Session(
                impersonate=impersonate,  # type: ignore[arg-type]
                proxies={"http": proxy, "https": proxy} if proxy else None,
            )
            _sessions[key] = session
            _key_locks[key] = threading.Lock()
            
        key_lock = _key_locks.get(key)
        if key_lock is None:
            key_lock = threading.Lock()
            _key_locks[key] = key_lock

    if warmup_url and warmup_key not in _warmed:
        with key_lock:
            if warmup_key not in _warmed:
                # A blocked (403) warm-up still returns normally and sets the cookie;
                # only a network error leaves the session unwarmed for a later retry.
                session.get(warmup_url, timeout=_timeout())
                _warmed.add(warmup_key)

    return session
```
- **Session Keying**: Sessions are partitioned by `(impersonate, proxy)`.
- **Double-Checked Warmup**: Per-key locks (`_key_locks`) guarantee that concurrent scanner threads targeting the same platform only run the warmup request once.
- **Clearance Ingestion**: `session.get(warmup_url)` populates the session's cookie jar even if the endpoint responds with `403 Forbidden` (`impersonate.py:121-122`).

### 9.3 `impersonate_request` (`impersonate.py:44-60`)
```python
def impersonate_request(
    url: str,
    method: Literal["GET", "POST"] = "GET",
    warmup_url: Optional[str] = None,
    impersonate: str = DEFAULT_IMPERSONATE,
    **kwargs,
) -> cffi.Response:
    session = _get_warm_session(impersonate, get_proxy(), warmup_url)
    kwargs.setdefault("timeout", _timeout())
    kwargs.setdefault("allow_redirects", False)
    return session.request(method, url, **kwargs)
```
- Sets `allow_redirects=False` by default (enables OSINT status inspection of HTTP 301/302 redirects).
- Retrieves timeout via `_timeout()` (`impersonate.py:129-133`), respecting CLI `--timeout` flag (`get_global_timeout()`).

### 9.4 `impersonate_validate` (`impersonate.py:19-42`)
Higher-level wrapper matching the scanner validation protocol:
```python
def impersonate_validate(
    url: str,
    func: Callable[[cffi.Response], Result],
    warmup_url: Optional[str] = None,
    impersonate: str = DEFAULT_IMPERSONATE,
    show_url: Optional[str] = None,
    **kwargs,
) -> Result:
    display_url = show_url or url
    try:
        response = impersonate_request(
            url, warmup_url=warmup_url, impersonate=impersonate, **kwargs
        )
        return func(response).update(url=display_url)
    except Exception as e:
        return Result.error(e, url=display_url)
```

### 9.5 `impersonate_request_async` & Email Service Integration
- In `user_scanner/core/impersonate.py:75-93`:
  ```python
  async def impersonate_request_async(
      url: str,
      method: Literal["GET", "POST"] = "GET",
      warmup_url: Optional[str] = None,
      impersonate: str = DEFAULT_IMPERSONATE,
      **kwargs,
  ) -> cffi.Response:
      return await asyncio.to_thread(
          impersonate_request,
          url,
          method,
          warmup_url=warmup_url,
          impersonate=impersonate,
          **kwargs,
      )
  ```
  Runs `impersonate_request` inside a worker thread via `asyncio.to_thread`, enabling async email validation modules to share the synchronous session cache.
- In `Sherlock/src/services/email_service.py:80-115`:
  Sherlock wraps `impersonate_request_async` using a `contextvars.ContextVar` (`_SCAN_FINGERPRINT`) to dynamically alter the browser fingerprint per scan without altering validator module imports.

---

## 10. Android Wheel Availability & Cross-Platform Packaging

### 10.1 CPython 3.14 & Android Wheels on PyPI
`Sherlock-V2` requires Python `>=3.14` (`pyproject.toml:6`). For CPython 3.14 on Android, `curl-cffi 0.16.3` publishes precompiled wheels directly to PyPI:
- **PyPI Release**: `curl_cffi-0.16.3-cp314-cp314-android_24_arm64_v8a.whl`
  - Uploaded: 2026-09-02
  - Target ABI: `arm64_v8a` (64-bit ARM physical mobile devices)
  - Android API Level: `android_24` (Android 7.0 Nougat minimum API level floor)
  - Hash: `sha256:0c8b70191dc88ea770a5c39d7e213bff1606e248c13566777e6527f0d8cf96ec`
  - File size: ~8.6 MB (bundles precompiled BoringSSL and libcurl `.so` shared libraries)

### 10.2 Flet Forge Wheel Index (`pypi.flet.dev`)
For mobile app bundling via Flet / Serious Python (which packages Python runtimes into APKs/IPAs), the Flet Forge repository (`https://pypi.flet.dev/curl-cffi/`) provides both production and emulator wheels:
1. **`android_24_arm64_v8a`**: Physical Android devices.
2. **`android_24_x86_64`**: Android Studio emulators and x86_64 Chromebooks running Android runtime.
   - Example builds:
     - `curl_cffi-0.16.2-1-cp314-cp314-android_24_arm64_v8a.whl`
     - `curl_cffi-0.16.2-1-cp314-cp314-android_24_x86_64.whl`
     - `curl_cffi-0.16.2-1-cp313-cp313-android_24_arm64_v8a.whl`
     - `curl_cffi-0.16.2-1-cp313-cp313-android_24_x86_64.whl`
3. **iOS Support**:
   - `ios_13_0_arm64_iphoneos.whl` (physical iPhones/iPads)
   - `ios_13_0_arm64_iphonesimulator.whl` (Apple Silicon Mac simulator)
   - `ios_13_0_x86_64_iphonesimulator.whl` (Intel Mac simulator)

### 10.3 APK Build Implications
- **No On-Device C Compilation**: Because prebuilt `android_24_arm64_v8a` wheels exist on PyPI and both `arm64_v8a` + `x86_64` exist on `pypi.flet.dev`, building Sherlock-V2 mobile APKs does not require an Android NDK compilation toolchain for `curl-cffi`.
- **16 KiB Page Alignment**: Prebuilt shared libraries bundled inside the Android wheels comply with Android 15's 16 KiB ELF memory page alignment requirements.
