# Audit — `src/services/report_service.py`

File: `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/services/report_service.py` (865 lines)
Engine: `user-scanner 1.5.2.3` (`.venv\Lib\site-packages\user_scanner`) — the only truth
Removed by owner: `reportlab`, `pillow`, `svglib` (and therefore `jinja2`, `lxml`) — verified absent:
`importlib.import_module` fails for `reportlab`, `jinja2`, `pillow`, `svglib`, `lxml`.
UI: `flet 1.0.4` (`.venv\Lib\site-packages\flet`)
Read-only audit. Nothing was modified. All runtime claims below were executed against the venv.

---

## 1) File role

`ReportService` is the **export layer** of Sherlock-V3. It turns scan results into downloadable
bytes. It owns no I/O (no file writes, no path handling, no MIME declarations) — it returns
`bytes | None` and the shell writes them to disk.

| Unit | Lines | Status today |
|---|---|---|
| Module docstring (claims reportlab PDF + HTML exports) | `:1-6` | **factually wrong** — none of the PDF/HTML exports can run |
| Optional-import blocks (reportlab, jinja2) + import-time warnings | `:20-47` | both `False`; emits 2 warnings on every app start |
| Jinja-only helpers (`_human_date_filter`, `_jinja_env`) | `:50-63` | dead (`_JinjaEnvironment` name unbound without jinja2) |
| Enrichment key sets + date humaniser | `:66-87` | dead (enrichment service is a stub) |
| Row normalisation helper | `:90-92` | live (CSV, MD) |
| Markdown cell escaper | `:95-105` | live (MD); incomplete (no `<`/`>` escaping) |
| URL scheme allow-list (`_https_url`) | `:108-116` | dead — only used by the HTML/PDF paths |
| **CSV export** | `:119-156` | works, but bespoke schema + **no CSV formula-injection guard** |
| **TXT export** | `:159-168` | works; `username` parameter is dead |
| **Markdown dossier** | `:171-246` | works (stdlib only) — the only dossier format still alive |
| HTML CSS core + Jinja template | `:249-321` | dead |
| **HTML dossier** | `:324-402` | dead — returns `None` |
| Email Markdown export | `:405-452` | works (stdlib only) |
| Email HTML template + generator | `:455-562` | dead — returns `None` |
| PDF row cap / brand palette / **PDF dossier** | `:565-863` | dead — returns `None`; `_gold_palette` raises |

Callers (only two files):
- `src/app_shell.py:74-84` — email-mode `md`/`html` branch
- `src/app_shell.py:290-311` — `pdf` tile
- `src/app_shell.py:318-325` — `csv` tile
- `src/app_shell.py:369-408` — `md`/`html` tiles
- `src/app_shell.py:410-415` — `txt` tile

Export tiles live in `src/app_shell.py:507-566`; the per-format dispatch is `app_shell.py:237-471`.
No test file references `report_service` (`tests/` contains no import of it).

**Structural verdict: ~647 of 865 lines (75%) exist only to serve `reportlab`/`jinja2` or the
permanently-disabled enrichment feature.** By the owner's rule ("exports must be exactly the
exports the wrapped engine provides"), the file's correct shape is a thin, dependency-free
adapter over `user_scanner.core.formatter`, not a document generator.

---

## 2) Dead / broken map (what fails today, and how)

Import-time truth (executed):

```
WARN:services.report_service:reportlab not available: No module named 'reportlab'
WARN:services.report_service:jinja2 not available: No module named 'jinja2'
REPORTLAB_AVAILABLE = False
JINJA_AVAILABLE = False
```

