"""ActiveScanBanner — persistent banner shown when a scan is running in background."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft
from flet import Control

from core import tokens
from core.constants import MODE_EMAIL
from core.theme import AppColors


def ActiveScanBanner(
    target_query: str,
    search_mode: str,
    checked: int = 0,
    total: int = 0,
    on_tap: Callable[[], None] | None = None,
) -> Control:
    """Build a sticky floating notification banner indicating an active background scan."""
    is_email = search_mode == MODE_EMAIL
    icon_type = (
        ft.Icons.ALTERNATE_EMAIL_ROUNDED if is_email else ft.Icons.PERSON_SEARCH_ROUNDED
    )

    pct = int(checked / max(total, 1) * 100) if total > 0 else 0
    progress_str = f"{checked}/{total} ({pct}%)" if total > 0 else "Initializing..."

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(
                        icon_type,
                        size=tokens.ICON_SM,
                        color=AppColors.PRIMARY,
                    ),
                    width=32,
                    height=32,
                    border_radius=16,
                    bgcolor=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[
                        ft.Row(
                            [
                                ft.Text(
                                    f"Scanning '{target_query}'",
                                    size=tokens.FONT_SM,
                                    weight=ft.FontWeight.W_600,
                                    color=AppColors.PRIMARY,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    expand=True,
                                ),
                                ft.Text(
                                    progress_str,
                                    size=tokens.FONT_XS,
                                    weight=ft.FontWeight.W_500,
                                    color=AppColors.PRIMARY,
                                ),
                            ],
                            spacing=tokens.SPACE_XS,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.ProgressBar(
                            value=(checked / max(total, 1)) if total > 0 else None,
                            color=AppColors.PRIMARY,
                            bgcolor=ft.Colors.with_opacity(0.12, AppColors.PRIMARY),
                            height=3,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.TextButton(
                    content=ft.Text(
                        "View",
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.BOLD,
                        color=AppColors.PRIMARY,
                    ),
                    on_click=lambda e: on_tap() if on_tap else None,
                ),
            ],
            spacing=tokens.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_SM, tokens.SPACE_SM
        ),
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
        ),
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(1.2, ft.Colors.with_opacity(0.4, AppColors.PRIMARY)),
        ink=True,
        on_click=lambda e: on_tap() if on_tap else None,
    )
