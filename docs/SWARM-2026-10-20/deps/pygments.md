# pygments 2.21.0 — dependency audit (Sherlock-V3)

**Verdict: KEEP as transitive. NO direct use, NO new feature recommended.**
It is a hard requirement of two packages already in the venv (`rich`, `pytest`) and is
never imported by the app. Do not add it to `pyproject.toml`; do not build a UI on it.

---

## 1) Installed verification

| Item | Evidence |
|---|---|
| Version (source) | `.venv/Lib/site-packages/pygments/__init__.py:29` → `__version__ = '2.21.0'` |
| Version (dist-info) | `.venv/Lib/site-packages/pygments-2.21.0.dist-info/METADATA:3` → `Version: 2.21.0` |
| Install path | `.venv/Lib/site-packages/pygments/` (full package: `lexers/`, `styles/`, `formatters/`, `filters/`) |
| C / PyPy perf extension | **ABSENT.** `pygments-2.21.0.dist-info/RECORD` contains **no** `.pyd`, `.so`, `ucele`, or `_speedup` entries; `ls pygments/ucele* pygments/_speedup*` → *No such file*. Pure-Python: `pygments/lexer.py:11` → `import re`; `pygments/regexopt.py` has no C backend (regex optimization is pure Python). |

There is no `pygments/pygments/_speedups.py` in 2.21.0 — the package ships **no** optional
compiled accelerator, so there is no perf story to preserve.

## 2) In-venv consumers

**Hard requirements (must stay installed):**
- `rich-15.0.0.dist-info/METADATA` → `Requires-Dist: pygments>=2.7.2`
  - `rich/syntax.py:24-40` — module-level `from pygments.lexer import Lexer`, `pygments.lexers`,
    `pygments.style`, `pygments.styles`, `pygments.token`, `pygments.util`
  - `rich/traceback.py:23-27` — module-level pygments imports (token styles for tracebacks)
  - `rich/markdown.py:176` → `return cls(lexer_name or "text", markdown.code_theme)`;
    `:552` `code_theme: str = "monokai"`, `:562`, `:567` (`inline_code_theme`),
    `:730-732` CLI `--code-theme` flag. **Markdown fenced code blocks are Pygments-highlighted
    whenever `code_theme` is set.**
- `pytest-9.1.1.dist-info/METADATA` → `Requires-Dist: pygments (>=2.13.0,<3.0.0)`
  - `_pytest/_io/terminalwriter.py:13-17` imports; `:208` `_get_pygments_lexer()`;
    `:216` `_get_pygments_formatter()`; `:242-246` `pygments.highlight(source, lexer, formatter)`
    (used for diff/python output in the pytest terminal).

**Optional only:**
- `httpx-0.28.1.dist-info/METADATA` → `Requires-Dist: pygments==2.*; extra == 'cli'`
  - `httpx/_main.py` — the only non-rich/non-pytest importer (CLI help formatting).

**Not a consumer:** `user_scanner/` and `phonsint/` — `grep -rn "pygments" user_scanner/ phonsint/`
returns **zero** hits. (Both *require* `rich`, which is what pulls pygments into the venv;
`curl_cffi`, `httpx`, `phonsint`, `user_scanner` all list `Requires-Dist: rich`.)

**Why rich is in the venv:** the app itself never imports it —
`grep -rn "import rich\|from rich" src/` → **zero hits**. `rich` arrives transitively via
`httpx` / `curl_cffi` / `phonsint` / `user_scanner`.

**App-level usage:** `grep -rn "pygments\|Pygments" src/ tests/` → **zero hits**.
`pyproject.toml` `[project].dependencies` = `flet`, `flet-ads`, `user-scanner`, `phonsint` only.

## 3) App usage + honest opportunity assessment

**Premise corrections (the task brief was partly wrong):**
- `src/services/report_service.py` (865 lines) contains **no `json.dumps` and no JSON export at
  all**. Its exports are CSV (`:119`), TXT (`:159`), Markdown (`:171`), HTML (`:324`),
  email-Markdown (`:405`), email-HTML (`:491`), PDF (`:584`).
- The JSON export lives in `src/app_shell.py:327-366` — `json.dumps(data, indent=2).encode("utf-8")`
  at `:366`, written to a **file on disk** (a download), never rendered in the UI.
