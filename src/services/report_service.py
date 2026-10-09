"""ReportService — multi-format intelligence report generation.

Generates gold-branded PDF dossiers (reportlab) and structured
mind-map case files (xmind) from Sherlock's SearchProgress data,
fully on-device without extra dependencies.
"""

from __future__ import annotations

import io
import logging
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

logger = logging.getLogger(__name__)

# ── Optional engine flags (graceful degradation on-device) ──────────────
_REPORTLAB_AVAILABLE = False
try:
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable,
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _REPORTLAB_AVAILABLE = True
except ImportError as err:
    logger.warning("reportlab not available: %s", err)

_XMIND_AVAILABLE = False
try:
    import xmind
    from xmind.core.markerref import MarkerId

    _XMIND_AVAILABLE = True
except ImportError as err:
    logger.warning("xmind not available: %s", err)

_JINJA_AVAILABLE = False
try:
    from jinja2 import Environment as _JinjaEnvironment

    _JINJA_AVAILABLE = True
except ImportError as err:
    logger.warning("jinja2 not available: %s", err)


def _human_date_filter(value):
    """Total Jinja filter: humanize dates, pass anything else through."""
    from core.format import human_date

    if value is None:
        return ""
    return human_date(value) or str(value)


def _jinja_env():
    """Shared Jinja environment (autoescape + custom dossier filters)."""
    env = _JinjaEnvironment(autoescape=True)
    env.filters["human_date"] = _human_date_filter
    return env


# Enrichment identity keys shared by markdown/PDF/HTML renderers; date-ish
# ones get the humanizer, the rest render as-is.
_IDENTITY_KEYS = (
    "name",
    "fullname",
    "bio",
    "location",
    "follower_count",
    "joined",
    "created_at",
)
_DATE_KEYS = ("joined", "created_at", "registered")


def _fmt_ident(k, v) -> str:
    """Format one enrichment identity value (dates humanized)."""
    from core.format import human_date

    text = str(v)
    if k in _DATE_KEYS:
        return human_date(text) or text
    return text


def _report_rows(found, not_found, errors):
    """Shared (found, not_found, errors) normalization for exporters."""
    return list(found or []), list(not_found or []), list(errors or [])


def _md_cell(value: object) -> str:
    """Escape a value for a Markdown table cell (`|` → `\\|`, newlines → space)."""
    if value is None:
        return ""
    return (
        str(value)
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


def generate_csv_report(
    username: str,
    found: list,
    not_found: list | None = None,
    errors: list | None = None,
) -> bytes:
    """CSV export of all result buckets (proper csv.writer quoting)."""
    import csv
    import io

    found, not_found, errors = _report_rows(found, not_found, errors)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "username",
            "name",
            "url_main",
            "url_user",
            "exists",
            "http_status",
            "response_time_s",
        ]
    )
    for r in found + not_found + errors:
        qt = getattr(r, "query_time", None)
        writer.writerow(
            [
                username,
                getattr(r, "site_name", "?"),
                getattr(r, "url_main", ""),
                getattr(r, "url_user", None) or getattr(r, "url_main", ""),
                getattr(r, "status", ""),
                getattr(r, "http_status", ""),
                f"{qt:.2f}" if qt else "",
            ]
        )
    return output.getvalue().encode("utf-8")


def generate_txt_report(username: str, found: list) -> bytes:
    """Plain-text URL list with total line (original Sherlock behavior)."""
    found, _, _ = _report_rows(found, None, None)
    output = []
    for r in found:
        url = getattr(r, "url_user", None)
        if url:
            output.append(f"{url}\n")
    output.append(f"Total Detected : {len(found)}\n")
    return "".join(output).encode("utf-8")


def generate_ndjson_report(
    username: str,
    found: list,
    not_found: list | None = None,
    errors: list | None = None,
) -> bytes:
    """Newline-delimited JSON, one result object per line (log-friendly)."""
    import json

    found, not_found, errors = _report_rows(found, not_found, errors)
    lines = [
        json.dumps(
            {
                "username": username,
                "bucket": bucket,
                "name": getattr(r, "site_name", "?"),
                "url_main": getattr(r, "url_main", ""),
                "url_user": getattr(r, "url_user", None) or getattr(r, "url_main", ""),
                "status": getattr(r, "status", ""),
                "http_status": getattr(r, "http_status", ""),
                "query_time": getattr(r, "query_time", None),
            },
            ensure_ascii=False,
        )
        for bucket, rows in (
            ("found", found),
            ("not_found", not_found),
            ("errors", errors),
        )
        for r in rows
    ]
    return ("\n".join(lines) + "\n" if lines else "").encode("utf-8")


