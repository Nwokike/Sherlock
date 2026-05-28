"""Reusable widget factories."""

import logging

import flet as ft

from core import tokens

logger = logging.getLogger(__name__)


def section_header(text: str) -> ft.Container:
    return ft.Container(
        content=ft.Text(
            text,
            size=tokens.FONT_SM,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.PRIMARY,
            style=ft.TextStyle(letter_spacing=1),
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_XS,
        ),
    )


def setting_tile(
    icon: ft.Icons = None,
    title: str = "",
    subtitle: str = "",
    on_click=None,
) -> ft.Container:
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(
                    icon,
                    size=tokens.ICON_LG,
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
                        ),
                        ft.Text(
                            subtitle,
                            size=tokens.FONT_XS,
                            color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                        ),
                    ],
                    spacing=tokens.SPACE_XXS,
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_LG,
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


def glass_card(content: ft.Control, **kwargs) -> ft.Container:
    return ft.Container(
        content=content,
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_MD,
        ),
        border_radius=tokens.RADIUS_LG,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
        border=ft.Border.all(
            width=1, color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
        ),
        **kwargs,
    )


def solid_card(content: ft.Control, **kwargs) -> ft.Container:
    return ft.Container(
        content=content,
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_MD,
        ),
        border_radius=tokens.RADIUS_LG,
        **kwargs,
    )


def build_banner_ad(
    page: ft.Page, unit_id: str = "ca-app-pub-5679949845754640/5131365762"
) -> ft.Control:
    """Build a glass-container-wrapped banner ad (mobile only).

    Exact pattern from SpanInsight: "SPONSORED" label + BannerAd
    inside a frosted glass container. Returns empty Container on desktop.
    """
    if page.platform not in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
        return ft.Container(width=0, height=0)

    try:
        import flet_ads as fta

        ad = fta.BannerAd(
            unit_id=unit_id,
            width=320,
            height=50,
            on_error=lambda e: None,
        )
    except Exception as e:
        logger.warning("Failed to load BannerAd: %s", e)
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
            spacing=4,
        ),
        alignment=ft.Alignment.CENTER,
        padding=8,
        border_radius=tokens.RADIUS_LG,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
        ),
    )