| Function / site | Today | Exact behaviour (verified by execution) |
|---|---|---|
| `generate_pdf_dossier` `:584-863` | **returns `None`** | Guard `:605-606` (`not _REPORTLAB_AVAILABLE`) fires first → `None`. Caller `app_shell.py:307-310` raises `RuntimeError("PDF generation returned empty output")` → user sees **"Failed to save: PDF generation returned empty output"** (10 s error toast, `app_shell.py:460-469`). The PDF tile is still offered at `app_shell.py:519-526`. |
| `_gold_palette` `:570-581` | **raises `RuntimeError`** | `raise RuntimeError("reportlab unavailable — PDF palette requires reportlab")` at `:572-573`. **Unreachable today** — its only caller is `generate_pdf_dossier:611`, which is after the `:605` early return. A raise site that can never be hit. |
| `generate_html_report` `:324-402` | **returns `None`** | Guard `:338-340` → `logger.warning("jinja2 unavailable — HTML dossier skipped")` → `None`. Caller `app_shell.py:397-400` raises `RuntimeError("HTML generation returned empty output")` → **"Failed to save: HTML generation returned empty output"**. The HTML tile is still offered at `app_shell.py:551-558`. |
| `generate_email_html_report` `:491-562` | **returns `None`** | Guard `:498-500` → `None` → `app_shell.py:283-288` raises `ValueError("PDF dossiers are username-mode — email results export as CSV, JSON, TXT, Markdown, or HTML")`. **Misleading error:** the real cause is "jinja2 missing", and the message tells the user HTML *is* an option. The email-mode info tile (`app_shell.py:509-517`) also advertises HTML. |
| `_jinja_env` `:59-63` | **dead / would `NameError`** | `_JinjaEnvironment` is only bound when the jinja2 import at `:43` succeeds. Called from `:385` and `:550`, both unreachable. Called directly without jinja2 it raises `NameError`, not a clean error — the only protection is the `_JINJA_AVAILABLE` checks at `:338` / `:498`. |
| `_human_date_filter` `:50-56` | dead | Only consumer is the Jinja `human_date` filter registered at `:62`. |
| `_https_url` `:108-116` | dead | Callers are `:349` (HTML), `:526` (email HTML), `:724` (PDF) — all dead. |
| `_IDENTITY_KEYS` / `_DATE_KEYS` / `_fmt_ident` `:66-87` | dead | Only consumers are the enrichment blocks `:218-234` (MD), `:356-375` (HTML), `:769-839` (PDF). |
| MD enrichment block `:218-234` | **permanently dead** | `state.enrichments` is *always* empty: `EnrichService.is_available` is a **property returning `False`** (`src/services/enrich_service.py:17-18`) and `src/main.py:1183` returns early on it; `socid_extractor` is not installed. `enrichments.get(url)` at `:221` can therefore never return data. |
| PDF enrichment + avatar embed `:769-839` | permanently dead | Same reason, plus `ensure_cached_avatar` (`src/services/cache_service.py:243`) is unreachable — the avatar cache is warmed from `data.get("image"/"avatar"/"photo")` inside the `if data` branch of `src/main.py:1223-1235`, which never runs. |
| PDF-only module imports `:10` (`io`), `:13` (`Path`), `:14` (`_xml_escape`) | dead | Used only at `:649`, `:797`, `:704`/`:790`/`:805` — all inside the PDF path. `datetime`/`UTC` (`:12`) and `SITES_TOTAL_FALLBACK` (`:16`) are used only by the MD/HTML/PDF renderers. |
| `import io` `:127` | redundant | `io` is already imported at module level `:10`; the local re-import shadows it for no reason. |
| `generate_txt_report(username, ...)` `:159-168` | works, 1 dead param | `username` is **never referenced** in the body. Caller `app_shell.py:412-415` passes it. |
| MD double-escape `:230-234` | latent bug | `_md_cell` is applied to the value (`:231`) **and then again** to the joined detail (`:234`) → a literal `\|` in a value becomes `\\|` → broken Markdown cell. Currently masked because the enrichment path is dead. |
| MD `Time (s)` column `:206`, `:213` | **always empty** | `query_time` is hard-coded `None` in the producer: `src/services/sherlock_service.py:358`. The upstream `Result` carries no timing at all. |
| Report cache for md/html/pdf | **never hits** | `save_cached_report` computes its path **without** the scan signature: `src/services/cache_service.py:415` calls `cached_report_path(mode, query, found, ext)` while `load_cached_report` at `:403` calls `cached_report_path(mode, query, found, ext, sig)`. `results_fingerprint` (`:370-384`) mixes `sig` into the hash → save key ≠ load key → every export re-renders and the cache directory grows. (Adjacent file, but it is the only caching `report_service`'s output had.) |
| Stale-cache hazard (md/html/pdf) | real | A dossier rendered *before* the dependency removal is still served by `load_cached_report` (`app_shell.py:292`, `:374`) — the app can hand the user a bespoke HTML/PDF dossier it can no longer produce. |

**Summary:** of the seven public generators, **four are dead** (`generate_pdf_dossier`,
`generate_html_report`, `generate_email_html_report`, and — via the stub — every enrichment
branch). Two export tiles are therefore *guaranteed* to fail for every user, every time.

---

## 3) Surviving-format correctness (CSV / TXT / MD / JSON)

### 3.1 CSV — `generate_csv_report` `:119-156`

**CRITICAL — no CSV formula-injection guard.** The engine ships one:
`user_scanner/core/result.py:26-33` (`_neutralize_csv_cell`, prefixes `'` for cells starting
with `= + - @ \t \r \n`) and applies it to every field at `core/result.py:218`. The app's CSV
writer (`:131-155`) has **no such guard**, and the first column is the **user-supplied
username**. Executed proof:

```
username,name,url_main,url_user,exists,http_status,response_time_s
=cmd|calc!A0,GitHub,,https://github.com/alice,Claimed,,
```

The `=` cell is written verbatim → Excel/Sheets/LibreOffice evaluate it on open (CWE-1236).
This is the single highest-value defect in the file: it is a *working* export with a *security*
hole, and the fix is free if the engine's own exporter is used.

**Schema is bespoke and loses upstream data.** App columns (`:132-141`):
`username, name, url_main, url_user, exists, http_status, response_time_s`.
Engine `CSV_FIELDS` (`core/result.py:23`): `username, category, site_name, status, url, extra,
media, reason`. The app's schema **drops `extra`, `media`, `reason`** (the only fields that carry
actual intel: email recovery, phone, avatars, WAF reasons) and **invents three columns that are
structurally always empty**:

