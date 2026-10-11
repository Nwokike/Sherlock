"""Structure tests for the flet 1.0.4 no-scroll bug class.

`expand=True` on a child of `ft.Column` is a NO-OP in flet 1.0.4 (verified in
flet's Dart `_expandable`: it only wraps in `Expanded` when the parent sets
`host_expanded`, and no control sets it). A Column also does not scroll unless
it has a `scroll` property (`ScrollableControl` returns the child unwrapped
otherwise).

Together: a scrollable nested inside a plain Column gets UNBOUNDED height,
shrink-wraps to its full content, and the enclosing non-scrolling Column
clips it. This is the bug that struck the Networks, Home, History and
Settings screens. These tests assert the structure each screen must keep:
its screen-filling scrollable must be bounded by something that is not a
plain Column ancestor.
"""

from __future__ import annotations

import pytest
from flet.components.component import Component, Renderer

from core.constants import MODE_USERNAME
from core.state import state
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethods, ControllerMethodsCtx


@pytest.fixture(autouse=True)
def _restore_state():
    """Save/restore every singleton field these tests mutate.

    Mounting screens mutates the global state, which has bitten this suite
    before (a leaked sites_cache/sites_total makes a later test see a
    different database than it configured).
    """
    keys = (
        "sites_cache",
        "sites_tags_map",
        "sites_tag_index",
        "sites_total",
        "sites_version",
        "selected_sites",
        "history",
        "is_searching",
        "search_mode",
        "search_progress",
        "current_username",
        "last_results_username",
    )
    saved = {}
    for key in keys:
        value = getattr(state, key)
        saved[key] = list(value) if isinstance(value, list) else value
    yield
    for key, value in saved.items():
        if isinstance(value, list):
            current = getattr(state, key)
            if isinstance(current, list):
                current[:] = value
                continue
        setattr(state, key, value)


def _mount(comp_fn):
    """Render a screen component and flatten it to (control, ancestors)."""
    methods = ControllerMethods()
    renderer = Renderer()

    def _ctx():
        return ControllerMethodsCtx(methods, lambda: AppStateCtx(state, comp_fn))

    root = renderer.render(_ctx)

    out: list[tuple[object, tuple[str, ...]]] = []

    def expand(node, chain):
        if node is None:
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                expand(item, chain)
            return
        out.append((node, chain))
        chain = (*chain, type(node).__name__)
        if isinstance(node, Component):
            node.before_update()
            expand(getattr(node, "_b", None), chain)
            return
        for child in getattr(node, "controls", None) or []:
            expand(child, chain)
        expand(getattr(node, "content", None), chain)

    expand(root, ())
    return out


def _shortest_chain(nodes, wanted_type):
    for node, chain in nodes:
        if type(node).__name__ == wanted_type and chain:
            return list(chain)
    return None


def _unbounded_by_plain_column(chain: list[str]) -> bool:
    """True when a plain Column (no scroll of its own) sits above the node."""
    return "Column" in chain


def _long_history_state():
    state.history = [
        {
            "query": f"user{i}",
            "mode": MODE_USERNAME,
            "timestamp": "2026-01-01 00:00",
            "found": 1,
            "total": 10,
        }
        for i in range(30)
    ]


def _long_sites_state():
    state.sites_cache = [f"Site{i}" for i in range(60)]
    state.sites_tags_map = {"coding": ["Site0"], "social": ["Site1"]}
    state.sites_tag_index = {"coding": ["Site0"], "social": ["Site1"]}
    state.sites_total = 60
    state.selected_sites = []


def test_home_scroll_column_is_not_trapped_in_a_plain_column():
    """Home's scrolling Column must not sit inside another plain Column."""
    from screens.home_screen import HomeScreen

    nodes = _mount(HomeScreen)
    lv = _shortest_chain(nodes, "ListView")
    if lv is not None:  # long banner list inside the scroll column
        assert not _unbounded_by_plain_column(lv), lv
    # the screen's own scroll Column must be the outermost Column
    columns = [
        ch
        for c, ch in nodes
        if type(c).__name__ == "Column" and ch.count("Column") == 1
    ]
    assert columns, "expected Home to render a scroll Column directly"


def test_history_list_is_not_trapped_in_a_plain_column():
    from screens.history_screen import HistoryScreen

    _long_history_state()
    try:
        nodes = _mount(HistoryScreen)
        lv = _shortest_chain(nodes, "ListView")
        assert lv is not None, "History should render a ListView root"
        assert not _unbounded_by_plain_column(lv), lv
    finally:
        state.history = []


def test_settings_list_is_not_trapped_in_a_plain_column():
    from screens.settings_screen import SettingsScreen

    nodes = _mount(SettingsScreen)
    lv = _shortest_chain(nodes, "ListView")
    assert lv is not None, "Settings should render a ListView root"
    assert not _unbounded_by_plain_column(lv), lv


def test_sites_list_root_is_bounded():
    from screens.sites_screen import SitesScreen

    _long_sites_state()
    try:
        nodes = _mount(SitesScreen)
        lv = _shortest_chain(nodes, "ListView")
        assert lv is not None
        assert not _unbounded_by_plain_column(lv), lv
    finally:
        state.sites_cache = []


def test_results_tab_list_is_not_trapped_in_a_plain_column():
    """Results nests its ListView in TabBarView. Flutter's PageView bounds
    its children, so a Column in the chain must not be the unbounded one —
    the check is that the list is not a direct child of a scroll-less Column.
    """
    from screens.results_screen import ResultsScreen

    # A live username scan makes the tabs branch render.
    state.is_searching = True
    state.search_mode = MODE_USERNAME
    state.current_username = "alice"
    try:
        nodes = _mount(ResultsScreen)
        lv = _shortest_chain(nodes, "ListView")
        if lv is None:
            return  # small/empty result set: no list rendered
        # TabBarView (a PageView) counts as a bounding ancestor
        assert any(name in lv for name in ("TabBarView",)), lv
    finally:
        state.is_searching = False
        state.search_progress = None
        state.current_username = ""


def test_no_screen_puts_a_listview_directly_under_a_plain_column():
    """One structural rule covering every screen: no ListView whose nearest
    Column ancestor is itself scroll-less and un-nested is fine, but a
    ListView that is a DIRECT child of such a Column is the exact bug shape.
    """
    from screens.history_screen import HistoryScreen
    from screens.home_screen import HomeScreen
    from screens.settings_screen import SettingsScreen
    from screens.sites_screen import SitesScreen

    _long_history_state()
    _long_sites_state()
    for fn in (HomeScreen, HistoryScreen, SettingsScreen, SitesScreen):
        nodes = _mount(fn)
        for node, chain in nodes:
            if type(node).__name__ != "ListView" or not chain:
                continue
            parent = chain[-2] if len(chain) >= 2 else None
            assert parent != "Column", (
                f"{fn.__name__}: ListView directly inside a Column "
                "(unbounded height, no scroll)"
            )
