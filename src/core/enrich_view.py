"""Dynamic enrichment rendering — every field, no hardcoding.

OSINT payloads differ per platform holehe-v2 exposes rich facts, socid
extractors their own keys and neither set is knowable in advance. This
module turns ANY enrichment/extras mapping into display rows so the UI
shows everything the backend produced instead of a fixed hand-picked
list. The rule: never drop a field the engine returned.
"""

from __future__ import annotations

from core.format import human_date

# Keys consumed by the UI itself (avatar, measured identity) — shown where
# they belong, not as generic text rows. Everything else is rendered.
_RESERVED_KEYS = frozenset({"image", "avatar", "photo", "_extractor"})

# Keys whose values are dates on most platforms — humanized on display.
_DATE_HINTS = (
    "date",
    "time",
    "created",
    "updated",
    "joined",
    "registered",
    "since",
    "born",
)


def _label(key: str) -> str:
    """Humanize a JSON key: payerId -> "Payer Id", created_at -> "Created At"."""
    import re

    text = str(key).strip()
    if not text:
        return "Field"
    if text.startswith("_"):
        text = text[1:]
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    words = [w for w in text.split() if w]
    return " ".join(w[:1].upper() + w[1:] for w in words) or "Field"


def _flatten(value, prefix: str = "") -> list[tuple[str, str]]:
    """Flatten nested dicts/lists into (label, text) rows — nothing dropped."""
    rows: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for k, v in value.items():
            label = f"{prefix} {_label(k)}".strip() if prefix else _label(k)
            rows.extend(_flatten(v, label))
        return rows
    if isinstance(value, (list, tuple, set)):
        if not value:
            return rows
        if all(isinstance(v, dict) for v in value):
            for i, v in enumerate(value, 1):
                rows.extend(_flatten(v, f"{prefix} {i}".strip()))
            return rows
        rows.append((prefix or "List", _stringify(value)))
        return rows
    rows.append((prefix or "Value", _stringify(value)))
    return rows


def _stringify(value) -> str:
    """Render any enrichment value as compact display text."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list, tuple, set)):
        if not value:
            return "—"
        if isinstance(value, dict):
            return ", ".join(f"{k}: {_stringify(v)}" for k, v in value.items())
        return ", ".join(_stringify(v) for v in value)
    text = str(value).strip()
    if text.lower() in ("true", "false"):
        return "Yes" if text.lower() == "true" else "No"
    return text or "—"


def enrichment_rows(
    enrich: dict | None,
    extras: dict | None = None,
    skip: frozenset[str] | set[str] = frozenset(),
) -> list:
    """All enrichment fields as (key, label, value) rows, dates humanized.

    Pass `extras` (holehe Result.extra-style dict) to fold platform facts
    in too; overlapping keys keep the enrichment value. `skip` omits
    top-level keys the caller already renders specially (location, uid…).
    The `_extractor` source rides along as its own row for provenance.
    """
    merged: dict = {}
    for source in (extras, enrich):
        if isinstance(source, dict):
            for k, v in source.items():
                if v in (None, "", [], {}) and k in merged:
                    continue
                merged[k] = v

    rows: list[tuple[str, str, str]] = []
    source_label = ""
    for key, value in merged.items():
        if key in _RESERVED_KEYS or key in skip:
            if key == "_extractor":
                source_label = _stringify(value)
            continue
        low = key.lower()
        is_date = any(h in low for h in _DATE_HINTS)
        for label, text in _flatten(value, _label(key)):
            if is_date:
                human = human_date(text)
                if human:
                    text = human
            rows.append((key, label, text))
    if source_label:
        rows.append(("_extractor", "Source", source_label))
    return rows


def enrichment_summary(rows: list, cap: int = 4) -> list:
    """First `cap` rows for a card, most-informative first."""
    return rows[:cap] if rows else []
