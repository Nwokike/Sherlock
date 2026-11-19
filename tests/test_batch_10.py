"""Regression tests for Fix Batch 10 (P2 enrichment payoff)."""

import asyncio


def _site(name, url, status="Claimed"):
    from services.sherlock_service import SiteResult

    return SiteResult(
        site_name=name,
        url_main="https://example.com",
        url_user=url,
        status=status,
        http_status="200",
        query_time=0.1,
    )


def test_card_renders_extra_identity_rows():
    from components.result_card import ResultCard
    from tests.flet_tree import walk_texts

    tree = ResultCard(
        site_name="GitHub",
        status="Claimed",
        url_user="https://github.com/octocat",
        others={
            "extra": {"login": "octocat", "bio": "Hello world", "timezone": "UTC"},
            "media": {},
        },
    )
    texts = " ".join(t.value or "" for t in walk_texts(tree))
    assert "octocat" in texts
    assert "Hello world" in texts


def test_email_reports_prefer_identity_detail():
    from services.report_service import (
        generate_email_html_report,
        generate_email_markdown_report,
    )

    rows = [
        {
            "name": "GitHub",
            "domain": "github.com",
            "exists": True,
            "rateLimit": False,
            "unavailable": False,
            "others": {
                "message": "Account found",
                "extra": {"login": "octocat", "bio": "Dev"},
                "media": {"avatar": "https://avatars.example.com/u/1"},
            },
        }
    ]
    md = generate_email_markdown_report("a@b.com", rows).decode("utf-8")
    assert "octocat" in md or "Dev" in md
    html = generate_email_html_report("a@b.com", rows)
    assert html is not None
    text = html.decode("utf-8")
    assert "octocat" in text or "Dev" in text
    assert "avatars.example.com" in text


def test_graph_linked_identity_edges():
    from services.graph_service import build_identity_graph

    email_results = [
        {
            "name": "GitHub",
            "domain": "github.com",
            "exists": True,
            "emailrecovery": None,
            "phoneNumber": None,
            "others": {
                "extra": {
                    "verified_accounts": ["twitter:octocat"],
                    "websites": ["https://octocat.dev"],
                },
                "media": {},
            },
        }
    ]
    graph = build_identity_graph(
        username="alice", found_accounts=[], email_results=email_results
    )
    assert graph is not None
    reasons = {d.get("reason") for _, _, d in graph.edges(data=True)}
    assert "linked_identity" in reasons


def test_holehe_usernames_merge():
    from services.sherlock_service import extract_holehe_usernames

    rows = [
        {"exists": True, "others": {"extra": {"login": "octocat"}}},
        {"exists": True, "others": {"extra": {"username": "OctoCat"}}},  # dupe
        {"exists": False, "others": {"extra": {"login": "ghost"}}},  # not found
        {"exists": True, "others": {}},  # nothing
    ]
    assert extract_holehe_usernames(rows) == ["octocat"]
    assert extract_holehe_usernames([]) == []
    assert extract_holehe_usernames(None) == []


def test_csv_txt_ndjson_shapes():
    from services.report_service import (
        generate_csv_report,
        generate_ndjson_report,
        generate_txt_report,
    )

    found = [_site("GitHub", "https://github.com/alice")]
    csv_text = generate_csv_report("alice", found, [], []).decode("utf-8")
    assert csv_text.splitlines()[0].startswith("username,name,url_main")
    assert "github.com/alice" in csv_text

    txt = generate_txt_report("alice", found).decode("utf-8")
    assert "https://github.com/alice" in txt
    assert "Total Detected : 1" in txt

    ndjson = generate_ndjson_report("alice", found, [], []).decode("utf-8")
    import json

    row = json.loads(ndjson.strip().splitlines()[0])
    assert row["username"] == "alice"
    assert row["bucket"] == "found"

    assert generate_txt_report("alice", []).decode("utf-8").startswith("Total")


def test_cypher_bytes_shape():
    from services.report_service import generate_cypher_bytes

    found = [_site("GitHub", "https://github.com/alice")]
    payload = generate_cypher_bytes("alice", found, {})
    assert payload is None or b"MERGE" in payload


def test_graphml_roundtrip_and_analytics(tmp_path):
    from services.graph_service import (
        build_identity_graph,
        export_graphml_gexf,
        get_graph_analytics,
    )

    graph = build_identity_graph(
        username="alice", found_accounts=[_site("GitHub", "https://github.com/alice")]
    )
    out = export_graphml_gexf(graph, tmp_path / "g.graphml")
    assert out is not None and out.is_file()
    assert out.read_bytes()[:5] == b"<?xml"

    analytics = get_graph_analytics(graph)
    assert "top_pagerank" in analytics
    assert "top_closeness" in analytics


def test_pyvis_physics_kinds_params(tmp_path):
    from services.graph_service import build_identity_graph, export_pyvis_html

    graph = build_identity_graph(
        username="alice", found_accounts=[_site("GitHub", "https://github.com/alice")]
    )
    out = export_pyvis_html(graph, tmp_path / "g.html", physics=False)
    assert out is not None and out.is_file()
    out2 = export_pyvis_html(graph, tmp_path / "g2.html", kinds={"target", "account"})
    assert out2 is not None and out2.is_file()


def test_pivot_handle_extraction():
    from components.profile_detail_dialog import _extract_pivot_handles

    enrich = {
        "twitter_username": "octocat",
        "github_username": "octocat",  # dupe
        "bio": "Hi, I'm @someone elsewhere",
    }
    handles = _extract_pivot_handles(enrich, {})
    assert handles[0] == "octocat"
    assert "someone" in handles
    assert len(handles) <= 3
    assert _extract_pivot_handles({}, {}) == []


def test_enrich_second_hop(tmp_path, monkeypatch):
    """Level-2 URLs discovered in merged results get one extra fetch."""
    import services.enrich_service as enrich_mod
    from services.enrich_service import EnrichService

    fetched = []

    async def _fake_parse(url, timeout, headers=None, cookies_str=""):
        fetched.append(url)
        if url == "https://example.com/u":
            return ("<html>base</html>", 200)
        if url == "https://api.example.com/u":
            return ('{"orcid": "0000-0001-2"}', 200)
        if "openalex" in url:
            return ('{"works": 5}', 200)
        return (None, 404)

    async def _fake_extract(text):
        if text is None:
            return {}
        if "orcid" in text:
            return {"orcid": "0000-0001-2", "links": ["https://openalex.example/o/1"]}
        if "works" in text:
            return {"works_count": 5}
        if "base" in text:
            return {"bio": "base bio"}
        return {}

    async def _fake_parse_in_thread(url, timeout, headers=None, cookies_str=""):
        return await _fake_parse(url, timeout, headers, cookies_str)

    async def _fake_extract_in_thread(text):
        return await _fake_extract(text)

    monkeypatch.setattr(enrich_mod, "_parse_in_thread", _fake_parse_in_thread)
    monkeypatch.setattr(enrich_mod, "_extract_in_thread", _fake_extract_in_thread)

    service = EnrichService()
    monkeypatch.setattr(
        service, "get_mutations", lambda url: [("https://api.example.com/u", {})]
    )

    async def _run():
        one = await service.enrich_url_with_mutations(
            "https://example.com/u", max_depth=1
        )
        assert one.get("orcid") == "0000-0001-2"
        assert "works_count" not in one  # no 2nd hop at depth 1
        two = await service.enrich_url_with_mutations(
            "https://example.com/u", max_depth=2
        )
        assert two.get("works_count") == 5  # 2nd hop followed the link
        assert "https://openalex.example/o/1" in fetched

    asyncio.run(_run())