| App column | Why it is always empty |
|---|---|
| `url_main` | hard-coded `""` at `src/services/sherlock_service.py:354` |
| `http_status` | hard-coded `""` at `src/services/sherlock_service.py:357` (upstream `Result` has no HTTP status field) |
| `response_time_s` | `query_time=None` at `src/services/sherlock_service.py:358` |

**`exists` is a misnomer** — it holds `r.status`, i.e. the app vocabulary
`"Claimed" / "Available" / "WAF" / "Error"` (`src/services/sherlock_service.py:306-317`), not a
boolean. The engine's vocabulary is `"Found" / "Not Found" / "Error" / "Skipped"`
(`core/result.py:74-81`).

**Buckets are flattened without a bucket column** (`:143` `found + not_found + errors`) — a
consumer cannot distinguish a claimed account from a WAF-blocked site except by parsing the
`exists` text.

**Other CSV notes:** encoding is raw UTF-8 with no BOM and no declared MIME type (the file never
declares content types; the caller only supplies a file extension at `app_shell.py:422-424`).
No size guard is needed — a full 2746-site scan yields ~2746 rows.

### 3.2 TXT — `generate_txt_report` `:159-168`

Works. Executed output:

```
'https://github.com/alice\nhttps://x.com/alice\nhttps://foo.com/alice\nTotal Detected : 3\n'
```

Classic Sherlock URL-list shape. Issues: the `username` parameter is dead (`:159`); the "Total
Detected" count is the bucket size (correct); there is no header line, so a shared TXT file has
no target attribution (a one-line header using the currently-unused `username` would fix it).

### 3.3 Markdown — `generate_markdown_report` `:171-246`

The only dossier generator that still functions (stdlib only, zero extra dependencies).
Executed output confirms it renders.

- `Returns None` when there are no rows (`:187-188`) → caller `app_shell.py:397-400` turns that
  into `RuntimeError("MD generation returned empty output")` — an error toast where "nothing to
  export" would be right.
- **"Platforms checked" is wrong** (`:196-197`): the caller passes
  `checked_sites=progress.checked_sites or len(progress.found)` (`app_shell.py:394-395`), so
  when `progress.checked_sites` is 0 the metric reports the **found count** as "platforms
  checked". The fallback `len(found)+len(not_found)+len(errors)` is never reached in the app.
- `Time (s)` column always empty (see §2).
- Enrichment block `:218-234` permanently dead (see §2).
- `_md_cell` (`:95-105`) escapes `|` and newlines but **not `<` / `>`** — a platform name or
  enrichment value containing markup is live HTML when the Markdown is rendered as HTML. The
  (dead) HTML path was protected by Jinja autoescape; the Markdown path is not.
