# Dependency Reference: httpx 0.28.1

This reference document provides an in-depth architectural and code-level study of `httpx` version `0.28.1` as installed in the `Sherlock-V2` virtual environment (`/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/httpx`).

It details the internal design of sync and async clients, protocol support (HTTP/1.1 and HTTP/2), connection pooling, proxy routing, timeouts, retries, streaming lifecycles, authentication, cookie management, redirect policies, transport customization, and integration patterns within `user-scanner`, `phonsint`, and `Sherlock-V2`. It also evaluates compatibility and execution characteristics within mobile runtimes built with Flet.

All citations reference exact file locations and line numbers in `Sherlock-V2\.venv\Lib\site-packages` or the workspace.

---

## 1. Package Identity and Version

- **Package Name**: `httpx`
- **Installed Version**: `0.28.1`
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/httpx`
- **Version Definition**:
  - `httpx\__version__.py:1-4`:
    ```python
    __title__ = "httpx"
    __description__ = "A next generation HTTP client, for Python 3."
    __version__ = "0.28.1"
    ```
- **Metadata and Dependencies** (`httpx-0.28.1.dist-info\METADATA`):
  - Requires Python `>=3.8`
  - Core runtime dependencies:
    - `httpcore==1.*` (installed: `1.0.9`)
    - `certifi` (installed: `2026.10.18`)
    - `idna` (installed: `3.20`)
    - `anyio` (installed: `4.15.1`)
  - Optional extras:
    - `httpx[http2]`: requires `h2>=3,<5` (installed: `h2 4.4.1`, `hpack 4.2.0`, `hyperframe 6.1.0`)
    - `httpx[socks]`: requires `socksio==1.*` (installed: `socksio 1.0.0`)

---

## 2. Sync and Async Clients Architecture

`httpx` provides dual synchronous and asynchronous client APIs with near-identical interfaces, rooted in a shared base class.

### 2.1 The `BaseClient` Foundation

Both `Client` and `AsyncClient` inherit from `BaseClient` (`httpx\_client.py:188-592`), which encapsulates configuration merging and request building:
- **Client State**: Tracks lifecycle via `ClientState.UNOPENED`, `ClientState.OPENED`, and `ClientState.CLOSED` (`httpx\_client.py:125-136, 221`).
- **Base URL Handling**: Enforces trailing slashes so relative request URLs join predictably (`httpx\_client.py:206, 234-237`).
- **Configuration Merging**:
  - `build_request(...)` (`httpx\_client.py:340-390`) merges client-level `headers`, `cookies`, `params`, `timeout`, and `base_url` with request-specific arguments.
  - `_merge_headers(...)` (`httpx\_client.py:424-431`) preserves case-insensitive client headers while overlaying request headers.
  - `_merge_queryparams(...)` (`httpx\_client.py:433-443`) joins client query parameters with per-request parameters.
  - `_merge_cookies(...)` (`httpx\_client.py:417-422`) resolves cookie stores.

### 2.2 Synchronous Client (`httpx.Client`)

- **Class Definition**: `httpx\_client.py:594-1304`
- **Initialization** (`httpx\_client.py:650-717`):
  - Initializes the default transport via `_init_transport` (`httpx\_client.py:718-739`), returning an instance of `HTTPTransport`.
  - Sets up environment and explicit proxy transports via `_get_proxy_map` (`httpx\_client.py:239-252`).
  - Assembles mounts mapping `URLPattern` instances to transports (`httpx\_client.py:697-717`).
- **Lifecycle & Context Management**:
  - Thread-safe reuse: `Client` can be safely shared across threads (`httpx\_client.py:598`).
  - Context manager entry (`httpx\_client.py:751-754`) returns `self` and opens the underlying `_transport.__enter__()`.
  - Context manager exit (`httpx\_client.py:756-764`) calls `self.close()` to terminate pooled sockets.
- **Dispatch Flow**:
  - `Client.request(...)` (`httpx\_client.py:766-826`) builds an `httpx.Request` and calls `Client.send(...)`.
  - `Client.send(...)` (`httpx\_client.py:880-929`) routes the request through `_send_handling_auth` (`httpx\_client.py:930-963`), which invokes `_send_handling_redirects` (`httpx\_client.py:964-999`), and finally dispatches through `_send_single_request` (`httpx\_client.py:1001-1035`).
  - If `stream=False` (default), `response.read()` is invoked immediately in `Client.send` (`httpx\_client.py:921-922`), buffering the body and releasing the stream.

### 2.3 Asynchronous Client (`httpx.AsyncClient`)

- **Class Definition**: `httpx\_client.py:1307-1755`
- **Initialization** (`httpx\_client.py:1353-1420`):
  - Initializes `_transport` using `AsyncHTTPTransport` (`httpx\_client.py:1422-1443`).
  - Configures async proxy mounts.
- **Concurrency & Coroutine Safety**:
  - Concurrency model: Can be shared across concurrent `asyncio` or `trio` tasks within the same event loop (`httpx\_client.py:1312`).
  - Async context management: `__aenter__` enters `_transport.__aenter__()` (`httpx\_client.py:1455-1458`), and `__aexit__` awaits `self.aclose()` (`httpx\_client.py:1460-1468`).
- **Dispatch Flow**:
  - `AsyncClient.request(...)` (`httpx\_client.py:1502-1540`) builds request and awaits `AsyncClient.send(...)`.
  - `AsyncClient.send(...)` (`httpx\_client.py:1594-1644`) coordinates `_send_handling_auth` (`httpx\_client.py:1645-1678`) and `_send_handling_redirects` (`httpx\_client.py:1679-1714`).
  - Calls `_send_single_request` (`httpx\_client.py:1716-1748`), invoking `await transport.handle_async_request(request)`.
  - Buffers the body via `await response.aread()` if `stream=False` (`httpx\_client.py:1636-1637`).

---

## 3. Protocol Support: HTTP/1.1 and HTTP/2

`httpx 0.28.1` provides first-class support for both HTTP/1.1 and HTTP/2.

### 3.1 HTTP/2 Detection and Negotiation
- **Flag Configuration**:
  - `Client(http2=True)` (`httpx\_client.py:650`) and `AsyncClient(http2=True)` (`httpx\_client.py:1363`).
  - Guard import (`httpx\_client.py:676-684, 1390-1397`):
    ```python
    if http2:
        try:
            import h2  # noqa
        except ImportError:
            raise ImportError(
                "Using http2=True, but the 'h2' package is not installed. "
                "Make sure to install httpx using `pip install httpx[http2]`."
            ) from None
    ```
- **ALPN Negotiation**:
  - When `http2=True`, `HTTPTransport` and `AsyncHTTPTransport` (`httpx\_transports\default.py:162, 305`) forward `http2=True` into `httpcore.ConnectionPool` or `httpcore.AsyncConnectionPool`.
  - The TLS handshake advertises ALPN protocols `["h2", "http/1.1"]`. If the remote server selects `h2`, multiplexed streams are created over the single TCP connection.
- **Installed Stack**:
  - The virtual environment contains:
    - `h2` 4.4.1 (`.venv\Lib\site-packages\h2`)
    - `hpack` 4.2.0 (`.venv\Lib\site-packages\hpack`)
    - `hyperframe` 6.1.0 (`.venv\Lib\site-packages\hyperframe`)
  - No C-extension is required; this HTTP/2 stack is 100% pure Python.

---

## 4. Proxy Architecture

### 4.1 Proxy Model (`httpx.Proxy`)
- **Class Definition**: `httpx\_config.py:201-244`
- **Supported Schemes**:
  - `http://`, `https://`, `socks5://`, `socks5h://` (`httpx\_config.py:213-214`).
