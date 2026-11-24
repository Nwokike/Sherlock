"""Help & shortcuts — the in-app help surface the Settings row opens.

flet 1.1.2 has no `show_license_page`/`show_bottom_sheet`, so this is a plain
AlertDialog shown through `page.show_dialog`, matching the existing Live
Activity Terminal pattern in Settings.
"""

from __future__ import annotations

import flet as ft

from core import tokens
from core.format import email_total_label, sites_total_label


def _section(icon: ft.IconData, title: str, body: str) -> ft.Control:
    return ft.Row(
        controls=[
            ft.Icon(icon, size=tokens.ICON_SM, color=ft.Colors.PRIMARY),
            ft.Column(
                controls=[
                    ft.Text(title, size=tokens.FONT_SM, weight=ft.FontWeight.W_600),
                    ft.Text(
                        body,
                        size=tokens.FONT_XS,
                        color=ft.Colors.with_opacity(
                            tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                        ),
                    ),
                ],
                spacing=2,
                expand=True,
            ),
        ],
        spacing=tokens.SPACE_MD,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def build_help_dialog(page: ft.Page) -> ft.AlertDialog:
    """Compose the help dialog (caller shows it with page.show_dialog)."""
    email_scope = email_total_label() or "every platform"
    body = ft.Column(
        controls=[
            _section(
                ft.Icons.PERSON_SEARCH_ROUNDED,
                "Username search",
                f"Type a handle and Sherlock checks up to {sites_total_label()} "
                "networks at once. Scope and depth live in Settings → Scan "
                "Parameters.",
            ),
            ft.Divider(height=tokens.SPACE_MD, color=ft.Colors.TRANSPARENT),
            _section(
                ft.Icons.ALTERNATE_EMAIL_ROUNDED,
                "Email search",
                f"Paste an address to see where it is registered across "
                f"{email_scope} platforms, plus recovery hints and leaked data.",
            ),
            ft.Divider(height=tokens.SPACE_MD, color=ft.Colors.TRANSPARENT),
            _section(
                ft.Icons.NOTIFICATIONS_ACTIVE_ROUNDED,
                "Progress and cancel",
                "A scan keeps running in the OS shade with live progress and a "
                "Cancel action, so you can leave the app. The tiny header pill "
                "jumps back to Results.",
            ),
            ft.Divider(height=tokens.SPACE_MD, color=ft.Colors.TRANSPARENT),
            _section(
                ft.Icons.DOWNLOAD_ROUNDED,
                "Exports",
                "Results export as PDF dossiers, XMind mind maps, CSV/JSON and "
                "plain text.",
            ),
            ft.Divider(height=tokens.SPACE_MD, color=ft.Colors.TRANSPARENT),
            _section(
                ft.Icons.SHIELD_ROUNDED,
                "Privacy",
                "Searches run on your device. See Settings → Privacy policy for "
                "the full policy.",
            ),
        ],
        spacing=tokens.SPACE_SM,
        scroll=ft.ScrollMode.AUTO,
        width=tokens.DIALOG_WIDTH_LG,
    )
    return ft.AlertDialog(
        modal=False,
        title=ft.Row(
            controls=[
                ft.Icon(ft.Icons.HELP_OUTLINE_ROUNDED, color=ft.Colors.PRIMARY),
                ft.Text(
                    "Help & shortcuts",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        content=ft.Container(content=body, width=tokens.DIALOG_WIDTH_LG),
        actions=[ft.TextButton("Close", on_click=lambda e: page.pop_dialog())],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def show_help_dialog(page: ft.Page) -> None:
    page.show_dialog(build_help_dialog(page))
