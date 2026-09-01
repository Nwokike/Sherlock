"""ResultCard — single result row for both username and email OSINT results.

Supports rich profile previews:
- Avatar image (from socid-extractor) or stylized status icon
- Display name & platform label
- Profile bio / description snippet
- Follower count, location, recovery email & phone hints
- Method badge (register / login / password recovery)
- Tapping opens the ProfileDetailDialog for complete OSINT inspection
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft
from flet import Control

from core import tokens
from core.theme import AppColors


def _status_icon_and_color(status: str) -> tuple[str, str]:
    """Map a Sherlock status string to (icon, color)."""
    if status == "Claimed":
        return ft.Icons.CHECK_CIRCLE_ROUNDED, AppColors.SUCCESS
    elif status in ("Available", "Illegal"):
        return ft.Icons.CANCEL_ROUNDED, ft.Colors.with_opacity(
            tokens.OPACITY_MUTED, ft.Colors.ON_SURFACE
        )
    elif status == "WAF":
        return ft.Icons.SHIELD_ROUNDED, AppColors.WARNING
    else:
        return ft.Icons.ERROR_OUTLINE_ROUNDED, AppColors.WARNING


def _chip(label: str, color: str, bg: str) -> ft.Container:
    return ft.Container(
        content=ft.Text(
            label,
            size=tokens.FONT_XS,
            weight=ft.FontWeight.W_700,
            color=color,
        ),
        padding=ft.Padding(
            tokens.SPACE_SM, tokens.SPACE_XS, tokens.SPACE_SM, tokens.SPACE_XS
        ),
        border_radius=tokens.RADIUS_SM,
        bgcolor=bg,
    )


def ResultCard(
    site_name: str,
    status: str,
    url_user: str | None = None,
    url_main: str | None = None,
    query_time: float | None = None,
    on_open: Callable[[str], None] | None = None,
    on_tap: Callable[[], None] | None = None,
    # Email-mode extras (holehe fields)
    email_recovery: str | None = None,
    phone_number: str | None = None,
    others: dict | None = None,
    method: str | None = None,
    rate_limit: bool = False,
    frequent_rate_limit: bool = False,
    # Enrichment extras (socid-extractor fields)
    enrichment: dict | None = None,
) -> Control:
    """Build a single result tile for the results tabs."""
    icon, icon_color = _status_icon_and_color(status)

    # ── Status chip ────────────────────────────────────────────────────
    chip_label = "WAF BLOCKED" if status == "WAF" else status
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
        else (
            ft.Colors.with_opacity(tokens.OPACITY_LIGHT, AppColors.WARNING)
            if status in ("WAF", "Error")
            else ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE)
        )
    )

    display_url = url_user or url_main or site_name

    def _handle_click(e):
        if on_tap:
            on_tap()
        elif on_open and url_user:
            on_open(url_user)

    # ── Extras / Enriched lines ────────────────────────────────────────
    extra_lines: list[ft.Control] = []

    # Recovery email hint
    if email_recovery:
        extra_lines.append(
            ft.Row(
                [
                    ft.Icon(
                        ft.Icons.MAIL_OUTLINE_ROUNDED, size=12, color=AppColors.PRIMARY
                    ),
                    ft.Text(
                        email_recovery,
                        size=tokens.FONT_XS,
                        color=AppColors.PRIMARY,
                        italic=True,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                    ),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    # Phone number hint
    if phone_number:
        extra_lines.append(
            ft.Row(
                [
                    ft.Icon(ft.Icons.PHONE_OUTLINED, size=12, color=AppColors.PRIMARY),
                    ft.Text(
                        phone_number,
                        size=tokens.FONT_XS,
                        color=AppColors.PRIMARY,
                        italic=True,
                    ),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    # Full name & creation date from others dict
    if others and isinstance(others, dict):
        if others.get("FullName"):
            extra_lines.append(
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.PERSON_OUTLINE_ROUNDED,
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            others["FullName"],
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            expand=True,
                        ),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        if others.get("Date, time of the creation"):
            extra_lines.append(
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.CALENDAR_TODAY_ROUNDED,
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            f"Created: {others['Date, time of the creation']}",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

    # Enrichment data from socid-extractor
    avatar_url = None
    if enrichment and isinstance(enrichment, dict):
        avatar_url = (
            enrichment.get("image")
            or enrichment.get("avatar")
            or enrichment.get("photo")
        )
        bio = enrichment.get("bio") or enrichment.get("description")
        if bio:
            extra_lines.append(
                ft.Text(
                    bio,
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    italic=True,
                )
            )
        location = enrichment.get("location")
        if location:
            extra_lines.append(
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.LOCATION_ON_OUTLINED,
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            location,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        followers = enrichment.get("follower_count") or enrichment.get("followers")
        following = enrichment.get("following_count") or enrichment.get("following")
        if followers is not None or following is not None:
            parts = []
            if followers is not None:
                parts.append(f"{followers} followers")
            if following is not None:
                parts.append(f"{following} following")
            extra_lines.append(
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.PEOPLE_OUTLINE_ROUNDED,
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            " · ".join(parts),
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        # Extra socid fields — company, verified, links, website
        company = enrichment.get("company") or enrichment.get("occupation")
        if company:
            extra_lines.append(
                ft.Text(
                    str(company),
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                )
            )
        if enrichment.get("is_verified"):
            extra_lines.append(
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.VERIFIED_ROUNDED, size=12, color=ft.Colors.BLUE
                        ),
                        ft.Text(
                            "Verified",
                            size=tokens.FONT_XS,
                            color=ft.Colors.BLUE,
                            weight=ft.FontWeight.W_600,
                        ),
                    ],
                    spacing=4,
                )
            )
        links = enrichment.get("links")
        if links and isinstance(links, list) and links[0]:
            first_link = links[0] if isinstance(links[0], str) else str(links[0])
            if first_link.startswith("http"):
                extra_lines.append(
                    ft.Text(
                        first_link,
                        size=tokens.FONT_XS,
                        color=AppColors.PRIMARY,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    )
                )

    # Frequently rate-limited notice
    if rate_limit and frequent_rate_limit:
        extra_lines.append(
            ft.Text(
                "⚡ Frequently rate limited — result may be unreliable",
                size=tokens.FONT_XS,
                color=AppColors.WARNING,
                italic=True,
            )
        )

    # Method badge for email mode
    method_badge = None
    if method:
        method_color = (
            AppColors.PRIMARY
            if method == "register"
            else AppColors.WARNING
            if method == "password recovery"
            else ft.Colors.ON_SURFACE_VARIANT
        )
        method_badge = ft.Container(
            content=ft.Text(
                method, size=9, color=method_color, weight=ft.FontWeight.W_600
            ),
            padding=ft.Padding(6, 2, 6, 2),
            border_radius=tokens.RADIUS_SM,
            bgcolor=ft.Colors.with_opacity(0.1, method_color),
        )

    # ── Avatar / Leading Icon ─────────────────────────────────────────
    # Guard against relative/non-http avatar URLs from socid-extractor.
    has_valid_avatar = bool(
        avatar_url and isinstance(avatar_url, str) and avatar_url.startswith("http")
    )
    if has_valid_avatar:
        leading_control = ft.Image(
            src=avatar_url,
            width=36,
            height=36,
            border_radius=18,
            fit=ft.BoxFit.COVER,
            error_content=ft.Container(
                content=ft.Icon(icon, size=tokens.RESULT_ICON, color=icon_color),
                width=36,
                height=36,
                border_radius=18,
                bgcolor=ft.Colors.with_opacity(tokens.OPACITY_LIGHT, icon_color),
                alignment=ft.Alignment.CENTER,
            ),
        )
    else:
        leading_control = ft.Container(
            content=ft.Icon(icon, size=tokens.RESULT_ICON, color=icon_color),
            width=36,
            height=36,
            border_radius=18,
            bgcolor=ft.Colors.with_opacity(tokens.OPACITY_LIGHT, icon_color),
            alignment=ft.Alignment.CENTER,
        )

    # ── Title / Name row ──────────────────────────────────────────────
    display_title = site_name
    if enrichment and (enrichment.get("name") or enrichment.get("fullname")):
        display_title = (
            f"{site_name} · {enrichment.get('name') or enrichment.get('fullname')}"
        )
    elif others and others.get("FullName"):
        display_title = f"{site_name} · {others['FullName']}"

    name_row_controls: list[ft.Control] = [
        ft.Text(
            display_title,
            size=tokens.FONT_MD,
            weight=ft.FontWeight.W_600,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            expand=True,
        ),
    ]
    if query_time is not None:
        name_row_controls.append(
            ft.Text(
                f"({query_time:.2f}s)",
                size=tokens.FONT_XS,
                color=ft.Colors.with_opacity(
                    tokens.OPACITY_MUTED, ft.Colors.ON_SURFACE
                ),
            )
        )
    if method_badge:
        name_row_controls.append(method_badge)

    detail_column = ft.SelectionArea(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=name_row_controls,
                    spacing=tokens.SPACE_SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(
                    display_url,
                    size=tokens.FONT_XS,
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                    ),
                    no_wrap=False,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                *extra_lines,
            ],
            spacing=tokens.SPACE_XXS,
            expand=True,
        ),
    )

    is_clickable = (
        on_tap is not None
        or on_open is not None
        or url_user is not None
        or url_main is not None
    )

    return ft.Container(
        content=ft.Row(
            controls=[
                leading_control,
                detail_column,
                _chip(chip_label, chip_color, chip_bg),
            ],
            spacing=tokens.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=12,
            bottom=12,
        ),
        border=ft.Border.only(
            bottom=ft.BorderSide(
                width=0.5,
                color=ft.Colors.with_opacity(
                    tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE
                ),
            )
        ),
        on_click=_handle_click if is_clickable else None,
        ink=True if is_clickable else False,
    )
