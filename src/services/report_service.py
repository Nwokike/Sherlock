"""ReportService — multi-format intelligence report generation.

Exports are the exports the wrapped engine provides, plus dependency-free
app formats. CSV and JSON are produced by `user_scanner.core.formatter`
(the engine's own schema and CSV formula-injection guard) over engine
`Result` objects reconstructed from the app's result rows. TXT, Markdown
and HTML are stdlib-only app formats. No third-party PDF dependencies.
"""

from __future__ import annotations

import csv
import html
import io
import json
import logging
from datetime import UTC, datetime

from core.constants import SITES_TOTAL_FALLBACK

logger = logging.getLogger(__name__)


def _report_rows(found, not_found, errors):
    """Shared (found, not_found, errors) normalization for exporters."""
    return list(found or []), list(not_found or []), list(errors or [])


def _md_cell(value: object) -> str:
    """Escape a value for a Markdown table cell (`|` → `\\|`, newlines → space,
    `<`/`>` → entities so a rendered-Markdown viewer cannot inject HTML)."""
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "\\|")
        .replace("\r\n", " ")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _https_url(url: object) -> str | None:
    """Allow only http(s) hyperlinks, else None (caller renders plain text)."""
    if not isinstance(url, str):
        return None
    u = url.strip()
    low = u.lower()
    if low.startswith("https://") or low.startswith("http://"):
        return u
    return None


# ── Engine-native CSV / JSON ─────────────────────────────────────────────
# The engine's canonical export surface is user_scanner.core.formatter
# (into_csv / into_json over core.result.Result objects). App rows are
# SiteResult objects (or restored cached snapshots), so we reconstruct
# engine Results from them — the engine then applies its own schema
# (CSV_FIELDS), status labels and _neutralize_csv_cell formula guard
# (core/result.py:26-33, applied at :218).


def _to_engine_result(r, username: str):
    """Return the engine `Result` for one app result row.

    Prefers the lossless upstream object carried on the row (mapper-set
    ``raw``); falls back to reconstructing one from the shared attribute
    surface (site_name / status / urls / tags / ids_data) so restored
    cached snapshots export identically.
    """
    from user_scanner.core.result import Result

    raw = getattr(r, "raw", None)
    if raw is not None and hasattr(raw, "status"):
        try:
            return raw.update(username=username, is_email=False)
        except Exception:  # pragma: no cover — fall through to reconstruction
            pass

    status = getattr(r, "status", "")
    if status == "Claimed":
        result = Result.taken()
    elif status == "Available":
        result = Result.available()
    else:
        reason = getattr(r, "error_type", None) or getattr(r, "context", None)
        result = Result.error(reason) if reason else Result.error()

    tags = getattr(r, "tags", None) or []
    ids = getattr(r, "ids_data", None) or {}
    extra = ids.get("extra") if isinstance(ids.get("extra"), dict) else {}
    media = ids.get("media") if isinstance(ids.get("media"), dict) else {}
    result.update(
        username=username,
        site_name=getattr(r, "site_name", "?"),
        category=str(tags[0]) if tags else None,
        is_email=False,
        url=getattr(r, "url_user", None) or getattr(r, "url_main", "") or "",
        extra=extra,
        media=media,
    )
    return result


def _engine_results(username: str, found, not_found, errors) -> list:
    rows, _nf, _err = _report_rows(found, not_found, errors)
    return [_to_engine_result(r, username) for r in rows]


def generate_csv_report(
    username: str,
    found: list,
    not_found: list | None = None,
    errors: list | None = None,
) -> bytes:
    """CSV export via the engine's own formatter (schema + formula guard)."""
    try:
        from user_scanner.core.formatter import into_csv

        return into_csv(_engine_results(username, found, not_found, errors)).encode(
            "utf-8"
        )
    except ImportError:  # pragma: no cover — user-scanner is a hard dep
        logger.warning("user_scanner formatter unavailable — local CSV writer")
        return _local_csv(username, found, not_found, errors)


