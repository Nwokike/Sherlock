"""Settings view — advanced search parameters and database updates."""

from __future__ import annotations

import logging
import flet as ft

from core import tokens
from core.constants import (
    APP_NAME,
    APP_VERSION,
    STORAGE_THEME,
    STORAGE_NSFW,
    STORAGE_EXCLUSIONS,
    STORAGE_TIMEOUT,
    STORAGE_LOCAL_DB,
)
from core.state import state
from core.theme import AppColors
from core.styles import section_header, build_banner_ad

logger = logging.getLogger(__name__)


def build_settings_view(
    page: ft.Page,
    sherlock_service,
    storage,
) -> ft.View:
    sync_btn_ref = ft.Ref[ft.Button]()
    db_status_ref = ft.Ref[ft.Text]()

    # Theme change helper
    async def _on_theme_change(e):
        val = e.control.value.lower()
        if val == "system":
            new_mode = ft.ThemeMode.SYSTEM
        elif val == "light":
            new_mode = ft.ThemeMode.LIGHT
        else:
            new_mode = ft.ThemeMode.DARK
        page.theme_mode = new_mode
        state.theme_mode = new_mode

        if storage:
            await storage.set(STORAGE_THEME, val)
        page.update()

    # Toggle NSFW helper
    async def _toggle_nsfw(e):
        state.nsfw_enabled = e.control.value
        if storage:
            await storage.set(STORAGE_NSFW, "true" if e.control.value else "false")
        # Reload sites dynamically
        page.run_task(sherlock_service.load_sites)

    # Toggle Exclusions helper
    async def _toggle_exclusions(e):
        state.ignore_exclusions = e.control.value
        if storage:
            await storage.set(
                STORAGE_EXCLUSIONS, "true" if e.control.value else "false"
            )
        # Reload sites dynamically
        page.run_task(sherlock_service.load_sites)

    # Toggle Offline DB helper
    async def _toggle_local_db(e):
        state.use_local_db = e.control.value
        if storage:
            await storage.set(STORAGE_LOCAL_DB, "true" if e.control.value else "false")
        # Reload sites dynamically
        page.run_task(sherlock_service.load_sites)

    # Timeout change helper
    async def _on_timeout_change(e):
        val = int(e.control.value)
        state.timeout = val
        if storage:
            await storage.set(STORAGE_TIMEOUT, str(val))

    # Sync database from GitHub
    async def _sync_db(e):
        if state.db_sync_status == "Syncing...":
            return

        state.db_sync_status = "Syncing..."
        if sync_btn_ref.current:
            sync_btn_ref.current.disabled = True
            sync_btn_ref.current.content = ft.Row(
                [
                    ft.ProgressRing(
                        width=16, height=16, stroke_width=2, color=ft.Colors.WHITE
                    ),
                    ft.Text("Syncing...", size=tokens.FONT_SM),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            )
        page.update()

        success = await sherlock_service.sync_database()

        if success:
            state.db_sync_status = "Synced!"
            if db_status_ref.current:
                db_status_ref.current.value = (
                    f"Database active ({sherlock_service._total_sites} sites loaded)"
                )

            page.snack_bar = ft.SnackBar(
                content=ft.Text(
                    "Database synced successfully with GitHub!", color=ft.Colors.WHITE
                ),
                bgcolor=ft.Colors.GREEN_600,
            )
        else:
            state.db_sync_status = "Failed"
            page.snack_bar = ft.SnackBar(
                content=ft.Text(
                    "Database sync failed. Check connection.", color=ft.Colors.WHITE
                ),
                bgcolor=AppColors.ERROR,
            )

        page.snack_bar.open = True

        # Reset button status
        state.db_sync_status = "Idle"
        if sync_btn_ref.current:
            sync_btn_ref.current.disabled = False
            sync_btn_ref.current.content = ft.Text(
                "Check for Updates", size=tokens.FONT_SM, weight=ft.FontWeight.W_600
            )

        page.update()

    async def _go_back():
        page.views.pop()
        await page.push_route(page.views[-1].route if page.views else "/home")

    async def _launch_sherlock_project(e):
        await ft.UrlLauncher().launch_url("https://github.com/sherlock-project/sherlock")

    appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK_ROUNDED,
            on_click=lambda e: page.run_task(_go_back),
        ),
        title=ft.Text("Settings", size=tokens.FONT_LG, weight=ft.FontWeight.W_600),
        center_title=False,
        bgcolor=ft.Colors.TRANSPARENT,
    )

    # 1. SCANNING PREFERENCES CARD
    scanning_card = ft.Container(
        content=ft.Column(
            controls=[
                # NSFW switch
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.BLOCK_ROUNDED,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            size=tokens.ICON_MD,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "Include NSFW Sites",
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                ),
                                ft.Text(
                                    "Include adult/NSFW networks in scans",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.with_opacity(
                                        0.5, ft.Colors.ON_SURFACE
                                    ),
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Switch(
                            value=state.nsfw_enabled,
                            on_change=lambda e: page.run_task(_toggle_nsfw, e),
                            active_color=ft.Colors.PRIMARY,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(
                    height=1, color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)
                ),
                # Exclusions switch
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.SHIELD_ROUNDED,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            size=tokens.ICON_MD,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "Ignore False Positives Exclusions",
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                ),
                                ft.Text(
                                    "Scans exclusions list (may increase false positives)",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.with_opacity(
                                        0.5, ft.Colors.ON_SURFACE
                                    ),
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Switch(
                            value=state.ignore_exclusions,
                            on_change=lambda e: page.run_task(_toggle_exclusions, e),
                            active_color=ft.Colors.PRIMARY,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=tokens.SPACE_MD,
        ),
        padding=tokens.SPACE_LG,
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(
            width=1, color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)
        ),
    )

    # 2. PERFORMANCE & TIMEOUT CARD
    performance_card = ft.Container(
        content=ft.Column(
            controls=[
                # Offline DB switch
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.FLASH_ON_ROUNDED,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            size=tokens.ICON_MD,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "Fast Offline Scan",
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                ),
                                ft.Text(
                                    "Load local network list instantly without internet",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.with_opacity(
                                        0.5, ft.Colors.ON_SURFACE
                                    ),
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Switch(
                            value=state.use_local_db,
                            on_change=lambda e: page.run_task(_toggle_local_db, e),
                            active_color=ft.Colors.PRIMARY,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(
                    height=1, color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)
                ),
                # Timeout Selector
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.TIMER_OUTLINED,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            size=tokens.ICON_MD,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "Request Timeout",
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                ),
                                ft.Text(
                                    "Maximum connection wait time per site",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.with_opacity(
                                        0.5, ft.Colors.ON_SURFACE
                                    ),
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Dropdown(
                            value=str(state.timeout),
                            options=[
                                ft.DropdownOption("5", "5s"),
                                ft.DropdownOption("10", "10s"),
                                ft.DropdownOption("15", "15s"),
                                ft.DropdownOption("30", "30s"),
                                ft.DropdownOption("60", "60s"),
                            ],
                            width=90,
                            height=48,
                            text_size=tokens.FONT_MD,
                            border_radius=tokens.RADIUS_SM,
                            focused_border_color=ft.Colors.PRIMARY,
                            on_select=lambda e: page.run_task(_on_timeout_change, e),
                            content_padding=5,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=tokens.SPACE_MD,
        ),
        padding=tokens.SPACE_LG,
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(
            width=1, color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)
        ),
    )

    # 3. DATABASE UPDATE CARD
    sync_card = ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.CLOUD_SYNC_ROUNDED,
                            color=ft.Colors.PRIMARY,
                            size=tokens.ICON_LG,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "Network Database Sync",
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.PRIMARY,
                                ),
                                ft.Text(
                                    ref=db_status_ref,
                                    value=f"Database active ({sherlock_service._total_sites} sites loaded)",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.with_opacity(
                                        0.6, ft.Colors.ON_SURFACE
                                    ),
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                ),
                ft.Container(height=tokens.SPACE_XXS),
                ft.Text(
                    "Sync with the latest official Sherlock repository list on GitHub to find usernames across brand new networks.",
                    size=tokens.FONT_XS,
                    color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                ),
                ft.Container(height=tokens.SPACE_XXS),
                ft.Button(
                    ref=sync_btn_ref,
                    content=ft.Text(
                        "Check for Updates",
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_600,
                    ),
                    on_click=lambda e: page.run_task(_sync_db, e),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_SM),
                        bgcolor=ft.Colors.PRIMARY,
                        color=ft.Colors.WHITE,
                        elevation=0,
                        padding=ft.Padding(16, 12, 16, 12),
                    ),
                    width=320,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        padding=tokens.SPACE_LG,
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(
            width=1, color=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)
        ),
    )

    # 4. PREFERENCES (THEME) CARD
    theme_card = ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.COLOR_LENS_ROUNDED,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            size=tokens.ICON_MD,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "App Theme Mode",
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                ),
                                ft.Text(
                                    "Choose between System, Light, or Dark",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.with_opacity(
                                        0.5, ft.Colors.ON_SURFACE
                                    ),
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Dropdown(
                            value=page.theme_mode.value.capitalize()
                            if isinstance(page.theme_mode, ft.ThemeMode)
                            else "System",
                            options=[
                                ft.DropdownOption("System", "System"),
                                ft.DropdownOption("Light", "Light"),
                                ft.DropdownOption("Dark", "Dark"),
                            ],
                            width=110,
                            height=48,
                            text_size=tokens.FONT_MD,
                            border_radius=tokens.RADIUS_SM,
                            focused_border_color=ft.Colors.PRIMARY,
                            on_select=lambda e: page.run_task(_on_theme_change, e),
                            content_padding=5,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
        ),
        padding=tokens.SPACE_LG,
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(
            width=1, color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)
        ),
    )

    content = ft.ListView(
        controls=[
            ft.Container(height=tokens.SPACE_SM),
            section_header("PREFERENCES"),
            theme_card,
            build_banner_ad(page),
            ft.Container(height=tokens.SPACE_SM),
            section_header("SCAN PARAMETERS"),
            scanning_card,
            build_banner_ad(page),
            ft.Container(height=tokens.SPACE_SM),
            section_header("CONNECTION & SPEED"),
            performance_card,
            build_banner_ad(page),
            ft.Container(height=tokens.SPACE_SM),
            section_header("DATABASE UPDATE"),
            sync_card,
            build_banner_ad(page),
            ft.Container(height=tokens.SPACE_SM),
            section_header("ABOUT"),
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            f"{APP_NAME} v{APP_VERSION}",
                            size=tokens.FONT_MD,
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.ON_SURFACE,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Container(height=2),
                        ft.Text(
                            "A user-friendly UI for the open-source Sherlock Project.",
                            size=tokens.FONT_XS,
                            color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            "Making it accessible to everyone — no terminal needed.",
                            size=tokens.FONT_XS,
                            color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Container(height=6),
                        ft.TextButton(
                            "github.com/sherlock-project/sherlock",
                            style=ft.ButtonStyle(
                                color=ft.Colors.PRIMARY,
                                text_style=ft.TextStyle(size=tokens.FONT_XS),
                            ),
                            on_click=_launch_sherlock_project,
                        ),
                    ],
                    spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(
                    left=tokens.SPACE_LG,
                    right=tokens.SPACE_LG,
                    top=tokens.SPACE_LG,
                    bottom=tokens.SPACE_LG,
                ),
            ),
        ],
        spacing=0,
        expand=True,
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
    )

    view = ft.View(
        route="/settings",
        controls=[
            ft.SafeArea(
                ft.Container(
                    content=content,
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