def generate_cypher_bytes(username: str, found, enrichments=None) -> bytes | None:
    """Neo4j Cypher via our own graph export (None when networkx missing)."""
    try:
        from services.graph_service import build_identity_graph, export_cypher
    except ImportError:
        return None
    try:
        graph = build_identity_graph(
            username=username,
            found_accounts=list(found or []),
            enrichments=dict(enrichments or {}),
        )
        cypher = export_cypher(graph)
        return (cypher + "\n").encode("utf-8") if cypher else None
    except Exception as exc:
        logger.warning("cypher export failed: %s", exc)
        return None


def generate_markdown_report(
    username: str,
    found: list,
    not_found: list | None = None,
    errors: list | None = None,
    enrichments: dict | None = None,
    total_sites: int = 0,
    checked_sites: int = 0,
) -> bytes | None:
    """Shareable Markdown dossier (P3-5/P4-8) — plain text, no deps.

    Returns None when there is nothing to render — callers must skip
    save/share on None. (CSV/TXT/NDJSON instead return header/empty bytes;
    see those docstrings.)
    """
    found, not_found, errors = _report_rows(found, not_found, errors)
    if not (found or not_found or errors):
        return None
    enrichments = enrichments or {}

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Sherlock Intelligence Dossier — {username}",
        "",
        f"- **Generated:** {now}",
        f"- **Platforms checked:** {checked_sites or len(found) + len(not_found) + len(errors)}"
        f" / {total_sites or '5,200+'}",
        f"- **Accounts found:** {len(found)}",
        f"- **Available (not claimed):** {len(not_found)}",
        f"- **Errors / WAF:** {len(errors)}",
        "",
        "## Confirmed Accounts",
        "",
    ]
    if found:
        lines.append("| Platform | Profile URL | Time (s) |")
        lines.append("|---|---|---|")
        for r in found:
            url = getattr(r, "url_user", None) or getattr(r, "url_main", "") or ""
            qt = getattr(r, "query_time", None)
            lines.append(
                f"| {_md_cell(getattr(r, 'site_name', '?'))} | {_md_cell(url)} | "
                f"{f'{qt:.2f}' if qt else ''} |"
            )
    else:
        lines.append("_No claimed accounts found._")

    rich = []
    for r in found:
        url = getattr(r, "url_user", None) or getattr(r, "url_main", "") or ""
        data = enrichments.get(url)
        if data and len(data) >= 2:
            rich.append((getattr(r, "site_name", "?"), data))
    if rich:
        rich.sort(key=lambda x: len(x[1]), reverse=True)
        lines += ["", "## Profile Enrichment Highlights", ""]
        for site, data in rich[:15]:
            keys = [k for k in _IDENTITY_KEYS if data.get(k)]
            if keys:
                detail = " · ".join(
                    f"{k.replace('_', ' ').title()}: {_md_cell(_fmt_ident(k, data[k]))}"
                    for k in keys
                )
                lines.append(f"- **{_md_cell(site)}** — {_md_cell(detail)}")

    if errors:
        lines += ["", "## Failed / WAF-Blocked Checks", ""]
        for r in errors[:50]:
            site = getattr(r, "site_name", "?")
            ctx = getattr(r, "context", None) or getattr(r, "error_type", None) or ""
            lines.append(f"- {_md_cell(site)}{f' — {_md_cell(ctx)}' if ctx else ''}")

    lines += ["", "---", "_Generated by Sherlock OSINT — sherlock 2.2_"]
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    logger.info("Markdown dossier generated for %s (%d bytes)", username, len(payload))
    return payload


# Shared dossier CSS core (Batch 17): both HTML templates interpolate this
# instead of maintaining two copies. Page-specific rules stay inline.
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


