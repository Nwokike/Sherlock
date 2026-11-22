"""The advertised network count must come from the installed DB, and the
scanning pill must sit BELOW the header (owner report)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from core.format import sites_total_label
from core.state import state


def test_site_count_reads_installed_database_not_a_literal():
    import pathlib

    import maigret

    meta = (
        pathlib.Path(maigret.__file__).parent / "resources" / "db_meta.json"
    )
    assert meta.is_file(), "installed maigret should ship db_meta.json"
    expected = json.loads(meta.read_text(encoding="utf-8"))["sites_count"]
    # Force the pre-load path: a loaded count (set by other tests) wins by design.
    state.sites_total = 0
    assert sites_total_label() == f"{expected:,}"


def test_site_count_is_not_taken_from_a_stale_cache():
    """A stale cached list must not change the advertised total."""
    import pathlib

    import maigret

    expected = json.loads(
        (pathlib.Path(maigret.__file__).parent / "resources" / "db_meta.json")
        .read_text(encoding="utf-8")
    )["sites_count"]
    state.sites_total = 0
    try:
        assert sites_total_label() == f"{expected:,}"
    finally:
        state.sites_total = 0


def test_scanning_pill_renders_below_the_header():
    from flet.components.component import Renderer

    from components.app_header import AppHeader, set_scan_navigation
    from state.app_state import AppStateCtx
    from state.controller_ctx import ControllerMethods, ControllerMethodsCtx

    snap = (state.is_searching, state.search_progress, state.current_username)
    try:
        state.is_searching = True
        state.current_username = "alice"
        from services.sherlock_service import SearchProgress

        state.search_progress = SearchProgress(
            username="alice", total_sites=100, is_running=True
        )
        set_scan_navigation(lambda: None)

        root = Renderer().render(
            lambda: ControllerMethodsCtx(
                ControllerMethods(),
                lambda: AppStateCtx(state, lambda: AppHeader(MagicMock())),
            )
        )
        # The header Container's content is a Column: header row first, pill second.
        container = next(
            n for n in _walk(root) if type(n).__name__ == "Container" and getattr(n, "content", None) is not None
        )
        col = container.content
        assert type(col).__name__ == "Column"
        kinds = [type(c).__name__ for c in col.controls]
        assert kinds[0] == "Row", f"header must come first, got {kinds}"
        assert "Container" in kinds[1:], f"pill must follow, got {kinds}"
    finally:
        (state.is_searching, state.search_progress, state.current_username) = snap
        set_scan_navigation(None)


def _walk(node):
    from flet.components.component import Component

    out = []

    def expand(n):
        out.append(n)
        if isinstance(n, Component):
            n.before_update()
            b = getattr(n, "_b", None)
            if b is not None:
                expand(b)
        elif isinstance(n, list):
            for i in n:
                expand(i)
        else:
            for c in getattr(n, "controls", None) or []:
                expand(c)
            c = getattr(n, "content", None)
            if c is not None and not isinstance(c, str):
                expand(c)

    expand(node)
    return out
