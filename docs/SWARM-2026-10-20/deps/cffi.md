# Dependency Audit: `cffi` (2.1.1) — Sherlock-V3

Audit date: 2026-10-20
Scope: installed package at `.venv/Lib/site-packages/cffi` + `_cffi_backend`
Source of truth: the installed `.venv` (no PyPI/network inference for runtime behaviour)

---

## 1. Installed verification

### 1.1 Version identity

| Artifact | Evidence | Value |
|---|---|---|
| Package `__init__` | `cffi/__init__.py:8-9` | `__version__ = "2.1.1"`, `__version_info__ = (2, 1, 1)` |
| Verifier module pin | `cffi/__init__.py:14` | `__version_verifier_modules__ = "0.8.6"` |
| Dist metadata | `cffi-2.1.1.dist-info/METADATA:3` | `Version: 2.1.1` |
| Dist metadata | `cffi-2.1.1.dist-info/METADATA:24` | `Requires-Python: >=3.10` |
| Dist metadata | `cffi-2.1.1.dist-info/METADATA:27` | `Requires-Dist: pycparser; implementation_name != "PyPy"` |
| Installer | `cffi-2.1.1.dist-info/INSTALLER:1` | `uv` |
| Top-level names | `cffi-2.1.1.dist-info/top_level.txt` | `_cffi_backend`, `cffi` |

Background doc `docs/reference/dep-cffi.md:13` cites `uv.lock:27-34` for the cffi block; in the
**current V3** `uv.lock` the block is `uv.lock:28-84` (line 27 is `[[package]]`). The
background doc's version and metadata are otherwise still accurate.

### 1.2 Backend binary identity

- File: `.venv/Lib/site-packages/_cffi_backend.cp314-win_amd64.pyd`, **181,248 bytes**.
- Wheel tag: `cffi-2.1.1.dist-info/WHEEL:4` → `Tag: cp314-cp314-win_amd64` (matches
  `Root-Is-Purelib: false`, `WHEEL:3` — a platform wheel, not pure-Python).
- `top_level.txt` confirms `_cffi_backend` ships **inside the `cffi` distribution** — there is no
  separate `_cffi-backend` PyPI project. `cffi-2.1.1.dist-info/RECORD` line:
  `_cffi_backend.cp314-win_amd64.pyd,sha256=npmyGExg8hqIyvw3Q4be01WehpTtfPER8oaeBm0wMzQ,181248`
- **Independently verified**: sha256 of the on-disk `.pyd` (base64-urlsafe) recomputed in the venv
  interpreter = `npmyGExg8hqIyvw3Q4be01WehpTtfPER8oaeBm0wMzQ`, size `181248` — **byte-identical to
  the RECORD entry**. The binary is the one the wheel shipped, unpatched.
- Interpreter: Python **3.14.7**, CPython (`sys.implementation.name == 'cpython'`) — consistent
  with the `cp314` ABI tag.

### 1.3 Version guard (`cffi/api.py`)

```python
cffi/api.py:41   import _cffi_backend as backend
cffi/api.py:42   from . import __version__
cffi/api.py:43   if backend.__version__ != __version__:
cffi/api.py:47       raise Exception("Version mismatch: ...")
```

The guard fires in `FFI.__init__` (api.py:34-53). Note the guard is **only** reached when a
`cffi.FFI` object is constructed — see §5.

**Live load check (no C compilation, no network):**

```
python: 3.14.7 cpython
sha256(b64) = npmyGExg8hqIyvw3Q4be01WehpTtfPER8oaeBm0wMzQ
size = 181248
backend __version__ = 2.1.1
backend file: ...\.venv\Lib\site-packages\_cffi_backend.cp314-win_amd64.pyd
cffi pkg: 2.1.1
```

Backend `__version__` (2.1.1) matches `cffi.__version__` (2.1.1) → guard satisfied.
Note `_cffi_backend.FFI` (the C-level type) has **no `cdef` attribute** (`hasattr → False`);
`cdef` exists only on the Python-level `cffi.api.FFI` wrapper.

---

## 2. Position in dependency graph

cffi is **purely transitive**. It is not a declared dependency of the app.

```
Sherlock-V3 (pyproject.toml:7-12)          uv.lock:487-492  requires-dist
  ├─ flet            (direct)
  ├─ flet-ads        (direct)
  ├─ user-scanner    (direct)  ──► uv.lock:534 ──► curl-cffi
  └─ phonsint        (direct)  ──► uv.lock:353 ──► curl-cffi
                                              uv.lock:101 ──► cffi
                                                       uv.lock:32  ──► pycparser
```