- "Errors / WAF" section `:236-241` prefers `r.context` over `r.error_type`; `context` holds
  `pivot_source` (`src/services/sherlock_service.py:359`), so a pivot row can be labelled with a
  pivot source as if it were an error cause. `error_type` holds the upstream reason and is the
  better first choice.

### 3.4 JSON — *not in this file*

There is **no JSON export in `report_service.py`**. The JSON tile is served by inline code in
`src/app_shell.py:327-366` with a bespoke object `{username, total_sites, checked_sites,
found[], not_found[], errors[]}` whose rows are a hand-picked subset
(`name, url_main, url_user, status, http_status, response_time_s, tags`) — again dropping
upstream `extra`/`media`/`reason`, and again emitting the three always-empty fields. It is
off-engine too, just implemented in a sibling file.

### 3.5 Share / clipboard

`report_service.py` has **no share or clipboard path at all** — it never touches the clipboard,
the platform share sheet, or the filesystem. The app's copy/share actions (`app_shell.py:145-194`
copy, `:196-235` share) operate directly on `r.url_user`. Consequence: the MD docstring's claim
"**Shareable** Markdown dossier" (`:180`) is inaccurate — nothing ever shares the bytes; the app
only writes them to a file. The same applies to the HTML/PDF "dossier" wording.

### 3.6 Adjacent write path (not this file, but load-bearing for these exports)

- `app_shell.py:421-426` passes `allowed_extensions=[ext]` **without**
  `file_type=FilePickerFileType.CUSTOM`; per flet 1.0.4
  (`.venv\Lib\site-packages\flet\controls\services\file_picker.py:283-304`) `allowed_extensions`
  "has effect only if `file_type` is `FilePickerFileType.CUSTOM`" — the extension filter is
  decorative today.
- `app_shell.py:437-441` re-writes the file on desktop although flet already wrote `src_bytes`
  to the chosen path (`file_picker.py:288-294`) — a redundant second write.
- The file name is slugified safely (`app_shell.py:42-55`, `_safe_filename`, incl. Windows
  reserved names) — no path-traversal surface. `report_service.py` itself never builds a path.

---

## 4) Engine-native exports vs. app tiles

### 4.1 What the installed engine actually exposes

`user_scanner.core.formatter` (`.venv\Lib\site-packages\user_scanner\core\formatter.py`, 41 lines
total) exposes **exactly five** names:

| Symbol | Signature | Location | Dependency flag |
|---|---|---|---|
| `CSV_HEADER` | `str` (= `",".join(CSV_FIELDS)`) | `core/formatter.py:6` | stdlib only |
| `into_json` | `into_json(results: List[Result]) -> str` | `core/formatter.py:9-10` | stdlib only |
| `get_json_data` | `get_json_data(results: List[Result]) -> list` | `core/formatter.py:13-15` | stdlib only |
| `into_csv` | `into_csv(results: List[Result], include_header: bool = True) -> str` | `core/formatter.py:18-19` | stdlib only |
| `into_pdf` | `into_pdf(results: List[Result], target: str = "Target", scan_type: str = "Unknown", total_modules: Optional[int] = None, include_media: bool = True, version: Optional[str] = None) -> bytes` | `core/formatter.py:22-39` | **requires `reportlab`** — delegates to `user_scanner/core/pdf_generator.py:246-258`, which raises `ImportError("ReportLab is required for PDF generation…")` when `REPORTLAB_AVAILABLE` is False (`pdf_generator.py:22-28`). `PIL` (`pdf_generator.py:30-34`) and `svglib` (`:36-40`) are optional media embedders. |

Per-result exports on `user_scanner.core.result.Result`:

| Symbol | Location | Notes |
|---|---|---|
| `CSV_FIELDS = ["username","category","site_name","status","url","extra","media","reason"]` | `core/result.py:23` | the engine's canonical CSV schema |
| `_neutralize_csv_cell(value)` | `core/result.py:26-33` | formula-injection guard |
| `Result.to_dict() -> dict` | `core/result.py:184-191` | full row; `is_email` rows get `email` instead of `username` (`:188-190`) |
| `Result.to_json() -> str` | `core/result.py:196-198` | `json.dumps(self.to_dict(), indent=4)` |
| `Result.to_csv() -> str` | `core/result.py:200-224` | guard applied at `:218` |
| `Status.to_label(is_email=False)` | `core/result.py:74-81` | `"Found" / "Not Found" / "Error" / "Skipped"`; `"Registered" / "Not Registered"` for email |

