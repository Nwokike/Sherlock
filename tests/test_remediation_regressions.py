"""Behavioral regressions for the 2.3.0 remediation (not structure theater)."""

from __future__ import annotations

import asyncio

import curl_cffi.requests


def test_one_storage_service_per_page_prevents_lost_updates(tmp_path, fake_page, monkeypatch):
    """13 independent instances rewrote the whole file and erased each other."""
    import services.storage_service as mod
    from services.storage_service import StorageService

    # A real flet Page has `web`; the harness default is neither, which our
    # detection treats as web. Make this explicitly file-backed.
    fake_page.web = False
    fake_page.session_id = None
    monkeypatch.setattr(mod, "get_storage_dir", lambda: tmp_path / "data")
    if hasattr(fake_page, mod.StorageService._PAGE_ATTR):
        delattr(fake_page, mod.StorageService._PAGE_ATTR)
    first = StorageService.for_page(fake_page)
    second = StorageService.for_page(fake_page)
    assert first is second

    async def run():
        await first.set("theme", "dark")
        await first.flush()
        await second.set("timeout", "30")
        await second.flush()

    asyncio.run(run())
    data = (tmp_path / "data" / "storage.json").read_text()
    assert "dark" in data and "30" in data, "a screen's setting was overwritten"


def test_impersonate_wrapper_accepts_params_and_json(monkeypatch):
    """5 holehe validators were permanently broken by upstream kwargs."""
    import holehe_v2.core.impersonate as imp

    import services.email_service  # noqa: F401 — installs the wrapper at import time

    captured: list = []

    class _Session:
        def __init__(self, impersonate=None):
            captured.append(("session", impersonate))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, **kwargs):
            captured.append((method, url, kwargs))
            return "ok"

    monkeypatch.setattr(curl_cffi.requests, "AsyncSession", _Session)

    async def run():
        return await imp.impersonate_request_async(
            "https://example.com/search",
            "POST",
            params={"q": "1"},
            json={"a": 2},
        )

    assert asyncio.run(run()) == "ok"
    call = next(c for c in captured if c[0] == "POST")
    assert call[2]["params"] == {"q": "1"}
    assert call[2]["json"] == {"a": 2}


def test_markdown_report_escapes_html_payloads():
    from services.report_service import generate_markdown_report
    from services.sherlock_service import SiteResult

    row = SiteResult(
        site_name="<img src=x onerror=alert(1)>",
        url_main="",
        url_user="https://example.com/u",
        status="Claimed",
        http_status="200",
    )
    report = generate_markdown_report("alice", [row], [], [])
    assert report is not None
    text = report.decode()
    assert "<img" not in text
    assert "&lt;img" in text



def test_results_screen_banners_are_pooled_across_renders(monkeypatch):
    """Reverting any screen banner to build_banner_ad() must fail this."""
    from flet.components.component import Renderer

    import components.banner_ad as banner_mod
    from core.constants import MODE_USERNAME
    from core.state import state
    from screens.results_screen import ResultsScreen
    from services.sherlock_service import SiteResult
    from state.app_state import AppStateCtx
    from state.controller_ctx import ControllerMethods, ControllerMethodsCtx

    builds = []
    real_build = banner_mod.build_banner_ad

    def counting_build(page=None):
        builds.append(1)
        return real_build(page)

    monkeypatch.setattr(banner_mod, "build_banner_ad", counting_build)
    banner_mod.clear_banner_pool()
    saved = (state.search_mode, state.is_searching, state.search_progress,
             state.last_results, state.last_results_username)
    try:
        state.search_mode = MODE_USERNAME
        state.is_searching = False
        state.search_progress = None
        state.last_results_username = "alice"
        state.last_results = {
            "GitHub": SiteResult(
                site_name="GitHub", url_main="", url_user="https://github.com/alice",
                status="Claimed", http_status="200",
            )
        }

        def render():
            r = Renderer()
            return r.render(
                lambda: ControllerMethodsCtx(
                    ControllerMethods(), lambda: AppStateCtx(state, ResultsScreen)
                )
            )

        render()
        first = len(builds)
        render()
        assert len(builds) == first, "a re-render constructed new banner ads"
    finally:
        (state.search_mode, state.is_searching, state.search_progress,
         state.last_results, state.last_results_username) = saved
        banner_mod.clear_banner_pool()


