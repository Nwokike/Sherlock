"""Snackbar helper — the working Flet 0.85 way to surface messages.

`page.snack_bar` does not exist in Flet 0.85.0 (verified against the
installed package); the supported path is `page.show_dialog(...)`, and
SnackBar is a DialogControl. This helper wraps that with the one edge
case that matters: showing a second snack while the first is still open
raises RuntimeError ("Dialog is already opened") — in that case replace
the lingering snack, but never close a real (non-snack) dialog.
"""

import logging

import flet as ft

logger = logging.getLogger(__name__)


def show_snack(
    page: ft.Page,
    message: str,
    bgcolor: str | None = None,
    duration: int = 4000,
) -> None:
    """Best-effort snackbar: logs failures, never raises."""
    try:
        snack = ft.SnackBar(
            content=ft.Text(message, color=ft.Colors.WHITE),
            bgcolor=bgcolor or ft.Colors.BLACK,
            duration=duration,
        )
        try:
            page.show_dialog(snack)
        except RuntimeError:
            popped = page.pop_dialog()
            if popped is None or isinstance(popped, ft.SnackBar):
                page.show_dialog(snack)
    except Exception as ex:
        logger.warning("show_snack failed: %s", ex)