The engine's own CLI is the reference for how these are meant to be called:
`user_scanner/__main__.py:721` (`formatter.into_pdf(...)`), `:738` (`formatter.get_json_data(...)`),
`:782` (`formatter.into_csv(..., include_header=not has_content)`).

**The engine provides CSV, JSON and PDF. It provides no Markdown, no HTML, no TXT, no "dossier".**

### 4.2 Tile-by-tile mapping

| App tile (`src/app_shell.py`) | `format_type` | Today | Engine-native call | Verdict |
|---|---|---|---|---|
| PDF Intelligence Dossier `:519-526` | `pdf` | `report_service.generate_pdf_dossier` → `None` → RuntimeError | `formatter.into_pdf(results, target=…, scan_type=…, total_modules=…)` (`core/formatter.py:22-39`) → **also dead** (needs `reportlab`, `pdf_generator.py:254-258`) | **DELETE TILE** — no engine PDF without `reportlab`; the owner removed it |
| CSV Spreadsheet `:527-534` | `csv` | `report_service.generate_csv_report` (bespoke, unguarded) | `formatter.into_csv(results, include_header=True)` (`core/formatter.py:18-19`) | **REPLACE** — engine schema + guard |
| JSON Data `:535-542` | `json` | inline `json.dumps` in `app_shell.py:327-366` (bespoke) | `formatter.into_json(results)` (`core/formatter.py:9-10`) or `get_json_data(results)` (`:13-15`) | **REPLACE** |
| Markdown Report `:543-550` | `md` | `report_service.generate_markdown_report` (works) | — none — | **KEEP (slimmed)** *or* **DELETE** under strict parity; it adds zero dependencies |
| HTML Dossier `:551-558` | `html` | `report_service.generate_html_report` → `None` → RuntimeError | — none — | **DELETE TILE** — bespoke + `jinja2` |
| Plain Text List `:559-566` | `txt` | `report_service.generate_txt_report` (works) | — none — | **KEEP** — classic Sherlock list, stdlib only |

### 4.3 The prerequisite nobody has done: the app throws the engine `Result` away

Engine-native export is *impossible* today because the app never keeps the upstream objects:

- Username scan: `src/services/sherlock_service.py:183-189` receives the engine `Result` in
  `_on_result`, appends it to a **function-local** `raw_results` list (`:181`) that is only used
  as the cross-scan seed (`:232`) and is then dropped; `_map_username_result` (`:299-367`)
  projects it into a **lossy** `SiteResult`.
- Email scan: `src/services/email_service.py:_map_result` (`:112-160`) maps the engine `Result`
  into `EmailResult` and keeps only `others` (`:128-133`) — the raw result is discarded.
- Phone scan: `src/main.py:1810-1816` builds dicts from `phonsint` results with the same
  `others` shape — the raw `phonsint` result is discarded.

Reconstructing an engine `Result` from `SiteResult` is possible but lossy: `reason` is kept only
for Error/WAF rows (`src/services/sherlock_service.py:362`), `category` survives only as
`tags[0]` (`:348`), `extra`/`media` survive only inside `ids_data` (`:341`), and the upstream
`http_status`/timing fields do not exist at all. **Correct fix: carry the raw object** — add a
field to the app dataclasses and set it in the mapper (2 lines each):

- `src/services/sherlock_service.py:30-44` → add `raw: Any = None` to `SiteResult`; set
  `raw=r` in `_map_username_result` (`:352-362`).
- `src/services/email_service.py:38-48` → add `raw: Any = None` to `EmailResult`; set it in
  `_map_result` (`:143-160`).
The phone engine has a parallel native surface worth using for the phone CSV/JSON path
(`phonsint/core/result.py:20` `CSV_FIELDS`, `:176` `to_dict`, `:182` `to_json`, `:186` `to_csv`
with its own guard at `:23`; `phonsint/__main__.py:54` `export_results(results, file_path,
fmt="json")`). The app's phone/email CSV is built inline in `app_shell.py:95-118` with **no
formula guard** — the same hole as §3.1, on a different path.