- `pyproject.toml:7-12` declares only `flet`, `flet-ads`, `user-scanner>=1.5.2.3`,
  `phonsint>=0.1.0`. **No `cffi`.**
- `curl_cffi-0.16.3.dist-info/METADATA:20` → `Requires-Dist: cffi>=2.0.0` (cffi is a hard
  runtime dep of curl-cffi).
- `uv.lock:28-33` → cffi 2.1.1 depends on `pycparser` (marker `implementation_name != 'PyPy'`).
  `pycparser` 3.11 **is** installed in the venv, but is never imported at runtime (§4.3).
- Role: cffi is the C-FFI layer that lets `curl_cffi` call libcurl. Two distinct artifacts:
  - the **Python package** `cffi/` (`api.py`, `cparser.py`, `model.py`, `recompiler.py`, …) — the
    C-source parser + out-of-line code generator, used at **build time**;
  - the **C extension** `_cffi_backend*.pyd` — the libffi call bridge, needed at **runtime**.

### 2.1 Import mode used by curl_cffi at runtime

`curl_cffi/__init__.py` (installed, verbatim):

```python
curl_cffi/__init__.py:63   import _cffi_backend  # noqa: F401  # required by _wrapper
curl_cffi/__init__.py:67   # This line includes _wrapper.so into the wheel
curl_cffi/__init__.py:68   from ._wrapper import ffi, lib
```

The premise "confirm `from ._wrapper import ffi, lib`" is **confirmed at
`curl_cffi/__init__.py:68`**, with the important refinement that `_wrapper` is **not** a Python
module in this wheel — it is a pre-built binary:

- `curl_cffi/_wrapper.pyd` (39,936 bytes) is present in the installed package
  (`curl_cffi-0.16.3.dist-info/RECORD`: `curl_cffi/_wrapper.pyd,sha256=19NU3BtrC-...`).
- There is **no** `curl_cffi/_wrapper.py`. The `from ._wrapper import ffi, lib` therefore loads a
  compiled **ABI-mode** cffi module (out-of-line API), not a runtime-`cdef` module.
- `curl_cffi-0.16.3.dist-info/WHEEL:4` → `Tag: cp310-abi3-win_amd64`; the native libcurl-impersonate
  ships alongside as `curl_cffi.libs/libcurl-impersonate-1172405423dc93b7aeed557f2a2ca325.dll`,
  wired up by the delvewheel patch at `curl_cffi/__init__.py:1-10`.

**No `cdef()` is invoked at import time.** Proven empirically — after `import curl_cffi`:

```
curl_cffi imported OK, version 0.16.3
cffi pkg in sys.modules?     False
cffi.api in sys.modules?     False
cffi.cparser in sys.modules? False
pycparser in sys.modules?    False
_cffi_backend in sys.modules? True
```

The `cffi` **Python package is never loaded at runtime**. Only the `_cffi_backend` C extension is.
`pycparser` is not loaded. The cdef/parse step happened when curl-cffi was **built** (setup.py
→ `set_source()` → C compile → `_wrapper.pyd`); the shipped artifact is pre-parsed.

Consequence: the `cffi>=2.0.0` requirement of curl-cffi is a **build-time** requirement for
downstream packagers, but a **runtime** requirement for the `_cffi_backend` extension — which
ships in the same distribution.

---

## 3. Wheel availability evidence from `uv.lock`

### 3.1 `cffi` 2.1.1 — `uv.lock:28-84` → **ANDROID: NO**

`grep -c android` over the cffi block (`uv.lock:28-84`) = **0**.

Full platform set published for cffi 2.1.1 (extracted from the wheel URLs):

| Platform | Tags present |
|---|---|
| iOS | `ios_13_0_arm64_iphoneos`, `ios_13_0_arm64_iphonesimulator` |
| macOS | `macosx_10_15_x86_64`, `macosx_11_0_arm64` |
| Linux glibc | `manylinux2014_{aarch64,ppc64le,s390x,x86_64}` |
| Linux musl | `musllinux_1_2_{aarch64,x86_64}` |
| Windows | `win32`, `win_amd64`, `win_arm64` |
| **Android** | **NONE** |
| Linux armv7l / riscv64 / i686 | NONE |

