# Audit — `src/core/logger_handler.py`

**File:** `src/core/logger_handler.py` (152 lines)
**Scope:** this file only. Consumers cited for evidence only (`src/main.py`, `src/screens/settings_screen.py`, `src/services/*`).
**Env used for verification:** project venv `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv` — Python **3.14.7**, `user_scanner`, `phonsint`, `httpx`, `rich`, `psutil`, `flet` installed there.

---

## 1) File role

Three responsibilities, only one of which works as advertised:

| Lines | Role | Status |
|---|---|---|
| `:21-52` | `MemoryLogHandler` — a `logging.Handler` that keeps the last 500 formatted records in a `collections.deque` so the in-app "Live Activity Terminal" can render them (`src/screens/settings_screen.py:1562`, `:1578`, `:1595`) | Works. Bounded, thread-safe, no rotation (none needed — it is a ring, not a file). |
| `:54-115` | `_QUIET_WHEN_MUTED` + `set_engine_logs()` — a global "mute the OSINT engines" policy driven by `state.log_engine_logs` (default `False`, `src/core/state.py:128`) | **Policy is built on a false premise and is actively harmful** — see 2.C3/N3. Two of six entries are no-ops. |
| `:118-152` | `get_telemetry_snapshot()` — CPU/RAM/RSS/battery string for the terminal header | Works with two small bugs (first `cpu_percent` = 0.0, `bat.percent` may be `None`). |

It is also the natural owner of engine-output capture — **it currently is not** (Section 3).

---

## 2) Correctness findings

### C1 — Thread safety of the ring buffer: **OK, no bug** (refutes the obvious worry)

`src/core/logger_handler.py:34-39`

`logging.Handler.handle()` (stdlib) wraps `emit()` in `self.acquire()/self.release()` — `self.lock` is a `threading.RLock`. So every `emit` from a scan worker thread is serialized against every other, and `deque.append` is additionally atomic under the GIL. The buffer cannot be corrupted by the concurrent writes a 2,521-module scan produces.

`get_logs()` (`:41-44`) does **not** take that lock, so a snapshot can be torn (a line missing, ordering fine). Empirically verified on CPython 3.14.7: 20,000 concurrent `list(deque)` reads against a writer appending continuously produced **0** `RuntimeError: deque mutated during iteration`. Benign for a log viewer. No fix needed.

### C2 — The handler's `level=logging.DEBUG` is unreachable (misleading API)

`src/core/logger_handler.py:26-27` vs `src/main.py:2397-2398`

`logging.basicConfig(level=logging.INFO)` sets the root logger to INFO. `Logger.debug()` short-circuits on `isEnabledFor(DEBUG)` and **never constructs a LogRecord**, so the handler's DEBUG threshold never sees a DEBUG record. The `level` constructor parameter is dead API surface (harmless, but it reads as if DEBUG is captured — it is not).

### C3 — "Verbose" never reaches DEBUG

`src/core/logger_handler.py:105-110`

`set_engine_logs(True)` sets the engine loggers to `logging.NOTSET`, which delegates to the root level — **INFO** (`src/main.py:2398`). So the "engine logs" toggle restores INFO+ but never DEBUG. All three services log progress failures at DEBUG (`src/services/sherlock_service.py:202`, `src/services/phone_service.py:171`, `src/services/email_service.py:288` — all `logger.debug("on_progress failed", exc_info=True)`), and those stay invisible in verbose mode. The toggle copy in `src/screens/settings_screen.py:1706-1711` implies full verbosity.

Fix: `logging.getLogger(name).setLevel(logging.DEBUG if verbose else quiet_level)` (and leave root alone).

### C4 — **The mute table's justification is false, and it suppresses real errors**

`src/core/logger_handler.py:60-63` (rationale) and `:67-74` (table)

The comment claims the engine services' WARNINGs "are per-site outcomes (403, bot wall, rate limit) repeated thousands of times — each one is already classified onto the result card as a badge". Enumerated every `logger.*` call in the three services:

- `src/services/sherlock_service.py` — INFO`:127` (modules loaded), INFO`:158` (cancelled), DEBUG`:202`, EXCEPTION`:218`, WARNING`:245` ("cross-scan pass failed"), WARNING`:247` ("username scan failed for %s"), EXCEPTION`:267`, WARNING`:288` ("hudson scan failed")
- `src/services/email_service.py` — DEBUG`:288`, WARNING`:398`, EXCEPTION`:403`, WARNING`:425`
- `src/services/phone_service.py` — DEBUG`:171`, EXCEPTION`:225`

**Not one of these is per-site.** They are all one-per-scan. Meanwhile the actual thousands of per-site lines are upstream `print()` calls that never enter the logging system at all (Section 3). Net effect of `:68-70`:

- Silenced: genuine failures — "username scan failed for %s", "cross-scan pass failed", "email cross-scan pass failed", "hudson scan failed" — from **both** the console and the in-app terminal.
- Silenced: useful startup context — `sherlock_service.py:127` "user-scanner: loaded %d modules".
- Not silenced: the noise the table was written to suppress.

Recommended: drop the three `services.*` entries (or mute them at WARNING, not ERROR) and suppress the real noise at its source — stdout (Section 3).

### C5 — Two of the six mute entries are no-ops against the installed packages

`src/core/logger_handler.py:71-72`

- `("user_scanner", logging.ERROR)` — the installed `user_scanner` package declares exactly one logger, `logging.getLogger("user-scanner-mcp")` (`.venv/Lib/site-packages/user_scanner/mcp/server.py:23`, `mcp/handlers.py:34`) — hyphenated, and only in the MCP entry point the app never runs. There is **no** logger named `user_scanner`.
- `("phonsint", logging.ERROR)` — `phonsint` contains **no** `getLogger` call at all.