def _local_csv(username: str, found, not_found, errors) -> bytes:
    """Fallback writer mirroring the engine schema, with the engine's
    formula-injection guard ported (user_scanner/core/result.py:26-33)."""

    def _neutralize(cell: object) -> str:
        text = "" if cell is None else str(cell)
        if text[:1] in ("=", "+", "-", "@", "\t", "\r", "\n"):
            return "'" + text
        return text

    rows, not_found, errors = _report_rows(found, not_found, errors)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["username", "category", "site_name", "status", "url", "extra", "media", "reason"]
    )
    for r in rows:
        tags = getattr(r, "tags", None) or []
        ids = getattr(r, "ids_data", None) or {}
        writer.writerow(
            [
                _neutralize(username),
                _neutralize(str(tags[0]) if tags else ""),
                _neutralize(getattr(r, "site_name", "?")),
                _neutralize(getattr(r, "status", "")),
                _neutralize(
                    getattr(r, "url_user", None) or getattr(r, "url_main", "") or ""
                ),
                _neutralize(json.dumps(ids.get("extra") or {}, ensure_ascii=False)),
                _neutralize(json.dumps(ids.get("media") or {}, ensure_ascii=False)),
                _neutralize(
                    getattr(r, "error_type", None) or getattr(r, "context", None) or ""
                ),
            ]
        )
    return output.getvalue().encode("utf-8")


def generate_json_report(
    username: str,
    found: list,
    not_found: list | None = None,
    errors: list | None = None,
) -> bytes:
    """JSON export via the engine's own formatter (Result.to_dict shape)."""
    try:
        from user_scanner.core.formatter import into_json

        return into_json(_engine_results(username, found, not_found, errors)).encode(
            "utf-8"
        )
    except ImportError:  # pragma: no cover — user-scanner is a hard dep
        logger.warning("user_scanner formatter unavailable — local JSON writer")
        rows = _engine_results(username, found, not_found, errors)
        return json.dumps(
            [
                {
                    "username": username,
                    "site_name": getattr(r, "site_name", "?"),
                    "status": getattr(r, "status", ""),
                    "url": getattr(r, "url_user", None)
                    or getattr(r, "url_main", "")
                    or "",
                }
                for r in rows
            ],
            indent=4,
        ).encode("utf-8")


def generate_txt_report(username: str, found: list) -> bytes:
    """Plain-text URL list with target header + total line (original
    Sherlock behavior)."""
    rows, _, _ = _report_rows(found, None, None)
    output = [f"Sherlock OSINT — {username}\n\n"] if username else []
    for r in rows:
        url = getattr(r, "url_user", None)
        if url:
            output.append(f"{url}\n")
    output.append(f"Total Detected : {len(rows)}\n")
    return "".join(output).encode("utf-8")


def generate_markdown_report(
    username: str,
    found: list,
    not_found: list | None = None,
    errors: list | None = None,
    total_sites: int = 0,
    checked_sites: int = 0,
) -> bytes | None:
    """Markdown dossier — plain text, no deps.

    Returns None when there is nothing to render — callers must skip
    save/share on None.
    """
    found, not_found, errors = _report_rows(found, not_found, errors)
    if not (found or not_found or errors):
        return None

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Sherlock Intelligence Dossier — {username}",
        "",
        f"- **Generated:** {now}",
        f"- **Platforms checked:** {checked_sites or len(found) + len(not_found) + len(errors)}"
        f" / {total_sites or SITES_TOTAL_FALLBACK}",
        f"- **Accounts found:** {len(found)}",
        f"- **Available (not claimed):** {len(not_found)}",
        f"- **Errors / WAF:** {len(errors)}",
        "",
        "## Confirmed Accounts",
        "",
    ]
    if found:
        lines.append("| Platform | Profile URL |")
        lines.append("|---|---|")
        for r in found:
            url = getattr(r, "url_user", None) or getattr(r, "url_main", "") or ""
            lines.append(
                f"| {_md_cell(getattr(r, 'site_name', '?'))} | {_md_cell(url)} |"
            )
    else:
        lines.append("_No claimed accounts found._")

    if errors:
        lines += ["", "## Failed / WAF-Blocked Checks", ""]
        for r in errors[:50]:
            site = getattr(r, "site_name", "?")
            ctx = getattr(r, "error_type", None) or getattr(r, "context", None) or ""
            lines.append(f"- {_md_cell(site)}{f' — {_md_cell(ctx)}' if ctx else ''}")

    lines += ["", "---", "_Generated by Sherlock OSINT_"]
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    logger.info("Markdown dossier generated for %s (%d bytes)", username, len(payload))
    return payload


