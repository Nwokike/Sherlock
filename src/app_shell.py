"""AppShell — top-level shell branching onboarding, results, sites vs dashboard.

Mirrors KTV's AppShell pattern: use_state for active_view + injected controller
closures + chrome sync via use_effect. Manages both appbar AND navigation_bar.
"""

import asyncio
import logging

import flet as ft
from flet import Control

from components.active_scan_banner import ActiveScanBanner
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


def _email_export_bytes(format_type: str, app_state) -> bytes | None:
    """CSV/JSON/TXT export for email-mode results (holehe-v2 dict rows).

    PDF/XMind dossiers are username-mode (SiteResult-shaped) — returns
    None for them so the caller shows visible guidance instead of failing.
    """
    if format_type not in ("csv", "json", "txt", "md", "html"):
        return None
    rows = list(app_state.email_results or [])
    addr = app_state.email_results_address or "unknown"
    if format_type in ("md", "html"):
        from services.report_service import (
            generate_email_html_report,
            generate_email_markdown_report,
        )

        fn = (
            generate_email_html_report
            if format_type == "html"
            else generate_email_markdown_report
        )
        return fn(addr, rows)

    def _status_of(r) -> str:
        if r.get("exists"):
            return "FOUND"
        if r.get("rateLimit"):
            return "RATE_LIMITED"
        if r.get("unavailable"):
            return "UNAVAILABLE"
        return "not found"

    if format_type == "csv":
        import csv
        import io
        import json

        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            ["email", "platform", "domain", "status", "message", "extra_json"]
        )
        for r in rows:
            others = r.get("others") or {}
            extra = others.get("extra") or {}
            writer.writerow(
                [
                    addr,
                    r.get("name", ""),
                    r.get("domain", ""),
                    _status_of(r),
                    others.get("message") or others.get("error") or "",
                    json.dumps(extra, ensure_ascii=False, default=str)
                    if extra
                    else "",
                ]
            )
        return out.getvalue().encode("utf-8")

    if format_type == "json":
        import json

        payload = {
            "email": addr,
            "found": sum(1 for r in rows if r.get("exists")),
            "results": rows,
        }
        return json.dumps(payload, indent=2, ensure_ascii=False, default=str).encode(
            "utf-8"
        )

    lines = [f"Sherlock email OSINT — {addr}", ""] + [
        f"{r.get('name', '?')} ({r.get('domain', '')}): {_status_of(r)}"
        for r in rows
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


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
                share_text_content = "\n".join(urls[:20])
                try:
                    # Service construction self-registers with the page —
                    # appending to page.services is redundant and pins a
                    # reference that defeats Flet's service GC.
                    share_service = ft.Share()
                    await share_service.share_text(share_text_content)
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

                controller.close_dialog()
                progress = app_state.search_progress
                if not progress:
                    return
                is_email = getattr(progress, "email", None) is not None
                username = (
                    app_state.email_results_address or "unknown"
                    if is_email
                    else (app_state.last_results_username or "unknown")
                )

                try:
                    from services.cache_service import (
                        load_cached_report,
                        save_cached_report,
                    )

                    if is_email:
                        report_bytes = _email_export_bytes(format_type, app_state)
                        if report_bytes is None:
                            raise ValueError(
                                "PDF/XMind dossiers are username-mode — email "
                                "results export as CSV, JSON, TXT, Markdown, or HTML"
                            )
                    elif format_type == "pdf":
                        from services.report_service import generate_pdf_dossier

                        report_bytes = load_cached_report(
                            "pdf", username, list(progress.found), "pdf"
                        )
                        if report_bytes is None:
                            pdf_bytes = generate_pdf_dossier(
                                username=username,
                                found=list(progress.found),
                                not_found=list(progress.not_found),
                                errors=list(progress.errors),
                                enrichments=dict(app_state.enrichments or {}),
                                total_sites=progress.total_sites or 5203,
                                checked_sites=progress.checked_sites
                                or len(progress.found),
                            )
                            if not pdf_bytes:
                                raise RuntimeError(
                                    "PDF generation returned empty output"
                                )
                            report_bytes = pdf_bytes
                            save_cached_report(
                                "pdf", username, list(progress.found), "pdf", pdf_bytes
                            )

                    elif format_type == "xmind":
                        from services.report_service import generate_xmind_case

                        report_bytes = load_cached_report(
                            "xmind", username, list(progress.found), "xmind"
                        )
                        if report_bytes is None:
                            xmind_path = generate_xmind_case(
                                username=username,
                                found=list(progress.found),
                                enrichments=dict(app_state.enrichments or {}),
                            )
                            if not xmind_path or not xmind_path.exists():
                                raise RuntimeError(
                                    "XMind generation returned empty output"
                                )
                            report_bytes = xmind_path.read_bytes()
                            save_cached_report(
                                "xmind",
                                username,
                                list(progress.found),
                                "xmind",
                                report_bytes,
                            )

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

                    elif format_type in ("md", "html"):
                        from services.report_service import (
                            generate_html_report,
                            generate_markdown_report,
                        )

                        cached_text = load_cached_report(
                            format_type, username, list(progress.found), format_type
                        )
                        if cached_text is not None:
                            report_bytes = cached_text
                        else:
                            gen = (
                                generate_html_report
                                if format_type == "html"
                                else generate_markdown_report
                            )
                            report_bytes = gen(
                                username=username,
                                found=list(progress.found),
                                not_found=list(progress.not_found),
                                errors=list(progress.errors),
                                enrichments=dict(app_state.enrichments or {}),
                                total_sites=progress.total_sites or 5203,
                                checked_sites=progress.checked_sites
                                or len(progress.found),
                            )
                            if not report_bytes:
                                raise RuntimeError(
                                    f"{format_type.upper()} generation returned empty output"
                                )
                            save_cached_report(
                                format_type,
                                username,
                                list(progress.found),
                                format_type,
                                report_bytes,
                            )
                    else:
                        output = []
                        for r in progress.found:
                            if r.url_user:
                                output.append(f"{r.url_user}\n")
                        output.append(f"Total Detected : {len(progress.found)}\n")
                        report_bytes = "".join(output).encode("utf-8")

                    ext = format_type.lower()
                    # Self-registers on construction; a page.services append
                    # would pin it against Flet's service GC.
                    file_picker = ft.FilePicker()
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

            hub_rows = [
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
                for item in analytics.get("top_canonical_nodes", [])
            ]

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

            async def _copy_cypher():
                try:
                    from services.graph_service import export_cypher

                    text = export_cypher(G)
                    if not text:
                        raise RuntimeError("empty Cypher export")
                    cb = ft.Clipboard()
                    await cb.set(text)
                    from core.notify import show_snack

                    show_snack(
                        page, "Cypher copied to clipboard!", bgcolor=AppColors.SUCCESS
                    )
                except Exception as exc:
                    logger.warning("Failed to copy Cypher: %s", exc)
                    from core.notify import show_snack

                    show_snack(page, f"Cypher copy failed: {exc}", bgcolor=AppColors.ERROR)

            async def _open_interactive_viewer():
                try:
                    from pathlib import Path as _Path

                    from services.graph_service import export_pyvis_html
                    from services.storage_service import get_cache_dir

                    saved = export_pyvis_html(
                        G, _Path(get_cache_dir()) / "identity_graph.html"
                    )
                    if not saved:
                        raise RuntimeError("pyvis export unavailable")
                    await ft.UrlLauncher().launch_url(saved.as_uri())
                except Exception as exc:
                    logger.warning("Interactive viewer failed: %s", exc)
                    from core.notify import show_snack

                    show_snack(
                        page, f"Interactive viewer failed: {exc}", bgcolor=AppColors.ERROR
                    )

            communities = analytics.get("communities", [])
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
                            ft.Container(height=tokens.SPACE_SM),
                            ft.Text(
                                "Evidence Communities",
                                size=tokens.FONT_XS,
                                weight=ft.FontWeight.BOLD,
                                color=AppColors.PRIMARY,
                            ),
                            ft.Column(
                                controls=[
                                    ft.Row(
                                        [
                                            ft.Text(
                                                f"{c['size']} linked",
                                                size=tokens.FONT_XS,
                                                weight=ft.FontWeight.W_600,
                                                color=AppColors.PRIMARY,
                                            ),
                                            ft.Text(
                                                ", ".join(
                                                    str(m) for m in c["members"][:4]
                                                ),
                                                size=tokens.FONT_XS,
                                                color=ft.Colors.ON_SURFACE_VARIANT,
                                                max_lines=1,
                                                overflow=ft.TextOverflow.ELLIPSIS,
                                                expand=True,
                                            ),
                                        ],
                                        spacing=tokens.SPACE_SM,
                                    )
                                    for c in communities[:5]
                                ]
                                if communities
                                else [
                                    ft.Text(
                                        "No multi-node clusters yet.",
                                        size=tokens.FONT_XS,
                                        color=ft.Colors.with_opacity(
                                            tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                                        ),
                                    )
                                ],
                                spacing=2,
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
                    ft.TextButton(
                        "Cypher",
                        icon=ft.Icons.DATA_OBJECT_ROUNDED,
                        on_click=lambda e: asyncio.create_task(_copy_cypher()),
                        tooltip="Copy Neo4j Cypher to clipboard",
                    ),
                    ft.TextButton(
                        "Viewer",
                        icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                        on_click=lambda e: asyncio.create_task(
                            _open_interactive_viewer()
                        ),
                        tooltip="Open interactive graph in your browser",
                    ),
                    ft.TextButton("Close", on_click=lambda e: controller.close_dialog()),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            controller.open_sheet(dlg)

        def _show_export_dialog(e):
            from core.state import state as app_state

            if not app_state.search_progress:
                return
            sheet = ft.BottomSheet(
                content=ft.Container(
                    content=ft.ListView(
                        controls=[
                            ft.ListTile(
                                title=ft.Text(
                                    "Identity Network Analysis",
                                    weight=ft.FontWeight.W_600,
                                ),
                                subtitle=ft.Text("Graph clustering & hub analytics"),
                                leading=ft.Icon(
                                    ft.Icons.ACCOUNT_TREE_ROUNDED,
                                    color=AppColors.PRIMARY,
                                ),
                                on_click=lambda e: (
                                    controller.close_dialog(),
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
                                    ft.Icons.PICTURE_AS_PDF_ROUNDED,
                                    color=AppColors.PRIMARY,
                                ),
                                on_click=lambda e: (
                                    controller.close_dialog(),
                                    _on_export_click("pdf"),
                                ),
                            ),
                            ft.ListTile(
                                title=ft.Text(
                                    "XMind Mind Map (.xmind)",
                                    weight=ft.FontWeight.W_600,
                                ),
                                subtitle=ft.Text("Visual intelligence case file"),
                                leading=ft.Icon(
                                    ft.Icons.HUB_ROUNDED, color=AppColors.PRIMARY
                                ),
                                on_click=lambda e: (
                                    controller.close_dialog(),
                                    _on_export_click("xmind"),
                                ),
                            ),
                            ft.ListTile(
                                title=ft.Text(
                                    "CSV Spreadsheet (.csv)", weight=ft.FontWeight.W_600
                                ),
                                subtitle=ft.Text("Spreadsheet compatible data"),
                                leading=ft.Icon(
                                    ft.Icons.TABLE_CHART_ROUNDED,
                                    color=AppColors.PRIMARY,
                                ),
                                on_click=lambda e: (
                                    controller.close_dialog(),
                                    _on_export_click("csv"),
                                ),
                            ),
                            ft.ListTile(
                                title=ft.Text(
                                    "JSON Data (.json)", weight=ft.FontWeight.W_600
                                ),
                                subtitle=ft.Text("Structured JSON export"),
                                leading=ft.Icon(
                                    ft.Icons.DATA_OBJECT_ROUNDED,
                                    color=AppColors.PRIMARY,
                                ),
                                on_click=lambda e: (
                                    controller.close_dialog(),
                                    _on_export_click("json"),
                                ),
                            ),
                            ft.ListTile(
                                title=ft.Text(
                                    "Markdown Report (.md)",
                                    weight=ft.FontWeight.W_600,
                                ),
                                subtitle=ft.Text("Shareable plain-text dossier"),
                                leading=ft.Icon(
                                    ft.Icons.DESCRIPTION_ROUNDED,
                                    color=AppColors.PRIMARY,
                                ),
                                on_click=lambda e: (
                                    controller.close_dialog(),
                                    _on_export_click("md"),
                                ),
                            ),
                            ft.ListTile(
                                title=ft.Text(
                                    "HTML Dossier (.html)",
                                    weight=ft.FontWeight.W_600,
                                ),
                                subtitle=ft.Text("Offline single-file report"),
                                leading=ft.Icon(
                                    ft.Icons.HTML_ROUNDED,
                                    color=AppColors.PRIMARY,
                                ),
                                on_click=lambda e: (
                                    controller.close_dialog(),
                                    _on_export_click("html"),
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
                                    controller.close_dialog(),
                                    _on_export_click("txt"),
                                ),
                            ),
                        ],
                        spacing=0,
                        padding=ft.Padding(0, 0, 0, tokens.SPACE_MD),
                    ),
                    padding=ft.Padding(0, tokens.SPACE_XS, 0, tokens.SPACE_MD),
                    height=470,
                ),
                scrollable=True,
                show_drag_handle=True,
            )
            controller.open_sheet(sheet)

        def _restart(e):
            from core.constants import MODE_EMAIL as _MODE_EMAIL
            from core.state import state as app_state

            # Owner fix: the retry button must respect the MODE of the
            # results being viewed — email results re-run the email engine
            # (previously it only ever started a username scan, so the
            # email retry silently did nothing or restarted an old query).
            prog = app_state.search_progress
            is_email = app_state.search_mode == _MODE_EMAIL or getattr(
                prog, "email", None
                ) is not None
            if is_email:
                target = app_state.email_results_address or getattr(
                    prog, "email", None
                )
                if target:
                    asyncio.create_task(controller.start_email_search(target))
                    controller.show_results()
            elif app_state.last_results_username:
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
    # Single portal-managed overlay dialog (flet 1.0 use_dialog): identity
    # survives every scan-progress re-render — no scheduler drops, no
    # focus loss while results tick (P1-2).
    active_dialog, set_active_dialog = ft.use_state(None)
    try:
        # use_dialog touches ft.context.page, which raises outside a live
        # flet app (unit-test harness). The hook is still invoked every
        # render so hook ordering stays stable; in-app there is no throw.
        ft.use_dialog(active_dialog)
    except RuntimeError:
        pass

    controller = ft.use_context(ControllerMethodsCtx)
    state = ft.use_context(AppStateCtx)

    # Inject view-local closures into the controller methods instance
    controller.show_results = lambda: set_active_view("results")
    controller.show_sites = lambda: set_active_view("sites")
    controller.go_home = lambda: set_active_view("dashboard")
    controller.back = lambda: set_active_view("dashboard")
    controller.open_sheet = lambda d: set_active_dialog(d)
    controller.close_dialog = lambda: set_active_dialog(None)

    def _system_back():
        # Owner: system/back button must never kill the single-view app.
        # Map it onto in-app navigation: results/sites → dashboard,
        # settings/history tabs → home tab, home root → swallowed.
        if _should_show_onboarding(state):
            return
        if active_view != "dashboard":
            controller.back()
        elif active_tab != 0:
            set_active_tab(0)

    controller.handle_system_back = _system_back
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

    # NOTE: progress_version deliberately NOT in deps — the reactive patch
    # already pushes scan progress to the UI; adding it here forced a second
    # full page.update() serialization per progress tick and saturated the
    # main loop (the scan freeze). Chrome only needs to sync on branch,
    # auth, or theme changes.
    ft.use_effect(
        _sync_chrome,
        [
            active_tab,
            active_view,
            state.has_accepted_terms,
            state.theme_mode,
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
        active_banner = None
        if state.is_searching and state.current_username:
            from core.constants import MODE_EMAIL, MODE_USERNAME

            prog = state.search_progress
            checked = getattr(prog, "checked_sites", 0) or getattr(
                prog, "checked_modules", 0
            )
            total = getattr(prog, "total_sites", 0) or getattr(prog, "total_modules", 0)
            active_scan_mode = (
                MODE_EMAIL
                if (prog and hasattr(prog, "checked_modules"))
                else MODE_USERNAME
            )

            def _view_active_scan(mode=active_scan_mode):
                state.search_mode = mode
                controller.show_results()

            # Phase-aware banner (owner report): during the recursive tail
            # the ACTIVE target differs from the query that started the
            # scan; when counts are full but the engine hasn't returned
            # (final drains/follow-ups), say so honestly.
            banner_target = state.current_username
            prog_user = getattr(prog, "username", None)
            if prog_user and prog_user != state.current_username:
                banner_target = f"{prog_user} · follow-up"
            finishing = bool(total and checked >= total)

            active_banner = ActiveScanBanner(
                target_query=banner_target,
                search_mode=active_scan_mode,
                checked=checked,
                total=total,
                finishing=finishing,
                on_tap=_view_active_scan,
            )

        if active_tab == 0:
            tab_body = HomeScreen(banner=active_banner)
        elif active_tab == 1:
            tab_body = HistoryScreen(banner=active_banner)
        else:
            tab_body = SettingsScreen(banner=active_banner)

        screen = _dashboard_scaffold(body=tab_body)

    return ft.SafeArea(content=screen, expand=True)
