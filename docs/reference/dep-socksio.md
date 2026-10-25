# Dependency Reference: socksio (1.0.0)

This document provides an in-depth reference for `socksio 1.0.0`, its SOCKS protocol capabilities, how `httpx` and `httpcore` leverage it for SOCKS5 proxy support, how `user-scanner` integrates it within Sherlock-V2, and the architectural implications for Flet mobile deployments (iOS and Android).

---

## 1. Package Overview & Version

| Attribute | Details | File / Reference |
|---|---|---|
| **Package Name** | `socksio` | `socksio-1.0.0.dist-info/METADATA:2` |
| **Installed Version** | `1.0.0` | `socksio/__init__.py:25` |
| **Author** | Seth Michael Larson (`sethmichaellarson@gmail.com`) | `socksio-1.0.0.dist-info/METADATA:7-8` |
| **License** | MIT License | `socksio-1.0.0.dist-info/METADATA:11` |
| **Package Type** | Pure Python wheel (`py3-none-any`, `Root-Is-Purelib: true`) | `socksio-1.0.0.dist-info/WHEEL:3-4` |
| **Python Requirement** | `>=3.6` | `socksio-1.0.0.dist-info/METADATA:9` |
| **Runtime Dependencies** | None (0 external dependencies; relies solely on Python standard library) | `socksio-1.0.0.dist-info/METADATA` |
| **Filesystem Location** | `Sherlock-V2/.venv/Lib/site-packages/socksio/` | Local environment |

### 1.1 Architectural Model: Sans-I/O
`socksio` is implemented following the **sans-I/O** architectural pattern (similar to `h11` for HTTP/1.1 and `hyper-h2` for HTTP/2). The library does not create, read from, or write to network sockets. Instead, it encapsulates:
1. SOCKS protocol state machines.
2. Serialization of request objects into protocol bytes (`conn.data_to_send()`).
3. Parsing of incoming byte streams into typed reply objects (`conn.receive_data(data)`).

Network I/O is completely delegated to calling frameworks (such as `httpcore`, `httpx`, `asyncio`, or standard `socket`).

---

## 2. Protocol Capabilities: SOCKS4, SOCKS4A, and SOCKS5

`socksio` provides client-side protocol support for SOCKS4, SOCKS4A, and SOCKS5.

### 2.1 SOCKS4 & SOCKS4A (`socksio/socks4.py`)

- **Commands Supported (`SOCKS4Command`)** (`socksio/socks4.py:23-27`):
  - `CONNECT = b"\x01"`: Establish outgoing TCP stream connection.
  - `BIND = b"\x02"`: Passive port binding for inbound connections.
- **Reply Codes (`SOCKS4ReplyCode`)** (`socksio/socks4.py:14-20`):
  - `REQUEST_GRANTED = b"\x5A"` (90)
  - `REQUEST_REJECTED_OR_FAILED = b"\x5B"` (91)
  - `CONNECTION_FAILED = b"\x5C"` (92)
  - `AUTHENTICATION_FAILED = b"\x5D"` (93)
- **SOCKS4 vs SOCKS4A Framing**:
  - `SOCKS4Request` (`socksio/socks4.py:30-102`): Accepts only IPv4 addresses. Attempting to pass domain names or IPv6 addresses raises `SOCKSError("IPv6 addresses and domain names are not supported by SOCKS4")` (`socksio/socks4.py:69-72`). Requires a non-empty `user_id` (`socksio/socks4.py:89-90`).
  - `SOCKS4ARequest` (`socksio/socks4.py:104-170`): Extension allowing domain names. It sets the destination IP to an invalid IPv4 address `0.0.0.x` (`b"\x00\x00\x00\xFF"`, `socksio/socks4.py:164`) and appends the domain name string terminated by null bytes (`socksio/socks4.py:167-168`), allowing proxy-side DNS resolution.
- **Connection Handler (`SOCKS4Connection`)** (`socksio/socks4.py:209-253`):
  - Manages outgoing byte buffer `_data_to_send` and incoming buffer `_received_data`.
  - Calling `conn.send(request)` appends serialized bytes; `conn.data_to_send()` returns and flushes the buffer (`socksio/socks4.py:246-253`).
  - `conn.receive_data(data)` unpacks into an 8-byte `SOCKS4Reply` (`socksio/socks4.py:187-207, 234-244`).

### 2.2 SOCKS5 (`socksio/socks5.py`)

