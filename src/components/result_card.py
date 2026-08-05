"""ResultCard — single SiteResult row with status chip, query time, and URL.

Premium result card with clear visual hierarchy, status color coding,
and ink interaction.
"""

import flet as ft
from flet import Control

from core import tokens
from core.theme import AppColors


def ResultCard(
    site_name: str,
    status: str,
    url_user: str | None = None,
    url_main: str | None = None,
    query_time: float | None = None,
    on_open: callable = None,
) -> Control:
    """Build a single result tile for the results tabs."""
    if status == "Claimed":
        icon = ft.Icons.CHECK_CIRCLE_ROUNDED
        icon_color = AppColors.SUCCESS
    elif status in ("Available", "Illegal"):
        icon = ft.Icons.CANCEL_ROUNDED
        icon_color = ft.Colors.with_opacity(tokens.OPACITY_MUTED, ft.Colors.ON_SURFACE)
    elif status == "WAF":
        icon = ft.Icons.SHIELD_ROUNDED
        icon_color = AppColors.WARNING
    else:
        icon = ft.Icons.ERROR_OUTLINE_ROUNDED
        icon_color = AppColors.WARNING

    display_url = url_user or url_main or site_name

    async def _open(e):
        if on_open:
            on_open()

    # Status chip
    chip_label = "WAF BLOCKED" if status == "WAF" else status
    chip_color = (
        AppColors.SUCCESS
        if status == "Claimed"
        else AppColors.WARNING
        if status == "WAF"
        else ft.Colors.with_opacity(tokens.OPACITY_DIM, ft.Colors.ON_SURFACE)
    )
    chip_bg = (
        ft.Colors.with_opacity(tokens.OPACITY_LIGHT, AppColors.SUCCESS)
        if status == "Claimed"
        else (
            ft.Colors.with_opacity(tokens.OPACITY_LIGHT, AppColors.WARNING)
            if status == "WAF"
            else ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE)
        )
    )

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, size=tokens.RESULT_ICON, color=icon_color),
                    width=36,
                    height=36,
                    border_radius=18,
                    bgcolor=ft.Colors.with_opacity(tokens.OPACITY_LIGHT, icon_color),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Text(
                                    site_name,
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Text(
                                    f"({query_time:.2f}s)" if query_time else "",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.with_opacity(
                                        tokens.OPACITY_MUTED, ft.Colors.ON_SURFACE
                                    ),
                                ),
                            ],
                            spacing=tokens.SPACE_SM,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text(
                            display_url,
                            size=tokens.FONT_XS,
                            color=ft.Colors.with_opacity(
                                tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                            ),
                            no_wrap=False,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=tokens.SPACE_XXS,
                    expand=True,
                ),
                ft.Container(
                    content=ft.Text(
                        chip_label,
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.W_700,
                        color=chip_color,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_SM,
                        tokens.SPACE_XS,
                        tokens.SPACE_SM,
                        tokens.SPACE_XS,
                    ),
                    border_radius=tokens.RADIUS_SM,
                    bgcolor=chip_bg,
                ),
            ],
            spacing=tokens.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=12,
            bottom=12,
        ),
        border=ft.Border.only(
            bottom=ft.BorderSide(
                width=0.5,
                color=ft.Colors.with_opacity(
                    tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE
                ),
            )
        ),
        on_click=_open if url_user else None,
        ink=True,
    )
