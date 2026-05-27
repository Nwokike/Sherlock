"""Results view — live search results with found/not-found/error tabs."""

from __future__ import annotations

import logging
from typing import Callable, Optional

import flet as ft

from core import tokens
from core.state import state
from core.theme import AppColors
from services.sherlock_service import SearchProgress, SiteResult

logger = logging.getLogger(__name__)


def _build_result_tile(result: SiteResult) -> ft.Container:
    if result.status == "Claimed":
        icon = ft.Icons.CHECK_CIRCLE_ROUNDED
        icon_color = ft.Colors.GREEN
    elif result.status == "Available":
        icon = ft.Icons.CANCEL_ROUNDED
        icon_color = ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE)
    else:
        icon = ft.Icons.ERROR_OUTLINE_ROUNDED
        icon_color = ft.Colors.ORANGE

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(icon, size=tokens.ICON_SM, color=icon_color),
                ft.Column(
                    controls=[
                        ft.Text(
                            result.site_name,
                            size=tokens.FONT_MD,
                            weight=ft.FontWeight.W_500,
                        ),
                        ft.Text(
                            result.url_user or result.url_main or result.site_name,
                            size=tokens.FONT_XS,
                            color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                            no_wrap=False,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Container(
                    content=ft.Text(
                        result.status,
                        size=tokens.FONT_XXS,
                        weight=ft.FontWeight.W_700,
                        color=(
                            ft.Colors.GREEN if result.status == "Claimed"
                            else ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE)
                        ),
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_SM, tokens.SPACE_XS,
                        tokens.SPACE_SM, tokens.SPACE_XS,
                    ),
                    border_radius=tokens.RADIUS_SM,
                    bgcolor=(
                        ft.Colors.with_opacity(0.1, ft.Colors.GREEN)
                        if result.status == "Claimed"
                        else ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE)
                    ),
                ),
            ],
            spacing=tokens.SPACE_SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=12,
            bottom=12,
        ),
        border=ft.border.only(
            bottom=ft.BorderSide(0.5, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE))
        ),
        on_click=lambda e, u=result.url_user: (
            e.page.launch_url(u) if u else None
        ),
        ink=True,
    )


