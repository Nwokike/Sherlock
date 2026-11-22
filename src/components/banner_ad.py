"""BannerAd — single canonical banner ad builder (mobile only).

One helper so every screen (Home, Results, History, Settings, Sites) shows
the exact same ad. Production unit ID lives in core/constants.py
(AD_BANNER_UNIT_ID).

Revenue-critical sizing: the glass container stretches FULL WIDTH on every
screen — Home/History/Results wrap their banners in shrink-wrap Columns
(320px, left-aligned) while Settings' ListView forces full width, so a
stretcher Row with an expand=True banner equalizes all screens to the
Settings look. The ad itself stays pinned at its native 320x50 (fixed
width/height via LayoutControl) and is centered inside the stretched glass. Never set ``alignment``
on a wide Container — it can expand to fill the parent's offer and caused
the full-page regression. No SPONSORED label by design (removed
intentionally 2026-09-03).

The mounted-but-unfilled AdView renders as an empty box ("#" placeholder on
some devices): if this banner ever appears empty on mobile, open Settings →
Troubleshooting & Logs — the on_error handler writes the exact AdMob failure
code there. flet_ads has no dispose() API; Flet's renderer unmounts the
native ad view with the tree.
"""

import logging

import flet as ft
from flet import Control

from core import tokens
from core.constants import AD_BANNER_UNIT_ID
from core.theme import adaptive_glass_bg, adaptive_glass_border

logger = logging.getLogger(__name__)


# Screen-level banners are constructed once and reused across re-renders.
# This is revenue-critical, not just a perf nicety: the shipped Dart
# (flutter/flet_ads/lib/src/banner.dart:20-82) builds a NEW native BannerAd on
# every widget build and only calls load() when !_isLoaded — so any re-render
# after the first load produces a fresh, UNLOADED, blank ad. Returning the
# same Python control keeps the same widget and its State, so the ad stays
# filled and keeps accruing AdMob's own auto-refresh impressions.
_BANNER_POOL: dict[str, Control] = {}
# The page each pooled control was built under: its glass colors are baked in
# at build time, so a control must never be handed to a different page.
_BANNER_POOL_PAGES: dict[str, object] = {}


def _resolve_page(page: ft.Page | None):
    if page is not None:
        return page
    try:
        from flet import context

        return context.page
    except Exception:
        return None


def pooled_banner_ad(slot: str, page: ft.Page | None = None) -> Control:
    """Return the banner for `slot`, building it once and reusing it after.

    Safe to call from any render path: the same control object comes back
    every time, so the ad is never re-requested by a re-render and never goes
    blank. Rebuilt only when the requesting page differs from the one the
    control was built under.
    """
    resolved = _resolve_page(page)
    ad = _BANNER_POOL.get(slot)
    if ad is not None and _BANNER_POOL_PAGES.get(slot) is resolved:
        return ad
    ad = build_banner_ad(page)
    _BANNER_POOL[slot] = ad
    _BANNER_POOL_PAGES[slot] = resolved
    return ad


def clear_banner_pool() -> None:
    """Drop every pooled banner (page teardown / theme change).

    Pooled controls carry the page they were built under — their glass colors
    are frozen at build time — so keeping them past a teardown would show a
    stale theme and hold dead native views. The next render path simply
    rebuilds what it needs.
    """
    _BANNER_POOL.clear()
    _BANNER_POOL_PAGES.clear()


def build_banner_ad(page: ft.Page | None = None) -> Control:
    """Glass-container-wrapped banner ad (mobile only).

    `page` is optional; during component rendering it is resolved via
    `flet.context.page` when omitted (the old core/styles.py signature).
    On desktop/web it renders an empty zero-size container, so it is
    safe to place on shared screens.
    """
    if page is None:
        try:
            from flet import context

            page = context.page
        except Exception:
            return ft.Container(width=0, height=0)

    if not page or not hasattr(page, "platform"):
        return ft.Container(width=0, height=0)

    try:
        if not page.platform.is_mobile():
            return ft.Container(width=0, height=0)
    except Exception:
        return ft.Container(width=0, height=0)

    try:
        import flet_ads as fta

        ad = fta.BannerAd(
            unit_id=AD_BANNER_UNIT_ID,
            width=320,
            height=50,
            on_load=lambda e: logger.info("BannerAd loaded"),
            on_error=lambda e: logger.warning(
                "BannerAd load error: %s", getattr(e, "data", e)
            ),
            # Revenue telemetry (measurement only — never gates serving):
            # impressions and paid events land in the in-app terminal so the
            # owner can see what each slot actually earns.
            on_impression=lambda e: logger.info("BannerAd impression"),
            on_paid=lambda e: logger.info(
                "BannerAd paid: %s", getattr(e, "data", None)
            ),
        )
    except Exception as e:
        logger.warning("Failed to load BannerAd: %s", e)
        return ft.Container(width=0, height=0)

    banner = ft.Container(
        content=ft.Column(
            [
                ft.Container(content=ad, width=320, height=50),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_XS,
            tight=True,
        ),
        expand=True,
        padding=tokens.SPACE_SM,
        border_radius=tokens.RADIUS_LG,
        bgcolor=adaptive_glass_bg(page),
        border=ft.Border.all(1, adaptive_glass_border(page)),
    )

    # Full-width wrapper: the glass banner must stretch edge-to-edge on every
    # screen (Home/History/Results use Columns that shrink-wrap children, so a
    # bare container stays 320px and left-aligned there; Settings' ListView is
    # the only parent that already forces full width). A zero-margin stretcher
    # Row hosting the expand=True banner equalizes all screens. The inner
    # Column centers the 320x50 ad within the stretched glass.
    return ft.Row(
        controls=[banner],
        alignment=ft.MainAxisAlignment.CENTER,
    )
