"""Snackbar helper — the working Flet 1.0.1 way to surface messages.

``page.show_dialog(...)`` is the supported path (verified against the installed
flet 1.0.1: ``SnackBar`` is a ``DialogControl``; there is no ``page.open``).
This helper wraps that with the one edge case that matters: showing a second
snack while the first is still open raises RuntimeError ("Dialog is already
opened") — in that case replace the lingering snack, but never close a real
(non-snack) dialog.
"""

import logging

import flet as ft

logger = logging.getLogger(__name__)


def show_snack(
    page: ft.Page,
    message: str,
    bgcolor: str | None = None,
    duration: int = 4000,
    action_label: str | None = None,
    on_action=None,
) -> None:
    """Best-effort snackbar: logs failures, never raises."""
    try:
        action = None
        if action_label:
            action = ft.SnackBarAction(action_label, on_click=on_action)
        snack = ft.SnackBar(
            content=ft.Text(message, color=ft.Colors.WHITE),
            bgcolor=bgcolor or ft.Colors.BLACK,
            # DurationValue accepts int ms, but be explicit — version-proof.
            duration=ft.Duration(milliseconds=duration),
            action=action,
        )
        try:
            page.show_dialog(snack)
        except RuntimeError:
            popped = page.pop_dialog()
            # Only re-show when nothing (or another snack) was on top: never
            # dismiss a real AlertDialog just to deliver a snackbar.
            if popped is None or isinstance(popped, ft.SnackBar):
                page.show_dialog(snack)
            else:
                logger.debug(
                    "show_snack skipped: top dialog is %s, not a SnackBar",
                    type(popped).__name__,
                )
    except Exception as ex:
        logger.warning("show_snack failed: %s", ex)
