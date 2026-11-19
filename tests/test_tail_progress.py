"""The recursive-tail freeze — `_apply_progress` must admit every target.

Reported by the owner: "scan would get to the end, maybe 98% or 99% and
then get stuck. I thought we had addressed that, but I think it's coming
back." The old re-attach fix (`c9b86cf`) is intact; this is a different,
newer stall introduced by the 2.3.0 completion sweep.

Mechanism, verified in `src/main.py::_apply_progress`:

  - the engine APPENDS recursive secondaries to `state.search_targets`
    (sherlock_service, `targets.append`) and `parse_usernames` puts permute
    variants there too. That append's own comment says it exists
    *precisely* so the staleness filter admits those ticks.
  - the old guard compared ONLY against `state.current_username` and fired
    FIRST, so it dropped every secondary tick — and the final apply, whose
    `last_prog` IS the last secondary.

Net effect: the primary target renders, the recursive tail (default ON,
up to 20 targets x 500 sites) renders nothing, and `is_searching` stays
True the whole way. The bar sits at 98/99% forever.

The fix admits anything whose identity is the active query OR a member of
`search_targets`, and still drops genuine supersede traffic — the second
test below pins that half.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from core.constants import MODE_USERNAME
from core.state import state
from main import AppController
from services.sherlock_service import SearchProgress


def _make_controller() -> AppController:
    page = MagicMock()
    page.dialog = None
    controller = AppController(page)
    controller._enrich_queue = None
    return controller


def _snapshot():
    return {
        "current_username": state.current_username,
        "search_mode": state.search_mode,
        "is_searching": state.is_searching,
        "search_targets": list(state.search_targets or []),
        "search_progress": state.search_progress,
    }


def _restore(snap):
    state.current_username = snap["current_username"]
    state.search_mode = snap["search_mode"]
    state.is_searching = snap["is_searching"]
    state.search_targets = snap["search_targets"]
    state.search_progress = snap["search_progress"]


def test_recursive_tail_tick_is_admitted():
    """A secondary target's tick must reach state, not be dropped."""
    controller = _make_controller()
    snap = _snapshot()
    try:
        state.current_username = "primaryuser"
        state.search_mode = MODE_USERNAME
        state.search_targets = ["primaryuser", "secondaryuser"]
        state.is_searching = True
        state.search_progress = None

        tail = SearchProgress(
            username="secondaryuser", total_sites=500, is_running=True
        )
        asyncio.run(controller._apply_progress(tail))

        assert state.search_progress is tail, (
            "recursive-tail tick was dropped as 'superseded' — the tail "
            "freezes while the engine keeps running (stuck at 98/99%)"
        )
    finally:
        _restore(snap)


def test_permute_variant_tick_is_admitted():
    """Variants are joined into the scan, so their ticks count too."""
    controller = _make_controller()
    snap = _snapshot()
    try:
        state.current_username = "john.doe"
        state.search_mode = MODE_USERNAME
        # parse_usernames puts every comma-joined handle here.
        state.search_targets = ["john.doe", "john_doe", "johndoe"]
        state.is_searching = True
        state.search_progress = None

        variant = SearchProgress(username="john_doe", total_sites=500, is_running=True)
        asyncio.run(controller._apply_progress(variant))

        assert state.search_progress is variant, "permute-variant tick was dropped"
    finally:
        _restore(snap)


def test_superseded_scan_tick_is_still_dropped():
    """The fix must not weaken the protection it replaced.

    A dying scan's identity is in neither the active query nor the live
    target list — it must still be refused, or a superseded scan would
    clobber the replacement's progress slot.
    """
    controller = _make_controller()
    snap = _snapshot()
    try:
        state.current_username = "newtarget"
        state.search_mode = MODE_USERNAME
        state.search_targets = ["newtarget"]
        state.is_searching = True
        state.search_progress = None

        dead = SearchProgress(username="oldtarget", total_sites=500, is_running=True)
        asyncio.run(controller._apply_progress(dead))

        assert state.search_progress is None, (
            "a superseded scan's tick was allowed to clobber the live slot"
        )
    finally:
        _restore(snap)


def _texts_of(control) -> list[str]:
    """Every string value in a rendered component tree."""
    from flet.components.component import Component

    out: list[str] = []

    def expand(node):
        out.append(node)
        if isinstance(node, Component):
            node.before_update()
            b = getattr(node, "_b", None)
            if b is not None:
                expand(b)
        elif isinstance(node, list):
            for item in node:
                expand(item)
        else:
            for ch in getattr(node, "controls", None) or []:
                expand(ch)
            content = getattr(node, "content", None)
            if content is not None and not isinstance(content, str):
                expand(content)

    expand(control)
    return [n.value for n in out if hasattr(n, "value") and isinstance(n.value, str)]


def _render_results():
    from flet.components.component import Renderer

    from screens.results_screen import ResultsScreen
    from state.app_state import AppStateCtx
    from state.controller_ctx import ControllerMethods, ControllerMethodsCtx

    renderer = Renderer()
    return renderer.render(
        lambda: ControllerMethodsCtx(
            ControllerMethods(), lambda: AppStateCtx(state, ResultsScreen)
        )
    )


def test_results_leaves_initializing_once_a_tick_lands():
    """The owner's top symptom: Results stuck on "Initializing" forever.

    The shade notification and the screen are fed from the SAME call site
    (`_apply_progress`), but the screen only re-renders when the flusher
    bumps `progress_version`. So the chain that must hold is:

        tick -> state.search_progress assigned
             -> _render_dirty set
             -> flusher bumps progress_version
             -> Results re-renders and leaves "Initializing"

    There was no test for any link of it. The "Initializing" condition is
    `checked == 0 and engine_total == 0`, so a first tick carrying a real
    denominator has to take it away.
    """
    controller = _make_controller()
    snap = _snapshot()
    version_before = state.progress_version
    try:
        state.current_username = "primaryuser"
        state.search_mode = MODE_USERNAME
        state.search_targets = ["primaryuser"]
        state.is_searching = True

        # Fresh scan: no tick yet — this is the initializing state.
        state.search_progress = SearchProgress(
            username="primaryuser", total_sites=0, is_running=True
        )
        assert any("Initializing" in t for t in _texts_of(_render_results())), (
            "expected Results to start at the initializing state"
        )

        # The engine's first tick, arriving the way a worker sends it:
        # `_progress_from_thread` coalesces on a 500ms window and the flush
        # that follows sets `_render_dirty` — that flag is the whole bridge
        # between "the shade shows a number" and "the screen does".
        first = SearchProgress(
            username="primaryuser", total_sites=5200, is_running=True
        )
        loop = asyncio.new_event_loop()
        controller._main_loop = loop
        try:
            controller._progress_from_thread(first)
            loop.run_until_complete(asyncio.sleep(0.8))
        finally:
            loop.close()
            controller._main_loop = None

        # Link 1: the tick reached state.
        assert state.search_progress is first, "tick never reached state"
        # Link 2: the flush marked the shell dirty (what the flusher reads).
        assert controller._render_dirty, (
            "the worker bridge never marked the render dirty — the shade "
            "would advance while the screen stays frozen"
        )
        # Link 3: bumping (what the flusher does) moves progress_version.
        state.progress_version += 1
        assert state.progress_version > version_before

        # Link 4: the screen actually leaves "Initializing".
        still = [t for t in _texts_of(_render_results()) if "Initializing" in t]
        assert not still, "Results still shows Initializing after a real tick"
    finally:
        _restore(snap)