---

## 5) Realignment plan

### 5.1 DELETE from `report_service.py` (647 lines → file drops to ~120)

| Lines | What | Why |
|---|---|---|
| `:20-40` | reportlab import block | dependency removed; the import-time warning is pure noise |
| `:41-47` | jinja2 import block | dependency removed |
| `:50-63` | `_human_date_filter`, `_jinja_env` | jinja2-only |
| `:66-87` | `_IDENTITY_KEYS`, `_DATE_KEYS`, `_fmt_ident` | enrichment-only; enrichment service is a stub (`src/services/enrich_service.py:17-18`) |
| `:108-116` | `_https_url` | only used by the dead HTML/PDF paths |
| `:249-321` | `_DOSSIER_CSS_CORE`, `_HTML_TEMPLATE` | jinja2 dossier |
| `:324-402` | `generate_html_report` | bespoke HTML dossier + jinja2 |
| `:455-488` | `_EMAIL_HTML_TEMPLATE` | jinja2 dossier |
| `:491-562` | `generate_email_html_report` | bespoke HTML dossier + jinja2 |
| `:565-567` | `_FOUND_PDF_ROW_CAP` | PDF only |
| `:570-581` | `_gold_palette` | PDF only; its raise site `:572-573` is already unreachable |
| `:584-863` | `generate_pdf_dossier` | bespoke PDF + reportlab; engine's own PDF is equally unavailable |
| `:10`, `:13`, `:14` | `io`, `Path`, `_xml_escape` imports | PDF-only |
| `:127` | duplicate `import io` | redundant with `:10` |
| `:1-6` | module docstring | rewrite — it currently advertises exports that cannot run |

### 5.2 KEEP AND FIX

| Unit | Action |
|---|---|
| `generate_csv_report` `:119-156` | **Rewrite as a thin adapter**: build/collect the upstream `Result` objects and return `formatter.into_csv(results, include_header=True).encode("utf-8")` (`core/formatter.py:18-19`). This inherits the engine schema (`core/result.py:23`) **and** the formula-injection guard (`core/result.py:26-33`, applied at `:218`) and drops the three always-empty columns plus the invented `exists` column. |
| `generate_txt_report` `:159-168` | **Keep.** Add a target header line using the currently-unused `username` param, or drop the param and update `app_shell.py:412-415`. Keep the "Total Detected" line (Sherlock parity). |
| `generate_markdown_report` `:171-246` | **Keep only if the owner accepts a dependency-free text format.** Then: delete the dead enrichment block `:218-234`; delete the always-empty `Time (s)` column `:206`/`:213`; fix the double escape `:230-234`; fix or drop the "Platforms checked" metric `:196-197`; add `<`/`>` escaping to `_md_cell` `:95-105`. Under strict engine parity → **delete the generator and the tile** instead. |
| `generate_email_markdown_report` `:405-452` | **Keep** — stdlib only, and its input schema is *live* (`others` = `{"message","url","extra","media"}`, built at `src/services/email_service.py:128-133`; phone rows use the same shape at `src/main.py:1814`). It is not a dependency-adding dossier. |
| `_report_rows` `:90-92`, `_md_cell` `:95-105` | Keep as helpers for the survivors; extend `_md_cell` for HTML-safety. |
| `return None` semantics `:182-188`, `:335-337`, `:408-410` | Keep the "None ⇒ nothing to render" contract, but make the *caller* treat `None` as "nothing to export", not as an error (`app_shell.py:397-400` currently raises). |

### 5.3 Exact engine call per surviving tile

| Tile | Call | Citation |
|---|---|---|
| CSV | `user_scanner.core.formatter.into_csv(results, include_header=True)` | `.venv\Lib\site-packages\user_scanner\core\formatter.py:18-19` |
| JSON | `user_scanner.core.formatter.into_json(results)` | `core/formatter.py:9-10` (or `get_json_data` at `:13-15` for the `list` form) |
| per-row (any format) | `Result.to_dict()` / `Result.to_json()` / `Result.to_csv()` | `core/result.py:184-191` / `:196-198` / `:200-224` |
| TXT | app-level `generate_txt_report` — **no engine equivalent** | `src/services/report_service.py:159-168` |
| MD | app-level `generate_markdown_report` — **no engine equivalent** | `src/services/report_service.py:171-246` |
| PDF | `formatter.into_pdf(...)` — **unavailable** (needs `reportlab`) | `core/formatter.py:22-39` → `core/pdf_generator.py:246-258` |
| HTML | none — **tile must be deleted** | — |