Also missing: `httpcore` (httpx's transport layer) is never muted, so httpcore messages still land in the terminal. httpx itself logs only under `"httpx"` (`.venv/Lib/site-packages/httpx/_client.py:117`).

### C6 — The whole root-filter path is dead code

`src/core/logger_handler.py:76-97`

`_BARE_LOGGING_SOURCES` is an **empty tuple** (`:80`). `any(source in pathname for source in ())` is always `False`, so `_EngineNoiseFilter.filter()` (`:90-94`) always returns `True` — it can never drop a record. The filter is nevertheless installed on the root logger at `:112-115` on every startup.

The premise is also false for the installed engines: `grep -rn "logging\.(info|warning|error|debug)"` over `user_scanner/` and `phonsint/` returns **nothing** outside the MCP package. There are no bare-root records to suppress.

Secondary issue: matching by `record.pathname` substring (`:93-94`) is coarse — any unrelated module whose path contains the string is silenced app-wide.

Recommendation: delete `:76-97` unless the source list is populated; it currently costs a root filter on every root-logged record for zero benefit.

### C7 — The httpx mute is app-global, not engine-scoped

`src/core/logger_handler.py:73` + `src/services/http_client.py:17`

The app's own pooled httpx client (avatars, enrichment, proxied lookups) logs one INFO line per response — `HTTP Request: GET ... "200 OK"` (`.venv/Lib/site-packages/httpx/_client.py:1026`, `:1741`). Muting the `"httpx"` logger to WARNING removes those status lines **app-wide**, not just for engine traffic. Transport failures still surface (httpx logs raised exceptions at WARNING), so the httpx agent's note is *partially* confirmed: what is lost is every response-status line and any way to tell engine traffic from app traffic in the terminal.

If engine-only muting is wanted, filter per-record by URL rather than per-logger, or simply remove the entry once engine output is captured properly (Section 3).

### C8 — Telemetry bugs

`src/core/logger_handler.py:118-152`

- **`:125`** — `psutil.cpu_percent(interval=None)` on its **first** call has no previous sample and returns `0.0`. The first telemetry string in the terminal therefore always reads `CPU: 0.0%`. Fix: prime it once at import/startup, or use `interval=0.1` for the first call.
- **`:147-148`** — `bat.percent` can be `None` on macOS/Windows; `f"{None:.0f}"` raises `TypeError`, swallowed by `:149-150`, so the whole battery line is dropped instead of just the field. Guard with `getattr(bat, "percent", None)`.
- **`:127-128, :134-135, :141-142, :149-150`** — bare `except Exception: pass` gives a silent `"Telemetry: unavailable"` with no diagnosis; a `logger.debug` would cost nothing.
- **`:138`** — `psutil.Process()` is reconstructed on every refresh; cache it.

### C9 — The singleton is created at import but attached late

`src/core/logger_handler.py:52` + `src/main.py:2403`

`in_memory_log_handler` is constructed at module import but only added to the root logger inside `main()`. Records logged during import (before `main()`) never reach the in-app terminal. Low severity, easy to note.

### C10 — Format string duplicated across two files

`src/core/logger_handler.py:28-31` duplicates `src/main.py:2398-2399` exactly (`"%(asctime)s [%(name)s] %(levelname)s: %(message)s"`, `datefmt="%H:%M:%S"`). Two sources of truth for the terminal format that will drift. Export one `LOG_FORMAT`/`LOG_DATEFMT` from this module and use it in `basicConfig`.

### C11 — **No file logging anywhere in the repo**

`grep -rn "RotatingFileHandler|FileHandler|TimedRotating" --include=*.py .` → **zero hits** across the whole project.

The 500-entry ring is the only retention, so: (a) everything before the last ~500 lines is gone, and (b) nothing survives a crash — precisely the diagnostic case this module advertises ("diagnostic terminal", `:1`). This file should own a `RotatingFileHandler(maxBytes=1_048_576, backupCount=3)` attached next to the memory handler at `src/main.py:2402-2404`.

### C12 — Ring buffer size vs. a 2,521-module scan

`src/core/logger_handler.py:24`

**Memory bound is genuinely fine.** `deque(maxlen=500)` discards the oldest on append, so the buffer is hard-capped at 500 formatted strings (~30-60 KB of text plus per-object overhead — well under 100 KB). There is no unbounded growth from scan volume. The only unbounded growth is a *single* record's content (a giant exception payload is stored verbatim); truncating `record.getMessage()` would bound that too.

**But the ring keeps the least useful slice.** At ~1 line per module, 2,521 modules evict the entire startup context (module count, target list, scan start) long before the user opens the terminal. The terminal shows the tail. Fix: a larger ring (2,000-5,000) plus a file log for the durable record, or a separate "pinned summary" region.

### Ring buffer → UI plumbing (who reads, how often, cost)

- Readers: `src/screens/settings_screen.py:1562` (on dialog open), `:1595` (`_refresh_telemetry`, wired to a manual Refresh button at `:1630`), `:1578` (copy-to-clipboard, joins the whole buffer).
- Cadence: **not polled** — refresh is user-triggered only. No high-frequency rebuild.
- Cost: `get_logs()` is O(n), n ≤ 500 → trivial. The `"\n".join(...)` builds a ~30-60 KB string assigned to `ft.Text.value` and re-rendered on each refresh — acceptable, but the whole 500-line blob is re-sent to the Flutter layer instead of appending a delta.
- **Dead slice:** `_TERMINAL_DISPLAY_LINES = 500` (`src/screens/settings_screen.py:1554`) equals the deque `maxlen` (`src/core/logger_handler.py:24`), so the `[-_TERMINAL_DISPLAY_LINES:]` slices at `:1562`/`:1595` are no-ops. It reads as a display cap but is really the buffer size. If the buffer is resized (C12) the cap must be derived from one place — expose `MemoryLogHandler.max_len` and slice with it.

---

## 3) Engine-output gap + minimal fix

### Confirmed facts

1. **The engines barely use `logging`.** `user_scanner` and `phonsint` contain no `logging.info/warning/error/debug` calls outside the MCP package. Their per-site output is plain `print()`.
2. **`user_scanner/core/cross_scan.py` prints with rich colors** at lines 92, 99, 120, 125, 129, 147, 158, 167, **341, 346**, 355, 367, 375, 384, 393, 396, 403, 406, 522, 523. The rich agent's ":341-349" is confirmed: `cross_scan.py:341` and `:346` are the two prints inside `_sweep_targets`.
3. **The app reaches that code.** `src/services/user_scanner_compat.py:448` calls upstream `_sweep_targets(pivots, for_usernames)`.
4. **The compat layer's own docstring is wrong.** `src/services/user_scanner_compat.py:10-11` claims the drivers "stream progress via callbacks instead of printing to stdout (upstream orchestrators are CLI-coupled: rich Progress + print())" — but it imports and calls upstream helpers that still print, so the cross-scan path leaks stdout.
5. **The only stdout capture that exists today is narrow:** `contextlib.redirect_stdout(io.StringIO())` in `src/services/sherlock_service.py:279-292` and `src/services/email_service.py:416-429` — Hudson-Rock only, captured into a `StringIO` that is returned as a string, never logged.
6. **Consequence:** in the Flet desktop app, stdout goes to the launching terminal (or nowhere). `in_memory_log_handler` never sees it, so the "Live Activity Terminal" shows only the app's own lines while the engine's cross-scan narrative is missing. And the `httpx` mute (`:73`) is beside the point — the per-request flood is httpx's own INFO logging, and the engine's actual narrative is invisible.

### Minimal stdlib fix — this file should own it

**(a) Recommended: one stdout tee installed once, at startup (thread-safe).**

Add to `src/core/logger_handler.py`:

```python
import contextlib, io, re, sys, threading

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

class _EngineStdoutTee(io.TextIOBase):
    """Mirror process stdout into the logging system (engine narrative)."""
    def __init__(self, original) -> None:
        self._original = original
        self._lock = threading.Lock()
        self._pending = ""

    def write(self, s: str) -> int:
        with self._lock:
            try:
                self._original.write(s)          # keep the real console output
            except Exception:
                pass
            *lines, self._pending = (self._pending + s).split("\n")
            for line in lines:
                self._log_line(line)
        return len(s)

    def _log_line(self, line: str) -> None:
        clean = _ANSI_RE.sub("", line).rstrip()
        if clean.strip():
            logging.getLogger("engine.stdout").info(clean)

    def flush(self) -> None:
        try:
            self._original.flush()
        except Exception:
            pass

    def isatty(self) -> bool:
        return False          # rich/progress must not emit ANSI + cursor moves
    def writable(self) -> bool:
        return True
```

Install it once in `main()` right after `set_engine_logs(...)` (`src/main.py:2408`):

```python
if not isinstance(sys.stdout, _EngineStdoutTee):
    sys.stdout = _EngineStdoutTee(sys.stdout)
```

and **add `("engine.stdout", logging.ERROR)` to `_QUIET_WHEN_MUTED`** (`:67`) — otherwise the captured narrative instantly floods the terminal that the mute exists to protect, and the mute toggle stops working.

**(b) Narrow alternative, if the tee is considered too broad:**

```python
@contextlib.contextmanager
def capture_engine_stdout(logger_name: str = "engine.stdout"):
    prev = sys.stdout
    sys.stdout = _EngineStdoutTee(prev)
    try:
        yield
    finally:
        sys.stdout = prev
```

**Caveat that must be stated with (b):** `contextlib.redirect_stdout` mutates the process-global `sys.stdout` and is **not thread-safe**. This app runs scans on worker threads (`src/services/sherlock_service.py:259-266` runs a private event loop in a thread; the email/phone services do the same), and `run_hudson` can be invoked alongside the main scan. A redirect around one thread's code will capture another thread's stdout, and the `finally` restore can put back the wrong object. That is why (a) is preferred: installed before any thread starts, so there is no restore race — the only requirement is the lock inside the tee so concurrent writes do not interleave mid-line.

**Two mandatory details:**
- `isatty() -> False` so upstream `rich` does not think it is on a terminal (no ANSI/cursor control sequences written into the log).
- Upstream hardcodes `Fore.MAGENTA` etc. into the printed strings, so ANSI must be stripped with `_ANSI_RE` before storing — otherwise `src/screens/settings_screen.py:1563-1570` renders escape codes as garbage.

### Verdict on the proposed `core/engine_output.py` (rich agent)

**It does not overlap mechanically with this file, but it duplicates this file's responsibilities, and on its own it does not fix the gap.**

1. **`Console(record=True)` does not capture upstream `print()` calls.** `rich.console.Console` only records what is passed to `console.print(...)`; `Console.file` is the underlying stream (`rich/console.py:757-766`) and a plain `print()` goes to `sys.stdout` regardless. To capture upstream prints you must route `sys.stdout` into that stream — i.e. you need the redirect/tee anyway. A `Console(record=True)` on its own captures nothing.
2. **`record=True` is a memory liability for a long scan.** Every render appends to `Console._record_buffer` (`rich/console.py:748`, `:2064-2065`); the buffer is only trimmed by `export_text(clear=True)` (`:2192`, `:2221`). A long-lived console over thousands of prints grows that list without bound — exactly the unbounded-growth risk `MemoryLogHandler`'s ring was designed to avoid.
3. **A second capture path creates a second mute policy and a second buffer**, while the in-app terminal reads only `in_memory_log_handler` (`src/screens/settings_screen.py:1562`) — engine output captured elsewhere would not appear in the terminal unless it is fed into this handler anyway.

**Recommendation: this file should own engine-output capture.** If a richer renderer is wanted later, it should consume this handler's buffer (or the tee installed here) rather than introduce a parallel capture. Do not add a second `Console(record=True)`.

---

## 4) NEW bugs

Findings not in the known context.

| ID | Location | Finding |
|---|---|---|
| **N1** | `src/core/logger_handler.py:71-72` | `("user_scanner", ERROR)` and `("phonsint", ERROR)` mute logger names that **do not exist** in the installed packages (verified in `.venv/Lib/site-packages/user_scanner` and `phonsint`). Two dead entries. |
| **N2** | `src/core/logger_handler.py:80-94` | `_EngineNoiseFilter` is a **guaranteed no-op** — `_BARE_LOGGING_SOURCES` is empty, so `any(...)` is always `False` and `filter()` always returns `True`. The whole root-filter path (`:76-97`) is dead code, installed on every startup. |
| **N3** | `src/core/logger_handler.py:60-63` | The stated rationale for muting the three services to ERROR is **false**: those services contain **no** per-site log call sites (all 15 `logger.*` calls enumerated in 2.C4 are one-per-scan). The mute therefore hides real failures ("username scan failed for %s", "cross-scan pass failed", "hudson scan failed") and the INFO "user-scanner: loaded %d modules", while the actual thousands of per-site lines never enter the logging system. |
| **N4** | `src/core/logger_handler.py:100-110` | Verbose mode never reaches DEBUG (NOTSET → root INFO), so `logger.debug("on_progress failed", exc_info=True)` in all three services stays invisible even with the toggle on. |
| **N5** | `src/core/logger_handler.py:125` | First `psutil.cpu_percent(interval=None)` returns `0.0` → the first telemetry snapshot always reads `CPU: 0.0%`. |
| **N6** | `src/core/logger_handler.py:147-148` | `bat.percent` may be `None` on macOS/Windows → `f"{None:.0f}"` raises `TypeError`, swallowed at `:149-150`, silently dropping the entire battery line. |
| **N7** | `src/core/logger_handler.py:26-27` | `level=logging.DEBUG` is unreachable in practice (root is INFO via `src/main.py:2397-2398`) and misleading. |
| **N8** | `src/core/logger_handler.py:52` | Handler built at import time but attached to root only at `src/main.py:2403` → import-time records are lost from the terminal. |
| **N9** | `src/core/logger_handler.py:73` | The httpx mute also silences the app's own pooled client (`src/services/http_client.py:17`); every response-status line app-wide is lost, and engine traffic becomes indistinguishable from app traffic. |
| **N10** | `src/core/logger_handler.py:64-66` | The comment "httpx logs one INFO line per HTTP request, which is the engines' entire traffic" is wrong — the engines also emit a narrative via `print()`; HTTP logs are not the whole story. |
| **N11** | whole file | **No file logging exists in the repo at all.** The module advertises a "diagnostic terminal" but persists nothing; a crash loses every diagnostic. |
| **N12** | `src/core/logger_handler.py:34-39` | `emit`'s only failure channel is `handleError()`, which writes to `sys.stderr` — with no logger-level visibility. Low severity, but note that a stdout tee would make stderr the sole fallback. |

**Known context — confirm/refute:**

- `:34` `emit` + `@override` — **confirmed optional and stdlib-only.** The venv runs Python 3.14.7, so `from typing import override` works (stdlib since 3.12); `typing_extensions` is also installed. Cosmetic only, no behavior change.
- `:65-73` httpx at WARNING — **confirmed, with the extra finding (N9) that the mute is app-wide, not engine-scoped.**
- Rich agent's "upstream prints bypass this handler" — **confirmed** (Section 3, facts 1-6), and the `core/engine_output.py` proposal is **not** the right shape (Section 3 verdict).
- `src/screens/settings_screen.py:1562-1570` renders these logs — **confirmed**; it also shows the read is manual, not polled.

---

## 5) Improvements, ordered

1. **Own engine-output capture in this file** — install the stdout tee (Section 3a), strip ANSI, `isatty() → False`, and add `("engine.stdout", logging.ERROR)` to `_QUIET_WHEN_MUTED` so the mute toggle still governs the captured noise. Highest value: it is the only change that makes the in-app terminal show what the engines actually did.
2. **Re-derive the mute table from evidence** — remove the no-op `user_scanner` / `phonsint` entries (N1); stop muting `services.*` to ERROR (N3) — mute at WARNING or drop them; add `httpcore` if httpcore noise shows up; reconsider the httpx entry once engine traffic is captured (N9).
3. **Delete the dead root-filter path** `:76-97` unless `_BARE_LOGGING_SOURCES` is populated with real paths (N2).
4. **Add file persistence here** — `RotatingFileHandler(maxBytes=1 MB, backupCount=3)` attached next to the memory handler at `src/main.py:2402-2404`, writing under `%LOCALAPPDATA%/Sherlock-V3/logs/` (N11).
5. **Make verbose actually verbose** — set engine loggers to `DEBUG` in verbose mode instead of `NOTSET` (N4).
6. **Make the buffer lifetime and the display cap one number** — expose `MemoryLogHandler.max_len`, raise it to ~2,000-5,000 for long scans, and slice with it in `src/screens/settings_screen.py:1562`/`:1595` instead of the coincidentally equal `_TERMINAL_DISPLAY_LINES = 500` (C12).
7. **One formatter, one format string** — export `LOG_FORMAT`/`LOG_DATEFMT` from this module and use them in `logging.basicConfig` (`src/main.py:2397-2399`) (C10).
8. **Fix telemetry** — prime `cpu_percent` at import; guard `bat.percent is None`; cache `psutil.Process()`; replace `except Exception: pass` with `logger.debug` (C8, N5, N6).
9. **Cosmetic** — `from typing import override` + `@override` on `emit` (stdlib-only on 3.14.7). Optionally truncate `record.getMessage()` to bound single-record size.

---

## 6) Verdict

**Keep-and-fix, do not rewrite.** The ring buffer itself is sound: bounded (500 entries, ~<100 KB), thread-safe under the stdlib handler lock, and correctly read by the terminal UI at user-driven cadence.

The problems are all in the *policy* half of the file and in what it fails to capture:

- **The mute table does not do what its comment claims** (N3). It suppresses genuine one-per-scan failures while the thousands of per-site lines it was written to suppress never enter the logging system, because the engines emit them via `print()`, not `logging` (confirmed against the installed `user_scanner` / `phonsint`).
- **Two of six mute entries target non-existent loggers** (N1) and the entire root-filter path is a guaranteed no-op (N2).
- **There is no engine-output capture**, so the "Live Activity Terminal" shows the app's own lines and silently omits the engine narrative — including the cross-scan output that `src/services/user_scanner_compat.py:448` provably triggers. The minimal fix is a stdlib stdout tee in this file (Section 3a), not the proposed `Console(record=True)` in a new `core/engine_output.py`, which captures nothing on its own and grows an unbounded `_record_buffer` over a long scan.
- **Nothing is persisted** (N11) — no file handler exists anywhere in the repo, so a crash destroys every diagnostic.
- **Verbose mode never reaches DEBUG** (N4) and the telemetry header has two small live bugs (N5, N6).

Highest-value order: engine-output tee (1) → mute table re-derivation (2) → dead code removal (3) → file logging (4).
