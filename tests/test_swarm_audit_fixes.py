"""Fixes from the 19-agent verification swarm (v2.3.2).

Every audit finding that turned out to be REAL, with the test that would
catch its reintroduction. Two auditor claims are deliberately NOT fixed
here because they were wrong: `except A, B:` is valid Python 3.14 (PEP 758,
the whole repo compiles under 3.14.7) and the two maigret
`WindowsSelectorEventLoopPolicy` warnings are kept visible on purpose.

1. **The supersede early-return was unguarded.** `is_cancelled` cannot tell
   a user cancel from a supersede — `_kill_all_activity` marks every live
   progress object cancelled — so a dying scan could clear the live
   replacement's `is_searching` and stop its shared render flusher.
2. **The mode chip could flip the running scan's identity.** `search_mode`
   is the tick pipeline's notion of which engine is live, so a mid-scan chip
   tap froze the live progress display.
3. **The result-list memo fingerprints were too narrow.** Enrichment VALUES
   and the email card's recovery/phone/domain fields sat outside the deps,
   so a later enrichment pass or a re-scan kept rendering the old card.
4. **`section.setFolded(True)`** — the installed xmind signature takes no
   argument, so the TypeError landed in the guard and the fold never applied.
5. **The kill left the dead scan's target scope behind**, so a dying scan's
   secondary tick stayed admissible until the replacement's engine rebound
   the list.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.constants import MODE_EMAIL, MODE_USERNAME
from core.state import state
from main import AppController
from services.sherlock_service import SearchProgress, SiteResult


def _expand(node, out):
    """Depth-first walk of a rendered component tree (component harness)."""
    from flet.components.component import Component

    out.append(node)
    if isinstance(node, Component):
        node.before_update()
        b = getattr(node, "_b", None)
        if b is not None:
            _expand(b, out)
    elif isinstance(node, list):
        for item in node:
            _expand(item, out)
    else:
        for ch in getattr(node, "controls", None) or []:
            _expand(ch, out)
        content = getattr(node, "content", None)
        if content is not None and not isinstance(content, str):
            _expand(content, out)


def _nodes_of(root) -> list:
    out: list = []
    _expand(root, out)
    return out


def _texts_of(control) -> list[str]:
    return [
        n.value
        for n in _nodes_of(control)
        if isinstance(getattr(n, "value", None), str)
    ]


def _texts_under(node) -> list[str]:
    return [
        n.value for n in _nodes_of(node) if isinstance(getattr(n, "value", None), str)
    ]


# ── 1. A superseded scan must not touch the replacement ──────────────────


def _controller() -> AppController:
    controller = AppController(MagicMock())
    controller._controller_methods = MagicMock()
    controller._controller_methods.show_results = lambda: None
    return controller


def test_superseded_username_return_cannot_touch_the_replacement():
    """The early-return branch must be ownership-guarded.

    `is_cancelled` is not a supersede test: the kill path marks every live
    progress cancelled. Reaching that branch while a replacement is live must
    not clear its flags or stop its shared render flusher.
    """
    controller = _controller()
    controller.sherlock_service = MagicMock()
    controller.sherlock_service.load_sites = AsyncMock()
    controller.storage = MagicMock()
    controller.storage.set = AsyncMock()
    stopped = []
    controller._stop_render_flusher = lambda: stopped.append(1)

    async def _search(**kwargs):
        if kwargs.get("username") == "oldtarget":
            try:
                await asyncio.sleep(3600)  # in flight when the kill lands
            except asyncio.CancelledError:
                pass  # the engine reports the stop as a RESULT, not a raise
            return MagicMock(is_cancelled=True)
        await asyncio.sleep(3600)  # the replacement stays live
        return MagicMock(is_cancelled=False)

    controller.sherlock_service.search = _search

    state.history = []
    state.target_results = {}
    state.is_searching = False
    state.search_progress = None
    state.is_online = True

    async def run():
        task_a = asyncio.create_task(controller.start_search("oldtarget"))
        await asyncio.sleep(0.05)
        assert state.current_username == "oldtarget"
        task_b = asyncio.create_task(controller.start_search("newtarget"))
        await asyncio.sleep(0.05)
        # A's engine returns now (superseded), while B is the live scan.
        await asyncio.wait_for(
            asyncio.gather(task_a, return_exceptions=True), timeout=5
        )
        assert state.current_username == "newtarget", "the kill never landed"
        assert state.is_searching is True, (
            "the superseded scan cleared the LIVE replacement's is_searching"
        )
        assert stopped == [], "the superseded scan stopped the shared flusher"
        task_b.cancel()
        await asyncio.gather(task_b, return_exceptions=True)

    asyncio.run(run())


def test_superseded_same_target_return_cannot_touch_the_replacement():
    """The cancel-then-retry-the-same-name flow: target equality is NOT
    ownership.

    The user cancels a scan and immediately searches the same handle again
    (the owner's own flow). The new scan has the same target and mode, so a
    guard comparing only those passes and the dying scan clears the LIVE
    scan's flags, stops its flusher and retracts its bar. Ownership is the
    registered task, and that has moved on.
    """
    controller = _controller()
    controller.sherlock_service = MagicMock()
    controller.sherlock_service.load_sites = AsyncMock()
    controller.storage = MagicMock()
    controller.storage.set = AsyncMock()
    stopped = []
    controller._stop_render_flusher = lambda: stopped.append(1)

    calls = {"n": 0}

    async def _search(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass  # the engine reports the stop as a RESULT
            return MagicMock(is_cancelled=True)
        await asyncio.sleep(3600)  # the replacement stays live
        return MagicMock(is_cancelled=False)

    controller.sherlock_service.search = _search

    state.history = []
    state.target_results = {}
    state.is_searching = False
    state.search_progress = None
    state.is_online = True

    async def run():
        task_a = asyncio.create_task(controller.start_search("alice"))
        await asyncio.sleep(0.05)
        # The user cancels: the kill clears the flag, which is exactly what
        # makes the re-attach gate stand aside for the second start.
        state.is_searching = False
        task_b = asyncio.create_task(controller.start_search("alice"))
        await asyncio.sleep(0.05)
        assert calls["n"] == 2, "the retry was swallowed by the re-attach gate"
        await asyncio.wait_for(
            asyncio.gather(task_a, return_exceptions=True), timeout=5
        )
        assert state.is_searching is True, (
            "the dying same-target scan cleared the LIVE retry's is_searching"
        )
        assert stopped == [], "the dying same-target scan stopped the flusher"
        task_b.cancel()
        await asyncio.gather(task_b, return_exceptions=True)

    asyncio.run(run())


def test_superseded_email_return_cannot_touch_the_replacement():
    """Same guard on the email branch."""
    controller = _controller()
    controller.email_service = MagicMock()
    controller.email_service.is_available = True
    controller.storage = MagicMock()
    controller.storage.set = AsyncMock()
    stopped = []
    controller._stop_render_flusher = lambda: stopped.append(1)

    async def _search(**kwargs):
        if kwargs.get("email") == "old@example.com":
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass
            return MagicMock(is_cancelled=True)
        await asyncio.sleep(3600)
        return MagicMock(is_cancelled=False)

    controller.email_service.search = _search

    state.history = []
    state.target_results = {}
    state.is_searching = False
    state.search_progress = None
    state.is_online = True

    async def run():
        task_a = asyncio.create_task(controller.start_email_search("old@example.com"))
        await asyncio.sleep(0.05)
        task_b = asyncio.create_task(controller.start_email_search("new@example.com"))
        await asyncio.sleep(0.05)
        await asyncio.wait_for(
            asyncio.gather(task_a, return_exceptions=True), timeout=5
        )
        assert state.current_username == "new@example.com", "the kill never landed"
        assert state.is_searching is True, (
            "the superseded email scan cleared the LIVE replacement's is_searching"
        )
        assert stopped == [], "the superseded email scan stopped the shared flusher"
        task_b.cancel()
        await asyncio.gather(task_b, return_exceptions=True)

    asyncio.run(run())


# ── 2. The chip must not flip a running scan's identity ──────────────────


def _render_home():
    from flet.components.component import Renderer

    from screens.home_screen import HomeScreen
    from state.app_state import AppStateCtx
    from state.controller_ctx import ControllerMethods, ControllerMethodsCtx

    renderer = Renderer()
    root = renderer.render(
        lambda: ControllerMethodsCtx(
            ControllerMethods(), lambda: AppStateCtx(state, HomeScreen)
        )
    )
    return root, _nodes_of(root)


def _find_mode_pills(nodes):
    import flet as ft

    return [
        n
        for n in nodes
        if type(n).__name__ == "Container"
        and getattr(n, "padding", None) == ft.Padding(12, 6, 12, 6)
    ]


def test_mode_chip_is_visibly_locked_and_ignored_while_a_scan_is_live():
    """`search_mode` is the tick pipeline's scan identity, not just intent.

    `_apply_progress` drops ticks whose mode disagrees with it, so a
    mid-scan mode flip froze the live progress. While a scan is genuinely
    ticking the mode belongs to `start_*`: the pills go visually inert and
    `_switch_mode` ignores the change even if it is reached another way
    (the typed/pasted-address auto-switch).
    """
    import screens.home_screen as home_mod

    saved_spawn = home_mod.spawn
    home_mod.spawn = lambda coro, *a, **k: coro.close()  # no persist task
    snap = (state.search_mode, state.is_searching, state.search_progress)
    try:
        state.search_mode = MODE_USERNAME
        state.is_searching = True
        state.search_progress = SearchProgress(
            username="alice", total_sites=100, is_running=True
        )

        _root, nodes = _render_home()
        pills = _find_mode_pills(nodes)
        assert len(pills) == 2, f"expected the two mode pills, found {len(pills)}"
        email_pill = next(p for p in pills if "Email" in _texts_under(p))
        assert email_pill.on_click is None, (
            "the locked pill still takes taps — a mid-scan flip freezes the "
            "live progress (every tick fails the cross-mode guard)"
        )
        assert email_pill.opacity == 0.45, "the lock must be visible, not silent"

        # The other way in: a pasted full address auto-switches the mode.
        # `_on_input_change` runs the forward (username->email) flip, so the
        # guard inside `_switch_mode` has to hold on its own.
        bars = [n for n in nodes if type(n).__name__ == "SearchBar"]
        assert bars and bars[0].on_change is not None

        class _Event:
            class Control:
                value = "alice@example.com"

            control = Control()

        bars[0].on_change(_Event())
        assert state.search_mode == MODE_USERNAME, (
            "the pasted-address auto-switch flipped the LIVE scan's mode"
        )

        # …and the pills work again the moment no scan owns the mode.
        state.is_searching = False
        state.search_progress = None
        _root, nodes = _render_home()
        pills = _find_mode_pills(nodes)
        email_pill = next(p for p in pills if "Email" in _texts_under(p))
        assert email_pill.on_click is not None, "idle pills must be tappable"
        email_pill.on_click(None)
        assert state.search_mode == MODE_EMAIL, (
            "the guard must not block an idle mode switch"
        )
    finally:
        home_mod.spawn = saved_spawn
        state.search_mode, state.is_searching, state.search_progress = snap


# ── 3. Memo fingerprints must cover what the cards render ────────────────


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


def test_email_card_refreshes_when_a_row_gains_recovery_details():
    """A re-scanned row must not keep its old card.

    The fingerprint carried only (name, exists, rateLimit, unavailable), so
    the recovery address / phone / domain / extras were outside the memo
    deps and the tab rendered the previous scan's row (and its dialog).
    """
    snap = (
        state.search_mode,
        state.is_searching,
        state.search_progress,
        state.email_results,
        state.email_results_address,
    )
    try:
        state.search_mode = MODE_EMAIL
        state.is_searching = False
        state.search_progress = None
        state.email_results_address = "alice@example.com"
        row = {
            "name": "GitHub",
            "domain": "github.com",
            "exists": True,
            "rateLimit": False,
            "unavailable": False,
            "emailrecovery": None,
            "phoneNumber": None,
            "others": {},
        }
        state.email_results = [dict(row)]

        root = _render_results()
        assert "recovered@mail.com" not in _texts_under(root)

        # The re-scan returns the same row with details filled in — the
        # (name, flags) fingerprint is unchanged.
        state.email_results = [{**row, "emailrecovery": "recovered@mail.com"}]
        state.progress_version += 1
        _nodes_of(root)  # re-render the same component

        assert "recovered@mail.com" in _texts_under(root), (
            "stale memo: the tab kept rendering the previous scan's row"
        )
    finally:
        (
            state.search_mode,
            state.is_searching,
            state.search_progress,
            state.email_results,
            state.email_results_address,
        ) = snap


def test_username_card_refreshes_when_an_enrichment_value_changes():
    """Enrichment VALUES are memo deps, not just keys.

    `_enrichment_fingerprint` was `sorted(v.keys())`, so a later enrichment
    pass that updated a value under an existing key never reached the card.
    The username card renders bio/location straight from that dict
    (result_card.py, the merged-profile block outside the `others` gate).
    """
    snap = (
        state.search_mode,
        state.is_searching,
        state.search_progress,
        state.last_results,
        state.last_results_username,
        state.enrichments,
    )
    try:
        state.search_mode = MODE_USERNAME
        state.is_searching = False
        state.search_progress = None
        state.last_results_username = "alice"
        state.last_results = {
            "GitHub": SiteResult(
                site_name="GitHub",
                url_main="",
                url_user="https://github.com/alice",
                status="Claimed",
                http_status="200",
            )
        }
        state.enrichments = {"https://github.com/alice": {"location": "Lagos"}}

        root = _render_results()
        assert any("Lagos" in t for t in _texts_under(root))
        assert not any("Abuja" in t for t in _texts_under(root))

        # A later pass refines the value under the same key.
        state.enrichments = {"https://github.com/alice": {"location": "Abuja"}}
        state.progress_version += 1
        _nodes_of(root)  # re-render the same component

        assert any("Abuja" in t for t in _texts_under(root)), (
            "stale memo: the card kept its first enrichment snapshot"
        )
    finally:
        (
            state.search_mode,
            state.is_searching,
            state.search_progress,
            state.last_results,
            state.last_results_username,
            state.enrichments,
        ) = snap


# ── 4. The kill drops the dead scan's target scope ───────────────────────


def test_kill_drops_the_dead_scans_target_scope():
    """A dying scan's secondary tick must not stay admissible.

    `_apply_progress` admits a tick whose target is in `state.search_targets`,
    and the replacement does not rebind that list until its engine starts —
    so the kill has to drain it.
    """
    controller = _controller()
    snap = (
        state.search_targets,
        state.current_username,
        state.search_mode,
        state.is_searching,
        state.search_progress,
    )
    try:
        state.search_targets = ["oldprimary", "oldsecondary"]
        state.current_username = "oldprimary"
        state.search_mode = MODE_USERNAME
        state.is_searching = True
        state.search_progress = None

        controller._kill_all_activity("test")

        assert list(state.search_targets or []) == [], (
            "the dead scan's scope survived the kill"
        )

        state.current_username = "newprimary"
        dead = SearchProgress(username="oldsecondary", total_sites=10, is_running=True)
        asyncio.run(controller._apply_progress(dead))
        assert state.search_progress is None, (
            "a dying scan's secondary tick clobbered the live progress slot"
        )
    finally:
        (
            state.search_targets,
            state.current_username,
            state.search_mode,
            state.is_searching,
            state.search_progress,
        ) = snap


# ── 5. The XMind fold actually applies ──────────────────────────────────


def test_xmind_folds_the_uncategorized_section(tmp_path):
    """`setFolded(True)` raised TypeError into the guard, so P4-9 never ran.

    The installed signature is `setFolded(self)` — no argument
    (.venv/Lib/site-packages/xmind/core/topic.py). The fold is written as
    `branch="folded"` on the section topic in content.xml.
    """
    import re
    import zipfile

    from services.report_service import generate_xmind_case

    rows = [
        SiteResult(
            site_name="SomeObscureSite",
            url_user="https://x.example/alice",
            url_main="",
            status="Claimed",
            http_status="200",
        )  # no tags -> the "Uncategorized" catch-all section
    ]
    out = tmp_path / "case.xmind"
    result = generate_xmind_case("alice", rows, output_path=out)
    if result is None:
        pytest.skip("xmind not installed")

    with zipfile.ZipFile(out) as zf:
        xml = zf.read("content.xml").decode("utf-8")

    # String match rather than an XML parse: the file is our own output, and
    # this pins exactly the shape that matters — the folded topic IS the
    # Uncategorized section.
    folded_section = re.search(
        r'<topic[^>]*branch="folded"[^>]*>\s*<title>Uncategorized</title>', xml
    )
    assert folded_section, (
        "the catch-all section is not folded — setFolded's TypeError was "
        "swallowed by the guard again"
    )
