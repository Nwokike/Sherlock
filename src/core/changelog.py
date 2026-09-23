"""Bundled changelog shown by the update dialog when the app is up to
date — works fully offline. One line per release; keep the entry for the
current APP_VERSION in sync when bumping (guarded by tests)."""

CHANGELOG: dict[str, str] = {
    "2.2.0": (
        "• Bigger engine: 5,200+ enabled networks (Maigret 0.6.6 DB doubled)\n"
        "• Recursive search is real — secondary IDs scanned in a bounded pass\n"
        "• Email reborn on holehe-v2: 181 modules, rich profile extras, CSV/JSON/TXT/MD/HTML export\n"
        "• Bot-protection badges with exact cause + fix advice; keyword-match chips\n"
        "• Category presets + Scope-to-Filter one-tap scanning; Dating & new country chips\n"
        "• PDF: tappable links, page numbers, avatar cards; XMind evidence links & category sheets\n"
        "• Interactive graph viewer, Cypher export, evidence communities\n"
        "• Stealth: socks5 fixed everywhere, chrome131/Android fingerprints, I2P/cookies fields\n"
        "• Biometric History lock, DB health check, deep-enrichment & keywords toggles\n"
        "• Bundled Outfit font (offline startup), ~21MB leaner installs, 223 tests + CI gates"
    ),
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
