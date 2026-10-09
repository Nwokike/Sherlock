"""Shared page services — mount once, reuse everywhere (flet 1.0.1).

Every ``Service`` construction registers a new entry on the page
(``page._services.register_service`` appends + pushes a wire update, no dedup).
Constructing ``HapticFeedback``/``Clipboard``/``Share``/``UrlLauncher`` inline
per-click therefore accumulates duplicate services over a long session.

``mount_shared_services(page)`` (called once from ``AppController.init``)
constructs one of each and stashes them on the page object. The ``shared_*``
getters take an optional page and otherwise resolve ``flet.context.page``
themselves, returning the mounted instance when available and falling back to
inline construction otherwise (test harness without a live page, or callers
that run before init). Fallback preserves today's behavior exactly.
"""

from __future__ import annotations

import logging

import flet as ft

logger = logging.getLogger("SharedServices")

_ATTR_NAMES = {
    "haptics": "shared_haptics",
    "clipboard": "shared_clipboard",
    "share": "shared_share",
    "url_launcher": "shared_url_launcher",
}


def mount_shared_services(page: ft.Page) -> None:
    """Construct one of each transient service and stash on the page.

    Construction self-registers through ``page._services`` (see flet
    ``controls/services/service.py``); the explicit ``services.append`` mirrors
    the existing FilePicker/Connectivity pattern in ``AppController.init``.
    Mounting is idempotent — a second call reuses the existing instances.
    """
    specs = (
        ("haptics", ft.HapticFeedback),
        ("clipboard", ft.Clipboard),
        ("share", ft.Share),
        ("url_launcher", ft.UrlLauncher),
    )
    for key, factory in specs:
        attr = _ATTR_NAMES[key]
        existing = getattr(page, attr, None)
        if existing is not None:
            continue
        try:
            instance = factory()
        except Exception as exc:
            logger.debug("Shared service %s unavailable: %s", key, exc)
            continue
        try:
            if instance not in page.services:
                page.services.append(instance)
        except Exception as exc:
            logger.debug("Shared service %s mount skipped: %s", key, exc)
        setattr(page, attr, instance)


def _current_page() -> ft.Page | None:
    try:
        from flet import context

        return context.page
    except Exception:
        return None


def _shared(page: ft.Page | None, key: str, factory):
    resolved = page if page is not None else _current_page()
    if resolved is not None:
        instance = getattr(resolved, _ATTR_NAMES[key], None)
        if instance is not None:
            return instance
    return factory()


def shared_haptics(page: ft.Page | None = None) -> ft.HapticFeedback:
    """Mounted HapticFeedback, or a fresh instance outside a live app."""
    return _shared(page, "haptics", ft.HapticFeedback)


def shared_clipboard(page: ft.Page | None = None) -> ft.Clipboard:
    """Mounted Clipboard, or a fresh instance outside a live app."""
    return _shared(page, "clipboard", ft.Clipboard)


def shared_share(page: ft.Page | None = None) -> ft.Share:
    """Mounted Share, or a fresh instance outside a live app."""
    return _shared(page, "share", ft.Share)


def shared_url_launcher(page: ft.Page | None = None) -> ft.UrlLauncher:
    """Mounted UrlLauncher, or a fresh instance outside a live app."""
    return _shared(page, "url_launcher", ft.UrlLauncher)
