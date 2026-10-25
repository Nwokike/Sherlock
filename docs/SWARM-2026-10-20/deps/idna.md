# idna — dependency audit (Sherlock-V3)

Scope: the **installed** `idna` in `.venv` only (source of truth). No app files modified.

## 1) Installed verification

| Item | Value | Evidence |
|---|---|---|
| Version | `3.20` | `idna/package_data.py:1` (`__version__ = "3.20"`), re-exported at `idna/__init__.py:23` |
| dist-info | `idna-3.20.dist-info/METADATA:1-3` | `Name: idna`, `Version: 3.20`, `Requires-Python: >=3.9` |
| Unicode data | `18.0.0` | `idna/idnadata.py:3` → `unicode_version` (`idna/__init__.py:21`) |
| Wheel tag | `py3-none-any` (pure-Python) | `idna-3.20.dist-info/WHEEL:1-4` (`Root-Is-Purelib: true`, `Generator: flit 4.1.0`) |
| uv.lock | `idna 3.20`, sdist + `idna-3.20-py3-none-any.whl` | `uv.lock:228-234` |

### Top-level API (`idna/__init__.py:1-46`)
- `encode(s, strict=False, uts46=False, std3_rules=False, transitional=False) -> bytes` — `idna/core.py:732`
- `decode(s, strict=False, uts46=False, std3_rules=False, display=False) -> str` — `idna/core.py:799`
- `uts46_remap(domain, std3_rules=True, transitional=False) -> str` — `idna/core.py:637`
- `IDNAError(UnicodeError)` — `idna/core.py:70`; subclasses `IDNABidiError` (`:110`), `InvalidCodepoint` (`:114`), `InvalidCodepointContext` (`:118`)
- Also exported: `alabel` (`core.py:524`), `ulabel` (`:558`), `check_bidi` (`:170`), `check_label` (`:442`), `check_nfc` (`:327`), `check_hyphen_ok` (`:309`), `check_initial_combiner` (`:288`), `valid_contextj` (`:339`), `valid_contexto` (`:393`), `valid_label_length` (`:141`), `valid_string_length` (`:156`), `intranges_contain` (`intranges.py`)
- `__all__` frozen at `idna/__init__.py:25-46`.

### CLI presence — YES
- Console script `idna` → `idna.cli:main`: `idna-3.20.dist-info/entry_points.txt:1-2`; binary present at `.venv/Scripts/idna.exe` (47,616 B, also in `RECORD:1`).
- `python -m idna` works via `idna/__main__.py`; `main()` at `idna/cli.py:98`. Smoke-tested: `python -m idna --help` prints usage (encode/decode modes, `--strict`, `--version`).
- Not used by the app; a dev convenience only.

## 2) Consumers in venv (httpx + anyio only)

Whole-`site-packages` grep for `import idna` / `from idna` — exactly four call sites, in two packages:

**httpx 0.28.1** (unconditional, module-level import):
- `httpx/_urls.py:6` `import idna`; `httpx/_urls.py:191` `host = idna.decode(host)` — only when `host.startswith("xn--")`, i.e. decoding an A-label back to U-label for display.
- `httpx/_urlparse.py:25` `import idna`; `httpx/_urlparse.py:390` `return idna.encode(host.lower()).decode("ascii")`; `httpx/_urlparse.py:391` `except idna.IDNAError: raise InvalidURL(...)` — host→A-label on every URL parse.

**anyio 4.15.1** (lazy import inside the function):
- `anyio/_core/_sockets.py:62-69` `idna2008_resolve(host)` → `host.encode("ascii")`, falling back to `import idna` + `idna.encode(host, uts46=True)` only for non-ASCII hosts.
- `anyio/streams/tls.py:147-149` imports `idna2008_resolve` for the TLS SNI `server_hostname`.

Dependency metadata confirms the graph: `httpx-0.28.1.dist-info/METADATA` → `Requires-Dist: idna` (unconditional); `anyio-4.15.1.dist-info/METADATA` → `Requires-Dist: idna>=2.8`; `uv.lock:10` and `uv.lock:206` list `{ name = "idna" }` under anyio and httpx respectively.

No other installed package imports it. `idna` itself has no runtime deps (only `all` extra: ruff/mypy/ty/pytest/hypothesis/coverage).

## 3) App usage (zero) — and why that is correct

- `grep -rn -i "idna" src/ tests/` → **0 matches** (both substring and whole-word counts = 0). The app never imports it.
- `pyproject.toml:7-12` declares only `flet`, `flet-ads`, `user-scanner`, `phonsint`; `idna` is purely transitive (httpx → idna, anyio → idna).
- What idna does *for* the app, indirectly: it is the IDNA codec underneath httpx's URL layer, so **internationalized domain names** in site/manifest URLs are encoded to ASCII A-labels (`xn--…`) before DNS/TLS, and `httpx.URL.host` decodes them back for display. Without it, httpx would reject any non-ASCII host with `InvalidURL`.
- Every URL the app actually builds is already ASCII:
  - Site modules (from `user-scanner`): 6,917 unique URL literals / 4,344 unique hosts scanned — **0 non-ASCII hosts**.
  - App-built URLs are f-strings over ASCII site names, e.g. `src/screens/results_screen.py:416` `f"https://{r.get('domain','')}"`, `src/components/profile_detail_dialog.py:205-210`.
  - User-typed proxy/manifest URLs (`src/screens/settings_screen.py:82-125`) are passed straight to httpx, which does the IDNA encoding internally.
- Conclusion: zero direct usage is the *correct* state, not an omission.

## 4) Verdict

**N/A — no direct-use opportunity (and no action needed).**

- As a transitive dependency: **PERFECT** — single version `3.20` pinned in `uv.lock`, pure-Python `py3-none-any` wheel, no native build, no runtime sub-dependencies, and it is required unconditionally by httpx (the app's HTTP stack) so it can never drift out of the venv.
- As a direct import for the app: nothing to do. The GUI is ASCII-only at the URL layer (0 non-ASCII hosts in 4,344 site domains), and the one case where IDNA matters — a user-entered non-ASCII proxy/manifest host — is already handled inside httpx via `idna.encode` at `httpx/_urlparse.py:390`. Importing `idna` in the app would duplicate that logic for no gain.
- The `idna` console script (`Scripts/idna.exe`, `python -m idna`) is a harmless dev/debug tool; it can stay installed.
