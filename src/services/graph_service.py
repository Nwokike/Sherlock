"""GraphService — Identity Relationship Graph mapping using NetworkX.

Constructs an interactive identity cluster graph linking targets,
claimed social accounts, and shared evidence (emails, phone numbers,
full names, bio links, and cross-platform handles).
"""

from __future__ import annotations

import logging
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


def build_identity_graph(
    username: str,
    found_accounts: list,
    enrichments: dict | None = None,
    email_results: list | None = None,
) -> Any | None:
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

    # 2. Add found accounts
    for r in found_accounts:
        site = getattr(r, "site_name", "Unknown")
        acc_id = f"acc:{site}"
        url = getattr(r, "url_user", None) or getattr(r, "url_main", "") or ""

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
        if not data and hasattr(r, "ids_data") and isinstance(r.ids_data, dict):
            data = r.ids_data

        # Shared full name
        name_val = data.get("fullname") or data.get("name")
        if name_val and isinstance(name_val, str) and len(name_val.strip()) > 2:
            clean_name = name_val.strip().title()
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
                G.add_edge(
                    target_id, email_acc_id, weight=0.9, reason="registered_email"
                )

            rec_email = er.get("emailrecovery")
            if rec_email and "@" in rec_email:
                rec_node_id = f"rec_email:{rec_email.strip().lower()}"
                if not G.has_node(rec_node_id):
                    G.add_node(
                        rec_node_id,
                        kind="evidence_email",
                        label=rec_email,
                        size=10,
                        color=COLOR_EMAIL,
                        title=f"Recovery Email Hint: {rec_email}",
                    )
                G.add_edge(
                    email_acc_id, rec_node_id, weight=0.85, reason="recovery_hint"
                )

            phone = er.get("phoneNumber")
            if phone:
                phone_node_id = f"phone:{phone.strip()}"
                if not G.has_node(phone_node_id):
                    G.add_node(
                        phone_node_id,
                        kind="evidence_phone",
                        label=phone,
                        size=10,
                        color=COLOR_PHONE,
                        title=f"Recovery Phone Hint: {phone}",
                    )
                G.add_edge(
                    email_acc_id, phone_node_id, weight=0.85, reason="recovery_phone"
                )

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
        return {"nodes": 0, "edges": 0, "components": 0, "density": 0.0}

    components = list(nx.connected_components(G))
    degree_cent = nx.degree_centrality(G)
    top_canonical = sorted(degree_cent.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "nodes": len(G.nodes),
        "edges": len(G.edges),
        "components": len(components),
        "component_sizes": [len(c) for c in components],
        "density": round(nx.density(G), 3),
        "top_canonical_nodes": [
            {
                "id": node_id,
                "label": G.nodes[node_id].get("label", node_id),
                "centrality": round(score, 3),
            }
            for node_id, score in top_canonical
        ],
    }