- **Credential Handling**:
  - If username/password are embedded in the proxy URL (e.g. `http://user:pass@host:port`), `Proxy.__init__` strips credentials from `url` and sets `self.auth = (url.username, url.password)` (`httpx\_config.py:216-220`).
  - `raw_auth` property returns UTF-8 byte tuples for low-level HTTP Basic proxy authorization (`httpx\_config.py:227-233`).
  - `__repr__` masks the password component (`httpx\_config.py:237`).

### 4.2 Transport Routing
- **HTTP / HTTPS Proxies**:
  - In `HTTPTransport` (`httpx\_transports\default.py:168-186`), HTTP proxies instantiate `httpcore.HTTPProxy`, which sends `CONNECT` requests for HTTPS tunneling or forwards plain HTTP requests.
  - In `AsyncHTTPTransport` (`httpx\_transports\default.py:312-330`), `httpcore.AsyncHTTPProxy` is used.
- **SOCKS5 Proxies**:
  - In `HTTPTransport` (`httpx\_transports\default.py:187-210`), scheme `socks5` or `socks5h` checks for `socksio` (`httpx\_transports\default.py:189-195`) and initializes `httpcore.SOCKSProxy`.
  - In `AsyncHTTPTransport` (`httpx\_transports\default.py:331-354`), `httpcore.AsyncSOCKSProxy` is initialized.
