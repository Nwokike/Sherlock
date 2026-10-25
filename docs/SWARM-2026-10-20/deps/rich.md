# rich 15.0.0 — Installed-Source Audit for Sherlock V3 (Flet GUI)

**Audit date:** 2026-10-20
**Source of truth:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/rich` (the only source consulted — no PyPI docs, no training-data recall)
**Interpreter:** `.venv/Scripts/python.exe` — Python 3.14.7
**Background doc (V2-era, verified not trusted):** `docs/reference/dep-rich.md`

---

## 1) Installed verification

### 1.1 Identity

| Item | Value | Evidence |
|---|---|---|
| Version | `15.0.0` | `.venv/Lib/site-packages/rich-15.0.0.dist-info/` present; `rich/__init__.py:1` docstring |
| Requires | `markdown-it-py>=2.2.0`, `pygments>=2.13.0,<3.0.0` (+ optional `ipywidgets` extra) | `rich-15.0.0.dist-info/METADATA` `Requires-Dist:` lines |
| colorama? | **Not a dependency of rich** | METADATA has no `colorama` entry — the background doc's §3.6 claim is **correct** |

### 1.2 Top-level exports — the background doc is WRONG here

`rich/__init__.py:8`:

```python
__all__ = ["get_console", "reconfigure", "print", "inspect", "print_json"]
```

That is the **entire** public top-level surface. Verified empirically:

```
from rich import Console   -> FAIL: cannot import name 'Console' from 'rich'
from rich import Table     -> FAIL
from rich import Panel     -> FAIL
from rich import Progress  -> FAIL
from rich import Tree      -> FAIL
from rich import Markdown  -> FAIL
from rich import Text      -> FAIL
from rich import Style     -> FAIL
from rich import Theme     -> FAIL
from rich import box       -> OK   (submodule, but NOT in __all__)
from rich import print / inspect / get_console / reconfigure / print_json -> OK
```

> **Correction to `docs/reference/dep-rich.md:31-33`** — it lists "Re-exported classes: `rich.console.Console`, `rich.table.Table`, `rich.panel.Panel`, `rich.progress.Progress`, `rich.text.Text`, `rich.style.Style`, `rich.theme.Theme`, `rich.box`" as *top-level* exports. They are **not** top-level. Any code written against that doc will raise `ImportError` at runtime.

**Correct import paths (all verified importable):**

| Component | Import | Line |
|---|---|---|
| Console | `from rich.console import Console` | `rich/console.py:581` |
| Table | `from rich.table import Table` | `rich/table.py` |
| Panel | `from rich.panel import Panel` | `rich/panel.py` |
| Progress | `from rich.progress import Progress` | `rich/progress.py:1061` |
| Tree | `from rich.tree import Tree` | `rich/tree.py:14` |
| Markdown | `from rich.markdown import Markdown` | `rich/markdown.py:513` |
| Text | `from rich.text import Text` | `rich/text.py` |
| Style | `from rich.style import Style` | `rich/style.py` |
| Theme | `from rich.theme import Theme` | `rich/theme.py` |
| box | `from rich import box` | `rich/box.py` |
| Syntax (bonus) | `from rich.syntax import Syntax` | `rich/syntax.py:243` |
| JSON / pretty / traceback | `rich.json`, `rich.pretty`, `rich.traceback` | verified importable |

### 1.3 `Console(record=True)` + export APIs — signatures verified

`Console.__init__` (`rich/console.py:581-651`) is **keyword-only**:

```python
Console(*, color_system="auto", force_terminal=None, force_jupyter=None,
        force_interactive=None, soft_wrap=False, theme=None, stderr=False,
        file=None, quiet=False, width=None, height=None, style=None,
        no_color=None, tab_size=8, record=False, markup=True, emoji=True,
        emoji_variant=None, highlight=True, log_time=True, log_path=True,
        log_time_format="[%X]", highlighter=ReprHighlighter(),
        legacy_windows=None, safe_box=True, get_datetime=None, get_time=None,
        _environ=None)