ABI variants: `cp314`, `cp314t` (free-threaded), `cp315`, `cp315t`.

Only an sdist is offered besides wheels (`uv.lock:34`):
`cffi-2.1.1.tar.gz`, 530,807 bytes.

### 3.2 `curl-cffi` 0.16.3 — `uv.lock:96-125` → **ANDROID: YES (arm64-v8a only)**

`grep -c android` over the curl-cffi block (`uv.lock:96-125`) = **1**:

```
uv.lock:116  curl_cffi-0.16.3-cp314-cp314-android_24_arm64_v8a.whl   (8,607,323 bytes)
```

That single line at `uv.lock:116` is **the only `android` occurrence in the entire `uv.lock`**
(`grep -c android uv.lock` = 1).

### 3.3 The asymmetry — and why it matters for `flet build apk`

`grep -c "android.*x86_64" uv.lock` = **0**. curl-cffi ships exactly one Android wheel:
`android_24_arm64_v8a` (API 24+, arm64-v8a).

`pyproject.toml:36` → `target_arch = ["arm64-v8a", "x86_64"]`.

So for an APK build:

| Target arch | curl-cffi | cffi | Outcome |
|---|---|---|---|
| `arm64-v8a` | wheel present (`:116`) | **no wheel** → sdist | cffi must be **compiled from source** with the NDK (C compiler required) |
| `x86_64` | **no wheel** → sdist | **no wheel** → sdist | curl-cffi must be compiled from source (builds libcurl-impersonate from C) **and** cffi from source |

Note the inversion: **curl-cffi went out of its way to publish an Android wheel** — it must, because
its own `_wrapper.pyd` needs `_cffi_backend` at runtime (`curl_cffi/__init__.py:63`) and the
Android wheel cannot vendor the host-Python `_cffi_backend`. But **upstream cffi has not published
any Android wheel**, even though it *does* publish iOS wheels (`ios_13_0_arm64_iphoneos`,
`iphonesimulator`). cffi 2.1.1 is therefore the **sole hard blocker** on the `arm64-v8a` APK path:
`pip`/`uv` will fall back to `cffi-2.1.1.tar.gz` and try to build `_cffi_backend` with the NDK
cross-compiler, which is not a guaranteed-success step in a Flet/CI container.

Secondary gap: `x86_64` Android has **no** curl-cffi wheel either, so that arch needs a full
source build of libcurl-impersonate.

Windows/Desktop and macOS/Linux are unaffected — all needed wheels exist.

---

## 4. App-usage audit + what breaks if removed

### 4.1 Direct usage: **ZERO**

```
$ grep -rnE "(^|[^_a-zA-Z])cffi([^_a-zA-Z]|$)|_cffi_backend" src/ tests/ | grep -v "use_curl_cffi"
→ (no matches)   count = 0
```

Every raw `cffi` hit in `src/`/`tests/` is the **boolean flag** `use_curl_cffi` (an app-level
"Stealth TLS" toggle), never the library:

- `src/core/state.py:133` `use_curl_cffi: bool = True`
- `src/core/constants.py:64` `STORAGE_USE_CURL_CFFI = "sherlock_use_curl_cffi"`
- `src/screens/home_screen.py:535-537, 858-864` (toggle)
- `src/screens/settings_screen.py:681-682, 953-962` (toggle)
- `src/services/email_service.py:207, 251` (`use_stealth_fingerprint = use_curl_cffi`)
- `src/main.py:808, 1087, 1536`, `src/services/cache_service.py:630` (comments only)

**No `import cffi`, no `import _cffi_backend`, no `FFI()`, no `cdef()` anywhere in the app.**

### 4.2 What breaks if cffi were removed

The app's own code never touches cffi. The break is entirely transitive, and it happens at
`import curl_cffi` → `curl_cffi/__init__.py:63` (`import _cffi_backend`):

```
curl_cffi/__init__.py:63  import _cffi_backend  →  ImportError if the cffi dist is absent
```

(There is no try/except around it; the import is unconditional and top-level.)

Downstream blast radius, measured in the installed venv:

- **107** `user_scanner` site modules import `user_scanner.core.impersonate`
  (`user_scanner/core/impersonate.py:5` → `from curl_cffi import requests as cffi`).
  (Counted: 109 files in `user_scanner` mention `impersonate`; minus `core/impersonate.py` and one
  non-site file ⇒ **107** site modules — matches the figure in the task brief.)
