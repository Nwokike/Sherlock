# Dependency Update Sweep

Checked: 2026-10-10 · Against: PyPI live API · Installed truth: `.venv`
(synced from `uv.lock`)

## Direct dependencies (declared in pyproject.toml)

| Package | Locked | Latest on PyPI | Status |
|---|---|---|---|
| flet | 1.0.4 | 1.0.4 | **updated this release** (was 1.0.1) |
| flet-ads | 1.0.4 | 1.0.4 | **updated this release** (was 1.0.1) |
| flet-local-auth | 1.0.4 | 1.0.4 | **updated this release** (was 1.0.1) |
| holehe-v2 | 1.0.3 | 1.0.3 | current |
| maigret | 0.6.6 | 0.6.6 | current |
| socid-extractor | 0.1.1 | 0.1.1 | current |
| httpx[http2,socks] | 0.28.1 | 0.28.1 | current |

All seven direct dependencies are at their latest published versions.

## Transitive dependencies that ship inside the app

| Package | Locked | Latest | Risk | Note |
|---|---|---|---|---|
| **networkx** | 2.8.8 | **3.7** | **MAJOR — do not auto-upgrade** | See below |
| aiohttp | 3.14.3 | 3.14.4 | low | patch bump |
| pycares | 5.0.1 | 5.1.0 | low | DNS resolver, via aiodns |
| jinja2 | 3.1.6 | 3.1.6 | — | current |
| reportlab | 5.0.1 | 5.0.1 | — | current |
| xmind | 1.2.0 | 1.2.0 | — | current |
| pycountry | 26.2.16 | 26.2.16 | — | current |
| curl-cffi | 0.16.3 | 0.16.3 | — | current |
| psutil | 7.2.2 | 7.2.2 | — | current |
| cffi | 2.1.1 | 2.1.1 | — | current |

## The networkx question (needs a decision, not an upgrade)

`networkx` jumps from **2.8.8 to 3.7** — a two-major-version gap. It reaches
us transitively through maigret, but **Sherlock imports it directly** in
`src/services/graph_service.py`, so this is effectively a direct dependency
whose version we do not control.

Functions the app calls that changed across the 3.x line:
- `node_link_data(G, ...)` — 3.x reworked the link/edge keyword; older calls
  emit deprecation warnings and 4.0 will change defaults.
- `cytoscape_data` — moved/was deprecated in favour of a return-format
  argument in newer releases.
- `greedy_modularity_communities`, `connected_components`,
  `degree_centrality`, `betweenness_centrality`, `pagerank`,
  `closeness_centrality` — signatures mostly stable, but
  `pagerank`/`closeness_centrality` accept new keyword arguments and emit
  warnings on some old patterns.
- `write_graphml` / `write_gexf` — stable.

Also relevant: maigret itself pins/expects a networkx version range, and
`filterwarnings = error` is enabled in pytest for our own modules — a new
deprecation warning from networkx 3.x would **hard-fail the CI gate**.

**Recommendation: hold at 2.8.8 for this release.** If you want the upgrade,
it is its own task with a test matrix over every graph export (GraphML, GEXF,
Cypher, Cytoscape JSON, node-link JSON, communities, PageRank, closeness) —
the existing `tests/test_geo_and_reports.py` graph tests are the starting
point, and `-W error` will surface every deprecation immediately.

**Low-risk upgrade available now:** `aiohttp` 3.14.3 → 3.14.4 and `pycares`
5.0.1 → 5.1.0 are patch/minor bumps pulled in with maigret. They can be
adopted with `uv lock --upgrade-package aiohttp --upgrade-package pycares`
and a full test run, but they are maigret-internal paths (the app only uses
aiohttp for its own client via a patched TCPConnector in the maigret engine
session), so the practical benefit is near zero.

## What changed this release (for the record)

`flet`, `flet-ads`, and `flet-local-auth` were all moved 1.0.1 → 1.0.4.
Before adopting I diffed the wheels: `flet-ads` and `flet-local-auth` 1.0.4
are **byte-identical** to their 1.0.1 code except version metadata and the
flet pin (verified with a recursive diff of the unpacked wheels). No ad,
consent, or biometric logic changed. The bump exists because 1.0.4 carries
the fix for the `jni`/`jni_flutter` resolution that broke every platform
build, and because `flet_local_auth` hard-pins `flet==<its own version>`.