```

`record` is at `rich/console.py:638`; the docstring at `rich/console.py:604-606` states it is *"required to call `export_html`, `export_svg`, and `export_text`"*.

| Method | Exact signature | Line |
|---|---|---|
| `export_text` | `export_text(self, *, clear: bool = True, styles: bool = False) -> str` | `rich/console.py:2192` |
| `export_html` | `export_html(self, *, theme=None, clear: bool = True, code_format=None, inline_styles: bool = False) -> str` | `rich/console.py:2244` |
| `export_svg` | `export_svg(self, *, title="Rich", theme=None, clear=True, code_format=CONSOLE_SVG_FORMAT, font_aspect_ratio=0.61, unique_id=None) -> str` | `rich/console.py:2352` |
| `capture` | `capture(self) -> Capture` (context manager; suppresses terminal write) | `rich/console.py:1096` |
| `print_json` | `print_json(self, json=None, *, data=None, indent=2, highlight=True, skip_keys=False, ensure_ascii=False, check_circular=True, allow_nan=True, default=None, sort_keys=False, ...)` | `rich/console.py:1758` |

`clear=True` is the default on all three exports — **the record buffer is drained on first export**. Any GUI panel that exports repeatedly must pass `clear=False` on all but the last call, or copy the buffer.

### 1.4 `Console` is `sys.stdout is None`-safe (important for windowless Flet)

`rich/console.py:757-763`:

```python
@property
def file(self) -> IO[str]:
    file = self._file or (sys.stderr if self.stderr else sys.stdout)
    file = getattr(file, "rich_proxied_file", file)
    if file is None:
        file = NULL_FILE          # rich/console.py:34 imports rich._null_file.NULL_FILE
    return file
