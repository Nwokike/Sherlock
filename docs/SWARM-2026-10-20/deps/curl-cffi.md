# Dependency Audit: `curl-cffi` 0.16.3 (Sherlock-V3)

**Scope**: installed package at `.venv/Lib/site-packages/curl_cffi` (the `.venv` is the only source of truth), plus how `user-scanner` and `phonsint` (both transitive deps) and the Sherlock-V3 app use it.
**Date**: 2026-10-20 · **Desktop venv**: CPython 3.14 win_amd64 (`.python-version` = `3.14`).
**No network calls were made.** Load test was import + object construction only.

---

## 1. Installed verification

### 1.1 Version and libcurl build string — VERIFIED

| Item | Value | Source |
|---|---|---|
| Package version | `0.16.3` | `curl_cffi/__version__.py:5` (`metadata.version("curl_cffi")`) |
| Installed location | `.venv/Lib/site-packages/curl_cffi` + `curl_cffi-0.16.3.dist-info` | filesystem |
| Native lib | `curl_cffi/_wrapper.pyd` (39,936 bytes, win_amd64) | filesystem |
| Bundled native libs | `curl_cffi.libs/` (delvewheel patch at `curl_cffi/__init__.py:1-11`) | filesystem |

`curl_cffi.__curl_version__` resolves without creating an easy handle (`__version__.py:8-15`):

```text
libcurl/8.21.0-IMPERSONATE BoringSSL zlib/1.3.1 brotli/1.2.0 zstd/1.5.7 WinIDN nghttp2/1.63.0 ngtcp2/1.20.0 nghttp3/1.15.0
```

BoringSSL (client-hello control, GREASE, cipher control), HTTP/2 via nghttp2, HTTP/3 via ngtcp2/nghttp3, brotli/zstd/zlib.

### 1.2 Load test — PASSED

Executed in the project venv (no network):

```
import curl_cffi                              -> OK
curl_cffi.__version__                         -> 0.16.3
curl_cffi.__curl_version__                    -> libcurl/8.21.0-IMPERSONATE ...
from curl_cffi import requests                -> OK (module curl_cffi.requests.impersonate)
curl_cffi.requests.impersonate                -> module present
cffi.Session(impersonate='chrome')            -> constructed OK, .impersonate == 'chrome', .close() OK
import user_scanner.core.impersonate          -> OK  (imports curl_cffi at module scope, line 5)
impersonate_validate('not-a-url', ...)        -> Result(status=Status.ERROR)  # no crash, no network
```

So **the binary loads and the engine's impersonation path is fully functional on this desktop venv.**

### 1.3 Impersonate targets installed — VERIFIED

Source of truth: `curl_cffi/requests/impersonate.py`.

* `BrowserType` enum (`impersonate.py:128`): **47 members** — `edge99/101`, `chrome99/100/101/104/107/110/116/119/120/123/124/131/133a/136/142/145/146/150`, `chrome99_android`, `chrome131_android`, `safari153/155/170/172_ios/180/180_ios/184/184_ios/260/260_ios/2601`, `safari15_3/15_5/17_0/17_2_ios/18_0/18_0_ios` (deprecated aliases), `firefox133/135/144/147`, `tor145`.
* Default aliases `DEFAULT_*` (`impersonate.py:81-89`) and the alias map `REAL_TARGET_MAP` (`impersonate.py:92-103`, 9 entries):

| Alias | Resolves to | Alias | Resolves to |
|---|---|---|---|
| `chrome` | `chrome150` | `chrome_android` | `chrome131_android` |
| `edge` | `edge101` | `firefox` | `firefox147` |
| `safari` | `safari2601` | `tor` | `tor145` |
| `safari_beta` | `safari2601` | `safari_ios` | `safari260_ios` |
| `safari_ios_beta` | `safari260_ios` | | |

