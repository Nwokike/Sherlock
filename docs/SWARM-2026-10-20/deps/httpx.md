# httpx 0.28.1 / httpcore 1.0.9 — Dependency Audit (Sherlock-V3)

**Auditor:** dependency-audit subagent
**Date:** 2026-10-20
**Source of truth:** the installed venv at `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/`
**Packages:** `httpx` 0.28.1 (`httpx-0.28.1.dist-info`), `httpcore` 1.0.9 (`httpcore-1.0.9.dist-info`), plus the folded-in `h2` 4.4.1 / `hpack` 4.2.0 / `hyperframe` 6.1.0 / `h11` 0.16.0 / `socksio` 1.0.0 / `anyio` 4.15.1 / `certifi` 2026.10.18 / `idna` 3.20
**Background doc (V2-era, verified):** `docs/reference/dep-httpx.md`
**venv package count:** 34 (verified — `ls -d .venv/Lib/site-packages/*.dist-info | wc -l` → 34)

> Scope note: `httpx` is **not** a direct dependency of Sherlock-V3. `pyproject.toml:9-12` declares only `flet`, `flet-ads`, `user-scanner>=1.5.2.3`, `phonsint>=0.1.0`. `httpx` arrives transitively through `user-scanner` (`user_scanner-1.5.2.3.dist-info/METADATA:10-11` → `httpx[http2]>=0.27,<0.29` and `socksio>=1.0,<2`). The app nevertheless imports `httpx` **directly** in one file. That direct import — and only that import — is the subject of this audit.

---

## 1) Installed httpx + httpcore verification

### 1.1 Identity

| Fact | Value | Evidence |
|---|---|---|
| `httpx.__version__` | `0.28.1` | `httpx/__version__.py:3` |
| `httpcore.__version__` | `1.0.9` | `httpcore/__init__.py:134` |
| `httpx` requires Python | `>=3.8` | `httpx-0.28.1.dist-info/METADATA:26` |
| `httpx` runtime deps | `anyio`, `certifi`, `httpcore==1.*`, `idna` | `METADATA:27-30` |
| `httpx` extras declared | `brotli`, `cli`, `http2`, `socks`, `zstd` | `METADATA:31-43` |

Runtime check against the live venv:

```
httpx 0.28.1 / httpcore 1.0.9 / py 3.14.7
```

### 1.2 `Timeout`

`httpx/_config.py:72-158`; constructor at `:86-130`.

- Four independent phases: `connect`, `read`, `write`, `pool`.
- The app's construction style `Timeout(connect=…, read=…, write=…, pool=…)` is legal: when **all four** are set explicitly, the `else` branch at `:111-120` assigns them directly and no default is required.
- `Timeout(connect=5.0)` alone raises `ValueError("httpx must either include a default, or set all four parameters explicitly.")` (`:122-126`) — verified at runtime. The app does not hit this (it sets all four).
- Default when nothing is passed: `DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)` (`_config.py:246`).
- Serialised into `request.extensions["timeout"]` and mapped to `httpcore` exceptions via `httpx/_transports/default.py:78-82` / `100-119`.

### 1.3 `Limits`

`httpx/_config.py:159-198`; constructor `:173-182`.

- Keyword-only: `max_connections`, `max_keepalive_connections`, `keepalive_expiry` (default `5.0`).
- httpx default: `DEFAULT_LIMITS = Limits(max_connections=100, max_keepalive_connections=20)` (`_config.py:247`).
- The app's `Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0)` is a valid call and **does** land on the transport — runtime-verified on the created pool: `max_conn=20 keepalive=10 expiry=30.0`.

### 1.4 HTTP/2 guard

`httpx/_client.py:676-684` (sync `Client`) and `:1390-1397` (async `AsyncClient`):

```python
if http2:
    try:
        import h2  # noqa
    except ImportError:
        raise ImportError("Using http2=True, but the 'h2' package is not installed. …")
```

`h2` 4.4.1 **is** installed (with `hpack` 4.2.0, `hyperframe` 6.1.0) → `http2=True` is valid in this venv. The guard is the *only* thing the client-level `http2=True` does when an explicit `transport=` is supplied.

### 1.5 Proxy schemes

- `httpx.Proxy` accepts exactly `("http", "https", "socks5", "socks5h")` — `httpx/_config.py:213-214`, else `ValueError("Unknown scheme for proxy URL …")`.
- The transport re-checks the same set: `httpx/_transports/default.py:168` (sync http/https), `:187` (sync socks), `:312` (async http/https), `:331` (async socks), with the `else: raise ValueError("Proxy protocol must be either 'http', 'https', 'socks5', or 'socks5h'")` at `:352-355` (async) / `:210-213` (sync).
- Runtime-verified rejections: `socks4://…` → `ValueError: Unknown scheme for proxy URL`; `socks://…` → same.
- The app's whitelist `settings_screen.py:76` `_PROXY_SCHEMES = ("http", "https", "socks5", "socks5h")` **exactly matches** httpx's. No mismatch. ✅
- Credentials embedded in the proxy URL are extracted by `Proxy.__init__` (`_config.py:216-220`) and sent as proxy Basic auth (`raw_auth`, `:227-233`); the password is masked in `__repr__` (`:243`).

