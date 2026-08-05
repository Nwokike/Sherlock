"""LoadingState — centered progress ring + label, for in-screen waits.

Modern loading state with branded spinner color.
Plain function — testable without a renderer.
"""

import flet as ft
from flet import Control

from core import tokens


def LoadingState(label: str | None = None) -> Control:
    return ft.Container(
        alignment=ft.Alignment.CENTER,
        expand=True,
        content=ft.Column(
            controls=[
                ft.ProgressRing(
                    width=40,
                    height=40,
                    stroke_width=3,
                    color=ft.Colors.PRIMARY,
                ),
                ft.Container(height=tokens.SPACE_SM),
                ft.Text(
                    label or "Loading...",
                    size=tokens.FONT_MD,
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                    ),
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
    )
