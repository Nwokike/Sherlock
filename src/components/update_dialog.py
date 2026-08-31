"""UpdateDialog — modal dialog for app updates and cross-promotion announcements.

Platform-aware:
- Android: Offers Google Play Store and Direct APK (GitHub Releases) options.
- Desktop / Other: Offers GitHub Releases download option.
- Announcement type: Offers direct action link for featured apps/news.
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft

from core import tokens
from core.constants import ERR_OPEN_URL
from core.theme import AppColors

logger = logging.getLogger("UpdateDialog")


def show_update_dialog(page: ft.Page, update_data: dict) -> None:
    """Display the update or announcement dialog."""
    if not page or not update_data:
        return

    is_mandatory = bool(update_data.get("mandatory", False))
    is_announcement = update_data.get("type") == "announcement"
    title_text = update_data.get(
        "title",
        "Announcement"
        if is_announcement
        else f"New Version {update_data.get('version', '')} Available! 🎉",
    )
    release_notes = update_data.get("release_notes", "")
    github_url = update_data.get("github_url", "")
    playstore_url = update_data.get("playstore_url", "")
    action_url = update_data.get("action_url") or github_url

    # Detect platform
    is_android = page.platform == ft.PagePlatform.ANDROID

    async def _launch(url: str):
        page.pop_dialog()
        try:
            await ft.UrlLauncher().launch_url(url)
        except Exception as exc:
            logger.warning("Failed to launch URL %s: %s", url, exc)
            from core.notify import show_snack

            show_snack(page, ERR_OPEN_URL, bgcolor=AppColors.ERROR)

    def _dismiss(e):
        page.pop_dialog()

    # Action buttons based on type and platform
    actions: list[ft.Control] = []

    if is_announcement:
        if action_url:
            actions.append(
                ft.FilledButton(
                    content=ft.Text(
                        "Learn More",
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.WHITE,
                    ),
                    icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                    on_click=lambda e: asyncio.create_task(_launch(action_url)),
                )
            )
    else:
        if is_android:
            # Android: Play Store + GitHub APK
            if playstore_url:
                actions.append(
                    ft.FilledButton(
                        content=ft.Text(
                            "Google Play",
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.WHITE,
                        ),
                        icon=ft.Icons.SHOP_ROUNDED,
                        on_click=lambda e: asyncio.create_task(_launch(playstore_url)),
                    )
                )
            if github_url:
                actions.append(
                    ft.OutlinedButton(
                        content=ft.Text(
                            "Direct APK (GitHub)",
                            weight=ft.FontWeight.W_600,
                        ),
                        icon=ft.Icons.DOWNLOAD_ROUNDED,
                        on_click=lambda e: asyncio.create_task(_launch(github_url)),
                    )
                )
        else:
            # Desktop / Other: GitHub Download
            if github_url:
                actions.append(
                    ft.FilledButton(
                        content=ft.Text(
                            "Download from GitHub",
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.WHITE,
                        ),
                        icon=ft.Icons.DOWNLOAD_ROUNDED,
                        on_click=lambda e: asyncio.create_task(_launch(github_url)),
                    )
                )

    if not is_mandatory:
        actions.append(
            ft.TextButton(
                "Later",
                on_click=_dismiss,
                style=ft.ButtonStyle(
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                    )
                ),
            )
        )

    # Content body
    content_controls: list[ft.Control] = []

    if not is_announcement and update_data.get("version"):
        content_controls.append(
            ft.Text(
                f"Version {update_data['version']} is now available.",
                size=tokens.FONT_SM,
                color=ft.Colors.ON_SURFACE,
                weight=ft.FontWeight.W_500,
            )
        )
        content_controls.append(ft.Container(height=tokens.SPACE_SM))

    if release_notes:
        if not is_announcement:
            content_controls.append(
                ft.Text(
                    "What's New:",
                    size=tokens.FONT_SM,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.PRIMARY,
                )
            )
            content_controls.append(ft.Container(height=tokens.SPACE_XS))
        content_controls.append(
            ft.Text(
                release_notes,
                size=tokens.FONT_SM,
                color=ft.Colors.with_opacity(tokens.OPACITY_DIM, ft.Colors.ON_SURFACE),
                selectable=True,
            )
        )

    icon_data = (
        ft.Icons.CAMPAIGN_ROUNDED if is_announcement else ft.Icons.ROCKET_LAUNCH_ROUNDED
    )
    icon_color = AppColors.ACCENT if is_announcement else AppColors.PRIMARY

    dlg = ft.AlertDialog(
        modal=is_mandatory,
        title=ft.Row(
            [
                ft.Icon(icon_data, color=icon_color, size=24),
                ft.Text(
                    title_text,
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.BOLD,
                    font_family="Outfit",
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=ft.Container(
            content=ft.Column(
                controls=content_controls,
                tight=True,
                spacing=0,
                scroll=ft.ScrollMode.AUTO,
            ),
            width=360,
        ),
        actions=actions,
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dlg)
