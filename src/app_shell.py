"""AppShell — top-level shell branching onboarding, results, sites vs dashboard.

Mirrors KTV's AppShell pattern: use_state for active_view + injected controller
closures + chrome sync via use_effect. Manages both appbar AND navigation_bar.
"""

import logging
import re
import unicodedata
from typing import Any

import flet as ft
from flet import Control

from core.tasks import spawn
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


_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _safe_filename(raw: object, max_len: int = 64) -> str:
    """Slugify user input for the export save-dialog filename (stdlib only).

    NFKD ascii-fold → lower → [^a-z0-9]+ → "-" → strip, with "scan"
    fallback, Windows-reserved guard (CON/PRN/AUX/NUL/COM1-9/LPT1-9), and a
    64-char cap on the slug portion.
    """
    text = unicodedata.normalize("NFKD", str(raw or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = text[:max_len].strip("-") or "scan"
    if text.upper() in _WINDOWS_RESERVED:
        text = f"{text}-file"
    return text


def _email_export_bytes(format_type: str, app_state) -> bytes | None:
    """CSV/JSON/TXT export for email-mode results (holehe-v2 dict rows).

    PDF dossiers are username-mode (SiteResult-shaped) — returns
    None for them so the caller shows visible guidance instead of failing.
    """
    if format_type not in ("csv", "json", "txt", "md", "html"):
        return None
    from core.constants import MODE_PHONE
    if getattr(app_state, "search_mode", "") == MODE_PHONE:
        rows = list(app_state.phone_results or [])
        addr = app_state.phone_results_address or "unknown"
    else:
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
                    json.dumps(extra, ensure_ascii=False, default=str) if extra else "",
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
        f"{r.get('name', '?')} ({r.get('domain', '')}): {_status_of(r)}" for r in rows
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _extract_row_url(r: Any) -> str | None:
    """Safely extract target URL from a result row (SiteResult, PhoneResult, EmailResult, or dict)."""
    u = getattr(r, "url_user", None) or getattr(r, "url_main", None) or getattr(r, "url", None)
    if not u and isinstance(r, dict):
        u = r.get("url_user") or r.get("url_main") or r.get("url")
    if not u:
        others = getattr(r, "others", None) or (r.get("others") if isinstance(r, dict) else None)
        if isinstance(others, dict):
            u = others.get("url") or (others.get("extra") or {}).get("url")
    return str(u) if u else None


def _build_appbar(active_view: str, active_tab: int, controller) -> ft.AppBar:
    """Build the appropriate appbar for the current view/tab."""
    from core import tokens
    from core.constants import SITES_TOTAL_FALLBACK

    if active_view == "results":

        def _copy_urls(e):
            try:
                from core.shared_services import shared_haptics

                spawn(shared_haptics().medium_impact())
            except Exception:
                pass

            async def _copy():
                from flet import context

                page = context.page
                from core.notify import show_snack
                from core.state import state as app_state

                if not (app_state.search_progress and app_state.search_progress.found):
                    show_snack(page, "Nothing to copy yet", bgcolor=AppColors.WARNING)
                    return
                found = app_state.search_progress.found
                urls = [u for r in found if (u := _extract_row_url(r))]
                if not urls:
                    show_snack(page, "Nothing to copy yet", bgcolor=AppColors.WARNING)
                    return
                try:
                    from core.shared_services import shared_clipboard

                    cb = shared_clipboard(page)
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

            spawn(_copy())

        def _share_urls(e):
            try:
                from core.shared_services import shared_haptics

                spawn(shared_haptics().light_impact())
            except Exception:
                pass

            async def _share():
                from flet import context

                from core.notify import show_snack
                from core.state import state as app_state

                page = context.page
                if not (app_state.search_progress and app_state.search_progress.found):
                    show_snack(page, "Nothing to share yet", bgcolor=AppColors.WARNING)
                    return
                urls = [u for r in app_state.search_progress.found if (u := _extract_row_url(r))]
                if not urls:
                    show_snack(page, "Nothing to share yet", bgcolor=AppColors.WARNING)
                    return
                share_text_content = "\n".join(urls[:20])
                if len(urls) > 20:
                    show_snack(
                        page,
                        f"Sharing first 20 of {len(urls)} URLs",
                        bgcolor=AppColors.WARNING,
                    )
                try:
                    from core.shared_services import shared_share

                    share_service = shared_share()
                    await share_service.share_text(share_text_content)
                except Exception as ex:
                    logger.warning("Share failed: %s", ex)

            spawn(_share())

        def _on_export_click(format_type: str):
            """Full export dialog — Excel, CSV, or Text (original Sherlock behavior)."""

            async def _do_export():
                from flet import context

                page = context.page
                from core.constants import MODE_EMAIL, MODE_PHONE
                from core.state import state as app_state
                from core.theme import AppColors

                progress = app_state.search_progress
                if not progress:
                    return
                is_phone = getattr(progress, "phone", None) is not None
                is_email = getattr(progress, "email", None) is not None
                is_email_or_phone = is_phone or is_email or app_state.search_mode in (MODE_EMAIL, MODE_PHONE)
                if is_phone:
                    username = getattr(progress, "phone", None) or app_state.phone_results_address or "unknown"
                elif is_email:
                    username = getattr(progress, "email", None) or app_state.email_results_address or "unknown"
                else:
                    username = getattr(progress, "username", None) or app_state.last_results_username or "unknown"

                try:
                    from services.cache_service import (
                        load_cached_report,
                        save_cached_report,
                    )

                    # Scan signature: a re-scan that found the same accounts but
                    # has a different checked/not-found/error shape must NOT
                    # reuse the earlier report, or a mid-scan export is served
                    # as the completed one.
                    _sig = "|".join(
                        str(v)
                        for v in (
                            getattr(progress, "checked_sites", None)
                            or getattr(progress, "checked_modules", 0),
                            getattr(progress, "total_sites", None)
                            or getattr(progress, "total_modules", 0),
                            len(getattr(progress, "not_found", []) or []),
                            len(getattr(progress, "errors", []) or []),
                        )
                    )

                    if is_email_or_phone:
                        report_bytes = _email_export_bytes(format_type, app_state)
                        if report_bytes is None:
                            raise ValueError(
                                "Nothing to export for this mode — run a scan "
                                "first, then export as CSV, JSON, TXT, "
                                "Markdown, or HTML"
                            )

                    elif format_type == "csv":
                        from services.report_service import generate_csv_report

                        report_bytes = generate_csv_report(
                            getattr(progress, "username", username),
                            list(progress.found),
                            list(progress.not_found),
                            list(progress.errors),
                        )

                    elif format_type == "json":
                        from services.report_service import generate_json_report

                        report_bytes = generate_json_report(
                            getattr(progress, "username", username),
                            list(progress.found),
                            list(progress.not_found),
                            list(progress.errors),
                        )

                    elif format_type in ("md", "html"):
                        from services.report_service import (
                            generate_html_report,
                            generate_markdown_report,
                        )

                        cached_text = load_cached_report(
                            format_type, username, list(progress.found),
                            format_type, _sig,
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
                                total_sites=progress.total_sites
                                or SITES_TOTAL_FALLBACK,
                                checked_sites=progress.checked_sites
                                or len(progress.found),
                            )
                            if not report_bytes:
                                raise RuntimeError(
                                    "Nothing to render — the scan has no results"
                                )
                            save_cached_report(
                                format_type,
                                username,
                                list(progress.found),
                                format_type,
                                report_bytes,
                                _sig,
                            )
                    else:
                        from services.report_service import generate_txt_report

                        report_bytes = generate_txt_report(
                            getattr(progress, "username", username),
                            list(progress.found),
                        )

                    ext = format_type.lower()
                    # Self-registers on construction; a page.services append
                    # would pin it against Flet's service GC. src_bytes is
                    # written by the picker itself on desktop.
                    file_picker = ft.FilePicker()
                    path = await file_picker.save_file(
                        file_name=f"sherlock_{_safe_filename(username)}.{ext}",
                        dialog_title=f"Save scan report as {format_type.upper()}",
                        src_bytes=report_bytes,
                    )
                    if not path:
                        return

                    from core.notify import show_snack

                    show_snack(page, "Saved successfully!", bgcolor=AppColors.SUCCESS)

                    # Ad item: an interstitial at the "I got what I came for"
                    # moment. share_account('Anda') — the report just landed on
                    # disk, so a pause here is expected rather than intrusive.
                    # The service's own interval guard prevents stacking with
                    # the search interstitial.
                    try:
                        from main import _AD_SERVICE_REF

                        ad_service = _AD_SERVICE_REF.get("service")
                        if ad_service is not None:
                            await ad_service.show_interstitial()
                    except Exception as exc:
                        logger.warning("Export interstitial failed: %s", exc)
                except Exception as ex:
                    logger.exception("Export failed")
                    from core.notify import show_snack

                    show_snack(
                        page,
                        f"Failed to save: {ex!s}",
                        bgcolor=AppColors.ERROR,
                        duration=10000,
                    )

            spawn(_do_export())

        def _show_export_dialog(e):
            from core.constants import MODE_EMAIL, MODE_PHONE
            from core.state import state as app_state

            if not app_state.search_progress:
                return
            prog = app_state.search_progress
            dialog_is_phone = getattr(prog, "phone", None) is not None or app_state.search_mode == MODE_PHONE
            dialog_is_email = not dialog_is_phone and (
                getattr(prog, "email", None) is not None or app_state.search_mode == MODE_EMAIL
            )

            def _export_tile(
                title: str,
                subtitle: str,
                icon,
                format_type: str,
            ) -> ft.ListTile:
                return ft.ListTile(
                    title=ft.Text(
                        title,
                        weight=ft.FontWeight.W_600,
                    ),
                    subtitle=ft.Text(subtitle),
                    leading=ft.Icon(
                        icon,
                        color=AppColors.PRIMARY,
                    ),
                    on_click=lambda e, f=format_type: (
                        controller.close_dialog(),
                        _on_export_click(f),
                    ),
                )

            tiles = []
            if dialog_is_phone:
                tiles.append(
                    ft.ListTile(
                        title=ft.Text(
                            "Phone formats: CSV, JSON, Markdown, HTML, TXT",
                            weight=ft.FontWeight.W_600,
                        ),
                        subtitle=ft.Text("Everything exports offline, on-device"),
                    )
                )
            elif dialog_is_email:
                tiles.append(
                    ft.ListTile(
                        title=ft.Text(
                            "Email formats: CSV, JSON, Markdown, HTML, TXT",
                            weight=ft.FontWeight.W_600,
                        ),
                        subtitle=ft.Text("Everything exports offline, on-device"),
                    )
                )
            tiles.append(
                _export_tile(
                    "CSV Spreadsheet (.csv)",
                    "Spreadsheet compatible data",
                    ft.Icons.TABLE_CHART_ROUNDED,
                    "csv",
                )
            )
            tiles.append(
                _export_tile(
                    "JSON Data (.json)",
                    "Structured JSON export",
                    ft.Icons.DATA_OBJECT_ROUNDED,
                    "json",
                )
            )
            tiles.append(
                _export_tile(
                    "Markdown Report (.md)",
                    "Shareable plain-text dossier",
                    ft.Icons.DESCRIPTION_ROUNDED,
                    "md",
                )
            )
            tiles.append(
                _export_tile(
                    "HTML Dossier (.html)",
                    "Offline single-file report",
                    ft.Icons.HTML_ROUNDED,
                    "html",
                )
            )
            tiles.append(
                _export_tile(
                    "Plain Text List (.txt)",
                    "Discovered URLs only",
                    ft.Icons.ARTICLE_ROUNDED,
                    "txt",
                )
            )
            sheet = ft.BottomSheet(
                content=ft.Container(
                    content=ft.ListView(
                        controls=tiles,
                        spacing=0,
                        padding=ft.Padding(0, 0, 0, tokens.SPACE_MD),
                    ),
                    padding=ft.Padding(0, tokens.SPACE_XS, 0, tokens.SPACE_MD),
                    height=470,
                ),
                scrollable=True,
                show_drag_handle=True,
                on_dismiss=lambda e: controller.close_dialog(),
            )
            controller.open_sheet(sheet)

        def _restart(e):
            from core.constants import MODE_EMAIL as _MODE_EMAIL
            from core.constants import MODE_PHONE as _MODE_PHONE
            from core.state import state as app_state

            # Owner fix: the retry button must respect the MODE of the
            # results being viewed — email re-runs the email engine, phone
            # re-runs the phone engine (previously only a username scan was
            # ever started, so email/phone retries silently did nothing or
            # restarted an old query).
            prog = app_state.search_progress
            is_phone = (
                app_state.search_mode == _MODE_PHONE
                or getattr(prog, "phone", None) is not None
            )
            is_email = (
                app_state.search_mode == _MODE_EMAIL
                or getattr(prog, "email", None) is not None
            )
            if is_phone:
                target = app_state.phone_results_address or getattr(prog, "phone", None)
                if target:
                    spawn(controller.start_phone_search(target))
                    controller.show_results()
            elif is_email:
                target = app_state.email_results_address or getattr(prog, "email", None)
                if target:
                    # NOTE: is_searching is deliberately NOT set here. Setting
                    # it optimistically made start_*_search take the
                    # re-attach path (is_searching + same target) and return
                    # without scanning — leaving the flag stuck True so every
                    # later search also just re-attached to a dead scan. The
                    # empty-frame concern is covered by the results screen
                    # rendering the cached rows first, then the scan view the
                    # moment start_search sets the flag itself.
                    # search_mode is likewise left alone: start_*_search sets
                    # it after its own gates, so an offline/busy retry
                    # cannot strand a live scan of the other mode with its
                    # ticks being dropped.
                    spawn(controller.start_email_search(target))
                    controller.show_results()
            elif app_state.last_results_username:
                spawn(controller.start_search(app_state.last_results_username))
                controller.show_results()

        from core.constants import MODE_EMAIL, MODE_PHONE
        from core.state import state as app_state

        is_email_results = (
            app_state.search_mode in (MODE_EMAIL, MODE_PHONE)
            or getattr(app_state.search_progress, "email", None) is not None
            or getattr(app_state.search_progress, "phone", None) is not None
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
                ]
            )
        # Export is available in both modes: the export sheet filters its
        # tiles by mode (email exports CSV/JSON/TXT/Markdown/HTML; PDF
        # dossiers are username-mode and show guidance instead).
        _actions.append(
            ft.IconButton(
                icon=ft.Icons.DOWNLOAD_ROUNDED,
                tooltip="Export",
                on_click=_show_export_dialog,
            )
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
                tooltip="Back",
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
                tooltip="Back",
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
    controller.go_home = lambda: (set_active_view("dashboard"), set_active_tab(0))
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

    def _show_settings():
        set_active_view("dashboard")
        set_active_tab(2)

    def _show_history():
        set_active_view("dashboard")
        set_active_tab(1)

    controller.show_settings = _show_settings
    controller.show_history = _show_history

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
            logger.exception("Failed to build appbar")

        # Onboarding: no nav bar
        if _should_show_onboarding(state):
            page.views[0].navigation_bar = None
            try:
                page.update()
            except Exception:
                logger.exception("Failed to update page in onboarding chrome sync")
            return

        # Results / Sites: no navigation bar (full-screen)
        if active_view in ("results", "sites"):
            page.views[0].navigation_bar = None
            try:
                page.update()
            except Exception:
                logger.exception("Failed to update page in results/sites chrome sync")
            return

        # Dashboard: show the navigation bar
        current_nav = page.views[0].navigation_bar
        unseen = getattr(state, "history_unseen", 0) or 0
        history_badge = (
            ft.Badge(
                label=str(unseen),
                bgcolor=ft.Colors.PRIMARY,
                text_color=ft.Colors.WHITE,
                small_size=10,
                large_size=16,
            )
            if unseen > 0
            else None
        )
        if isinstance(current_nav, ft.NavigationBar):
            current_nav.selected_index = active_tab
            if len(current_nav.destinations) > 1:
                current_nav.destinations[1].badge = history_badge
        else:
            destinations = [
                ft.NavigationBarDestination(
                    icon=icon,
                    label=label,
                    badge=history_badge if label == "History" else None,
                )
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
            logger.exception("Failed to update page in dashboard chrome sync")

    # NOTE: progress_version deliberately NOT in deps — the reactive patch
    # already pushes scan progress to the UI; adding it here forced a second
    # full page.update() serialization per progress tick and saturated the
    # main loop (the scan freeze). Chrome only needs to sync on branch,
    # auth, theme, or badge changes.
    ft.use_effect(
        _sync_chrome,
        [
            active_tab,
            active_view,
            state.has_accepted_terms,
            state.is_first_launch,
            state.theme_mode,
            # The History destination badge reads this inside `_sync_chrome`.
            # Without it as a dep the effect never re-ran on a completed
            # scan, so the badge appeared only after an unrelated change
            # (tab switch, theme) happened to re-run it.
            state.history_unseen,
        ],
    )

    # --- Branching ---
    from screens.history_screen import HistoryScreen
    from screens.home_screen import HomeScreen
    from screens.onboarding_screen import OnboardingScreen
    from screens.results_screen import ResultsScreen
    from screens.settings_screen import SettingsScreen
    from screens.sites_screen import SitesScreen

    # The branch is a pure function of these two local values plus the one-time
    # onboarding flags. Nothing else in AppState may decide which screen is
    # mounted.
    onboarding = _should_show_onboarding(state)
    branch = (
        "onboarding"
        if onboarding
        else (
            "results"
            if active_view == "results"
            else ("sites" if active_view == "sites" else "dashboard")
        )
    )

    # Screen construction is memoized on the branch ONLY.
    #
    # `use_context(AppStateCtx)` subscribes this component to the whole
    # observable — `Observable.__on_change` fires on any field change and does
    # not say which one (.venv/flet/components/observable.py:82-92). So the
    # shell re-renders on every write, and this render body used to construct
    # the active screen from scratch each time: 20 setting cards, or 5,178
    # network rows. With `progress_version` written 18x per scan tick in
    # main.py, that is dozens of full re-mounts per second — the multi-minute
    # freeze. The screens each hold their own AppStateCtx subscription, so
    # they re-render themselves when their fields change; the shell does not
    # need to, and must not.
    # Reactive in-app scan banner (non-memoized so progress ticks update it
    # without re-mounting the whole screen — that re-mount was the freeze).
    def _live_banner():
        if not (state.is_searching and state.current_username):
            return None
        prog = state.search_progress
        checked = getattr(prog, "checked_sites", 0) or getattr(prog, "checked_modules", 0)
        total = getattr(prog, "total_sites", 0) or getattr(prog, "total_modules", 0)
        finishing = bool(total and checked >= total and getattr(prog, "is_running", False))
        from components.active_scan_banner import ActiveScanBanner

        return ActiveScanBanner(
            target_query=state.current_username,
            search_mode=state.search_mode,
            checked=checked,
            total=total,
            on_tap=controller.show_results,
            finishing=finishing,
        )

    live_banner = _live_banner()

    screen = ft.use_memo(
        lambda: (
            OnboardingScreen()
            if branch == "onboarding"
            else (
                ResultsScreen()
                if branch == "results"
                else (
                    SitesScreen()
                    if branch == "sites"
                    else (
                        HomeScreen(banner=live_banner)
                        if active_tab == 0
                        else (
                            HistoryScreen(banner=live_banner)
                            if active_tab == 1
                            else SettingsScreen(banner=live_banner)
                        )
                    )
                )
            )
        ),
        [branch, active_tab, live_banner is not None],
    )

    return ft.SafeArea(content=screen, expand=True)
