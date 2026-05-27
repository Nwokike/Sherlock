"""Home view — search input and quick actions."""

from __future__ import annotations

import logging
from typing import Callable, Optional

import flet as ft

from core import tokens
from core.constants import APP_NAME, LBL_PASTE_CLIPBOARD, LBL_NO_RESULTS, LBL_HISTORY
from core.state import state
from core.theme import AppColors
from core.styles import glass_card

logger = logging.getLogger(__name__)

_USERNAME_RE = None


def _is_valid_username(text: str) -> bool:
    return len(text.strip()) >= 1


def build_home_view(
    page: ft.Page,
    on_navigate: Callable,
    storage,
    ad_service,
    on_search: Callable,
) -> ft.View:
    username_ref = ft.Ref[ft.TextField]()
    recent_list = ft.Ref[ft.Column]()
    progress_bar = ft.Ref[ft.ProgressBar]()

    def _perform_search(username: str):
        if not _is_valid_username(username):
            if username_ref.current:
                username_ref.current.error_text = "Enter a username"
                page.update()
            return
        state.current_username = username.strip()
        on_search(username.strip())

    def _on_submit(e):
        if username_ref.current:
            _perform_search(username_ref.current.value.strip())

    def _on_search_click(e):
        if username_ref.current:
            _perform_search(username_ref.current.value.strip())

    async def _paste_clipboard(e):
        try:
            text = await page.get_clipboard()
            if text and username_ref.current:
                username_ref.current.value = text.strip()
                username_ref.current.error_text = None
                page.update()
                _perform_search(text.strip())
        except Exception:
            pass

    async def _load_history():
        try:
            raw = await storage.get("sherlock_history")
            if raw:
                import json
                entries = json.loads(raw)
                recent_list.current.controls.clear()
                for entry in entries[-5:]:
                    username = entry.get("username", "")
                    found = entry.get("found", 0)
                    total = entry.get("total", 0)
                    ts = entry.get("timestamp", "")

                    tile = ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.PERSON_SEARCH_OUTLINED,
                                    size=tokens.ICON_MD,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            username,
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        ft.Text(
                                            f"{found}/{total} found",
                                            size=tokens.FONT_XS,
                                            color=ft.Colors.with_opacity(
                                                0.5, ft.Colors.ON_SURFACE
                                            ),
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                ft.Icon(
                                    ft.Icons.CHEVRON_RIGHT,
                                    size=tokens.ICON_SM,
                                    color=ft.Colors.with_opacity(
                                        0.3, ft.Colors.ON_SURFACE
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding(
                            left=tokens.SPACE_LG,
                            right=tokens.SPACE_LG,
                            top=12,
                            bottom=12,
                        ),
                        on_click=lambda e, u=username: _perform_search(u),
                        border=ft.border.only(
                            bottom=ft.BorderSide(
                                0.5, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
                            )
                        ),
                    )
                    recent_list.current.controls.append(tile)
                page.update()
        except Exception:
            pass

    def _build_progress_section():
        progress = ft.Container(
            visible=False,
            content=ft.Column(
                controls=[
                    ft.ProgressBar(
                        ref=progress_bar,
                        color=ft.Colors.PRIMARY,
                        bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
                        height=3,
                    ),
                    ft.Text(
                        "Searching...",
                        size=tokens.FONT_SM,
                        color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                spacing=tokens.SPACE_XS,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(
                left=tokens.SPACE_LG,
                right=tokens.SPACE_LG,
                top=tokens.SPACE_MD,
                bottom=0,
            ),
        )
        return progress

    progress_section = _build_progress_section()

    header = ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(height=40),
                ft.Icon(
                    ft.Icons.PERSON_SEARCH_ROUNDED,
                    size=64,
                    color=ft.Colors.PRIMARY,
                ),
                ft.Container(height=8),
                ft.Text(
                    APP_NAME,
                    size=28,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.ON_SURFACE,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Hunt down social media accounts\nby username across 400+ networks",
                    size=tokens.FONT_MD,
                    color=ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE),
                    text_align=ft.TextAlign.CENTER,
                    height=40,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_XXL,
            bottom=tokens.SPACE_XL,
        ),
    )

    search_box = ft.Container(
        content=ft.Column(
            controls=[
                ft.TextField(
                    ref=username_ref,
                    hint_text="Enter username...",
                    prefix_icon=ft.Icons.SEARCH,
                    border_radius=tokens.RADIUS_LG,
                    border_width=1.5,
                    border_color=ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE),
                    focused_border_color=ft.Colors.PRIMARY,
                    bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
                    filled=True,
                    fill_color=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
                    text_style=ft.TextStyle(
                        size=tokens.FONT_LG,
                    ),
                    on_submit=_on_submit,
                    suffix=ft.IconButton(
                        icon=ft.Icons.PASTE_ROUNDED,
                        tooltip=LBL_PASTE_CLIPBOARD,
                        on_click=_paste_clipboard,
                    ),
                ),
                ft.Container(height=tokens.SPACE_MD),
                ft.FilledButton(
                    content=ft.Text(
                        "Search",
                        size=tokens.FONT_LG,
                        weight=ft.FontWeight.W_600,
                    ),
                    on_click=_on_search_click,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(tokens.RADIUS_LG),
                        padding=ft.Padding(
                            left=tokens.SPACE_XL * 2,
                            right=tokens.SPACE_XL * 2,
                            top=tokens.SPACE_MD,
                            bottom=tokens.SPACE_MD,
                        ),
                    ),
                    width=240,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=0,
            bottom=tokens.SPACE_LG,
        ),
        alignment=ft.Alignment.CENTER,
    )

    recent_section = ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(
                                "Recent",
                                size=tokens.FONT_SM,
                                weight=ft.FontWeight.W_700,
                                color=ft.Colors.with_opacity(
                                    0.5, ft.Colors.ON_SURFACE
                                ),
                                style=ft.TextStyle(letter_spacing=1),
                            ),
                            ft.Container(expand=True),
                            ft.TextButton(
                                content=ft.Text(
                                    "See all",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.PRIMARY,
                                ),
                                on_click=lambda e: on_navigate("/history"),
                            ),
                        ]
                    ),
                    padding=ft.Padding(
                        left=tokens.SPACE_LG,
                        right=tokens.SPACE_LG,
                        top=tokens.SPACE_MD,
                        bottom=tokens.SPACE_XS,
                    ),
                ),
                ft.Column(ref=recent_list, spacing=0),
            ],
            spacing=0,
        ),
    )

    main_content = ft.ListView(
        controls=[header, search_box, progress_section, recent_section],
        spacing=0,
        expand=True,
    )

    ad_banner = ad_service.get_banner_ad()

    controls = [main_content]
    if ad_banner:
        controls.append(ad_banner)

    view = ft.View(
        route="/home",
        controls=controls,
        padding=0,
        spacing=0,
    )

    page.run_task(_load_history)

    return view
