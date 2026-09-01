"""Regression tests for the v2.0.0 email→username mode-switch hang.

Root cause: `state.search_progress` is a single shared slot for both
scan modes. After an email search finished, it still held the
EmailSearchProgress object; rendering ResultsScreen in username mode
dereferenced username-only fields off it (total_sites /
SiteResult.site_name). That AttributeError fired INSIDE the render
pass, and Flet's updates scheduler calls control.update() without a
per-control try/except — the scheduler task died, freezing the whole
UI with no trace in any log (no snack, no terminal, taps dead).

Fixes under test:
  1. results_screen resolves username view data through
     _resolve_username_view_data (type-guarded, last_results fallback).
  2. start_search/start_email_search install a fresh, correctly-typed
     progress object before the UI can render the results screen.
  3. A new search hard-kills every prior activity instantly
     (_kill_all_activity cancels the previous search task + engines).
  4. _apply_progress drops ticks from killed/superseded scans so a
     dying scan can never clobber the current search's progress slot.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from core.constants import MODE_EMAIL, MODE_USERNAME
from core.state import state
from main import AppController
from screens.results_screen import _resolve_username_view_data
from services.email_service import EmailResult, EmailSearchProgress
from services.sherlock_service import SearchProgress, SiteResult


class _ParkedSherlockService:
    """Scan that never finishes on its own — must be killed."""

    def cancel(self):
        pass

    async def load_sites(self):
        return 400

    async def search(self, username, on_progress=None, timeout=30):
        await asyncio.sleep(30)
        raise AssertionError("parked scan should have been killed")


class _ParkedEmailService:
    def __init__(self):
        self.is_available = True

    def cancel(self):
        pass

    async def search(
        self,
        email,
        on_progress=None,
        timeout=10,
        skip_password_recovery=False,
        concurrency=15,
    ):
        await asyncio.sleep(30)
        raise AssertionError("parked scan should have been killed")


class _InstantEmailService:
    """Completes immediately, like a finished email search."""

    def __init__(self):
        self.is_available = True

    def cancel(self):
        pass

    async def search(
        self,
        email,
        on_progress=None,
        timeout=10,
        skip_password_recovery=False,
        concurrency=15,
    ):
        return EmailSearchProgress(
            email=email,
            total_modules=3,
            checked_modules=3,
            is_running=False,
        )


def _site(name, status):
    return SiteResult(
        site_name=name,
        url_main="https://x.com",
        url_user="https://x.com/kiri",
        status=status,
        http_status="200",
    )


@pytest.fixture
def clean_state():
    state.reset_search()
    state.search_mode = MODE_USERNAME
    state.current_username = ""
    state.last_results = {}
    state.last_results_username = ""
    yield state
    state.reset_search()
    state.search_mode = MODE_USERNAME
    state.current_username = ""
    state.last_results = {}
    state.last_results_username = ""


@pytest.fixture
def controller(fake_page):
    c = AppController(fake_page)
    c.ad_service = None
    c.enrich_service = None
    yield c
    if c._search_task and not c._search_task.done():
        c._search_task.cancel()


# --- 1. Render-side guard ------------------------------------------------


def test_stale_email_progress_never_crashes_username_render(clean_state):
    """THE repro: exactly the state the user hit — email search done,
    pill switched to username, results screen renders."""
    state.search_progress = EmailSearchProgress(
        email="someone@example.com",
        total_modules=121,
        checked_modules=121,
        found=[
            EmailResult(name="GitHub", domain="github.com", method="login"),
        ],
        is_running=False,
    )
    # Must not raise — this exact call shape killed the UI before.
    view = _resolve_username_view_data(state)
    assert view.has_progress is False
    assert view.found == []
    assert view.not_found == []
    assert view.errors == []
    assert view.is_running is False
    assert view.is_cancelled is False


def test_username_render_falls_back_to_last_results(clean_state):
    state.search_progress = None
    state.last_results = {
        "GitHub": _site("GitHub", "Claimed"),
        "Reddit": _site("Reddit", "Available"),
        "Blocked": _site("Blocked", "WAF"),
    }
    view = _resolve_username_view_data(state)
    assert [r.site_name for r in view.found] == ["GitHub"]
    assert [r.site_name for r in view.not_found] == ["Reddit"]
    assert [r.site_name for r in view.errors] == ["Blocked"]
    assert view.checked == 3


def test_username_render_uses_live_username_progress(clean_state):
    state.search_progress = SearchProgress(
        username="kiri",
        total_sites=409,
        checked_sites=12,
        found=[_site("GitHub", "Claimed")],
        is_running=True,
    )
    view = _resolve_username_view_data(state)
    assert view.has_progress is True
    assert view.total == 409
    assert view.checked == 12
    assert view.is_running is True
    assert [r.site_name for r in view.found] == ["GitHub"]


# --- 2/3. Controller lifecycle: fresh typed progress + instant kill -------


def test_email_then_username_installs_typed_progress(controller, clean_state):
    """The user's exact sequence at the controller level."""
    controller.sherlock_service = _ParkedSherlockService()
    controller.email_service = _InstantEmailService()

    async def scenario():
        state.is_online = True
        state.search_mode = MODE_EMAIL
        # The app always spawns searches as their own task (home_screen
        # `asyncio.create_task(_run())`) — mirror that here.
        email_task = asyncio.create_task(
            controller.start_email_search("bob@example.com")
        )
        await email_task
        assert isinstance(state.search_progress, EmailSearchProgress)

        # User switches pill and searches a username.
        state.search_mode = MODE_USERNAME
        task = asyncio.create_task(controller.start_search("alice"))
        await asyncio.sleep(0.1)
        # Fresh USERNAME-typed progress — the stale email object is gone
        # before any render can see it.
        assert isinstance(state.search_progress, SearchProgress)
        assert state.search_progress.is_running is True
        task.cancel()

    asyncio.run(scenario())