- There is **no "Raw JSON" screen**. `grep -rni "raw json|raw_json|json view|jsonview" src/ tests/`
  → zero hits.

**The only raw-JSON surface that exists today** is a collapsible tile inside the profile detail
dialog: `src/components/profile_detail_dialog.py:919-949` — an `ft.ExpansionTile` titled
`"Raw OSINT Indicators / JSON"` (`:931`), holding a single `ft.Text` (`:943-949`) rendering
`json_str` (built at `:925`, truncated at 20 000 chars at `:926-927`) with
`font_family="Courier New"` and `color=AppColors.TERMINAL_GREEN`, `selectable=True`.
Scan/engine logs are shown the same way in the "Live Activity Terminal" dialog:
`src/screens/settings_screen.py:1562-1570` (same Courier New / `TERMINAL_GREEN` styling),
with a copy button at `:1572-1581`.

**Would `pygments.highlight()` on that JSON be a genuine UX improvement? No.** Reasons:

1. **It would fight the deliberate design language.** Both raw panes are intentionally styled as a
   hacker terminal — monospace `Courier New` on `AppColors.TERMINAL_BG` with green text
   (`profile_detail_dialog.py:946-947`, `settings_screen.py:1568-1569`). Multi-colour token
   highlighting on top of an already-themed terminal surface reads as noise, not improvement.
2. **Flet has no syntax-highlighting control.** `flet/controls/` contains no code/syntax control
   (grep for `highlight|syntax` in `flet/controls/*.py` matches only `buttons.py`,
   `device_info.py`, `theme.py` — none are code rendering). You would have to hand-roll a
   Pygments-token → `ft.TextSpan` mapper (`flet/controls/core/text_span.py:14` `class TextSpan`),
   then ship thousands of individual spans over the wire to Flutter for a pane that can be
   20 000 characters long. Non-trivial new code plus a real render/perf cost.
3. **The payload is small and shallow.** `raw_payload` holds only `enrichment` + `others` OSINT
   metadata (`profile_detail_dialog.py:919-923`) — not a deep log dump where colour pays off.
4. **The actionable need is already met.** The raw pane's real purpose is "copy this"; the copy
   action exists (`copy_text=value` on rows, `_copy_logs` at `settings_screen.py:1572-1581`) and
   colour does not improve copying.
5. **The export path is a file, not a screen.** `app_shell.py:366` writes JSON to disk; the user's
   editor already highlights it. Highlighting it in-app would be redundant.
6. **Pygments is the wrong tool for the log terminal.** `settings_screen.py:1562-1570` renders
   *log lines*, not code — Pygments lexers do not apply.

**Would it help in the Markdown/HTML/PDF reports?** No. `generate_markdown_report`
(`report_service.py:171`) and `generate_html_report` (`:324`) emit *data tables* of sites, not
code. Embedding a highlighted JSON blob in a shareable report would be noise, and the HTML report
is consumed by third parties/email clients, where Pygments inline styles would only bloat output.

**Exact file where such a view would live, if it were ever wanted:** a new
`ft.Text`-span renderer replacing the `ft.Text` at
`src/components/profile_detail_dialog.py:943-949` (plus a helper that maps
`pygments.lexer` tokens to `ft.TextSpan`). **Recommendation: do not build it.**

## 4) Verdict

- **Classification:** pure transitive dependency, used by `rich` (hard) and `pytest` (hard);
  optional for `httpx[cli]`. Not imported by `src/` or `tests/`.
- **Add to `pyproject.toml`?** No. It is already guaranteed present via `rich`/`pytest`, and
  declaring it directly would imply a direct use the codebase does not have.
- **Remove / vendor / pin?** No. Removing it breaks `rich` and `pytest` outright. Pinning it
  is unnecessary (both parents already constrain it: `rich` → `>=2.7.2`,
  `pytest` → `>=2.13.0,<3.0.0`; installed 2.21.0 satisfies both).
- **New feature built on it?** No. The one candidate raw-JSON pane
  (`src/components/profile_detail_dialog.py:943-949`) is already styled coherently, is small,
  and is copy-oriented; a Pygments-highlighted version would require hand-rolling Flet
  `TextSpan` mapping for no genuine gain. **Honest answer to the brief's question: no.**
- **Security/maintenance:** no compiled extension present, so no native-binary surface.
  Upstream 2.21.0 is current and matches the range both parents allow.
