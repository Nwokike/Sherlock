# Audit — `src/services/http_client.py`

**File:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/services/http_client.py` (112 lines)
**Audited against (installed deps = truth):** `httpx 0.28.1`, `httpcore 1.0.9`, `h2 4.4.1`, `socksio 1.0.0` (`.venv/Lib/site-packages`), `user-scanner 1.5.2.3` (`.venv/Lib/site-packages/user_scanner`), CPython 3.14.7.
**Scope:** this file only. Call sites cited for context only.

---

## 1) File role

The app's single pooled `httpx.AsyncClient` for non-scan HTTP: proxy-aware, rebuilt when `core.state.proxy_url` / `core.state.retries` change, closed on app shutdown.

| Member | Lines | Role |
|---|---|---|
| `_client` / `_client_proxy` / `_client_retries` | `http_client.py:23-25` | Module-global singleton + the two "did settings change?" fingerprints. |
| `_get_retries()` | `http_client.py:28-35` | Reads `state.retries`, coerces to int, clamps to `0..3`. |
| `get_client()` | `http_client.py:38-85` | Returns the shared client; rebuilds it when proxy/retries changed. |
| `_drain(old)` | `http_client.py:88-97` | Fire-and-forget close of a replaced client. |
| `_aclose(client)` | `http_client.py:100-104` | `await client.aclose()` wrapped in a WARNING log. |
| `close_client()` | `http_client.py:107-112` | Async teardown; wired to `page.on_close` at `src/main.py:2434-2437`. |

**Real consumers (exactly two):**
- `src/services/cache_service.py:278-281` — avatar download, `async with get_client().stream("GET", url, ...)`, 5 MB cap. **No per-request timeout** → inherits the client timeout.
- `src/services/update_service.py:72-74` — update check, `await get_client().get(self.config_url, timeout=4.0)`. Per-request timeout → survives any client-level timeout override.

Nothing else in `src/` or `tests/` imports this module. The engine (`user-scanner`) has its own sync client cache and is untouched by this module.

**Module necessity verdict: KEEP.** Two consumers, both want a pooled + proxy-aware client, and `update_service`'s 4 s fast-fail plus `cache_service`'s 5 MB stream cap are real semantics worth preserving. The module's *complexity*, not its existence, is the problem (§5).

---

## 2) API verification summary

**No hallucinated APIs.** Every symbol and keyword used at `http_client.py:49-77` exists in installed `httpx 0.28.1` with the exact name used.

| Usage | Installed truth (`httpx 0.28.1`) | Verdict |
|---|---|---|
| `httpx.Limits(max_connections=, max_keepalive_connections=, keepalive_expiry=)` — `:49-53` | `httpx/_config.py` `Limits` — all three field names exist | ✅ correct |
| `httpx.Timeout(connect=, read=, write=, pool=)` — `:54` | `httpx/_config.py` `Timeout` — exactly these 4 fields; `Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)` constructs cleanly | ✅ correct |
| `httpx.AsyncHTTPTransport(retries=, limits=, http2=, proxy=)` — `:58`, `:60-62` | `httpx/_transports/default.py` signature: `verify, cert, trust_env, http1, http2, limits, proxy, uds, local_address, retries, socket_options` | ✅ names correct — ⚠️ **`retries` is silently dropped when `proxy=` is set** (see BUG-3) |
| `httpx.AsyncClient(transport=, mounts=, timeout=, http2=, limits=, follow_redirects=)` — `:63-69`, `:71-77` | `httpx/_client.py` `AsyncClient.__init__` — all present, all kw-only | ✅ names correct — ⚠️ **client-level `limits=`/`http2=` are inert when `transport=` is supplied** (see NEW-1) |
| `client.timeout`, `client._transport`, `client._mounts` — used in probes | plain attributes / `_init_transport` / `_mounts` dict | ✅ |
| `asyncio.get_running_loop()` — `:91` | stdlib | ✅ |
| `except TypeError, ValueError:` — `:33` | **PEP 758** (unparenthesized except tuples), CPython **3.14+** only | ✅ **not a bug** — venv is 3.14.7, `pyproject.toml` `requires-python = ">=3.14"`, `.python-version` = `3.14`; the file compiles (`py_compile` OK) and the style is used consistently elsewhere (`src/main.py:664,702,719`, `src/core/actions.py:26`, `src/components/update_dialog.py:228`) |
| `http2=True` — `:58,62,67,73` | requires the `h2` package (`httpx/_client.py` raises `ImportError` if missing) | ✅ **safe today** — `h2 4.4.1` is installed transitively via `user-scanner` → `httpx[http2]` and `phonsint` → `httpx[http2]` (both hard deps in `pyproject.toml`); `socksio 1.0.0` likewise via `user-scanner` |
| `socks5://` support — `:61` | `httpx/_transports/default.py` handles `socks5`/`socks5h`; requires `socksio` | ✅ installed |

