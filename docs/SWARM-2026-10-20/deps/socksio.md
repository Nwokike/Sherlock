# Dependency Audit: socksio 1.0.0 (Sherlock V3)

Repo root: `/home/maikel/.zcode/workspace/default/Sherlock-V3`
Venv (source of truth): `.venv\Lib\site-packages\` (Python 3.14.7, win32)

Background doc (V2-era): `docs/reference/dep-socksio.md` — largely still accurate on the
socksio/httpx/httpcore internals; the gaps are in the app layer (V3), which the V2 doc did
not audit.

---

## 1. Installed verification

### 1.1 Version and provenance

| Fact | Value | Evidence |
|---|---|---|
| Installed version | `1.0.0` | `.venv\Lib\site-packages\socksio\__init__.py:25` (`__version__ = "1.0.0"`); `socksio-1.0.0.dist-info\METADATA:3` |
| Summary | "Sans-I/O implementation of SOCKS4, SOCKS4A, and SOCKS5." | `socksio-1.0.0.dist-info\METADATA:4` |
| Packaging | Pure Python, `Tag: py3-none-any`, `Root-Is-Purelib: true` | `socksio-1.0.0.dist-info\WHEEL` |
| Runtime deps | None (stdlib only) | `socksio-1.0.0.dist-info\METADATA` (no `Requires-Dist`) |
| Why it is installed | `user-scanner` requires it **directly and unconditionally** | `user_scanner-1.5.2.3.dist-info\METADATA:11` → `Requires-Dist: socksio>=1.0,<2` |
| httpx / httpcore declare it only as an extra | `Requires-Dist: socksio==1.*; extra == 'socks'` | `httpx-0.28.1.dist-info\METADATA:40-41`; `httpcore-1.0.9.dist-info\METADATA:33-34` |

The app itself declares only `user-scanner>=1.5.2.3` (`pyproject.toml:10`) — socksio arrives
transitively, and is present in the venv regardless of whether `httpx[socks]` was installed.

### 1.2 Sans-I/O design — confirmed

`grep -rn "socket" socksio/*.py` returns **only address-encoding helpers**, never a socket
object or an I/O call:

- `socksio/utils.py:4` — `import socket`
- `socksio/utils.py:39,42` — `socket.inet_pton(...)` (IPv6 / IPv4 literal detection)
- `socksio/utils.py:51,53` — `socket.inet_ntop(...)` (reply address rendering)

A second grep for `.connect(` / `.recv(` / `.send(` / `socket.socket(` / `select.` across
`socksio/*.py` returns **zero matches**. There is no `socket.socket()`, no `connect`, no
`recv`/`send`, no event loop.

The library is a pure state machine: callers push protocol objects in
(`conn.send(request)`) and pull bytes out (`conn.data_to_send()`), and feed received bytes
back in (`conn.receive_data(data)`). The `socksio/socks4.py` / `socksio/socks5.py`
`Connection` classes only own an outgoing buffer and an incoming buffer. All real network
I/O is delegated to the caller — in this stack, `httpcore`.

### 1.3 Protocol coverage

| Protocol | Objects | Evidence |
|---|---|---|
| SOCKS4 | `SOCKS4Request`, `SOCKS4Reply`, `SOCKS4ReplyCode`, `SOCKS4Command`, `SOCKS4Connection` | `socksio/socks4.py:14-27,30,104`; exported `socksio/__init__.py:4-11` |
| SOCKS4A | `SOCKS4ARequest` — allows domain names (proxy-side DNS) | `socksio/socks4.py:104-140`; `from_address` at `:138-140` keeps `AddressType.DN` |
| SOCKS5 | `SOCKS5Connection`, `SOCKS5CommandRequest`, `SOCKS5Reply`, `SOCKS5AType`, `SOCKS5AuthMethod`, `SOCKS5UsernamePasswordRequest` | `socksio/socks5.py:15-62`; exported `socksio/__init__.py:12-23` |

Constraints worth knowing:

- Plain **SOCKS4 rejects hostnames and IPv6**: `SOCKS4Request.from_address` raises
  `SOCKSError("IPv6 addresses and domain names are not supported by SOCKS4")`
  (`socksio/socks4.py:69-72`), and requires a non-empty `user_id` (`socksio/socks4.py:89-90`).
  SOCKS4A is the variant that permits hostnames.
- SOCKS5 address types: `IPV4_ADDRESS = b"\x01"`, `DOMAIN_NAME = b"\x03"`,
  `IPV6_ADDRESS = b"\x04"` (`socksio/socks5.py:32-37`).
- `encode_address` (`socksio/utils.py:34-44`) falls back to `AddressType.DN` for any
  non-IP-literal string — this is the mechanism that produces **remote (proxy-side) DNS**.
- Auth: `NO_AUTH_REQUIRED` and `USERNAME_PASSWORD` (RFC 1929) are implemented;
  `GSSAPI` exists as an enum value only (`socksio/socks5.py:19`) and the METADATA explicitly
  lists "SOCKS5 GSS-API authentication" as not yet implemented.
- `UDP_ASSOCIATE` exists as a command enum (`socksio/socks5.py:29`) but socksio has no
  datagram framing — TCP `CONNECT` is the only usable mode, which is all HTTP needs.

### 1.4 The app never imports socksio — confirmed

```
grep -rn "import socksio|from socksio" --include=*.py --include=*.toml .   (excluding .venv)
  → no matches
grep -rn -i "socks" src/
  src\screens\settings_screen.py:75,92,1450     (scheme allow-list + hint text)
  src\services\http_client.py:6,7               (docstring only)
```

The only `httpx` import in `src/` is `src/services/http_client.py:17`. `src/` contains
**zero** references to `socksio`, `httpcore`, `SOCKSProxy`, or `SOCKS4*`. socksio is reached
only indirectly: app → httpx transport → httpcore SOCKSProxy → socksio state machine.

---

## 2. Real scheme support chain

### 2.1 The chain, end to end

```
app Settings field (src/screens/settings_screen.py:1447-1451)
   └─ state.proxy_url (src/core/state.py:102)
        ├─ app httpx path  : src/services/http_client.py:43 → httpx.AsyncHTTPTransport(proxy=...)  (59-62)
        └─ user-scanner path: src/services/user_scanner_compat.py:132-133 / src/services/email_service.py:262-264
              └─ user_scanner.core.helpers.set_proxy_manager (core/helpers.py:680-686)
                   └─ ProxyManager keeps explicit schemes (core/helpers.py:622-645)
                        └─ get_proxy() (core/helpers.py:689-693)
                             └─ httpx.Client(proxy=proxy_val) (core/orchestrator.py:275) / curl_cffi session (core/impersonate.py:56)
```

### 2.2 httpx — the scheme gate (two independent gates)

**Gate 1 — `Proxy` constructor.** `httpx/_config.py:213-214`:

```python
if url.scheme not in ("http", "https", "socks5", "socks5h"):
    raise ValueError(f"Unknown scheme for proxy URL {url!r}")
```

**Gate 2 — transport construction.** `httpx/_transports/default.py`:

- sync: `:187` `elif proxy.url.scheme in ("socks5", "socks5h"):`
  → `:189` `import socksio` inside `try` → `:191-194` on ImportError:
  `"Using SOCKS proxy, but the 'socksio' package is not installed. Make sure to install httpx using pip install httpx[socks]."`
  → `:196` `httpcore.SOCKSProxy(...)`
- async: identical at `:331-340` (`httpcore.AsyncSOCKSProxy(...)`)
- fallback: `:211-215` (sync) and `:356-359` (async):
  `raise ValueError("Proxy protocol must be either 'http', 'https', 'socks5', or 'socks5h', but got {scheme!r}.")`

**Verdict:** httpx supports exactly `http`, `https`, `socks5`, `socks5h`. Nothing else.

### 2.3 SOCKS4 / SOCKS4A — present in socksio, absent in httpx and httpcore

- socksio ships both (`socksio/socks4.py:30` `SOCKS4Request`, `:104` `SOCKS4ARequest`,
  `:209` `SOCKS4Connection`).
- httpx never mentions socks4 — `grep -rn -i "socks4" httpx/` returns **no matches**; the
  only SOCKS strings in the whole package are `httpx/_config.py:213` and
  `httpx/_transports/default.py:187,213,331,357`.
- httpcore never mentions socks4 either — `grep -rn -i "socks4" httpcore/` → no matches.
  `httpcore/_sync/connection_pool.py:130` (and `_async/connection_pool.py:130`) dispatch only
  on `b"socks5"` / `b"socks5h"`.

So SOCKS4/4A is **library capability that no consumer in this stack can reach**. A
`socks4://` URL dies at the httpx `Proxy` constructor with a clean `ValueError`
(`httpx/_config.py:214`) — never at the socksio layer, because socksio's `SOCKS4Connection`
is never instantiated by httpcore.

### 2.4 httpcore — `SOCKSProxy`, and the lazy-import question

- `httpcore/__init__.py:46` exports `SOCKSProxy`; `:9` exports `AsyncSOCKSProxy`;
  `:98` / `:90` list them in `__all__`.
- Implementation: `httpcore/_sync/socks_proxy.py:105` `class SOCKSProxy(ConnectionPool)`
  and `:189` `class Socks5Connection(ConnectionInterface)`;
  async twin at `httpcore/_async/socks_proxy.py`.
- The SOCKS5 handshake itself is driven entirely by socksio:
  `httpcore/_sync/socks_proxy.py:49` `conn = socksio.socks5.SOCKS5Connection()`,
  `:57` `conn.send(SOCKS5AuthMethodsRequest([...]))`, `:63` `conn.receive_data(...)`,
  `:76` username/password sub-negotiation, `:88-92` `SOCKS5CommandRequest.from_address(CONNECT, (host, port))`.
  Reply-code mapping to `httpcore.ProxyError` at `:100-102`.

**Is socksio imported lazily?** Partly — and the failure mode differs by entry point:

| Entry point | Where socksio is imported | Failure if socksio missing |
|---|---|---|
| `httpx` transport | `httpx/_transports/default.py:189` (sync) / `:333` (async), inside `try/except ImportError` at **transport construction time** | `ImportError("Using SOCKS proxy, but the 'socksio' package is not installed...")` — raised eagerly when the client is built |
| `httpcore.SOCKSProxy` used directly | `httpcore/_sync/socks_proxy.py:6` `import socksio` (module level), but the module itself is imported lazily inside `ConnectionPool.create_connection` → `httpcore/_sync/connection_pool.py:131` `from .socks_proxy import Socks5Connection` | `ModuleNotFoundError` at **first connection creation**, not at pool construction |

**The "RuntimeError path" does not exist for socksio.** `grep -rn "RuntimeError" httpcore/`
yields 26 hits; the only module-level ones are `httpcore/__init__.py:59` and `:70`, and they
belong to `AnyIOBackend` and `TrioBackend` ("Attempted to use 'httpcore.AnyIOBackend' but
'anyio' is not installed"). There is **no** `RuntimeError` guarding socksio anywhere in
httpcore. The only socksio-missing failure mode is `ImportError`/`ModuleNotFoundError`
(as tabulated above). *This corrects a common assumption and is worth recording because
the failure is timing-sensitive: with direct httpcore use it appears at request time,
which looks like a network error rather than a dependency error.*

In this repo the risk is nil: socksio is a hard, unconditional dependency of user-scanner
(`user_scanner-1.5.2.3.dist-info\METADATA:11`), so it is always importable, and the
httpx `try/except ImportError` probe at `default.py:189` always succeeds.

### 2.5 `socks5://` vs `socks5h://` — identical behaviour in this stack (important)

httpcore dispatches both schemes to the same class:

```python
# httpcore/_sync/connection_pool.py:130  (identical at _async/connection_pool.py:130)
if self._proxy.url.scheme in (b"socks5", b"socks5h"):
    from .socks_proxy import Socks5Connection
```

and the destination is handed over as a **hostname string**, never a resolved IP:

```python
# httpcore/_sync/socks_proxy.py:237-238
"host": self._remote_origin.host.decode("ascii"),
```

That string flows into `SOCKS5CommandRequest.from_address` (`httpcore/_sync/socks_proxy.py:88-92`)
→ `socksio/socks5.py:188-189` → `encode_address` (`socksio/utils.py:34-44`) → for a hostname
this yields `AddressType.DN` → `SOCKS5AType.DOMAIN_NAME` (`socksio/socks5.py:36,43-44`).

**Consequence:** in httpx/httpcore, `socks5://` and `socks5h://` both perform **proxy-side DNS
resolution**. There is no local-DNS "socks5" variant in this stack, so the usual
"socks5 leaks DNS, socks5h does not" distinction **does not apply here** — both are
DNS-leak-free with respect to the destination hostname. The `socks5h` scheme is therefore
harmless and self-documenting, but choosing it changes nothing functionally.

### 2.6 user-scanner — ProxyManager scheme preservation

`user_scanner/core/helpers.py`:

- `_load_proxies_from_list` (`:622-632`): *"Keep explicit schemes, default to http:// when
  missing."* → `:627-628` `if "://" not in line: line = "http://" + line`.
- `_load_proxies` (file variant) (`:634-645`), with the explicit comment at `:641-642`:
  *"Keep explicit schemes (http://, socks5://, socks5h://, etc.). Only prepend http:// when
  no scheme is provided."*

So `socks5://` and `socks5h://` survive the round-trip through ProxyManager intact, and a
bare `1.2.3.4:8080` is normalised to `http://1.2.3.4:8080`. SOCKS4 strings are also preserved
verbatim by ProxyManager (it does not filter schemes) — they only fail later, at httpx.

Rotation: `get_next_proxy` (`:655-663`) round-robins under a `threading.Lock`;
`get_random_proxy` (`:665-669`); `count()` (`:671-673`).
Global singleton: `_proxy_manager` (`:677`), `set_proxy_manager` (`:680-686`), `get_proxy`
(`:689-693`), `get_proxy_count` (`:696-700`).

### 2.7 Proxy validation — endpoint and semantics

`user_scanner/core/helpers.py:577-605`:

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

- **Target URL:** `http://gstatic.com/generate_204` (plain **HTTP**).
- **Accept:** status `200` or `204`; anything else = proxy considered dead.
- **Timeout:** default **5 seconds** (`validate_proxies(..., timeout: int = 5, ...)` at `:603`).
- **Concurrency:** default **max_workers = 50**, implemented as an `asyncio.Semaphore`
  (`:589`), with `asyncio.gather` over all entries (`:597-599`).
- **Error semantics:** every exception is swallowed (`:583-584`). The function returns only
  the *surviving* proxies; it **never reports why** a proxy failed, and it cannot distinguish
  "proxy refused the connection" from "scheme unsupported" from "DNS failure".

Note also `httpx.AsyncClient(proxy=...)` is still a supported kwarg in the installed
httpx 0.28.1 (`httpx/_client.py:651`), so the validation path is valid.

### 2.8 The curl_cffi (impersonation) leg

`user_scanner/core/impersonate.py:56` and `:67` pass `get_proxy()` — i.e. the *same* proxy
string that ProxyManager preserved — into a curl_cffi session. curl_cffi understands
`socks5://`/`socks5h://` natively (it is not built on socksio), so both legs of a scan agree
on the scheme. SOCKS4 would be accepted by curl_cffi but rejected by httpx — another reason
to keep the scheme allow-list narrow and consistent.

---

## 3. App usage and invalid-input behaviour

### 3.1 Where the app's proxy lives

| Layer | Location |
|---|---|
| Storage key | `src/core/constants.py:46` `STORAGE_PROXY_URL = "sherlock_proxy_url"` |
| State field | `src/core/state.py:102` `proxy_url: str = ""` |
| Restore on boot | `src/main.py:732-734` |
| Settings field | `src/screens/settings_screen.py:1447-1451` (hint at `:1450`) |
| Commit handler | `src/screens/settings_screen.py:475-484` |
| Proxy file (separate) | `src/core/constants.py:76`, `src/core/state.py:78`, `src/screens/settings_screen.py:1466-1475` |
| I2P gateway (separate) | `src/core/constants.py:52`, `src/core/state.py:110`, `src/screens/settings_screen.py:1456-1465` |

### 3.2 Which layer actually receives it — two consumers

1. **The app's own httpx client** — `src/services/http_client.py:43` reads
   `state.proxy_url` *live on every access* and rebuilds the pooled client when the proxy
   changes (`:45-48`). With a proxy set it mounts a dedicated
   `httpx.AsyncHTTPTransport(retries=..., limits=..., http2=True, proxy=proxy)` at
   `all://` (`:59-65`). This is the path that actually exercises socksio for the app's own
   HTTP traffic (update check, avatar downloads, etc.).

2. **user-scanner** — via the global `set_proxy_manager`:
   - `src/services/user_scanner_compat.py:132-133` (username scan), fed from
     `src/services/sherlock_service.py:211` and `:242` via
     `proxy=getattr(app_state, "proxy_url", "") or None`.
   - `src/services/email_service.py:262-264` (email scan), fed from
     `src/main.py:1088`, `:1537`, `:1778` via
     `proxy=getattr(state, "proxy_url", "") or ""`.

   Inside user-scanner the proxy reaches httpx at `core/orchestrator.py:275`
   (`httpx.Client(http2=use_http2, proxy=proxy_val, verify=verify)`) and curl_cffi at
   `core/impersonate.py:56`.

### 3.3 Invalid input — does it fail silently or error cleanly?

| Input | Where it is caught | User-visible result |
|---|---|---|
| `socks4://…` / `socks4a://…` in the **Settings proxy field** | `src/screens/settings_screen.py:75` `_PROXY_SCHEMES = ("http","https","socks5","socks5h")`; `:91-92` → "scheme must be http://, https://, socks5:// or socks5h://" | **Clean error.** `_on_proxy_change` (`:475-484`) shows `Invalid proxy URL: scheme must be http://, https://, socks5:// or socks5h://.` and returns `False` — the value is **not** written to `state.proxy_url` and **not** persisted. No runtime failure. |
| `socks4://…` in the **proxy file** | No app-side gate. Reaches `httpx.Proxy.__init__` → `httpx/_config.py:214` `ValueError: Unknown scheme for proxy URL …` → swallowed by `except Exception: pass` (`user_scanner/core/helpers.py:583`) | **Mis-reported.** The proxy is simply dropped, and the user sees "No proxies passed validation" (`src/screens/settings_screen.py:676`) — indistinguishable from a dead proxy. |
| Bare scheme `socks5://` (no host) | `src/screens/settings_screen.py:93-94` "missing host (bare scheme is not a proxy)" | Clean error, not persisted. |
| Bad / out-of-range port | `src/screens/settings_screen.py:96-100` ("invalid port", "port N out of range 1-65535") | Clean error, not persisted. |
| Empty field | `src/screens/settings_screen.py:84-86` → `None` (valid) | Means "direct connection". |
| Unreachable/dead SOCKS5 proxy at scan time | httpx raises `httpx.ConnectError`/`httpx.ProxyError` (`httpx/_transports/default.py:87` maps `httpcore.ProxyError`) | Surfaced only as a **per-site scan error** inside the results list. There is no dedicated "your proxy died" banner. `set_proxy_manager` failures are swallowed (`src/services/user_scanner_compat.py:131-135`, `src/services/email_service.py:261-266` both `except Exception: pass`). |

**Conclusion for SOCKS4/4a:** the app never lets them through the Settings field, so they
cannot reach socksio. They error cleanly at the UI. The only place they can leak in is the
**proxy file**, where the error message is misleading.

### 3.4 Does the app surface `validate_proxies` results? — Yes, in two places

**Settings → "Validate Proxies"** (`src/screens/settings_screen.py:643-678`, button at
`:1476-1486`):

- Collects the comma-separated `state.proxy_url` (`:646-647`) **plus** every non-empty line
  of `state.proxy_file` (`:648-660`).
- Runs `validate_proxies` off the UI thread: `:668`
  `working = await asyncio.to_thread(validate_proxies, proxies)`.
- Results: `"{n}/{m} proxy/proxies OK"` (`:670-674`, SUCCESS), `"No proxies passed
  validation"` (`:676`, ERROR), `"Proxy validation failed: {exc}"` (`:678`, ERROR).

**Home → "Validate proxy" chip** (`src/screens/home_screen.py:547-563`, chip at `:903-909`):

- Validates only `state.proxy_url` (`:548`), one entry.
- `"Proxy OK: 1/1 working"` (`:561`) or `"Proxy failed validation"` (`:563`).

So yes, `validate_proxies` output is surfaced — but note the two limits already noted in
§2.7: the probe target is plain-HTTP `gstatic.com/generate_204` (so the **TLS-over-SOCKS**
leg is never exercised), and the function reports *counts only*, never *reasons*.

### 3.5 Two real defects found in the app wiring

**(A) Stale proxy is never cleared.** Both `set_proxy_manager` call sites are guarded by
`if proxy:` — `src/services/user_scanner_compat.py:130` and `src/services/email_service.py:263`.
`set_proxy_manager` clears the global only when called with no arguments
(`user_scanner/core/helpers.py:683-686`: `if proxy_file or proxies is not None: … else:
_proxy_manager = None`). Because the app never calls it with empty arguments, **clearing the
proxy field in Settings and starting a new scan leaves the previous proxy active inside
user-scanner** — username and email scans keep tunnelling through the old SOCKS proxy while
the app's own httpx client (`src/services/http_client.py:43-48`) has already reverted to
direct. The two legs of the app then disagree about whether traffic is proxied.

**(B) The proxy file is validated but never used.** `state.proxy_file` is referenced only in
`src/screens/settings_screen.py:639-641` (persist) and `:648-658` (read for validation).
No call site passes `proxy_file=` to `set_proxy_manager`, and no call site passes the file's
lines as `proxies=[...]`. `ProxyManager._load_proxies` and the round-robin rotation
(`user_scanner/core/helpers.py:634-663`) are therefore **dead code from the app's point of
view**. The "Validate Proxies" button can report "12/12 proxy/proxies OK" for a file whose
proxies are then never used for a single request.

---

## 4. Proposals (concrete)

### P1 — Clear the proxy manager when the proxy field is emptied (fixes defect A)
`src/services/user_scanner_compat.py:130` and `src/services/email_service.py:263`:

```python
# before
if proxy:
    set_proxy_manager(proxies=[proxy])
# after
set_proxy_manager(proxies=[proxy]) if proxy else set_proxy_manager()
```

`set_proxy_manager()` with no arguments sets `_proxy_manager = None`
(`user_scanner/core/helpers.py:685-686`). Do **not** call `set_proxy_manager(proxies=[])` —
`ProxyManager._load_proxies_from_list` raises `ValueError("No valid proxies found in list")`
(`:631-632`).

### P2 — Wire the proxy file into the scan (fixes defect B)
At the same two call sites, prefer the file when it is set, mirroring the Settings
validation path (`src/screens/settings_screen.py:648-658`):

```python
if proxy_file:
    set_proxy_manager(proxy_file=proxy_file)     # keeps scheme, enables round-robin
elif proxy:
    set_proxy_manager(proxies=[proxy])
else:
    set_proxy_manager()
```

`ProxyManager(proxy_file=...)` already preserves `socks5://`/`socks5h://`
(`user_scanner/core/helpers.py:641-645`) and rotates round-robin (`:655-663`), so this needs
no changes in the third-party package.

### P3 — Distinguish "unsupported scheme" from "dead proxy" in validation
The app knows its own allow-list (`src/screens/settings_screen.py:75`). Before handing lines
to `validate_proxies`, split the list into supported and unsupported:

```python
supported = [p for p in proxies if urlparse(p).scheme.lower() in _PROXY_SCHEMES]
rejected  = [p for p in proxies if urlparse(p).scheme.lower() not in _PROXY_SCHEMES]
# snackbar: f"{len(supported)-len(working)}/{len(supported)} OK; "
#           f"{len(rejected)} skipped (unsupported scheme, e.g. socks4://)"
```

This removes the current confusing "No proxies passed validation" for a `socks4://` line
(`src/screens/settings_screen.py:676`).

### P4 — SOCKS5h as the recommended default (with accurate wording)
`src/screens/settings_screen.py:1450` currently hints
`"socks5://127.0.0.1:1080 or http://proxy:8080 (empty = direct)"`. Change it to:

```
"socks5h://127.0.0.1:1080 or http://proxy:8080 (empty = direct)"
```

with a help line under the field:

> `socks5h` resolves the target hostname at the proxy. In this app `socks5://` and
> `socks5h://` behave identically (both use proxy-side DNS), so `socks5h` is simply the
> explicit, self-documenting choice.

Being precise here matters: it avoids implying that `socks5://` leaks DNS when, per §2.5, it
does not in this stack. It also matches the on-device Tor convention (Orbot/Arti expose
`127.0.0.1:9050` with remote DNS).

### P5 — Probe an HTTPS target so the TLS-over-SOCKS leg is validated
`validate_proxies` targets plain HTTP (`user_scanner/core/helpers.py:580`), so a proxy that
handshakes fine but cannot carry TLS reports as "working" and then fails on every real
target. The app can add a second, app-side probe using its own client
(`src/services/http_client.py`) against an HTTPS 204 endpoint, and report the two results
separately. (Do not patch the vendored `user_scanner` package — keep the fix in the app.)

### P6 — Map transport errors to actionable messages
`httpcore.ProxyError` → `httpx.ProxyError` (`httpx/_transports/default.py:87`). Catch
`httpx.ProxyError` and `httpx.ConnectError` in the app's own probe and say which:
- "SOCKS handshake rejected by proxy" → `ProxyError`
- "proxy host unreachable" → `ConnectError`
- "SOCKS auth failed" → `ProxyError("Invalid username/password")`
  (`httpcore/_sync/socks_proxy.py:85`)

Today every one of these collapses into the same "Proxy failed validation"
(`src/screens/home_screen.py:563`).

### P7 — SOCKS4/4A note in Settings help
The current error message ("scheme must be http://, https://, socks5:// or socks5h://")
is accurate but does not say *why* socks4 is unavailable. Adding one line to the help text
prevents the most likely user mistake (pasting a `socks4://` line from a proxy vendor list):

> SOCKS4/SOCKS4A are not supported: the installed HTTP stack only speaks SOCKS5.

### P8 — Mobile: SOCKS5 works on Android/iOS; Tor-via-Orbot is an unused opportunity
- socksio is a **pure-Python** wheel (`py3-none-any`, `Root-Is-Purelib: true`) with **no
  runtime dependencies and no C extension**, so it is importable on Android (`arm64-v8a`,
  `x86_64` per `pyproject.toml:35-37`) and on iOS without any native build step. The app's
  own `httpx`+`httpcore`+socksio path is fully portable.
- **DNS-leak property:** the destination hostname is always sent to the proxy as a
  `DOMAIN_NAME` ATYP (`socksio/socks5.py:36`; `socksio/utils.py:43-44`), so the target
  hostname is never resolved on-device. Both `socks5://` and `socks5h://` are DNS-leak-free
  with respect to the target (§2.5).
- **Unused feature opportunity — Tor on device:** Orbot (Android) and Arti (iOS) expose a
  local SOCKS5 port (`127.0.0.1:9050`) with remote DNS by default. A one-tap preset
  (`socks5h://127.0.0.1:9050`) plus a "Tor" badge would give Sherlock a genuine
  anonymity-preserving mode with zero new dependencies — the whole protocol stack is
  already installed and wired. Note the practical limit: socksio has **no UDP ASSOCIATE**
  support, so only TCP `CONNECT` traffic works — which is exactly what HTTP needs, but any
  future DNS-over-UDP or QUIC path would not be tunnelable.
- **Practical caveat for Android:** a SOCKS5 server on `127.0.0.1` inside the app sandbox
  requires the proxy to live on-device (Orbot) — the app cannot bind a loopback port that a
  separate VPN app owns; users must use Orbot's own listener rather than a per-app VPN
  slot.

---

## 5. Verdict

**ISSUES FOUND.**

The dependency itself is in good shape: socksio 1.0.0 is installed, pure-Python, genuinely
sans-I/O (no socket I/O anywhere — only `inet_pton`/`inet_ntop` for address encoding), and
correctly reachable through httpx → httpcore → socksio with no version friction
(user-scanner pins `socksio>=1.0,<2`; httpx/httpcore want `socksio==1.*`; 1.0.0 satisfies
all three).

The scheme story is coherent end to end for the supported set — `http`, `https`, `socks5`,
`socks5h` — enforced consistently by the app (`src/screens/settings_screen.py:75`),
user-scanner's ProxyManager (`user_scanner/core/helpers.py:641-645`), httpx
(`httpx/_config.py:213`, `httpx/_transports/default.py:187,331`) and httpcore
(`httpcore/_sync/connection_pool.py:130`). SOCKS4/4A exist in socksio but are unreachable
through httpx/httpcore and are correctly rejected at the app's Settings field.

Three defects and one documentation error need fixing:

1. **Stale proxy is never cleared** (defect A) — the proxy manager is only set, never reset,
   so clearing the Settings field does not stop user-scanner from tunnelling through the
   previous proxy.
2. **The proxy file is validated but never used** (defect B) — "Validate Proxies" reports
   results for a file that is never fed to `set_proxy_manager`; rotation is dead code.
3. **Unsupported schemes in the proxy file are mis-reported** as dead proxies, because
   `validate_proxies` swallows every exception (`user_scanner/core/helpers.py:583`).
4. **Correction to the background doc:** there is **no** `RuntimeError` path for a missing
   socksio in httpcore — the only module-level `RuntimeError`s are for the AnyIO and Trio
   backends (`httpcore/__init__.py:59,70`). The real failure modes are `ImportError` at
   httpx transport construction (`httpx/_transports/default.py:191-194`) and
   `ModuleNotFoundError` at first connection when httpcore is used directly
   (`httpcore/_sync/connection_pool.py:131` → `httpcore/_sync/socks_proxy.py:6`).

Also worth recording: in this stack `socks5://` and `socks5h://` are **behaviourally
identical** (both resolve DNS at the proxy) — a detail the V2-era doc and the Settings hint
text do not convey.

Proposed fixes P1-P8 above are all app-local; no changes to the installed packages are
required, and no third-party package needs patching.
