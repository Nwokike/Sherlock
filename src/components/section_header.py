"""Section header — uppercase label row for settings / grouped lists."""

import flet as ft
from flet import Control

from core import tokens


def SectionHeader(text: str) -> Control:
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