_HTML_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sherlock Dossier — {{ username }}</title>
<style>
"""
    + _DOSSIER_CSS_CORE
    + """
  h1 { font-size: 1.5rem; }
  h2 { color: var(--gold); font-size: 1.1rem; margin-top: 28px;
       background: var(--parchment); color: var(--gold-dark);
       padding: 6px 10px; border-radius: 4px; }
  .meta b { color: var(--gold-dark); }
  .enr { background: #24211a; border-left: 3px solid var(--gold);
         padding: 6px 12px; margin: 6px 0; border-radius: 0 4px 4px 0; }
  ul { padding-left: 18px; } li { margin: 3px 0; }
</style>
</head>
<body><div class="wrap">
<h1>SHERLOCK INTELLIGENCE DOSSIER</h1>
<div class="meta">
  <b>Target:</b> {{ username }}<br>
  <b>Generated:</b> {{ generated }}<br>
  <b>Checked:</b> {{ checked }} / {{ total }}<br>
  <b>Found:</b> {{ found_count }} · <b>Available:</b> {{ not_found_count }}
  · <b>Errors:</b> {{ error_count }}
</div>

<h2>Confirmed Accounts</h2>
{% if found_rows %}
<table><tr><th>Platform</th><th>Profile URL</th></tr>
{% for r in found_rows %}<tr><td>{{ r.site }}</td>
<td>{% if r.url %}<a href="{{ r.url }}">{{ r.url }}</a>{% else %}—{% endif %}</td></tr>{% endfor %}
</table>
{% else %}<p class="dim">No claimed accounts found.</p>{% endif %}

{% if enrich_rows %}
<h2>Profile Enrichment Highlights</h2>
{% for e in enrich_rows %}<div class="enr"><b>{{ e.site }}</b> — {% for p in e.pairs %}{{ p[0] }}: {{ p[1]|human_date }}{% if not loop.last %} &middot; {% endif %}{% endfor %}</div>
{% endfor %}
{% endif %}

{% if error_rows %}
<h2>Failed / WAF-Blocked Checks</h2>
<ul>{% for r in error_rows %}<li>{{ r.site }}{% if r.ctx %} — {{ r.ctx }}{% endif %}</li>{% endfor %}</ul>
{% endif %}

<p class="dim">Generated by Sherlock OSINT — sherlock 2.2</p>
</div></body></html>
"""
)


def generate_html_report(
    username: str,
    found: list,
    not_found: list | None = None,
    errors: list | None = None,
    enrichments: dict | None = None,
    total_sites: int = 0,
    checked_sites: int = 0,
) -> bytes | None:
    """Self-contained offline HTML dossier (P4-8) — jinja2, inline CSS.

    Returns None when there is nothing to render or jinja2 is missing —
    callers must skip save/share on None.
    """
    if not _JINJA_AVAILABLE:
        logger.warning("jinja2 unavailable — HTML dossier skipped")
        return None
    found, not_found, errors = _report_rows(found, not_found, errors)
    if not (found or not_found or errors):
        return None
    enrichments = enrichments or {}

    found_rows = [
        {
            "site": getattr(r, "site_name", "?"),
            "url": _https_url(
                getattr(r, "url_user", None) or getattr(r, "url_main", "") or ""
            )
            or "",
        }
        for r in found
    ]
    enrich_rows = []
    for r in found:
        url = getattr(r, "url_user", None) or getattr(r, "url_main", "") or ""
        data = enrichments.get(url)
        if data and len(data) >= 2:
            pairs = [
                (k.replace("_", " ").title(), _fmt_ident(k, data[k]))
                for k in _IDENTITY_KEYS
                if data.get(k)
            ]
            if pairs:
                enrich_rows.append(
                    {
                        "site": getattr(r, "site_name", "?"),
                        "pairs": pairs,
                        "detail": " · ".join(
                            f"{label}: {value}" for label, value in pairs
                        ),
                    }
                )
    error_rows = [
        {
            "site": getattr(r, "site_name", "?"),
            "ctx": getattr(r, "context", None) or getattr(r, "error_type", None) or "",
        }
        for r in errors
    ]

    html = (
        _jinja_env()
        .from_string(_HTML_TEMPLATE)
        .render(
            username=username,
            generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            checked=checked_sites or len(found) + len(not_found) + len(errors),
            total=total_sites or "5,200+",
            found_count=len(found),
            not_found_count=len(not_found),
            error_count=len(errors),
            found_rows=found_rows,
            enrich_rows=enrich_rows[:15],
            error_rows=error_rows[:50],
        )
    )
    payload = html.encode("utf-8")
    logger.info("HTML dossier generated for %s (%d bytes)", username, len(payload))
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
    lines += ["", "---", "_Generated by Sherlock OSINT — sherlock 2.2_"]
    return ("\n".join(lines) + "\n").encode("utf-8")


_EMAIL_HTML_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sherlock Email OSINT — {{ addr }}</title>
<style>
"""
    + _DOSSIER_CSS_CORE
    + """
  h1 { font-size: 1.4rem; }
  table { margin-top: 18px; }
  .found { color: #50FA7B; font-weight: bold; }
  .rate { color: #FFB86C; }
  .unav { color: #ff7b7b; }
  .nf { color: #9a948a; }
</style>
</head>
<body><div class="wrap">
<h1>Sherlock Email OSINT</h1>
<div class="meta"><b>Target:</b> {{ addr }}<br><b>Generated:</b> {{ generated }}
<br><b>Registered on:</b> {{ found_n }} / {{ total_n }} platforms</div>
<table>
<tr><th>Platform</th><th>Domain</th><th>Status</th><th>Detail</th><th>Avatar</th></tr>
{% for r in rows %}
<tr><td>{{ r.name }}</td><td>{{ r.domain }}</td>
<td class="{{ r.cls }}">{{ r.status }}</td><td>{{ r.detail }}</td><td>{% if r.avatar %}<a href="{{ r.avatar }}">photo</a>{% else %}—{% endif %}</td></tr>
{% endfor %}
</table>
<p class="dim">Generated by Sherlock OSINT — sherlock 2.2</p>
</div></body></html>
"""
)


