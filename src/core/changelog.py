"""Bundled changelog shown by the update dialog when the app is up to
date — works fully offline. One line per release; keep the entry for the
current APP_VERSION in sync when bumping (guarded by tests)."""

CHANGELOG: dict[str, str] = {
    "2.1.0": (
        "• Full dependency squeeze and 3,300+ platform polish\n"
        "• Full ecosystem integration on 3,300+ sites engine\n"
        "• Username engine upgraded to Maigret with 3,300+ platforms\n"
        "• Fix: msgpack-safe site selection (list instead of set)"
    ),
    "2.0.0": (
        "• Dual-Mode OSINT: Username & Email search\n"
        "• 120+ platforms email check via holehe\n"
        "• Profile enrichment (bio, location, followers)\n"
        "• Redesigned results with recovery hints\n"
        "• Privacy-first: 100% on-device OSINT"
    ),
}


def notes_for(version: str) -> str:
    """Changelog entry for a version, falling back to the latest entry."""
    return CHANGELOG.get(version) or next(reversed(CHANGELOG.values()), "")