- **Environment Proxies**:
  - When `trust_env=True` (default), `get_environment_proxies()` (`httpx\_utils.py`) extracts proxy definitions from `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and respects exclusion rules in `NO_PROXY`.

---

## 5. Timeouts

`httpx` uses an explicit 4-phase timeout model rather than a single monolithic socket timer.

### 5.1 The `Timeout` Configuration Class
- **Class Definition**: `httpx\_config.py:72-158`
- **Default Timeout**:
  - `DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)` (`httpx\_config.py:246`).
- **Timeout Breakdown**:
  1. `connect`: Maximum time in seconds to establish socket/TCP and complete TLS handshake (`httpx\_config.py:90, 101, 117`).
  2. `read`: Maximum time to wait for a socket read operation or response byte chunk (`httpx\_config.py:91, 102, 118`).
  3. `write`: Maximum time to wait for a socket write operation or request payload transmission (`httpx\_config.py:92, 103, 119`).
  4. `pool`: Maximum time to wait when acquiring an available connection from the pool (`httpx\_config.py:93, 104, 120`).
- **Flexible Construction**:
  - `Timeout(5.0)` sets all four phases to 5.0 seconds.
  - `Timeout(None)` disables all timeouts completely.
  - `Timeout(5.0, connect=10.0)` sets connect to 10.0s, other three phases to 5.0s.
  - `Timeout(None, connect=5.0)` enforces 5.0s on connect, leaving read/write/pool unconstrained.
- **Transport Delivery**:
  - Serialized via `timeout.as_dict()` (`httpx\_config.py:132-138`) into `request.extensions["timeout"]` (`httpx\_client.py:377, 591`).
  - Mapped to `httpcore` timeout exceptions in `httpx\_transports\default.py:78-82, 100-119`:
    - `httpcore.ConnectTimeout` -> `httpx.ConnectTimeout`
    - `httpcore.ReadTimeout` -> `httpx.ReadTimeout`
    - `httpcore.WriteTimeout` -> `httpx.WriteTimeout`
    - `httpcore.PoolTimeout` -> `httpx.PoolTimeout`

---

## 6. Retries

### 6.1 Low-Level Transport Retries
- `httpx` delegates connection-level retries directly to `httpcore`.
- In `HTTPTransport` (`httpx\_transports\default.py:147, 165`) and `AsyncHTTPTransport` (`httpx\_transports\default.py:291, 309`):
  - Argument `retries: int = 0` is forwarded to `httpcore.ConnectionPool(retries=retries)` and `httpcore.HTTPProxy(retries=retries)`.
  - These retries trigger exclusively on connection drop/reset errors when attempting to reuse a cached connection from the pool.
- **Critical Architectural Warning in Transport/Proxy Wiring**:
  - As identified in `Sherlock/src/services/http_client.py:55-57`:
    ```python
    # NOTE: do NOT wire as transport=+proxy= combo — when transport= is
    # given, httpx builds proxy mounts internally WITHOUT retries, so the
    # proxy leg would silently lose retry behavior. Both legs explicit.
    ```
  - When `Client(transport=custom_transport, proxy=...)` is constructed, `_init_proxy_transport` (`httpx\_client.py:700-708, 740-750`) creates the proxy transport using default parameters (`retries=0`). To apply retries to proxied requests, developers must explicitly pass `mounts={"all://": AsyncHTTPTransport(retries=retries, proxy=proxy, ...)}`.

### 6.2 Application-Level Retries
- `httpx` does not silently retry HTTP status codes (e.g. 500, 502, 503, 504) or POST request idempotency violations at the client layer.
- Application code (such as `user_scanner.core.orchestrator.make_request`, lines 309-316) layers explicit retry logic around `client.request()` for targeted exceptions like `httpx.ConnectTimeout` and `httpx.ReadTimeout`.

---

## 7. Streaming Requests and Responses

### 7.1 Response Streaming Lifecycles
- **Method Signatures**:
  - Sync: `Client.stream(method, url, ...)` (`httpx\_client.py:828-878`)
  - Async: `AsyncClient.stream(method, url, ...)` (`httpx\_client.py:1543-1593`)
- **Context Manager Guarantee**:
  - `Client.stream` and `AsyncClient.stream` yield an unbuffered `Response` where `response.stream` is active.
  - In `finally` blocks, `response.close()` (`httpx\_client.py:877`) or `await response.aclose()` (`httpx\_client.py:1592`) is invoked, preventing connection leaks even when exceptions occur inside the stream block.

### 7.2 Byte and Text Iteration APIs
- `httpx\_models.py:884-960` (sync) and `httpx\_models.py:982-1064` (async):
  - `iter_bytes(chunk_size=None)` / `aiter_bytes(chunk_size=None)`:
    - Iterates over decoded response bytes. Automatically applies decompressors: gzip, deflate, brotli, zstd (`httpx\_decoders.py`).
  - `iter_text(chunk_size=None)` / `aiter_text(chunk_size=None)`:
    - Iterates over decoded unicode string chunks via `TextDecoder` based on detected or explicit `response.encoding`.
  - `iter_lines()` / `aiter_lines()`:
    - Line-by-line decoding via `LineDecoder`, splitting on universal newlines (`\r\n`, `\n`, `\r`).
  - `iter_raw(chunk_size=None)` / `aiter_raw(chunk_size=None)`:
    - Bypasses all decompression decoders and yields raw, encoded network bytes straight from the socket stream.
- **Safety Flags**:
  - `response.is_stream_consumed` (`httpx\_models.py:939, 1043`) prevents double-reading, raising `StreamConsumed`.
  - `response.is_closed` (`httpx\_models.py:941, 1045`) raises `StreamClosed` if iteration is attempted on a closed connection.

---

## 8. Authentication Framework

### 8.1 The Generator-Based `Auth` Base Class
- **Class Definition**: `httpx\_auth.py:22-112`
- **Protocol**:
  - `auth_flow(request: Request) -> Generator[Request, Response, None]` (`httpx\_auth.py:38-60`).
  - To dispatch a request, the flow yields it: `response = yield request`.
  - The client transmits the request, receives the response, and sends it back into the generator via `auth_flow.send(response)`.
  - The generator inspects `response` (e.g. checks for 401 Unauthorized), modifies or constructs a subsequent request (e.g. attaching updated tokens or challenge hashes), and yields the new request.
  - The flow completes with a `return` or `StopIteration`.
- **Sync & Async Flow Handlers**:
  - `sync_auth_flow` (`httpx\_auth.py:62-86`) and `async_auth_flow` (`httpx\_auth.py:87-111`) handle request and response body caching if `requires_request_body=True` or `requires_response_body=True`.
  - Executed inside `_send_handling_auth` in `httpx\_client.py:930-963` (sync) and `httpx\_client.py:1645-1678` (async).

### 8.2 Built-in Auth Implementations
1. `BasicAuth(username, password)` (`httpx\_auth.py:126-144`):
   - Computes base64 encoded credentials and sets header `Authorization: Basic <token>`.
2. `FunctionAuth(func)` (`httpx\_auth.py:113-124`):
   - Wraps any single-argument callable `func(request) -> request`.
3. `NetRCAuth(file=None)` (`httpx\_auth.py:145-174`):
   - Reads user credentials from `.netrc` matching `request.url.host`.
4. `DigestAuth(username, password)` (`httpx\_auth.py:175-274`):
   - Implements RFC 7616 / RFC 2617 HTTP Digest authentication.
   - Dispatches initial unauthenticated request; upon receiving 401 with `WWW-Authenticate: Digest ...`, extracts `nonce`, `realm`, `qop`, `opaque`, computes response hash (supporting `MD5`, `SHA-256`, `SHA-512`), sets `Authorization: Digest ...`, and replays the request (`httpx\_auth.py:193-223`).

---

## 9. Cookie Handling and Persistence

### 9.1 The `Cookies` Model
- **Class Definition**: `httpx\_models.py:1079-1180`
- **Backing Store**:
  - Wraps Python's standard library `http.cookiejar.CookieJar` (`httpx\_models.py:1086-1100`).
  - Implements `typing.MutableMapping[str, str]` for dictionary-like operations (`cookies["session_id"] = "xyz"`).
- **Extraction and Injection**:
  - `extract_cookies(response)` (`httpx\_models.py:1101-1109`): parses `Set-Cookie` headers from the response and stores them according to domain, path, and expiry rules.
  - `set_cookie_header(request)` (`httpx\_models.py:1110-1116`): inspects `request.url` and attaches appropriate `Cookie: key=val; ...` headers.
- **Client Extraction Hook**:
  - At the completion of every single request in `_send_single_request` (`httpx\_client.py:1022, 1725`), `self.cookies.extract_cookies(response)` is invoked automatically.

### 9.2 Deprecation of Per-Request Cookies
- In `Client.request` (`httpx\_client.py:804-810`) and `AsyncClient.request` (`httpx\_client.py:1519-1525`):
  ```python
  if cookies is not None:
      message = (
          "Setting per-request cookies=<...> is being deprecated, because "
          "the expected behaviour on cookie persistence is ambiguous. Set "
          "cookies directly on the client instance instead."
      )
      warnings.warn(message, DeprecationWarning, stacklevel=2)
  ```
- Best practice: Configure cookies directly on `client.cookies` or pass raw `headers={"Cookie": "..."}`.

---

## 10. Redirect Handling

### 10.1 Redirection Execution and Loop Prevention
- **Redirect Configuration**:
  - Default: `follow_redirects=False` (`httpx\_client.py:197, 654, 1367`).
  - Max redirects limit: `DEFAULT_MAX_REDIRECTS = 20` (`httpx\_config.py:248`).
- **Loop Enforcement**:
  - `_send_handling_redirects` (`httpx\_client.py:970-974, 1685-1689`):
    ```python
    if len(history) > self.max_redirects:
        raise TooManyRedirects("Exceeded maximum allowed redirects.", request=request)
    ```
  - Appends each intermediate redirected response to `response.history` (`httpx\_client.py:983, 1699`).

### 10.2 Method Rewriting and RFC Compliance
- `_redirect_method` (`httpx\_client.py:494-516`):
  - Status `303 (See Other)`: Forces method to `GET` (RFC 7231 Section 6.4.4).
  - Status `302 (Found)`: Rewrites to `GET` for browser compatibility (unless original method was `HEAD`).
  - Status `301 (Moved Permanently)`: Rewrites `POST` to `GET` (browser convention).
  - Status `307 (Temporary Redirect)` and `308 (Permanent Redirect)`: Strictly preserves original method (`POST` stays `POST`).
- `_redirect_stream` (`httpx\_client.py:573-583`):
  - When method switches to `GET`, outgoing payload stream is dropped (`return None`).

### 10.3 Security and Cross-Origin Header Sanitization
- `_redirect_headers` (`httpx\_client.py:546-572`):
  - **Authorization Stripping**: When a redirect points to a different origin (`_same_origin(...)` returns `False`), the `Authorization` header is stripped immediately (`httpx\_client.py:556`) unless it is an HTTP-to-HTTPS upgrade on the same host and default port (`_is_https_redirect`, lines 62-75).
  - **Host Header Update**: Updates `Host` header to target hostname (`httpx\_client.py:559`).
  - **Body Header Cleanup**: If switching to `GET`, removes `Content-Length` and `Transfer-Encoding` (`httpx\_client.py:564-565`).
  - **Cookie Header Sanitization**: Clears raw `Cookie` header from request (`httpx\_client.py:569`), relying on the client cookie store to evaluate matching cookies for the new target.

---

## 11. Transport Customization and URL Mounting

`httpx` separates high-level HTTP protocol logic from transport mechanics through clean abstract interfaces.

### 11.1 Transport Base Classes
- `BaseTransport` (`httpx\_transports\base.py:14-63`):
  - Abstract method: `handle_request(request: Request) -> Response` (line 26).
  - Optional teardown: `close()` (line 61).
- `AsyncBaseTransport` (`httpx\_transports\base.py:65-87`):
  - Abstract method: `handle_async_request(request: Request) -> Response` (line 77).
  - Optional teardown: `aclose()` (line 85).

### 11.2 Standard and Built-in Transports
1. `HTTPTransport` / `AsyncHTTPTransport` (`httpx\_transports\default.py:135, 279`):
   - Default network transports backed by `httpcore.ConnectionPool` and `httpcore.AsyncConnectionPool`.
   - Supports `local_address`, `uds` (Unix domain sockets), `socket_options`, and connection pool limits (`Limits(max_connections=..., max_keepalive_connections=...)`).
2. `MockTransport` (`httpx\_transports\mock.py:15-44`):
   - Implements both `BaseTransport` and `AsyncBaseTransport`.
   - Accepts a callable `handler(request: Request) -> Response` to execute deterministic unit tests without network I/O.
3. `ASGITransport` (`httpx\_transports\asgi.py:63-125`):
   - Connects directly to ASGI applications (e.g. FastAPI, Starlette) in-memory without binding TCP ports.
4. `WSGITransport` (`httpx\_transports\wsgi.py:77-160`):
   - Connects directly to WSGI applications (e.g. Flask, Django) in-memory via synthetic WSGI environments.

### 11.3 URL Mount Routing
- Clients accept a `mounts` dictionary mapping URL patterns to distinct transport instances (`httpx\_client.py:652, 711-717, 1365, 1428-1433`).
- Examples:
  - Routing specific domains through a proxy while leaving standard traffic direct.
  - Mounting a mock transport on `test://` or an ASGI app on `app://`.
  - Disabling HTTP/2 on legacy domains:
    ```python
    mounts = {
        "all://": httpx.HTTPTransport(http2=True),
        "all://*legacy-site.org": httpx.HTTPTransport(http2=False),
    }
    client = httpx.Client(mounts=mounts)
    ```

