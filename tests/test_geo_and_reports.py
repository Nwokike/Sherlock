"""Comprehensive unit tests for Geographic Intelligence, Reporting, and Graph Analytics."""

from types import SimpleNamespace

from core.geo_utils import get_country_by_tag, get_site_country, resolve_location
from core.logger_handler import get_telemetry_snapshot
from services.graph_service import (
    build_identity_graph,
    export_cytoscape_json,
    export_node_link_json,
    get_graph_analytics,
)
from services.report_service import generate_pdf_dossier, generate_xmind_case


# ── Geographic Intelligence (pycountry) ───────────────────────────────


def test_get_country_by_tag():
    us = get_country_by_tag("us")
    assert us is not None
    assert us.alpha_2 == "US"
    assert us.name == "United States"
    assert us.flag == "🇺🇸"

    ng = get_country_by_tag("ng")
    assert ng is not None
    assert ng.alpha_2 == "NG"
    assert ng.flag == "🇳🇬"

    assert get_country_by_tag("xyz") is None
    assert get_country_by_tag("") is None


def test_get_site_country():
    tags = ("coding", "us", "social")
    c = get_site_country(tags)
    assert c is not None
    assert c.alpha_2 == "US"

    no_country_tags = ("coding", "forum", "crypto")
    assert get_site_country(no_country_tags) is None


def test_resolve_location():
    loc1 = resolve_location("Berlin, Germany")
    assert loc1 is not None
    assert loc1.alpha_2 == "DE"
    assert loc1.flag == "🇩🇪"

    loc2 = resolve_location("Tokyo, Japan")
    assert loc2 is not None
    assert loc2.alpha_2 == "JP"

    loc3 = resolve_location("San Francisco, CA, USA")
    assert loc3 is not None
    assert loc3.alpha_2 == "US"

    loc4 = resolve_location("Lagos, Nigeria")
    assert loc4 is not None
    assert loc4.alpha_2 == "NG"


# ── Report Generation (reportlab + xmind) ─────────────────────────────


def test_generate_pdf_dossier():
    found = [
        SimpleNamespace(
            site_name="GitHub",
            url_user="https://github.com/alice",
            url_main="https://github.com",
            status="Claimed",
            query_time=0.42,
            tags=["coding"],
            ids_data={"name": "Alice Smith"},
        ),
        SimpleNamespace(
            site_name="Twitter",
            url_user="https://twitter.com/alice",
            url_main="https://twitter.com",
            status="Claimed",
            query_time=0.35,
            tags=["social"],
            ids_data=None,
        ),
    ]
    not_found = [
        SimpleNamespace(
            site_name="Reddit",
            url_user=None,
            url_main="https://reddit.com",
            status="Available",
            query_time=0.2,
            tags=["social"],
            ids_data=None,
        )
    ]
    enrichments = {
        "https://github.com/alice": {
            "name": "Alice Smith",
            "bio": "Open Source Engineer",
            "location": "Berlin, Germany",
            "follower_count": 250,
        }
    }

    pdf = generate_pdf_dossier(
        username="alice",
        found=found,
        not_found=not_found,
        errors=[],
        enrichments=enrichments,
        total_sites=3302,
        checked_sites=3,
    )
    assert pdf is not None
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_generate_xmind_case(tmp_path):
    found = [
        SimpleNamespace(
            site_name="GitHub",
            url_user="https://github.com/alice",
            url_main="https://github.com",
            status="Claimed",
            tags=["coding"],
            ids_data={"name": "Alice Smith"},
        ),
        SimpleNamespace(
            site_name="Instagram",
            url_user="https://instagram.com/alice",
            url_main="https://instagram.com",
            status="Claimed",
            tags=["social"],
            ids_data=None,
        ),
    ]
    enrichments = {
        "https://github.com/alice": {
            "name": "Alice Smith",
            "bio": "Software Architect",
        }
    }

    out_file = tmp_path / "test_case.xmind"
    result_path = generate_xmind_case(
        username="alice",
        found=found,
        enrichments=enrichments,
        output_path=out_file,
    )
    assert result_path is not None
    assert result_path.exists()
    assert result_path.stat().st_size > 500


# ── Identity Relationship Graph (networkx) ───────────────────────────


def test_identity_graph_and_analytics():
    found = [
        SimpleNamespace(
            site_name="GitHub",
            url_user="https://github.com/alice",
            url_main="https://github.com",
        ),
        SimpleNamespace(
            site_name="Twitter",
            url_user="https://twitter.com/alice",
            url_main="https://twitter.com",
        ),
    ]
    enrichments = {
        "https://github.com/alice": {
            "name": "Alice Smith",
            "email": "alice@example.com",
            "links": ["https://alicesmith.dev"],
        },
        "https://twitter.com/alice": {
            "fullname": "Alice Smith",
        },
    }
    email_results = [
        {
            "name": "adobe",
            "domain": "adobe.com",
            "exists": True,
            "emailrecovery": "a***e@example.com",
            "phoneNumber": "***-1234",
        }
    ]

    G = build_identity_graph("alice", found, enrichments, email_results)
    assert G is not None
    assert len(G.nodes) >= 6
    assert len(G.edges) >= 6

    analytics = get_graph_analytics(G)
    assert analytics["nodes"] == len(G.nodes)
    assert analytics["edges"] == len(G.edges)
    assert analytics["components"] >= 1
    assert len(analytics["top_canonical_nodes"]) > 0

    cy = export_cytoscape_json(G)
    assert cy is not None
    assert "elements" in cy
    assert "nodes" in cy["elements"]
    assert "edges" in cy["elements"]

    nl = export_node_link_json(G)
    assert nl is not None
    assert "nodes" in nl
    assert "links" in nl


# ── Live Terminal Telemetry (psutil) ──────────────────────────────────


def test_telemetry_snapshot():
    snap = get_telemetry_snapshot()
    assert isinstance(snap, str)
    assert len(snap) > 5
    assert "CPU:" in snap or "RAM:" in snap or "App RSS:" in snap