### 1.6 Retries semantics — transport vs. mounts (**the important one**)

`retries` is a **connection-establishment** setting, not a request-retry setting.

- httpcore applies it in `httpcore/_async/connection.py:110-165`: `retries_left = self._retries`, and the retry loop re-attempts **only** on `ConnectError` / `ConnectTimeout`, with exponential backoff. It never retries a status code, a read timeout, or a non-idempotent request.
- `httpcore/_async/connection_pool.py:57` (param) → `:109` (`self._retries = retries`) → `:174` (forwarded to each `AsyncConnection`).
- httpcore's proxy pools *do* accept `retries` (`httpcore/_async/http_proxy.py:71`, `httpcore/_async/socks_proxy.py:120`).

**But httpx 0.28.1 never passes `retries` to them.** In `httpx/_transports/default.py`:

| Branch | Lines | `retries` forwarded? |
|---|---|---|
| direct → `httpcore.AsyncConnectionPool` | `:299-310` | **Yes** — `retries=retries` at `:309` |
| `http`/`https` proxy → `httpcore.AsyncHTTPProxy` | `:312-329` | **No** — the kwarg list ends at `socket_options` (`:329`) |
| `socks5`/`socks5h` proxy → `httpcore.AsyncSOCKSProxy` | `:331-350` | **No** |

Runtime-verified:

```
direct pool:    AsyncConnectionPool  _retries = 3
httpproxy pool: AsyncHTTPProxy        _retries = 0   # retries=3 was passed
socks pool:     AsyncSOCKSProxy       _retries = 0   # retries=3 was passed
```

(The same is true on the sync side: `default.py:155-166` forwards `retries`, `:168-185` and `:187-210` do not.)

**The `transport=` + `proxy=` caveat has two halves, and the app only fixed one of them:**

1. `httpx.AsyncClient(transport=…, proxy=…)` → `_init_proxy_transport` (`_client.py:1454-1472`, sync `:740-758`) has **no `retries` parameter** → the internally-built proxy mount gets `retries=0`. This half of the app's comment is **correct**.
2. But building the proxy transport *yourself* as `httpx.AsyncHTTPTransport(retries=N, proxy=…)` also yields `retries=0`, because httpx drops the kwarg for proxy pools. **There is no public httpx API in 0.28.1 that gives a proxied leg connection retries.** The app's "both legs explicit" workaround is a no-op for the proxy leg.

### 1.7 Redirects

- Client default `follow_redirects=False` (verified via `inspect.signature(httpx.AsyncClient.__init__)`), `DEFAULT_MAX_REDIRECTS = 20` (`_config.py:248`).
- The app sets `follow_redirects=True` on the shared client — correct and necessary for CDN avatars and the GitHub-hosted update config.
- Cross-origin `Authorization` stripping and method rewriting on 301/302/303/307/308 live in `httpx/_client.py:494-583` (`_redirect_method` `:494`, `_redirect_headers` `:546`, `_redirect_stream` `:573`); the loop guard is `TooManyRedirects` raised at `_client.py:972` (sync) / `:1687` (async).

### 1.8 Auth flows available

`httpx/_auth.py` — all generator-based (`auth_flow` yields the request, receives the response back):

| Class | Line | Notes |
|---|---|---|
| `Auth` | `:22` | base; `auth_flow`, `sync_auth_flow`, `async_auth_flow` (`:62-111`) |
| `FunctionAuth` | `:113` | single-arg callable |
| `BasicAuth` | `:126` | `Authorization: Basic …` |
| `NetRCAuth` | `:145` | reads `~/.netrc` by host |
| `DigestAuth` | `:175` | RFC 7616 / 2617, MD5/SHA-256/SHA-512 |

All exported in `httpx/__init__.py`. **The app uses none of them.**

### 1.9 Cookies API

`httpx/_models.py:1079` — `class Cookies(typing.MutableMapping[str, str])`, wrapping `http.cookiejar.CookieJar` (`:1086-1100`).
- `extract_cookies(response)` (`:1101-1109`) runs automatically after every request (`_client.py:1022` sync, `:1737` async).
- Per-request `cookies=` is **deprecated** and warns (`_client.py:1519-1525` async, `:804-810` sync).
- **The app uses none of it.**

### 1.10 Streaming APIs

- `Client.stream` (`_client.py:828-878`) / `AsyncClient.stream` (`:1543-1593`) — async/sync context managers that guarantee `close()` / `aclose()` in a `finally`.
- Byte/text iteration: `iter_bytes` / `aiter_bytes`, `iter_text` / `aiter_text`, `iter_lines` / `aiter_lines`, `iter_raw` / `aiter_raw` (`_models.py:884-960` sync, `:982-1064` async).
- The app uses `aiter_bytes(_AVATAR_CHUNK)` at `cache_service.py:295` — correct API, and it is the one streaming consumer.

