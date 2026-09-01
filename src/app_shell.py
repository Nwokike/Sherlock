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
                    if format_type == "pdf":
                        from services.report_service import generate_pdf_dossier

                        pdf_bytes = generate_pdf_dossier(
                            username=username,
                            found=list(progress.found),
                            not_found=list(progress.not_found),
                            errors=list(progress.errors),
                            enrichments=dict(app_state.enrichments or {}),
                            total_sites=progress.total_sites or 3302,
                            checked_sites=progress.checked_sites or len(progress.found),
                        )
                        if not pdf_bytes:
                            raise RuntimeError("PDF generation returned empty output")
                        report_bytes = pdf_bytes

                    elif format_type == "xmind":
                        from services.report_service import generate_xmind_case

                        xmind_path = generate_xmind_case(
                            username=username,
                            found=list(progress.found),
                            enrichments=dict(app_state.enrichments or {}),
                        )
                        if not xmind_path or not xmind_path.exists():
                            raise RuntimeError("XMind generation returned empty output")
                        report_bytes = xmind_path.read_bytes()

                    elif format_type == "csv":
                        import csv
                        import io

                        output = io.StringIO()
                        writer = csv.writer(output)
                        writer.writerow(
                            [
                                "username",
                                "name",
                                "url_main",
                                "url_user",
                                "exists",
                                "http_status",
                                "response_time_s",
                            ]
                        )
                        all_results = (
                            progress.found + progress.not_found + progress.errors
                        )
                        for r in all_results:
                            writer.writerow(
                                [
                                    progress.username,
                                    r.site_name,
                                    r.url_main,
                                    r.url_user or r.url_main,
                                    r.status,
                                    r.http_status,
                                    f"{r.query_time:.2f}" if r.query_time else "",
                                ]
                            )
                        report_bytes = output.getvalue().encode("utf-8")

                    elif format_type == "json":
                        import json

                        data = {
                            "username": progress.username,
                            "total_sites": progress.total_sites,
                            "checked_sites": progress.checked_sites,
                            "found": [
                                {
                                    "name": r.site_name,
                                    "url_main": r.url_main,
                                    "url_user": r.url_user,
                                    "status": r.status,
                                    "http_status": r.http_status,
                                    "response_time_s": r.query_time,
                                    "tags": getattr(r, "tags", []),
                                }
                                for r in progress.found
                            ],
                            "not_found": [
                                {
                                    "name": r.site_name,
                                    "url_main": r.url_main,
                                    "url_user": r.url_user or r.url_main,
                                    "status": r.status,
                                }
                                for r in progress.not_found
                            ],
                            "errors": [
                                {
                                    "name": r.site_name,
                                    "url_main": r.url_main,
                                    "url_user": r.url_user or r.url_main,
                                    "status": r.status,
                                    "context": getattr(r, "context", None),
                                }
                                for r in progress.errors
                            ],
                        }
                        report_bytes = json.dumps(data, indent=2).encode("utf-8")

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

        def _show_graph_analysis_dialog(progress, app_state):
            from flet import context

            page = context.page
            if not page:
                return

            from services.graph_service import (
                build_identity_graph,
                export_cytoscape_json,
                get_graph_analytics,
            )

            username = app_state.last_results_username or getattr(
                progress, "username", "target"
            )
            G = build_identity_graph(
                username=username,
                found_accounts=list(progress.found),
                enrichments=dict(app_state.enrichments or {}),
                email_results=list(app_state.email_results or []),
            )
            analytics = get_graph_analytics(G)
            cy_data = export_cytoscape_json(G)

            metric_row = ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    str(analytics["nodes"]),
                                    size=tokens.FONT_LG,
                                    weight=ft.FontWeight.BOLD,
                                    color=AppColors.PRIMARY,
                                ),
                                ft.Text(
                                    "Entities",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=0,
                        ),
                        expand=True,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    str(analytics["edges"]),
                                    size=tokens.FONT_LG,
                                    weight=ft.FontWeight.BOLD,
                                    color=AppColors.PRIMARY,
                                ),
                                ft.Text(
                                    "Connections",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=0,
                        ),
                        expand=True,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    str(analytics["components"]),
                                    size=tokens.FONT_LG,
                                    weight=ft.FontWeight.BOLD,
                                    color=AppColors.SUCCESS,
                                ),
                                ft.Text(
                                    "Clusters",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=0,
                        ),
                        expand=True,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_EVENLY,
            )

            hub_rows = []
            for item in analytics.get("top_canonical_nodes", []):
                hub_rows.append(
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.HUB_ROUNDED, size=14, color=AppColors.PRIMARY
                            ),
                            ft.Text(
                                item["label"],
                                size=tokens.FONT_SM,
                                weight=ft.FontWeight.W_500,
                                expand=True,
                            ),
                            ft.Text(
                                f"Rank: {item['centrality']}",
                                size=tokens.FONT_XS,
                                color=AppColors.PRIMARY,
                            ),
                        ],
                        spacing=tokens.SPACE_SM,
                    )
                )

            async def _copy_cytoscape():
                import json

                try:
                    cb = ft.Clipboard()
                    if cy_data:
                        await cb.set(json.dumps(cy_data, indent=2))
                        from core.notify import show_snack

                        show_snack(
                            page,
                            "Cytoscape JSON copied to clipboard!",
                            bgcolor=AppColors.SUCCESS,
                        )
                except Exception as exc:
                    logger.warning("Failed to copy cytoscape json: %s", exc)

            dlg = ft.AlertDialog(
                modal=False,
                title=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.ACCOUNT_TREE_ROUNDED,
                            color=AppColors.PRIMARY,
                            size=tokens.ICON_MD,
                        ),
                        ft.Text(
                            "Identity Network Analysis",
                            size=tokens.FONT_MD,
                            weight=ft.FontWeight.BOLD,
                            font_family="Outfit",
                            color=AppColors.PRIMARY,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                f"Graph clustering and canonical hubs for {username}",
                                size=tokens.FONT_XS,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            ft.Container(height=tokens.SPACE_XS),
                            ft.Container(
                                content=metric_row,
                                padding=tokens.SPACE_MD,
                                border_radius=tokens.RADIUS_MD,
                                bgcolor=ft.Colors.with_opacity(0.08, AppColors.PRIMARY),
                            ),
                            ft.Container(height=tokens.SPACE_SM),
                            ft.Text(
                                "Top Canonical Accounts / Hubs",
                                size=tokens.FONT_XS,
                                weight=ft.FontWeight.BOLD,
                                color=AppColors.PRIMARY,
                            ),
                            ft.Container(
                                content=ft.Column(
                                    controls=hub_rows
                                    if hub_rows
                                    else [
                                        ft.Text(
                                            "No hubs identified.", size=tokens.FONT_XS
                                        )
                                    ],
                                    spacing=4,
                                ),
                                padding=ft.Padding(0, 4, 0, 4),
                            ),
                        ],
                        tight=True,
                        spacing=0,
                    ),
                    width=380,
                ),
                actions=[
                    ft.TextButton(
                        "Copy Cytoscape JSON",
                        icon=ft.Icons.COPY_ROUNDED,
                        on_click=lambda e: asyncio.create_task(_copy_cytoscape()),
                    ),
                    ft.TextButton("Close", on_click=lambda e: page.pop_dialog()),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.show_dialog(dlg)

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
                                "Identity Network Analysis",
                                weight=ft.FontWeight.W_600,
                            ),
                            subtitle=ft.Text("Graph clustering & hub analytics"),
                            leading=ft.Icon(
                                ft.Icons.ACCOUNT_TREE_ROUNDED, color=AppColors.PRIMARY
                            ),
                            on_click=lambda e: (
                                page.pop_dialog(),
                                _show_graph_analysis_dialog(
                                    app_state.search_progress, app_state
                                ),
                            ),
                        ),
                        ft.ListTile(
                            title=ft.Text(
                                "PDF Intelligence Dossier (.pdf)",
                                weight=ft.FontWeight.W_600,
                            ),
                            subtitle=ft.Text("Gold-branded printable report"),
                            leading=ft.Icon(
                                ft.Icons.PICTURE_AS_PDF_ROUNDED, color=AppColors.PRIMARY
                            ),
                            on_click=lambda e: (
                                page.pop_dialog(),
                                _on_export_click("pdf"),
                            ),
                        ),
                        ft.ListTile(
                            title=ft.Text(
                                "XMind Mind Map (.xmind)", weight=ft.FontWeight.W_600
                            ),
                            subtitle=ft.Text("Visual intelligence case file"),
                            leading=ft.Icon(
                                ft.Icons.HUB_ROUNDED, color=AppColors.PRIMARY
                            ),
                            on_click=lambda e: (
                                page.pop_dialog(),
                                _on_export_click("xmind"),
                            ),
                        ),
                        ft.ListTile(
                            title=ft.Text(
                                "CSV Spreadsheet (.csv)", weight=ft.FontWeight.W_600
                            ),
                            subtitle=ft.Text("Spreadsheet compatible data"),
                            leading=ft.Icon(
                                ft.Icons.TABLE_CHART_ROUNDED, color=AppColors.PRIMARY
                            ),
                            on_click=lambda e: (
                                page.pop_dialog(),
                                _on_export_click("csv"),
                            ),
                        ),
                        ft.ListTile(
                            title=ft.Text(
                                "JSON Data (.json)", weight=ft.FontWeight.W_600
                            ),
                            subtitle=ft.Text("Structured JSON export"),
                            leading=ft.Icon(
                                ft.Icons.DATA_OBJECT_ROUNDED, color=AppColors.PRIMARY
                            ),
                            on_click=lambda e: (
                                page.pop_dialog(),
                                _on_export_click("json"),
                            ),
                        ),
                        ft.ListTile(
                            title=ft.Text(
                                "Plain Text List (.txt)", weight=ft.FontWeight.W_600
                            ),
                            subtitle=ft.Text("Discovered URLs only"),
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
