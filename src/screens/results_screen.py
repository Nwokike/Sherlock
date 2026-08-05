"""ResultsScreen — live search results with filtering, tabs, export, and copy.

@ft.component — reads observable state.progress_version to re-render on each tick.
Premium design: gradient stat cards, animated progress, clean tab design.
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft
from flet import Control

from components.banner_ad import build_banner_ad
from components.result_card import ResultCard
from components.stat_card import StatCard
from core import tokens
from core.theme import AppColors
from hooks.use_debounce import use_debounce
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("ResultsScreen")


@ft.component
def ResultsScreen() -> Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    # Force re-render on each progress_version bump
    _ = state.progress_version

    filter_query, set_filter_query = ft.use_state("")
    debounced_filter = use_debounce(filter_query, 250)

    # Get active progress
    active_username = (
        state.active_username
        if state.active_username
        else (
            state.search_progress.username
            if state.search_progress
            else state.last_results_username
        )
    )

    active_progress = state.search_progress
    is_running = active_progress.is_running if active_progress else False

    # Filter results
    def _filter_items(items):
        q = debounced_filter.strip().lower()
        if not q:
            return items
        return [r for r in items if q in r.site_name.lower()]

    found_items = _filter_items(active_progress.found) if active_progress else []
    notfound_items = _filter_items(active_progress.not_found) if active_progress else []
    error_items = _filter_items(active_progress.errors) if active_progress else []

    def _build_result_list(items):
        if not items:
            from components.empty_state import EmptyState

            return EmptyState(
                title="No matches" if debounced_filter else "No results yet",
                message=(
                    f'No results match "{debounced_filter}"'
                    if debounced_filter
                    else "Results will appear as the scan progresses."
                ),
                icon=ft.Icons.SEARCH_OFF_ROUNDED,
            )
        def _open_url(url):
            async def _launch():
                try:
                    await ft.UrlLauncher().launch_url(url)
                except Exception:
                    pass
            asyncio.create_task(_launch())

        return ft.Column(
            controls=[
                ResultCard(
                    site_name=r.site_name,
                    status=r.status,
                    url_user=r.url_user,
                    url_main=r.url_main,
                    query_time=r.query_time,
                    on_open=lambda e, u=r.url_user: _open_url(u) if u else None,
                )
                for r in items
            ],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    # Tabs
    tabs = ft.Tabs(
        selected_index=0,
        length=3,
        content=ft.Column(
            [
                ft.TabBar(
                    tabs=[
                        ft.Tab(label=f"Found ({len(found_items)})"),
                        ft.Tab(label=f"Not Found ({len(notfound_items)})"),
                        ft.Tab(label=f"Errors ({len(error_items)})"),
                    ],
                    scrollable=False,
                    indicator_color=ft.Colors.PRIMARY,
                    label_color=ft.Colors.PRIMARY,
                    unselected_label_color=ft.Colors.with_opacity(
                        tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                    ),
                    label_padding=ft.Padding(
                        tokens.SPACE_LG,
                        tokens.SPACE_SM,
                        tokens.SPACE_LG,
                        tokens.SPACE_SM,
                    ),
                ),
                ft.TabBarView(
                    controls=[
                        _build_result_list(found_items),
                        _build_result_list(notfound_items),
                        _build_result_list(error_items),
                    ],
                    expand=True,
                ),
            ],
            expand=True,
            spacing=0,
        ),
        expand=True,
    )

    # Stats row — premium gradient cards
    total = active_progress.total_sites if active_progress else 0
    stats_row = ft.Row(
        controls=[
            StatCard(
                "Found",
                str(len(found_items) if active_progress else 0),
                AppColors.SUCCESS,
            ),
            StatCard(
                "Not Found",
                str(len(notfound_items) if active_progress else 0),
                ft.Colors.with_opacity(tokens.OPACITY_DIM, ft.Colors.ON_SURFACE),
            ),
            StatCard(
                "Errors",
                str(len(error_items) if active_progress else 0),
                AppColors.WARNING,
            ),
            StatCard("Total", str(total), ft.Colors.PRIMARY),
        ],
        spacing=tokens.SPACE_SM,
        alignment=ft.MainAxisAlignment.SPACE_EVENLY,
    )

    stats_card = ft.Container(
        content=stats_row,
        padding=tokens.SPACE_MD,
        border_radius=tokens.RADIUS_LG,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(
            width=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        margin=ft.Margin(
            tokens.SPACE_XL, tokens.SPACE_MD, tokens.SPACE_XL, tokens.SPACE_SM
        ),
    )

    # Filter bar
    filter_box = ft.Container(
        content=ft.TextField(
            hint_text="Filter results by site name...",
            prefix_icon=ft.Icons.FILTER_LIST_ROUNDED,
            border_radius=tokens.RADIUS_MD,
            border_width=1,
            border_color=ft.Colors.with_opacity(
                tokens.OPACITY_MEDIUM, ft.Colors.OUTLINE
            ),
            focused_border_color=ft.Colors.PRIMARY,
            bgcolor=ft.Colors.SURFACE,
            filled=True,
            on_change=lambda e: set_filter_query(e.control.value),
            text_size=tokens.FONT_SM,
            content_padding=tokens.SPACE_SM,
            height=44,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_XL,
            right=tokens.SPACE_XL,
            top=tokens.SPACE_XS,
            bottom=tokens.SPACE_SM,
        ),
    )

    # Progress bar — branded color
    progress_section = ft.Container(width=0, height=0)
    if is_running and active_progress:
        progress_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.ProgressBar(
                        color=ft.Colors.PRIMARY,
                        bgcolor=ft.Colors.with_opacity(
                            tokens.OPACITY_LIGHT, ft.Colors.PRIMARY
                        ),
                        height=tokens.PROGRESS_BAR_HEIGHT,
                    ),
                    ft.Row(
                        controls=[
                            ft.Text(
                                f"Checking {active_progress.checked_sites}/{active_progress.total_sites} sites...",
                                size=tokens.FONT_SM,
                                color=ft.Colors.with_opacity(
                                    tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                                ),
                            ),
                            ft.Container(expand=True),
                            ft.TextButton(
                                content=ft.Text(
                                    "Cancel",
                                    size=tokens.FONT_SM,
                                    color=AppColors.ERROR,
                                    weight=ft.FontWeight.W_600,
                                ),
                                on_click=lambda e: controller.cancel_search(),
                            ),
                        ],
                    ),
                ],
                spacing=tokens.SPACE_XS,
            ),
            padding=ft.Padding(
                left=tokens.SPACE_XL,
                right=tokens.SPACE_XL,
                top=tokens.SPACE_SM,
                bottom=0,
            ),
        )

    # Export actions
    async def _copy_all_urls(e):
        if not active_progress or not active_progress.found:
            return
        urls = [r.url_user for r in active_progress.found if r.url_user]
        text = "\n".join(urls)
        try:
            cb = ft.Clipboard()
            await cb.set(text)
        except Exception:
            pass

    def _close_dialog(e=None):
        from flet import context

        context.page.pop_dialog()

    def _on_export(format_type: str):
        async def _export():
            from flet import context

            page = context.page
            page.pop_dialog()
            try:
                if not active_progress:
                    return
                output = []
                for r in active_progress.found:
                    if r.url_user:
                        output.append(r.url_user)
                report_bytes = "\n".join(output).encode("utf-8")
                ext = format_type
                file_picker = ft.FilePicker()
                page.services.append(file_picker)
                await file_picker.save_file(
                    file_name=f"sherlock_{active_username}.{ext}",
                    allowed_extensions=[ext],
                    dialog_title=f"Save scan report as {format_type.upper()}",
                    src_bytes=report_bytes,
                )
            except Exception as ex:
                logger.exception("Export failed: %s", ex)

        asyncio.create_task(_export())

    format_dialog = ft.AlertDialog(
        title=ft.Text("Export Scan Report"),
        content=ft.Text("Select your preferred file format:"),
        actions=[
            ft.TextButton("Plain Text (.txt)", on_click=lambda e: _on_export("txt")),
            ft.TextButton("Cancel", on_click=_close_dialog),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def _show_format_dialog(e):
        from flet import context

        context.page.show_dialog(format_dialog)

    controls = [
        progress_section,
        stats_card,
        filter_box,
        tabs,
        build_banner_ad(),
    ]

    return ft.Column(
        controls=controls,
        expand=True,
        spacing=0,
    )