---

## 12. Sherlock-V2, user-scanner, and phonsint Integration

`Sherlock-V2` depends on `user-scanner>=1.5.2.3` and `phonsint>=0.1.0` (`Sherlock-V2\pyproject.toml:10-11`). An analysis of their codebases reveals distinct networking architectures.

### 12.1 `user-scanner`: Pervasive `httpx` Foundation
`user-scanner` uses `httpx` as its primary network engine across more than 4,700 sites.

- **Connection Pool Caching** (`user_scanner\core\orchestrator.py:267-276`):
  ```python
  _clients: Dict[tuple, httpx.Client] = {}
  _clients_lock = threading.Lock()

  def get_client(use_http2: bool, proxy_val: Optional[str], verify: bool = True) -> httpx.Client:
      key = (use_http2, proxy_val, verify)
      if key not in _clients:
          with _clients_lock:
              if key not in _clients:
                  _clients[key] = httpx.Client(http2=use_http2, proxy=proxy_val, verify=verify)
      return _clients[key]
  ```
  - **Thread-safe Client Re-use**: Synchronous `httpx.Client` instances are cached by their configuration key `(use_http2, proxy_val, verify)`. This ensures that worker threads share connection pools and keepalive sockets.

- **Request Dispatcher (`make_request`)** (`user_scanner\core\orchestrator.py:279-317`):
  - Injects standard browser headers (`User-Agent`, `Accept`, `Accept-Encoding`, `Accept-Language`, `sec-fetch-dest`).
  - Reads global timeout (`get_global_timeout()`, defaulting to 5.0s).
  - Retrieves shared client from `get_client(...)`.
  - Implements targeted timeout retry catching `httpx.ConnectTimeout` and `httpx.ReadTimeout` (`lines 310-316`).
  - Forwards `method`, `follow_redirects`, and request parameters directly to `client.request(...)`.

