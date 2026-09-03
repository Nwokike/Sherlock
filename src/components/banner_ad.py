"""BannerAd — single canonical banner ad builder (mobile only).

One helper so every screen (Home, Results, History, Settings, Sites) shows
the exact same ad. Production unit ID lives in core/constants.py
(AD_BANNER_UNIT_ID).

Revenue-critical sizing: the glass container stretches FULL WIDTH on every
screen — Home/History/Results wrap their banners in shrink-wrap Columns
(320px, left-aligned) while Settings' ListView forces full width, so a
stretcher Row with an expand=True banner equalizes all screens to the
Settings look. The ad itself stays pinned at its native 320x50 (AdSize
banner) and is centered inside the stretched glass. Never set ``alignment``
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
