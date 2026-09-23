"""Wave D tests: text reports, graph exports, biometric fallback, actions."""

from __future__ import annotations

from types import SimpleNamespace


def _result(site="GitHub", url="https://github.com/x", tags=None):
    return SimpleNamespace(
        site_name=site,
        url_user=url,
        url_main="https://example.com",
        query_time=1.23,
        context=None,
        error_type=None,
        tags=tags or ["coding"],
    )


class TestMarkdownHtmlReports:
    """P3-5/P4-8: username-mode Markdown + HTML dossiers."""

    def test_markdown_contains_table_and_enrichment(self):
        from services.report_service import generate_markdown_report

        r = _result()
        payload = generate_markdown_report(
            "target",
            [r],
            [],
            [],
            {"https://github.com/x": {"bio": "hello", "name": "Target"}},
            5203,
            1,
        )
        assert payload is not None
        text = payload.decode("utf-8")
        assert "# Sherlock Intelligence Dossier — target" in text
        assert "github.com/x" in text
        assert "Profile Enrichment Highlights" in text
        assert "Bio: hello" in text

    def test_html_contains_gold_theme_and_links(self):
        from services.report_service import generate_html_report

        r = _result()
        err = SimpleNamespace(
            site_name="Blocked",
            url_user=None,
            url_main=None,
            query_time=None,
            context="Cloudflare challenge",
            error_type="Bot protection",
            tags=[],
        )
        payload = generate_html_report("target", [r], [], [err], {}, 5203, 1)
        assert payload is not None
        html = payload.decode("utf-8")
        assert "<table>" in html
        assert 'href="https://github.com/x"' in html
        assert "Cloudflare challenge" in html

    def test_empty_report_returns_none(self):
        from services.report_service import (
            generate_html_report,
            generate_markdown_report,
        )

        assert generate_markdown_report("t", [], [], [], {}, 0, 0) is None
        assert generate_html_report("t", [], [], [], {}, 0, 0) is None


class TestGraphExports:
    """P3-5 cypher + P4-6 pyvis viewer + P4-7 communities."""

    def test_cypher_export(self):
        from services.graph_service import build_identity_graph, export_cypher

        r = _result()
        G = build_identity_graph(
            "target",
            [r],
            {"https://github.com/x": {"email": "a@b.c", "fullname": "Some Name"}},
            [],
        )
        cy = export_cypher(G)
        assert "MERGE" in cy
        assert "LINK" in cy
        assert "shared" not in cy.splitlines()[0]  # header comment only
        assert "a@b.c" in cy  # evidence node emitted

    def test_communities_and_bridges(self):
        from services.graph_service import build_identity_graph, get_graph_analytics

        r1 = _result("GitHub", "https://github.com/x")
        r2 = _result("Reddit", "https://reddit.com/x")
        # Shared fullname links both accounts through the name evidence node.
        G = build_identity_graph(
            "target",
            [r1, r2],
            {
                "https://github.com/x": {"fullname": "Shared Person"},
                "https://reddit.com/x": {"fullname": "Shared Person"},
            },
            [],
        )
        an = get_graph_analytics(G)
        assert "communities" in an and "bridge_nodes" in an
        assert an["nodes"] >= 4
        # The shared-name node must join both accounts into one community.
        big = an["communities"][0] if an["communities"] else {"size": 1}
        assert big["size"] >= 3

    def test_pyvis_html_written(self, tmp_path):
        from services.graph_service import build_identity_graph, export_pyvis_html

        G = build_identity_graph("target", [_result()], {}, [])
        out = export_pyvis_html(G, tmp_path / "graph.html")
        assert out is not None and out.exists()
        content = out.read_text(encoding="utf-8")
        assert "network" in content.lower()
        assert len(content) > 5000  # inline CDN assets present


class TestXmindUpgrade:
    """P4-9/P4-11: relationships, fold, category sheets."""

    def test_case_file_generation_with_evidence(self, tmp_path):
        from services.report_service import generate_xmind_case

        r1 = _result("GitHub", "https://github.com/x")
        r2 = _result("Reddit", "https://reddit.com/x")
        enrich = {
            "https://github.com/x": {"email": "same@evidence.io"},
            "https://reddit.com/x": {"email": "same@evidence.io"},
        }
        out = generate_xmind_case(
            "target", [r1, r2], enrich, output_path=tmp_path / "case.xmind"
        )
        assert out is not None and out.exists()
        assert out.stat().st_size > 500  # content.json + metadata written


class TestBiometricFallback:
    """P1-4: honest False outside a live app or when the dep is missing."""

    def test_authenticate_unavailable(self, monkeypatch):
        import asyncio

        import services.biometric_service as bs

        monkeypatch.setattr(bs, "_AUTH_AVAILABLE", False)
        assert asyncio.run(bs.authenticate()) is False

    def test_authenticate_without_page(self, monkeypatch):
        import asyncio

        import services.biometric_service as bs

        monkeypatch.setattr(bs, "_AUTH_AVAILABLE", True)

        class _Ctx:
            page = None

        monkeypatch.setattr(bs, "_fla", SimpleNamespace(LocalAuthException=Exception))
        import flet

        monkeypatch.setattr(flet, "context", _Ctx(), raising=False)
        # context is imported inside the function from flet.controls.context
        import flet.controls.context as fctx

        monkeypatch.setattr(
            fctx, "page", property(lambda self: (_ for _ in ()).throw(RuntimeError("x"))), raising=False
        )
        # Simpler: page property raising RuntimeError is flet's own behavior —
        # just verify the no-auth-availability path above and the page-None path:
        assert asyncio.run(bs.authenticate()) in (False,)


class TestClientActions:
    """P1-3: open_url_action binds only inside a live app."""

    def test_returns_none_without_page(self):
        from core.actions import open_url_action

        # Test harness has no flet page context — must be None, not raise.
        assert open_url_action("https://example.com") is None


class TestStateDefaults:
    """New Wave-D state keys exist with safe defaults."""

    def test_new_defaults(self):
        from core.state import state

        assert state.search_keywords == ""
        assert state.deep_enrich is False
        assert state.cookies_path == ""
        assert state.i2p_proxy == ""
        assert state.check_domains is False
        assert state.unhealthy_sites is None
        assert state.biometric_lock is False
        assert state.history_unlocked is False
        # Owner rule: headline features default ON (stored values still win).
        # Assert the CLASS default — the shared singleton may have been
        # mutated by earlier tests in the same session.
        from core.state import AppState

        assert AppState.recursive_search is True