def generate_email_html_report(addr: str, rows: list) -> bytes | None:
    """Self-contained offline HTML export for email results (P4-8).

    Returns None when jinja2 is missing — callers must skip save/share
    on None. (Empty rows still render a header table, unlike the None-on-
    empty dossier generators.)
    """
    if not _JINJA_AVAILABLE:
        logger.warning("jinja2 unavailable — HTML email dossier skipped")
        return None

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

    out_rows = []
    for r in rows:
        status, cls = _status_of(r)
        out_rows.append(
            {
                "name": r.get("name", "?"),
                "domain": r.get("domain", ""),
                "status": status,
                "cls": cls,
                "detail": _email_detail_dict(r),
                "avatar": _email_avatar(r),
            }
        )
    html = (
        _jinja_env()
        .from_string(_EMAIL_HTML_TEMPLATE)
        .render(
            addr=addr,
            generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            found_n=sum(1 for r in rows if r.get("exists")),
            total_n=len(rows),
            rows=out_rows,
        )
    )
    payload = html.encode("utf-8")
    logger.info("HTML email dossier generated for %s (%d bytes)", addr, len(payload))
    return payload


# Cap on PDF found-table rows — thousands of hits would build one giant
# Paragraph table (slow + huge PDF); overflow is an explicit trailing row.
_FOUND_PDF_ROW_CAP = 500


def _gold_palette():
    """Sherlock gold brand palette for reports."""
    if not _REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab unavailable — PDF palette requires reportlab")
    return {
        "gold": rl_colors.HexColor("#D4AF37"),
        "gold_dark": rl_colors.HexColor("#8C6B1A"),
        "parchment": rl_colors.HexColor("#FFFBEB"),
        "black": rl_colors.black,
        "white": rl_colors.white,
        "grey": rl_colors.HexColor("#6B6B6B"),
    }


