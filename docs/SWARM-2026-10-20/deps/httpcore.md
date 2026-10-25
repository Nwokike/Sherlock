# httpcore 1.0.9 — Dependency Report (synthesized)

> `httpcore` was studied inside the httpx audit task (see `httpx.md` §1) because
> the app only reaches it through `httpx`'s API. This file preserves the
> one-report-per-package invariant; the full verification detail lives in
> `httpx.md`. Facts below are from the installed venv
> `.venv/Lib/site-packages/httpcore` (source of truth).

## Installed verification
- `httpcore` **1.0.9** (`uv.lock:186-192`; `httpcore-1.0.9.dist-info`).
- Dependencies (verified from METADATA): `certifi`, `h11`; SOCKS support is an
  optional extra (`socksio`), which `uv.lock` does **not** pull for httpcore
  directly — `socksio` enters only via `user-scanner`'s own
  `Requires-Dist: socksio>=1.0,<2` (`user_scanner-1.5.2.3.dist-info/METADATA:11`).
- AnyIO is **not** a dependency of httpcore 1.0.9 (the V2-era anyio doc's claim
  "via httpx **and** httpcore" is stale; corrected by the anyio agent:
  `uv.lock:203` is the single `{ name = "anyio" }` reference, under httpx).

## Consumers in this venv
- `httpx` only — `httpx/_transports/default.py` constructs
  `httpcore.ConnectionPool` / `AsyncConnectionPool` / `HTTPProxy` /
  `SOCKSProxy`.
- App: `src/services/http_client.py:17` imports httpx; the app never imports
  httpcore directly. Engines: `user_scanner/core/orchestrator.py` get_client
  builds `httpx.Client` (sync) — httpcore is always one layer below.

## Correctness findings carried over from httpx.md (verified there)
- httpx 0.28.1 never forwards `retries` to the proxy transports
  (`AsyncHTTPProxy` / `AsyncSOCKSProxy` are built with default retries=0 in
  `httpx/_client.py` `_init_proxy_transport`) — so the app's "retries" slider
  is inert on the proxy leg.
- `AsyncSOCKSProxy` exists and imports cleanly with socksio installed; SOCKS4/4A
  are unreachable through httpx (schemes limited to socks5/socks5h).
- httpcore's pool limits and the app's `Limits(...)` are effectively inert on
  the engine path because user-scanner builds its own clients.

## Verdict
PERFECT as a transitive dependency; **N/A for direct app use** — zero direct
imports in `src/` and no reason to import it. No action.