### 1.11 Transports available

| Transport | Location | Notes |
|---|---|---|
| `HTTPTransport` | `_transports/default.py:135` | sync, httpcore `ConnectionPool` |
| `AsyncHTTPTransport` | `_transports/default.py:279` | async, httpcore `AsyncConnectionPool`; `uds`, `local_address`, `socket_options`, `retries` |
| `MockTransport` | `_transports/mock.py:15` | implements **both** `BaseTransport` and `AsyncBaseTransport`; `handler(request) -> Response` |
| `ASGITransport` | `_transports/asgi.py:63` | in-memory ASGI |
| `WSGITransport` | `_transports/wsgi.py:77` | in-memory WSGI |

All five are exported from `httpx/__init__.py`. **The app uses only `AsyncHTTPTransport`.**

### 1.12 The mounts mechanism

- `AsyncClient(mounts=…)` → `_client.py:1412-1430`: the client first builds `_mounts` from the proxy map (`:1412-1425`), then `self._mounts.update({URLPattern(key): transport …})` (`:1426-1429`), then sorts (`:1430`).
- `_transport_for_url(url)` (`:1474-1482`) walks `_mounts` in order and returns the first matching transport, falling back to `self._transport`.
- Runtime-verified `URLPattern` semantics: `"all://"` matches **both** `http://` and `https://` URLs. ✅ The app's `mounts={"all://": proxy_transport}` therefore covers every scheme.
- `allow_env_proxies = trust_env and transport is None` (`:1399`) — see §2.4.

### 1.13 httpcore 1.0.9

- **Backend:** `httpcore/_backends/auto.py` `AutoBackend` → `current_async_library()` (`httpcore/_synchronization.py:23-40`) returns `"asyncio"` (neither `sniffio` nor `trio` is installed) → `httpcore/_backends/anyio.py` (which `import anyio` at `:6`). `anyio` 4.15.1 is installed. The **trio** backend (`_backends/trio.py`) is dead code here — `trio` is **not** installed.
- **ConnectionPool limits defaults:** `httpcore/_async/connection_pool.py:48-62` → `max_connections=10` (`:52`), `max_keepalive_connections=None` (`:53`), `keepalive_expiry=None` (`:54`), `retries=0` (`:57`). `None` is widened to `sys.maxsize` (`:94-101`). Note this differs from httpx's `DEFAULT_LIMITS` (100/20) — httpx always passes explicit values, so the httpcore defaults never apply to an httpx-built pool.
- **SOCKSProxy availability:** `httpcore/_async/socks_proxy.py:6` — `import socksio` at **module level, unconditional**. `socksio` 1.0.0 **is** installed → the import succeeds. Runtime-verified: `httpcore._async.socks_proxy.socksio` resolves, and `httpx.AsyncHTTPTransport(proxy='socks5://127.0.0.1:1080')` constructs an `AsyncSOCKSProxy` without error.
- **Is socksio REALLY usable here?** Yes, end-to-end: `user-scanner` declares `socksio>=1.0,<2` (`user_scanner-1.5.2.3.dist-info/METADATA:11`) and `httpx[http2]>=0.27,<0.29` (`:10`); the venv satisfies both; `socksio` 1.0.0 is importable; `httpcore` imports it at module scope; `httpx` raises a clear `ImportError("Using SOCKS proxy, but the 'socksio' package is not installed…")` only if it is absent (`_transports/default.py:333-338`). **SOCKS is genuinely functional, not a paper dependency.**

### 1.14 Which `httpx[...]` extras are actually installed

| Extra | Required | Installed? | Consequence |
|---|---|---|---|
| `httpx[http2]` | `h2<5,>=3` | ✅ **h2 4.4.1** (+ hpack 4.2.0, hyperframe 6.1.0) | `http2=True` is legal everywhere |
| `httpx[socks]` | `socksio==1.*` | ✅ **socksio 1.0.0** | `socks5://` / `socks5h://` proxies work |
| `httpx[brotli]` | `brotli` / `brotlicffi` | ❌ **not installed** | no Brotli decoding |
| `httpx[zstd]` | `zstandard>=0.18.0` | ❌ **not installed** | no Zstandard decoding |
| `httpx[cli]` | `click==8.*` | ❌ **not installed** (`click` was removed with reportlab) | `httpx` CLI unavailable |
| `httpx-sse` | (separate package, not an httpx extra) | ❌ **not installed** | no SSE support |

**The missing brotli/zstd extras cause no protocol bug.** httpx derives its `Accept-Encoding` from the decoders it actually has: `SUPPORTED_DECODERS` (`_decoders.py:381-387`) pops `"br"` (`:390-391`) and `"zstd"` (`:392-393`) when the packages are absent, and `ACCEPT_ENCODING` is computed from that dict (`_client.py:118-121`). Runtime-verified:

```
ACCEPT_ENCODING = 'gzip, deflate'
client default Accept-Encoding: gzip, deflate
```

So servers fall back to gzip. It is a **bandwidth optimisation opportunity**, not a correctness issue.

---

## 2) App wiring correctness (file:line)

### 2.1 The one app-level httpx consumer

`grep -rn "httpx" src/` confirms **`src/services/http_client.py` is the only app file that imports httpx**. There is no `import requests`, `import aiohttp`, `urllib.request`, or `urlopen` anywhere in `src/`. (`phonsint` uses `curl_cffi`, not httpx — verified: `phonsint/core/impersonate.py:4`, `phonsint/modules/crm/zoho.py:3`.)

Consumers of the shared client:

| Call site | What it does |
|---|---|
| `src/services/update_service.py:72-74` | `await get_client().get(self.config_url, timeout=4.0)` — GitHub-hosted update/announcement JSON |
| `src/services/cache_service.py:278-281` | `async with get_client().stream("GET", url, headers={"User-Agent": "Sherlock/2.x"})` — avatar CDN download, 5 MB cap |
| `src/main.py:2432-2437` | `from services.http_client import close_client` → `await close_client()` inside `page.on_close` |

### 2.2 Parameter-by-parameter verification of `src/services/http_client.py`

| Line | App code | Installed API | Verdict |
|---|---|---|---|
| 49-53 | `httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0)` | `_config.py:173-182` | ✅ valid; runtime-verified on the pool (`20 / 10 / 30.0`) |
| 54 | `httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)` | `_config.py:111-120` | ✅ valid (all four set) |
| 58 | `httpx.AsyncHTTPTransport(retries=retries, limits=limits, http2=True)` | `default.py:280-292` | ✅ valid kwargs; `retries` reaches the direct pool (`:309`) |
| 60-62 | `httpx.AsyncHTTPTransport(retries=retries, limits=limits, http2=True, proxy=proxy)` | `default.py:280-292` | ✅ valid kwargs — but **`retries` is silently dropped** (§1.6) |
| 63-69 | `httpx.AsyncClient(transport=direct, mounts={"all://": proxy_transport}, timeout=timeout, http2=True, follow_redirects=True)` | `_client.py:1353-1356` signature | ✅ all params exist; `mounts` accepted (`:1405-1415`) |
| 71-77 | `httpx.AsyncClient(transport=direct, timeout=timeout, http2=True, limits=limits, follow_redirects=True)` | idem | ✅ params exist, but `limits=` is **inert** (see B5) |
| — | `verify=` never passed | `default.py:281` `verify: ssl.SSLContext | str | bool = True` | ✅ default `True` → certifi CA bundle (`_config.py:33-40`). Correct. |
| 68/76 | `follow_redirects=True` | client default `False` | ✅ intentional override, needed for CDN + GitHub redirects |
| 67/74 | `http2=True` on the client | `_client.py:1390-1397` guard | ✅ legal (h2 installed), but redundant — the transport already carries `http2=True` |
| 45-46 | rebuild key `(proxy, retries)` | — | ✅ sound design |
| 28-35 | `_get_retries()` clamps to `[0, 3]` | — | ✅ correct; runtime-verified `state.retries=4 → 3` |

**No API hallucination anywhere.** Every httpx symbol and keyword the app uses exists in 0.28.1 with a compatible signature. `ruff check src/services/http_client.py src/services/cache_service.py src/services/update_service.py` → **All checks passed!**

### 2.3 Client lifecycle in an asyncio app — correct

Verified by execution, not by reading:

```
c1 state: ClientState.UNOPENED
rebuilt on proxy change? True
old c1 state after drain: ClientState.CLOSED
new c2 state: ClientState.UNOPENED
after close_client(): module _client = None, c2 state = ClientState.CLOSED
double close ok
```

- **`aclose` on shutdown** — `close_client()` (`:107-113`) is wired into `page.on_close` (`src/main.py:2432-2437`), and `page.on_close` is a real flet 1.0.4 event (`flet/controls/page.py:676`). ✅
- **Idempotency** — `httpx.AsyncClient.aclose` guards on `self._state != ClientState.CLOSED` (`_client.py:1982-1988`), so a double close is safe. ✅
- **Rebuild-on-settings-change** — correct: proxy/retries change ⇒ new client; old client drained in a tracked background task; `AsyncClient.aclose` closes both `self._transport` **and** every mount (`_client.py:1985-1988`), so the direct transport *and* the proxy transport are both torn down. ✅
- **`_drain` without a loop** (`:88-97`) — correctly detects the missing loop, logs at WARNING, and returns instead of raising. `spawn` (`src/core/tasks.py:18-31`) uses `asyncio.create_task(coro, name=…)`, valid on 3.14. ✅
- **Sync/async mixing** — none in the app. Both consumers are async (`await` / `async with`). The app never touches the sync `httpx.Client` nor the module-level sync helpers `httpx.get`/`httpx.stream` (`_api.py:39-405` are all `def`, not `async def`). ✅
- **The engines' sync client is correctly offloaded** — user-scanner's `orchestrator.get_client` (`user_scanner/core/orchestrator.py:267-276`) caches **sync** `httpx.Client` objects; the app drives the sync site-check functions via `loop.run_in_executor(None, func, …)` (`src/services/user_scanner_compat.py:203` and `:282`), so the sync pool never blocks the event loop, and `httpx.Client` is thread-safe. ✅