* Resolution helper: `resolve_latest_browser_type()` (`impersonate.py:105`); native-vs-fingerprint dispatch via `NATIVE_TARGET_NAMES` / `DEPRECATED_NATIVE_TARGET_ALIASES` (`curl_cffi/requests/utils.py:386-396`).
* **Both engines use `DEFAULT_IMPERSONATE = "chrome"`** (`user_scanner/core/impersonate.py:10`, `phonsint/core/impersonate.py:6`) → resolves to `chrome150` at runtime. Valid on this build.

### 1.4 Session / AsyncSession API — VERIFIED

`curl_cffi/requests/session.py`:

* `Session.__init__(curl=None, thread=None, use_thread_local_curl=True, **kwargs)` — thread-local easy handles by default (`session.py:481+`).
* `Session.request(method, url, params=, data=, content=, json=, headers=, cookies=, files=, auth=, timeout=NOT_SET, allow_redirects=None, max_redirects=None, proxies=, proxy=, proxy_auth=, verify=, referer=, accept_encoding='gzip, deflate, br', content_callback=, impersonate=, ja3=, akamai=, perk=, extra_fp=, default_headers=, default_encoding='utf-8', quote=, http_version=, interface=, doh_url=, cert=, stream=, max_recv_speed=0, multipart=, discard_cookies=False)`.
* `Session.get(url, **kwargs)` → same parameter set.
* **Redirect default**: the *session* default is `allow_redirects=True` (`session.py:236, 266`); a per-request `None` inherits the session value (`session.py:726-727`). The engines override this to **False** (`user_scanner/core/impersonate.py:58`, `phonsint/core/impersonate.py:78`) so a 301/302 is visible to the validator; individual modules opt back in (e.g. `user_scanner/user_scan/social/facebook.py:47` passes `allow_redirects=True`).
* `AsyncSession(*, loop=None, async_curl=None, max_clients=10, **kwargs)` — multi-handle based. **Neither engine uses it** (see §4.8).
* Proxies: `proxies={"http": …, "https": …}` (what the engines pass) and singular `proxy=` are both supported; `http/https/socks5/socks5h` schemes supported.

### 1.5 Exception classes — VERIFIED

`curl_cffi/requests/exceptions.py` (all subclass `RequestException`):

```
CurlError (curl_cffi/curl.py)  [carries .code: CurlECode]
└── RequestException (exceptions.py:13)  ← NOTE: also inherits OSError
    ├── CookieConflict(28)  SessionClosed(32)  ImpersonateError(36)
    ├── InvalidJSONError(41) → JSONDecodeError(46)
    ├── HTTPError(50) → IncompleteRead(54)
    ├── ConnectionError(58) → DNSError(62) / SSLError(70) → CertificateVerifyError(74)
    │                      → ConnectTimeout(83)
    ├── ProxyError(66)  Timeout(78) → ReadTimeout(93)
    ├── URLRequired(98)  TooManyRedirects(102)
    ├── MissingSchema(107)  InvalidSchema(111)  InvalidURL(115) → InvalidProxyURL(125)
    ├── InvalidHeader(120)  ChunkedEncodingError(130)  ContentDecodingError(135)
```

`code2error()` / `CODE2ERROR` map raw `CurlECode` values onto the above (`exceptions.py:176-228`).
**Correction to the V2 background doc** (`docs/reference/dep-curl-cffi.md` §8): the hierarchy it prints omits `OSError` — `RequestException(CurlError, OSError)` — so `except OSError` also catches every curl_cffi error.

---

## 2. Usage by engines + app (recount from the installed engines)

### 2.1 Counts — the "113 modules" figure is WRONG

Recounted by scanning every `.py` under `.venv/Lib/site-packages/user_scanner` (2,805 files) and `phonsint` (18 files):

| Population | Count | Notes |
|---|---|---|
| `user_scanner` username modules (`user_scan/**`) | 2,521 | of which **67** reach curl_cffi, **2,391** use `generic_validate` (httpx path) |
| `user_scanner` email modules (`email_scan/**`) | 220 | of which **39** reach curl_cffi, **180** use httpx, 1 other |
| `user_scanner` files referencing the impersonation API | **108** | 68 `user_scan/` + 39 `email_scan/` + `core/impersonate.py` |
| `user_scanner` calls to `impersonate_validate` | **55** module files (+ `core/impersonate.py` itself) | 27 also call `impersonate_request`; 15 use both |
| `phonsint` site modules | **5** | **4** reach curl_cffi: `modules/auth/microsoft.py`, `modules/social/instagram.py`, `modules/social/facebook.py`, `modules/shopping/amazon.py`; only `modules/crm/zoho.py` does not |

