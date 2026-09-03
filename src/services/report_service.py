"""ReportService — multi-format intelligence report generation.

Generates gold-branded PDF dossiers (reportlab) and structured
mind-map case files (xmind) from Sherlock's SearchProgress data,
fully on-device without extra dependencies.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

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


def _gold_palette():
    """Sherlock gold brand palette for reports."""
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
    ready for FilePicker.save_file / Share, or None if reportlab is
    unavailable.
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
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title=f"Sherlock Dossier — {username}",
        author="Sherlock OSINT",
    )

    story: list = [
        Paragraph("SHERLOCK INTELLIGENCE DOSSIER", styles["DossierTitle"]),
        HRFlowable(width="100%", thickness=1.5, color=pal["gold"], spaceAfter=10),
    ]

    # Case metadata table
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta_rows = [
        ["Target", username],
        ["Generated", now],
        [
            "Platforms Checked",
            str(checked_sites or len(found) + len(not_found) + len(errors)),
        ],
        ["Platforms Available", str(total_sites or "3,300+")],
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
            f"Username <b>{username}</b> was investigated across "
            f"{total_sites or '3,300+'} platforms. "
            f"<b>{len(found)}</b> claimed accounts were confirmed, "
            f"{len(not_found)} platforms reported available, and "
            f"{len(errors)} checks failed (WAF / error pages).",
            styles["BodyGold"],
        )
    )
    story.append(Spacer(1, 8))

    # Found accounts table
    story.append(Paragraph("Confirmed Accounts", styles["H1Gold"]))
    header = ["Platform", "Profile URL"]
    rows = [header]
    for r in found:
        url = getattr(r, "url_user", None) or getattr(r, "url_main", "") or ""
        rows.append([str(getattr(r, "site_name", "?")), url[:120]])

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

    # Enrichment highlight cards (top 10 richest)
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
            keys = [
                k
                for k in (
                    "name",
                    "fullname",
                    "bio",
                    "location",
                    "follower_count",
                    "joined",
                    "created_at",
                )
                if data.get(k)
            ]
            if not keys:
                continue
            detail = " · ".join(
                f"{k.replace('_', ' ').title()}: {data[k]}" for k in keys
            )
            story.append(Paragraph(f"<b>{site}</b> — {detail}", styles["BodyGold"]))

    doc.build(story)
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
    confidence. Returns the written file path, or None if xmind is
    unavailable.
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
        key = tags[0].title() if tags else "Uncategorized"
        sections.setdefault(key, []).append(r)

    for section_name, results in sorted(sections.items()):
        section = root.addSubTopic()
        section.setTitle(section_name)
        section.addLabel(f"{len(results)} account(s)")
        if section_name.lower() in ("social", "social media"):
            section.addMarker(MarkerId.flagGreen)

        for r in results:
            site = getattr(r, "site_name", "Unknown")
            acct = section.addSubTopic()
            acct.setTitle(site)
            url = getattr(r, "url_user", None) or getattr(r, "url_main", None)
            if url:
                try:
                    acct.setURLHyperlink(url)
                except Exception:
                    pass
            acct.addLabel("Claimed")
            acct.addMarker(
                MarkerId.starGold if hasattr(MarkerId, "starGold") else MarkerId.starRed
            )

            enrich = enrichments.get(url or "")
            if enrich:
                note_lines = [f"{k}: {v}" for k, v in list(enrich.items())[:8]]
                try:
                    acct.setPlainNotes("\n".join(note_lines))
                except Exception:
                    pass

    xmind.save(wb, str(output_path))
    logger.info(
        "XMind case file generated for %s at %s (%d accounts)",
        username,
        output_path,
        len(found),
    )
    return output_path
