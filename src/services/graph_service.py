"""GraphService — Identity Relationship Graph mapping using NetworkX.

Constructs an interactive identity cluster graph linking targets,
claimed social accounts, and shared evidence (emails, phone numbers,
full names, bio links, and cross-platform handles).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_NETWORKX_AVAILABLE = False
try:
    import networkx as nx
    from networkx.readwrite.json_graph import cytoscape_data, node_link_data

    _NETWORKX_AVAILABLE = True
except ImportError as err:
    logger.warning("networkx not available: %s", err)
    nx = None
    cytoscape_data = None
    node_link_data = None


# Brand colors for graph visualization nodes
COLOR_TARGET = "#D4AF37"  # Gold
COLOR_ACCOUNT = "#50FA7B"  # Green
COLOR_EMAIL = "#61AFEF"  # Blue
COLOR_PHONE = "#FFB86C"  # Orange
COLOR_NAME = "#BD93F9"  # Purple
COLOR_LINK = "#8BE9FD"  # Cyan


def _field(row, key: str, default=""):
    """Mapping-or-attribute read: dict rows and SiteResult objects alike."""
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def build_identity_graph(
    username: str,
    found_accounts: list,
    enrichments: dict | None = None,
    email_results: list | None = None,
) -> nx.Graph | None:
    """Build a NetworkX Graph modeling the identity network for a target.

    Connects:
    - Target node (`target:<username>`)
    - Account nodes (`acc:<site_name>`) with URL and status
    - Shared evidence nodes:
        - `email:<address>` (from holehe or socid enrichment)
        - `phone:<number>` (from recovery data)
        - `name:<fullname>` (from disclosed profile name)
        - `link:<url>` (from bio website links)
    """
    if not _NETWORKX_AVAILABLE or nx is None:
        return None

    G = nx.Graph()
    enrichments = enrichments or {}
    email_results = email_results or []

    # 1. Add root target node
    target_id = f"target:{username}"
    G.add_node(
        target_id,
        kind="target",
        label=username,
        size=24,
        color=COLOR_TARGET,
        title=f"Target Query: {username}",
    )

    # 2. Add found accounts (index i keeps ids unique when names collide
    # or repeat across rows; ids are lower-normalized, labels keep case).
    for i, r in enumerate(found_accounts):
        site = str(_field(r, "site_name", "Unknown")).strip() or "Unknown"
        url = _field(r, "url_user", None) or _field(r, "url_main", "") or ""
        acc_id = f"acc:{site.lower()}:{i}" if not url else f"acc:{url.lower()}"

        G.add_node(
            acc_id,
            kind="account",
            label=site,
            url=url,
            site=site,
            size=16,
            color=COLOR_ACCOUNT,
            title=f"Account on {site}: {url}",
        )
        G.add_edge(target_id, acc_id, weight=1.0, reason="claimed_account")

        # 3. Add enrichment evidences per account
        data = enrichments.get(url) or {}
        if not data:
            ids_data = _field(r, "ids_data", None)
            if isinstance(ids_data, dict):
                data = ids_data

        # Shared full name (original case preserved — no .title() mangling).
        name_val = data.get("fullname") or data.get("name")
        if name_val and isinstance(name_val, str) and len(name_val.strip()) > 2:
            clean_name = name_val.strip()
            name_node_id = f"name:{clean_name.lower()}"
            if not G.has_node(name_node_id):
                G.add_node(
                    name_node_id,
                    kind="evidence_name",
                    label=clean_name,
                    size=12,
                    color=COLOR_NAME,
                    title=f"Disclosed Name: {clean_name}",
                )
            G.add_edge(acc_id, name_node_id, weight=0.8, reason="disclosed_name")

        # Shared email
        email_val = data.get("email")
        if email_val and isinstance(email_val, str) and "@" in email_val:
            email_clean = email_val.strip().lower()
            email_node_id = f"email:{email_clean}"
            if not G.has_node(email_node_id):
                G.add_node(
                    email_node_id,
                    kind="evidence_email",
                    label=email_clean,
                    size=12,
                    color=COLOR_EMAIL,
                    title=f"Disclosed Email: {email_clean}",
                )
            G.add_edge(acc_id, email_node_id, weight=0.95, reason="disclosed_email")

        # External links
        links_val = data.get("links")
        if links_val:
            link_list = links_val if isinstance(links_val, list) else [links_val]
            for lk in link_list[:3]:
                lk_str = str(lk).strip()
                if lk_str.startswith("http") and " " not in lk_str:
                    link_node_id = f"link:{lk_str.lower()}"
                    if not G.has_node(link_node_id):
                        G.add_node(
                            link_node_id,
                            kind="evidence_link",
                            label=lk_str[:30],
                            url=lk_str,
                            size=10,
                            color=COLOR_LINK,
                            title=f"Profile Link: {lk_str}",
                        )
                    G.add_edge(acc_id, link_node_id, weight=0.7, reason="profile_link")

    # 4. Add email recovery intelligence
    for er in email_results:
        if isinstance(er, dict) and er.get("exists"):
            domain = er.get("domain") or er.get("name") or "email_platform"
            email_acc_id = f"email_acc:{domain}"
            if not G.has_node(email_acc_id):
                G.add_node(
                    email_acc_id,
                    kind="email_account",
                    label=domain,
                    size=14,
                    color=COLOR_EMAIL,
                    title=f"Registered Email on {domain}",
                )
            G.add_edge(target_id, email_acc_id, weight=0.9, reason="registered_email")

            rec_email = er.get("emailrecovery")
            if isinstance(rec_email, str) and "@" in rec_email:
                rec_clean = rec_email.strip().lower()
                rec_node_id = f"rec_email:{rec_clean}"
                if not G.has_node(rec_node_id):
                    G.add_node(
                        rec_node_id,
                        kind="evidence_email",
                        label=rec_clean,
                        size=10,
                        color=COLOR_EMAIL,
                        title=f"Recovery Email Hint: {rec_clean}",
                    )
                G.add_edge(
                    email_acc_id, rec_node_id, weight=0.85, reason="recovery_hint"
                )

            phone = er.get("phoneNumber")
            if isinstance(phone, (str, int)):
                phone_s = str(phone).strip()
                if phone_s:
                    phone_node_id = f"phone:{phone_s}"
                    if not G.has_node(phone_node_id):
                        G.add_node(
                            phone_node_id,
                            kind="evidence_phone",
                            label=phone_s,
                            size=10,
                            color=COLOR_PHONE,
                            title=f"Recovery Phone Hint: {phone_s}",
                        )
                    G.add_edge(
                        email_acc_id,
                        phone_node_id,
                        weight=0.85,
                        reason="recovery_phone",
                    )

            # holehe-v2 Result.extra identity facts (gravatar verified
            # accounts / websites / links, github login, etsy bio, ...).
            others = er.get("others")
            extra = (
                others.get("extra")
                if isinstance(others, dict) and isinstance(others.get("extra"), dict)
                else {}
            )
            for _key in ("verified_accounts", "websites", "links"):
                _vals = extra.get(_key)
                if not isinstance(_vals, (list, tuple)):
                    _vals = [_vals] if _vals else []
                for _v in list(_vals)[:5]:
                    _s = str(_v).strip()
                    if not _s:
                        continue
                    _nid = f"link:{_s.lower()}"
                    if not G.has_node(_nid):
                        G.add_node(
                            _nid,
                            kind="evidence_link",
                            label=_s[:30],
                            url=_s,
                            size=10,
                            color=COLOR_LINK,
                            title=f"Linked Identity ({_key}): {_s}",
                        )
                    G.add_edge(email_acc_id, _nid, weight=0.7, reason="linked_identity")

    logger.info(
        "Identity graph built for %s: %d nodes, %d edges",
        username,
        len(G.nodes),
        len(G.edges),
    )
    return G


def export_cytoscape_json(G: Any) -> dict | None:
    """Export graph in Cytoscape.js format for interactive visualization."""
    if not _NETWORKX_AVAILABLE or G is None:
        return None
    try:
        return cytoscape_data(G)
    except Exception as exc:
        logger.warning("Cytoscape export failed: %s", exc)
        return None


def export_node_link_json(G: Any) -> dict | None:
    """Export graph in standard Node-Link JSON format."""
    if not _NETWORKX_AVAILABLE or G is None:
        return None
    try:
        return node_link_data(G)
    except Exception as exc:
        logger.warning("Node-Link export failed: %s", exc)
        return None


def get_graph_analytics(G: Any) -> dict:
    """Compute centralities, clusters, and graph metrics."""
    if not _NETWORKX_AVAILABLE or G is None or len(G.nodes) == 0:
        # Same schema as the success path below — consumers may index
        # component_sizes / top_canonical_nodes unconditionally.
        return {
            "nodes": 0,
            "edges": 0,
            "components": 0,
            "component_sizes": [],
            "density": 0.0,
            "communities": [],
            "bridge_nodes": [],
            "top_canonical_nodes": [],
        }

    components = list(nx.connected_components(G))
    degree_cent = nx.degree_centrality(G)
    top_canonical = sorted(degree_cent.items(), key=lambda x: x[1], reverse=True)[:5]

    # P4-7: evidence communities (greedy modularity — pure Python, uses our
    # edge weights) + bridge nodes (betweenness, capped for O(nm) cost).
    communities = []
    try:
        from networkx.algorithms.community import greedy_modularity_communities

        comms = list(greedy_modularity_communities(G, weight="weight"))
        communities = sorted(
            (
                {
                    "size": len(c),
                    "members": [
                        G.nodes[m].get("label", m)
                        for m in sorted(
                            c, key=lambda m: str(G.nodes[m].get("label", m))
                        )[:5]
                    ],
                }
                for c in comms
            ),
            key=lambda x: x["size"],
            reverse=True,
        )[:8]
    except Exception as exc:
        logger.debug("Community detection skipped: %s", exc)

    bridges = []
    top_pagerank = []
    top_closeness = []
    if len(G.nodes) <= 150:
        try:
            bc = nx.betweenness_centrality(G)
            bridges = sorted(
                (
                    {"label": G.nodes[n].get("label", n), "score": round(s, 3)}
                    for n, s in bc.items()
                    if s > 0
                ),
                key=lambda x: x["score"],
                reverse=True,
            )[:3]
        except Exception as exc:
            logger.debug("Betweenness skipped: %s", exc)
        try:
            try:
                pr = nx.pagerank(G)
            except Exception as exc:
                # networkx delegates pagerank to pagerank_scipy, which needs
                # numpy/scipy — not installed on the device. The pure-Python
                # eigenvector centrality covers the same "who matters" view.
                logger.debug("PageRank (scipy) unavailable: %s", exc)
                try:
                    pr = nx.eigenvector_centrality(G, max_iter=500)
                except Exception as exc2:
                    logger.debug("Eigenvector centrality unavailable: %s", exc2)
                    pr = {}
            top_pagerank = sorted(
                (
                    {"id": n, "label": G.nodes[n].get("label", n), "score": round(s, 3)}
                    for n, s in pr.items()
                ),
                key=lambda x: x["score"],
                reverse=True,
            )[:5]
        except Exception as exc:
            logger.debug("PageRank skipped: %s", exc)
        try:
            cc = nx.closeness_centrality(G)
            top_closeness = sorted(
                (
                    {"id": n, "label": G.nodes[n].get("label", n), "score": round(s, 3)}
                    for n, s in cc.items()
                ),
                key=lambda x: x["score"],
                reverse=True,
            )[:5]
        except Exception as exc:
            logger.debug("Closeness skipped: %s", exc)

    return {
        "nodes": len(G.nodes),
        "edges": len(G.edges),
        "components": len(components),
        "component_sizes": [len(c) for c in components],
        "density": round(nx.density(G), 3),
        "communities": communities,
        "bridge_nodes": bridges,
        "top_canonical_nodes": [
            {
                "id": node_id,
                "label": G.nodes[node_id].get("label", node_id),
                "centrality": round(score, 3),
            }
            for node_id, score in top_canonical
        ],
        "top_pagerank": top_pagerank,
        "top_closeness": top_closeness,
    }


def export_graphml_gexf(
    G: Any, out_path: str | Path, fmt: str = "graphml"
) -> Path | None:
    """Write Gephi-compatible GraphML/GEXF (all attrs are scalars — safe)."""
    if not _NETWORKX_AVAILABLE or G is None:
        return None
    try:
        writer = nx.write_graphml if fmt == "graphml" else nx.write_gexf
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        writer(G, out)
        return out
    except Exception as exc:
        logger.warning("GraphML/GEXF export failed: %s", exc)
        return None


def export_cypher(G: Any) -> str:
    """Neo4j-style Cypher statements for the identity graph (P3-5)."""
    if not _NETWORKX_AVAILABLE or G is None:
        return ""

    def esc(value) -> str:
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )

    lines = ["// Sherlock identity graph — Cypher export"]
    for n, d in G.nodes(data=True):
        kind = re.sub(r"[^A-Za-z0-9_]", "_", str(d.get("kind", "node"))) or "node"
        label = esc(d.get("label", n))
        lines.append(f"MERGE (`{kind}`:Entity {{id: '{esc(n)}', label: '{label}'}});")
    for u, v, d in G.edges(data=True):
        reason = esc(d.get("reason", "linked"))
        lines.append(
            f"MATCH (a {{id: '{esc(u)}'}}), (b {{id: '{esc(v)}'}}) "
            f"MERGE (a)-[:LINK {{reason: '{reason}'}}]->(b);"
        )
    logger.info("Cypher export: %d nodes, %d edges", len(G.nodes), len(G.edges))
    return "\n".join(lines) + "\n"


def export_pyvis_html(
    G: Any, out_path: str | Path, *, physics: bool = True, kinds: set[str] | None = None
) -> Path | None:
    """Write a self-contained interactive graph (P4-6, pyvis inline CDN).

    Returns the written Path, or None (logged) on any failure — the caller
    surfaces a visible error per the owner's no-swallowing rule.
    """
    if not _NETWORKX_AVAILABLE or G is None or len(G.nodes) == 0:
        return None
    try:
        from pyvis.network import Network
    except Exception as exc:
        logger.warning("pyvis unavailable for interactive viewer: %s", exc)
        return None
    try:
        net = Network(
            height="640px",
            width="100%",
            bgcolor="#1E1E2E",
            font_color="#EEEEEE",
            notebook=False,
            directed=False,
            cdn_resources="in_line",
            select_menu=True,
            filter_menu=True,
        )
        kept: set = set()
        for n, d in G.nodes(data=True):
            if kinds is not None and d.get("kind") not in kinds:
                continue
            kept.add(n)
            net.add_node(
                n,
                label=str(d.get("label", n)),
                title=str(d.get("title", "")),
                color=str(d.get("color", "#D4AF37")),
                size=int(d.get("size", 12)),
            )
        for u, v, d in G.edges(data=True):
            # pyvis asserts both endpoints exist; with kinds= filtered out a
            # node, its edges must be skipped or the whole export returns None.
            if u not in kept or v not in kept:
                continue
            reason = str(d.get("reason", "linked"))
            # Reason-specific edge colors so relationship types are legible.
            edge_colors = {
                "member": "#8C6B1A",
                "registered_email": "#D4AF37",
                "recovery_hint": "#4FC3F7",
                "recovery_phone": "#4FC3F7",
                "linked": "#D4AF37",
            }
            net.add_edge(
                u,
                v,
                title=reason,
                color=edge_colors.get(reason, "#D4AF37"),
            )
        try:
            net.toggle_physics(physics)
        except Exception:
            pass
        # Physics tuning: force-atlas spreads the identity clusters instead of
        # collapsing them into a hairball (the old default was unconfigured).
        try:
            net.set_options(
                """{
                  "physics": {"forceAtlas2Based": {"gravitationalConstant": -50,
                             "centralGravity": 0.01, "springLength": 120,
                             "springConstant": 0.08},
                             "maxVelocity": 40, "solver": "forceAtlas2Based",
                             "timestep": 0.3},
                  "edges": {"smooth": {"type": "continuous"}, "color": {"inherit": false}}
                }"""
            )
        except Exception:
            pass
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(net.generate_html(notebook=False), encoding="utf-8")
        logger.info("Interactive graph written: %s", out)
        return out
    except Exception as exc:
        logger.warning("pyvis graph export failed: %s", exc)
        return None
