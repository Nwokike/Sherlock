"""BannerAd — single canonical banner ad builder (mobile only).

Plain helper so every screen (Home, Results, History, Settings, Sites)
shows the exact same ad. Consolidates the previous two implementations
(components/banner_ad.py and core/styles.py) into one.

Revenue-critical: ad construction mirrors the original v1.x pattern —
production unit ID, standard 320x50 banner, mobile-only gate, plain
on_error handler. flet_ads 0.85.0 has no dispose() API, so no lifecycle
hooks here; Flet's renderer unmounts the native ad view with the tree.
"""

import logging

import flet as ft
from flet import Control

from core import tokens
from core.theme import adaptive_glass_bg, adaptive_glass_border

logger = logging.getLogger(__name__)

_UNIT_ID = "ca-app-pub-5679949845754640/5131365762"


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

        req = fta.AdRequest(
            keywords=[
                "osint",
                "security",
                "search",
                "technology",
                "investigation",
                "software",
                "tools",
            ]
        )
        ad = fta.BannerAd(
            unit_id=_UNIT_ID,
            width=320,
            height=50,
            request=req,
            on_load=lambda e: logger.info("BannerAd loaded successfully!"),
            on_error=lambda e: logger.warning(
                "BannerAd load error: %s", getattr(e, "data", e)
            ),
        )
    except Exception as e:
        logger.warning("Failed to load BannerAd: %s", e)
        return ft.Container(width=0, height=0)

    return ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    "SPONSORED",
                    size=tokens.FONT_XS,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    style=ft.TextStyle(letter_spacing=1),
                ),
                ad,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_XS,
        ),
        alignment=ft.Alignment.CENTER,
        padding=tokens.SPACE_SM,
        border_radius=tokens.RADIUS_LG,
        bgcolor=adaptive_glass_bg(page),
        border=ft.Border.all(1, adaptive_glass_border(page)),
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
        ),
    )
