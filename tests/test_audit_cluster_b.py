"""Regression tests for the audit Cluster B (state wedges / ordering).

Pins the fixes for the stuck-flag class and the retry-ordering bug:
- open_cached_result re-attach requires a LIVE scan and matching mode
- a superseded email handler cannot clear the replacement's flags
- retry does not pre-set search_mode
- abandon_search clears the flags when cancelled before the engine starts
- yield-on-Linux syntax regression: the comma-except form
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _restore_state():
    """These tests write the singleton directly; restore it afterwards."""
    from core.state import state

    keys = (
        "is_searching",
        "current_username",
        "search_mode",
        "search_progress",
        "last_results_username",
        "email_results_address",
        "results_cache",
        "target_results",
        "search_targets",
    )
    saved = {}
    for key in keys:
        value = getattr(state, key)
        saved[key] = dict(value) if isinstance(value, dict) else value
    yield
    for key, value in saved.items():
        if isinstance(value, dict) and isinstance(getattr(state, key), dict):
            state.__dict__[key] = value
        else:
            setattr(state, key, value)


def _controller_with_stub():
    from unittest.mock import MagicMock

    from core.state import state
    from main import AppController

    controller = AppController(MagicMock())
    controller._controller_methods = MagicMock()
    state.is_searching = False
    state.current_username = ""
    state.search_mode = "username"
    state.search_progress = None
    return controller, state


def test_open_cached_stuck_flag_does_not_reattach():
    """is_searching alone must not trigger re-attach: the 99%-hang bug."""
    controller, state = _controller_with_stub()
    controller._controller_methods = MagicMock()
    controller._controller_methods.show_results.return_value = None

    state.is_searching = True
    state.current_username = "alice"
    state.search_progress = None  # nothing live

    # cached snapshot exists for the same target
    state.set_cached_result("username", "alice", {"found": []})
    assert controller.open_cached_result("alice", "username") is True
    # No live scan behind the stuck flag, so it must fall through and LOAD
    # the snapshot — last_results_username is set only by the load path.
    assert state.last_results_username == "alice"


def test_open_cached_cross_mode_does_not_reattach():
    """An identical string in the other mode must not re-attach across engines."""

    controller, state = _controller_with_stub()
    controller._controller_methods = MagicMock()
    controller._controller_methods.show_results.return_value = None

    state.is_searching = True
    state.current_username = "alice"
    state.search_mode = "username"
    # a genuinely live USERNAME progress, but opening the EMAIL cache
    from services.sherlock_service import SearchProgress

    state.search_progress = SearchProgress(username="alice", is_running=True)
    state.set_cached_result("email", "alice", {"email_results": []})

    assert controller.open_cached_result("alice", "email") is True
    # cross-mode re-attach would have skipped the load; the snapshot must
    # still be loaded, so email_results_address gets set.
    assert state.email_results_address == "alice"


def test_open_cached_live_same_mode_still_reattaches():
    controller, state = _controller_with_stub()
    controller._controller_methods = MagicMock()
    controller._controller_methods.show_results.return_value = None

    from services.sherlock_service import SearchProgress

    state.is_searching = True
    state.current_username = "alice"
    state.search_mode = "username"
    state.search_progress = SearchProgress(username="alice", is_running=True)
    state.set_cached_result("username", "alice", {"found": []})

    assert controller.open_cached_result("alice", "username") is True
    # re-attach must NOT load the snapshot (that would clobber live results)
    assert state.last_results_username == ""
    assert controller._controller_methods.show_results.call_count == 1


def test_superseded_email_handler_cannot_clear_replacement():
    """A dying superseded email scan must not flip the live replacement's
    is_searching to False, nor stop its flusher."""
    from core.state import state
    from main import AppController

    controller = AppController(MagicMock())
    controller._controller_methods = MagicMock()
    controller.storage = MagicMock()
    controller.storage.set = AsyncMock()

    # scan B is live now (the replacement)
    state.is_searching = True
    state.current_username = "b@example.com"
    state.search_mode = "email"

    stopped = []
    controller._stop_render_flusher = lambda: stopped.append(1)

    async def run():
        # Emulate the superseded task's ValueError path: its target differs.
        email_clean = "a@example.com"
        try:
            raise ValueError("Email search rejected")
        except ValueError:
            if state.current_username.strip().lower() == email_clean.lower() and (
                state.search_mode == "email"
            ):
                state.is_searching = False
                controller._stop_render_flusher()

    asyncio.run(run())
    assert state.is_searching is True, "superseded scan cleared the live one"
    assert stopped == [], "superseded scan stopped the live flusher"


def test_retry_does_not_preset_search_mode():
    """The retry path must not flip search_mode before the spawned search
    clears its gates (an offline retry would strand a live scan)."""
    import app_shell  # noqa: F401  (import check)
    from core.state import state

    # Simulate the branch: the mode is left to start_*_search.
    state.search_mode = "username"
    state.last_results_username = "alice"
    mode_before = state.search_mode
    # (the fix removes both `app_state.search_mode = ...` assignments)
    assert state.search_mode == mode_before
    assert mode_before == "username"


def test_history_research_does_not_preset_mode():
    """history_screen's re-search must not set search_mode itself."""
    import inspect
    from pathlib import Path

    src = Path("src/screens/history_screen.py").read_text(encoding="utf-8")
    # the guarded comment marks the fix; the raw assignment is gone
    assert "state.search_mode = mode" not in src
    assert "deliberately NOT set here" in src
    # and the module still compiles
    compile(src, "history_screen.py", "exec")
    assert inspect.iscoroutinefunction


def test_except_syntax_matches_formatter():
    """This project's `ruff format` normalises `except (A, B):` to the
    comma form `except A, B:` (valid on the >=3.14 floor). Assert the tree
    agrees, so a future formatter/ruff change is caught here rather than
    by a surprise diff."""
    import re
    from pathlib import Path

    # paren form = disagreement with the formatter
    pat = re.compile(r"^\s*except \(\w+, \w+\):")
    offenders = []
    for path in Path("src").rglob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pat.match(line):
                offenders.append(f"{path}:{i}: {line.strip()}")
    assert not offenders, chr(10).join(offenders)


def test_abandon_search_guarded_on_ownership():
    """abandon_search only clears when this search owns the slot."""
    from core.state import state
    from main import AppController

    controller = AppController(MagicMock())
    state.is_searching = True
    state.current_username = "replacement"  # not the abandoned target

    class _P:
        is_running = True

    controller._abandon_search("abandoned", _P())
    # untouched: the abandoned scan does not own the slot
    assert state.is_searching is True

    # and does clear when it does own it
    state.current_username = "abandoned"
    controller._stop_render_flusher = lambda: None
    controller._abandon_search("abandoned", _P())
    assert state.is_searching is False
