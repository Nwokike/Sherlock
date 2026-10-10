"""Regression tests for the owner's field report (v2.3.1).

Three device bugs, each reproduced from the owner's terminal log:

1. **Re-attach deadlock** — after a cancel, `state.is_searching` stayed True
   (the Results retry button set it optimistically) so every later search hit
   the smart re-attach path and returned without scanning. The app sat at 99%
   forever. The gate now requires a genuinely live progress object, and the
   retry button no longer sets the flag.
2. **Back button closes the app from any screen** — the app had exactly one
   view, and flet's Dart `_handleSystemPopRoute` bails out when the top view
   is the only one (`views.length <= 1`), so the framework popped the route
   itself and `on_view_pop` never fired. A `/blank` underlay restores the
   pop delivery, and the navigation logic (already present) runs.
3. **Networks screen could not scroll vertically** — flet 1.0.4 ignores
   `expand` on Column children (no control sets `host_expanded`, verified
   against the installed Dart-side wrapper), so the ListView got unbounded
   height, shrink-wrapped to all 5,200 rows, and the enclosing Column (no
   `scroll=`) never scrolled. The list is now the screen root.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

# ── 1. Re-attach deadlock ────────────────────────────────────────────────


def test_stuck_is_searching_does_not_swallow_search():
    """A scan that was killed must not re-attach: a fresh one must start.

    This is the exact log sequence: search -> cancel -> search -> the second
    search printed "Re-attaching" and never scanned.
    """
    from core.constants import MODE_USERNAME
    from core.state import state
    from main import AppController

    controller = AppController(MagicMock())
    controller.sherlock_service = MagicMock()
    controller.sherlock_service.load_sites = AsyncMock()
    started = []

    async def _search(**kwargs):
        started.append(kwargs.get("username"))
        if len(started) == 1:
            # the first scan is cancelled by the user mid-flight
            raise asyncio.CancelledError
        # the second one is the search under test — it must actually run
        return MagicMock(is_cancelled=True)

    controller.sherlock_service.search = _search
    controller._controller_methods = MagicMock()
    controller._controller_methods.show_results = lambda: None

    state.history = []
    state.is_searching = False
    state.current_username = "aham_bu_onyeka"
    state.search_mode = MODE_USERNAME
    state.search_progress = None

    async def run():
        # First scan: the engine raises CancelledError (the user's cancel),
        # which start_search re-raises after clearing the flag.
        await asyncio.gather(
            controller.start_search("aham_bu_onyeka"),
            return_exceptions=True,
        )
        # Simulate the stale flag left behind by the old retry path: no live
        # progress object, but is_searching stuck True.
        state.is_searching = True
        state.search_progress = None
        state.search_targets = []
        state.target_results = {}
        await controller.start_search("aham_bu_onyeka")

    asyncio.run(run())
    # Two real engine invocations: the second search must NOT have been
    # swallowed by the re-attach path.
    assert started == ["aham_bu_onyeka", "aham_bu_onyeka"], started


def test_live_scan_still_reattaches():
    """The smart re-attach must still work for a genuinely live scan."""
    from core.constants import MODE_USERNAME
    from core.state import state
    from main import AppController
    from services.sherlock_service import SearchProgress

    controller = AppController(MagicMock())
    controller.sherlock_service = MagicMock()
    controller.sherlock_service.search = AsyncMock(
        side_effect=AssertionError("must not run a new engine pass")
    )
    controller._controller_methods = MagicMock()
    controller._controller_methods.show_results = lambda: None

    prog = SearchProgress(username="alice", total_sites=5203, is_running=True)
    state.is_searching = True
    state.current_username = "alice"
    state.search_mode = MODE_USERNAME
    state.search_progress = prog

    asyncio.run(controller.start_search("alice"))
    assert controller.sherlock_service.search.await_count == 0  # re-attached


# ── 2. Back button ────────────────────────────────────────────────────────


def test_back_underlay_installed():
    """The app needs 2+ views or Android's pop never reaches on_view_pop.

    `on_view_pop` is flet's only hook for the Android back button, and its
    Dart implementation bails out when the top view is the only one
    (`_handleSystemPopRoute`: `views.length <= 1`) — the framework pops the
    route itself and the activity finishes. So the shell must sit on a blank
    underlay.
    """
    import flet as ft

    from main import AppController

    shell = ft.View(route="/")
    page = MagicMock()
    page.views = [shell]
    controller = AppController(page)
    controller._install_back_underlay()
    assert len(page.views) == 2
    assert page.views[0].route == "/blank"

    # idempotent: a second install must not stack another underlay
    controller._install_back_underlay()
    assert len(page.views) == 2

    # it never runs before the shell exists (the root shell view is created
    # by page.render during init)
    empty = MagicMock()
    empty.views = []
    AppController(empty)._install_back_underlay()
    assert empty.views == []


# ── 3. Networks screen layout ─────────────────────────────────────────────


def test_sites_screen_list_owns_the_scroll():
    """The root must be the ListView, not a Column wrapping it.

    A Column root gives the list unbounded height (flet ignores `expand` on
    column children) and never scrolls — the screen clips and cannot be
    scrolled at all.
    """
    from flet.components.component import Component, Renderer

    from core.state import state
    from screens.sites_screen import _ROW_HEIGHT, SitesScreen
    from state.app_state import AppStateCtx
    from state.controller_ctx import ControllerMethods, ControllerMethodsCtx

    state.sites_cache = [f"Site{i:02d}" for i in range(30)]
    state.sites_tags_map = {"coding": ["Site00"]}
    state.sites_tag_index = {"coding": ["Site00"]}
    state.sites_total = 30
    state.selected_sites = []
    state.sites_version += 1

    methods = ControllerMethods()
    renderer = Renderer()
    root = renderer.render(
        lambda: ControllerMethodsCtx(methods, lambda: AppStateCtx(state, SitesScreen))
    )

    def expand(node, out):
        out.append(node)
        if isinstance(node, Component):
            node.before_update()
            if getattr(node, "_b", None) is not None:
                expand(node._b, out)
        elif isinstance(node, list):
            for item in node:
                expand(item, out)
        else:
            for ch in getattr(node, "controls", None) or []:
                expand(ch, out)
            content = getattr(node, "content", None)
            if content is not None and not isinstance(content, str):
                expand(content, out)

    nodes = []
    expand(root, nodes)
    lists = [c for c in nodes if type(c).__name__ == "ListView"]
    assert lists, "no ListView rendered"
    kids = lists[0].controls
    # header rides inside the list (first controls), rows follow
    assert len(kids) > 4
    assert list_item_is_a_site_row(kids[4])
    assert _ROW_HEIGHT == 56.0


def list_item_is_a_site_row(control) -> bool:
    """A site row is a height-56 Container with a Checkbox inside."""
    if type(control).__name__ != "Container":
        return False
    return getattr(control, "height", None) == 56.0


def test_sites_banners_every_ten_rows():
    from flet.components.component import Component, Renderer

    from components.banner_ad import _BANNER_POOL
    from core.state import state
    from screens.sites_screen import SitesScreen
    from state.app_state import AppStateCtx
    from state.controller_ctx import ControllerMethods, ControllerMethodsCtx

    _BANNER_POOL.clear()
    state.sites_cache = [f"Site{i:02d}" for i in range(35)]
    state.sites_tags_map = {"coding": ["Site00"]}
    state.sites_tag_index = {"coding": ["Site00"]}
    state.sites_total = 35
    state.selected_sites = []
    state.sites_version += 1

    methods = ControllerMethods()
    renderer = Renderer()
    root = renderer.render(
        lambda: ControllerMethodsCtx(methods, lambda: AppStateCtx(state, SitesScreen))
    )

    def expand(node, out):
        out.append(node)
        if isinstance(node, Component):
            node.before_update()
            if getattr(node, "_b", None) is not None:
                expand(node._b, out)
        elif isinstance(node, list):
            for item in node:
                expand(item, out)
        else:
            for ch in getattr(node, "controls", None) or []:
                expand(ch, out)
            content = getattr(node, "content", None)
            if content is not None and not isinstance(content, str):
                expand(content, out)

    nodes = []
    expand(root, nodes)
    kids = next(c for c in nodes if type(c).__name__ == "ListView").controls
    banner_ids = {id(v) for v in _BANNER_POOL.values()}
    positions = [i for i, k in enumerate(kids) if id(k) in banner_ids]
    # 4 header controls, then a banner after every 10th row.
    gaps = [positions[i + 1] - positions[i] - 1 for i in range(len(positions) - 1)]
    assert gaps and all(g == 10 for g in gaps), (positions, gaps)
    assert len(positions) <= 15