### Live timeout evidence (the decisive probe)

Probe: import `user_scanner.core.cross_scan` (installs the engine monkeypatch), import `services.http_client`, call `get_client()`, print `client.timeout`.

| Scenario | `client.timeout` |
|---|---|
| Monkeypatch active, `get_global_timeout() is None`, no engine proxy manager | `Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)` ✅ |
| After `helpers.set_global_timeout(15.0)` | **`Timeout(timeout=15.0)`** ← the app's 4-field timeout is gone |

The second row is not hypothetical: the app itself calls `set_global_timeout` — `src/services/sherlock_service.py:101-103` (`set_global_timeout(float(state.timeout))`, and `state.timeout: int = 15` at `src/core/state.py:98`) on **every** `load_sites()` call, i.e. every username scan; `src/services/email_service.py:255-256` does the same with the email timeout. The monkeypatch is installed by `user_scanner/core/email_orchestrator.py:26-52` the first time `user_scanner.core.cross_scan` is imported — which the app does lazily at `src/services/user_scanner_compat.py:401` (cross-scan) and `src/services/sherlock_service.py:223`. **After the first cross-scan the process is permanently patched.**

---

## 3) Confirmed known bugs

### BUG-1 — The app's 4-field timeout is silently replaced by a flat one ✅ CONFIRMED
`http_client.py:54` builds `httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)`; the engine's process-wide monkeypatch (`user_scanner/core/email_orchestrator.py:26-36`) does `kwargs["timeout"] = global_timeout` **unconditionally**, overriding the kwarg the app just passed. Live probe output: `after ctor : Timeout(timeout=15.0)`.

Consequences: `connect` becomes 15 s instead of 5 s, `pool` becomes 15 s instead of 5 s (a request waiting for a free connection can stall 15 s), and the write/read split is lost. The override is applied **at construction time only**, so the damage lands on the *next rebuild* (proxy change in Settings → `src/screens/settings_screen.py:482` sets `state.proxy_url` → next `get_client()` rebuilds → new client gets `Timeout(timeout=15.0)`). `update_service.py:74` is immune (per-request `timeout=4.0` wins); `cache_service.py:280` is **not** (no per-request timeout).

### BUG-2 — Traffic re-routes through the engine's proxy when the app's proxy is empty ✅ CONFIRMED
`http_client.py:71-77` (the no-app-proxy branch) constructs `httpx.AsyncClient(transport=direct, ...)` and passes **no `proxy=` kwarg** → the monkeypatch's `if "proxy" not in kwargs` fires and injects the engine's proxy (`user_scanner/core/email_orchestrator.py:28-31` → `helpers.get_proxy()` → `_proxy_manager.get_next_proxy()`).

