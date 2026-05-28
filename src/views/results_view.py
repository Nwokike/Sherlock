"""Results view — live search results with live filtering and premium exports."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

import flet as ft

from core import tokens
from core.state import state
from core.theme import AppColors
from core.styles import build_banner_ad
from services.sherlock_service import SearchProgress, SiteResult

logger = logging.getLogger(__name__)


def _build_result_tile(result: SiteResult) -> ft.Container:
    if result.status == "Claimed":
        icon = ft.Icons.CHECK_CIRCLE_ROUNDED
        icon_color = ft.Colors.GREEN
    elif result.status == "Available" or result.status == "Illegal":
        icon = ft.Icons.CANCEL_ROUNDED
        icon_color = ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE)
    else:
        icon = ft.Icons.ERROR_OUTLINE_ROUNDED
        icon_color = ft.Colors.ORANGE

    async def _open_result_url(e, url=result.url_user):
        if url:
            await ft.UrlLauncher().launch_url(url)

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(icon, size=tokens.ICON_SM, color=icon_color),
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Text(
                                    result.site_name,
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                ),
                                ft.Text(
                                    f"({result.query_time:.2f}s)"
                                    if result.query_time
                                    else "",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.with_opacity(
                                        0.4, ft.Colors.ON_SURFACE
                                    ),
                                ),
                            ],
                            spacing=tokens.SPACE_XS,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
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
                            ft.Colors.GREEN
                            if result.status == "Claimed"
                            else ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE)
                        ),
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_SM,
                        tokens.SPACE_XS,
                        tokens.SPACE_SM,
                        tokens.SPACE_XS,
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
        border=ft.Border.only(
            bottom=ft.BorderSide(
                width=0.5, color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
            )
        ),
        on_click=_open_result_url if result.url_user else None,
        ink=True,
    )


def build_results_view(
    page: ft.Page,
    progress: Optional[SearchProgress],
    on_navigate: Callable,
    on_restart: Callable,
    on_cancel: Callable,
) -> ft.View:
    found_list = ft.Ref[ft.Column]()
    notfound_list = ft.Ref[ft.Column]()
    error_list = ft.Ref[ft.Column]()
    progress_bar = ft.Ref[ft.ProgressBar]()
    progress_row = ft.Ref[ft.Row]()
    tab_container = ft.Ref[ft.Tabs]()
    search_field = ft.Ref[ft.TextField]()

    # Filter query
    filter_query = ""

    def _build_stats():
        if not progress:
            return ft.Container()
        total = progress.total_sites
        found = len(progress.found)
        not_found = len(progress.not_found)
        errors = len(progress.errors)

        return ft.Container(
            content=ft.Row(
                controls=[
                    _stat_card("Found", str(found), AppColors.SUCCESS),
                    _stat_card(
                        "Not Found",
                        str(not_found),
                        ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE),
                    ),
                    _stat_card("Errors", str(errors), AppColors.WARNING),
                    _stat_card("Total", str(total), ft.Colors.PRIMARY),
                ],
                spacing=tokens.SPACE_SM,
                alignment=ft.MainAxisAlignment.SPACE_EVENLY,
            ),
            padding=tokens.SPACE_LG,
            border_radius=tokens.RADIUS_MD,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border=ft.Border.all(
                width=1, color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)
            ),
            margin=ft.Margin(
                tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_SM
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

        query = filter_query.strip().lower()

        # Update Found tab
        found_list.current.controls.clear()
        found_items = [
            r for r in progress.found if not query or query in r.site_name.lower()
        ]
        for r in found_items:
            found_list.current.controls.append(_build_result_tile(r))
        if not found_items:
            found_list.current.controls.append(
                ft.Container(
                    content=ft.Text(
                        "No matches" if query else "No accounts found",
                        color=ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE),
                        text_align=ft.TextAlign.CENTER,
                    ),
                    padding=tokens.SPACE_XXL,
                    alignment=ft.Alignment.CENTER,
                )
            )

        # Update Not Found tab
        notfound_list.current.controls.clear()
        notfound_items = [
            r for r in progress.not_found if not query or query in r.site_name.lower()
        ]
        for r in notfound_items:
            notfound_list.current.controls.append(_build_result_tile(r))
        if not notfound_items:
            notfound_list.current.controls.append(
                ft.Container(
                    content=ft.Text(
                        "No matches" if query else "All sites returned results",
                        color=ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE),
                        text_align=ft.TextAlign.CENTER,
                    ),
                    padding=tokens.SPACE_XXL,
                    alignment=ft.Alignment.CENTER,
                )
            )

        # Update Errors tab
        error_list.current.controls.clear()
        error_items = [
            r for r in progress.errors if not query or query in r.site_name.lower()
        ]
        for r in error_items:
            error_list.current.controls.append(_build_result_tile(r))
        if not error_items:
            error_list.current.controls.append(
                ft.Container(
                    content=ft.Text(
                        "No matches" if query else "No errors",
                        color=ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE),
                        text_align=ft.TextAlign.CENTER,
                    ),
                    padding=tokens.SPACE_XXL,
                    alignment=ft.Alignment.CENTER,
                )
            )

    def _on_filter_change(e):
        nonlocal filter_query
        filter_query = e.control.value
        _update_lists()
        page.update()

    def _cancel_search():
        if on_cancel:
            on_cancel()

    async def _copy_all_urls(e):
        if not progress or not progress.found:
            page.snack_bar = ft.SnackBar(
                ft.Text("No profiles found."), bgcolor=ft.Colors.RED
            )
            page.snack_bar.open = True
            page.update()
            return

        urls = [r.url_user for r in progress.found if r.url_user]
        text = "\n".join(urls)
        try:
            cb = ft.Clipboard()
            await cb.set(text)
            page.snack_bar = ft.SnackBar(
                ft.Text(
                    f"Copied {len(urls)} profile URLs to clipboard",
                    color=ft.Colors.WHITE,
                ),
                bgcolor=ft.Colors.GREEN,
            )
        except Exception:
            page.snack_bar = ft.SnackBar(
                ft.Text("Failed to copy URLs", color=ft.Colors.WHITE),
                bgcolor=ft.Colors.RED,
            )
        page.snack_bar.open = True
        page.update()

    async def _generate_export_bytes(fmt: str, progress_obj: SearchProgress) -> bytes:
        username = progress_obj.username
        loop = asyncio.get_event_loop()

        def _generate():
            if fmt == "txt":
                lines = [f"{r.url_user}\n" for r in progress_obj.found]
                lines.append(f"Total Detected : {len(progress_obj.found)}\n")
                return "".join(lines).encode("utf-8")

            elif fmt == "csv":
                import csv, io
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(["Username", "Site", "Home URL", "Profile URL", "Exists", "Time (s)"])
                for r in progress_obj.found + progress_obj.not_found + progress_obj.errors:
                    writer.writerow([
                        username, r.site_name, r.url_main, r.url_user,
                        r.status, f"{r.query_time:.2f}" if r.query_time else "",
                    ])
                return buf.getvalue().encode("utf-8")

            elif fmt == "xlsx":
                import pandas as pd, io
                rows = []
                for r in progress_obj.found + progress_obj.not_found + progress_obj.errors:
                    rows.append({
                        "Username": username, "Site": r.site_name,
                        "Home URL": r.url_main, "Profile URL": r.url_user,
                        "Exists": r.status, "Response Time (s)": r.query_time,
                    })
                df = pd.DataFrame(rows)
                buf = io.BytesIO()
                df.to_excel(buf, index=False, sheet_name="Sherlock Report")
                return buf.getvalue()

        return await loop.run_in_executor(None, _generate)

    async def _export_results(format_type: str):
        if not progress:
            return

        username = progress.username
        ext = format_type.lower()
        filename = f"sherlock_{username}.{ext}"

        try:
            data = await _generate_export_bytes(ext, progress)
        except Exception as e:
            logger.error("Export generation failed: %s", e)
            page.snack_bar = ft.SnackBar(
                content=ft.Text(f"Failed to generate export: {str(e)}", color=ft.Colors.WHITE),
                bgcolor=ft.Colors.ERROR,
            )
            page.snack_bar.open = True
            page.update()
            return

        picker = ft.FilePicker()
        ext_map = {"txt": ["txt"], "csv": ["csv"], "xlsx": ["xlsx"]}
        result = await picker.save_file(
            file_name=filename,
            allowed_extensions=ext_map.get(ext, [ext]),
            src_bytes=data,
        )

        if not result:
            return

        page.snack_bar = ft.SnackBar(
            content=ft.Text(f"Exported successfully!", color=ft.Colors.WHITE),
            bgcolor=ft.Colors.GREEN_600,
        )
        page.snack_bar.open = True
        page.update()

    def _close_sheet(e=None):
        page.bottom_sheet.open = False
        page.update()

    def _show_export_menu(e):
        bs = ft.BottomSheet(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Export Report",
                            size=tokens.FONT_LG,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            "Select your preferred format to export the scan results. Reports are stored in your system Downloads folder.",
                            size=tokens.FONT_XS,
                            color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                        ),
                        ft.Container(height=tokens.SPACE_XS),
                        ft.ListTile(
                            leading=ft.Icon(
                                ft.Icons.TEXT_SNIPPET_ROUNDED,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            title=ft.Text(
                                "Text List (.txt)",
                                size=tokens.FONT_MD,
                                weight=ft.FontWeight.W_500,
                            ),
                            subtitle=ft.Text(
                                "Simple list containing only claimed URLs",
                                size=tokens.FONT_XS,
                            ),
                            on_click=lambda e: (
                                page.run_task(_export_results, "txt"),
                                _close_sheet(),
                            ),
                        ),
                        ft.ListTile(
                            leading=ft.Icon(
                                ft.Icons.GRID_ON_ROUNDED, color=ft.Colors.GREEN_600
                            ),
                            title=ft.Text(
                                "CSV Spreadsheet (.csv)",
                                size=tokens.FONT_MD,
                                weight=ft.FontWeight.W_500,
                            ),
                            subtitle=ft.Text(
                                "Comma-separated spreadsheet containing all entries",
                                size=tokens.FONT_XS,
                            ),
                            on_click=lambda e: (
                                page.run_task(_export_results, "csv"),
                                _close_sheet(),
                            ),
                        ),
                        ft.ListTile(
                            leading=ft.Icon(
                                ft.Icons.TABLE_CHART_ROUNDED, color=ft.Colors.BLUE_600
                            ),
                            title=ft.Text(
                                "Excel Spreadsheet (.xlsx)",
                                size=tokens.FONT_MD,
                                weight=ft.FontWeight.W_500,
                            ),
                            subtitle=ft.Text(
                                "Professional Excel sheet with formatting",
                                size=tokens.FONT_XS,
                            ),
                            on_click=lambda e: (
                                page.run_task(_export_results, "xlsx"),
                                _close_sheet(),
                            ),
                        ),
                        ft.Container(height=tokens.SPACE_SM),
                    ],
                    spacing=tokens.SPACE_XS,
                    tight=True,
                ),
                padding=tokens.SPACE_LG,
                border_radius=ft.BorderRadius.only(
                    top_left=tokens.RADIUS_MD, top_right=tokens.RADIUS_MD
                ),
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            ),
            open=True,
        )
        page.bottom_sheet = bs
        page.update()

    username = progress.username if progress else state.last_results_username

    appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK_ROUNDED,
            on_click=lambda e: on_navigate("/home"),
        ),
        title=ft.Row(
            [
                ft.Image(src="icon.png", width=24, height=24, border_radius=4),
                ft.Text(username, size=tokens.FONT_LG, weight=ft.FontWeight.W_600),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        center_title=False,
        bgcolor=ft.Colors.TRANSPARENT,
        actions=[
            ft.IconButton(
                icon=ft.Icons.CONTENT_COPY_ROUNDED,
                tooltip="Copy all profile URLs to clipboard",
                on_click=_copy_all_urls,
                disabled=not (progress and len(progress.found) > 0),
            ),
            ft.IconButton(
                icon=ft.Icons.DOWNLOAD_ROUNDED,
                tooltip="Export report",
                on_click=_show_export_menu,
                disabled=progress.is_running if progress else False,
            ),
            ft.IconButton(
                icon=ft.Icons.REFRESH_ROUNDED,
                tooltip="Search again",
                on_click=lambda e: on_restart(username),
                disabled=progress.is_running if progress else False,
            ),
        ],
    )

    filter_box = ft.Container(
        content=ft.TextField(
            ref=search_field,
            hint_text="Filter matches by name or domain...",
            prefix_icon=ft.Icons.FILTER_LIST_ROUNDED,
            border_radius=tokens.RADIUS_SM,
            border_width=1,
            border_color=ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE),
            focused_border_color=ft.Colors.PRIMARY,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            filled=True,
            on_change=_on_filter_change,
            text_size=tokens.FONT_SM,
            content_padding=8,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_XS,
            bottom=tokens.SPACE_SM,
        ),
    )

    found_count = len(progress.found) if progress else 0
    notfound_count = len(progress.not_found) if progress else 0
    error_count = len(progress.errors) if progress else 0

    tabs = ft.Tabs(
        ref=tab_container,
        selected_index=0,
        length=3,
        content=ft.Column(
            [
                ft.TabBar(
                    tabs=[
                        ft.Tab(label=f"Found ({found_count})"),
                        ft.Tab(label=f"Not Found ({notfound_count})"),
                        ft.Tab(label=f"Errors ({error_count})"),
                    ],
                    scrollable=False,
                    indicator_color=ft.Colors.PRIMARY,
                    label_color=ft.Colors.PRIMARY,
                    unselected_label_color=ft.Colors.with_opacity(
                        0.5, ft.Colors.ON_SURFACE
                    ),
                ),
                ft.TabBarView(
                    controls=[
                        # Panel 1
                        ft.Container(
                            content=ft.Column(
                                ref=found_list,
                                spacing=0,
                                scroll=ft.ScrollMode.AUTO,
                                expand=True,
                            ),
                            expand=True,
                        ),
                        # Panel 2
                        ft.Container(
                            content=ft.Column(
                                ref=notfound_list,
                                spacing=0,
                                scroll=ft.ScrollMode.AUTO,
                                expand=True,
                            ),
                            expand=True,
                        ),
                        # Panel 3
                        ft.Container(
                            content=ft.Column(
                                ref=error_list,
                                spacing=0,
                                scroll=ft.ScrollMode.AUTO,
                                expand=True,
                            ),
                            expand=True,
                        ),
                    ],
                    expand=True,
                ),
            ],
            expand=True,
            spacing=0,
        ),
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
                                    color=ft.Colors.with_opacity(
                                        0.5, ft.Colors.ON_SURFACE
                                    ),
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
                    left=tokens.SPACE_LG,
                    right=tokens.SPACE_LG,
                    top=tokens.SPACE_SM,
                    bottom=0,
                ),
            )
        )

    controls.extend(
        [
            _build_stats(),
            filter_box,
            tabs,
        ]
    )

    controls.append(build_banner_ad(page))

    view = ft.View(
        route="/results",
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

    return view