- **Commands Supported (`SOCKS5Command`)** (`socksio/socks5.py:24-29`):
  - `CONNECT = b"\x01"`: TCP stream connection.
  - `BIND = b"\x02"`: Inbound port binding.
  - `UDP_ASSOCIATE = b"\x03"`: Defined in command enum; datagram framing (`SOCKS5Datagram`) currently raises `NotImplementedError` (`socksio/socks5.py:285, 288`).
- **Address Types (`SOCKS5AType`)** (`socksio/socks5.py:32-47`):
  - `IPV4_ADDRESS = b"\x01"` (4-byte packed binary)
  - `DOMAIN_NAME = b"\x03"` (1-byte length prefix followed by ASCII domain bytes)
  - `IPV6_ADDRESS = b"\x04"` (16-byte packed binary)
- **Authentication Methods (`SOCKS5AuthMethod`)** (`socksio/socks5.py:15-21`):
  - `NO_AUTH_REQUIRED = b"\x00"`
  - `GSSAPI = b"\x01"` (enum defined, but handshake unhandled)
  - `USERNAME_PASSWORD = b"\x02"` (RFC 1929 subnegotiation implemented)
  - `NO_ACCEPTABLE_METHODS = b"\xFF"`
- **Reply Codes (`SOCKS5ReplyCode`)** (`socksio/socks5.py:50-62`):
  - `SUCCEEDED = b"\x00"`
  - `GENERAL_SERVER_FAILURE = b"\x01"`
  - `CONNECTION_NOT_ALLOWED_BY_RULESET = b"\x02"`
  - `NETWORK_UNREACHABLE = b"\x03"`
  - `HOST_UNREACHABLE = b"\x04"`
  - `CONNECTION_REFUSED = b"\x05"`
  - `TTL_EXPIRED = b"\x06"`
  - `COMMAND_NOT_SUPPORTED = b"\x07"`
  - `ADDRESS_TYPE_NOT_SUPPORTED = b"\x08"`

### 2.3 SOCKS5 State Machine (`SOCKS5State`)
The state transitions are enforced inside `SOCKS5Connection` (`socksio/socks5.py:291-389`):
1. `CLIENT_AUTH_REQUIRED (1)`: Initial state. Client sends `SOCKS5AuthMethodsRequest`.
2. `SERVER_AUTH_REPLY (2)`: Proxy server responds with selected `SOCKS5AuthMethod`.
   - If `NO_AUTH_REQUIRED`, transitions to `CLIENT_AUTHENTICATED (3)`.
   - If `USERNAME_PASSWORD`, transitions to `CLIENT_WAITING_FOR_USERNAME_PASSWORD (5)`.
3. `SERVER_VERIFY_USERNAME_PASSWORD (6)`: Client sends `SOCKS5UsernamePasswordRequest`. Proxy replies with `SOCKS5UsernamePasswordReply`.
   - If `reply.success` is `True`, transitions to `CLIENT_AUTHENTICATED (3)`.
   - If `reply.success` is `False`, transitions to `MUST_CLOSE (7)`.
4. `CLIENT_AUTHENTICATED (3)`: Client sends `SOCKS5CommandRequest` (e.g. `CONNECT`).
5. `TUNNEL_READY (4)`: Proxy responds with `SOCKS5ReplyCode.SUCCEEDED`. The TCP stream is now transparently bridged to destination.
6. `MUST_CLOSE (7)`: Connection error or rejected authentication.

---

## 3. How httpx & httpcore Use socksio for `socks5://` Proxies

### 3.1 Dependency Declaration
- `httpx` marks SOCKS support as an optional extra: `Requires-Dist: socksio==1.*; extra == 'socks'` (`httpx-0.28.1.dist-info/METADATA:41`).
- `httpcore` marks SOCKS support as an optional extra: `Requires-Dist: socksio==1.*; extra == 'socks'` (`httpcore-1.0.9.dist-info/METADATA:34`).
- `user-scanner` directly requires `socksio>=1.0,<2` (`user_scanner-1.5.2.3.dist-info/METADATA:11`), ensuring `socksio` is always present in the environment even when `httpx` is installed without the `[socks]` extra.

### 3.2 Transport Scheme Routing in `httpx`
In `httpx/_transports/default.py`:
- **Synchronous Transport (`HTTPTransport`)** (`httpx/_transports/default.py:187-210`):
  ```python
  elif proxy.url.scheme in ("socks5", "socks5h"):
      try:
          import socksio  # noqa
      except ImportError:
          raise ImportError(
              "Using SOCKS proxy, but the 'socksio' package is not installed. "
              "Make sure to install httpx using `pip install httpx[socks]`."
          ) from None

      self._pool = httpcore.SOCKSProxy(
          proxy_url=httpcore.URL(...),
          proxy_auth=proxy.raw_auth,
          ssl_context=ssl_context,
          ...
      )
  ```
