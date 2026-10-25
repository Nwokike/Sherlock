# certifi — Dependency Audit (Sherlock-V3, 2026-10-20)

Scope: installed `certifi` in `Sherlock-V3/.venv` (the only source of truth). App never imports
`certifi` directly; it is transitive via `httpx` / `httpcore` / `curl_cffi`.

## 1) Installed verification

| Item | Value | Evidence |
|---|---|---|
| Version | `2026.10.18` | `certifi/__init__.py:4` → `__version__ = "2026.10.18"`; `certifi-2026.10.18.dist-info/METADATA:3` → `Version: 2026.10.18` |
| Location | `.venv/Lib/site-packages/certifi/` | `certifi-2026.10.18.dist-info/RECORD` lists `certifi/__init__.py`, `core.py`, `cacert.pem`, `py.typed`, `tests/` |
| cacert.pem | present, **234,072 bytes**, 3,855 lines, **117** `BEGIN CERTIFICATE` blocks | `certifi/cacert.pem`; `RECORD` line `certifi/cacert.pem,sha256=2HiHIAyacF3MyTe5uDteZ-RwJMSkt_ndFXAMcuD1VFM,234072` |
| API | `where()` → abs path to cacert.pem; `contents()` → PEM text; lazy + `atexit` cleanup | `certifi/core.py:19-49` (py≥3.11 `importlib.resources` path), `core.py:52-84` (<3.11 legacy) |
| Runtime check | `certifi.where()` = `…\.venv\Lib\site-packages\certifi\cacert.pem` (exists, 234072 B); `httpx` default ctx loads **117** CA certs | executed in the venv interpreter; `ssl.get_default_verify_paths().cafile` = **None** on this host |
| Packaging note | `cacert.pem` is package *data* inside the `certifi/` dir, not an external path — any whole-`site-packages` copy carries it | `RECORD` |

No app code imports `certifi` (`grep -rni certifi src/` → 0 hits).

## 2) Consumers in the venv (file:line)

- `httpx/_config.py:31` `import certifi` → `create_ssl_context()`:
  - `:33-35` `verify=True` + `trust_env` + `SSL_CERT_FILE` → `ssl.create_default_context(cafile=$SSL_CERT_FILE)`
  - `:36-37` else `SSL_CERT_DIR` → `capath=`
  - `:38-40` **default** → `ssl.create_default_context(cafile=certifi.where())`
  - `:41-44` `verify=False` → `CERT_NONE` (app never uses this)
  - `:45-54` `verify=<str|context>` deprecated paths
- `httpx/_transports/default.py:153` (sync) and `:297` (async) call `create_ssl_context(verify=verify, cert=cert, trust_env=trust_env)`; default `verify=True`, `trust_env=True` (`:138-140`, `:282-284`).
- `httpcore/_ssl.py:3,7-8` `default_ssl_context()` → `ssl.create_default_context()` + `context.load_verify_locations(certifi.where())`; used by the connection pools when no explicit `ssl_context` (`httpcore/_async/connection_pool.py:50,67-68,92`).
- `curl_cffi/curl.py:15` `import certifi`; `_default_cacert()` at `:22-35` resolution order:
  1. `:24` env vars `SSL_CERT_FILE`, `CURL_CA_BUNDLE`, `REQUESTS_CA_BUNDLE` (used if the path exists)
  2. `:29-31` `ssl.get_default_verify_paths().cafile` (OS trust store)
  3. `:34-35` **fallback `certifi.where()`**
  - `:37` `DEFAULT_CACERT = _default_cacert()`; applied at `:566` (`CurlOpt.CAINFO`) and `:568` (`PROXY_CAINFO`).
  - Runtime on this host: step 1 unset, step 2 `None` → `DEFAULT_CACERT` = the certifi `cacert.pem` path. So curl_cffi also trusts certifi here.
- Dependency graph (`uv.lock`): `certifi` ← `curl_cffi` (`uv.lock:100`), `httpcore` (`:190`), `httpx` (`:204`). `httpx` itself is required by `flet` (`flet-1.0.4.dist-info/METADATA` → `Requires-Dist: httpx>=0.28.1; platform_system != "Emscripten"`), `user_scanner` (`httpx[http2]`, `curl_cffi`) and `phonsint` (`httpx[http2]`, `curl_cffi`) — so certifi is unavoidably in the graph on every platform except Emscripten.