- **6** `phonsint` modules import `phonsint.core.impersonate` (`phonsint/core/impersonate.py:4`).
- For scale, `src/core/constants.py:21` records the full catalogue: *"user-scanner: 2,521 username
  + 220 email modules; phonsint: 5 phone modules."*

Failure mode is **not** a hard crash, because the app's loader is deliberately tolerant
(`src/services/user_scanner_compat.py:8-9`):

> *"Tolerant module loading (upstream `load_modules` aborts a whole category on one bad import;
> here we skip + log the offender)."*

`src/services/user_scanner_compat.py:33-40` (`load_user_modules`) drives
`_load_modules_tolerant(cat_path)` (`:49`), which skips and logs each module that fails to import.

So with cffi removed:
- the app **still boots**;
- the **107 impersonating username sites + 6 phone sites silently disappear** from the scan
  catalogue (per-module log lines only) — a *silent capability regression*, not an error dialog;
- any explicit `import curl_cffi` in app code would raise `ImportError` at call time. The app
  itself makes no such import — its curl_cffi contact points are all inside the third-party
  `*_impersonate` modules.
- TLS-fingerprint impersonation (DataDome / bot-wall bypass) is lost for those 107 sites; they fall
  back to plain httpx and are far more likely to be rate-limited or blocked.

**Important nuance:** the Python package `cffi/` (`api.py`, `cparser.py`, `model.py`,
`recompiler.py`) is **not** required at runtime at all — only the `_cffi_backend` extension is
(§2.1). Since both ship in the same wheel, "remove cffi" necessarily means "remove
`_cffi_backend`" ⇒ the 113-module breakage. But if one wanted a *runtime-lean* build, the
`cffi/` Python package and `pycparser` could in principle be dropped while keeping
`_cffi_backend*.pyd` — the `cffi` distribution simply does not ship them separately, and
`uv`/pip cannot install a partial distribution.

### 4.3 `pycparser` is installed but dead weight at runtime

`pycparser` 3.11 is present in the venv (pulled by `uv.lock:32`) but is **never imported** (§2.1
sys.modules probe). It exists solely so that cffi's `cparser` module can parse C declarations when
a build actually calls `cdef`/`set_source`. It is pure-Python and platform-agnostic, so it is
harmless for Android packaging.

---

## 5. Runtime failure candidates

### 5.1 Can anything in this app trigger `cdef()` at runtime? — **No**

The full call chain to `cdef` is:

```
cffi/api.py:94   FFI.cdef(csource, ...)      (public)
cffi/api.py:112  -> self._cdef(...)
cffi/api.py:117      with self._lock:
cffi/api.py:119          self._parser.parse(csource, ...)   ← pycparser invoked here
```

`self._parser` is only created inside `FFI.__init__` (`cffi/api.py:61` `self._parser =
cparser.Parser()`), and `cparser` itself is imported only there (`cffi/api.py:58`
`from . import cparser`). Consequences:

- `import cffi` (the package) does **not** import `cparser` or `pycparser` — both are deferred to
  `FFI()` construction.
- Nothing in the app constructs a `cffi.FFI`. The only FFI objects in the process are the
  ABI-mode `ffi`/`lib` exported by the pre-built `curl_cffi/_wrapper.pyd`; those are C-level
  objects created by the extension at import time, not by `cffi.api.FFI`.
- `_cffi_backend.FFI` has **no** `cdef` attribute (verified live), so even the C-level FFI cannot
  reach the parser.
- ⇒ `cffi/api.py:119` (the only place pycparser is actually run) is **unreachable** in this app.
  `cffi/cparser.py:4-7` (`import pycparser`) and the module-global `lock` at
  `cffi/cparser.py:15` are never executed.

**No C compilation, no pycparser, no `cdef` at runtime.** The FFI surface is fully pre-baked.

### 5.2 Thread-safety claims — verified against source

The cffi docs' thread-safety caveats are real but **inapplicable here**:

1. **pycparser is not thread-safe** → `cffi/cparser.py:334-342`:
   ```python
   cffi/cparser.py:334   if lock is not None:
   cffi/cparser.py:335       lock.acquire()     # pycparser is not thread-safe...
   cffi/cparser.py:341       if lock is not None:
   cffi/cparser.py:342           lock.release()
   ```
   with the module-global lock created at `cffi/cparser.py:15`
   (`lock = _thread.allocate_lock()`), and the shared parser at `cffi/cparser.py:37, 51-54`
   (`_parser_cache`).
   → **Never exercised**: the lock lives in `cffi.cparser`, which is only imported when a
   `cffi.FFI` is constructed, and no `cffi.FFI` is ever constructed. `curl_cffi` uses a *compiled*
   ABI module, so it never touches `cffi.cparser` at all.

