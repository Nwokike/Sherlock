# markdown-it-py — dependency audit (Sherlock-V3)

**Verdict up front:** `markdown-it-py` is a **pure transitive artifact** of `rich`, is **never imported at runtime** by Sherlock-V3 or by any of its direct dependencies, and the app has **no legitimate use for it**. Do not add it as a direct dependency.

---

## 1) Installed verification

| Fact | Evidence |
|---|---|
| Installed version `4.2.0` | `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/markdown_it/__init__.py:4` → `__version__ = "4.2.0"` |
| Dist metadata agrees | `...\.venv\Lib\site-packages\markdown_it_py-4.2.0.dist-info\METADATA:2-3` → `Name: markdown-it-py` / `Version: 4.2.0` |
| Pure-python wheel, no ABI tag | `...markdown_it_py-4.2.0.dist-info\WHEEL:1-4` → `Root-Is-Purelib: true`, `Tag: py3-none-any`; installed by `uv` (`INSTALLER` = `uv`) |
| Sole runtime dep | `mdurl` — `...markdown_it_py-4.2.0.dist-info\METADATA` (`Requires-Dist: mdurl>=0.1.1`); `mdurl 0.1.2` installed at `...\.venv\Lib\site-packages\mdurl\` |
| uv.lock entry + wheel tag | `/home/maikel/.zcode/workspace/default/Sherlock-V3/uv.lock:246-255` — `name = "markdown-it-py"`, `version = "4.2.0"`, `source = { registry = "https://pypi.org/simple" }`; wheel at `uv.lock:254` = `markdown_it_py-4.2.0-py3-none-any.whl` (sha256 `9f7ebbcd…`) |
| Lock chain | `uv.lock:431-441` `rich 15.0.0` → `uv.lock:435` `{ name = "markdown-it-py" }`; `rich` itself is reached only via `phonsint` (`uv.lock:356`) and `user-scanner` (`uv.lock:536`) |
| App root package | `uv.lock:469-490` — `sherlock` (virtual) depends on `flet`, `flet-ads`, `phonsint`, `user-scanner` **only**; `markdown-it-py` is absent from `requires-dist` (`uv.lock:481-487`) and from `pyproject.toml` `dependencies` |

**Confirm: the app never imports it.** `grep -rn "markdown_it|MarkdownIt|from markdown_it" src/ tests/` → **zero hits**. Same for `import rich` in `src/` → **zero hits**.

## 2) In-venv consumer

- **Only importer outside the package itself:** `...\.venv\Lib\site-packages\rich\markdown.py:7` → `from markdown_it import MarkdownIt` (and `:8` `from markdown_it.token import Token`).
- `rich` declares the dependency at `...\.venv\Lib\site-packages\rich-15.0.0.dist-info\METADATA:28` → `Requires-Dist: markdown-it-py (>=2.2.0)`.
- **But `rich.markdown` is itself never used by anything the app runs.** Its only importers in the whole venv are demo/test blocks: `rich/tree.py:206` (inside `if __name__ == "__main__":`) and `rich/__main__.py:8` (CLI demo). `user_scanner` and `phonsint` import `rich.progress`, `rich.table`, `rich.panel`, `rich.console` only — never `rich.markdown`.
- Verified at runtime: `import rich` → `'markdown_it' in sys.modules` is `False`; only `import rich.markdown` pulls it in. So `markdown_it` is **never even loaded** in a normal Sherlock run — it is dead weight on disk (~1 MB incl. `mdurl`).
- Side effect: `markdown_it_py-4.2.0.dist-info/entry_points.txt` installs a `markdown-it` console script → `.venv\Scripts\markdown-it.exe` (CLI renderer; unused by the app).

## 3) App usage + honest opportunity assessment

**Release-notes / changelog display path (the only markdown the app renders):**

1. `src\services\update_service.py:101` — `release_notes=_safe_text(data.get("release_notes"), "")[:10000]` (server payload, truncated to 10 kB).
2. `src\components\update_dialog.py:181-186` — update-available mode:
   `ft.Markdown(data.get("release_notes", ""), selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB, on_tap_link=…)`.
3. `src\components\update_dialog.py:205-210` — up-to-date mode: `ft.Markdown(notes_for(APP_VERSION), …)`, with the bundled text from `src\core\changelog.py:5-34` (plain `•`-bulleted strings) via `src\core\changelog.py:37-39`.
4. Entry points: `src\components\app_header.py:93` ("What's New" chip) and `src\screens\settings_screen.py:1410` (version row → same dialog).

**Key point: `ft.Markdown` parses on the Flutter/Dart client, not in Python.** `...\.venv\Lib\site-packages\flet\controls\core\markdown.py` contains no parser and no `markdown_it` import (grep → zero hits); it ships a `value: str` field (`markdown.py:940`) that the Flet client renders. Python-side markdown-it-py could not replace it.

**Export path (the other markdown surface):**

- `src\services\report_service.py:171` `generate_markdown_report` — **generates** Markdown (not parses it): hand-built strings with a hand-rolled cell escaper `_md_cell` (`report_service.py:95-106`, escapes `|` → `\|`, newlines → space) and `_https_url` allow-listing (`report_service.py:108-118`).
- `src\services\report_service.py:268` `_HTML_TEMPLATE` / `:324` `generate_html_report` — bespoke Jinja2 HTML dossier with an inline gold-branded CSS block (`report_service.py:270-319`).
- `src\services\report_service.py:405` `generate_email_markdown_report` / `:455` `_EMAIL_HTML_TEMPLATE` / `:491` `generate_email_html_report`.
- Wired in `src\app_shell.py:73` and `src\app_shell.py:368-390`; export tiles at `src\app_shell.py:545` (".md") and the HTML tile.

**Honest assessment of the "should we use it?" question — No, on both counts:**

- **Release notes:** the app never *parses* markdown; it hands raw text to `ft.Markdown`, which the client renders. markdown-it-py is a Python CommonMark→HTML/tokenizer library — replacing `ft.Markdown` with it would mean re-implementing Flet's rich markdown widget (tables, code blocks, GITHUB_WEB extension set, `on_tap_link` wiring) in Python and rendering the result as `ft.Text`. Strictly worse, and it would break the client-side rendering. **Current handling is correct and adequate.**
- **Markdown/HTML export:** the app is a Markdown *producer*, not a consumer — a parser is the wrong tool. The one scenario where markdown-it-py would earn its keep (Markdown → HTML conversion) is already covered by Jinja2 templates with inline CSS, which produce a styled, self-contained dossier. markdown-it-py would emit unstyled bare HTML and drop the gold branding, the meta block, and the per-row enrichment layout (`report_service.py:288-318`). **Current handling is adequate.**
- **Adjacent finding (worth flagging to another audit, not this one):** `jinja2` is **not installed** in the venv and **not in `uv.lock`**, so `_JINJA_AVAILABLE` is `False` (`report_service.py:41-47`) and `generate_html_report` / `generate_email_html_report` bail out with `return None` at `report_service.py:338-340` and `:498-500` — the HTML export tiles in `app_shell.py` are effectively dead paths. `reportlab` is likewise absent (PDF dossier disabled). If a real HTML export is wanted, the fix is **adding `jinja2`**, not `markdown-it-py`.

## 4) Verdict

- **Installed & locked:** yes, `4.2.0`, `py3-none-any`, purely via `rich 15.0.0` ← `phonsint`/`user-scanner`.
- **App import:** none. **Runtime import:** none — `rich.markdown` is never reached by app code.
- **Legitimate use in Sherlock-V3: none.** The app generates Markdown (doesn't parse it) and displays Markdown through Flet's client-side `ft.Markdown` widget. markdown-it-py cannot improve either path.
- **Recommendation:** leave it as an undeclared transitive dep of `rich`. Do **not** promote it to a direct dependency in `pyproject.toml`/`uv.lock`. No code changes required; no app files were modified.
- **Only real cleanup lever (optional, out of scope here):** if the team wanted to drop it from the venv entirely, it would require `rich` to drop its hard `markdown-it-py` requirement — not actionable here, and it would risk breaking `rich`'s public `Markdown` API for downstream users of `user-scanner`/`phonsint`.
