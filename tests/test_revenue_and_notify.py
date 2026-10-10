"""Regression tests for the revenue + notification batch (post-2.3.0).

- Interleaved results banners: every 10 when the list is bigger than 10,
  every 5 when it is 10 or fewer, all tabs, capped per list.
- Banner pool: the same slot returns the same control across calls, so a
  re-render never re-requests an ad.
- Interstitial minimum interval: a second show inside the window is skipped.
- History badge counter: increments on save, clears on reset and on open.
- Resume summary is consumed once (one snack, not one per resume).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

# ── Banner spacing ───────────────────────────────────────────────────────


def test_banner_spacing_rule():
    from screens.results_screen import _banner_slots

    # >10 results -> one every 10 (after the 10th, 20th, ...)
    assert _banner_slots(11) == [9]
    assert _banner_slots(20) == [9]
    assert _banner_slots(35) == [9, 19, 29]
    # <=10 -> one every 5 (after the 5th); exactly 10 is covered, not 0
    assert _banner_slots(7) == [4]
    assert _banner_slots(9) == [4]
    assert _banner_slots(10) == [4]
    # nothing to interleave
    assert _banner_slots(0) == []
    assert _banner_slots(1) == []
    assert _banner_slots(4) == []


def test_banner_spacing_capped_for_huge_lists():
    from screens.results_screen import _BANNER_MAX_PER_LIST, _banner_slots

    slots = _banner_slots(5203)
    assert len(slots) == _BANNER_MAX_PER_LIST
    # still monotonic, still inside the list, never on the last card
    assert slots == sorted(slots)
    assert all(0 <= s < 5202 for s in slots)


# ── Banner pool ──────────────────────────────────────────────────────────


def test_banner_pool_returns_stable_control():
    """The same slot must hand back the SAME control: a fresh BannerAd per
    render burns a request and flashes the slot."""
    from components import banner_ad

    banner_ad._BANNER_POOL.clear()
    try:
        first = banner_ad.pooled_banner_ad("slot-a")
        second = banner_ad.pooled_banner_ad("slot-a")
        assert first is second
        other = banner_ad.pooled_banner_ad("slot-b")
        assert other is not first
    finally:
        banner_ad._BANNER_POOL.clear()


def test_result_list_places_banners_between_cards():
    """Cards keep their order and slots carry banners in between."""
    from screens.results_screen import _banner_slots, _build_result_list

    items = list(range(25))
    made = []
    banner = object()

    def build_card(r):
        made.append(("card", r))
        return object()

    tree = _build_result_list(
        items, "Empty", "nothing", build_card, "", banner_at=lambda i: banner
    )
    controls = tree.controls
    slots = _banner_slots(len(items))
    assert len(controls) == len(items) + len(slots)
    banner_positions = [i for i, c in enumerate(controls) if c is banner]
    # a banner sits right after the card at each slot index
    assert banner_positions == [s + 1 + k for k, s in enumerate(slots)]
    assert controls[9] is not banner  # the 10th card is still a card
    assert controls[10] is banner


# ── Interstitial interval ────────────────────────────────────────────────


def test_interstitial_min_interval_blocks_burst():
    import time

    from services.ad_service import AdService

    svc = AdService(MagicMock())
    svc._last_interstitial_at = time.monotonic()  # one just showed
    svc._can_request_ads = True
    svc._is_mobile = lambda: True
    # a second call inside the window must be skipped and must NOT reset the
    # clock (otherwise a burst could keep deferring forever)
    before = svc._last_interstitial_at

    async def run():
        return await svc.show_interstitial()

    import asyncio

    assert asyncio.run(run()) is False
    assert svc._last_interstitial_at == before

    # outside the window it proceeds (and stamps the new time)
    svc._last_interstitial_at = 0.0
    svc.interstitial = None

    def _fresh(**kwargs):
        # sync on purpose: an async def would only build a coroutine and
        # never raise, so the construction-failure branch would not run.
        raise AssertionError("should not construct on this path")

    import flet_ads as fta

    original = fta.InterstitialAd
    fta.InterstitialAd = _fresh
    try:
        svc._is_mobile = lambda: True
        assert asyncio.run(run()) is False  # construction failure swallowed
    finally:
        fta.InterstitialAd = original


# ── History badge counter ────────────────────────────────────────────────


def test_history_unseen_counter_lifecycle():
    from core.state import AppState

    st = AppState()
    assert st.history_unseen == 0
    st.history_unseen = 3
    st.reset_search()
    assert st.history_unseen == 0


def test_save_to_history_bumps_unseen():
    """Each completed scan adds one to the badge count."""
    import asyncio

    from core.state import state
    from main import AppController

    controller = AppController(MagicMock())
    storage = MagicMock()
    storage.set = AsyncMock()
    storage.get = AsyncMock(return_value=None)
    controller.storage = storage

    state.history = []
    state.history_unseen = 0

    async def run():
        await controller._save_to_history("alice", 3, 10, mode="username")
        await controller._save_to_history("bob", 1, 10, mode="username")

    asyncio.run(run())
    assert state.history_unseen == 2
    assert [e["query"] for e in state.history] == ["bob", "alice"]


# ── Resume summary ───────────────────────────────────────────────────────


def test_resume_summary_surfaces_once():
    """The scan-finished snack fires on the first resume after a scan, then
    the summary is consumed (no repeat snack on the next resume)."""
    import asyncio

    from core.state import state
    from main import AppController

    controller = AppController(MagicMock())
    controller.connectivity = None
    controller._last_scan_summary = ("username", "torvalds", 14)

    state.history_unlocked = True

    async def run():
        await controller._on_lifecycle_change(
            type("E", (), {"state": __import__("flet").AppLifecycleState.RESUME})()
        )

    asyncio.run(run())
    assert controller._last_scan_summary is None


def test_resume_relocks_history_and_probes_connectivity():
    import asyncio

    import flet as ft

    from core.state import state
    from main import AppController

    controller = AppController(MagicMock())
    probe = MagicMock()
    probe.get_connectivity = AsyncMock(return_value=[])
    controller.connectivity = probe
    state.history_unlocked = True

    async def run():
        await controller._on_lifecycle_change(
            type(
                "E",
                (),
                {"state": ft.AppLifecycleState.RESUME},
            )()
        )

    asyncio.run(run())
    assert state.history_unlocked is False
    assert probe.get_connectivity.await_count == 1