- **Asynchronous Transport (`AsyncHTTPTransport`)** (`httpx/_transports/default.py:331-354`):
  Identical check instantiating `httpcore.AsyncSOCKSProxy(...)`.
- **Protocol Limitation**: `httpx` explicitly restricts proxy schemes to `http`, `https`, `socks5`, and `socks5h` (`httpx/_transports/default.py:212-215, 356-359`). SOCKS4 / SOCKS4A are not supported by `httpx` despite `socksio` offering SOCKS4 modules.

### 3.3 SOCKS5 Handshake Implementation in `httpcore`
In `httpcore/_sync/socks_proxy.py` (and mirrored in `httpcore/_async/socks_proxy.py`):
1. **Fallback guard** (`httpcore/_sync/__init__.py:19-28`): If `socksio` is absent, instantiating `httpcore.SOCKSProxy` raises `RuntimeError("Attempted to use SOCKS support, but the socksio package is not installed...")`.
2. **Handshake Sequence (`_init_socks5_connection`)** (`httpcore/_sync/socks_proxy.py:42-103`):
   - **Step 1: Auth Negotiation** (`lines 49-60`): Instantiates `conn = socksio.socks5.SOCKS5Connection()`. Sends `SOCKS5AuthMethodsRequest([auth_method])` where auth method is `NO_AUTH_REQUIRED` or `USERNAME_PASSWORD`. Outgoing bytes are retrieved via `conn.data_to_send()` and sent over `stream.write()`.
   - **Step 2: Method Verification** (`lines 62-70`): Reads bytes from `stream.read(max_bytes=4096)`, parses via `conn.receive_data()`, and asserts that the response is `SOCKS5AuthReply`.
   - **Step 3: User/Pass Authentication** (`lines 72-86`): If `USERNAME_PASSWORD` was negotiated, sends `SOCKS5UsernamePasswordRequest(username, password)` and asserts `SOCKS5UsernamePasswordReply.success`.
   - **Step 4: Connect Command** (`lines 88-94`):
     ```python
     conn.send(
         socksio.socks5.SOCKS5CommandRequest.from_address(
             socksio.socks5.SOCKS5Command.CONNECT, (host, port)
         )
     )
     ```
   - **Step 5: Connect Verification** (`lines 96-103`): Reads proxy response and asserts `response.reply_code == socksio.socks5.SOCKS5ReplyCode.SUCCEEDED`.
3. **Address Resolution & DNS Leaks** (`socksio/utils.py:34-45`):
   `socksio.utils.encode_address` tests for IPv6 (`socket.inet_pton(AF_INET6)`), then IPv4 (`socket.inet_pton(AF_INET)`). If both fail (meaning a domain name was provided), it returns `AddressType.DN, addr.encode()`. When `SOCKS5CommandRequest` packs the address (`socksio/socks5.py:224-226`), it uses `SOCKS5AType.DOMAIN_NAME` with length prefix. Therefore, domain name resolution is executed remotely on the SOCKS5 proxy server, avoiding local DNS leaks.
4. **TLS Layering over Tunnel** (`httpcore/_sync/socks_proxy.py:248-268`):
   When destination scheme is `https`, `httpcore` wraps the established TCP tunnel using `stream.start_tls(ssl_context=..., server_hostname=sni_hostname)`. ALPN is negotiated for `http/1.1` or `h2`.

---

## 4. How user-scanner Leverages socksio & Proxy Architecture

Within Sherlock-V2, the underlying scanning engine is `user-scanner` (`user_scanner-1.5.2.3`). Its proxy subsystem directly integrates with `socksio` through `httpx`.

### 4.1 ProxyManager Architecture (`user_scanner/core/helpers.py:608-674`)
- **Initialization**: Can be loaded from a list of strings (`_load_proxies_from_list`, line 622) or from a file path (`_load_proxies`, line 634).
- **Scheme Preservation**:
  ```python
  # Keep explicit schemes (http://, socks5://, socks5h://, etc.).
  # Only prepend http:// when no scheme is provided.
  if "://" not in line:
      line = "http://" + line
  self.proxies.append(line)
  ```
  Lines 627-629 and 642-644 explicitly preserve SOCKS schemes (`socks5://user:pass@host:port`, `socks5h://...`).
