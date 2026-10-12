"""Regression tests for the owner's field report (v2.3.1).

Three device bugs, each reproduced from the owner's terminal log:

1. **Re-attach deadlock** — after a cancel, `state.is_searching` stayed True
   (the Results retry button set it optimistically) so every later search hit
   the smart re-attach path and returned without scanning. The app sat at 99%
   forever. The gate now requires a genuinely live progress object, and the
   retry button no longer sets the flag.
2. **Back button closed the app from any screen** — the app had exactly one
   view, and flet's Dart `_handleSystemPopRoute` bails out when the top view
   is the only one (`views.length <= 1`), so the framework finished the
   activity and no handler ran. Fixed with `View.can_pop=False` +
   `on_confirm_pop` (the will-pop hook): back navigates in-app and the view
   is kept. A `/blank` underlay was tried first and reverted — it blanked the
   app at startup (it became the render target when inserted before
   page.render) and left the blank view visible after back popped the shell.
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


def test_root_view_back_guard_installed():
    """Android back on a single-view app must not exit it.

    flet's Dart system-back handler bails when the top view is the only one
    (`_handleSystemPopRoute`: `views.length <= 1`) and the framework finishes
    the activity. `View.can_pop=False` + `on_confirm_pop` is the supported
    will-pop hook: back fires the handler and `confirm_pop(False)` keeps the
    view on the stack. No second view is introduced — an earlier attempt used
    a blank underlay, which both blanked the app on startup and left the
    blank view visible after back popped the shell.
    """
    import flet as ft

    from main import AppController

    shell = ft.View(route="/")
    page = MagicMock()
    page.views = [shell]
    controller = AppController(page)
    controller._guard_root_view_pop()

    # exactly one view still, and it is now un-poppable with a handler
    assert len(page.views) == 1
    assert page.views[0].can_pop is False
    handler = page.views[0].on_confirm_pop
    assert handler.__func__ is controller._on_root_confirm_pop.__func__
    assert handler.__self__ is controller

    # idempotent
    controller._guard_root_view_pop()
    assert len(page.views) == 1

    # harmless before the shell view exists
    empty = MagicMock()
    empty.views = []
    AppController(empty)._guard_root_view_pop()
    assert empty.views == []


def test_back_handler_never_pops_the_view():
    """The handler navigates in-app and always resolves with should_pop=False."""
    import asyncio

    import flet as ft

    from main import AppController

    shell = ft.View(route="/")
    page = MagicMock()
    page.views = [shell]
    controller = AppController(page)
    controller._guard_root_view_pop()

    navigated = []
    methods = MagicMock()
    methods.handle_system_back = lambda: navigated.append(1)
    controller._controller_methods = methods

    resolved = []

    async def _confirm_pop(should_pop):
        resolved.append(should_pop)

    shell.confirm_pop = _confirm_pop

    async def run():
        await controller._on_root_confirm_pop(type("E", (), {"control": shell})())

    asyncio.run(run())
    assert navigated == [1], "in-app navigation must run"
    assert resolved == [False], "the view must be kept"

    # even when navigation raises, the pop still resolves False (app survives)
    def _boom():
        raise RuntimeError("nav exploded")

    methods.handle_system_back = _boom
    resolved.clear()

    async def run2():
        await controller._on_root_confirm_pop(type("E", (), {"control": shell})())

    asyncio.run(run2())
    assert resolved == [False]


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
    """A site row is a height-56 Container with a Checkbox inside.

    Rows are `SiteRow` components, so a list child may be the Component
    wrapper rather than the built Container — accept either.
    """
    if type(control).__name__ == "Component":
        fn = getattr(control, "fn", None)
        return getattr(fn, "__name__", "") == "SiteRow"
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