- **Generic Validator (`generic_validate`)** (`user_scanner\core\orchestrator.py:319-335`):
  ```python
  def generic_validate(
      url: str, func: Callable[[httpx.Response], Result], **kwargs
  ) -> Result:
      display_url = kwargs.get("show_url", None)
      try:
          response = make_request(url, **kwargs)
          result = func(response)
          return result.update(url=display_url)
      except Exception as e:
          return Result.error(e, url=display_url)
  ```
  - Standardizes OSINT checks across site modules: issues request through `make_request`, hands `httpx.Response` to module-defined parser `func`, and packages result into a structured `Result` object.
  - Used in 4,789 site definitions across `user_scanner\user_scan\*`.

- **Status Validator (`status_validate`)** (`user_scanner\core\orchestrator.py:337-366`):
  - Wraps `generic_validate` to inspect `response.status_code` against lists of `available` and `taken` HTTP status codes.

- **Impersonate Alternative (`user_scanner\core\impersonate.py:19-42`)**:
  - Out of thousands of targets, exactly 113 sites in `user_scanner` use `impersonate_validate` instead of `generic_validate`.
  - These 113 sites are protected by anti-bot TLS fingerprinting (e.g. DataDome, Cloudflare) that reject standard OpenSSL TLS ClientHellos, requiring `curl_cffi` browser impersonation.