**Corrected headline**: **106 site modules** in `user_scanner` (67 username + 39 email) + **4 of 5** phone modules in `phonsint` = **110 site modules that reach `curl_cffi`**, out of 2,741 `user_scanner` modules + 5 `phonsint` modules (~4%).

`docs/reference/dep-httpx.md:389` and `:427` state "exactly 113 sites in `user_scanner` use `impersonate_validate`". **That is wrong for V3's installed engines.** The correct numbers are: **55** modules call `impersonate_validate`, **67** username modules reach curl_cffi by any path, **39** email modules do, **108** files total under `user_scanner` (106 of them site modules). The 113 figure should be corrected in `docs/reference/dep-httpx.md` and the V2 background doc.

### 2.2 How the engines call it

`user_scanner/core/impersonate.py` (the only curl_cffi import site in `user_scanner`, line 5):

* `impersonate_validate(url, func, warmup_url=None, impersonate="chrome", show_url=None, **kwargs)` (lines 19-41) — wraps the request, calls the module's `func(response)`, and converts **any** exception into `Result.error(e, url=…)` (lines 40-41). This is the graceful-degradation guarantee.
* `impersonate_request(...)` (lines 44-59) — `kwargs.setdefault("timeout", _timeout())`, `kwargs.setdefault("allow_redirects", False)`, then `session.request(method, url, **kwargs)`.
* `_get_warm_session(impersonate, proxy, warmup_url)` (lines 96-126) — process-global session cache keyed by `(impersonate, proxy)`, plus a `warmup_url` clearance-cookie warm-up guarded by a per-key `threading.Lock` and a double-checked `_warmed` set.
* `impersonate_request_async(...)` (lines 75-93) — `asyncio.to_thread(impersonate_request, …)`; **the blocking `Session` is used, not `AsyncSession`**.
* Timeout comes from `get_global_timeout()` (CLI `-t` flag) else `DEFAULT_TIMEOUT = 15.0` (lines 11, 129-133).

`phonsint/core/impersonate.py` is a near-duplicate of the same design (lines 4, 35-97), with its own `set_global_timeout` / `set_global_proxy` globals and the same `allow_redirects=False` default.

### 2.3 How the **app** uses it — the app never imports curl_cffi

`grep -rn "import curl_cffi|from curl_cffi" src/` → **0 hits** across all 54 app `.py` files. The app only carries a **boolean flag**:

| Location | Role |
|---|---|
| `src/core/state.py:133` | `use_curl_cffi: bool = True` |
| `src/core/constants.py:64` | `STORAGE_USE_CURL_CFFI = "sherlock_use_curl_cffi"` |
| `src/main.py:806-808` | loads persisted value into `state.use_curl_cffi` |
| `src/main.py:1087`, `src/main.py:1536` | passes `use_curl_cffi=` into the scan services |
| `src/screens/settings_screen.py:681-683, 953-962` | "Stealth TLS (curl-cffi)" switch |
| `src/screens/home_screen.py:535-539, 858-864` | home-screen chip toggle |
| `src/services/email_service.py:207, 250-251` | `use_curl_cffi` → `use_stealth_fingerprint` |
| `src/services/cache_service.py:630` | comment: "The engines build their own httpx/curl_cffi clients internally" |

**The flag is a dead end.** `grep -rn "use_curl_cffi|stealth" .venv/.../user_scanner .venv/.../phonsint` → **0 hits**: the engines have no `use_curl_cffi` / stealth switch at all. In `email_service.py` the derived `use_stealth_fingerprint` is computed at line 250-251 and then **never referenced again** (the only other occurrence is the parameter declaration at line 210). And in the username path each of the 67 modules **statically** imports `impersonate_validate` at module scope — there is no runtime switch between `generic_validate` and `impersonate_validate` (only 1 file in the whole package mentions both, and that is `core/impersonate.py` in a docstring).

