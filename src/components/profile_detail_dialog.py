"""ProfileDetailDialog — rich inspection modals for OSINT results.

Extracted helpers: EmailDossier + UsernameDossier share DossierRow.
"""

from __future__ import annotations

import asyncio
import json
import logging

import flet as ft

from core import tokens
from core.constants import ERR_OPEN_URL
from core.geo_utils import resolve_location
from core.theme import AppColors

logger = logging.getLogger("ProfileDetailDialog")


def _stringify(value) -> str:
    """Render any enrichment value as display text.

    socid-extractor's extract() can return non-string values (its final dict
    keeps lists/dicts as-is), so a plain `str()`/`join()` explodes on shapes
    like a list of link dicts — which killed the dossier modal mid-build on
    rich results.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for key in ("url", "link", "href", "value"):
                    if isinstance(item.get(key), str):
                        parts.append(item[key])
                        break
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return ", ".join(parts)
    return str(value)


def _dossier_row(
    page: ft.Page,
    icon: ft.IconData,
    title: str,
    value: str,
    can_copy: bool = False,
) -> ft.Container:
    """Shared detail row with optional copy — used by both dossiers."""
    copy_btn = (
        ft.IconButton(
            icon=ft.Icons.CONTENT_COPY_ROUNDED,
            icon_size=16,
            tooltip=f"Copy {title}",
            on_click=lambda e, v=value, t=title: asyncio.create_task(
                _copy_text(page, v, t)
            ),
        )
        if can_copy
        else ft.Container(width=0)
    )
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(icon, size=16, color=AppColors.PRIMARY),
                ft.Column(
                    [
                        ft.Text(
                            title,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            value,
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_500,
                            color=ft.Colors.ON_SURFACE,
                            selectable=True,
                        ),
                    ],
                    spacing=0,
                    expand=True,
                ),
                copy_btn,
            ],
            spacing=tokens.SPACE_SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(0, 4, 0, 4),
    )


async def _copy_text(page: ft.Page, text: str, label: str):
    try:
        cb = ft.Clipboard()
        await cb.set(text)
        from core.notify import show_snack

        show_snack(page, f"{label} copied to clipboard", bgcolor=AppColors.SUCCESS)
    except Exception as exc:
        logger.warning("Copy failed: %s", exc)


def _email_dossier(
    page: ft.Page,
    site_name: str,
    status: str,
    target_query: str | None,
    url_main: str | None,
    query_time: float | None,
    email_recovery: str | None,
    phone_number: str | None,
    others: dict,
    method: str | None,
    rate_limit: bool,
    frequent_rate_limit: bool,
):
    platform_url = url_main or (
        f"https://{site_name.lower()}.com"
        if "." not in site_name
        else f"https://{site_name}"
    )
    if not platform_url.startswith("http"):
        platform_url = f"https://{platform_url}"

    async def _launch_platform_url():
        page.pop_dialog()
        try:
            await ft.UrlLauncher().launch_url(platform_url)
        except Exception as exc:
            logger.warning("Failed to launch platform URL %s: %s", platform_url, exc)
            from core.notify import show_snack

            show_snack(page, ERR_OPEN_URL, bgcolor=AppColors.ERROR)

    status_text = (
        "Account Confirmed"
        if status == "Claimed"
        else "Rate Limited"
        if rate_limit or status in ("Error", "WAF")
        else "No Account Found"
    )
    status_color = (
        AppColors.SUCCESS
        if status == "Claimed"
        else AppColors.WARNING
        if rate_limit or status in ("Error", "WAF")
        else ft.Colors.ON_SURFACE_VARIANT
    )
    status_bg = (
        ft.Colors.with_opacity(tokens.OPACITY_LIGHT, AppColors.SUCCESS)
        if status == "Claimed"
        else ft.Colors.with_opacity(tokens.OPACITY_LIGHT, AppColors.WARNING)
        if rate_limit or status in ("Error", "WAF")
        else ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE)
    )

    header_row = ft.Row(
        controls=[
            ft.Container(
                content=ft.Icon(
                    ft.Icons.ALTERNATE_EMAIL_ROUNDED
                    if status == "Claimed"
                    else ft.Icons.LANGUAGE_ROUNDED,
                    size=28,
                    color=status_color,
                ),
                width=56,
                height=56,
                border_radius=28,
                bgcolor=ft.Colors.with_opacity(0.12, status_color),
                alignment=ft.Alignment.CENTER,
            ),
            ft.Column(
                controls=[
                    ft.Row(
                        [
                            ft.Text(
                                site_name.capitalize(),
                                size=tokens.FONT_LG,
                                weight=ft.FontWeight.BOLD,
                                font_family="Outfit",
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                expand=True,
                            ),
                            ft.Container(
                                content=ft.Text(
                                    status_text,
                                    size=tokens.FONT_XS,
                                    weight=ft.FontWeight.BOLD,
                                    color=status_color,
                                ),
                                padding=ft.Padding(8, 3, 8, 3),
                                border_radius=tokens.RADIUS_SM,
                                bgcolor=status_bg,
                            ),
                        ],
                        spacing=tokens.SPACE_SM,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        platform_url,
                        size=tokens.FONT_XS,
                        color=ft.Colors.with_opacity(
                            tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                        ),
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=2,
                expand=True,
            ),
        ],
        spacing=tokens.SPACE_MD,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    items: list[ft.Control] = []
    if target_query:
        items.append(
            _dossier_row(
                page,
                ft.Icons.MARK_EMAIL_READ_ROUNDED,
                "Investigated Email",
                target_query,
                can_copy=True,
            )
        )
    if method:
        items.append(
            _dossier_row(
                page,
                ft.Icons.SECURITY_ROUNDED,
                "Detection Vector",
                f"{method.capitalize()} API / Endpoint",
            )
        )
    if email_recovery:
        items.append(
            _dossier_row(
                page,
                ft.Icons.MAIL_LOCK_OUTLINED,
                "Masked Recovery Email",
                email_recovery,
                can_copy=True,
            )
        )
    if phone_number:
        items.append(
            _dossier_row(
                page,
                ft.Icons.PHONE_ANDROID_ROUNDED,
                "Recovery Phone Hint",
                phone_number,
                can_copy=True,
            )
        )
    if others.get("FullName"):
        items.append(
            _dossier_row(
                page,
                ft.Icons.PERSON_OUTLINE_ROUNDED,
                "Disclosed Full Name",
                str(others["FullName"]),
                can_copy=True,
            )
        )
    if others.get("Date, time of the creation"):
        items.append(
            _dossier_row(
                page,
                ft.Icons.CALENDAR_TODAY_ROUNDED,
                "Account Created Timestamp",
                str(others["Date, time of the creation"]),
            )
        )
    if query_time:
        items.append(
            _dossier_row(
                page,
                ft.Icons.TIMER_OUTLINED,
                "Probe Response Time",
                f"{query_time:.2f} seconds",
            )
        )
    if frequent_rate_limit or rate_limit:
        items.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.WARNING_AMBER_ROUNDED,
                            color=AppColors.WARNING,
                            size=16,
                        ),
                        ft.Text(
                            "Platform endpoint enforces strict rate limits.",
                            size=tokens.FONT_XS,
                            color=AppColors.WARNING,
                            expand=True,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                padding=ft.Padding(8, 4, 8, 4),
                border_radius=tokens.RADIUS_SM,
                bgcolor=ft.Colors.with_opacity(0.1, AppColors.WARNING),
                margin=ft.Margin(0, tokens.SPACE_XS, 0, tokens.SPACE_XS),
            )
        )

    def _dismiss(e):
        page.pop_dialog()

    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text(
            "Email Intelligence Dossier",
            size=tokens.FONT_MD,
            weight=ft.FontWeight.BOLD,
            font_family="Outfit",
            color=AppColors.PRIMARY,
        ),
        content=ft.Container(
            content=ft.Column(
                controls=[
                    header_row,
                    ft.Divider(
                        height=tokens.SPACE_MD,
                        color=ft.Colors.with_opacity(0.1, ft.Colors.OUTLINE),
                    ),
                    ft.Column(
                        controls=items,
                        spacing=tokens.SPACE_XS,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                ],
                tight=True,
                spacing=0,
            ),
            width=380,
        ),
        actions=[
            ft.TextButton(
                "Copy Platform URL",
                icon=ft.Icons.LINK_ROUNDED,
                on_click=lambda e: asyncio.create_task(
                    _copy_text(page, platform_url, "Platform website link")
                ),
            ),
            ft.FilledButton(
                content=ft.Text(
                    "Visit Website", weight=ft.FontWeight.W_600, color=ft.Colors.WHITE
                ),
                icon=ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                on_click=lambda e: asyncio.create_task(_launch_platform_url()),
            ),
            ft.TextButton("Close", on_click=_dismiss),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)


def _username_dossier(
    page: ft.Page,
    site_name: str,
    status: str,
    target_query: str | None,
    url_user: str | None,
    url_main: str | None,
    query_time: float | None,
    others: dict,
    enrichment: dict,
):
    profile_url = (
        url_user
        or url_main
        or (
            f"https://{site_name.lower()}.com"
            if "." not in site_name
            else f"https://{site_name}"
        )
    )

    async def _launch_profile_url():
        page.pop_dialog()
        try:
            await ft.UrlLauncher().launch_url(profile_url)
        except Exception as exc:
            logger.warning("Failed to launch profile URL %s: %s", profile_url, exc)
            from core.notify import show_snack

            show_snack(page, ERR_OPEN_URL, bgcolor=AppColors.ERROR)

    enrich = enrichment or {}
    avatar_url = enrich.get("image") or enrich.get("avatar") or enrich.get("photo")
    display_name = _stringify(
        enrich.get("name")
        or enrich.get("fullname")
        or others.get("FullName")
        or target_query
        or site_name
    )
    bio = enrich.get("bio") or enrich.get("description")
    location = enrich.get("location")
    uid = enrich.get("uid") or enrich.get("id")
    followers = enrich.get("follower_count") or enrich.get("followers")
    following = enrich.get("following_count") or enrich.get("following")
    posts = enrich.get("posts_count") or enrich.get("posts")
    join_date = (
        others.get("Date, time of the creation")
        or enrich.get("joined")
        or enrich.get("created_at")
    )
    links = enrich.get("links") or enrich.get("url")

    # Validate avatar is http(s) — socid may return relative paths.
    has_valid_avatar = bool(
        avatar_url and isinstance(avatar_url, str) and avatar_url.startswith("http")
    )

    if has_valid_avatar:
        avatar_control = ft.Image(
            src=avatar_url,
            width=56,
            height=56,
            border_radius=28,
            fit=ft.BoxFit.COVER,
            error_content=ft.Container(
                content=ft.Icon(
                    ft.Icons.PERSON_ROUNDED, size=28, color=AppColors.PRIMARY
                ),
                width=56,
                height=56,
                border_radius=28,
                bgcolor=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
                alignment=ft.Alignment.CENTER,
            ),
        )
    else:
        status_color = (
            AppColors.SUCCESS
            if status == "Claimed"
            else AppColors.WARNING
            if status in ("WAF", "Error")
            else ft.Colors.ON_SURFACE_VARIANT
        )
        avatar_control = ft.Container(
            content=ft.Icon(
                ft.Icons.CHECK_CIRCLE_ROUNDED
                if status == "Claimed"
                else ft.Icons.LANGUAGE_ROUNDED,
                size=28,
                color=status_color,
            ),
            width=56,
            height=56,
            border_radius=28,
            bgcolor=ft.Colors.with_opacity(0.12, status_color),
            alignment=ft.Alignment.CENTER,
        )

    chip_color = (
        AppColors.SUCCESS
        if status == "Claimed"
        else AppColors.WARNING
        if status in ("WAF", "Error")
        else ft.Colors.with_opacity(tokens.OPACITY_DIM, ft.Colors.ON_SURFACE)
    )
    chip_bg = (
        ft.Colors.with_opacity(tokens.OPACITY_LIGHT, AppColors.SUCCESS)
        if status == "Claimed"
        else ft.Colors.with_opacity(tokens.OPACITY_LIGHT, AppColors.WARNING)
        if status in ("WAF", "Error")
        else ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE)
    )

    header_row = ft.Row(
        controls=[
            avatar_control,
            ft.Column(
                controls=[
                    ft.Row(
                        [
                            ft.Text(
                                display_name,
                                size=tokens.FONT_LG,
                                weight=ft.FontWeight.BOLD,
                                font_family="Outfit",
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                expand=True,
                            ),
                            ft.Container(
                                content=ft.Text(
                                    status,
                                    size=tokens.FONT_XS,
                                    weight=ft.FontWeight.BOLD,
                                    color=chip_color,
                                ),
                                padding=ft.Padding(8, 3, 8, 3),
                                border_radius=tokens.RADIUS_SM,
                                bgcolor=chip_bg,
                            ),
                        ],
                        spacing=tokens.SPACE_SM,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        site_name,
                        size=tokens.FONT_SM,
                        color=AppColors.PRIMARY,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(
                        profile_url,
                        size=tokens.FONT_XS,
                        color=ft.Colors.with_opacity(
                            tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                        ),
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=2,
                expand=True,
            ),
        ],
        spacing=tokens.SPACE_MD,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    items: list[ft.Control] = []
    if bio:
        items.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Biography / About",
                            size=tokens.FONT_XS,
                            weight=ft.FontWeight.BOLD,
                            color=AppColors.PRIMARY,
                            font_family="Outfit",
                        ),
                        ft.Text(
                            str(bio),
                            size=tokens.FONT_SM,
                            color=ft.Colors.ON_SURFACE,
                            selectable=True,
                        ),
                    ],
                    spacing=4,
                ),
                padding=tokens.SPACE_MD,
                border_radius=tokens.RADIUS_MD,
                bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
                border=ft.Border.all(
                    1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)
                ),
                margin=ft.Margin(0, tokens.SPACE_SM, 0, tokens.SPACE_SM),
            )
        )

    metric_cols = []
    if followers is not None:
        metric_cols.append(
            ft.Column(
                [
                    ft.Text(
                        str(followers),
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.BOLD,
                        color=AppColors.PRIMARY,
                        font_family="Outfit",
                    ),
                    ft.Text(
                        "Followers",
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            )
        )
    if following is not None:
        metric_cols.append(
            ft.Column(
                [
                    ft.Text(
                        str(following),
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.BOLD,
                        color=AppColors.PRIMARY,
                        font_family="Outfit",
                    ),
                    ft.Text(
                        "Following",
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            )
        )
    if posts is not None:
        metric_cols.append(
            ft.Column(
                [
                    ft.Text(
                        str(posts),
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.BOLD,
                        color=AppColors.PRIMARY,
                        font_family="Outfit",
                    ),
                    ft.Text(
                        "Posts", size=tokens.FONT_XS, color=ft.Colors.ON_SURFACE_VARIANT
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            )
        )
    if metric_cols:
        items.append(
            ft.Container(
                content=ft.Row(
                    metric_cols, alignment=ft.MainAxisAlignment.SPACE_EVENLY
                ),
                padding=tokens.SPACE_MD,
                border_radius=tokens.RADIUS_MD,
                bgcolor=ft.Colors.with_opacity(0.06, AppColors.PRIMARY),
                margin=ft.Margin(0, 0, 0, tokens.SPACE_SM),
            )
        )
    if location:
        loc_text = _stringify(location)
        geo = resolve_location(loc_text)
        loc_display = f"{geo.flag} {loc_text}" if (geo and geo.flag) else loc_text
        items.append(
            _dossier_row(page, ft.Icons.LOCATION_ON_OUTLINED, "Location", loc_display)
        )
    if uid:
        items.append(
            _dossier_row(
                page,
                ft.Icons.BADGE_OUTLINED,
                "Account UID / ID",
                _stringify(uid),
                can_copy=True,
            )
        )
    if join_date:
        items.append(
            _dossier_row(
                page,
                ft.Icons.CALENDAR_TODAY_ROUNDED,
                "Account Created / Joined",
                _stringify(join_date),
            )
        )
    if links:
        link_str = _stringify(links)
        items.append(
            _dossier_row(
                page,
                ft.Icons.LINK_ROUNDED,
                "External Links / Websites",
                link_str,
                can_copy=True,
            )
        )
    if query_time:
        items.append(
            _dossier_row(
                page,
                ft.Icons.TIMER_OUTLINED,
                "Response Time",
                f"{query_time:.2f} seconds",
            )
        )

    # Raw OSINT metadata payload preview
    raw_payload = {}
    if enrich:
        raw_payload["enrichment"] = enrich
    if others:
        raw_payload["others"] = others
    if raw_payload:
        json_str = json.dumps(raw_payload, indent=2, ensure_ascii=False)
        items.append(
            ft.ExpansionTile(
                title=ft.Text(
                    "Raw OSINT Indicators / JSON",
                    size=tokens.FONT_SM,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.PRIMARY,
                ),
                leading=ft.Icon(
                    ft.Icons.CODE_ROUNDED, size=16, color=AppColors.PRIMARY
                ),
                controls=[
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    json_str,
                                    size=10,
                                    font_family="Courier New",
                                    color=AppColors.TERMINAL_GREEN,
                                    selectable=True,
                                )
                            ],
                            scroll=ft.ScrollMode.AUTO,
                        ),
                        bgcolor=AppColors.TERMINAL_BG,
                        border=ft.Border.all(
                            1,
                            ft.Colors.with_opacity(
                                tokens.OPACITY_LIGHT, ft.Colors.WHITE
                            ),
                        ),
                        border_radius=tokens.RADIUS_SM,
                        padding=tokens.SPACE_SM,
                        margin=ft.Margin(0, tokens.SPACE_XS, 0, tokens.SPACE_SM),
                        height=160,
                    )
                ],
            )
        )

    def _dismiss(e):
        page.pop_dialog()

    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text(
            "User Social Profile Dossier",
            size=tokens.FONT_MD,
            weight=ft.FontWeight.BOLD,
            font_family="Outfit",
            color=AppColors.PRIMARY,
        ),
        content=ft.Container(
            content=ft.Column(
                controls=[
                    header_row,
                    ft.Divider(
                        height=tokens.SPACE_MD,
                        color=ft.Colors.with_opacity(0.1, ft.Colors.OUTLINE),
                    ),
                    ft.Column(
                        controls=items
                        if items
                        else [
                            ft.Text(
                                "Profile found. Tap Open Profile to view on platform.",
                                size=tokens.FONT_SM,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                italic=True,
                            )
                        ],
                        spacing=tokens.SPACE_XS,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                ],
                tight=True,
                spacing=0,
            ),
            width=380,
        ),
        actions=[
            ft.TextButton(
                "Copy Profile Link",
                icon=ft.Icons.LINK_ROUNDED,
                on_click=lambda e: asyncio.create_task(
                    _copy_text(page, profile_url, "Profile link")
                ),
            ),
            ft.FilledButton(
                content=ft.Text(
                    "Open Profile", weight=ft.FontWeight.W_600, color=ft.Colors.WHITE
                ),
                icon=ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                on_click=lambda e: asyncio.create_task(_launch_profile_url()),
            ),
            ft.TextButton("Close", on_click=_dismiss),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)


def show_profile_detail_dialog(
    page: ft.Page,
    site_name: str,
    status: str,
    mode: str = "username",
    target_query: str | None = None,
    url_user: str | None = None,
    url_main: str | None = None,
    query_time: float | None = None,
    email_recovery: str | None = None,
    phone_number: str | None = None,
    others: dict | None = None,
    method: str | None = None,
    rate_limit: bool = False,
    frequent_rate_limit: bool = False,
    enrichment: dict | None = None,
) -> None:
    """Display rich intelligence modal tailored for Username or Email OSINT."""
    if not page:
        return
    others = others or {}
    enrichment = enrichment or {}
    try:
        if mode == "email":
            _email_dossier(
                page,
                site_name,
                status,
                target_query,
                url_main,
                query_time,
                email_recovery,
                phone_number,
                others,
                method,
                rate_limit,
                frequent_rate_limit,
            )
        else:
            _username_dossier(
                page,
                site_name,
                status,
                target_query,
                url_user,
                url_main,
                query_time,
                others,
                enrichment,
            )
    except Exception:
        # Never fail silently — a mid-build crash here leaves the tap doing
        # nothing on device. Log the full traceback and tell the user.
        logger.exception(
            "Dossier dialog failed to build (mode=%s, site=%s)", mode, site_name
        )
        from core.notify import show_snack

        show_snack(
            page,
            "Couldn't open details. The error was logged.",
            bgcolor=AppColors.ERROR,
        )