def test_new_search_kills_prior_scan_instantly(controller, clean_state):
    controller.sherlock_service = _ParkedSherlockService()
    controller.email_service = _ParkedEmailService()

    async def scenario():
        state.is_online = True
        state.search_mode = MODE_USERNAME
        t1 = asyncio.create_task(controller.start_search("alice"))
        await asyncio.sleep(0.1)
        assert not t1.done()

        t2 = asyncio.create_task(controller.start_email_search("bob@example.com"))
        # The prior scan must die within a couple of loop ticks.
        for _ in range(25):
            await asyncio.sleep(0.02)
            if t1.cancelled():
                break
        assert t1.cancelled(), "prior search was not killed instantly"
        assert state.is_searching is True  # owned by the NEW search
        assert isinstance(state.search_progress, EmailSearchProgress)
        assert state.search_progress.email == "bob@example.com"
        t2.cancel()

    asyncio.run(scenario())


def test_cancel_button_kills_running_search(controller, clean_state):
    controller.sherlock_service = _ParkedSherlockService()

    async def scenario():
        state.is_online = True
        state.search_mode = MODE_USERNAME
        t1 = asyncio.create_task(controller.start_search("alice"))
        await asyncio.sleep(0.1)
        assert not t1.done()

        controller.cancel_search()  # sync — from the UI thread/loop
        for _ in range(25):
            await asyncio.sleep(0.02)
            if t1.cancelled():
                break
        assert t1.cancelled(), "cancel button did not kill the scan"
        assert state.is_searching is False

    asyncio.run(scenario())


# --- 4. Stale progress tick rejection -------------------------------------


def test_apply_progress_drops_superseded_scan_ticks(controller, clean_state):
    async def scenario():
        page = MagicMock()
        ctl = AppController(page)
        state.search_mode = MODE_USERNAME
        state.current_username = "alice"
        state.search_targets = ["alice"]
        state.is_searching = True
        fresh = SearchProgress(username="alice", is_running=True)
        state.search_progress = fresh

        # Cross-mode tick (a dying email scan's late callback)
        await ctl._apply_progress(
            EmailSearchProgress(email="old@example.com", is_running=True)
        )
        assert state.search_progress is fresh

        # Same-mode tick from a different (superseded) target
        await ctl._apply_progress(SearchProgress(username="bob"))
        assert state.search_progress is fresh

        # Current target tick applies
        await ctl._apply_progress(SearchProgress(username="alice"))
        assert state.search_progress is not fresh

    asyncio.run(scenario())


def test_apply_progress_drops_cross_mode_email_ticks(controller, clean_state):
    async def scenario():
        page = MagicMock()
        ctl = AppController(page)
        state.search_mode = MODE_USERNAME
        state.current_username = "alice"
        state.search_targets = ["alice"]
        state.is_searching = True
        fresh = SearchProgress(username="alice", is_running=True)
        state.search_progress = fresh

        # Email tick while username mode is active → dropped even if it
        # matches current_username (shape does not match the mode).
        await ctl._apply_progress(EmailSearchProgress(email="alice", is_running=True))
        assert state.search_progress is fresh

    asyncio.run(scenario())