Consequences:

1. The UI toggle labelled "Stealth TLS (curl-cffi)" **does not gate anything**. The 67 username + 39 email modules always impersonate.
2. It also cannot act as a mobile fallback — turning it off would not avoid `import curl_cffi`.
3. Only 1 of 2,391 username modules (`user_scan/**` minus the 67) and 180 of 220 email modules use the plain httpx path.

### 2.4 Import-time coupling and how the app loads modules

`from curl_cffi import requests as cffi` is a **module-scope import** in both `user_scanner/core/impersonate.py:5` and `phonsint/core/impersonate.py:4`. Therefore `curl_cffi` is a hard **import-time** dependency of 110 site modules, and `curl_cffi/__init__.py:63` in turn does `import _cffi_backend` (the compiled extension shipped by the `cffi` package — present here as `_cffi_backend.cp314-win_amd64.pyd`).

Module loaders:

* **Upstream `user_scanner` loader — UNGUARDED**: `user_scanner/core/helpers.py:504-517` calls `spec.loader.exec_module(module)` with **no `try/except`**. A single `ImportError` aborts the whole category (and in the upstream CLI orchestrator, `orchestrator.py:176/206`, the whole scan).
* **Upstream `phonsint` loader — guarded**: `phonsint/core/helpers.py:50-64` wraps `exec_module` in `try/except Exception: continue` → offending modules are silently dropped.
* **The app's own loader — guarded**: `src/services/user_scanner_compat.py:61-83` (`_load_modules_tolerant`) does a per-file import with `except Exception`, logs `skipped module %s: %s` and continues. The app deliberately does **not** use upstream's loader (docstring: *"Per-file import with try/except — upstream aborts the whole category"*). This is the right call and it is what keeps a missing `curl_cffi` from crashing the app.

Net effect on a platform where `curl_cffi` cannot be imported: **the app does not crash — 110 modules silently vanish** (one `logger.warning` each), and the user is shown "site not found" for 110 sites that are merely unsupported. That is a *silent correctness* problem, not a crash.

---

## 3. Mobile build implications (uv.lock evidence)

### 3.1 The build targets

`pyproject.toml`:

```toml
requires-python = ">=3.14"          # .python-version = 3.14
[tool.flet.android]
target_arch = ["arm64-v8a", "x86_64"]
```

### 3.2 `curl-cffi` in `uv.lock` (entry at `uv.lock:96-125`)

`curl-cffi 0.16.3` depends on `certifi` and `cffi` (`uv.lock:99-102`). Its wheel list contains **exactly one Android wheel**:

```
uv.lock:116  curl_cffi-0.16.3-cp314-cp314-android_24_arm64_v8a.whl
```

There is **no `android` x86_64 wheel** and **no `cp314t` (free-threaded) Android wheel**. The Android wheel is also `cp314` (not `abi3`), so it only matches CPython 3.14 — which is what this project pins, so that part lines up.

### 3.3 `cffi` in `uv.lock` (entry at `uv.lock:28-…`) — THE CRITICAL FINDING

`cffi 2.1.1` publishes wheels for: iOS (`ios_13_0_arm64_iphoneos`, `..._iphonesimulator`), macOS (x86_64 / arm64), manylinux + musllinux (aarch64, ppc64le, s390x, x86_64), Windows (`win32`, `win_amd64`, `win_arm64`) — for `cp314`, `cp314t` and `cp315`.

**`grep -n "android" uv.lock` returns exactly ONE line: the `curl_cffi` arm64_v8a wheel above. There is ZERO Android wheel for `cffi`.**

Since `curl_cffi/__init__.py:63` executes `import _cffi_backend` — and `_cffi_backend` is the compiled extension that ships in the **`cffi`** wheel, not in the `curl_cffi` wheel — the dependency chain is:

```
curl_cffi (android_24_arm64_v8a wheel EXISTS)
  └── cffi  (NO android wheel)   ← breaks
        └── _cffi_backend (compiled C extension, platform-specific)
```