def generate_email_markdown_report(addr: str, rows: list) -> bytes | None:
    """Markdown export for holehe-v2 email results (dict rows).

    Returns None when `rows` is empty (aligned with the other dossier
    generators) — callers must skip save/share on None.
    """
    if not rows:
        return None

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    def _status_of(r) -> str:
        if r.get("exists"):
            return "FOUND"
        if r.get("rateLimit"):
            return "RATE_LIMITED"
        if r.get("unavailable"):
            return "UNAVAILABLE"
        return "not found"

    def _email_detail(r) -> str:
        """Rich detail: identity facts first, raw message as fallback."""
        others = r.get("others") or {}
        extra = others.get("extra") if isinstance(others.get("extra"), dict) else {}
        for key in ("bio", "username", "login", "full_name", "display_name"):
            val = extra.get(key)
            if isinstance(val, str) and val.strip():
                return f"{key.replace('_', ' ').title()}: {val.strip()}"
        return others.get("message") or others.get("error") or ""

    found_n = sum(1 for r in rows if r.get("exists"))
    lines = [
        f"# Sherlock Email OSINT — {addr}",
        "",
        f"- **Generated:** {now}",
        f"- **Registered on:** {found_n} / {len(rows)} platforms",
        "",
        "| Platform | Domain | Status | Detail |",
        "|---|---|---|---|",
    ]
    for r in rows:
        detail = _email_detail(r)
        lines.append(
            f"| {_md_cell(r.get('name', '?'))} | {_md_cell(r.get('domain', ''))} | "
            f"{_status_of(r)} | {_md_cell(detail)} |"
        )
    lines += ["", "---", "_Generated by Sherlock OSINT_"]
    return ("\n".join(lines) + "\n").encode("utf-8")


# Shared dossier CSS core: both HTML builders interpolate this instead of
# maintaining two copies. Page-specific rules stay inline.
_DOSSIER_CSS_CORE = """  :root { --gold: #D4AF37; --gold-dark: #8C6B1A; --parchment: #FFFBEB; }
  body { font-family: Georgia, 'Times New Roman', serif; margin: 0;
         background: #1c1a14; color: #eae6da; }
  .wrap { max-width: 860px; margin: 0 auto; padding: 28px 20px 60px; }
  h1 { color: var(--gold); border-bottom: 2px solid var(--gold);
       padding-bottom: 10px; }
  .meta { background: var(--parchment); color: #333; border-radius: 6px;
          padding: 12px 16px; display: inline-block; }
  table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
  th { background: var(--gold-dark); color: #fff; text-align: left;
       padding: 7px 10px; }
  td { border-bottom: 1px solid #3a3628; padding: 6px 10px; }
  tr:nth-child(even) td { background: #24211a; }
  a { color: var(--gold); }
  .dim { color: #9a948a; font-size: 0.85rem; }"""

_HTML_PAGE_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{css}
{extra_css}
</style>
</head>
<body><div class="wrap">
{body}
<p class="dim">Generated by Sherlock OSINT</p>
</div></body></html>
"""


def _html_date(value) -> str:
    from core.format import human_date

    if value is None:
        return ""
    return html.escape(human_date(value) or str(value))


def generate_html_report(
    username: str,
    found: list,
    not_found: list | None = None,
    errors: list | None = None,
    total_sites: int = 0,
    checked_sites: int = 0,
) -> bytes | None:
    """Self-contained offline HTML dossier — stdlib string template,
    inline CSS, all values escaped. Returns None when there is nothing
    to render — callers must skip save/share on None."""
    found, not_found, errors = _report_rows(found, not_found, errors)
    if not (found or not_found or errors):
        return None

    found_rows = []
    for r in found:
        url = _https_url(
            getattr(r, "url_user", None) or getattr(r, "url_main", "") or ""
        )
        link = (
            f'<a href="{html.escape(url, quote=True)}">{html.escape(url)}</a>'
            if url
            else "—"
        )
        found_rows.append(
            f"<tr><td>{html.escape(str(getattr(r, 'site_name', '?')))}</td>"
            f"<td>{link}</td></tr>"
        )
    error_rows = []
    for r in errors[:50]:
        ctx = getattr(r, "error_type", None) or getattr(r, "context", None) or ""
        error_rows.append(
            f"<li>{html.escape(str(getattr(r, 'site_name', '?')))}"
            f"{f' — {html.escape(str(ctx))}' if ctx else ''}</li>"
        )

    body = f"""<h1>SHERLOCK INTELLIGENCE DOSSIER</h1>
<div class="meta">
  <b>Target:</b> {html.escape(username)}<br>
  <b>Generated:</b> {datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}<br>
  <b>Checked:</b> {checked_sites or len(found) + len(not_found) + len(errors)} / {total_sites or SITES_TOTAL_FALLBACK}<br>
  <b>Found:</b> {len(found)} · <b>Available:</b> {len(not_found)}
  · <b>Errors:</b> {len(errors)}
