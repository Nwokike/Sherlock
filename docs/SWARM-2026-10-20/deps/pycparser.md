# pycparser 3.11 — Dependency Audit (Sherlock-V3)

**Auditor:** dependency-audit subagent
**Date:** 2026-10-20
**Source of truth:** the installed venv at `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/` (pycparser 3.11, cffi 2.1.1, curl-cffi 0.16.3, Python 3.14.7)
**Background doc (V2-era, verified):** `docs/reference/dep-pycparser.md`
**Package under audit:** `pycparser` 3.11 (`pycparser-3.11.dist-info`, installed by `uv`)

> Scope note: `pycparser` is **not** a direct dependency of Sherlock-V3. `pyproject.toml:6-11` declares only `flet`, `flet-ads`, `user-scanner>=1.5.2.3`, `phonsint>=0.1.0`. `pycparser` arrives transitively: `sherlock → {phonsint, user-scanner} → curl-cffi → cffi → pycparser`. The app itself imports it nowhere. The question this audit answers is: **is pycparser ever loaded into the running process, and is it load-bearing?**

---

## 1) Installed verification

### 1.1 Identity

| Fact | Value | Evidence |
|---|---|---|
| Package name | `pycparser` | `pycparser-3.11.dist-info/METADATA:2` |
| Version (metadata) | `3.11` | `pycparser-3.11.dist-info/METADATA:3` |
| Version (module) | `3.11` | `pycparser/__init__.py:11` → `__version__ = "3.11"` |
| Runtime check | `3.11 C:\...\site-packages\pycparser\__init__.py` | live venv import (§2, T5) |
| Summary | `C parser in Python` | `METADATA:4` |
| Author / Maintainer | Eli Bendersky `<eliben@gmail.com>` | `METADATA:5-6` |
| License | `BSD-3-Clause` (SPDX expression) | `METADATA:7` |
| Requires-Python | `>=3.10` | `METADATA:17` |
| Classifiers | Python 3.10 → 3.15 | `METADATA:12-16` |
| Declared runtime deps | **none** | `METADATA` has no `Requires-Dist` |
| Wheel tag | `py3-none-any` (`Root-Is-Purelib: true`) | `pycparser-3.11.dist-info/WHEEL:4-5` |
| Installer | `uv` | `pycparser-3.11.dist-info/INSTALLER` |

### 1.2 Package layout as installed (`.venv/Lib/site-packages/pycparser/`)

| File | Bytes | Lines | Role |
|---|---|---|---|
| `__init__.py` | 2,816 | 98 | exports `CParser`, `parse_file`, `preprocess_file` |
| `c_parser.py` | 95,003 | 2,464 | hand-written recursive-descent C parser |
| `c_lexer.py` | 25,842 | 721 | regex-based lexer, typedef-scope feedback |
| `c_ast.py` | 34,029 | 1,379 | AST node classes (generated from `_c_ast.cfg`) |
| `c_generator.py` | 22,157 | 610 | AST → C source generator |
| `ast_transforms.py` | 6,512 | 184 | `fix_switch_cases`, `fix_atomic_specifiers` |
| `_c_ast.cfg` | 5,078 | 214 | declarative AST schema |
| `_ast_gen.py` | 11,521 | 359 | code generator for `c_ast.py` |

**Absent (verified):** no `lextab.py`, no `yacctab.py`, no `ply/` package, no `utils/fake_libc_include`, no `examples/` — `ls pycparser/` returns exactly the 8 files above, and `ls pycparser/ | grep -i tab` exits 1.

### 1.3 Background-doc claim verification — parser architecture

The V2 doc's four structural claims were re-checked against the installed 3.11 source. **All four hold; only the cited line numbers are stale.**

