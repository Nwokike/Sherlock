"""StatCard — a single numeric stat in a compact column with gradient accent.

Premium stat card with large number, label, and subtle color background.
"""

import flet as ft
from flet import Control

from core import tokens


def StatCard(label: str, value: str, color) -> Control:
    val_str = str(value)
    # Scale font so 3- and 4-digit numbers (e.g. 509, 3302) fit without wrapping on small phones
    num_size = (
        15
        if len(val_str) >= 5
        else (16 if len(val_str) >= 4 else (18 if len(val_str) >= 3 else 20))
    )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    val_str,
                    size=num_size,
                    weight=ft.FontWeight.W_800,
                    color=color,
                    text_align=ft.TextAlign.CENTER,
                    no_wrap=True,
                    max_lines=1,
                ),
                ft.Text(
                    label,
                    size=tokens.FONT_XS,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                    ),
                    text_align=ft.TextAlign.CENTER,
                    no_wrap=True,
                    max_lines=1,
                ),
            ],
            spacing=tokens.SPACE_XXS,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        expand=True,
        padding=ft.Padding(
            left=tokens.SPACE_XS,
            right=tokens.SPACE_XS,
            top=tokens.SPACE_SM,
            bottom=tokens.SPACE_SM,
        ),
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, color),
    )