### 12.2 `phonsint`: Specialized Browser Impersonation
- In contrast to `user-scanner`, `phonsint` (`0.1.0`) targets high-security telecommunication and account recovery endpoints (e.g. `microsoft.py`, `zoho.py`, `amazon.py`, `facebook.py`, `instagram.py`).
- All module checks in `phonsint` route through `curl_cffi.requests.AsyncSession` or `impersonate_request_async` (`phonsint\core\impersonate.py:68-80`, `phonsint\modules\crm\zoho.py:34`).
- `phonsint` uses `curl_cffi` because consumer phone lookup endpoints aggressively enforce JA3/JA4 TLS fingerprint matching and HTTP/2 SETTINGS frame fingerprinting, which standard Python TLS engines do not emulate.

### 12.3 `Sherlock` GUI Client Pattern (`Sherlock\src\services\http_client.py`)
In the Sherlock Flet desktop/mobile application, `httpx` is used to create a shared, reactive, async HTTP service:
- Lines 38-85: `get_client()` constructs a pooled `httpx.AsyncClient` configured with:
  - `Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0)`
  - `Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)`
  - `http2=True`
  - Explicit proxy mounts (`mounts={"all://": proxy_transport}`) to preserve retries
- Dynamic rebuild: Automatically tears down and rebuilds the connection pool when the user alters proxy or retry settings in the GUI (`http_client.py:45-48`).
- Safe connection draining: `_drain(old)` and `_aclose(client)` (`http_client.py:88-106`) close replaced clients in a background task without blocking the UI loop.