- **Thread Safety**: Uses `self.lock = threading.Lock()` (`line 614`) during round-robin index updates:
  ```python
  with self.lock:
      proxy = self.proxies[self.current_index]
      self.current_index = (self.current_index + 1) % len(self.proxies)
      return proxy
  ```
- **Global Singletons**: Managed via `set_proxy_manager()`, `get_proxy()`, and `get_proxy_count()` (`lines 680-700`).

### 4.2 Proxy Validation Workflow (`--validate-proxies`)
- **CLI Trigger** (`user_scanner/__main__.py:401-424`):
  When the CLI runs with `--validate-proxies` and `--proxy-file`:
  1. Loads all candidate proxies into a temporary `ProxyManager(args.proxy_file)`.
  2. Executes `validate_proxies(all_proxies)` (`helpers.py:603-605`).
  3. Re-initializes the global proxy manager with only the validated, functional proxies: `set_proxy_manager(proxies=working_proxies)`.
- **Validation Mechanics** (`user_scanner/core/helpers.py:577-601`):
  ```python
  async def _validate_proxy_async(proxy: str, timeout: int) -> Optional[str]:
      try:
          async with httpx.AsyncClient(proxy=proxy, timeout=timeout) as client:
              response = await client.get("http://gstatic.com/generate_204")
              if response.status_code in (200, 204):
                  return proxy
      except Exception:
          pass
      return None
  ```
  - `_validate_proxies_batch` wraps this in an `asyncio.Semaphore(max_workers)` (default 50 concurrency) with `asyncio.gather`.
  - Passing `proxy="socks5://..."` into `httpx.AsyncClient` invokes `httpcore.AsyncSOCKSProxy`, which executes the `socksio` state machine handshake against `gstatic.com:80`. If the SOCKS proxy is alive and connects successfully, the proxy is kept.

### 4.3 Proxy Consumption Across Scanning Engines
1. **Username Scanner (`user_scanner/core/orchestrator.py:270-307`)**:
   - `get_client(use_http2, proxy_val, verify)` caches persistent `httpx.Client` instances keyed by `(use_http2, proxy_val, verify)`.
   - `make_request()` automatically pulls `proxy_val = get_proxy()` if none was passed.
2. **Email Scanner (`user_scanner/core/email_orchestrator.py:23-53`)**:
   - Monkey-patches `httpx.AsyncClient.__init__` and `httpx.Client.__init__` to inject `kwargs["proxy"] = get_proxy()` dynamically.
3. **Impersonation Scanner (`user_scanner/core/impersonate.py:56, 108`)**:
   - Routes requests through `curl_cffi.Session(proxies={"http": proxy, "https": proxy})` for TLS fingerprint spoofing (bypassing bot walls like Cloudflare / DataDome).

---

## 5. Flet Mobile Implications (iOS & Android)

Sherlock-V2 incorporates `flet>=1.0.4` (`pyproject.toml:8`) as its UI framework. Deploying Sherlock-V2 or `user-scanner` to mobile platforms (via `flet build apk`, `flet build ipa`, or `serious-python`) introduces specific networking and dependency considerations.

### 5.1 Pure Python vs C-Extensions (`socksio` vs `curl_cffi`)
- **`socksio` Compatibility**: Because `socksio` is 100% pure Python with no C-extensions or external dependencies, it compiles into Python bytecode and packages seamlessly into Android APKs and iOS IPAs using `serious-python`.
- **The `curl_cffi` Problem on Mobile**: `user_scanner.core.impersonate` depends on `curl_cffi` (`curl_cffi-0.16.3`), which wraps native C libraries (libcurl + BoringSSL). `curl_cffi` does not supply prebuilt binary wheels for `aarch64-linux-android` or `aarch64-apple-ios`. In mobile builds, any scanning module relying on `impersonate_validate` will fail unless patched or excluded. In contrast, standard scanning modules using `httpx` + `httpcore` + `socksio` function without compilation barriers.

### 5.2 Mobile Network Sandboxing & Permissions
- **Android Manifest**: Requires explicit network permission:
  ```xml
  <uses-permission android:name="android.permission.INTERNET" />
  ```
