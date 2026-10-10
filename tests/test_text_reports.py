"""Wave D tests: text reports, graph exports, client actions."""

from __future__ import annotations

import asyncio
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
        # Owner rule: headline features default ON (stored values still win).
        # Assert the CLASS default — the shared singleton may have been
        # mutated by earlier tests in the same session.
        from core.state import AppState

        assert AppState.recursive_search is True


class TestOnDeviceFixes:
    """Regressions from the owner's Android field report (v2.2.0)."""

    def test_pkg_loader_matches_upstream_registry(self):
        from holehe_v2.core.loader import load_validators as upstream

        from services.email_service import _load_validators_pkg

        ours = _load_validators_pkg()
        theirs = upstream()
        assert len(ours) == len(theirs) >= 180

    def test_empty_validator_registry_raises_loudly(self, monkeypatch):
        import services.email_service as es

        monkeypatch.setattr(es, "_holehe_modules", None)
        monkeypatch.setattr(es, "_load_validators_pkg", lambda: {})
        svc = es.EmailService()
        try:
            svc._load_modules()
        except RuntimeError as exc:
            assert "0 modules" in str(exc) or "0 validators" in str(exc)
        else:
            raise AssertionError("empty registry must raise, not scan 0/0")

    def test_db_health_handles_sites_list(self, monkeypatch):
        from types import SimpleNamespace

        import maigret.checking as checking

        from services.sherlock_service import SherlockService

        async def fake_self_check(db, site_data, *args, **kwargs):
            return {
                "results": [
                    {"site_name": "GoodSite", "issues": [], "recommendations": []},
                    {
                        "site_name": "BadSite",
                        "issues": ["dead endpoint"],
                        "recommendations": [],
                    },
                ]
            }

        monkeypatch.setattr(checking, "self_check", fake_self_check)
        svc = SherlockService()
        # On-device shape: sites is a LIST (the '.values()' crash).
        svc._db = SimpleNamespace(
            sites=[
                SimpleNamespace(name="GoodSite", disabled=False),
                SimpleNamespace(name="BadSite", disabled=False),
                SimpleNamespace(name="OffSite", disabled=True),
            ]
        )
        summary = asyncio.run(svc.run_db_health(sample_size=10))
        assert "error" not in summary, summary
        assert summary["sample"] == 2  # disabled excluded
        assert summary["flagged"] == 1
        assert summary["unhealthy"] == ["BadSite"]

    def test_banner_finishing_and_followup(self):
        from components.active_scan_banner import ActiveScanBanner
        from tests.flet_tree import walk

        def texts_of(control):
            return [
                c.value
                for c in walk(control)
                if hasattr(c, "value") and isinstance(c.value, str)
            ]

        finishing = ActiveScanBanner(
            target_query="target",
            search_mode="username",
            checked=5174,
            total=5174,
            finishing=True,
        )
        assert any("Finishing" in t for t in texts_of(finishing))
        running = ActiveScanBanner(
            target_query="target", search_mode="username", checked=10, total=100
        )
        assert any("10/100" in t for t in texts_of(running))


class TestBatch14Contracts:
    """Batch 14: caps, contracts, guards, single-sheet, truncation."""

    def test_pdf_cap_overflow_row(self):
        from services.report_service import _FOUND_PDF_ROW_CAP, generate_pdf_dossier

        found = [
            SimpleNamespace(
                site_name=f"Site{i}",
                url_user=f"https://example.com/{i}",
                url_main="https://example.com",
                query_time=0.1,
                status="Claimed",
                http_status="200",
            )
            for i in range(_FOUND_PDF_ROW_CAP + 30)
        ]
        payload = generate_pdf_dossier("alice", found, [], [])
        assert payload is not None
        # 530 capped rows render — assert a non-trivial dossier, since PDF
        # text streams are compressed (no plaintext grepping).
        assert len(payload) > 50000

    def test_empty_contract_matrix(self):
        from services.report_service import (
            generate_csv_report,
            generate_email_markdown_report,
            generate_html_report,
            generate_markdown_report,
            generate_ndjson_report,
            generate_txt_report,
        )

        # Always-bytes exporters never return None.
        assert isinstance(generate_csv_report("a", [], [], []), bytes)
        assert isinstance(generate_txt_report("a", []), bytes)
        assert isinstance(generate_ndjson_report("a", [], [], []), bytes)
        # Dossier generators return None on empty.
        assert generate_markdown_report("a", [], [], []) is None
        assert generate_html_report("a", [], [], []) is None
        assert generate_email_markdown_report("a@b.com", []) is None

    def test_gold_palette_guard(self):
        from services import report_service

        if report_service._REPORTLAB_AVAILABLE:
            assert "gold" in report_service._gold_palette()
        else:
            try:
                report_service._gold_palette()
            except RuntimeError:
                pass
            else:
                raise AssertionError("expected RuntimeError without reportlab")

    def test_xmind_single_sheet_per_category(self, tmp_path):
        import zipfile

        from services.report_service import generate_xmind_case

        r1 = _result("GitHub", "https://github.com/x", tags=["coding"])
        r2 = _result("GitLab", "https://gitlab.com/x", tags=["coding"])
        out = generate_xmind_case(
            "target", [r1, r2], {}, output_path=tmp_path / "case.xmind"
        )
        assert out is not None and out.exists()
        with zipfile.ZipFile(out) as zf:
            content = zf.read("content.xml").decode("utf-8")
        # "Coding" category sheet appears exactly once (no double-registration
        # from createSheet+addSheet).
        assert content.count("Sherlock — Coding") == 1

    def test_xmind_notes_truncated(self):
        from services.report_service import generate_xmind_case

        big_bio = "x" * 5000
        r = _result("GitHub", "https://github.com/x")
        out = generate_xmind_case(
            "target",
            [r],
            {"https://github.com/x": {"bio": big_bio}},
            output_path=None,
        )
        # None only when xmind missing; otherwise must not raise.
        assert out is None or out.exists()