### 5.4 Required changes outside this file (for the realignment to land)

- `src/app_shell.py:519-526` — delete the PDF tile; `:551-558` — delete the HTML tile;
  `:290-311` — delete the PDF export branch; `:368-408` — delete the HTML branch (keep MD);
  `:327-366` — replace the inline JSON with `formatter.into_json(results)`;
  `:74-84` — delete the email-HTML branch; `:509-517` — drop "HTML" from the email-mode note.
- `src/services/sherlock_service.py:30-44` + `:352-362` — carry the upstream `Result`
  (`raw` field) so the engine exporters can be fed real engine objects.
- `src/services/email_service.py:38-48` + `:143-160` — same for email rows.
- `src/services/cache_service.py:415` — pass `sig` to `cached_report_path` (one-line fix) so the
  report cache actually hits.
- `src/app_shell.py:283-288` — the email-mode error message must not advertise HTML (and must
  not blame "PDF dossiers" for an HTML-tile failure).
- `src/app_shell.py:421-424` — pass `file_type=ft.FilePickerFileType.CUSTOM` if the extension
  filter is meant to apply; drop the redundant desktop rewrite at `:437-441`.

---

## 6) Verdict

**Failing today, for every user, every time:**
- PDF tile → "Failed to save: PDF generation returned empty output" (`app_shell.py:307-310`).
- HTML tile → "Failed to save: HTML generation returned empty output" (`app_shell.py:397-400`).
- Email-mode HTML tile → "PDF dossiers are username-mode — email results export as CSV, JSON,
  TXT, Markdown, or HTML" — a message that is both wrong about the cause and wrong about HTML
  being available (`app_shell.py:283-288`).

**Working but off-engine and unsafe:**
- CSV → exports a bespoke 7-column schema (3 of them structurally always empty) that **drops
  upstream `extra`/`media`/`reason`** and carries **no CSV formula-injection guard** — the
  user-supplied username is written raw and will execute in Excel/Sheets
  (`report_service.py:119-156` vs `core/result.py:26-33`, `:218`).
- JSON → bespoke inline schema, same data loss (`app_shell.py:327-366`).
- TXT → correct Sherlock-parity URL list; `username` param unused.
- MD → works, stdlib only, but carries a dead enrichment section, an always-empty time column,
  a wrong "platforms checked" metric and an HTML-unsafe cell escaper.

**Primary recommendation — delete-and-realign.** The file should shrink from 865 lines to roughly
120: delete the reportlab/jinja2/enrichment machinery (647 lines, 75%), keep the two
dependency-free text exports, and make `user_scanner.core.formatter` the single source of truth
for CSV and JSON. The engine already provides the CSV schema, the formula-injection guard, the
JSON row shape, and (behind `reportlab`, which the owner removed) the PDF path — the app is
hand-rolling worse versions of the first two and a broken version of the third.

**Do not** simply swap `into_csv` in and leave the rest: the engine exporters need upstream
`Result` objects, and the app currently discards them at
`src/services/sherlock_service.py:181-189` and `src/services/email_service.py:112-160`. Carrying
the raw result through the dataclasses is the one prerequisite that makes every engine-native
export possible — and it is two lines per dataclass.

**Owner decision points (need an explicit ruling):**
1. Does the rule mean *strict* parity (CSV + JSON only — drop TXT and MD too) or *no extra
   dependencies* (TXT and MD stay, since they are stdlib-only)? The engine has no TXT/MD
   equivalent; TXT is classic Sherlock, MD is a bespoke dossier but dependency-free.
2. The PDF tile has **no** working replacement: the engine's `into_pdf` also needs `reportlab`
   (`core/pdf_generator.py:254-258`). Either the tile is deleted, or `reportlab` is reinstalled
   (explicitly refused) — there is no third option.