Live probe (engine proxy manager holding `http://127.0.0.1:9999`, app proxy empty):
```
mounts = {'all://': 'AsyncHTTPTransport'}
   pool: AsyncHTTPProxy | _retries: 0
```
All app traffic — including the GitHub update check and third-party avatar CDNs — is silently pushed through the engine's rotating proxy list. In the app-proxy branch (`:63-69`) the app's own `mounts={"all://": proxy_transport}` *does* win (probe: proxy `127.0.0.1:8888` = the app's), so the bug bites exactly in the case where the user asked for **no** proxy.

### BUG-3 — `retries` is inert on the proxy leg; the comment asserts the opposite ✅ CONFIRMED (worse than reported)
`http_client.py:55-57` claims: *"when transport= is given, httpx builds proxy mounts internally WITHOUT retries, so the proxy leg would silently lose retry behavior. Both legs explicit."* The comment is inverted — the app's *own* explicit proxy transport loses retries too. `httpx/_transports/default.py` builds `httpcore.AsyncHTTPProxy(...)` / `AsyncSOCKSProxy(...)` **without** a `retries=` kwarg (only the `proxy is None` branch forwards `retries=retries` to `AsyncConnectionPool`).

Direct proof (same `retries=3` on all three transports):
```
direct       pool=AsyncConnectionPool  _retries=3
http-proxy   pool=AsyncHTTPProxy       _retries=0
socks-proxy  pool=AsyncSOCKSProxy      _retries=0
```
Net effect: **whenever a proxy is configured, the retries slider does nothing at all** — `http_client.py:61` passes `retries=retries`, httpx accepts it, and it is dropped. And in the proxy branch the *direct* transport that carries the only surviving `retries` (`http_client.py:58`) is unreachable (see NEW-7). httpcore itself *does* honour retries on proxy pools (`httpcore/_async/http_proxy.py` forwards `retries` to `super().__init__`; `httpcore/_async/connection_pool.py:109` stores `self._retries`; `httpcore/_async/connection.py:110` uses it) — httpx is the layer that loses it.

### BUG-4 — Dead client-level `limits=` (and `http2=`) ✅ CONFIRMED
`http_client.py:75` passes `limits=limits` to `httpx.AsyncClient` **while also** passing `transport=direct` (`:72`). `httpx/_client.py` `AsyncClient._init_transport` is literally `if transport is not None: return transport` — the client-level `limits`, `http2`, `verify`, `cert` are all discarded. The same applies to `http2=True` at `:67` and `:73` (it survives only as an `import h2` availability gate). Behaviourally harmless (the transports carry the same limits), but it is a second, competing source of truth for the same knobs.

### BUG-4b — `trust_env` half-state ✅ CONFIRMED
`httpx/_client.py`: `allow_env_proxies = trust_env and transport is None`. Because both branches pass `transport=`, `allow_env_proxies` is **always False** → `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` env vars are ignored by this client, while `trust_env` remains `True` on both the client and the transports (so `SSL_CERT_FILE`/`SSL_CERT_DIR` *are* honoured). The module never states which half it wants, and the docstring at `:5-7` ("socks5/http proxies apply to every httpx path") reads as if env proxies were included.

### BUG-4c — Orphaned internal proxy transport ✅ CONFIRMED
When the monkeypatch injects `proxy=` **and** the app passes `mounts=`, httpx builds a proxy transport in `_init_proxy_transport(...)`, then `self._mounts.update(mounts)` **replaces** that entry (probe D: the surviving mount pointed at the app's `8888`). The discarded transport is in neither `client._transport` nor `client._mounts`, so `AsyncClient.aclose()` (which closes only `self._transport` + `self._mounts.values()`) never closes it. Every rebuild while the engine holds a proxy creates one more orphaned `httpcore.AsyncHTTPProxy` pool. Triggered directly by this module's choice to pass both `transport=` and `mounts=`.

### BUG-4d — No close on `on_disconnect` ✅ CONFIRMED (wiring level)
`close_client()` (`http_client.py:107-112`) is wired only to `page.on_close` (`src/main.py:2434-2437`). `page.on_disconnect` (`src/main.py:2413-2417`) flushes storage only — a disconnect without a close (web reload, mobile background kill) leaves the pooled client and its keepalive sockets open for the life of the process.

---

## 4) NEW bugs

### NEW-1 — Use-after-close race on every rebuild (highest real-world risk)
`http_client.py:47-48` calls `_drain(_client)` → `:97` `spawn(_aclose(old))` → `old.aclose()` closes the httpcore pool **while in-flight requests still hold the old client**. The app's avatar download (`src/services/cache_service.py:278-281`) is a long-lived `async with ... .stream(...)`; if the user changes the proxy in Settings (`src/screens/settings_screen.py:482`) mid-download, the pending read dies with `httpx.ReadError`/`RemoteProtocolError` and the avatar is silently skipped (the UI falls back to the remote URL). Same hazard in `close_client()` (`:110-112`) at shutdown. httpx's own guard (`AsyncClient._state == CLOSED` → "Cannot send a request, as the client has been closed") protects *new* requests, not in-flight ones.

### NEW-2 — `_drain` leaks the old client when there is no running loop
`http_client.py:90-96`: with no running loop the function logs a WARNING and **returns without closing**. The message says "relying on GC", but neither `httpx.AsyncClient` nor `httpcore` pools have a finalizer that closes sockets — the keepalive connections are reaped by the OS only when the process exits. The module docstring's promise (`:9`) *"No silent failures: swap/close problems are logged at WARNING"* is technically true but misleading: the resource really is leaked. Today `get_client()` is only called from the Flet event loop, so this path is latent.

### NEW-3 — Cross-loop close hazard
`_drain` binds the close task to **whatever loop is running in the calling thread** (`core/tasks.py:19` → `asyncio.create_task`). If `get_client()` is ever called from a worker thread (`src/services/sherlock_service.py:12` uses `threading`), the old client — whose connections belong to the main loop — is closed from the wrong loop → `RuntimeError` swallowed into the WARNING at `:104`. Latent today (both consumers run on the event loop: `src/main.py:1245,1633` via `spawn`, `src/main.py:2300` via `page.run_task`), but the module has no thread-affinity contract.

### NEW-4 — `get_client()` mutates globals with no lock
`http_client.py:40,78-79`: the "is the cached client still current?" check (`:45`) and the assignment (`:78`) are not atomic. Two threads can both pass `:45`, both build a client, and one built client is dropped **without ever being closed** (another pool leak), with both callers receiving different clients. Latent (single-loop today) but undocumented.

### NEW-5 — The `retries` setting's contract does not match httpx's `retries`
httpcore's `retries` means *"The maximum number of retries when trying to establish a connection"* (`httpcore/_async/connection_pool.py:96-108`) — **connect** failures only. The UI promise is *"Number of retries when a network request drops or times out"* (`src/screens/settings_screen.py:904`). Read timeouts and mid-stream drops are **not** retried. `http_client.py:28-35` / `:58,61` faithfully plumb a knob whose stated semantics are wrong.

### NEW-6 — Silent clamp of the retries value
`http_client.py:35` `max(0, min(3, retries))` silently caps any value above 3 and any negative value, with no log. Nothing in the file documents the 0..3 ceiling.

### NEW-7 — The `direct` transport is dead weight in the proxy branch
`http_client.py:58` + `:64`: with `mounts={"all://": proxy_transport}` every http/https request is intercepted by the mount, so `client._transport` (the `AsyncConnectionPool` at `direct`) is **unreachable** — probe output: `client._transport pool: AsyncConnectionPool`. It allocates a second connection pool, is closed by `aclose()`, and holds the only copy of the working `retries` setting. The two branches at `:59-69` and `:70-77` should be one code path.

### NEW-8 — Stale/incorrect docstring claims
- `:5-7` *"proxy is read live from core.state on access, so socks5/http proxies apply to every httpx path"* — false twice once the monkeypatch is live (BUG-2: the engine's proxy overrides "no proxy"; BUG-4b: OS/env proxies are *not* applied), and it is only ever true for the app's two consumers.
- `:3` *"Replaces throwaway per-call clients (update check, avatar downloads)"* — accurate.
- `:9` *"No silent failures"* — overstated (NEW-2).
- `:55-57` — factually inverted (BUG-3).

### NEW-9 — `close_client()` does not cancel/await a pending `_drain` task
`http_client.py:107-112`: a drain task spawned earlier may still be pending when `close_client()` runs. Double-close is harmless (httpx guards with `ClientState.CLOSED`), but the task is untracked, so at interpreter shutdown it can be cancelled mid-`aclose()` and produce a spurious WARNING from `core/tasks.py:30`.

### NEW-10 — Dead `_drain` name
`_drain` (`:88`) closes; it does not drain. Cosmetic, but the name misleads the next maintainer about the in-flight-request semantics that are actually broken (NEW-1).

---

## 5) Minimal simplification + correct fixes

### 5a. Collapse the two build branches into one (removes NEW-7, BUG-4, BUG-4b, BUG-4c at once)

`httpx.AsyncHTTPTransport(proxy=None)` *is* the direct transport, so the `direct`/mounts duality is unnecessary. Replace `http_client.py:49-77` with:

```python
def _build(proxy: str | None, retries: int) -> httpx.AsyncClient:
    limits = httpx.Limits(
        max_connections=20,
        max_keepalive_connections=10,
        keepalive_expiry=30.0,
    )
    timeout = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)

    if proxy:
        transport = httpx.AsyncHTTPTransport(limits=limits, http2=True, proxy=proxy)
        # httpx drops `retries` for proxy pools (only the direct branch forwards
        # it); httpcore DOES honour it -> restore it here (BUG-3).
        transport._pool._retries = retries
    else:
        transport = httpx.AsyncHTTPTransport(retries=retries, limits=limits, http2=True)

    client = httpx.AsyncClient(
        transport=transport,
        proxy=None,          # explicit: blocks user-scanner's __init__ monkeypatch
        timeout=timeout,
        follow_redirects=True,
        trust_env=False,     # env proxies are NOT honoured (transport= is supplied)
    )
    client.timeout = timeout   # re-assert: the monkeypatch overrides kwargs["timeout"]
    return client
```

Each line maps to a proven defect:
- `proxy=None` **explicitly passed to `AsyncClient`** → the monkeypatch's `if "proxy" not in kwargs` no longer fires → **BUG-2 fixed** (probe-verified: `mounts: {}`, engine proxy not injected).
- `client.timeout = timeout` after construction → **BUG-1 fixed** (probe-verified: `after reassert: Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)` and `build_request(...).extensions["timeout"] == {'connect': 5.0, 'read': 15.0, 'write': 10.0, 'pool': 5.0}`). `httpx.Client.timeout` is a plain assignable attribute; `build_request` reads it back.
- `transport._pool._retries = retries` → **BUG-3 fixed** on the proxy leg (httpcore honours `_retries`; verified in `httpcore/_async/connection_pool.py:109` and `connection.py:110`).
- No `mounts=`, no second `direct` transport, no client-level `limits=`/`http2=` → **BUG-4, BUG-4b, BUG-4c, NEW-7 removed**; the orphaned-transport path disappears because `proxy=` is never injected.
- `trust_env=False` documents the env-proxy half-state (no-op today because `transport=` is supplied, but it makes the intent explicit and survives httpx changes).

### 5b. Fix the use-after-close race (NEW-1)
Retire instead of immediately closing. Keep replaced clients in a list and close them when they are provably idle — or, simplest and safe, close them only at shutdown:

```python
_retiring: list[httpx.AsyncClient] = []      # new module global

# inside get_client(), replacing _drain(_client) at :47-48:
if _client is not None:
    _retiring.append(_client)     # in-flight requests keep working

# inside close_client(), replacing the single await at :110-112:
for old in [*_retiring, _client]:
    if old is not None:
        await _aclose(old)
_retiring.clear()
```
Number of rebuilds is bounded by user settings changes (a handful per session), so the deferred-close list stays tiny. If immediate reclamation is required, gate the close on the old client having no in-flight requests — httpx exposes no such counter, so the retired-list is the pragmatic answer.

### 5c. Make the engine interaction explicit instead of accidental (BUG-1, BUG-2 root cause)
The clean upstream fix is for `src/services/sherlock_service.py:101-103` and `src/services/email_service.py:255-256` to stop mutating a **process-global** timeout that every `httpx.AsyncClient` in the process reads. Until that lands, the two-line guard in 5a (`proxy=None` + `client.timeout = timeout`) is the local containment. Add a comment at `http_client.py:44` naming the engine monkeypatch, so the next reader knows why the re-assert exists.

### 5d. Document what `retries` actually does (NEW-5)
Either relabel the UI copy at `src/screens/settings_screen.py:904` to "connection retries (connect failures only)", or implement real request-level retry in this module (a small retry loop around `client.get` / the stream). Do not leave the two promises divergent.

### 5e. Small correctness/clarity items
- `http_client.py:88` — rename `_drain` → `_retire` (NEW-10).
- `http_client.py:90-96` — when there is no running loop, close synchronously if possible (`asyncio.run` is not safe here) or, at minimum, log at ERROR with "client not closed" wording instead of "relying on GC" (NEW-2).
- `http_client.py:35` — log the clamp when `retries` is out of range (NEW-6).
- `http_client.py:1-10` — rewrite the docstring: drop the "applies to every httpx path" claim, state that env proxies are ignored, and state that the engine monkeypatch is counteracted (NEW-8).
- `http_client.py:55-57` — **delete** the comment; it is inverted (BUG-3).

### 5f. Wiring (outside the file, flagged for the owning audit)
- `src/main.py:2413-2417` — call `close_client()` from `_on_disconnect` as well as `_on_close` (BUG-4d).

---

## 6) Verdict

**Keep the module; shrink it.** It is small (112 lines), has exactly two genuine consumers, and both want exactly what it offers (pooled + proxy-aware + swappable settings). But roughly half its lines encode assumptions that installed `httpx 0.28.1` does not honour, and the engine's process-wide `httpx.AsyncClient.__init__` monkeypatch takes over two of the three things the module exists to control.

| # | Finding | Severity | Status |
|---|---|---|---|
| BUG-1 | App timeout flattened to `Timeout(timeout=15.0)` by the engine monkeypatch | **High** | Confirmed by live probe |
| BUG-2 | Engine proxy silently applied when the app has no proxy | **High** | Confirmed by live probe |
| BUG-3 | `retries` dropped on every proxy transport; comment asserts the opposite | **High** | Confirmed (`_retries=0` vs `3`) |
| BUG-4 | Client-level `limits=` inert when `transport=` is supplied | Medium | Confirmed in `_init_transport` |
| BUG-4b | `trust_env` half-state; env proxies silently ignored | Low | Confirmed |
| BUG-4c | Orphaned proxy transport per rebuild, never closed | Low | Confirmed |
| BUG-4d | No `close_client()` on `on_disconnect` | Medium | Confirmed (wiring) |
| NEW-1 | Use-after-close race on rebuild / shutdown | **High** | Code-path proven |
| NEW-2 | `_drain` leaks the client when no loop is running | Medium | Code-path proven |
| NEW-3 | Cross-loop close hazard | Low | Latent |
| NEW-4 | Unsynchronised global mutation | Low | Latent |
| NEW-5 | `retries` semantics ≠ UI promise | Medium | Confirmed (httpcore docstring) |
| NEW-6 | Silent clamp, undocumented | Low | Confirmed |
| NEW-7 | Dead `direct` transport in the proxy branch | Medium | Confirmed by probe |
| NEW-8 | Stale/incorrect docstrings | Low | Confirmed |
| NEW-9 | Untracked drain task at shutdown | Low | Confirmed |
| NEW-10 | Misleading `_drain` name | Cosmetic | Confirmed |
| — | PEP 758 `except TypeError, ValueError:` (`:33`) | **None** | **Verified safe** (3.14+, project-wide style) |
| — | `http2=True` / socks5 support (`:58,61,62,67,73`) | **None** | **Verified safe** (`h2`/`socksio` present via `user-scanner`/`phonsint`) |

**Priority order:** NEW-1 → BUG-1 → BUG-2 → BUG-3 → NEW-7/BUG-4 → the rest.
**Estimated diff:** ~25 lines changed in `http_client.py` (one `_build()` helper, a retired-client list, three deleted comment/branch blocks) — a net *simplification* that simultaneously closes every High finding.
