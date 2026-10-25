# Sherlock V3 — Swarm Audit Plan (2026-10-20)

Owner directive: verify that this app is a **maximal one-to-one Flet wrap** of
`user-scanner` *(+ phonsint for phone OSINT)*. Every installed dependency must
be utilized to the fullest, and every app file must be audited for bugs,
hallucinated APIs, and better implementations.

**Ground rule: the installed package in `.venv` is the only source of truth.**
Any docs/reference claim that disagrees with live introspection is wrong.

## Context that changed today
- Removed `reportlab`, `pillow`, `svglib` from `pyproject.toml` and ran
  `uv sync`. These three were added by the previous AI "just for exports",
  violating the owner rule: *exports must be the exports the wrapped engine
  itself provides* (user-scanner ships JSON/CSV/PDF via its own
  `core/formatter.py` and `core/pdf_generator.py`). `.venv` now holds 34
  packages; the extra transitive packages those three dragged in (lxml,
  tinycss2, cssselect2, webencodings, charset-normalizer, requests,
  urllib3, jinja2, click, pyyaml, watchfiles, qrcode… ) are gone too.
- `src/services/report_service.py` still imports the removed libraries and is
  now intentionally broken until the V3 export rework. File audit agents must
  flag it, not caringly patch it.

## How work is split (rule: ONE task per subagent)
1. **Dependency agents** — one per installed dependency/subdependency
   (34 agents, `docs/SWARM-2026-10-20/deps/<package>.md`). Each agent's single
   job: fully verify that package against the installed copy in `.venv`,
   then audit how this app uses it and report every leftover capability we are
   not exploiting, with concrete integration proposals.
2. **File agents** — one per application/test file (57 agents,
   `docs/SWARM-2026-10-20/files/<path>.md`). Each agent's single job: audit
   that one file — correctness, hallucinated APIs, bugs, edge cases, and how
   it could be written better. If the file is perfect, it must say so.
3. Batches run sequentially (6 tasks per batch) to stay clear of rate limits.

## Prior work
`docs/reference/dep-*.md` already contain package studies compiled 2026-10-19
against the Sherlock-V2 venv. Dependency agents must re-verify against the
current V3 `.venv` (versions match the stamps in
`docs/reference/README.md`) and treat existing entries as background, not
truth. The index references `dep-flet.md`, which is missing from this repo —
the flet agent compiles it fresh from `.venv` as `dep-flet.md`.

## Deliverables status
- [x] Dependency tree (see `dependency-tree.md`)
- [x] File inventory (see `file-inventory.md`)
- [ ] Dependency agents (34)
- [ ] File agents (57)
- [ ] Synthesis + V3 fix plan
