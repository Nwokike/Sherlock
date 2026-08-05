"""Header — Sherlock branded top bar with theme toggle.

Clean, modern header with app icon + brand name + action icons.
Uses ft.context.page for page access (no page param needed).
"""

from collections.abc import Callable

import flet as ft
from flet import Control

from core import tokens
from core.theme import is_dark_mode


def _icon_btn(
    icon: str,
    on_click: Callable[[], None],
    tooltip: str = "",
    icon_color: str | None = None,
) -> Control:
    """Compact ink-enabled icon button."""
    return ft.Container(
        content=ft.Icon(
            icon,
            size=tokens.ICON_MD,
            color=icon_color or ft.Colors.ON_SURFACE,
        ),
        padding=tokens.SPACE_SM,
        border_radius=tokens.RADIUS_SM,
        ink=True,
        tooltip=tooltip,
        on_click=lambda e: on_click(),
    )


def Header(
    on_settings_click: Callable[[], None] | None = None,
    on_search_click: Callable[[], None] | None = None,
    on_refresh_click: Callable[[], None] | None = None,
) -> Control:
    """Sherlock branded header bar.

    Shows app icon + name on the left, action icons on the right.
    """
    from flet import context

    try:
        page = context.page
        is_dark = is_dark_mode(page)
    except Exception:
        is_dark = False

    def _toggle_theme():
        from flet import context

        page = context.page
        new_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        page.theme_mode = new_mode

    actions: list[Control] = []

    if callable(on_refresh_click):
        actions.append(_icon_btn(ft.Icons.REFRESH_ROUNDED, on_refresh_click, "Refresh"))

    if callable(on_search_click):
        actions.append(_icon_btn(ft.Icons.SEARCH_ROUNDED, on_search_click, "Search"))

    actions.append(
        _icon_btn(
            ft.Icons.DARK_MODE_ROUNDED if is_dark else ft.Icons.LIGHT_MODE_ROUNDED,
            _toggle_theme,
            "Dark Mode" if is_dark else "Light Mode",
        )
    )

    return ft.Container(
        padding=ft.Padding(
            left=tokens.SPACE_XL,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_LG,
            bottom=tokens.SPACE_SM,
        ),
        content=ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Image(
                                src="icon.png",
                                width=32,
                                height=32,
                                border_radius=tokens.RADIUS_SM,
                            ),
                        ),
                        ft.Text(
                            "Sherlock",
                            size=tokens.FONT_XL,
                            weight=ft.FontWeight.W_700,
                            color=ft.Colors.ON_SURFACE,
                        ),
                    ],
                    spacing=tokens.SPACE_MD,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(controls=actions, spacing=tokens.SPACE_XS),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