### 2.4 `trust_env` — a half-state, worth a decision

`trust_env` is left at its default `True` on both the client and the transport. Because the app supplies `transport=`, `allow_env_proxies = trust_env and transport is None` evaluates to **False** (`_client.py:1399`). Runtime-verified with `HTTPS_PROXY`/`HTTP_PROXY` set:

```
plain client (no transport=):  mounts={'https://': …, 'http://': …}   # env proxy honored
client WITH transport= (app):  mounts={}                               # env proxy IGNORED
```

But the transport's own `trust_env=True` still feeds `create_ssl_context(verify=True, cert=None, trust_env=True)` (`_transports/default.py:297`), which honours `SSL_CERT_FILE` / `SSL_CERT_DIR` (`_config.py:34-37`) — verified by pointing `SSL_CERT_FILE` at a bogus file and getting an `ssl` error at construction.

**Result: env *proxies* are ignored, env *CA files* are honored.** For an app with its own explicit proxy setting this is arguably the right call, but it is accidental rather than deliberate — nothing in the code says so.

### 2.5 The `user-scanner` global-state interaction — the app's client is **not** independent

`user_scanner/core/email_orchestrator.py:23-52` **monkey-patches `httpx.AsyncClient.__init__` and `httpx.Client.__init__` process-wide at import time** (async patch at `:27-37`, sync patch at `:39-49`, both installed at `:51-52`):

```python
_original_async_client_init = httpx.AsyncClient.__init__

def _patched_async_client_init(self, *args, **kwargs):
    if "proxy" not in kwargs and "proxies" not in kwargs:
        proxy = get_proxy()
        if proxy:
            kwargs["proxy"] = proxy
    global_timeout = get_global_timeout()
    if global_timeout is not None:
        kwargs["timeout"] = global_timeout
    _original_async_client_init(self, *args, **kwargs)

httpx.AsyncClient.__init__ = _patched_async_client_init   # :51
httpx.Client.__init__ = _patched_client_init              # :52
```

`email_orchestrator` is imported at module scope by `user_scanner/core/cross_scan.py:26`, and the app imports `cross_scan` (lazily, inside functions) at `src/services/sherlock_service.py:223`, `src/services/email_service.py:368`, and `src/services/user_scanner_compat.py:401`.

Runtime-verified that the patch really does land in the app's process:

```
BEFORE import: AsyncClient.__init__ is httpx._client AsyncClient.__init__
AFTER  import: AsyncClient.__init__ is user_scanner.core.email_orchestrator _patched_async_client_init
```

And the app's own client is affected — measured against the real `src/` modules:

```
[app proxy EMPTY, user_scanner proxy SET]  timeout=Timeout(timeout=15.0)  effective pool=AsyncHTTPProxy
[app proxy SET]                            timeout=Timeout(timeout=15.0)  effective pool=AsyncHTTPProxy  _retries=0
[app proxy socks5://]                      timeout=Timeout(timeout=15.0)  effective pool=AsyncSOCKSProxy _retries=0
```

**The app's carefully-specified `Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)` is replaced by `Timeout(timeout=15.0)`, and the app's "direct" transport is bypassed in favour of user-scanner's proxy.** See B1/B2.

---

## 3) Bugs & hallucinations

**No API hallucinations.** Every httpx symbol/parameter the app uses exists in 0.28.1 with a compatible signature; `ruff` is clean. All defects below are logic/wiring bugs.

### B1 — CRITICAL: the app's `Timeout` is silently destroyed by user-scanner's global monkeypatch

`src/services/http_client.py:54` (app intent) vs. `user_scanner/core/email_orchestrator.py:33-35` (actual).

`set_global_timeout()` is called by the app at `src/services/sherlock_service.py:101-103` (every `load_sites()`) and `src/services/email_service.py:255-258`. The patch then **unconditionally overwrites** `kwargs["timeout"]`:

```python
global_timeout = get_global_timeout()
if global_timeout is not None:
    kwargs["timeout"] = global_timeout     # ← overwrites the app's explicit Timeout
```

Runtime-verified: `httpx.AsyncClient(timeout=Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0))` → `client.timeout == Timeout(timeout=15.0)` once `set_global_timeout(15.0)` has run. Passing `timeout=` explicitly does **not** defeat the patch (verified).

**Impact:** the app's per-phase budget is replaced by a flat `state.timeout` on all four phases. The `pool=5.0` cap becomes `pool=15.0` (3× the wait before `PoolTimeout`) and `connect=5.0` becomes `15.0` (3× the hang before `ConnectTimeout`). For the avatar download — the one place the app streams a remote body — a 15 s connect on a dead CDN is a 3× slowdown vs. the intended 5 s.

