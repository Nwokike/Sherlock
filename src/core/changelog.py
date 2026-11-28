"""Bundled changelog shown by the update dialog when the app is up to
date — works fully offline. One line per release; keep the entry for the
current APP_VERSION in sync when bumping (guarded by tests)."""

CHANGELOG: dict[str, str] = {
    "2.4.0": (
        "• New Phone mode (beta): check which major platforms a phone number is registered on\n"
        "• Silent by design — pre-authentication endpoints only, no SMS or push is sent to the target\n"
        "• Surfaces disclosed identity hints: masked email, display name, profile photo, regional datacenter\n"
        "• Phone settings expose the real engine options: concurrency, any region, and platform/category filters\n"
        "• Android packaging fix: phone validators are extracted from the Python ZIP so the catalog loads on-device\n"
        "• Progress: one flusher updates Results and the shade notification from the same live snapshot\n"
        "• Results, history, cached reopen, exports and the shade notification all support phone scans"
    ),
    "2.3.0": (
        "• Scans now live in the notification shade: a foreground-service progress bar with a Cancel action, so you can leave the app and still watch or stop the hunt\n"
        "• Wake lock keeps the screen on while a scan runs; the service stops at 100% or when you cancel\n"
        "• Username and email scans show the SAME live counts in the app and the shade (email counts validator platforms, not networks)\n"
        '• A tiny tappable "Scanning…" pill sits below the header — tap it to jump back to Results\n'
        "• 11,000+ networks via Maigret 0.6.7, with a live count on every screen\n"
        "• Email checks retry through rate limits and render recovery details; TLS fingerprint bumped to chrome150\n"
        "• Settings: live notification status and privacy & ads verdict, with rows that stack under their label on small screens\n"
        "• Flet, flet-ads and flet-notifications upgraded to 1.1.2\n"
        "• Every option verified against the engines: no dead settings\n"
        "• Release notes on every build are generated from this changelog"
    ),
    "2.2.0": (
        "• 5,200+ platforms: Maigret 0.6.6 database doubled\n"
        "• Recursive search on by default, category presets, scope-to-filter\n"
        "• Email rebuilt on holehe-v2: 181 validators, honest results, new exports\n"
        "• Bot-protection badges, tappable PDF links, interactive graph viewer\n"
        "• Biometric History lock, offline font, 21MB smaller, 229 tests + CI gates"
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


def _version_key(version: str) -> tuple[tuple[int, ...], str]:
    """Stdlib dotted-int sort key ('1.10.0' > '1.9.0'); odd suffixes sort
    by their raw string so ordering stays deterministic."""
    head = version.split("-", 1)[0].split("+", 1)[0]
    parts = head.split(".")
    if all(p.isdigit() for p in parts):
        return (tuple(int(p) for p in parts), version)
    return ((), version)


def notes_for(version: str) -> str:
    """Changelog entry for a version, falling back to the NEWEST entry.

    Dict insertion order is not guaranteed to be newest-first once older
    versions are appended below the head, so the fallback picks the highest
    version key.
    """
    if version in CHANGELOG:
        return CHANGELOG[version]
    if not CHANGELOG:
        return ""
    return CHANGELOG[max(CHANGELOG, key=_version_key)]
