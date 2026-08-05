"""AppState context — component-facing adapter over the observable state."""

import flet as ft

from core.state import state

AppStateCtx = ft.create_context(state)

__all__ = ["AppStateCtx", "state"]
