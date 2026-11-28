"""Pill dropdown — the proot-distro / CollabShell menu pattern.

A ``PopupMenuButton`` whose face is a small icon + value + chevron pill.
This is deliberately NOT ``ft.Dropdown``: Flet's dropdown renders a text
field, while the owner's apps use a real popup menu with the current choice
visible at once.
"""

from __future__ import annotations

import flet as ft

from core import tokens
from core.theme import AppColors


def pill_dropdown(
    label: str,
    icon: ft.IconData,
    options: list[str],
    value: str,
    on_select,
    *,
    tooltip: str = "",
    labels: dict[str, str] | None = None,
) -> ft.PopupMenuButton:
    """Build a compact popup-menu pill.

    ``labels`` maps an option value to its display text (the value itself is
    still what ``on_select`` receives), so keys stay exact while the face is
    readable — e.g. ``""`` displays as ``Auto``.
    """
    text_for = labels or {}

    def _text(option: str) -> str:
        return text_for.get(option, option)

    return ft.PopupMenuButton(
        content=ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, size=tokens.ICON_SM, color=AppColors.PRIMARY),
                    ft.Text(
                        text_for.get(value, value or label),
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.W_600,
                        color=AppColors.PRIMARY,
                        no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Icon(
                        ft.Icons.EXPAND_MORE_ROUNDED,
                        size=tokens.ICON_XS,
                        color=AppColors.PRIMARY,
                    ),
                ],
                spacing=tokens.SPACE_XXS,
                tight=True,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=5),
            border_radius=tokens.RADIUS_FULL,
            bgcolor=ft.Colors.with_opacity(tokens.OPACITY_LIGHT, AppColors.PRIMARY),
        ),
        items=[
            ft.PopupMenuItem(
                content=ft.Row(
                    controls=[
                        ft.Text(
                            _text(option),
                            size=tokens.FONT_XS,
                            weight=ft.FontWeight.W_600
                            if option == value
                            else ft.FontWeight.W_400,
                            color=ft.Colors.ON_SURFACE,
                        ),
                        *(
                            [
                                ft.Icon(
                                    ft.Icons.CHECK_ROUNDED,
                                    size=tokens.ICON_XS,
                                    color=AppColors.PRIMARY,
                                )
                            ]
                            if option == value
                            else []
                        ),
                    ],
                    spacing=tokens.SPACE_XS,
                ),
                on_click=lambda _e, option=option: on_select(option),
            )
            for option in options
        ],
        menu_position=ft.PopupMenuPosition.UNDER,
        tooltip=tooltip or label,
    )
