"""BannerAd component wrapper — glassmorphic banner ad (mobile only).

Uses ft.context.page pattern so callers don't need to pass page.
"""

import logging

import flet as ft
from flet import Control

from core import tokens

logger = logging.getLogger(__name__)

_UNIT_ID = "ca-app-pub-5679949845754640/5131365762"


def build_banner_ad(page: ft.Page | None = None) -> Control:
    """Build a glass-container-wrapped banner ad (mobile only)."""
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
            unit_id=_UNIT_ID,
            width=320,
            height=50,
            on_error=lambda e: None,
        )
    except Exception as e:
        logger.warning("Failed to load BannerAd: %s", e)
        return ft.Container(width=0, height=0)

    return ft.Container(
        content=ft.Column(
            [ad],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
        alignment=ft.Alignment.CENTER,
        padding=tokens.SPACE_SM,
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE),
        border=ft.Border.all(
            1,
            ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
        ),
    )