| Claim (background doc) | Verdict | Installed-source evidence |
|---|---|---|
| "Hand-crafted recursive-descent parser (pycparser 3.x overhaul)" | **TRUE** | `c_parser.py:1-8` header: `# Recursive-descent parser for the C language.`; `c_parser.py:47` `class CParser:`; docstring `c_parser.py:48-57`: *"Recursive-descent C parser… The parameters after `lexer` are accepted for backward compatibility with the old PLY-based parser and are otherwise unused."* |
| "No PLY transition tables in 3.x" | **TRUE** | `grep -n -i "ply\|yacc\|lex.lex\|tabmodule\|lextab\|parsetab" c_parser.py` returns **only** `c_parser.py:56` (the docstring sentence above) and `c_parser.py:63-66` (legacy ctor kwargs `lextab`, `yacc_optimize`, `yacctab`, `yacc_debug`). No `import ply`, no `yacc.yacc()`, no generated table module anywhere in the package; `lextab.py`/`yacctab.py` do not exist on disk. |
| "pycparser has no preprocessor; only `preprocess_file` shells out to `cpp`" | **TRUE** | `grep -rn "subprocess\|check_output\|Popen\|os.system\|shell=" pycparser/ --include="*.py"` → exactly two hits, both in `__init__.py`: `:13 from subprocess import check_output` and `:44 text = check_output(path_list, universal_newlines=True)` inside `preprocess_file` (`:20-52`). `parse_file` (`:55-98`) defaults `use_cpp=False` (`:56`) and only calls `preprocess_file` under `if use_cpp:` (`:90-91`). There is **no** other cpp invocation in the package. |
| "Lexer typedef-scope handling" | **TRUE** | Scope stack: `c_parser.py:76-84` (`self._scope_stack: list[dict[str, bool]] = [{}]`, comment *"Stack of scopes for keeping track of symbols… whether a name is a type"*); reset per parse at `c_parser.py:101`; `_push_scope` `:120-121`, `_pop_scope` `:123-126`, `_is_type_in_scope` `:148-155`. Callbacks: `_lex_on_lbrace_func` → `_push_scope()` (`c_parser.py:160-161`), `_lex_on_rbrace_func` → `_pop_scope()` (`:163-164`). The parser hands the lexer its callback: `c_parser.py:71-75` (`type_lookup_func=self._lex_type_lookup_func`), defined at `c_parser.py:166-171` → `_is_type_in_scope(name)`. Lexer side: `c_lexer.py:34-37` (docstring), `c_lexer.py:47,52` (ctor param), and the actual promotion `c_lexer.py:209-210` → `if tok_type == "ID" and self.type_lookup_func(value): tok_type = "TYPEID"`. |

**Doc drift found (cosmetic, V2-era citations no longer resolve):**

| Background doc citation | Actual location in installed 3.11 |
|---|---|
| `c_parser.py` "2,752 lines" | 2,464 |
| `c_lexer.py` "866 lines" | 721 |
| `c_ast.py` "1,380 lines" | 1,379 |
| `c_generator.py` "680 lines" | 610 |
| `ast_transforms.py` "187 lines" | 184 |
| `_c_ast.cfg` "215 lines" | 214 |
| `_ast_gen.py` "321 lines" | 359 |
| `c_lexer.py:87-92` for `#line` handling | `c_lexer.py:277-287` (`success()` sets `self._lineno = int(pp_line)` at `:282`, `self._filename = pp_filename` at `:287`); regex at `c_lexer.py:325` |
| `c_parser.py:2738-2748` for `c_ast.Pragma` | `c_parser.py:2224, 2225, 2232`; node at `c_ast.py:1364` |
| `cffi/cparser.py:50-54` `_get_parser()` | `cffi/cparser.py:49-54` (close enough) |
| "Sherlock-V2" paths throughout | V3 layout; `uv.lock` line numbers differ |

No V2 claim was found to be *factually* wrong — only the line numbers and file sizes are from a different install of the same version.

---

## 2) Runtime load evidence (real command outputs)

All commands executed in `/home/maikel/.zcode/workspace/default/Sherlock-V3` with `.venv/Scripts/python.exe` → **Python 3.14.7**.

