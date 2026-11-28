"""Phone mode parity — state, guards, results labels, history, exports, gate."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import flet as ft
import pytest

from core.constants import MODE_PHONE, MODE_USERNAME
from core.state import state
from main import AppController
from services.phone_service import PhoneResult, PhoneSearchProgress


@pytest.fixture(autouse=True)
def _restore_state():
    saved = {
        "search_mode": state.search_mode,
        "is_searching": state.is_searching,
        "current_username": state.current_username,
        "search_progress": state.search_progress,
        "search_targets": list(state.search_targets or []),
        "phone_results": list(state.phone_results or []),
        "phone_results_number": state.phone_results_number,
        "phone_found_count": state.phone_found_count,
        "phone_total_modules": state.phone_total_modules,
        "email_results": list(state.email_results or []),
        "email_results_address": state.email_results_address,
        "search_keywords": state.search_keywords,
    }
    yield
    for key, value in saved.items():
        if key in ("search_targets", "phone_results", "email_results"):
            getattr(state, key)[:] = value
        else:
            setattr(state, key, value)


def _controller(fake_page) -> AppController:
    controller = AppController(fake_page)
    controller._enrich_queue = None
    return controller


def _phone_row(name: str = "Facebook", exists: bool = True) -> dict:
    return {
        "name": name,
        "domain": "facebook.com",
        "method": "",
        "exists": exists,
        "rateLimit": False,
        "unavailable": False,
        "frequent_rate_limit": False,
        "emailrecovery": "j***e@gmail.com" if exists else None,
        "phoneNumber": "+14155552671",
        "others": {
            "extra": {"name": "Jane"} if exists else {},
            "media": {"avatar": "https://cdn.example/a.jpg"} if exists else {},
            "url": "https://facebook.com",
            "message": "",
            "category": "Social",
        },
    }


def test_state_reset_clears_phone():
    state.phone_results[:] = [_phone_row()]
    state.phone_results_number = "+14155552671"
    state.phone_found_count = 1
    state.phone_total_modules = 5
    state.reset_search()
    assert list(state.phone_results) == []
    assert state.phone_results_number == ""
    assert state.phone_found_count == 0
    assert state.phone_total_modules == 0


def test_apply_progress_admits_phone_and_drops_other_modes(fake_page):
    controller = _controller(fake_page)
    identity = "+14155552671"
    state.search_mode = MODE_PHONE
    state.current_username = identity
    state.search_targets = []
    state.search_progress = None

    tick = PhoneSearchProgress(
        phone=identity, total_modules=5, checked_modules=1, is_running=True
    )
    asyncio.run(controller._apply_progress(tick))
    controller._flush_pending_progress()
    assert state.search_progress is tick

    # An email tick while in phone mode must be dropped, not replace progress.
    state.search_progress = None
    from services.email_service import EmailSearchProgress

    email_tick = EmailSearchProgress(
        email="a@b.com", total_modules=2, checked_modules=1, is_running=True
    )
    asyncio.run(controller._apply_progress(email_tick))
    assert state.search_progress is None

    # A username tick while in phone mode must be dropped too.
    from services.sherlock_service import SearchProgress

    asyncio.run(
        controller._apply_progress(
            SearchProgress(username="alice", total_sites=10, checked_sites=1)
        )
    )
    assert state.search_progress is None


def test_phone_scan_completes_and_fills_state(fake_page):
    controller = _controller(fake_page)
    controller.storage = None
    fake_service = MagicMock()
    fake_service.check_available.return_value = (True, "")

    result = PhoneSearchProgress(
        phone="+14155552671",
        total_modules=2,
        checked_modules=2,
        found=[PhoneResult(name="Facebook", exists=True, phone="+14155552671")],
        not_found=[PhoneResult(name="Amazon", exists=False, phone="+14155552671")],
        is_running=False,
    )

    async def _search(**_kwargs):
        return result

    fake_service.search = _search
    controller.phone_service = fake_service
    state.is_online = True

    asyncio.run(controller.start_phone_search("+14155552671"))

    assert fake_page.dialogs == [], "phone scans must not open a first-use modal"
    assert state.search_mode == MODE_PHONE
    assert state.phone_results_number == "+14155552671"
    assert state.phone_found_count == 1
    assert state.phone_not_found_count == 1
    assert state.phone_total_modules == 2
    assert {r["name"] for r in state.phone_results} == {"Facebook", "Amazon"}


def test_phone_unavailable_reports_concrete_reason(fake_page, caplog):
    controller = _controller(fake_page)
    fake_service = MagicMock()
    reason = "phonsint validator catalog is empty — Android package extraction is missing"
    fake_service.check_available.return_value = (False, reason)
    controller.phone_service = fake_service
    snacks: list[str] = []
    controller._show_snack = lambda message, duration=0: snacks.append(message)

    asyncio.run(controller.start_phone_search("+14155552671"))

    assert snacks == [f"Phone lookup unavailable: {reason}"]
    assert f"Phone engine unavailable: {reason}" in caplog.text
    assert fake_service.search.call_count == 0


def test_cached_phone_result_reopens(fake_page):
    controller = _controller(fake_page)
    calls: list = []
    controller._controller_methods = MagicMock()
    controller._controller_methods.show_results = lambda: calls.append(1)
    state.set_cached_result(
        MODE_PHONE,
        "+14155552671",
        {
            "phone_results": [_phone_row()],
            "total": 5,
            "checked": 5,
        },
    )
    assert controller.open_cached_result("+14155552671", MODE_PHONE) is True
    assert state.search_mode == MODE_PHONE
    assert state.phone_results_number == "+14155552671"
    assert state.phone_results[0]["name"] == "Facebook"
    assert isinstance(state.search_progress, PhoneSearchProgress)
    assert state.phone_total_modules == 5
    assert calls == [1]


def test_history_infers_phone_mode():
    from screens.history_screen import _infer_mode

    assert _infer_mode({"mode": MODE_PHONE}, "+14155552671") == MODE_PHONE


def test_phone_exports_use_phone_rows():
    from app_shell import _email_export_bytes

    state.search_mode = MODE_PHONE
    state.phone_results[:] = [_phone_row()]
    state.phone_results_number = "+14155552671"

    csv_text = _email_export_bytes("csv", state).decode("utf-8")
    assert csv_text.splitlines()[0].startswith("phone")
    assert "+14155552671" in csv_text

    payload = json.loads(_email_export_bytes("json", state).decode("utf-8"))
    assert payload["phone"] == "+14155552671"
    assert payload["found"] == 1

    txt = _email_export_bytes("txt", state).decode("utf-8")
    assert txt.startswith("Sherlock phone OSINT")


def test_phone_exports_include_identity_detail_and_no_gravatar():
    from services.report_service import (
        generate_email_html_report,
        generate_email_markdown_report,
    )

    row = _phone_row()
    markdown = generate_email_markdown_report("+14155552671", [row], label="phone")
    assert markdown is not None
    text = markdown.decode("utf-8")
    assert "Phone OSINT" in text
    assert "Jane" in text

    html = generate_email_html_report("+14155552671", [row], label="phone")
    assert html is not None
    body = html.decode("utf-8")
    assert "Jane" in body
    assert "gravatar.com" not in body


def _nodes(comp) -> list:
    from flet.components.component import Component, Renderer

    from state.app_state import AppStateCtx
    from state.controller_ctx import ControllerMethods, ControllerMethodsCtx

    root = Renderer().render(
        lambda: ControllerMethodsCtx(ControllerMethods(), lambda: AppStateCtx(state, comp))
    )
    out: list = []

    def expand(node):
        out.append(node)
        if isinstance(node, Component):
            node.before_update()
            built = getattr(node, "_b", None)
            if built is not None:
                expand(built)
        elif isinstance(node, list):
            for item in node:
                expand(item)
        else:
            for child in getattr(node, "controls", None) or []:
                expand(child)
            content = getattr(node, "content", None)
            if content is not None and not isinstance(content, str):
                expand(content)
            for attr in ("label", "leading", "trailing", "title", "subtitle"):
                value = getattr(node, attr, None)
                if value is not None and not isinstance(value, str):
                    expand(value)

    expand(root)
    return out


def _texts(nodes) -> list[str]:
    return [n.value for n in nodes if hasattr(n, "value") and isinstance(n.value, str)]


def test_phone_results_screen_labels():
    from screens.results_screen import ResultsScreen

    state.reset_search()
    state.search_mode = MODE_PHONE
    state.current_username = "+14155552671"
    state.phone_results_number = "+14155552671"
    state.phone_total_modules = 1
    state.phone_results[:] = [_phone_row()]
    state.is_searching = False

    texts = _texts(_nodes(lambda: ResultsScreen()))
    assert any("Not Registered" in t for t in texts)
    assert any(t == "Found" for t in texts)


def test_home_has_phone_pill_and_dropdowns():
    from screens.home_screen import HomeScreen

    state.search_mode = MODE_PHONE
    state.is_searching = False
    nodes = _nodes(lambda: HomeScreen())
    texts = _texts(nodes)
    assert any(t == "Phone" for t in texts)
    assert any("BETA" in t for t in texts)
    assert any("Search Number" in t for t in texts)
    assert not any(t == "Search Networks" for t in texts)
    assert not any("No SMS sent" in t for t in texts)
    menus = [node for node in nodes if isinstance(node, ft.PopupMenuButton)]
    assert len(menus) == 1, "only Region should be a popup dropdown"
    assert any("Concurrency: 15" in t for t in texts)
    assert any("15s Timeout" in t for t in texts)
    assert any(t == "Auto" for t in texts), "Region pill must show the active Auto choice"


def test_settings_has_phone_card():
    from screens.settings_screen import SettingsScreen

    state.phone_concurrency = 17
    nodes = _nodes(lambda: SettingsScreen())
    texts = _texts(nodes)
    for row in (
        "Phone Concurrency",
        "Default Region",
        "Checked Platforms",
        "Silent Operation",
    ):
        assert any(row in t for t in texts), f"missing settings row: {row}"
    assert not any("Phone Mode (beta)" in t for t in texts)
    assert any(isinstance(node, ft.PopupMenuButton) for node in nodes)
    assert any(
        isinstance(node, ft.Slider) and node.label == "17" for node in nodes
    ), "phone concurrency must keep its original slider"


def test_scan_finished_phone_noun():
    from services import scan_notify as sn

    class _Svc:
        def __init__(self):
            self.shown = []

        async def stop_foreground_service(self):
            pass

        async def cancel(self, _id):
            pass

        async def show(self, _id, **kwargs):
            self.shown.append(kwargs)

    notifier = sn.ScanNotifier(MagicMock())
    notifier._service = _Svc()
    notifier._kind = "phone"
    notifier._target = "+14155552671"
    asyncio.run(notifier.scan_finished(2, 5))
    title = notifier._service.shown[-1]["title"]
    assert "2 matches" in title


def test_phone_detail_dialog_builds(fake_page):
    from components.profile_detail_dialog import show_profile_detail_dialog

    show_profile_detail_dialog(
        page=fake_page,
        site_name="Facebook",
        status="Claimed",
        mode="phone",
        target_query="+14155552671",
        url_main="https://facebook.com",
        phone_number="+14155552671",
        others={
            "extra": {"email": "j***e@gmail.com", "name": "Jane"},
            "media": {"avatar": "https://cdn.example/a.jpg"},
            "category": "Social",
            "message": "",
        },
    )
    assert fake_page.dialogs, "the phone dossier must open"


def test_shade_cancel_routes_by_mode(fake_page):
    from services.email_service import EmailSearchProgress

    controller = _controller(fake_page)
    called: list[str] = []
    controller.cancel_phone_search = lambda: called.append("phone")
    controller.cancel_email_search = lambda: called.append("email")
    controller.cancel_search = lambda: called.append("username")

    state.search_progress = PhoneSearchProgress(phone="+1", is_running=True)
    controller._cancel_active_scan()
    assert called == ["phone"]

    state.search_progress = EmailSearchProgress(email="a@b.com", is_running=True)
    controller._cancel_active_scan()
    assert called[-1] == "email"

    state.search_progress = None
    state.search_mode = MODE_USERNAME
    controller._cancel_active_scan()
    assert called[-1] == "username"


def test_phone_mode_constant():
    assert MODE_PHONE == "phone"
