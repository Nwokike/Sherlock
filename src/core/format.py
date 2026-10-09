"""Compact count formatting — thousands separators for rendered totals.

Single home for "5,203"-style rendering so cards, headers, and reports
agree: ints/floats get grouping, non-numeric input passes through as-is
(never crash a render on a bad count). Also hosts human_date() — the one
stdlib date-parser shared by cards, dialogs, and Jinja templates.
"""

from __future__ import annotations

import calendar
import datetime

_DATE_FORMATS = (
    # day-precision first, then month-precision
    "%Y-%m-%d",
    "%d %B %Y",
    "%d %b %Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%B %Y",
    "%b %Y",
    "%Y-%m",
)


def format_count(value: object) -> str:
    """Format a count with thousands separators ("5203" -> "5,203").

    Bools are returned as-is ("True"/"False" would be a lie for a count);
    floats keep one decimal when non-integral. Anything else is str()'d.
    """
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.1f}" if not value.is_integer() else f"{int(value):,}"
    return str(value)


def human_date(value: object) -> str | None:
    """Humanize a profile date ("2019-04-01T12:00:00Z" -> "Apr 2019").

    socid-extractor and holehe extras emit join/created dates in whatever
    shape the platform uses — ISO 8601 with offsets, bare dates, "March
    2019", unix seconds. Precision is preserved honestly: full dates get
    "Apr 1, 2019", month precision "Apr 2019", year-only "2019". Returns
    None when nothing parses — callers keep the raw string (never render
    a wrong date on a guess).
    """
    if value is None or isinstance(value, (dict, list, tuple, bool)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Unix seconds between 1971 and 2100 — anything wider is not a date.
        if 31_536_000 <= value <= 4_102_444_800:
            dt = datetime.datetime.fromtimestamp(value, datetime.UTC)
            return f"{calendar.month_abbr[dt.month]} {dt.year}"
        return None
    text = str(value).strip()
    if not text or len(text) > 40:
        return None
    if text.isdigit():
        if len(text) == 4 and 1900 <= int(text) <= 2100:
            return text  # year-only input stays "2019"
        if len(text) == 10 and 31_536_000 <= int(text) <= 4_102_444_800:
            dt = datetime.datetime.fromtimestamp(int(text), datetime.UTC)
            return f"{calendar.month_abbr[dt.month]} {dt.year}"

    candidate = text
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    dt = None
    try:
        dt = datetime.datetime.fromisoformat(candidate)
    except ValueError:
        pass

    if dt is None:
        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.datetime.strptime(candidate, fmt).replace(
                    tzinfo=datetime.UTC
                )
                break
            except ValueError:
                continue
        month_precision = fmt in ("%B %Y", "%b %Y", "%Y-%m")
    else:
        # fromisoformat accepted it: "2019" and "2019-04" parse as Jan 1
        # (relaxed parsing) — recover the true precision from the shape.
        parts = candidate.split("-")
        month_precision = len(parts) == 2
        year_only = len(parts) == 1
        if year_only:
            return candidate

    if dt is None:
        return None
    if month_precision:
        return f"{calendar.month_abbr[dt.month]} {dt.year}"
    return f"{calendar.month_abbr[dt.month]} {dt.day}, {dt.year}"