def build_results_view(
    page: ft.Page,
    progress: Optional[SearchProgress],
    on_navigate: Callable,
    on_restart: Callable,
    ad_service,
) -> ft.View:
    found_list = ft.Ref[ft.Column]()
    notfound_list = ft.Ref[ft.Column]()
    error_list = ft.Ref[ft.Column]()
    stats_text = ft.Ref[ft.Text]()
    progress_bar = ft.Ref[ft.ProgressBar]()
    progress_row = ft.Ref[ft.Row]()
    tab_container = ft.Ref[ft.Tabs]()

    def _build_stats():
        if not progress:
            return ft.Container()
        total = progress.total_sites
        checked = progress.checked_sites
        found = len(progress.found)
        not_found = len(progress.not_found)
        errors = len(progress.errors)

        return ft.Container(
            content=ft.Row(
                controls=[
                    _stat_card("Found", str(found), AppColors.SUCCESS),
                    _stat_card("Not Found", str(not_found), ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE)),
                    _stat_card("Errors", str(errors), AppColors.WARNING),
                    _stat_card("Total", str(total), ft.Colors.PRIMARY),
                ],
                spacing=tokens.SPACE_SM,
                alignment=ft.MainAxisAlignment.SPACE_EVENLY,
            ),
            padding=ft.Padding(
                left=tokens.SPACE_LG, right=tokens.SPACE_LG,
                top=tokens.SPACE_MD, bottom=tokens.SPACE_SM,
            ),
        )

    def _stat_card(label: str, value: str, color) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        value,
                        size=24,
                        weight=ft.FontWeight.W_700,
                        color=color,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        label,
                        size=tokens.FONT_XS,
                        color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            expand=True,
        )

    def _update_lists():
        if not progress:
            return

        found_list.current.controls.clear()
        for r in progress.found:
            found_list.current.controls.append(_build_result_tile(r))
        if not progress.found:
            found_list.current.controls.append(
                ft.Container(
                    content=ft.Text(
                        "No accounts found",
                        color=ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE),
                        text_align=ft.TextAlign.CENTER,
                    ),
                    padding=tokens.SPACE_XXL,
                    alignment=ft.Alignment.CENTER,
                )
            )

        notfound_list.current.controls.clear()
        for r in progress.not_found:
            notfound_list.current.controls.append(_build_result_tile(r))
        if not progress.not_found:
            notfound_list.current.controls.append(
                ft.Container(
                    content=ft.Text(
                        "All sites returned results",
                        color=ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE),
                        text_align=ft.TextAlign.CENTER,
                    ),
                    padding=tokens.SPACE_XXL,
                    alignment=ft.Alignment.CENTER,
                )
            )

        error_list.current.controls.clear()
        for r in progress.errors:
            error_list.current.controls.append(_build_result_tile(r))
        if not progress.errors:
            error_list.current.controls.append(
                ft.Container(
                    content=ft.Text(
                        "No errors",
                        color=ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE),
                        text_align=ft.TextAlign.CENTER,
                    ),
                    padding=tokens.SPACE_XXL,
                    alignment=ft.Alignment.CENTER,
                )
            )

    username = progress.username if progress else state.last_results_username

    appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK_ROUNDED,
            on_click=lambda e: on_navigate("/home"),
        ),
        title=ft.Text(username, size=tokens.FONT_LG, weight=ft.FontWeight.W_600),
        center_title=False,
        bgcolor=ft.Colors.TRANSPARENT,
        actions=[
            ft.IconButton(
                icon=ft.Icons.REFRESH_ROUNDED,
                tooltip="Search again",
                on_click=lambda e: on_restart(username),
            ),
        ],
    )

    def _build_tab(label: str, count: int, ref: ft.Ref) -> ft.Tab:
        return ft.Tab(
            text=f"{label} ({count})",
            content=ft.Container(
                content=ft.Column(
                    ref=ref,
                    spacing=0,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
                expand=True,
            ),
        )

    found_count = len(progress.found) if progress else 0
    notfound_count = len(progress.not_found) if progress else 0
    error_count = len(progress.errors) if progress else 0

    tabs = ft.Tabs(
        ref=tab_container,
        selected_index=0,
        tabs=[
            _build_tab("Found", found_count, found_list),
            _build_tab("Not Found", notfound_count, notfound_list),
            _build_tab("Errors", error_count, error_list),
        ],
        scrollable=False,
        indicator_color=ft.Colors.PRIMARY,
        label_color=ft.Colors.PRIMARY,
        unselected_label_color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
        expand=True,
    )

    _update_lists()

    controls = []
    if progress and progress.is_running:
        controls.append(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.ProgressBar(
                            ref=progress_bar,
                            color=ft.Colors.PRIMARY,
                            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
                            height=3,
                        ),
                        ft.Row(
                            ref=progress_row,
                            controls=[
                                ft.Text(
                                    f"Checking {progress.checked_sites}/{progress.total_sites} sites...",
                                    size=tokens.FONT_SM,
                                    color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                                ),
                                ft.Container(expand=True),
                                ft.TextButton(
                                    content=ft.Text(
                                        "Cancel",
                                        size=tokens.FONT_SM,
                                        color=AppColors.ERROR,
                                    ),
                                    on_click=lambda e: _cancel_search(),
                                ),
                            ],
                        ),
                    ],
                    spacing=2,
                ),
                padding=ft.Padding(
                    left=tokens.SPACE_LG, right=tokens.SPACE_LG,
                    top=tokens.SPACE_SM, bottom=0,
                ),
            )
        )

    controls.extend([
        _build_stats(),
        tabs,
    ])

    ad_banner = ad_service.get_banner_ad()
    if ad_banner:
        controls.append(ad_banner)

    view = ft.View(
        route="/results",
        controls=controls,
        appbar=appbar,
        padding=0,
        spacing=0,
    )

    return view
