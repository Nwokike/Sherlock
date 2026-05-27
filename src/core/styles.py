"""Reusable widget factories."""

import flet as ft

from core import tokens


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
                ) if icon else ft.Container(width=0),
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
        border=ft.border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
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
