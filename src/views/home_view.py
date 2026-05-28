"""Home view — search input, configuration status, and recent searches."""

from __future__ import annotations

import logging
from typing import Callable

import flet as ft

from core import tokens
from core.constants import APP_NAME, LBL_PASTE_CLIPBOARD, STORAGE_THEME
from core.state import state
from core.styles import build_banner_ad

logger = logging.getLogger(__name__)


def _is_valid_username(text: str) -> bool:
    return len(text.strip()) >= 1


def build_home_view(
    page: ft.Page,
    on_navigate: Callable,
    storage,
    on_search: Callable,
) -> ft.View:
    username_ref = ft.Ref[ft.TextField]()
    recent_list = ft.Ref[ft.Column]()
    progress_bar = ft.Ref[ft.ProgressBar]()
    theme_btn_ref = ft.Ref[ft.IconButton]()

    async def _toggle_quick_theme(e=None):
        is_dark = page.theme_mode == ft.ThemeMode.DARK or (
            page.theme_mode == ft.ThemeMode.SYSTEM
            and page.platform_brightness == ft.Brightness.DARK
        )
        new_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        page.theme_mode = new_mode
        state.theme_mode = new_mode
        if storage:
            await storage.set(
                STORAGE_THEME,
                "light" if new_mode == ft.ThemeMode.LIGHT else "dark",
            )
        if theme_btn_ref.current:
            theme_btn_ref.current.icon = (
                ft.Icons.WB_SUNNY_ROUNDED
                if new_mode == ft.ThemeMode.DARK
                else ft.Icons.NIGHTLIGHT_ROUNDED
            )
            theme_btn_ref.current.tooltip = (
                "Switch to Light Theme"
                if new_mode == ft.ThemeMode.DARK
                else "Switch to Dark Theme"
            )
        page.update()

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
            clipboard = ft.Clipboard()
            text = await clipboard.get()
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
                                            f"{found}/{total} matches found",
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
                                    ft.Icons.CHEVRON_RIGHT_ROUNDED,
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
                        border=ft.Border.only(
                            bottom=ft.BorderSide(
                                0.5, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
                            )
                        ),
                    )
                    recent_list.current.controls.append(tile)
                page.update()
        except Exception as e:
            logger.error("Failed to load history on home view: %s", e)

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

    # Premium targets config card showing selected sites scan scope
    def _build_targets_card():
        selected_count = len(state.selected_sites)
        if selected_count == 0:
            label = "Scanning all social networks (400+)"
            icon = ft.Icons.ALL_INCLUSIVE_ROUNDED
        else:
            label = f"Scanning {selected_count} selected target networks"
            icon = ft.Icons.CHECKLIST_RTL_ROUNDED

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, size=18, color=ft.Colors.PRIMARY),
                    ft.Text(
                        label,
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.W_500,
                        color=ft.Colors.with_opacity(0.7, ft.Colors.ON_SURFACE),
                        expand=True,
                    ),
                    ft.TextButton(
                        content=ft.Text(
                            "Customize",
                            size=tokens.FONT_XS,
                            color=ft.Colors.PRIMARY,
                            weight=ft.FontWeight.BOLD,
                        ),
                        on_click=lambda e: on_navigate("/sites"),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(tokens.SPACE_LG, 2, tokens.SPACE_MD, 2),
            border_radius=tokens.RADIUS_MD,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border=ft.Border.all(
                width=1, color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)
            ),
            margin=ft.Margin(tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_MD),
        )

    progress_section = _build_progress_section()
    targets_card = _build_targets_card()

    header = ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(height=40),
                ft.Image(
                    src="icon.png",
                    width=80,
                    height=80,
                    border_radius=16,
                    fit=ft.BoxFit.CONTAIN,
                ),
                ft.Container(height=12),
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
            top=tokens.SPACE_XL,
            bottom=tokens.SPACE_LG,
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
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    filled=True,
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
                        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_LG),
                        bgcolor=ft.Colors.PRIMARY,
                        color=ft.Colors.WHITE,
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
            bottom=tokens.SPACE_MD,
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
                                "Recent Searches",
                                size=tokens.FONT_SM,
                                weight=ft.FontWeight.W_700,
                                color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
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
        controls=[header, search_box, targets_card, progress_section, recent_section],
        spacing=0,
        expand=True,
    )

    ad_banner = build_banner_ad(page)

    controls = [main_content]
    controls.append(ad_banner)

    is_dark = page.theme_mode == ft.ThemeMode.DARK or (
        page.theme_mode == ft.ThemeMode.SYSTEM
        and page.platform_brightness == ft.Brightness.DARK
    )
    appbar = ft.AppBar(
        title=ft.Row(
            [
                ft.Image(src="icon.png", width=28, height=28, border_radius=6),
                ft.Text("Sherlock", size=tokens.FONT_MD, weight=ft.FontWeight.BOLD),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        actions=[
            ft.IconButton(
                ref=theme_btn_ref,
                icon=ft.Icons.WB_SUNNY_ROUNDED
                if is_dark
                else ft.Icons.NIGHTLIGHT_ROUNDED,
                tooltip="Switch to Light Theme" if is_dark else "Switch to Dark Theme",
                on_click=lambda e: page.run_task(_toggle_quick_theme, e),
            ),
        ],
        bgcolor=ft.Colors.TRANSPARENT,
        center_title=False,
    )

    view = ft.View(
        route="/home",
        controls=[
            ft.SafeArea(
                ft.Container(
                    content=ft.Column(controls, expand=True, spacing=0),
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment.TOP_LEFT,
                        end=ft.Alignment.BOTTOM_RIGHT,
                        colors=[
                            ft.Colors.SURFACE,
                            ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
                        ],
                    ),
                    expand=True,
                ),
                expand=True,
            )
        ],
        appbar=appbar,
        padding=0,
        spacing=0,
    )

    page.run_task(_load_history)

    return view