### 3.4 Answer to the owner's critical question

> **Are there Android wheels for `cffi`?**
> **No.** Not one, for any ABI, in the pinned lock (`uv.lock:28-…`, zero `android` entries).

**Therefore the `curl-cffi` dependency graph resolved from this `uv.lock` cannot be installed or imported on an Android build.**
Concretely, on an Android APK/IPA:

* `import curl_cffi` → `ImportError: No module named '_cffi_backend'` (or the wheel is simply unresolvable at install time).
* `user_scanner/core/impersonate.py:5` raises → the 67 username + 39 email modules fail to import; `phonsint/core/impersonate.py:4` raises → 4 of 5 phone modules fail to import.
* Via the app's tolerant loader these become **110 skipped modules with only a log line**, and the UI shows them as "not found".
* **The `x86_64` Android target is broken twice over**: neither `curl_cffi` nor `cffi` has an `android_x86_64` wheel in the lock, so the emulator/x86_64 build cannot use `curl_cffi` even if `cffi` were solved.

### 3.5 The V2 background doc's Android claims are optimistic

`docs/reference/dep-curl-cffi.md` §10 states that Flet Forge (`pypi.flet.dev`) publishes `curl-cffi` `android_24_x86_64` wheels and that *"building Sherlock-V2 mobile APKs does not require an Android NDK compilation toolchain for `curl-cffi`"*. Two problems:

1. It says nothing about **`cffi`**, which is the actual blocker (see §3.3). `curl-cffi` cannot work without a platform `cffi`/`_cffi_backend`.
2. `pypi.flet.dev` is a *different index* from the PyPI index recorded in `uv.lock`. The lock can only express PyPI wheels, so **the lock is not a valid source of truth for the mobile build** — the mobile build needs its own resolution against the Flet/Serious-Python index.

**Action required before shipping Android:** confirm that the index used by the Flet Android build provides `cffi` for **both** `android_24_arm64_v8a` and `android_24_x86_64` (and that `curl-cffi` provides `x86_64`, which PyPI does **not**). Until that is confirmed, treat `curl_cffi` as **desktop-only**, exactly as `docs/reference/dep-httpx.md:427` already warns.

### 3.6 Capability matrix

| Capability | Android arm64-v8a | Android x86_64 | Desktop |
|---|---|---|---|
| `import curl_cffi` (needs `cffi`/`_cffi_backend`) | **blocked** (no `cffi` wheel in lock) | **blocked** (no `cffi`, no `curl_cffi` android wheel) | works |
| 67 username modules on protected sites (TLS-fingerprint walls: DataDome, Cloudflare, etc.) | **unavailable** (silently skipped) | unavailable | works |
| 39 email modules | **unavailable** | unavailable | works |
| 4 of 5 phone modules (Microsoft, Instagram, Facebook, Amazon) | **unavailable** | unavailable | works |
| `phonsint` `crm/zoho.py` | works (no curl_cffi) | works | works |
| 2,391 username + 180 email modules on the httpx/`generic_validate` path | works | works | works |
| BoringSSL TLS impersonation (the whole point of the dep) | **unavailable** | unavailable | works |

### 3.7 What the app should do

1. **Capability probe, not a flag.** At startup, probe once (`try: import curl_cffi; except Exception`) and store e.g. `state.curl_cffi_available`. Use it to *disable/grey out* the "Stealth TLS (curl-cffi)" switch instead of pretending it works.
2. **Make the toggle honest or remove it.** `use_curl_cffi` currently reaches neither engine and is dropped in `email_service.py:250-251`. Either wire it end-to-end (requires an upstream engine change — neither engine has the switch) or relabel it as informational/unsupported on mobile.
3. **Surface the degradation instead of hiding it.** `_load_modules_tolerant` (`src/services/user_scanner_compat.py:61-83`) already knows how many modules it skipped and why. It should distinguish `ImportError` and report "N sites unavailable on this platform (TLS impersonation unsupported)" to the UI, so users do not read "not found" for "not attempted".
4. **Per-module runtime errors are already safe.** `impersonate_validate` catches every exception → `Result.error(e)` (`user_scanner/core/impersonate.py:40-41`), and `Result.error` → `Status.ERROR` (`user_scanner/core/result.py:137-138`). Any module that *does* import will report errors rather than crash.
5. **Plan a fallback.** For the protected 110 sites, the Android build needs either (a) a `cffi` Android wheel from the mobile index (then `curl_cffi` works and nothing changes), or (b) an httpx fallback path in the engines for `impersonate_validate` → `generic_validate` (would lose TLS-fingerprint clearing, i.e. some sites would return false negatives).

