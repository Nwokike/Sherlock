# Sherlock V2 — Milestones

Master plan for the Flet twin of Sherlock: a one-to-one wrap of
`user-scanner` (username + email OSINT) plus `phonsint` (phone OSINT),
reusing the original Sherlock app shell (design, screens, components, state,
storage, cache, ads, update service) verbatim. Engine services are remapped.

Non-goals (to preserve the one-to-one discipline): no socid-extractor
enrichment pipeline, no identity graph, no bespoke email extractors beyond
what a module's own `extra` fields return. Phone-mode masked emails come
from phonsint natively.

## Milestones

| # | Milestone | Scope | Status |
|---|---|---|---|
| M0 | Verified base | uv init + sync + dependency swarm + docs/reference | done |
| M1 | Skeleton twin | Copy original Sherlock src/ into V2, stub engine services, build + run (desktop) with all screens rendering, no import errors | next |
| M2 | Engine adapter | user-scanner + phonsint services with progress/cancel; tolerant module loader; basic username/email/phone scan end-to-end | pending |
| M3 | Scan-option parity | categories/modules, allow-loud, no-nsfw, timeout, concurrency, --all, -v, bulk files, permute, proxy + validate, hudson, cross-scan, email-domains | pending |
| M4 | Export + module screens | JSON/CSV/PDF/MD/HTML/TXT exports; module-list screens; sites screen adapted to upstream categories | pending |
| M5 | Shell parity | history, cache, storage, settings persistence, onboarding, ads, update service, notifications (if flet-notifications added) | pending |
| M6 | Tests + packaging | contract tests, offline smoke, Android arm64+x86_64 build, Windows, Linux, CI | pending |

## What V2 has that V1 doesn't
- One engine covers username + email (replaces maigret + holehe-v2) → fewer deps.
- Modules are tiny standalone `validate_*` functions returning structured `Result` → no CLI parsing, no subprocess.
- phonsint adds phone OSINT (masked emails, display names, avatars) as a third mode.
- Cross-scan, hudson breach intel, permutations, proxies, PDF dossier all come from upstream for free.

## What V1 has that V2 doesn't (yet)
- socid-extractor profile enrichment (avatar/bio/followers) → deferred; module `extra` fields cover most of it.
- Identity graph / cypher export → deferred (report_service.generate_cypher_bytes depends on graph_service).
- flet-notifications scan progress notification → deferred (not in V2 deps; add later if parity wanted).
- Maigret's 5,200+ networks vs user-scanner's 2,521 username modules → different coverage; user-scanner is the chosen base.

## M1 detail (to be planned in plan mode)
Copy `Sherlock/src/` verbatim into `Sherlock-V2/src/` (flattened, pythonpath=["src"]), copy assets, mirror pyproject [tool.flet] block, stub `sherlock_service`/`email_service`/`enrich_service`/`graph_service`/`http_client` so the shell imports and renders with no engine. Engine scans stubbed (no-op / NotImplementedError) for M1; wired in M2.

Deliverable: `flet run` (desktop) launches, all 7 screens render, navigation works, ads no-op on desktop, no import errors.