</div>

<h2>Confirmed Accounts</h2>
{("<table><tr><th>Platform</th><th>Profile URL</th></tr>" + "".join(found_rows) + "</table>") if found_rows else '<p class="dim">No claimed accounts found.</p>'}

{('<h2>Failed / WAF-Blocked Checks</h2><ul>' + "".join(error_rows) + "</ul>") if error_rows else ""}"""

    html_text = _HTML_PAGE_SHELL.format(
        title=f"Sherlock Dossier — {html.escape(username)}",
        css=_DOSSIER_CSS_CORE,
        extra_css="""  h1 { font-size: 1.5rem; }
  h2 { font-size: 1.1rem; margin-top: 28px;
       background: var(--parchment); color: var(--gold-dark);
       padding: 6px 10px; border-radius: 4px; }
  .meta b { color: var(--gold-dark); }""",
        body=body,
    )
    payload = html_text.encode("utf-8")
    logger.info("HTML dossier generated for %s (%d bytes)", username, len(payload))
    return payload


def generate_email_html_report(addr: str, rows: list) -> bytes | None:
    """Self-contained offline HTML export for email results — stdlib string
    template, all values escaped. (Empty rows still render a header table,
    unlike the None-on-empty dossier generators.)"""

    def _status_of(r) -> tuple[str, str]:
        if r.get("exists"):
            return "FOUND", "found"
        if r.get("rateLimit"):
            return "RATE_LIMITED", "rate"
        if r.get("unavailable"):
            return "UNAVAILABLE", "unav"
        return "not found", "nf"

    def _email_detail_dict(r) -> str:
        others = r.get("others") or {}
        extra = others.get("extra") if isinstance(others.get("extra"), dict) else {}
        for key in ("bio", "username", "login", "full_name", "display_name"):
            val = extra.get(key)
            if isinstance(val, str) and val.strip():
                return f"{key.replace('_', ' ').title()}: {val.strip()}"
        return others.get("message") or others.get("error") or ""

    def _email_avatar(r) -> str:
        """Per-row avatar: platform media first, then the address's own
        Gravatar (md5 of the lowercased address — Gravatar's contract, not
        a security use). d=mp renders a placeholder when none exists."""
        others = r.get("others") or {}
        media = others.get("media") if isinstance(others.get("media"), dict) else {}
        avatar = _https_url(media.get("avatar") or media.get("thumbnail_url"))
        if avatar:
            return avatar
        import hashlib

        digest = hashlib.md5(  # noqa: S324 — Gravatar requires md5
            addr.strip().lower().encode("utf-8")
        ).hexdigest()
        return f"https://gravatar.com/avatar/{digest}?s=200&d=mp"

    body_rows = []
    for r in rows:
        status, cls = _status_of(r)
        avatar = _https_url(_email_avatar(r))
        avatar_cell = (
            f'<a href="{html.escape(avatar, quote=True)}">photo</a>'
            if avatar
            else "—"
        )
        body_rows.append(
            f"<tr><td>{html.escape(str(r.get('name', '?')))}</td>"
            f"<td>{html.escape(str(r.get('domain', '')))}</td>"
            f'<td class="{cls}">{status}</td>'
            f"<td>{html.escape(_email_detail_dict(r))}</td>"
            f"<td>{avatar_cell}</td></tr>"
        )

    body = f"""<h1>Sherlock Email OSINT</h1>
<div class="meta"><b>Target:</b> {html.escape(addr)}<br><b>Generated:</b> {datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}
<br><b>Registered on:</b> {sum(1 for r in rows if r.get("exists"))} / {len(rows)} platforms</div>
<table>
<tr><th>Platform</th><th>Domain</th><th>Status</th><th>Detail</th><th>Avatar</th></tr>
{''.join(body_rows)}
</table>"""

    html_text = _HTML_PAGE_SHELL.format(
        title=f"Sherlock Email OSINT — {html.escape(addr)}",
        css=_DOSSIER_CSS_CORE,
        extra_css="""  h1 { font-size: 1.4rem; }
  table { margin-top: 18px; }
  .found { color: #50FA7B; font-weight: bold; }
  .rate { color: #FFB86C; }
  .unav { color: #ff7b7b; }
  .nf { color: #9a948a; }""",
        body=body,
    )
    payload = html_text.encode("utf-8")
    logger.info("HTML email dossier generated for %s (%d bytes)", addr, len(payload))
    return payload
