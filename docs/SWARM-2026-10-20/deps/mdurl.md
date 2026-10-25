# Dependency Audit: `mdurl` 0.1.2

**Scope:** transitive of `user-scanner`/`phonsint` → `rich` → `markdown-it-py` → `mdurl`.
**Verdict: N/A — pure transitive, correctly scoped, no app role. App code must not import it.**

## 1) Installed verification

- Installed at `.venv/Lib/site-packages/mdurl/` (7 files: `__init__.py`, `_decode.py`, `_encode.py`, `_format.py`,
  `_parse.py`, `_url.py`, `py.typed`) with `.venv/Lib/site-packages/mdurl-0.1.2.dist-info/`
  (`INSTALLER`, `LICENSE`, `METADATA`, `RECORD`, `REQUESTED`, `WHEEL`).
- Version: `mdurl/__init__.py:12` → `__version__ = "0.1.2"`; `mdurl-0.1.2.dist-info/METADATA:3` → `Version: 0.1.2`.
  Runtime import confirms `mdurl 0.1.2`. Lockfile `uv.lock:258-264` → `name = "mdurl"`, `version = "0.1.2"`,
  sdist `mdurl-0.1.2.tar.gz` (2022-08-14) + wheel `mdurl-0.1.2-py3-none-any.whl`.
- **Wheel tag** (`mdurl-0.1.2.dist-info/WHEEL`): `Tag: py3-none-any`, `Root-Is-Purelib: true` — pure Python, no
  ABI/platform pinning; generator flit 3.7.1.
- **Zero dependencies.** METADATA has no `Requires-Dist`; `importlib.metadata.requires('mdurl')` → `None`.
  Stdlib-only imports (`collections.abc`, `string`, `urllib.parse`, `re`, `functools`). A leaf package.
- Public API (`mdurl/__init__.py:1-18`): `decode`, `encode`, `format`, `parse` (alias of `url_parse`), `URL`, plus
  `ENCODE_DEFAULT_CHARS`/`ENCODE_COMPONENT_CHARS`/`DECODE_DEFAULT_CHARS`/`DECODE_COMPONENT_CHARS`.

## 2) Consumer chain

- Grep of all `.venv/Lib/site-packages/**/*.py` for `mdurl` returns exactly one file outside the package itself:
  **`.venv/Lib/site-packages/markdown_it/common/normalize_url.py:8` → `import mdurl`** — the **sole importer**.
  (Other hits are mdurl's own internals: `__init__.py:14-18`, `_parse.py:47`, `_format.py:6`.)
- All three public functions are exercised there: `:23`/`:48` `mdurl.parse(url, slashes_denote_host=True)`;
  `:37` `mdurl.encode(mdurl.format(parsed))`; `:63` `mdurl.decode(mdurl.format(parsed), mdurl.DECODE_DEFAULT_CHARS + "%")`.
- Implementation anchors: `mdurl/_encode.py:45` `encode(string, exclude=ENCODE_DEFAULT_CHARS, *, keep_escaped=True)`
  (percent-encodes unsafe chars, preserves valid `%XX`); `mdurl/_decode.py:33` `decode(string, exclude=DECODE_DEFAULT_CHARS)`
  (regex `(%[a-f0-9]{2})+`, UTF-8 sequences, U+FFFD fallback); `mdurl/_format.py:9` `format(url)` reassembles the
  `URL` NamedTuple (`mdurl/_url.py:6`); `mdurl/_parse.py:297` `url_parse(url, *, slashes_denote_host=False)`.
- Chain: `sherlock` (pyproject.toml) → `user-scanner` 1.5.2.3 / `phonsint` 0.1.0 (`uv.lock:475-476`, `:536`, `:356`
  → `Requires-Dist: rich>=13.0.0`) → `rich` 15.0.0 (`uv.lock:431`, `:435` → `markdown-it-py`) → `markdown-it-py` 4.2.0
  (`uv.lock:246`, `:250` → `mdurl~=0.1`) → `mdurl` 0.1.2. `rich/markdown.py:7-8` imports markdown_it.
- **Latency (runtime-verified):** `import rich` alone does NOT load mdurl; only `import rich.markdown` does. Neither
  `user_scanner/` nor `phonsint/` uses `rich.markdown` (zero hits), so mdurl is installed-but-unloaded in current
  flows — yet markdown-it-py's metadata mandates it, so it must stay installed.

## 3) App usage: none, no opportunity

- Grep over the app tree (excluding `.venv/`) for `mdurl` returns only `uv.lock:250,258,261,263` and prior docs —
  **zero hits in `src/`, `tests/`, or any app module.** The app never imports mdurl.
- The app never imports `rich` or `markdown_it` either (zero `import rich` hits in app source); both arrive only
  via `user-scanner`/`phonsint`.
- **No optimization opportunity.** Zero-dependency, pure-Python, ~11 KB leaf; nothing to vendor, re-pin, or remove.

## 4) Verdict

**N/A — PERFECT as a transitive dependency.** Version verified from installed source + dist-info; one well-defined
consumer exercising `parse`/`encode`/`decode`/`format`; zero third-party deps; pure-Python `py3-none-any` wheel; no
app usage, no app opportunity. Action: none — retain as an ordinary transitive of `markdown-it-py`.