```

Empirically verified under `sys.stdout = None`:

```
RICH OK, file=<rich._null_file.NullFile object at 0x...>
HTML len=408  TEXT len=16
TEXT: 'hello from rich\n'
```

`Console(record=True)` never raises when stdout is absent — it records to the in-memory buffer and writes to a null sink. This is the single strongest technical argument for rich in a packaged Flet app.

---

## 2) Where the engine prints, and what happens in a windowless Flet package

### 2.1 The app does NOT reach any rich `Progress`

Installed `user_scanner` rich usage:

| File | Line | What |
|---|---|---|
| `user_scanner/core/orchestrator.py` | 24 | `from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn` |
| `user_scanner/core/orchestrator.py` | 108, 211 | `with Progress(...)` construction sites |
| `user_scanner/core/email_orchestrator.py` | 21, 135, 259 | import + 2 `Progress(...)` sites |
| `user_scanner/core/pdf_generator.py` | 15, 230 | import + `Progress(...)` |
| `user_scanner/__main__.py` | 293-296 | `from rich.console import Console` / `rich.panel.Panel` / `rich.table.Table` / `rich import box` (CLI-only module listing) |

**None of these are reached by Sherlock V3.** The app drives module `validate_` functions directly:

- `src/services/sherlock_service.py:1-7` (docstring): *"Drives user-scanner's module validators directly (not `run_user_full`, which is CLI-coupled: rich Progress + print() + blocking asyncio.run())"*
- `src/services/email_service.py:3`: same for `run_email_full_batch`
- `src/services/user_scanner_compat.py:116` `run_username_scan()` → `:178` `_run_one_user()` → `get_scan_func(mod)` → `await func(username)`. No orchestrator, no Progress.
- Grep confirms `src/services/user_scanner_compat.py` contains **no** `rich` import, **no** `Progress`, **no** `Console` — the only hit is the word in the docstring at `:11`.
- `grep -rn "orchestrator\|run_user_full\|run_email_full" src/` → zero hits.

### 2.2 Can a `Progress` be hijacked? — Not injectable; and moot here

- `rich/progress.py:1101`: `console=console or get_console()`. The `Progress` constructor **does** accept a `console=` kwarg, but `user_scanner` never passes one (`orchestrator.py:108`, `orchestrator.py:211`, `email_orchestrator.py:135`, `email_orchestrator.py:259` all construct `Progress(...)` with columns only). So there is **no per-instance injection point**.
- The only global lever is `rich.reconfigure()` (`rich/__init__.py:39-50`), which mutates `rich.__init__._console.__dict__` in place — and `get_console()` (`rich/__init__.py:23-36`) is exactly the singleton `Progress` falls back to. So `rich.reconfigure(file=..., record=True)` **would** redirect a `Progress`'s output globally.
- **Verdict: not hijackable via the engine's API (no console is passed), but redirectable via `rich.reconfigure()`. In Sherlock V3 this is moot — no `Progress` object is ever constructed.** Any rich `Progress` reaching the GUI would be a regression.

### 2.3 What *does* print on the app's live path — and what happens windowless

`print()` sites reachable from `src/`:

| Installed site | Reached by Sherlock V3? |
|---|---|
| `user_scanner/core/cross_scan.py:341, 346, 355` (in `_sweep_targets`, def at `:333`) | **YES** — `src/services/user_scanner_compat.py:448` `usernames = _sweep_targets(pivots, for_usernames)` |
| `user_scanner/core/cross_scan.py:367, 375, 384` (in `_email_targets`, def at `:362`) | **YES** — `src/services/user_scanner_compat.py:457` `to_scan = _email_targets(ranked, for_emails, usable_email_modules)` |
| `user_scanner/core/result.py:303` (`print(self.get_console_output(configs))` inside `Result.show()`) | NO — the app never calls `Result.show()` |
| `user_scanner/core/orchestrator.py:147, 156, 180, 241, 250` | NO — orchestrator not used |
| `user_scanner/core/cross_scan.py:92-167` (in `run_cross_scan`) | NO — the app re-implements the loop in `user_scanner_compat.py:386+` using the private helpers, not `run_cross_scan` |
| `user_scanner/core/cross_scan.py:393-406, 522-555` (`_print_emails`, `_print_pivots`, `_print_summary`) | NO — not imported by the app |
| `user_scanner/core/hudson.py:30-105`, `loud_prompt.py:29-54` | NO — not used by the app |

Cross-scan is reachable from the GUI: `src/screens/home_screen.py:571-573` (`_toggle_cross_scan`), `src/services/email_service.py:366-372` (gated on `state.cross_scan_enabled`), `src/core/state.py:70`, `src/core/constants.py:68`.

These prints use **colorama** `Fore`/`Style` (raw ANSI), not rich markup — e.g. `cross_scan.py:341-345`:
```python
print(f"{Fore.YELLOW}[!] Username sweep off — checking only the sites pivots named.{Style.RESET_ALL}")
```

### 2.4 Windowless Flet package behaviour — empirically corrected

Measured on this venv (Python 3.14.7):

```
sys.stdout = None
print('hello')   ->  did NOT raise (silent no-op)
```

**`print()` with `sys.stdout is None` is a silent no-op in CPython 3.14 — it does NOT raise `AttributeError`.**

> **Correction to `docs/reference/dep-rich.md:310`** — it claims output "will either silently fail or raise `AttributeError: 'NoneType' object has no attribute 'write'`". The `AttributeError` branch does not occur here; the *silent fail* branch is the only one that fires.

**Operational consequence for Sherlock V3:** in a `flet pack` / PyInstaller `-w` / `pythonw.exe` build, the two cross-scan warnings are **silently discarded**. No crash, no trace, no user-visible signal, and no log record — because they are `print()`, not `logging`. A user whose cross-sweep budget was silently trimmed gets no indication. When stdout *does* exist (dev runs, `flet run` from a terminal), the same lines leak raw colorama ANSI to the developer's terminal.

**rich's behaviour under the same condition is strictly better**: `Console.file` → `NULL_FILE` (§1.4), i.e. *no crash, and the text is still capturable via `record=True`*.

---

## 3) App usage audit

### 3.1 Confirmations (all clean)

| Check | Result |
|---|---|
| `import rich` / `from rich…` in `src/` | **0 real hits.** The grep hits (`src/main.py:50` `STORAGE_ENRICH`, `src/main.py:55` `STORAGE_ENRICHMENT_MODE`, `src/services/enrich_service.py`, etc.) are all substring matches on "**enrich**ment", not the `rich` package. |
| `print(` statements in `src/` | **0 real hits.** Every grep match is a substring false positive: `_email_fingerprint(` (`src/screens/results_screen.py:121, 611-614`), `_username_fingerprint(` (`:150, 815-817`), `_enrichment_fingerprint(` (`:178, 818`), `results_fingerprint(` (`src/services/cache_service.py:370, 391`). |
| `sys.stdout` / `sys.__stdout__` manipulation in `src/` | **0 hits** |
| `ft.WebView` in `src/` | **0 hits** — and `ft.WebView` **does not exist in the installed Flet**. `search_flet_source("WebView")` returns only `WebViewConfiguration` (`flet/controls/services/url_launcher.py:41`), a URL-launcher service option — there is no WebView *control*. The task brief's "the app's existing WebView" premise is **false on both counts**. |
| `Result.get_console_output()` surfaced in the GUI | **0 hits** for `get_console_output` / `console_output` anywhere in `src/` — correctly absent; it returns colorama-ANSI text (`user_scanner/core/result.py:290`) and has no GUI value. |

### 3.2 What the app already does — the hand-rolled equivalents

**a) A structured in-app "terminal" that is NOT engine stdout**

- `src/core/logger_handler.py:21` `MemoryLogHandler` — `collections.deque(maxlen=500)` ring buffer (`:24`), formatted `"%(asctime)s [%(name)s] %(levelname)s: %(message)s"` (`:28-31`).
- `src/core/logger_handler.py:100` `set_engine_logs(verbose)` — mutes `services.sherlock_service`, `services.email_service`, `services.phone_service`, `user_scanner`, `phonsint` to `ERROR` and `httpx` to `WARNING` (`:67-74`).
- `src/core/logger_handler.py:118` `get_telemetry_snapshot()` — CPU/RAM/RSS/battery string.
- The GUI surface: `src/screens/settings_screen.py:1556` `_open_terminal()`, `:1562` `logs_list = in_memory_log_handler.get_logs()[-_TERMINAL_DISPLAY_LINES:]` (500 lines), `:1563-1571` rendered as a flat `ft.Text(..., font_family="Courier New", color=AppColors.TERMINAL_GREEN, selectable=True)`, with Copy (`:1573-1581`), telemetry refresh (`:1587-1597`), Clear (`:1600-1603`).
- Wiring: `src/main.py:80` import, `src/main.py:2403-2404` attaches the handler to the root logger, `src/main.py:2408` + `src/screens/settings_screen.py:585` apply the mute.

**This is a `logging`-based mirror of the engine's *log stream*, not of the engine's *stdout*.** The two cross-scan `print()` warnings (§2.3) never enter this buffer.

**b) Manual JSON rendering that rich `Syntax` would beat**

`src/components/profile_detail_dialog.py:919-940`:
```python
raw_payload["enrichment"] = enrich
raw_payload["others"] = others
json_str = json.dumps(raw_payload, indent=2, ensure_ascii=False, default=str)   # :925
if len(json_str) > 20_000: json_str = json_str[:20_000] + "\n… (truncated)"
...
ft.Text(json_str, size=10, font_family="Courier New",
        color=AppColors.TERMINAL_GREEN, selectable=True)   # :935-941
```
Flat green monospace — no syntax highlighting. `rich.syntax.Syntax` (Pygments-backed, `rich/syntax.py:243`) renders the same JSON with token colors and can be themed to match the app.

**c) Manual recursive flattening that rich `Tree` would beat**

`src/components/profile_detail_dialog.py:25-48` `_stringify()` — a hand-written recursive flattener for list-of-dict values, added because *"a plain `str()`/`join()` explodes on shapes like a list of link dicts"*. It digs for `"url" | "link" | "href" | "value"` keys and joins with `", "`.

`src/components/result_card.py:302-306` merges `v2_extra` (from `others["extra"]`) and `enrichment` into `_merged_profile`, then hand-renders each field (`:309-400`: bio, location, followers/following, company, `is_verified`). `media` is pulled apart by key at `src/components/result_card.py:216-219` (`others.get("media")` → `avatar` / `thumbnail_url`). The generic remainder is rendered as flat key/value `ft.Text` rows.

`rich.tree.Tree` (`rich/tree.py:14`, `.add()` at `:55`) models exactly this nested `extra` / `media` / `links` shape natively — arbitrary depth, arbitrary key names, no bespoke flattener per field.

**d) What rich is NOT needed for**

`src/services/report_service.py` already has first-class Markdown and HTML renderers — `generate_markdown_report` (`:171`), `generate_html_report` (`:324`), `generate_email_markdown_report` (`:405`), `generate_email_html_report` (`:491`), plus inline HTML templates (`:269`, `:456`) and CSV/TXT (`:119`, `:159`). Adding rich here would duplicate existing renderers for no gain.

---

## 4) Concrete GUI-appropriate rich proposals

### P1 — Capture the engine's *stdout* prints (the actual gap)

**Problem:** `cross_scan._sweep_targets` / `._email_targets` prints (§2.3) are invisible in a windowless package and leak ANSI in dev.

**Target:** `src/services/user_scanner_compat.py:448` and `:457` — the two call sites.

**Proposal (no new dependency):** route those two helpers' output into the existing `MemoryLogHandler` ring buffer rather than stdout. The cleanest hook is a tiny `contextlib.redirect_stdout` around the two calls writing into a `io.StringIO`, then `logger.info()` the captured text (colorama ANSI stripped) so it lands in the Live Activity Terminal (`src/screens/settings_screen.py:1556`) that already exists.

**rich alternative (heavier):** a module-level `Console(record=True, file=io.StringIO(), width=100, color_system="truecolor")` in `src/services/user_scanner_compat.py` and `console.capture()` around the calls. Rich's `capture()` (`rich/console.py:1096`) redirects *rich* writes, **not** third-party `print()` — so this only works if you also wrap `contextlib.redirect_stdout`. Given the engines print with colorama (not rich), the `redirect_stdout` + `logger.info` route is the correct one; rich adds nothing here.

### P2 — `rich.syntax.Syntax` for the raw-JSON preview

**Target:** `src/components/profile_detail_dialog.py:925` (json build) and `:935-941` (`ft.Text(json_str, ...)`).

**Proposal:** render with `from rich.syntax import Syntax` (`rich/syntax.py:243`) into a `Console(record=True, width=…, color_system="truecolor")`, `export_html(inline_styles=True)` (`rich/console.py:2244`), and display. **Blocker:** `ft.WebView` does not exist in the installed Flet (§3.1), so HTML cannot be shown natively. The realistic Flet path is `ft.Text` with the ANSI-free `console.export_text(styles=False)` (`rich/console.py:2192`) — which gives plain JSON, i.e. **no visual gain over the current `ft.Text`**. Conclusion: **rich `Syntax` is not worth it for this widget** unless Flet gains a WebView control; keep the current `ft.Text` + Pygments-free JSON. Low priority.

### P3 — `rich.tree.Tree` for the nested `extra` / `media` / `links` payloads

**Targets:**
- `src/components/profile_detail_dialog.py:25-48` (`_stringify`) — the bespoke list-of-dict flattener.
- `src/components/result_card.py:302-306` (`_merged_profile` merge) and `:216-219` (`media` key-poking).
- `src/components/result_card.py:410+` (the generic dynamic key/value rows).

**Proposal:** build a `Tree` (`rich/tree.py:14`) per result — root = site, children = `extra` / `media` / `links`, leaves = scalars — and render via `Console(record=True)` → `export_html(inline_styles=True)`.

**Honest assessment:** same `ft.WebView` blocker as P2. Without a WebView, the Tree collapses to indented plain text via `export_text(styles=False)`, which is *marginally* nicer than the current rows but not compelling, and would regress the per-field copy actions that `_dossier_row` (`src/components/profile_detail_dialog.py:96`) provides. **The current `ft.Row` / `ft.Text` rendering is already better for a Flet GUI than rich-as-text.** Recommend: **do not adopt**; instead, if nested structure needs to be visible, keep it native (Flet `ft.ExpansionTile` already used at `src/components/profile_detail_dialog.py:930`).

### P4 — The one place rich genuinely fits: a memory-Console "engine raw output" panel

**Slot that already exists:** the Live Activity Terminal dialog, `src/screens/settings_screen.py:1556-1700`.

**Current state:** `ft.Text("\n".join(logs_list), font_family="Courier New", color=AppColors.TERMINAL_GREEN, selectable=True)` (`:1563-1571`) — flat, single-colour, unparsed log text.

**Proposal:** add a **second, optional section** below it — an "Engine raw output" view backed by a long-lived `Console(record=True, width=120, color_system="truecolor")` owned by a new small module (e.g. `src/core/engine_output.py`):
1. `Console(record=True, ...)` — `record` at `rich/console.py:638`.
2. Feed it the **ANSI-bearing** engine text (the `get_console_output()`-style strings) — `Console` accepts pre-colored ANSI and normalizes it.
3. `export_html(inline_styles=True)` (`rich/console.py:2244`) → a standalone HTML document.
4. Display it. **Since `ft.WebView` does not exist in this Flet build**, the deliverable is instead: (a) `export_text(styles=False)` → plain `ft.Text` for the in-dialog view, and (b) `export_html(...)` written to a `.html` file and **opened in the system browser** via the app's existing `url_launcher` service (the app already has `ft.UrlLauncher`-style usage — `WebViewConfiguration` at `flet/controls/services/url_launcher.py:41` proves the service exists). That gives a genuinely colored, styled engine log without a WebView control.

**Value:** high — it is the only way to show the engine's *actual* raw output (currently 100% discarded) in a windowless build, and `Console` is provably `sys.stdout=None`-safe (§1.4), unlike `print()`.

**Cost:** one new small module + a hook in the terminal dialog; zero new third-party dependencies (rich is already installed transitively — but see §5 note on pinning it).

### P5 — Do NOT introduce

- `rich.print()` / `rich.get_console().print()` anywhere in `src/` — the background doc's §5.1-§5.5 reasoning holds and is confirmed by the code: `Progress` writes at 10 Hz with `\r` and cursor moves (`rich/progress.py:1101` → `Live`), which no Flet widget can render.
- `rich.reconfigure()` — it mutates the global console singleton (`rich/__init__.py:39-50`) that any `Progress` would use; a stray call could redirect engine progress output into the void.
- rich for report generation (§3.2d — the app already has Markdown/HTML renderers).

---

## 5) Verdict

# ISSUES FOUND

**The app is clean; the *dependency relationship* and the *background doc* are not.**

### Findings

| # | Severity | Finding | Evidence |
|---|---|---|---|
| **F1** | **High (doc)** | `docs/reference/dep-rich.md:31-33` wrongly lists `Console`/`Table`/`Panel`/`Progress`/`Text`/`Style`/`Theme`/`box` as top-level `rich` exports. Only `get_console, reconfigure, print, inspect, print_json` are exported (`rich/__init__.py:8`); `from rich import Console` **raises ImportError**. | verified empirically |
| **F2** | **Medium (doc)** | `docs/reference/dep-rich.md:310` claims `print()` under `sys.stdout=None` "will either silently fail or raise `AttributeError: 'NoneType' object has no attribute 'write'`". On this venv (CPython 3.14.7) it is a **silent no-op only** — no exception. The doc's "silent fail" branch is the accurate one. | verified empirically |
| **F3** | **Medium (runtime gap)** | The two cross-scan `print()` sites the app *does* reach (`user_scanner/core/cross_scan.py:341,346,355` via `user_scanner_compat.py:448`; `:367,375,384` via `:457`) are **silently discarded in a windowless package** and are **ANSI-leaking in dev**. They bypass `MemoryLogHandler` entirely, so they never appear in the Live Activity Terminal. | `src/services/user_scanner_compat.py:448,457`; `src/core/logger_handler.py:21` |
| **F4** | **Low (task premise)** | The brief's "the app's existing WebView" is false — `src/` has **0** `ft.WebView` references, and the installed Flet has **no `ft.WebView` control** (only `WebViewConfiguration` in `flet/controls/services/url_launcher.py:41`). Any rich HTML plan must target `ft.Text` / `ft.Markdown` / system browser. | `search_flet_source("WebView")` |
| **F5** | **Low (hygiene)** | rich is only a **transitive** dependency (via `user_scanner` → `user_scanner/core/orchestrator.py:24`). The app itself imports neither rich nor colorama. Any direct use (P4) requires rich to be declared explicitly in the app's own requirements, not relied on transitively. | `rich-15.0.0.dist-info`, `user_scanner-1.5.2.3.dist-info` |

### What is verified correct

- **No rich import anywhere in `src/`** — the grep hits are all "enrich**ment**" substring false positives.
- **No `print()` statement anywhere in `src/`** — all hits are `_…fingerprint(` substring false positives.
- **No `sys.stdout` manipulation in `src/`** — 0 hits.
- **No rich `Progress` on the app's live path** — the app drives module validators directly (`user_scanner_compat.py:116,178`), never `run_user_full`/`run_email_full_batch`/`run_cross_scan`. The `Progress` console is **not injectable** (`rich/progress.py:1101` → `get_console()`), and the app constructs none anyway.
- **`Result.get_console_output()` is not surfaced in the GUI** — 0 hits in `src/`. Correct; keep it that way (colorama ANSI, no GUI value).
- **`Console(record=True)` is `sys.stdout is None`-safe** (`rich/console.py:757-763` → `NULL_FILE`), and `export_text` / `export_html` / `export_svg` all exist with verified signatures (§1.3).
- **`rich.tree.Tree` (`rich/tree.py:14`) and `rich.markdown.Markdown` (`rich/markdown.py:513`) are present and importable** — but neither currently earns its keep (see P2/P3: no WebView target, and native Flet rows already provide per-field copy actions).

### Recommendation

**Do not adopt rich as a GUI rendering library.** The app's native Flet rendering is already better suited than rich-as-plain-text, and rich-as-HTML has no target control in this Flet build.

**Adopt rich in exactly one place (P4):** a long-lived `Console(record=True)` in a new `src/core/engine_output.py`, used to (a) hold the engine's raw ANSI output that currently vanishes, and (b) produce `export_html(inline_styles=True)` for a system-browser view, with `export_text(styles=False)` as the in-dialog fallback. **And fix the cross-scan print gap (F3)** by bridging those two helper calls into `MemoryLogHandler` — that fix needs no rich at all and should land first.

**Fix the background doc (F1, F2)** so no future agent writes `from rich import Console`.

### Dependency note

rich 15.0.0's own deps are `markdown-it-py>=2.2.0` and `pygments>=2.13.0,<3.0.0` (`rich-15.0.0.dist-info/METADATA`) — both already resolved in the venv (rich imports successfully, verified). rich does **not** depend on colorama; colorama arrives separately via `user_scanner/core/result.py` / `orchestrator.py` / `cross_scan.py`. No version conflict, no upgrade risk, no transitive-conflict hazard from using rich.
