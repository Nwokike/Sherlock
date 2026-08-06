"""Reusable widget factories — Sherlock × DDGS design language.

Glass cards, section headers, setting tiles, banner ads, and
adaptive helpers that switch between dark/light automatically.
"""

from collections.abc import Callable

import flet as ft

from core import tokens
from core.theme import (
    AppColors,
    adaptive_glass_bg,
    adaptive_glass_border,
)


# ─── SECTION HEADER ──────────────────────────────────────────────────────────


def section_header(text: str) -> ft.Container:
    """Uppercase section label."""
    return ft.Container(
        content=ft.Text(
            text,
            size=tokens.FONT_SM,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE_VARIANT,
            font_family="Outfit",
            style=ft.TextStyle(letter_spacing=0.5),
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_SM,
        ),
    )


# ─── GLASS CARD ──────────────────────────────────────────────────────────────


def glass_card(content: ft.Control, page: ft.Page | None = None) -> ft.Container:
    """Frosted glass card — adapts to dark/light."""
    return ft.Container(
        content=content,
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_MD,
        ),
        border_radius=tokens.RADIUS_LG,
        bgcolor=adaptive_glass_bg(page),
        border=ft.Border.all(1, adaptive_glass_border(page)),
    )


# ─── SOLID CARD ──────────────────────────────────────────────────────────────


def solid_card(content: ft.Control, page: ft.Page | None = None) -> ft.Container:
    """Solid surface card."""
    return ft.Container(
        content=content,
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_MD,
        ),
        border_radius=tokens.RADIUS_LG,
        bgcolor=AppColors.get_surface(page),
        border=ft.Border.all(1, AppColors.get_border(page)),
    )


# ─── SETTING TILE ────────────────────────────────────────────────────────────


def setting_tile(
    icon: ft.IconData | None = None,
    title: str = "",
    subtitle: str = "",
    on_click: Callable | None = None,
) -> ft.Container:
    """Settings row: icon + title + subtitle, clickable."""
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(
                    icon,
                    size=tokens.ICON_MD,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
                if icon
                else ft.Container(width=0),
                ft.Column(
                    controls=[
                        ft.Text(
                            title,
                            size=tokens.FONT_MD,
                            weight=ft.FontWeight.W_500,
                            font_family="Outfit",
                        ),
                        ft.Text(
                            subtitle,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            font_family="Outfit",
                        ),
                    ],
                    spacing=tokens.SPACE_XXS,
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=14,
            bottom=14,
        ),
        on_click=on_click,
    )


# ─── BANNER AD ───────────────────────────────────────────────────────────────


def build_banner_ad(page: ft.Page) -> ft.Control:
    """Glass-container-wrapped banner ad (mobile only).

    Requires page parameter. Caller must pass ft.context.page.
    """
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
            unit_id="ca-app-pub-5679949845754640/5131365762",
            width=320,
            height=50,
            on_error=lambda e: None,
        )
    except Exception:
        return ft.Container(width=0, height=0)

    return ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    "SPONSORED",
                    size=8,
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