---

## 4. Correctness / robustness issues

| # | Severity | Issue | Evidence |
|---|---|---|---|
| 1 | **High (mobile)** | `cffi` has **no Android wheel** → `curl_cffi` unimportable → 110 modules unavailable on the Android build resolved from `uv.lock`; `x86_64` additionally has no `curl_cffi` android wheel | `uv.lock:28-…` (zero android entries for cffi), `uv.lock:116` (only `android_24_arm64_v8a`), `curl_cffi/__init__.py:63` |
| 2 | **High (UX)** | The "Stealth TLS (curl-cffi)" toggle is a **no-op**: it reaches neither engine, and `use_stealth_fingerprint` is computed then discarded | `src/services/email_service.py:250-251`; `grep use_curl_cffi\|stealth` in `user_scanner`/`phonsint` → 0 hits |
| 3 | **Medium-High (UX)** | When `curl_cffi` is unavailable, modules are **silently skipped** — the user sees "not found" for sites that were never queried | `src/services/user_scanner_compat.py:78-82` (log only), `phonsint/core/helpers.py:59-63` (`except: continue`) |
| 4 | **Medium (upstream)** | `user_scanner`'s own `load_modules` has **no exception guard** — one bad import kills an entire category (and the upstream CLI scan). The app already avoids it; the CLI path does not | `user_scanner/core/helpers.py:504-517` vs `src/services/user_scanner_compat.py:61-83` |
| 5 | **Medium** | No runtime impersonation fallback: the choice between `generic_validate` and `impersonate_validate` is **static per module** (module-scope imports). 67 username + 39 email modules can never fall back to httpx | `user_scanner/user_scan/social/facebook.py:3` (static import); 1 file in the package mentions both validators |
| 6 | **Low-Medium** | `phonsint` warm-up key ignores `warmup_url` (`if warmup_url and key not in _warmed`), so a second module with a different warm-up URL never performs its own warm-up and inherits the first module's clearance cookies. `user_scanner` keys on `(impersonate, proxy, warmup_url)` and gets this right | `phonsint/core/impersonate.py:56` vs `user_scanner/core/impersonate.py:99-100, 118-124` |
| 7 | **Low** | Sessions are never closed. `_sessions` is a process-global dict keyed by `(impersonate, proxy)`; on proxy rotation the dict and each `Session`'s curl handles grow unbounded — relevant on mobile where the app is suspended/resumed | `user_scanner/core/impersonate.py:13, 99-111`; `phonsint/core/impersonate.py:9, 40-49` |
| 8 | **Low** | Inconsistent warm-up failure semantics: `user_scanner` deliberately leaves a session *unwarmed* when the warm-up raises (so it retries later), `phonsint` swallows the exception and marks it warmed anyway | `user_scanner/core/impersonate.py:118-124` vs `phonsint/core/impersonate.py:59-63` |
| 9 | **Low (docs)** | Background doc `docs/reference/dep-curl-cffi.md` §8 prints the exception hierarchy without `OSError`; §10's Android claims omit the `cffi` blocker; `docs/reference/dep-httpx.md:389, 427` state "113 sites" — actual is 106 site modules (67 username + 39 email) + 4 phone modules, 108 files under `user_scanner` | `curl_cffi/requests/exceptions.py:13`; `uv.lock`; recount of installed engines |
| 10 | **Info** | The V2 doc's §4 (AsyncSession / `AsyncCurl` / Windows Proactor workaround) describes a code path **Sherlock never uses** — both engines' async entry points are `asyncio.to_thread` over the *synchronous* `Session` | `user_scanner/core/impersonate.py:75-93`; `phonsint/core/impersonate.py:82-97` |
| 11 | **Info** | `curl_cffi`'s own redirect default is `True`; the engines force `False` and let individual modules opt in. Any future engine code that forgets `allow_redirects=False` will silently follow 302s and lose the OSINT signal (a 302 to a canonical URL is the "profile exists" signal) | `session.py:236, 266, 726-727` vs `user_scanner/core/impersonate.py:58` |

