"""Regression tests for the owner's field report (v2.3.0 post-release).

Covers:
- dynamic enrichment rendering: every field shown, nothing hardcoded/dropped
  (paypal payerId/currency, wattpad locale/ambassador, nested dicts, lists).
- card overflow hint when the 6-row generic cap hides the rest.
- sites country chips carry flag emoji.
- email scan cancel clears is_searching (the stuck-button bug).
- biometric prompt: WindowsAuthMessages takes no arguments (a TypeError
  there crashed the unlock flow on Windows).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock


def _rows_to_dict(rows):
    return {label: value for _key, label, value in rows}


def test_enrichment_rows_show_every_field():
    """The owner's PayPal + Wattpad payloads must fully reach the UI."""
    from core.enrich_view import enrichment_rows

    paypal = {
        "fullname": "Onyeka Enwerem",
        "username": "Onyeka",
        "payerId": "GKGC3NYH5SPXN",
        "address": "Oakland, CA",
        "isProfileStatusActive": "True",
        "primaryCurrencyCode": "USD",
        "image": "https://pics.paypal.com/00/s/x/image_58.jpg",
        "_extractor": "PayPal",
    }
    wattpad = {
        "username": "Onyeka",
        "image": "https://img.wattpad.com/useravatar/7.128.jpg",
        "gender": "Unknown",
        "locale": "en_US",
        "created_at": "2010-03-15T15:16:34Z",
        "updated_at": "2010-03-15T15:16:34Z",
        "isPrivate": "False",
        "is_verified": "False",
        "verified_email": "False",
        "ambassador": "False",
        "isMuted": "False",
        "allowCrawler": "False",
        "follower_count": "0",
        "following_count": "0",
        "_extractor": "Wattpad API",
    }

    pp = _rows_to_dict(enrichment_rows(paypal))
    assert len(pp) == 7, pp  # 6 fields + Source (image is used as the avatar)
    assert pp["Payer Id"] == "GKGC3NYH5SPXN"
    assert pp["Primary Currency Code"] == "USD"
    assert pp["Is Profile Status Active"] == "Yes"  # "True" -> Yes
    assert pp["Source"] == "PayPal"

    wp = _rows_to_dict(enrichment_rows(wattpad))
    assert wp["Locale"] == "en_US"
    assert wp["Ambassador"] == "No"
    assert wp["Created At"] == "Mar 15, 2010"
    assert wp["Updated At"] == "Mar 15, 2010"
    assert wp["Follower Count"] == "0"
    assert wp["Source"] == "Wattpad API"


def test_enrichment_rows_flatten_nested_and_lists():
    from core.enrich_view import enrichment_rows

    rows = enrichment_rows(
        {
            "links": [{"url": "https://a.com", "name": "A"}, {"url": "https://b.com"}],
            "tags": ["x", "y"],
            "nested": {"deep": {"value": "z"}},
        }
    )
    text = " ".join(f"{label}: {value}" for _key, label, value in rows)
    assert "Links 1 Url: https://a.com" in text
    assert "Links 1 Name: A" in text
    assert "Links 2 Url: https://b.com" in text
    assert "Tags: x, y" in text
    assert "Nested Deep Value: z" in text


def test_enrichment_rows_skip_param():
    """The dialog passes skip= so specially-rendered fields aren't duplicated."""
    from core.enrich_view import enrichment_rows

    rows = enrichment_rows(
        {"location": "Oakland, CA", "bio": "dev", "payerId": "X"},
        skip={"location", "bio"},
    )
    keys = {k for k, _, _ in rows}
    assert "location" not in keys and "bio" not in keys
    assert "payerId" in keys