### 2.1 The three required probes

```
$ .venv/Scripts/python.exe -V
Python 3.14.7

$ .venv/Scripts/python.exe -c "import sys, cffi; print('pycparser' in sys.modules)"
False

$ .venv/Scripts/python.exe -c "import curl_cffi, sys; print('pycparser' in sys.modules)"
False
```

Both expected values confirmed. The `False` after `import cffi` is the interesting one: even importing the `cffi` **package** does not pull pycparser, because `cffi/__init__.py:1-9` only pulls `.api` and `.error`, and `cffi/api.py:58` (`from . import cparser`) sits *inside* `FFI.__init__`, not at module scope.

### 2.2 Deep import of the real dependency chain

```
$ .venv/Scripts/python.exe -c "import curl_cffi.requests as r, sys; print('pycparser' in sys.modules); print([m for m in sys.modules if 'pycparser' in m or 'cffi' in m])"
False
['_cffi_backend', 'curl_cffi._wrapper.lib', 'curl_cffi._wrapper', 'curl_cffi.__version__', 'curl_cffi.const',
 'curl_cffi.utils', 'curl_cffi.curl', 'curl_cffi.aio', 'curl_cffi.requests.exceptions', ... 'curl_cffi']
```

Note what is **absent** from that list: the `cffi` package itself and `pycparser`. Only `_cffi_backend` (the C extension) is loaded.

### 2.3 Positive controls — when *is* pycparser loaded?

```
$ .venv/Scripts/python.exe -c "import cffi.cparser, sys; print('pycparser' in sys.modules)"
True

$ .venv/Scripts/python.exe -c "import cffi, sys; f=cffi.FFI(); print('pycparser loaded after FFI():', 'pycparser' in sys.modules)"
pycparser loaded after FFI(): True

$ .venv/Scripts/python.exe -c "import cffi, sys; f=cffi.FFI(); f.cdef('int foo(int);'); print('pycparser loaded after cdef():', 'pycparser' in sys.modules)"
pycparser loaded after cdef(): True

$ .venv/Scripts/python.exe -c "import pycparser; print(pycparser.__version__, pycparser.__file__)"
3.11 /home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/pycparser/__init__.py
```

**Correction to the background doc's mechanism.** The V2 doc states pycparser is loaded *"because `cffi.cdef()` is never called at runtime"*. That reasoning is directionally right but mechanically imprecise: pycparser is loaded at **`cffi.FFI()` construction**, *before* any `cdef()` call. `cffi/api.py:58-61`:

```python
from . import cparser          # api.py:58  -> cffi/cparser.py:4-7 imports pycparser at module scope
self._parser = cparser.Parser()  # api.py:61
```

and `cffi/cparser.py:4-7`:

```python
try:
    from . import _pycparser as pycparser   # cffi/_pycparser.py DOES NOT EXIST in installed cffi 2.1.1
except ImportError:
    import pycparser                        # <- the branch actually taken
```

(The vendored `_pycparser.py` shim is absent from the installed `cffi/` directory — `ls` shows `_cffi_errors.h`, `_cffi_gen_src.py`, `_cffi_include.h`, `_embedding.h`, `_imp_emulation.py`, `_shimmed_dist_utils.py`, `api.py`, `backend_ctypes.py`, `cffi_opcode.py`, `commontypes.py`, `cparser.py`, `error.py`, `ffiplatform.py`, `gen_src.py`, `lock.py`, `model.py`, `parse_c_type.h`, `pkgconfig.py`, `recompiler.py`, `setuptools_ext.py`, `vengine_cpy.py`, `vengine_gen.py`, `verifier.py` — so cffi 2.1.1 hard-depends on the *external* pycparser package.)

The corrected rule: **pycparser is loaded iff the `cffi` package's declaration compiler is instantiated — i.e. iff someone constructs a `cffi.FFI()` object.** `cdef()` is one consumer of that parser, but not the trigger.

### 2.4 `ffi.cdef()` at runtime in curl_cffi — grep of the installed package