**Trigger:** requires `cross_scan` to have been imported (cross-scan enabled in Settings, or an email scan reaching `email_service.py:368`) *and* a subsequent client rebuild (proxy or retries changed) *and* `set_global_timeout` already called (always true after the first `load_sites()`).

### B2 — CRITICAL: the app's "direct" transport is bypassed — app traffic is silently routed through user-scanner's proxy

`src/services/http_client.py:63-77` (app) vs. `user_scanner/core/email_orchestrator.py:28-31` (actual).

The app never passes `proxy=` to `httpx.AsyncClient`. So when the patch finds a proxy it injects one, and httpx builds `_mounts = {"all://": <internal proxy transport>}` — which takes precedence over `self._transport`. The app's "direct" transport becomes unreachable.

Runtime-verified with the app's real modules:

```
--- CASE A: app proxy EMPTY, user_scanner proxy SET ---
mounts={'all://': 'AsyncHTTPTransport'}
effective pool=AsyncHTTPProxy        ← NOT the app's direct pool
```

**Concrete user-visible failure:**
1. User sets proxy `http://p:8080` → `state.proxy_url` set.
2. User runs a username scan → `src/services/user_scanner_compat.py:130-135` calls `set_proxy_manager(proxies=[proxy])`. The manager is **never reset to `None`** afterwards (`set_proxy_manager` is only ever called `if proxy:`), so `get_proxy()` keeps returning that proxy forever.
3. Cross-scan runs → `user_scanner.core.cross_scan` is imported → the patch is installed process-wide.
4. User **clears** the proxy in Settings → `state.proxy_url = ""` → `get_client()` rebuilds → the patch injects the *stale* manager proxy → the app's avatar downloads and update check now go through the proxy the user just removed.