---

## 13. Relevance to Flet Mobile (Android and iOS)

Flet packages Python applications for mobile deployment (Android APK/AAB and iOS IPA) using embedded mobile Python runtimes (e.g. `Serious Python` or `python-for-android`). The networking choice between `httpx` and C-extension libraries is critical in this environment.

### 13.1 Pure Python vs. Compiled C-Extensions
| Property | `httpx` Stack | `curl_cffi` / Native Stacks |
| :--- | :--- | :--- |
| **Code Architecture** | Pure Python (`httpx`, `httpcore`, `h11`, `h2`, `hpack`, `hyperframe`, `anyio`, `socksio`) | CFFI wrapper + compiled `libcurl` + compiled `BoringSSL`/OpenSSL |
| **Binary Artifacts** | None (pure `.py` / bytecode `.pyc` only) | Architecture-specific `.so` / `.dylib` / `.pyd` shared libraries |
| **Android Compatibility (`arm64-v8a`, `armeabi-v7a`, `x86_64`)** | **100% Works Out of the Box**. Runs in any standard Python mobile interpreter without cross-compilation. | **High Failure Rate**. Requires cross-compiling libcurl with CFFI for each mobile ABI; standard PyPI wheels fail to install or crash on load (`UnsatisfiedLinkError` / missing symbols). |
| **iOS Compatibility (`arm64`)** | **100% Works Out of the Box**. Complies with Apple dynamic loading policies. | **Severely Restricted**. Building dynamic C-extensions for iOS requires Xcode compilation frameworks; static linking required. |
| **TLS Implementation** | Python standard library `ssl` (linked to platform OpenSSL) | Bundled custom BoringSSL / libcurl binaries |
| **Package Size & Portability** | Minimal overhead, zero native `.so` footprint | Large multi-megabyte binary wheels per ABI |

### 13.2 Summary for Sherlock-V2 Mobile Architecture
1. **`httpx` is the Reliable Mobile Backbone**:
   Because `httpx`, `httpcore`, and its HTTP/2 dependencies (`h2`, `hpack`, `hyperframe`) are 100% pure Python, the 4,789 site checkers in `user-scanner` that use `make_request` and `generic_validate` work reliably on Android and iOS devices inside a Flet container.
