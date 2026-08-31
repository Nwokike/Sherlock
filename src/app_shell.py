"""AppShell — top-level shell branching onboarding, results, sites vs dashboard.

Mirrors KTV's AppShell pattern: use_state for active_view + injected controller
closures + chrome sync via use_effect. Manages both appbar AND navigation_bar.
"""

import asyncio

import logging

import flet as ft
from flet import Control

from core.theme import AppColors
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("AppShell")

_TAB_NAMES = ("Home", "History", "Settings")
_TAB_ICONS = (
    ft.Icons.HOME_ROUNDED,
    ft.Icons.HISTORY_ROUNDED,
    ft.Icons.SETTINGS_ROUNDED,
)


def _should_show_onboarding(state) -> bool:
    """Mirror of the branch in AppShell — exported for tests."""
    return state.is_first_launch or not state.has_accepted_terms


def _dashboard_scaffold(body: Control) -> Control:
    """Build the dashboard body container."""
    return ft.Container(content=body, expand=True)


def _build_appbar(active_view: str, active_tab: int, controller) -> ft.AppBar:
    """Build the appropriate appbar for the current view/tab."""
    from core import tokens

    if active_view == "results":

        def _copy_urls(e):
            try:
                asyncio.create_task(ft.HapticFeedback().medium_impact())
            except Exception:
                pass

            async def _copy():
                from flet import context

                page = context.page
                from core.notify import show_snack
                from core.state import state as app_state

                if not (app_state.search_progress and app_state.search_progress.found):
                    return
                urls = [
                    r.url_user for r in app_state.search_progress.found if r.url_user
                ]
                try:
                    cb = ft.Clipboard()
                    await cb.set("\n".join(urls))
                    show_snack(
                        page,
                        f"{len(urls)} URL{'s' if len(urls) != 1 else ''} copied",
                        bgcolor=AppColors.SUCCESS,
                    )
                except Exception as ex:
                    logger.warning("Copy failed: %s", ex)
                    show_snack(
                        page, "Couldn't copy — try again.", bgcolor=AppColors.ERROR
                    )

            asyncio.create_task(_copy())

        def _share_urls(e):
            try:
                asyncio.create_task(ft.HapticFeedback().light_impact())
            except Exception:
                pass

            async def _share():
                from core.state import state as app_state

                if not (app_state.search_progress and app_state.search_progress.found):
                    return
                urls = [
                    r.url_user for r in app_state.search_progress.found if r.url_user
                ]
                if not urls:
                    return
                try:
                    await ft.Share().share("\n".join(urls[:20]))
                except Exception as ex:
                    logger.warning("Share failed: %s", ex)

            asyncio.create_task(_share())

        def _on_export_click(format_type: str):
            """Full export dialog — Excel, CSV, or Text (original Sherlock behavior)."""

            async def _do_export():
                from flet import context

                page = context.page
                from core.state import state as app_state
                from core.theme import AppColors

                page.pop_dialog()
                progress = app_state.search_progress
                if not progress:
                    return
                is_email = getattr(progress, "email", None) is not None
                if is_email:
                    # Email export not supported via username Excel/CSV path — use email results view export
                    from core.notify import show_snack

                    show_snack(
                        page,
                        "Email exports use the Results copy/share actions.",
                        bgcolor=AppColors.ERROR,
                    )
                    return
                username = app_state.last_results_username or "unknown"

                try:
                    if format_type == "xlsx":
                        import io
                        import pandas as pd

                        output = io.BytesIO()
                        all_results = (
                            progress.found + progress.not_found + progress.errors
                        )
                        df_data = {
                            "username": [progress.username] * len(all_results),
                            "name": [r.site_name for r in all_results],
                            "url_main": [r.url_main for r in all_results],
                            "url_user": [r.url_user or r.url_main for r in all_results],
                            "exists": [r.status for r in all_results],
                            "http_status": [r.http_status for r in all_results],
                            "response_time_s": [
                                f"{r.query_time:.2f}" if r.query_time else ""
                                for r in all_results
                            ],
                        }
                        df = pd.DataFrame(df_data)
                        with pd.ExcelWriter(output, engine="openpyxl") as writer:
                            df.to_excel(writer, index=False, sheet_name="sheet1")
                        report_bytes = output.getvalue()

                    elif format_type == "csv":
                        import csv
                        import io

                        output = io.StringIO()
                        writer = csv.writer(output)
                        writer.writerow(
                            [
                                "Username",
                                "Site Name",
                                "Profile URL",
                                "Status",
                                "Query Time (s)",
                            ]
                        )
                        for r in progress.found:
                            writer.writerow(
                                [
                                    progress.username,
                                    r.site_name,
                                    r.url_user,
                                    r.status,
                                    f"{r.query_time:.2f}" if r.query_time else "",
                                ]
                            )
                        for r in progress.not_found:
                            writer.writerow(
                                [
                                    progress.username,
                                    r.site_name,
                                    r.url_user or r.url_main,
                                    r.status,
                                    f"{r.query_time:.2f}" if r.query_time else "",
                                ]
                            )
                        for r in progress.errors:
                            writer.writerow(
                                [
                                    progress.username,
                                    r.site_name,
                                    r.url_user or r.url_main,
                                    r.status,
                                    f"{r.query_time:.2f}" if r.query_time else "",
                                ]
                            )
                        report_bytes = output.getvalue().encode("utf-8")
                    else:
                        output = []
                        for r in progress.found:
                            if r.url_user:
                                output.append(f"{r.url_user}\n")
                        output.append(f"Total Detected : {len(progress.found)}\n")
                        report_bytes = "".join(output).encode("utf-8")

                    ext = format_type.lower()
                    file_picker = ft.FilePicker()
                    page.services.append(file_picker)
                    path = await file_picker.save_file(
                        file_name=f"sherlock_{username}.{ext}",
                        allowed_extensions=[ext],
                        dialog_title=f"Save scan report as {format_type.upper()}",
                        src_bytes=report_bytes,
                    )
                    if not path:
                        return

                    is_mobile = (
                        page.platform.is_mobile()
                        if hasattr(page.platform, "is_mobile")
                        else False
                    )
                    if not is_mobile:

                        def _write_file():
                            with open(path, "wb") as f:
                                f.write(report_bytes)

                        await asyncio.to_thread(_write_file)

                    from core.notify import show_snack

                    show_snack(page, "Saved successfully!", bgcolor=AppColors.SUCCESS)
                except Exception as ex:
                    logger.exception("Export failed: %s", ex)
                    from core.notify import show_snack

                    show_snack(
                        page,
                        f"Failed to save: {ex!s}",
                        bgcolor=AppColors.ERROR,
                        duration=10000,
                    )

            asyncio.create_task(_do_export())

        def _show_export_dialog(e):
            from flet import context

            page = context.page
            from core.state import state as app_state

            if not app_state.search_progress:
                return
            sheet = ft.BottomSheet(
                content=ft.Column(
                    [
                        ft.ListTile(
                            title=ft.Text(
                                "Excel Spreadsheet (.xlsx)", weight=ft.FontWeight.W_600
                            ),
                            subtitle=ft.Text("Full report with all columns"),
                            leading=ft.Icon(
                                ft.Icons.TABLE_CHART_ROUNDED, color=AppColors.PRIMARY
                            ),
                            on_click=lambda e: (
                                page.pop_dialog(),
                                _on_export_click("xlsx"),
                            ),
                        ),
                        ft.ListTile(
                            title=ft.Text(
                                "CSV Spreadsheet (.csv)", weight=ft.FontWeight.W_600
                            ),
                            subtitle=ft.Text("Spreadsheet compatible"),
                            leading=ft.Icon(
                                ft.Icons.GRID_ON_ROUNDED, color=AppColors.PRIMARY
                            ),
                            on_click=lambda e: (
                                page.pop_dialog(),
                                _on_export_click("csv"),
                            ),
                        ),
                        ft.ListTile(
                            title=ft.Text(
                                "Plain Text List (.txt)", weight=ft.FontWeight.W_600
                            ),
                            subtitle=ft.Text("URLs only"),
                            leading=ft.Icon(
                                ft.Icons.ARTICLE_ROUNDED, color=AppColors.PRIMARY
                            ),
                            on_click=lambda e: (
                                page.pop_dialog(),
                                _on_export_click("txt"),
                            ),
                        ),
                    ],
                    tight=True,
                ),
                show_drag_handle=True,
            )
            page.show_dialog(sheet)

        def _restart(e):
            from core.state import state as app_state

            if app_state.last_results_username:
                asyncio.create_task(
                    controller.start_search(app_state.last_results_username)
                )
                controller.show_results()

        from core.constants import MODE_EMAIL
        from core.state import state as app_state

        is_email_results = (
            app_state.search_mode == MODE_EMAIL
            or getattr(app_state.search_progress, "email", None) is not None
        )
        _actions: list[ft.Control] = []
        if not is_email_results:
            _actions.extend(
                [
                    ft.IconButton(
                        icon=ft.Icons.CONTENT_COPY_ROUNDED,
                        tooltip="Copy URLs",
                        on_click=_copy_urls,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.SHARE_ROUNDED,
                        tooltip="Share URLs",
                        on_click=_share_urls,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DOWNLOAD_ROUNDED,
                        tooltip="Export",
                        on_click=_show_export_dialog,
                    ),
                ]
            )
        _actions.append(
            ft.IconButton(
                icon=ft.Icons.REFRESH_ROUNDED,
                tooltip="Search again",
                on_click=_restart,
            )
        )
        return ft.AppBar(
            leading=ft.IconButton(
                icon=ft.Icons.ARROW_BACK_ROUNDED,
                on_click=lambda e: controller.go_home(),
            ),
            title=ft.Text(
                "Search Results",
                size=tokens.FONT_LG,
                weight=ft.FontWeight.W_600,
            ),
            center_title=False,
            bgcolor=ft.Colors.TRANSPARENT,
            actions=_actions,
        )

    if active_view == "sites":
        return ft.AppBar(
            leading=ft.IconButton(
                icon=ft.Icons.ARROW_BACK_ROUNDED,
                on_click=lambda e: controller.back(),
            ),
            title=ft.Text(
                "Social Networks",
                size=tokens.FONT_LG,
                weight=ft.FontWeight.W_600,
            ),
            center_title=False,
            bgcolor=ft.Colors.TRANSPARENT,
        )

    # Dashboard — no AppBar (Header component in HomeScreen provides branding)
    return None