def test_web_storage_keeps_dirty_when_set_fails(monkeypatch, tmp_path):
    import flet as ft

    import services.storage_service as mod

    class _Prefs:
        async def get(self, key):
            return None

        async def set(self, key, value):
            return False  # native write failed

    monkeypatch.setattr(ft, "SharedPreferences", _Prefs)

    class _Page:
        web = True
        session_id = "s"

        def __init__(self):
            self.services = []

    svc = mod.StorageService(_Page(), data_dir=tmp_path)
    assert svc._is_web is True

    async def run():
        await svc.set("k", "v")
        await svc.flush()

    asyncio.run(run())
    assert svc._dirty is True, "a failed web write falsely reported success"


def test_email_search_passes_run_generation(monkeypatch):
    import services.email_service as mod

    captured = {}

    async def fake_to_thread(fn, *args, **kwargs):
        captured["args"] = args
        from services.email_service import EmailSearchProgress
        return EmailSearchProgress(email="a@b.com")

    monkeypatch.setattr(mod.asyncio, "to_thread", fake_to_thread)
    svc = mod.EmailService()
    before = svc._run_id

    async def run():
        return await svc.search("a@b.com", lambda p: None)

    asyncio.run(run())
    assert svc._run_id == before + 1
    assert captured["args"][-1] == svc._run_id


def test_email_classifier_catches_real_block_messages():
    from services.email_service import _is_rate_limited

    assert _is_rate_limited("Blocked by Walmart bot protection (412)")
    assert _is_rate_limited("HTTP 429 too many requests")
    assert not _is_rate_limited("Connection timed out")


def test_xmind_enriched_row_does_not_crash_on_missing_marker(tmp_path):
    from services.report_service import generate_xmind_case
    from services.sherlock_service import SiteResult

    row = SiteResult(
        site_name="GitHub", url_main="", url_user="https://github.com/alice",
        status="Claimed", http_status="200", tags=["social"],
    )
    out = generate_xmind_case(
        "alice", [row], output_path=tmp_path / "case.xmind",
        enrichments={"https://github.com/alice": {"bio": "hi"}},
    )
    assert out is not None and out.exists()


def test_pagerank_falls_back_without_scipy(monkeypatch):
    import networkx as nx

    import services.graph_service as gs

    def boom(*a, **k):
        raise ModuleNotFoundError("No module named 'numpy'")

    monkeypatch.setattr(nx, "pagerank", boom)
    g = nx.Graph()
    g.add_edge("target:alice", "acc:github", weight=0.9)
    analytics = gs.get_graph_analytics(g)
    assert analytics["top_pagerank"], "PageRank fallback produced nothing"


def test_pyvis_kinds_filter_skips_dangling_edges(tmp_path):
    import networkx as nx

    from services.graph_service import export_pyvis_html

    g = nx.Graph()
    g.add_node("target:alice", kind="target", label="alice")
    g.add_node("acc:github", kind="account", label="GitHub")
    g.add_edge("target:alice", "acc:github", reason="member")
    out = export_pyvis_html(g, tmp_path / "g.html", kinds={"account"})
    assert out is not None and out.exists()


def test_human_date_eight_digit_is_year_only():
    from core.format import human_date

    assert human_date("20190401") == "2019"
    assert human_date("2019") == "2019"


def test_host_semaphores_are_per_event_loop():
    import services.enrich_service as mod

    async def grab():
        return mod._host_sem("https://example.com/x")

    a = asyncio.run(grab())
    b = asyncio.run(grab())
    assert a is not b, "semaphore reused across event loops"