- **Android Cleartext Traffic**: Android 9+ (API 28+) blocks unencrypted HTTP traffic by default (`android:usesCleartextTraffic="false"`). While HTTPS traffic tunneled over SOCKS5 is encrypted end-to-end, the initial SOCKS5 handshake to an unencrypted proxy (e.g. `127.0.0.1:1080`) is raw TCP. If testing HTTP endpoints (like `http://gstatic.com/generate_204`), Android network security configuration must permit cleartext traffic.
- **iOS App Transport Security (ATS)**: Apple ATS mandates HTTPS for system HTTP clients (`NSURLSession`). However, Python's `socket` module operates at the BSD socket layer, which bypasses ATS restrictions. Python SSL streams using standard CA bundles will still validate server certificates.

### 5.3 Background Execution & Socket Suspension
- Mobile OSs (iOS especially) aggressively suspend application execution and close background TCP sockets when an app is minimized.
- `httpcore.SOCKSProxy` maintains a connection pool with idle keepalive connections (`max_keepalive_connections`, `keepalive_expiry`). When the Flet app is paused by the OS, open SOCKS proxy tunnels will be silently dropped by the OS or the proxy server.
- Upon app resume, reused pooled connections will fail with `httpx.RemoteProtocolError` or socket reset errors unless connection pools are drained or reset during lifecycle pause/resume events.

### 5.4 Network Roaming & Connection Caching
- Mobile devices frequently transition between Wi-Fi and Cellular networks (IP address roaming).
- In `user_scanner/core/orchestrator.py:270-276`, `_clients` caches `httpx.Client` objects indefinitely. A cached client holding TCP streams to a SOCKS proxy over Wi-Fi will hang or raise timeout errors when the device switches to LTE/5G. Mobile Flet implementations must clear `_clients` when connectivity states change.

### 5.5 Privacy: Remote DNS Resolution & On-Device Tor (Orbot)
- **Preventing DNS Leaks**: On mobile cellular networks, carriers frequently inspect DNS lookups. Because `httpcore` and `socksio` utilize `SOCKS5AType.DOMAIN_NAME`, domain resolution occurs entirely on the remote proxy server, preventing DNS leaks on mobile data interfaces.
- **Local Tor Daemons (Orbot)**: On Android and iOS, privacy-focused users commonly run **Orbot** or **iCwt**, which provide a local SOCKS5 proxy on `127.0.0.1:9050`. `socksio` allows Sherlock-V2 / user-scanner to route all reconnaissance traffic through Tor on-device without requiring root, jailbreak, or system-wide VPN configurations.

---

## 6. Summary of Key Code Citations

| Functionality | Component | File Path | Line Range |
|---|---|---|---|
| SOCKS4 Command Enum | `SOCKS4Command` | `socksio/socks4.py` | 23–27 |
| SOCKS4 IPv4-only Check | `SOCKS4Request.from_address` | `socksio/socks4.py` | 68–73 |
| SOCKS4A Domain Encoding | `SOCKS4ARequest.dumps` | `socksio/socks4.py` | 159–170 |
| SOCKS5 Command Enum | `SOCKS5Command` | `socksio/socks5.py` | 24–29 |
| SOCKS5 Address Types | `SOCKS5AType` | `socksio/socks5.py` | 32–47 |
| SOCKS5 State Machine | `SOCKS5State` | `socksio/socks5.py` | 291–301 |
| SOCKS5 Handshake Engine | `SOCKS5Connection` | `socksio/socks5.py` | 306–400 |
| Domain Name Detection | `encode_address` | `socksio/utils.py` | 34–45 |
| httpx Sync SOCKS routing | `HTTPTransport.__init__` | `httpx/_transports/default.py` | 187–210 |
| httpx Async SOCKS routing | `AsyncHTTPTransport.__init__` | `httpx/_transports/default.py` | 331–354 |
| httpcore SOCKS5 Handshake | `_init_socks5_connection` | `httpcore/_sync/socks_proxy.py` | 42–103 |
| httpcore TLS Stream Upgrade | `Socks5Connection.handle_request` | `httpcore/_sync/socks_proxy.py` | 248–268 |
| ProxyManager Implementation | `ProxyManager` | `user_scanner/core/helpers.py` | 608–674 |
| Proxy Scheme Handling | `_load_proxies` | `user_scanner/core/helpers.py` | 641–646 |
| Async Proxy Probing | `_validate_proxy_async` | `user_scanner/core/helpers.py` | 577–585 |
| CLI `--validate-proxies` | `main` | `user_scanner/__main__.py` | 401–424 |
| Client Caching by Proxy | `get_client` | `user_scanner/core/orchestrator.py` | 270–276 |
| Auto-Proxy Monkey Patch | `_patched_client_init` | `user_scanner/core/email_orchestrator.py` | 23–53 |