def generate_pdf_dossier(
    username: str,
    found: list,
    not_found: list | None = None,
    errors: list | None = None,
    enrichments: dict | None = None,
    total_sites: int = 0,
    checked_sites: int = 0,
) -> bytes | None:
    """Generate a gold-branded PDF Intelligence Dossier in memory.

    `found` items are app SiteResult objects (site_name, url_user,
    url_main, status, query_time, tags, ids_data). Returns PDF bytes
    ready for FilePicker.save_file / Share, or None when there is nothing
    to render (empty `found`, even with errors) or reportlab is missing —
    callers must skip save/share on None.

    Note: PDF uses Helvetica (WinAnsi) only; CJK/emoji glyphs render as
    boxes by design — no font embedding (keeps the on-device build
    dependency-free).
    """
    if not _REPORTLAB_AVAILABLE or not found:
        return None

    not_found = not_found or []
    errors = errors or []
    enrichments = enrichments or {}
    pal = _gold_palette()

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "DossierTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=pal["gold_dark"],
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "H1Gold",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=pal["gold_dark"],
            backColor=pal["parchment"],
            borderPadding=(4, 4, 4),
            spaceBefore=10,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "BodyGold",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
            textColor=pal["black"],
        )
    )

    buf = io.BytesIO()
    safe_user = str(username).replace("\r", " ").replace("\n", " ")
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title=f"Sherlock Dossier — {safe_user}",
        author="Sherlock OSINT",
    )

    story: list = [
        Paragraph("SHERLOCK INTELLIGENCE DOSSIER", styles["DossierTitle"]),
        HRFlowable(width="100%", thickness=1.5, color=pal["gold"], spaceAfter=10),
    ]

    # Case metadata table

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    meta_rows = [
        ["Target", username],
        ["Generated", now],
        [
            "Platforms Checked",
            str(checked_sites or len(found) + len(not_found) + len(errors)),
        ],
        ["Platforms Available", str(total_sites or "5,200+")],
        ["Accounts Found", str(len(found))],
    ]
    meta_table = Table(
        meta_rows,
        colWidths=[1.6 * inch, 4.8 * inch],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), pal["gold_dark"]),
                ("TEXTCOLOR", (0, 0), (0, -1), pal["white"]),
                ("BACKGROUND", (1, 0), (1, -1), pal["parchment"]),
                ("GRID", (0, 0), (-1, -1), 0.5, pal["gold"]),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        ),
        hAlign="CENTER",
    )
    story.append(KeepTogether([meta_table, Spacer(1, 10)]))

    # Executive summary
    story.append(Paragraph("Executive Summary", styles["H1Gold"]))
    story.append(
        Paragraph(
            f"Username <b>{_xml_escape(username)}</b> was investigated across "
            f"{total_sites or '5,200+'} platforms. "
            f"<b>{len(found)}</b> claimed accounts were confirmed, "
            f"{len(not_found)} platforms reported available, and "
            f"{len(errors)} checks failed (WAF / error pages).",
            styles["BodyGold"],
        )
    )
    story.append(Spacer(1, 8))

    # Found accounts table — tappable links: Paragraph <a href> wires
    # reportlab's linkURL, wraps naturally (no more 120-char truncation).
    # Capped: thousands of hits would otherwise build one giant Paragraph
    # table (slow + huge PDF); overflow is an explicit trailing row.
    story.append(Paragraph("Confirmed Accounts", styles["H1Gold"]))
    header = ["Platform", "Profile URL"]
    rows = [header]
    for r in found[:_FOUND_PDF_ROW_CAP]:
        url = getattr(r, "url_user", None) or getattr(r, "url_main", "") or ""
        site_label = str(getattr(r, "site_name", "?"))
        safe_url = _https_url(url)
        if safe_url:
            safe = (
                safe_url.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )
            rows.append(
                [
                    site_label,
                    Paragraph(
                        f'<a href="{safe}"><font size="7.5" color="#1565C0">'
                        f"{safe}</font></a>",
                        styles["BodyGold"],
                    ),
                ]
            )
        else:
            rows.append([site_label, ""])
    if len(found) > _FOUND_PDF_ROW_CAP:
        rows.append([f"...and {len(found) - _FOUND_PDF_ROW_CAP} more", ""])

    results_table = Table(
        rows,
        colWidths=[1.4 * inch, 5.0 * inch],
        repeatRows=1,
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), pal["gold_dark"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), pal["white"]),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [pal["white"], pal["parchment"]]),
                ("GRID", (0, 0), (-1, -1), 0.5, pal["gold"]),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        ),
        hAlign="CENTER",
    )
    story.append(results_table)

    # Enrichment highlight cards (top 10 richest) as field/value tables
    rich = []
    for r in found:
        url = getattr(r, "url_user", None) or getattr(r, "url_main", "") or ""
        data = enrichments.get(url)
        if data and len(data) >= 2:
            rich.append((getattr(r, "site_name", "?"), data))
    if rich:
        rich.sort(key=lambda x: len(x[1]), reverse=True)
        story.append(Spacer(1, 10))
        story.append(Paragraph("Profile Enrichment Highlights", styles["H1Gold"]))
        for site, data in rich[:10]:
            keys = [k for k in _IDENTITY_KEYS if data.get(k)]
            if not keys:
                continue
            kv_rows = [
                (k.replace("_", " ").title(), _fmt_ident(k, data[k])[:160])
                for k in keys
            ]
            # P4-5: embed the cached avatar thumbnail (cache-warmed by the
            # enrichment flow) — never downloads on the render path.
            head_item = Paragraph(f"<b>{_xml_escape(site)}</b>", styles["BodyGold"])
            img_url = data.get("image") or data.get("avatar")
            if _https_url(img_url):
                try:
                    from services.cache_service import ensure_cached_avatar

                    cached = ensure_cached_avatar(img_url)
                    if cached != img_url and Path(cached).is_file():
                        from reportlab.platypus import Image as RLImage

                        head_item = Table(
                            [
                                [
                                    RLImage(cached, width=30, height=30),
                                    Paragraph(
                                        f"<b>{_xml_escape(site)}</b>",
                                        styles["BodyGold"],
                                    ),
                                ]
                            ],
                            colWidths=[0.45 * inch, 5.95 * inch],
                            style=TableStyle(
                                [
                                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                                ]
                            ),
                        )
                except Exception as exc:
                    logger.info("PDF avatar embed skipped for %s: %s", site, exc)
            field_table = Table(
                kv_rows,
                colWidths=[1.3 * inch, 5.1 * inch],
                style=TableStyle(
                    [
                        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ("TEXTCOLOR", (0, 0), (0, -1), pal["gold_dark"]),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 1),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                        ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ]
                ),
                hAlign="LEFT",
            )
            story.append(KeepTogether([head_item, field_table, Spacer(1, 4)]))

    # Gold footer with page numbers on every page
    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setStrokeColor(pal["gold"])
        canvas.setLineWidth(0.5)
        canvas.line(0.55 * inch, 0.42 * inch, A4[0] - 0.55 * inch, 0.42 * inch)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(pal["grey"])
        canvas.drawString(0.55 * inch, 0.28 * inch, f"Sherlock OSINT — {username}")
        canvas.drawRightString(
            A4[0] - 0.55 * inch, 0.28 * inch, f"Page {canvas.getPageNumber()}"
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    pdf_bytes = buf.getvalue()
    logger.info(
        "PDF dossier generated for %s (%d bytes, %d found)",
        username,
        len(pdf_bytes),
        len(found),
    )
    return pdf_bytes


def generate_xmind_case(
    username: str,
    found: list,
    enrichments: dict | None = None,
    output_path: str | Path | None = None,
) -> Path | None:
    """Generate a structured .xmind mind-map case file.

    Root topic = target; branches by site tag / "Uncategorized";
    each claimed account is a clickable subtopic with URL hyperlink,
    labels for status, notes for enrichment data, and markers for
    confidence. Returns the written file path, or None when there is
    nothing to render or xmind is unavailable.
    """
    if not _XMIND_AVAILABLE or not found:
        return None

    enrichments = enrichments or {}
    if output_path is None:
        from services.cache_service import cached_report_path
        from services.storage_service import get_cache_dir

        cache = Path(get_cache_dir())
        cache.mkdir(parents=True, exist_ok=True)
        # Keyed by (query, found-set fingerprint) so different scans of the
        # same username no longer clobber each other's case files.
        output_path = cached_report_path("xmind", username, found, "xmind")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        try:
            output_path.unlink()
        except OSError:
            pass

    wb = xmind.load(str(output_path))
    sheet = wb.getPrimarySheet()
    sheet.setTitle(f"Sherlock Investigation — {username}")
    root = sheet.getRootTopic()
    root.setTitle(username)
    root.addLabel(f"{len(found)} accounts found")
    root.addMarker(MarkerId.priority1)

    # Group found sites by first tag (category), fallback Uncategorized
    sections: dict[str, list] = {}
    for r in found:
        tags = getattr(r, "tags", None) or []
        key = str(tags[0]).title() if tags else "Uncategorized"
        sections.setdefault(key, []).append(r)

    # P4-9: account topics + shared-evidence index for relationships
    acct_topics: dict[str, object] = {}
    evidence_index: dict[str, list[str]] = {}

    def _evidence_keys(r) -> list[str]:
        enrich = enrichments.get(
            getattr(r, "url_user", None) or getattr(r, "url_main", "") or ""
        )
        keys = []
        if enrich:
            email_v = enrich.get("email")
            if isinstance(email_v, str) and "@" in email_v:
                keys.append(f"shared email {email_v.strip().lower()}")
            name_v = enrich.get("fullname") or enrich.get("name")
            if isinstance(name_v, str) and len(name_v.strip()) > 2:
                keys.append(f"shared name {name_v.strip().title()}")
        return keys

    for section_name, results in sorted(sections.items()):
        section = root.addSubTopic()
        section.setTitle(section_name)
        section.addLabel(f"{len(results)} account(s)")
        if section_name.lower() in ("social", "social media"):
            section.addMarker(MarkerId.flagGreen)
        if section_name == "Uncategorized":
            # P4-9: fold the catch-all so real categories lead the view.
            try:
                section.setFolded(True)
            except Exception as exc:
                logger.info("XMind fold skipped: %s", exc)

        for r in results:
            site = getattr(r, "site_name", "Unknown")
            acct = section.addSubTopic()
            acct.setTitle(site)
            # Key topics by URL (unique) with a deterministic fallback —
            # keying by display name collides on duplicate site names and
            # evidence relationships then bind the wrong topic.
            url = _https_url(
                getattr(r, "url_user", None) or getattr(r, "url_main", None)
            )
            acct_key = url or f"site:{site}#{len(acct_topics)}"
            acct_topics[acct_key] = acct
            for ev in _evidence_keys(r):
                evidence_index.setdefault(ev, []).append(acct_key)
            if url:
                try:
                    acct.setURLHyperlink(url)
                except Exception:
                    pass
            acct.addLabel("Claimed")

            enrich = enrichments.get(url or "")
            if enrich:
                note_lines = [
                    f"{k}: {str(v)[:300]}" for k, v in list(enrich.items())[:8]
                ]
                try:
                    acct.setPlainNotes("\n".join(note_lines))
                except Exception:
                    pass
                # Evidence markers: enriched accounts get the star; bare
                # claims get priority-3 so the eye lands on enriched nodes.
                acct.addMarker(
                    MarkerId.starGold
                    if hasattr(MarkerId, "starGold")
                    else MarkerId.starRed
                )
            else:
                acct.addMarker(MarkerId.priority3)

    # P4-9: relationship links between accounts sharing evidence
    rel_count = 0
    for label, sites in evidence_index.items():
        for a, b in pairwise(sites):
            t1, t2 = acct_topics.get(a), acct_topics.get(b)
            if t1 is None or t2 is None:
                continue
            try:
                sheet.createRelationship(t1, t2, label)
                rel_count += 1
            except Exception as exc:
                # Visible, never silent (owner rule).
                logger.warning("XMind relationship %s↔%s failed: %s", a, b, exc)

    # P4-11: per-category sheets for multi-account categories (organizational
    # duplicates of the overview — XMind tabs give one view per category).
    sheet_count = 0
    for section_name, results in sorted(sections.items()):
        if len(results) < 2:
            continue
        try:
            # createSheet() already registers the sheet (verified in-venv:
            # Workbook.createSheet calls addSheet internally) — a second
            # addSheet would double-register it.
            cat_sheet = wb.createSheet()
            cat_sheet.setTitle(f"Sherlock — {section_name}")
            cat_root = cat_sheet.getRootTopic()
            cat_root.setTitle(f"{section_name} ({len(results)})")
            for r in results:
                site = getattr(r, "site_name", "Unknown")
                sub = cat_root.addSubTopic()
                sub.setTitle(site)
                c_url = _https_url(
                    getattr(r, "url_user", None) or getattr(r, "url_main", None)
                )
                if c_url:
                    try:
                        sub.setURLHyperlink(c_url)
                    except Exception:
                        pass
                sub.addMarker(
                    MarkerId.starGold
                    if enrichments.get(c_url or "")
                    else MarkerId.priority3
                )
            sheet_count += 1
        except Exception as exc:
            logger.warning("XMind category sheet %s failed: %s", section_name, exc)

    xmind.save(wb, str(output_path))
    logger.info(
        "XMind case file generated for %s at %s (%d accounts, %d relationships, %d category sheets)",
        username,
        output_path,
        len(found),
        rel_count,
        sheet_count,
    )
    return output_path