2. **Per-FFI-instance lock** → `cffi/api.py:60` `self._lock = allocate_lock()` (from
   `cffi/lock.py:10` `from _thread import allocate_lock`), guarding `cdef`/`dlopen`/`typeof`
   (`api.py:80, 117, 142, 178-179, 202, 479, 525-526`). Again: a per-instance lock on an object
   that does not exist here.

3. **What *is* actually concurrent in this app** is `curl_cffi` **session** state, not cffi
   parsing. `user_scanner/core/impersonate.py:13-16` and `phonsint/core/impersonate.py:9-12` keep
   module-level `_sessions` / `_key_locks` / `_warmed` dicts guarded by `threading.Lock`, and
   reuse one `cffi.Session` per `(impersonate, proxy)` key. curl-cffi's `Session` is not documented
   as thread-safe for concurrent use of the same handle — but the upstream code already serialises
   per key. This is a **curl_cffi** concern, and it is *not* a cffi-package concern: cffi here is
   just the transport under the hood, and `_cffi_backend` itself is used in a thread-safe manner
   (libffi call frames are per-call). Nothing in this audit indicates a cffi-level race.

### 5.3 Other runtime candidates screened — all clear

- **Version mismatch guard** (`cffi/api.py:41-53`): satisfied, 2.1.1 == 2.1.1 (§1.2). Would only
  fire if `cffi` and `_cffi_backend` came from different distributions — not possible here since
  they are one wheel (verified against RECORD).
- **delvewheel DLL loading** (`curl_cffi/__init__.py:1-10`): adds `curl_cffi.libs` to the DLL
  search path at import. Windows-only concern; resolves the bundled
  `libcurl-impersonate-*.dll`. Not a cffi concern.
- **ABI/tag mismatch**: `cffi` wheel is `cp314-cp314-win_amd64` and the interpreter is CPython
  3.14.7 — matched. `curl_cffi` is `cp310-abi3-win_amd64` (stable ABI), so it also runs on
  3.14. No friction.
- **Free-threaded (`cp314t`) builds**: cffi *does* publish `cp314t`/`cp315t` wheels, so a
  free-threaded interpreter would be covered. Not currently used.

---

## 6. Verdict

# ISSUES FOUND

**1 issue.** Everything else is clean.

### What is clean

- **Zero direct app usage** — the app never imports `cffi` or `_cffi_backend`; it only names the
  boolean `use_curl_cffi`. Sherlock-V3 has no cffi coupling of its own.
- **Version consistency verified** — `cffi/__init__.py:8` (2.1.1) == `METADATA:3` (2.1.1) ==
  `_cffi_backend.__version__` (2.1.1) == the `cffi/api.py:43` guard.
- **Binary integrity verified** — the on-disk `.pyd` hashes byte-identically to its
  `dist-info/RECORD` entry (`npmyGExg8hqIyvw3Q4be01WehpTtfPER8oaeBm0wMzQ`, 181,248 bytes).
- **No `cdef` at runtime, ever** — `curl_cffi/_wrapper.pyd` is a pre-built ABI-mode module; the
  `cffi` Python package, `cffi.cparser` and `pycparser` are all absent from `sys.modules` after
  `import curl_cffi`. The pycparser thread-safety lock (`cffi/cparser.py:15, 334-342`) is
  therefore dead code in this app.
- **No C compilation at runtime**, no network, no compiler toolchain needed on the target.
- **Desktop / macOS / Linux packaging unaffected** — all required wheels exist.

### The issue

| ID | Severity | Finding |
|---|---|---|
| **CFFI-ANDROID-001** | **HIGH (blocks `flet build apk`)** | **`cffi` 2.1.1 publishes no Android wheel** (`uv.lock:28-84`, `grep -c android` = **0**), while **`curl-cffi` 0.16.3 does** (`uv.lock:116`, `curl_cffi-0.16.3-cp314-cp314-android_24_arm64_v8a.whl`). Because `curl_cffi/__init__.py:63` unconditionally `import _cffi_backend`, and `_cffi_backend` ships **inside the cffi distribution** (`cffi-2.1.1.dist-info/RECORD`), an Android build must **compile cffi 2.1.1 from sdist** (`uv.lock:34`) with the NDK. Compiling `_cffi_backend` is not a guaranteed-success step in a Flet/CI container. |

