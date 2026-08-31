"""ProfileDetailDialog — rich modal for inspecting OSINT result profiles.

Displays all extracted intelligence from Sherlock, holehe, and socid-extractor:
- Profile Avatar & Display Name / Username
- Bio / Description
- Platform verification / status chip
- Location, User ID (UID), Joined Date
- Follower, Following, and Post metrics
- Masked Recovery Email & Phone hints (with copy buttons)
- Leaked social links & websites
- Direct 'Open in Browser' and 'Copy URL' actions
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft

from core import tokens
from core.constants import ERR_OPEN_URL
from core.theme import AppColors

logger = logging.getLogger("ProfileDetailDialog")


def show_profile_detail_dialog(
    page: ft.Page,
    site_name: str,
    status: str,
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
    """Display rich profile intelligence modal."""
    if not page:
        return

    enrich = enrichment or {}
    other_data = others or {}

    avatar_url = enrich.get("image") or enrich.get("avatar") or enrich.get("photo")
    display_name = (
        enrich.get("name")
        or enrich.get("fullname")
        or other_data.get("FullName")
        or site_name
    )
    bio = enrich.get("bio") or enrich.get("description")
    location = enrich.get("location")
    uid = enrich.get("uid") or enrich.get("id")
    followers = enrich.get("follower_count") or enrich.get("followers")
    following = enrich.get("following_count") or enrich.get("following")
    posts = enrich.get("posts_count") or enrich.get("posts")
    join_date = (
        other_data.get("Date, time of the creation")
        or enrich.get("joined")
        or enrich.get("created_at")
    )
    extracted_email = enrich.get("email") or email_recovery
    extracted_phone = enrich.get("phone") or phone_number
    links = enrich.get("links") or enrich.get("url")

    target_url = (
        url_user
        or url_main
        or (
            f"https://{site_name.lower()}.com"
            if "." not in site_name
            else f"https://{site_name}"
        )
    )

    async def _launch_url():
        page.pop_dialog()
        try:
            await ft.UrlLauncher().launch_url(target_url)
        except Exception as exc:
            logger.warning("Failed to launch URL %s: %s", target_url, exc)
            from core.notify import show_snack

            show_snack(page, ERR_OPEN_URL, bgcolor=AppColors.ERROR)

    async def _copy_text(text: str, label: str):
        try:
            cb = ft.Clipboard()
            await cb.set(text)
            from core.notify import show_snack

            show_snack(page, f"{label} copied to clipboard", bgcolor=AppColors.SUCCESS)
        except Exception as exc:
            logger.warning("Copy failed: %s", exc)

    def _dismiss(e):
        page.pop_dialog()

    # --- Header Icon / Avatar ---
    if avatar_url:
        avatar_control = ft.Image(
            src=avatar_url,
            width=56,
            height=56,
            border_radius=28,
            fit=ft.BoxFit.COVER,
            error_content=ft.Container(
                content=ft.Icon(
                    ft.Icons.PERSON_ROUNDED,
                    size=28,
                    color=AppColors.PRIMARY,
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

    # --- Header Title & Status ---
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
                        target_url,
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

    # --- Intelligence Items ---
    info_items: list[ft.Control] = []

    # Bio Card
    if bio:
        info_items.append(
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

    # Metrics row (Followers, Following, Posts)
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
        info_items.append(
            ft.Container(
                content=ft.Row(
                    metric_cols,
                    alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                ),
                padding=tokens.SPACE_MD,
                border_radius=tokens.RADIUS_MD,
                bgcolor=ft.Colors.with_opacity(0.06, AppColors.PRIMARY),
                margin=ft.Margin(0, 0, 0, tokens.SPACE_SM),
            )
        )

    def _detail_row(
        icon: ft.IconData, title: str, value: str, can_copy: bool = False
    ) -> ft.Container:
        copy_btn = (
            ft.IconButton(
                icon=ft.Icons.CONTENT_COPY_ROUNDED,
                icon_size=16,
                tooltip=f"Copy {title}",
                on_click=lambda e: asyncio.create_task(_copy_text(value, title)),
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

    if location:
        info_items.append(
            _detail_row(ft.Icons.LOCATION_ON_OUTLINED, "Location", str(location))
        )
    if uid:
        info_items.append(
            _detail_row(
                ft.Icons.BADGE_OUTLINED, "Account UID / ID", str(uid), can_copy=True
            )
        )
    if extracted_email:
        info_items.append(
            _detail_row(
                ft.Icons.MAIL_OUTLINE_ROUNDED,
                "Recovery / Leaked Email",
                str(extracted_email),
                can_copy=True,
            )
        )
    if extracted_phone:
        info_items.append(
            _detail_row(
                ft.Icons.PHONE_OUTLINED,
                "Recovery Phone",
                str(extracted_phone),
                can_copy=True,
            )
        )
    if links:
        link_str = ", ".join(links) if isinstance(links, list) else str(links)
        info_items.append(
            _detail_row(
                ft.Icons.LINK_ROUNDED,
                "External Links / Websites",
                link_str,
                can_copy=True,
            )
        )
    if join_date:
        info_items.append(
            _detail_row(
                ft.Icons.CALENDAR_TODAY_ROUNDED,
                "Account Created / Joined",
                str(join_date),
            )
        )
    if method:
        info_items.append(
            _detail_row(
                ft.Icons.SECURITY_ROUNDED,
                "Detection Method",
                f"{method.capitalize()} Endpoint",
            )
        )
    if query_time:
        info_items.append(
            _detail_row(
                ft.Icons.TIMER_OUTLINED, "Response Time", f"{query_time:.2f} seconds"
            )
        )

    if frequent_rate_limit and rate_limit:
        info_items.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.WARNING_AMBER_ROUNDED,
                            color=AppColors.WARNING,
                            size=16,
                        ),
                        ft.Text(
                            "Frequently rate-limited endpoint — status may vary.",
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

    dlg = ft.AlertDialog(
        modal=False,
        content=ft.Container(
            content=ft.Column(
                controls=[
                    header_row,
                    ft.Divider(
                        height=tokens.SPACE_MD,
                        color=ft.Colors.with_opacity(0.1, ft.Colors.OUTLINE),
                    ),
                    ft.Column(
                        controls=info_items
                        if info_items
                        else [
                            ft.Text(
                                "No additional metadata found for this profile.",
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
                "Copy Link",
                icon=ft.Icons.LINK_ROUNDED,
                on_click=lambda e: asyncio.create_task(
                    _copy_text(target_url, "Profile link")
                ),
            ),
            ft.FilledButton(
                content=ft.Text(
                    "Open in Browser", weight=ft.FontWeight.W_600, color=ft.Colors.WHITE
                ),
                icon=ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                on_click=lambda e: asyncio.create_task(_launch_url()),
            ),
            ft.TextButton("Close", on_click=_dismiss),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dlg)