### Corrections to the V2 background doc (`docs/reference/dep-curl-cffi.md`)

* **§1.1, §2, §9, §10** — accurate (version, libcurl string, alias table, `_get_warm_session`, warm-up pattern, PyPI `android_24_arm64_v8a` wheel all verified against the installed source and `uv.lock`).
* **§8** — exception hierarchy is missing `RequestException(CurlError, OSError)`.
* **§10.2/§10.3** — omits that `cffi` (the mandatory dependency of `curl_cffi`) has no Android wheel in `uv.lock`; the "no NDK toolchain needed" conclusion only holds if the mobile index also ships `cffi` for the target ABIs, which is unverified and not expressible in this lock.
* **`docs/reference/dep-httpx.md:389/427`** — "113 sites" → **106** (`user_scanner`: 67 username + 39 email; 108 files counting `core/impersonate.py`), plus **4 of 5** phonsint modules.

---

## 5. Verdict

### **ISSUES FOUND**

**Desktop is healthy.** The installed `curl-cffi 0.16.3` loads cleanly: `libcurl/8.21.0-IMPERSONATE BoringSSL …`, 47 impersonation targets with a working alias map (`"chrome"` → `chrome150`), a complete `Session`/`AsyncSession` API, and a well-formed exception hierarchy. `user_scanner.core.impersonate` imports and constructs a session, and `impersonate_validate` degrades to `Result.error` instead of raising. The engines' integration is disciplined: process-wide session cache, per-key warm-up locking, `allow_redirects=False` for OSINT signal integrity, and every failure funnelled into `Result.error`.

**But three issues are material, and one is a build blocker:**

1. **BLOCKER (mobile):** `cffi` — the mandatory `_cffi_backend` provider for `curl_cffi` — has **no Android wheel** in `uv.lock` (zero android entries; the only android wheel in the whole lock is `curl_cffi`'s `arm64_v8a` one at `uv.lock:116`). `curl_cffi` therefore **cannot be imported on an Android build resolved from this lock**, and the `x86_64` Android target has no `curl_cffi` wheel at all. 110 site modules (67 username + 39 email + 4 of 5 phone) become unavailable.
2. **HIGH:** the app's "Stealth TLS (curl-cffi)" toggle is a **no-op** — it reaches neither engine and `use_stealth_fingerprint` is dropped at `src/services/email_service.py:250-251`. It is currently a misleading control and cannot serve as the mobile fallback.
3. **MEDIUM-HIGH:** on a platform without `curl_cffi`, degradation is **silent** — the tolerant loader logs and continues, so 110 sites present as "not found" rather than "not supported". The app should probe capability at startup, disable the switch, and surface the skipped-module count.

**Recommended actions (no app files were modified by this audit):**

1. Verify `cffi` availability for `android_24_arm64_v8a` **and** `android_24_x86_64` on the index the Flet Android build actually uses; if absent, either drop the `x86_64` target or plan an httpx fallback for the 110 modules.
2. Add a `curl_cffi` capability probe at startup; gate the "Stealth TLS" switch on it.
3. Report tolerant-loader skips (especially `ImportError`s) in the UI.
4. Fix the "113 modules" figure in `docs/reference/dep-httpx.md:389, 427` (→ 106) and the `cffi`-omission in `docs/reference/dep-curl-cffi.md` §10.
5. Forward the `phonsint` warm-up key bug (§4.6) and the missing `Session.close()` (§4.7) upstream.
