"""Client-action builders with safe out-of-app fallbacks (flet 1.0, P1-3).

`ft.OpenUrl` and friends bind to the live page's services during
construction (`shared_service()` → `ft.context.page`) and raise
RuntimeError outside a running Flet app — e.g. in the unit-test harness.
Callers use these builders to decide between:

- action present  → instant client-side open, Python handler only closes;
- action is None  → legacy Python UrlLauncher path (with visible errors).

Only the specific page-context RuntimeError is caught — real problems
stay loud (owner rule: no swallowing).
"""

from __future__ import annotations

import flet as ft


def open_url_action(url: str) -> ft.OpenUrl | None:
    """An ft.OpenUrl bound to the current page, or None outside a live app."""
    try:
        return ft.OpenUrl(url)
    except RuntimeError:
        # No page context (test harness / early init) — caller falls back
        # to the Python launch path.
        return None
