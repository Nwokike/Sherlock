"""TargetsCard — network-scope summary card on the Home dashboard.

Restores the pre-restructure "targets card": shows whether the search
will scan all networks or a custom selection, and opens the network
selection screen (SitesScreen) on tap. Plain function (no hooks) so it
is unit-testable without a renderer.
"""

import flet as ft
from flet import Control

from core import tokens
from core.theme import AppColors, adaptive_glass_bg, adaptive_glass_border

# Matches the marketing copy used by the search bar hint.
FALLBACK_TOTAL_LABEL = "400+"


def TargetsCard(
    selected_count: int,
    total_count: int,
    on_open: callable = None,
    page: ft.Page | None = None,
) -> Control:
    """Gold-tinted card summarising the current network scope.

    - selected_count == 0 → scanning everything.
    - selected_count > 0  → scanning a custom subset.

    Tapping anywhere on the card fires on_open() so the user can
    customize which networks get scanned.
    """
    custom_scope = selected_count > 0

    if custom_scope:
        title = f"{selected_count} networks selected"
        subtitle = "Scanning your custom network list"
        icon = ft.Icons.CHECK_CIRCLE_ROUNDED
    else:
        title = "All networks selected"
        subtitle = f"Scanning all {total_count or FALLBACK_TOTAL_LABEL} social networks"
        icon = ft.Icons.PUBLIC_ROUNDED

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, size=tokens.ICON_MD, color=AppColors.PRIMARY),
                    width=tokens.ICON_BACKDROP,
                    height=tokens.ICON_BACKDROP,
                    border_radius=tokens.ICON_BACKDROP_RADIUS,
                    bgcolor=ft.Colors.with_opacity(
                        tokens.OPACITY_LIGHT, AppColors.PRIMARY
                    ),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            title,
                            size=tokens.FONT_MD,
                            weight=ft.FontWeight.W_600,
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
                ft.Text(
                    "Customize",
                    size=tokens.FONT_XS,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.PRIMARY,
                    font_family="Outfit",
                ),
                ft.Icon(
                    ft.Icons.CHEVRON_RIGHT_ROUNDED,
                    size=tokens.ICON_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=tokens.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_MD,
            right=tokens.SPACE_SM,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_MD,
        ),
        margin=ft.Margin(tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0),
        border_radius=tokens.RADIUS_MD,
        bgcolor=adaptive_glass_bg(page),
        border=ft.Border.all(
            tokens.BORDER_WIDTH_DEFAULT,
            ft.Colors.with_opacity(tokens.OPACITY_MEDIUM, AppColors.PRIMARY)
            if custom_scope
            else adaptive_glass_border(page),
        ),
        ink=True,
        on_click=on_open,
    )