**Secondary (LOW):** `pyproject.toml:36` requests `target_arch = ["arm64-v8a", "x86_64"]`, but
`x86_64` has **no** curl-cffi Android wheel either (`grep -c "android.*x86_64" uv.lock` = 0) — that
arch needs a full source build of libcurl-impersonate. Either add an `x86_64` Android curl-cffi
wheel upstream, or restrict `target_arch` to `arm64-v8a` (the only arch with a real wheel path).

### Recommended follow-ups (not applied — no app files were modified)

1. **Track upstream cffi for an Android wheel.** cffi 2.1.1 already ships `ios_13_0_arm64_iphoneos`
   and `..._iphonesimulator` wheels (`uv.lock:36-37`) but *no* Android tag — the gap looks like an
   upstream oversight rather than a technical impossibility. Watch
   `https://github.com/python-cffi/cffi/releases`. Re-lock with `uv lock --upgrade-package cffi`
   once published.
2. **Until then, pre-build `_cffi_backend` for Android** (NDK cross-compile of cffi's sdist) and
   inject the resulting `.pyd` into the APK payload, or vendor a `pip install --only-binary`
   shim for the android target.
3. **Consider dropping `x86_64` from `pyproject.toml:36`** unless an emulator build is genuinely
   required — it is the arch with the least wheel coverage in the entire lockfile.
4. **Do not add `cffi` to `pyproject.toml` dependencies.** It is correctly transitive; pinning it
   directly would only re-encode `curl-cffi`'s own requirement and add upgrade friction.
5. **No action needed** for the `cffi` package itself on Desktop targets — the runtime footprint is
   a single 181 KB `.pyd` plus one DLL, and the Python-side `cffi` package is never even loaded.

---

### Files referenced

- `.venv/Lib/site-packages/cffi/__init__.py` (8-9, 14)
- `.venv/Lib/site-packages/cffi/api.py` (34-61, 80, 94-129, 142, 178-179, 202, 479, 525-526)
- `.venv/Lib/site-packages/cffi/cparser.py` (4-7, 15, 37, 51-54, 334-342)
- `.venv/Lib/site-packages/cffi/lock.py` (10)
- `.venv/Lib/site-packages/cffi-2.1.1.dist-info/METADATA` (3, 24, 27)
- `.venv/Lib/site-packages/cffi-2.1.1.dist-info/WHEEL` (3, 4)
- `.venv/Lib/site-packages/cffi-2.1.1.dist-info/RECORD`
- `.venv/Lib/site-packages/cffi-2.1.1.dist-info/top_level.txt`
- `.venv/Lib/site-packages/_cffi_backend.cp314-win_amd64.pyd`
- `.venv/Lib/site-packages/curl_cffi/__init__.py` (1-10, 63, 67-68)
- `.venv/Lib/site-packages/curl_cffi/_wrapper.pyd`
- `.venv/Lib/site-packages/curl_cffi-0.16.3.dist-info/METADATA` (20), `WHEEL` (4), `RECORD`
- `.venv/Lib/site-packages/user_scanner/core/impersonate.py` (5, 13-16)
- `.venv/Lib/site-packages/phonsint/core/impersonate.py` (4, 9-12)
- `uv.lock` (28-84, 32, 34, 35-83, 96-125, 101, 116, 353, 373, 475-476, 486-492, 529-534)
- `pyproject.toml` (7-12, 36)
- `src/core/constants.py` (21, 64), `src/core/state.py` (133)
- `src/screens/home_screen.py` (535-537, 555, 858-864)
- `src/screens/settings_screen.py` (681-682, 953-962)
- `src/services/email_service.py` (207, 251)
- `src/services/user_scanner_compat.py` (8-9, 33-40, 49)
- `src/services/sherlock_service.py` (19, 101, 110, 117, 223, 281, 300-301)
- `src/services/phone_service.py` (1-3, 17, 51, 102, 106)
- `src/main.py` (808, 1071, 1087, 1536)
- `docs/reference/dep-cffi.md` (V2 background doc; `uv.lock:27-34` → now `28-84`)