## 3) App-relevant checks

**(a) verify=False / custom SSL context in app code — none.**
`grep -rni "verify" src/` → 0 hits; `grep -rni "ssl" src/` → 0 hits; no `certifi`/`cafile`/`SSL_CERT_FILE`/`CURL_CA_BUNDLE` references. All app TLS goes through the shared client with httpx defaults (`src/services/http_client.py:58-77`: `httpx.AsyncHTTPTransport(retries=…, limits=…)` and `httpx.AsyncClient(…)` — no `verify=` argument, so `verify=True` → certifi). The bundled `flet` runtime also never touches TLS config (`grep -rn "verify=|ssl_context|CERT_NONE|check_hostname" flet/` → 0 hits).

**(b) Update service HTTPS → which CA store.**
`src/services/update_service.py:72-74` → `from services.http_client import get_client` → `get_client().get(self.config_url, timeout=4.0)`.
Chain: `http_client.get_client()` → `httpx.AsyncHTTPTransport(...)` (`src/services/http_client.py:58`) → `httpx/_transports/default.py:297` `create_ssl_context(verify=True, trust_env=True)` → `httpx/_config.py:38-40` → `ssl.create_default_context(cafile=certifi.where())`.
Result: update checks are verified against **certifi's Mozilla CA bundle** (117 roots), unless the process has `SSL_CERT_FILE`/`SSL_CERT_DIR` set (httpx `trust_env=True` honours them) — note curl_cffi honours `SSL_CERT_FILE`/`CURL_CA_BUNDLE`/`REQUESTS_CA_BUNDLE` but httpx does *not* honour `CURL_CA_BUNDLE`, so the two stacks can diverge if only `CURL_CA_BUNDLE` is set. The app sets none of these, so both agree on certifi.

**(c) Android packaging — what is verifiable from the venv/repo.**
- The flet build toolchain is **not in this venv**: only `flet` 1.0.4 (runtime), `flet-ads`; `flet-cli`/`fbuild`/serious-python are absent (`flet/cli.py` contains no `apk`/`build` command; no `build/`, `apk/`, `android/` artifacts in the repo). How the APK assembles site-packages therefore **cannot be confirmed from the venv** — it is decided by the external `flet build` toolchain, not by anything in `Sherlock-V3`.
- What *is* verifiable and favourable: `cacert.pem` lives inside the `certifi` package directory as package data (`RECORD`), so any mechanism that copies the app's site-packages tree into the APK carries it automatically; it needs no explicit `[tool.flet]`/asset declaration, and the app's `[tool.flet.cleanup] package_files` list (`pyproject.toml:55-66`) does not exclude it.
- `certifi.where()` is filesystem-based on py≥3.11 (`core.py:19-49`, `importlib.resources` + `as_file`): it returns a real path when the package is unpacked on disk (as an APK's assets are), and only extracts to a temp file in a zipimport situation.
- Android/serious-python CPython has no OS CA bundle at `ssl.get_default_verify_paths().cafile` (as measured on this host: `None`), so the certifi fallback is the *only* working trust anchor for `httpx`/`curl_cffi` there; dropping certifi from the bundle would break all HTTPS on Android.

## 4) Verdict

**PERFECT** — no issues found.

- certifi 2026.10.18 is intact and consistent (version, `cacert.pem` 234,072 B / 117 roots, `RECORD` hashes) in the venv.
- It is the effective default CA store for every HTTPS path the app uses (httpx → `certifi.where()`; curl_cffi → certifi fallback), because the app never sets `verify=False` and no env override is present.
- The only residual risk is packaging-side and unverifiable inside the venv: if the external flet/serious-python Android build excluded `certifi` (or its `cacert.pem`) from the bundled site-packages, TLS on Android would fail hard. Current repo config does not exclude it.
- Minor consistency note (not an issue): `curl_cffi` honours `CURL_CA_BUNDLE`/`REQUESTS_CA_BUNDLE` while httpx honours only `SSL_CERT_FILE`/`SSL_CERT_DIR`; the app sets none, so both stacks use certifi consistently today.