2. **Isolation of Impersonation Modules**:
   Modules requiring `curl_cffi` (such as `phonsint` and the 113 impersonated `user-scanner` sites) must be treated as desktop-only or conditionally bypassed on mobile platforms unless dedicated pre-built mobile CFFI wheels are bundled in the mobile app package.
3. **Connection Pooling on Mobile**:
   Mobile OS environments enforce strict resource and file descriptor limits. The pooled client pattern demonstrated in `Sherlock\src\services\http_client.py`—capping connection limits (`max_connections=20`, `max_keepalive_connections=10`) and using clean async draining (`_aclose`)—prevents socket exhaustion on mobile devices.

---

## 14. Verification and File Citation Index

| Component | Repository Path | Line Citation | Description |
| :--- | :--- | :--- | :--- |
| **Version** | `Sherlock-V2\.venv\Lib\site-packages\httpx\__version__.py` | lines 1-4 | Package metadata and version string `0.28.1` |
| **BaseClient** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_client.py` | lines 188-592 | Shared configuration, request merging, and state management |
| **Client** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_client.py` | lines 594-1304 | Synchronous HTTP client and dispatch logic |
| **AsyncClient** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_client.py` | lines 1307-1755 | Asynchronous HTTP client and dispatch logic |
| **HTTP/2 Verification** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_client.py` | lines 676-684, 1390-1397 | Import checks for `h2` package |
| **HTTPTransport** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_transports\default.py` | lines 135-245 | Low-level sync transport, retries, socket options, http2 pool |
| **AsyncHTTPTransport**| `Sherlock-V2\.venv\Lib\site-packages\httpx\_transports\default.py` | lines 279-385 | Low-level async transport, retries, socket options, http2 pool |
| **Timeouts** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_config.py` | lines 72-158, 246 | `Timeout` class (connect, read, write, pool) and defaults (5.0s) |
| **Limits** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_config.py` | lines 159-200, 247 | `Limits` class (max_connections=100, max_keepalive_connections=20) |
| **Proxies** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_config.py` | lines 201-244 | `Proxy` URL parsing, credential separation, and scheme checks |
| **Auth Base & Flows**| `Sherlock-V2\.venv\Lib\site-packages\httpx\_auth.py` | lines 22-112 | Generator-based `Auth` class (`auth_flow`, `sync_auth_flow`, `async_auth_flow`) |
| **BasicAuth** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_auth.py` | lines 126-144 | HTTP Basic authentication header generation |
| **DigestAuth** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_auth.py` | lines 175-274 | RFC 7616/2617 Digest challenge parsing and re-dispatch |
| **Cookies** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_models.py` | lines 1079-1180 | MutableMapping cookiejar wrapper |
| **Streaming Sync** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_models.py` | lines 884-960 | `iter_bytes`, `iter_text`, `iter_lines`, `iter_raw` |
| **Streaming Async** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_models.py` | lines 982-1064 | `aiter_bytes`, `aiter_text`, `aiter_lines`, `aiter_raw` |
| **Redirect Logic** | `Sherlock-V2\.venv\Lib\site-packages\httpx\_client.py` | lines 475-572 | Method rewriting, origin checks, and Authorization stripping |
| **user-scanner Pool**| `Sherlock-V2\.venv\Lib\site-packages\user_scanner\core\orchestrator.py` | lines 267-276 | Thread-safe `_clients` cache and `get_client` |
| **make_request** | `Sherlock-V2\.venv\Lib\site-packages\user_scanner\core\orchestrator.py` | lines 279-317 | Default headers, timeout injection, and retry wrapper |
| **generic_validate**| `Sherlock-V2\.venv\Lib\site-packages\user_scanner\core\orchestrator.py` | lines 319-335 | Standard validation callback execution across 4,789 sites |
| **user-scanner Impersonate** | `Sherlock-V2\.venv\Lib\site-packages\user_scanner\core\impersonate.py` | lines 19-42 | `curl_cffi` alternative for 113 bot-protected sites |
| **phonsint Impersonate** | `Sherlock-V2\.venv\Lib\site-packages\phonsint\core\impersonate.py` | lines 68-80 | Browser-impersonating requests for phone OSINT |
| **Sherlock GUI Client** | `Sherlock\src\services\http_client.py` | lines 38-85 | Flet application pooled client with dynamic proxy/retry switching |