```
$ grep -rn "cdef" .venv/Lib/site-packages/curl_cffi/ --include="*.py"
requests/cache.py:367:            and all(char in "0123456789abcdef" for char in file_path.stem)
requests/utils.py:170:    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz" + "0123456789-._~"
```

**Both hits are false positives** (the substring `cdef` inside `abcdef`). There is **zero** `ffi.cdef(...)` call anywhere in the installed `curl_cffi`.

```
$ grep -rn "^\s*\(import cffi\|from cffi\)" .venv/Lib/site-packages/curl_cffi/ --include="*.py"
(no output)
```

`curl_cffi` does not import the `cffi` package at all. Its binding path is:

- `curl_cffi/__init__.py:63` — `import _cffi_backend  # noqa: F401  # required by _wrapper`
- `curl_cffi/__init__.py:68` — `from ._wrapper import ffi, lib`
- `curl_cffi/curl.py:17` and `curl_cffi/aio.py:8` — `from ._wrapper import ffi, lib`

`_wrapper` is the **out-of-line (precompiled) API-mode** CFFI module: `curl_cffi/_wrapper.pyd` (39,936 B) plus `curl_cffi.libs/libcurl-impersonate-1172405423dc93b7aeed557f2a2ca325.dll` (3,885,056 B) are shipped pre-built in the wheel. The `ffi` object handed to the app is the *compiled* one; `cffi.cdef()` was executed **at curl-cffi build time on the maintainer's machine**, never in this process. Consequently `cffi.api.FFI` is never constructed, `cffi.cparser` is never imported, and pycparser is never loaded.

### 2.5 Whole-application import sweep (the decisive test)

All modules under `src/` were imported into a live interpreter:

```
$ .venv/Scripts/python.exe -c "<import every module under src/ as a package>"
pycountry library not available: No module named 'pycountry'
reportlab not available: No module named 'reportlab'
jinja2 not available: No module named 'jinja2'
APP: imported 53 failed 0
pycparser: False | cffi: False | _cffi_backend: False
```