def test_card_shows_every_field_and_overflow_hint():
    from components.result_card import ResultCard
    from tests.flet_tree import walk_texts

    card = ResultCard(
        site_name="GitHub",
        status="Claimed",
        url_user="https://github.com/octocat",
        others={
            "extra": {
                "login": "octocat",
                "bio": "hello world",  # styled line
                "payerId": "GKGC3NYH5SPXN",
                "locale": "en_US",
                "timezone": "UTC",
                "ambassador": "False",
                "primaryCurrencyCode": "USD",
                "gender": "Unknown",
                "isVerified": "True",
            },
            "media": {},
        },
    )
    texts = " ".join(t.value or "" for t in walk_texts(card))
    assert "Bio: hello world" in texts
    assert "Payer Id: GKGC3NYH5SPXN" in texts
    assert "Locale: en_US" in texts
    assert "Timezone: UTC" in texts
    # 8 non-styled fields against a 6-row cap -> an honest +2 hint
    assert "+2 more fields" in texts


def test_country_chips_carry_flags():
    """Sites screen country chips show flag + code, not bare codes."""
    from flet.components.component import Component, Renderer

    from core.state import state
    from screens.sites_screen import SitesScreen
    from state.app_state import AppStateCtx
    from state.controller_ctx import ControllerMethods, ControllerMethodsCtx
    from tests.flet_tree import walk_texts

    # Country chips derive from the inverted tag index, not sites_tags_map.
    prev_index = state.sites_tag_index
    prev_version = state.sites_version
    state.sites_tag_index = {
        "coding": ["GitHub"],
        "social": ["Twitter", "Reddit"],
        "gb": ["GitHub"],
        "ru": ["Twitter"],
        "us": ["Reddit"],
    }
    state.sites_version = prev_version + 1

    methods = ControllerMethods()
    renderer = Renderer()
    root = renderer.render(
        lambda: ControllerMethodsCtx(methods, lambda: AppStateCtx(state, SitesScreen))
    )

    def expand(node):
        if isinstance(node, Component):
            node.before_update()
            if getattr(node, "_b", None) is not None:
                yield from expand(node._b)
        elif isinstance(node, list):
            for item in node:
                yield from expand(item)
        else:
            yield node
            for ch in getattr(node, "controls", None) or []:
                yield from expand(ch)
            content = getattr(node, "content", None)
            if content is not None and not isinstance(content, str):
                yield from expand(content)

    nodes = list(expand(root))
    # Chip labels live in the `label` slot, which walk_texts does not enter.
    chip_labels = [
        getattr(getattr(c, "label", None), "value", None)
        for c in nodes
        if type(c).__name__ == "Chip"
    ]
    joined = " ".join(
        [t for t in chip_labels if t] + [c.value or "" for c in walk_texts(nodes)]
    )
    state.sites_tag_index = prev_index
    state.sites_version = prev_version
    assert "\U0001f1ec\U0001f1e7" in joined  # GB flag
    assert "\U0001f1f7\U0001f1fa" in joined  # RU flag
    assert "\U0001f1fa\U0001f1f8" in joined  # US flag


def test_windows_auth_messages_takes_no_args():
    """WindowsAuthMessages is a placeholder with no fields — passing any
    kwarg raised TypeError and crashed the unlock flow on Windows."""
    import flet_local_auth as fla

    assert fla.WindowsAuthMessages() is not None


def test_email_scan_cancel_clears_is_searching():
    """A cancelled scan must not leave is_searching stuck True (which
    disabled the Search button — 'the scan is not starting')."""
    from core.state import state
    from main import AppController

    controller = AppController(MagicMock())
    state.is_searching = False
    state.current_username = ""
    state.search_mode = "username"

    async def _cancelled(**kwargs):
        raise asyncio.CancelledError

    controller.sherlock_service = MagicMock()
    controller.sherlock_service.search = _cancelled
    controller.sherlock_service.load_sites = AsyncMock()

    async def _run():
        task = asyncio.create_task(controller.start_search("alice"))
        try:
            await asyncio.wait_for(task, timeout=20)
        except asyncio.CancelledError, Exception:
            pass

    asyncio.run(_run())
    assert state.is_searching is False, "cancelled scan left is_searching stuck"
