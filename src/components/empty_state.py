"""EmptyState — centered icon + title + optional message + optional action.

Modern, spacious empty state with circular icon backdrop.
Plain function — testable without a renderer.
"""

from collections.abc import Callable

import flet as ft
from flet import Control

from core import tokens


def EmptyState(
    title: str,
    message: str = "",
    action_label: str | None = None,
    on_action: Callable | None = None,
    icon: ft.IconData = ft.Icons.INFO_OUTLINE,
) -> Control:
    items = [
        ft.Container(
            content=ft.Icon(
                icon,
                size=tokens.ICON_EMPTY,
                color=ft.Colors.with_opacity(tokens.OPACITY_MEDIUM, ft.Colors.PRIMARY),
            ),
            width=tokens.ICON_EMPTY * 2,
            height=tokens.ICON_EMPTY * 2,
            border_radius=tokens.ICON_EMPTY,
            bgcolor=ft.Colors.with_opacity(tokens.OPACITY_LIGHT, ft.Colors.PRIMARY),
            alignment=ft.Alignment.CENTER,
            margin=ft.Margin(0, 0, 0, tokens.SPACE_XL),
        ),
        ft.Text(
            title,
            size=tokens.FONT_XL,
            weight=ft.FontWeight.W_600,
            text_align=ft.TextAlign.CENTER,
            color=ft.Colors.ON_SURFACE,
        ),
    ]
    if message:
        items.append(
            ft.Text(
                message,
                size=tokens.FONT_MD,
                color=ft.Colors.with_opacity(tokens.OPACITY_DIM, ft.Colors.ON_SURFACE),
                text_align=ft.TextAlign.CENTER,
                width=tokens.MESSAGE_MAX_WIDTH,
            )
        )
    if action_label and on_action:
        items.append(ft.Container(height=tokens.SPACE_SM))
        items.append(
            ft.FilledButton(
                content=ft.Text(action_label, weight=ft.FontWeight.W_600),
                on_click=on_action,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                    padding=ft.Padding(
                        left=tokens.SPACE_XL,
                        right=tokens.SPACE_XL,
                        top=tokens.SPACE_SM,
                        bottom=tokens.SPACE_SM,
                    ),
                ),
            )
        )
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            items,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
    )