(The three "not available" lines are the app's own optional-dependency log messages, not failures — 0 import failures.)

And the two direct dependencies that actually reach curl-cffi:

```
$ ... import user_scanner -> pycparser: False | cffi: False | _cffi_backend: False
$ ... import phonsint     -> pycparser: False | cffi: False | _cffi_backend: False
```

`user_scanner/core/impersonate.py:5` and `phonsint/core/impersonate.py:4` both do `from curl_cffi import requests as cffi` — that pulls `_cffi_backend` + `_wrapper` and stops there.

---

## 3) Dependency graph position

```
sherlock (pyproject.toml:6-11)
├── flet / flet-ads
├── user-scanner 1.5.2.3 ── curl-cffi 0.16.3 ── cffi 2.1.1 ── pycparser 3.11  ← (marker: implementation_name != 'PyPy')
└── phonsint 0.1.0 ─────── curl-cffi 0.16.3 ── cffi 2.1.1 ── pycparser 3.11  ← (same)
```

Lockfile evidence (`uv.lock`):

- `uv.lock:373-379` — `pycparser` 3.11, registry source, sdist `pycparser-3.11.tar.gz` (sha256 `d875f09c…`, 113,796 B) + **exactly one** wheel: `pycparser-3.11-py3-none-any.whl` (sha256 `51d5a8ba…`, 51,178 B).
- `uv.lock:28-33` — `cffi` 2.1.1 with `dependencies = [{ name = "pycparser", marker = "implementation_name != 'PyPy'" }]`.
- `uv.lock:96-102` — `curl-cffi` 0.16.3 with `dependencies = [{ name = "certifi" }, { name = "cffi" }]`.
- `uv.lock:353` (`phonsint` block) and `uv.lock:534` (`user-scanner` block) — both list `{ name = "curl-cffi" }`.

Installed-metadata corroboration:

- `cffi-2.1.1.dist-info/METADATA:27` → `Requires-Dist: pycparser; implementation_name != "PyPy"`
- `curl_cffi-0.16.3.dist-info/METADATA:20` → `Requires-Dist: cffi>=2.0.0`

So pycparser sits at **depth 3** from the app (app → user-scanner/phonsint → curl-cffi → cffi → pycparser), and it is a *conditional* dependency of cffi (skipped on PyPy).

### 3.1 Mobile / Android wheel availability

| Package | Wheel tag(s) in `uv.lock` | Android wheel? |
|---|---|---|
| `pycparser` 3.11 | `py3-none-any` (universal, pure Python) | **N/A — installs anywhere**, no compiler, 51 KB |
| `curl-cffi` 0.16.3 | `cp310-abi3-{macosx, manylinux, musllinux, win}`, `cp314-cp314-*`, `cp314-cp314t-*` | **YES** — `uv.lock:116`: `curl_cffi-0.16.3-cp314-cp314-android_24_arm64_v8a.whl` (8,607,323 B) |
| `cffi` 2.1.1 | 48 records: `ios_13_0_arm64_iphoneos`, `ios_13_0_arm64_iphonesimulator`, `macosx_10_15_x86_64`, `macosx_11_0_arm64`, `manylinux2014_{aarch64,ppc64le,s390x,x86_64}`, `musllinux_1_2_{aarch64,x86_64}`, `win32`, `win_amd64`, `win_arm64` (+ `cp314t` free-threaded and `cp315` variants) | **NO** — no android wheel |

`grep -n "android" uv.lock` returns exactly **one** line: `uv.lock:116`, the curl-cffi android wheel.

**The Android gap is on `cffi`, not on `pycparser`.** The app targets Android (`pyproject.toml`: `[tool.flet.android] bundle_id = "ng.kiri.sherlock"`, `target_arch = ["arm64-v8a", "x86_64"]`, `requires-python = ">=3.14"`), and curl-cffi ships a matching `cp314-android_24_arm64_v8a` wheel — but cffi 2.1.1 publishes **no** android wheel, so an Android install must build cffi from its sdist (`uv.lock:34`) with a C toolchain. pycparser, being `py3-none-any`, is the *one* piece of that chain that needs no compilation at all.

Whether that Android sdist build of cffi drags pycparser in as a **build-time** dependency: cffi's own extension machinery ships in the wheel (`cffi/setuptools_ext.py:30` `from cffi.api import FFI`, `cffi/setuptools_ext.py:92,125,169` `from cffi import recompiler`; `cffi/api.py:630 def set_source(...)`), and API-mode compilation necessarily constructs an `FFI` — which, per §2.3, imports pycparser at `cffi/api.py:58-61`. So on Android, pycparser can legitimately be required **at build time**. It is never required at **run time**.

---

## 4) App usage (zero) and what actually loads it

### 4.1 Source audit — zero hits

```
$ grep -rn "pycparser" src/ tests/
(no output; exit status 1)
```

```
$ grep -rn "pycparser" --include="*.py" --include="*.toml" --include="*.json" . | grep -v "/.venv/"
(no output)
```

- `src/` — **0** occurrences.
- `tests/` — **0** occurrences.
- Whole repo (excluding `.venv/` and `docs/`) — **0** occurrences in any `.py` / `.toml` / `.json`.
- `pyproject.toml:6-11` — direct deps are `flet`, `flet-ads`, `user-scanner>=1.5.2.3`, `phonsint>=0.1.0`. No `pycparser`, no `cffi`, no `curl-cffi`.
- `pyproject.toml:44-53` — the `[tool.flet.cleanup] package_files` prune list (`pycountry/locales/**`, `oauthlib/**`, `flask/**`, `werkzeug/**`, `click/**`, `blinker/**`, `itsdangerous/**`, `asgiref/**`) does **not** mention `pycparser` — consistent with it being a live install that is simply never imported.

### 4.2 What actually loads what at runtime

| Import | `pycparser` loaded? | `cffi` pkg loaded? | `_cffi_backend` loaded? |
|---|---|---|---|
| `import cffi` | No | Yes | Yes |
| `import cffi.cparser` | **Yes** | Yes | — |
| `cffi.FFI()` | **Yes** | Yes | Yes |
| `cffi.FFI().cdef(...)` | **Yes** | Yes | Yes |
| `import curl_cffi` | No | No | Yes |
| `import curl_cffi.requests` | No | No | Yes |
| `import user_scanner` | No | No | (lazy) |
| `import phonsint` | No | No | (lazy) |
| all 53 `src/` modules | No | No | No |

**Nothing in Sherlock-V3 constructs a `cffi.FFI()`.** There is no `ffi.cdef()` in `src/` or `tests/`, no API-mode cffi module, no `set_source()` call anywhere in the app or its two direct dependencies. The `cffi` *package* is not even imported — only `_cffi_backend` (the C extension) and `curl_cffi._wrapper` (the precompiled binding) are.

**The only thing in the universe that would load pycparser is a `cffi.FFI()` construction — i.e. API-mode C extension generation.** Sherlock-V3 has none.

### 4.3 Latent landmines found (upstream-owned, not app-facing)

1. **`cffi/cparser.py:19-25`** — `_workaround_for_static_import_finders()` does `import pycparser.yacctab` / `import pycparser.lextab`. **Those modules do not exist in pycparser 3.11** (verified: `ls pycparser/ | grep -i tab` → exit 1; 3.x dropped the PLY tables). The comment says *"This function is never called"*, and it is not called — but if it ever were, it would raise `ImportError` under pycparser 3.x. It is a dormant compatibility shim for pycparser 2.x.
2. **`cffi/cparser.py:206`** — `if pycparser.__version__ < '2.14':` is a **lexicographic string compare**. `"3.11" < "2.14"` is `False` (correct today). A future pycparser `"10.x"` would compare as `True` and wrongly apply the pre-2.14 source workaround to a modern parser. Not app-facing; upstream's bug.
3. **`cffi/cparser.py:4-7`** — the `from . import _pycparser` branch always fails in cffi 2.1.1 (module absent), so the `import pycparser` fallback is always taken. cffi 2.1.1 therefore hard-requires the *external* pycparser package rather than a vendored copy — meaning the `Requires-Dist` in `cffi-2.1.1.dist-info/METADATA:27` is genuinely load-bearing for cffi's `cdef` feature, even though it is inert for this app.

---

## 5) Verdict

### **NEVER-LOADED.** pycparser is dead weight in the Sherlock-V3 install — it is installed, it is not importable-by-accident, and it is not load-bearing.

Supporting facts, each independently verified:

1. **Version confirmed**: 3.11, from both `pycparser/__init__.py:11` and `pycparser-3.11.dist-info/METADATA:3`; live import returns `3.11`.
2. **Background doc architecture claims: all four TRUE.** Hand-written recursive descent (`c_parser.py:1-8, 47`), **no PLY tables** (only legacy kwarg names survive, `c_parser.py:56, 63-66`; no `lextab.py`/`yacctab.py` on disk), **no preprocessor** (the sole `check_output` is `__init__.py:44` inside `preprocess_file`; `parse_file` defaults `use_cpp=False` at `__init__.py:56`), **typedef-scope lexer feedback** (`c_parser.py:76-84, 120-171` + `c_lexer.py:209-210`). Only the V2 doc's *line numbers and file sizes* are stale.
3. **Runtime load: FALSE in every realistic path.** `import cffi` → False; `import curl_cffi` → False; `import curl_cffi.requests` → False; importing all 53 app modules → False; importing `user_scanner` / `phonsint` → False. Even the `cffi` *package* is never imported by the app.
4. **Not load-bearing.** pycparser is reachable only via `cffi.FFI()` construction (`cffi/api.py:58-61` → `cffi/cparser.py:4-7`). `curl_cffi` uses **out-of-line precompiled API mode** (`curl_cffi/__init__.py:63, 68` → `curl_cffi/_wrapper.pyd`), and `grep -rn "cdef"` over the installed `curl_cffi` returns only two false positives inside the literal `"abcdef"`/`"0123456789abcdef"` strings — **zero** `ffi.cdef()` calls. No code path in the app can load it.
5. **App usage: exactly zero.** `grep -rn "pycparser" src/ tests/` → no output. Repo-wide (excluding `.venv/`, `docs/`) → no output. Not in `pyproject.toml` dependencies.
6. **Mobile:** pycparser's wheel is `py3-none-any` — universal, no compiler, installs on Android at negligible cost. The real Android gap in this chain is **`cffi` 2.1.1, which publishes no android wheel** (48 wheel records; tags are ios/macosx/manylinux/musllinux/win only), while `curl-cffi` *does* ship `curl_cffi-0.16.3-cp314-cp314-android_24_arm64_v8a.whl` (`uv.lock:116`). If cffi must be compiled from sdist on Android, pycparser may be pulled in as a **build-time** dependency of cffi's API-mode compiler — never a runtime one.

### Recommendation

No action required. Do **not** add `pycparser` to `[tool.flet.cleanup] package_files` — it is harmless, pure-Python, ~51 KB, and `cffi`'s `Requires-Dist` (`cffi-2.1.1.dist-info/METADATA:27`) means an API-mode build of *any* future dependency would need it anyway; pruning it from the bundle would be a false economy with a real risk of breaking a future cffi-based package. If bundle size ever matters, the lever is `cffi` (or `curl-cffi`), not `pycparser`.

### Evidence index

| Subject | Location |
|---|---|
| Version | `pycparser/__init__.py:11`; `pycparser-3.11.dist-info/METADATA:3` |
| Pure-python wheel | `pycparser-3.11.dist-info/WHEEL:4-5` (`Root-Is-Purelib: true`, `Tag: py3-none-any`) |
| Recursive descent | `pycparser/c_parser.py:1-8`, `:47`, `:48-57` |
| No PLY tables | `pycparser/c_parser.py:56`, `:63-66`; no `lextab.py`/`yacctab.py` on disk |
| No preprocessor | `pycparser/__init__.py:13`, `:20-52` (`:44 check_output`), `:56`, `:90-91` |
| Typedef scope | `pycparser/c_parser.py:76-84`, `:101`, `:120-126`, `:148-171`; `pycparser/c_lexer.py:34-37`, `:47`, `:52`, `:209-210` |
| `#line` handling | `pycparser/c_lexer.py:277-287`, `:325` |
| `c_ast.Pragma` | `pycparser/c_parser.py:2224-2232`; `pycparser/c_ast.py:1364` |
| cffi → pycparser import | `cffi/api.py:58-61`; `cffi/cparser.py:4-7`, `:49-54`, `:206` |
| cffi `cdef` entry | `cffi/api.py:94`, `:119`; `cffi/api.py:630` (`set_source`) |
| curl-cffi binding | `curl_cffi/__init__.py:63`, `:68`; `curl_cffi/curl.py:17`; `curl_cffi/aio.py:8` |
| curl-cffi has no `cdef` | `grep -rn "cdef" curl_cffi/` → only `requests/cache.py:367`, `requests/utils.py:170` (both `"abcdef"` false positives) |
| cffi requires pycparser | `cffi-2.1.1.dist-info/METADATA:27` |
| curl-cffi requires cffi | `curl_cffi-0.16.3.dist-info/METADATA:20` |
| Lock entries | `uv.lock:28-33` (cffi), `:96-102` (curl-cffi), `:116` (android wheel), `:353`, `:373-379` (pycparser), `:534` |
| App deps | `pyproject.toml:6-11`; Android target `[tool.flet.android]` |
| Zero app usage | `grep -rn "pycparser" src/ tests/` → empty |