The reverse direction is benign (the app's explicit `mounts` win when both are set).

### B3 — HIGH: the comment at `http_client.py:55-57` is factually wrong, and the "fix" it describes does not work

```python
# NOTE: do NOT wire as transport=+proxy= combo — when transport= is
# given, httpx builds proxy mounts internally WITHOUT retries, so the
# proxy leg would silently lose retry behavior. Both legs explicit.
```

- The first half is **correct**: `_init_proxy_transport` (`_client.py:1454-1472`) has no `retries` parameter.
- The second half is **wrong**: building the proxy transport yourself with `retries=` does **not** help, because `httpx/_transports/default.py:312-329` and `:331-350` never forward `retries` to `httpcore.AsyncHTTPProxy` / `AsyncSOCKSProxy`. Runtime-verified: `AsyncHTTPTransport(retries=3, proxy='http://…')._pool._retries == 0`.
- Therefore the app's "Both legs explicit" pattern (`http_client.py:60-62`) is a **no-op for the proxy leg**, and the comment will keep a future maintainer from finding the real problem.

`docs/reference/dep-httpx.md:170` and `:179` repeat the same false claim ("forwarded to … `httpcore.HTTPProxy(retries=retries)`" and "developers must explicitly pass `mounts={"all://": AsyncHTTPTransport(retries=retries, proxy=proxy, …)}`") — the background doc is wrong here and must not be trusted.

### B4 — MEDIUM: the `retries` setting is a no-op for the proxy leg, full stop

`_get_retries()` (`http_client.py:28-35`) reads `state.retries` (UI-wired at `src/main.py:800` and `src/screens/settings_screen.py:593`) and feeds it into both transports. Measured outcome:

| Leg | `_retries` on the pool |
|---|---|
| direct (`http_client.py:58`) | ✅ the requested value (e.g. 3) |
| proxy (`http_client.py:60-62`) | ❌ **always 0** |

So the "Retries" slider is real for direct connections and **completely inert** whenever a proxy is configured — the exact case where retries matter most. There is no httpx API to fix this; it needs an app-level retry loop.

### B5 — LOW: `limits=limits` on the client is inert, and the two branches are asymmetric

`http_client.py:75` passes `limits=limits` to `httpx.AsyncClient`, but:
- `httpx.AsyncClient` has **no `limits` attribute** (runtime: `AttributeError: 'AsyncClient' object has no attribute 'limits'`) — `limits` is consumed only by `_init_transport` (`_client.py:1432-1440`), which returns the supplied transport immediately without looking at it.
- The proxy branch (`:63-69`) does not pass `limits=` to the client at all.

Harmless, but misleading — the real limits live on the transport, and a reader could believe the client-level `limits` is doing something.

### B6 — LOW: the client is not closed on `page.on_disconnect`

`src/main.py:2415-2418` — `_on_disconnect` only flushes storage; it does not call `close_client()`. On Android, `on_disconnect` fires when the app is backgrounded, and `on_close` may never run. The connection pool then survives until GC. Small, but it is the more common mobile path.

### B7 — LOW: `get_client()` has a use-after-close race

`http_client.py:38-85` returns a cached client; `_drain` (`:88-97`) closes the previous one on the *next* event-loop tick. A caller that obtained the client and then awaits before sending (`cache_service.py:280`) can have that client closed underneath it → `RuntimeError: Cannot send a request, as the client has been closed.` There is no lock around the get/rebuild sequence either.

### B8 — INFO: `except TypeError, ValueError:` requires Python ≥ 3.14

`http_client.py:33` uses PEP 758 syntax (unparenthesized multi-exception `except`). It parses on the project's 3.14 floor (`pyproject.toml:8` `requires-python = ">=3.14"`, `.python-version` → `3.14`) and `ruff` accepts it — but it is a portability landmine if the floor is ever lowered, and it is stylistically surprising in a codebase that otherwise uses parenthesised tuples.

### B9 — INFO: an orphaned internal proxy transport is created and never closed

When the monkeypatch injects `proxy=` **and** the app also supplies `mounts=`, httpx builds the internal proxy transport (`_client.py:1412-1425`) and then **overwrites** that dict entry with the app's mount (`:1426-1429`). The internal `AsyncHTTPTransport` (and its `httpcore` pool) is dropped without ever being closed. In practice harmless — it never opened a socket — but it is a leaked object per rebuild.

### B10 — INFO: `trust_env` half-state

See §2.4: env proxies are ignored (because `transport=` is supplied) while env CA files are honored (because the transport's own `trust_env=True`). Nothing in the code documents the intent.

---

## 4) Should app-level httpx stay?

### 4.1 It is **not** dead weight, and it does **not** have to contradict user-scanner

- **user-scanner's client is a *sync* `httpx.Client` cache** (`user_scanner/core/orchestrator.py:267-276`) built for its own site-check fan-out. It cannot serve the app's two needs: an **async** avatar stream (`cache_service.py:280`) and an **async** update fetch (`update_service.py:74`).
- The engines build their clients internally and expose **no injection point** — the app cannot hand its `AsyncClient` to `orchestrator.make_request`.
- The app's client is **not** a duplicate of the engine's client; it is the only async client in the process that the app owns.
- It is **live code**: two real call sites plus the shutdown hook.

**Conclusion: keep the module.** It earns its place.

### 4.2 But its current implementation is over-engineered for two call sites, and it is *corrupted* by user-scanner's global state

The "rebuild on every settings change" machinery, the drain task, the three-state cache — all of that exists to serve a `retries` knob that (a) is a no-op on the proxy leg and (b) has been silently overridden by the monkeypatch anyway. The complexity buys nothing and actively hides B1/B2.

### 4.3 Concrete improvements (all validated against the installed venv)

**Fix 1 — neutralise the monkeypatch (fixes B1 + B2, two lines).** The patch only injects `proxy` when the kwarg is *absent*, and it overwrites `timeout` in the constructor. So:

```python
_client = httpx.AsyncClient(
    proxy=None,                 # ← defeats the patch's proxy injection
    transport=direct,
    mounts=... ,
    timeout=timeout,
    http2=True,
    follow_redirects=True,
)
_client.timeout = timeout      # ← restore the app's own Timeout after construction
```

Runtime-verified: with `proxy=None` passed explicitly, `mounts` stays `{}` and the effective pool is the app's `AsyncConnectionPool` (not `AsyncHTTPProxy`); and `client.timeout = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)` sticks (`BaseClient.timeout` is a plain settable attribute). Passing `timeout=` in the constructor does **not** work — only the post-construction assignment does.

**Fix 2 — delete the wrong comment (`:55-57`) and stop pretending the proxy leg has retries.** Replace it with the truth: *httpx 0.28.1 cannot express connection retries for a proxied leg* (`_transports/default.py:312-329`, `:331-350`). If retries on the proxy leg are wanted, implement them in the app (a small retry loop around the request, catching `httpx.ConnectError`/`httpx.ConnectTimeout`) — that is also the only way to retry on *read* timeouts, which httpcore never retries.

**Fix 3 — drop `retries` from the client cache key** once Fix 2 lands, or keep it and accept that it only affects the direct leg. Also consider capping it lower: httpcore's retries are **connect-only** (`httpcore/_async/connection.py:110-165`), so `state.retries=3` buys nothing for a server that accepts the TCP connection and then stalls.

**Fix 4 — remove the inert `limits=limits` on the client (`:75`)** or make both branches symmetric; the effective limits are on the transport either way.

**Fix 5 — close the client on `page.on_disconnect` as well as `page.on_close`** (`src/main.py:2415-2418`), and make `close_client()` idempotent-safe (it already is — `httpx/_client.py:1982-1988`).

**Fix 6 — make `get_client()` race-free**: hold an `asyncio.Lock` around the get/rebuild sequence, and/or return the client *and* perform the request under the same lock so a rebuild cannot close a client mid-flight.

**Fix 7 — decide `trust_env` explicitly**: pass `trust_env=False` to the transport to make the intent obvious (the app has its own proxy setting; env proxies are already ignored by `transport=`; env CA files being honored is an accident worth removing on mobile).

**Fix 8 — consider `httpx[brotli]`.** Brotli is the one missing extra with a real payoff here: the app's only high-volume HTTP is avatar images, and Brotli typically cuts PNG/JPEG-on-the-wire size by 15-25 %. httpx already advertises only what it can decode, so adding the extra is a one-line `pyproject.toml` change plus `uv sync` — **no code change**. (`httpx[zstd]` is not worth it: the CDNs the app hits rarely offer it, and `zstandard` is a compiled wheel that hurts the Android/iOS story the V2 doc cared about.)

### 4.4 Unused httpx surface worth considering (installed, available, unused by the app)

| Capability | Where it lives | Proposal |
|---|---|---|
| `httpx.MockTransport` | `_transports/mock.py:15` | The app has **zero** network-mocking. `tests/` could use `MockTransport` to assert the update-service and avatar-cache paths (status handling, oversize rejection, the 5 MB cap) without touching the network. Today `tests/test_services.py` cannot test `update_service.py` at all. |
| `httpx.Auth` / `DigestAuth` / `NetRCAuth` | `_auth.py:22/145/175` | The update feed (`UPDATE_CONFIG_URL`) is a public GitHub raw file. If the owner ever moves it behind a private repo or a token, `auth=` is the clean hook. `NetRCAuth` would also let a desktop user drop `~/.netrc` credentials in. Low priority. |
| `httpx.Cookies` | `_models.py:1079` | The app has no session-bearing HTTP call today (avatars and a JSON feed are stateless). Worth keeping in mind if the app ever talks to an authenticated API. |
| `httpx.event_hooks` | `_client.py:1353` (param) | The app has a `state.log_engine_logs` troubleshooting toggle and silences `httpx` at WARNING (`src/core/logger_handler.py:65-73`). An `event_hooks={"request": …}` hook on the shared client would let the app log *its own* request/response pairs at DEBUG without touching the global logger filter — currently the app's two HTTP calls are completely invisible. |
| `httpx.AsyncClient(base_url=…)` | `_client.py:1353` (param) | Cosmetic; `update_service` has a single absolute URL. |
| `httpx-sse` | **not installed** | If the owner ever wants live server-pushed scan progress, `httpx-sse` is the missing package. Out of scope today. |

---

## 5) Verdict

**ISSUES FOUND.**

**No hallucinations, no version drift, no import errors, no missing timeouts, no sync/async mixing, and a correct client lifecycle.** Every httpx symbol the app uses exists in 0.28.1 with a compatible signature, `ruff` is clean, `page.on_close` is a real flet 1.0.4 event, the rebuild-on-settings-change logic works, `aclose` is idempotent, and the engines' sync client is correctly offloaded to an executor so it never blocks the event loop. On the httpx API surface the app is **correct**.

**But two of the three headline behaviours the module claims to deliver are not delivered in practice:**

1. **The app's `Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)` is silently replaced by a flat `Timeout(timeout=15.0)`** by user-scanner's process-wide `httpx.AsyncClient.__init__` monkeypatch (B1) — the patch is installed the moment `user_scanner.core.cross_scan` is imported, and the app imports it lazily from three call sites.
2. **The app's "direct" transport is bypassed and its traffic re-routed through user-scanner's proxy manager** when the app's own proxy is empty but the engine's manager still holds a stale proxy (B2) — i.e. the user clears the proxy in Settings and the app keeps using it.
3. **The `retries` slider is inert on the proxy leg** because httpx 0.28.1 never forwards `retries` to `httpcore.AsyncHTTPProxy`/`AsyncSOCKSProxy` (B3/B4) — and the code comment at `http_client.py:55-57`, plus the V2 background doc at `docs/reference/dep-httpx.md:170,179`, both assert the opposite. The background doc is wrong and must not be relied on.

**Secondary findings:** inert `limits=` on the client (B5), no close on `on_disconnect` (B6), a use-after-close race in `get_client()` (B7), PEP 758 syntax (B8), an orphaned internal proxy transport (B9), and an accidental `trust_env` half-state (B10).

**On the V3 simplification question:** the app-level httpx client **should stay** — user-scanner's client is a *sync* `httpx.Client` cache for site checks and cannot serve the app's two async needs (avatar streaming, update fetch), and the engines expose no injection point. The module is neither dead weight nor a duplicate. What should go is the *complexity* around it: the rebuild machinery, the retries key, and the incorrect comment. The two-line monkeypatch neutralisation (`proxy=None` in the constructor + `client.timeout = timeout` after construction) plus an honest comment about httpx's proxy-retry limitation fixes the two critical bugs outright.

---

*No files were modified during this audit. All findings were reproduced by executing the installed venv (`httpx` 0.28.1 / `httpcore` 1.0.9 / CPython 3.14.7) against the app's real modules in `src/`, and confirmed against the installed sources cited above.*
