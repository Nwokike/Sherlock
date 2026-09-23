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
from core.geo_utils import get_site_country, resolve_location
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
    elif status == "Unavailable":
        return ft.Icons.HIDE_SOURCE_ROUNDED, ft.Colors.with_opacity(
            tokens.OPACITY_MUTED, ft.Colors.ON_SURFACE
        )
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
    tags: list[str] | tuple[str, ...] | None = None,
    # Typed maigret error + protection metadata (badge bridge)
    error_type: str | None = None,
    error_hint: str = "",
    protection: list[str] | tuple[str, ...] | None = None,
    badge: str = "",
    keyword_hit: bool = False,
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
    # Avatar sources: socid enrichment (username mode) or holehe-v2
    # Result.media (email mode) — resolved before either block runs.
    avatar_url: str | None = None

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

    # Full name, creation date & holehe-v2 extras from others dict
    if others and isinstance(others, dict):
        # v2 streams profile media in-band (avatar producers: gravatar,
        # github, etsy, duolingo).
        v2_media = others.get("media") or {}
        v2_avatar = v2_media.get("avatar") or v2_media.get("thumbnail_url")
        if isinstance(v2_avatar, str) and v2_avatar.startswith("http"):
            avatar_url = avatar_url or v2_avatar
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

        # holehe-v2 Result.extra — rich per-platform facts (gravatar bio,
        # github login, etsy stats, atlassian SSO type, …) rendered as
        # scannable lines; capped so one card can't flood the list.
        v2_extra = others.get("extra") or {}
        _V2_SKIP = {
            "profile_url",
            "url",
            "contact_info",
            "crypto_addresses",
            "timezone",
            "languages",
            "pronouns",
        }
        v2_shown = 0
        for k, v in v2_extra.items():
            if k in _V2_SKIP or v in (None, "", [], {}):
                continue
            if isinstance(v, (list, tuple)):
                v2_text = f"{len(v)} linked"
            elif isinstance(v, dict):
                continue
            else:
                v2_text = str(v)
            if len(v2_text) > 90:
                v2_text = v2_text[:87] + "…"
            extra_lines.append(
                ft.Text(
                    f"{k.replace('_', ' ').title()}: {v2_text}",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                )
            )
            v2_shown += 1
            if v2_shown >= 6:
                break

    # Enrichment data from socid-extractor
    if enrichment and isinstance(enrichment, dict):
        avatar_url = (
            enrichment.get("image")
            or enrichment.get("avatar")
            or enrichment.get("photo")
            or avatar_url
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
            geo = resolve_location(str(location))
            loc_display = (
                f"{geo.flag} {location}" if (geo and geo.flag) else str(location)
            )
            extra_lines.append(
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.LOCATION_ON_OUTLINED,
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            loc_display,
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

    # Typed error advice (maigret solution_of) + bot-wall protection notice
    if status in ("WAF", "Error") and (error_hint or protection):
        if error_hint:
            extra_lines.append(
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.INFO_OUTLINE_ROUNDED,
                            size=12,
                            color=AppColors.PRIMARY,
                        ),
                        ft.Text(
                            error_hint,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            italic=True,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            expand=True,
                        ),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                )
            )
        if protection:
            extra_lines.append(
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.SHIELD_ROUNDED,
                            size=12,
                            color=AppColors.WARNING,
                        ),
                        ft.Text(
                            "Protected: " + ", ".join(str(p) for p in protection),
                            size=tokens.FONT_XS,
                            color=AppColors.WARNING,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
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
        from services.cache_service import ensure_cached_avatar

        # NOTE: no background download here — this renders per card per
        # progress tick; spawning an httpx task per render was a task storm
        # contributing to the scan freeze. The cache is warmed by the
        # dossier dialog when the user opens details.
        leading_control = ft.Image(
            src=ensure_cached_avatar(avatar_url),
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

    site_geo = get_site_country(tuple(tags)) if tags else None
    if site_geo and site_geo.flag:
        name_row_controls.append(
            ft.Text(
                site_geo.flag,
                size=tokens.FONT_SM,
                tooltip=f"{site_geo.flag} {site_geo.name}",
            )
        )

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
    if keyword_hit:
        # maigret KeywordMatchStatus.KEYWORD_FOUND — the scanned page
        # contained one of the keywords= terms.
        name_row_controls.append(
            _chip(
                "KEYWORD",
                AppColors.PRIMARY,
                ft.Colors.with_opacity(0.1, AppColors.PRIMARY),
            )
        )

    # Typed-error chip shown beside the status chip on failed checks
    # (e.g. "BOT PROTECTION", "CONNECTING FAILURE").
    error_chip: ft.Container | None = None
    if status in ("WAF", "Error") and error_type:
        err_label = str(error_type).upper()
        if len(err_label) > 18:
            err_label = err_label[:17] + "…"
        if badge in ("bot", "rate"):
            err_chip_color: str = AppColors.WARNING
        elif badge == "dead":
            err_chip_color = ft.Colors.with_opacity(
                tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
            )
        else:
            err_chip_color = ft.Colors.ON_SURFACE_VARIANT
        error_chip = _chip(
            err_label,
            err_chip_color,
            ft.Colors.with_opacity(tokens.OPACITY_LIGHT, err_chip_color),
        )

    detail_column = ft.Column(
        controls=[
            ft.Row(
                controls=name_row_controls,
                spacing=tokens.SPACE_SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Text(
                display_url,
                size=tokens.FONT_XS,
                color=ft.Colors.with_opacity(tokens.OPACITY_DIM, ft.Colors.ON_SURFACE),
                no_wrap=False,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
            *extra_lines,
        ],
        spacing=tokens.SPACE_XXS,
        expand=True,
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
                *([error_chip] if error_chip is not None else []),
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