@ft.component
def AppShell() -> Control:
    """Top-level shell. Branches: onboarding, results, sites, or dashboard tabs."""
    active_tab, set_active_tab = ft.use_state(0)
    active_view, set_active_view = ft.use_state("dashboard")

    controller = ft.use_context(ControllerMethodsCtx)
    state = ft.use_context(AppStateCtx)

    # Inject view-local closures into the controller methods instance
    controller.show_results = lambda: set_active_view("results")
    controller.show_sites = lambda: set_active_view("sites")
    controller.go_home = lambda: set_active_view("dashboard")
    controller.back = lambda: set_active_view("dashboard")
    controller.show_settings = lambda: (
        set_active_view("dashboard"),
        set_active_tab(2),
    )
    controller.show_history = lambda: (
        set_active_view("dashboard"),
        set_active_tab(1),
    )

    from flet import context

    def _sync_chrome():
        """Sync the root view's appbar + navigation_bar to the current branch."""
        page = context.page
        if not page or not page.views:
            return

        # Sync appbar
        try:
            page.views[0].appbar = _build_appbar(active_view, active_tab, controller)
        except Exception:
            pass

        # Onboarding: no nav bar
        if _should_show_onboarding(state):
            page.views[0].navigation_bar = None
            try:
                page.update()
            except Exception:
                pass
            return

        # Results / Sites: no navigation bar (full-screen)
        if active_view in ("results", "sites"):
            page.views[0].navigation_bar = None
            try:
                page.update()
            except Exception:
                pass
            return

        # Dashboard: show the navigation bar
        current_nav = page.views[0].navigation_bar
        if isinstance(current_nav, ft.NavigationBar):
            current_nav.selected_index = active_tab
        else:
            destinations = [
                ft.NavigationBarDestination(icon=icon, label=label)
                for icon, label in zip(_TAB_ICONS, _TAB_NAMES, strict=True)
            ]

            def _on_tab_change(e):
                idx = e.control.selected_index
                logger.info("Navigated to tab '%s' (index %d)", _TAB_NAMES[idx], idx)
                set_active_tab(idx)

            page.views[0].navigation_bar = ft.NavigationBar(
                destinations=destinations,
                selected_index=active_tab,
                on_change=_on_tab_change,
            )
        try:
            page.update()
        except Exception:
            pass

    ft.use_effect(
        _sync_chrome,
        [
            active_tab,
            active_view,
            state.has_accepted_terms,
            state.theme_mode,
            state.progress_version,
        ],
    )

    # --- Branching ---
    from screens.history_screen import HistoryScreen
    from screens.home_screen import HomeScreen
    from screens.onboarding_screen import OnboardingScreen
    from screens.results_screen import ResultsScreen
    from screens.settings_screen import SettingsScreen
    from screens.sites_screen import SitesScreen

    if _should_show_onboarding(state):
        screen = OnboardingScreen()
    elif active_view == "results":
        screen = ResultsScreen()
    elif active_view == "sites":
        screen = SitesScreen()
    else:
        if active_tab == 0:
            tab_body = HomeScreen()
        elif active_tab == 1:
            tab_body = HistoryScreen()
        else:
            tab_body = SettingsScreen()
        screen = _dashboard_scaffold(body=tab_body)

    return ft.SafeArea(content=screen, expand=True)
