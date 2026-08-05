"""StatCard — a single numeric stat in a compact column with gradient accent.

Premium stat card with large number, label, and subtle color background.
"""

import flet as ft
from flet import Control

from core import tokens


def StatCard(label: str, value: str, color) -> Control:
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    value,
                    size=tokens.STAT_NUMBER,
                    weight=ft.FontWeight.W_800,
                    color=color,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    label,
                    size=tokens.FONT_XS,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                    ),
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=tokens.SPACE_XXS,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        expand=True,
        padding=ft.Padding(
            left=tokens.SPACE_SM,
            right=tokens.SPACE_SM,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_MD,
        ),
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, color),
    )
