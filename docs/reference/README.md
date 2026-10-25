# `docs/reference/` — index and version stamps

Three families of reference, all compiled from live probes of the installed venv:

- **`dep-*.md`** — dependency API references compiled from the installed venv.
  These age with the PACKAGES. Where a dep doc disagrees with `importlib.metadata`
  + live introspection, the doc is wrong.

**Rule: the installed package is the only source of truth.**

## Version stamps (verified 2026-10-19, Python 3.14.7, Sherlock-V2 venv)

| Doc | Compiled against | Installed now | Banner |
|---|---|---|---|
| dep-flet.md | flet 1.0.4 | flet 1.0.4 | current |
| dep-flet-ads.md | flet-ads 1.0.4 | flet-ads 1.0.4 | current |
| dep-user-scanner.md | user-scanner 1.5.2.3 | user-scanner 1.5.2.3 | current |
| dep-phonsint.md | phonsint 0.1.0 | phonsint 0.1.0 | current |
| dep-httpx.md | httpx 0.28.1 | httpx 0.28.1 | current |
| dep-curl-cffi.md | curl-cffi 0.16.3 | curl-cffi 0.16.3 | current |
| dep-rich.md | rich 15.0.0 | rich 15.0.0 | current |
| dep-phonenumbers.md | phonenumbers 9.0.41 | phonenumbers 9.0.41 | current |
| dep-socksio.md | socksio 1.0.0 | socksio 1.0.0 | current |
| dep-ruff.md | ruff 0.17.1 | ruff 0.17.1 | current |
| dep-anyio.md | anyio 4.15.1 | anyio 4.15.1 | current |
| dep-cffi.md | cffi 2.1.1 | cffi 2.1.1 | current |
| dep-pycparser.md | pycparser 3.11 | pycparser 3.11 | current |
| dep-pytest-stack.md | pytest 9.1.1 (+ iniconfig 2.3.1, packaging 26.3, pluggy 1.7.0, pygments 2.21.0) | same | current |
| dep-small-transitives.md | msgpack 1.2.3, oauthlib 4.0.0, repath 0.9.0, six 1.17.0, certifi 2026.10.18, idna 3.20, mdurl 0.1.2, markdown-it-py 4.2.0, typing-extensions 4.16.0, h11 0.16.0, h2 4.4.1, hpack 4.2.0, hyperframe 6.1.0, colorama 0.4.6 | same | current |

**Rule: the installed package is the only source of truth.** Where a dep doc
disagrees with `importlib.metadata` + live introspection, the doc is wrong, and
the failure mode is real — the swarm audit traced ~8 criticals to following
`dep-primp.md`'s primp-1.3.1 surface (animepahe-tv `docs/swarm-audit-2026-10-13.md` §1.1).

## Cross-check notes
- All docs compiled against the installed venv (Python 3.14.7). No stale banners needed.
- Cross-checked against `/home/maikel/.zcode/workspace/default/animepahe-tv/docs/reference/`:
  - `dep-flet.md`, `dep-httpx.md`, `dep-anyio.md`, `dep-httpcore.md`, `dep-msgpack.md`, `dep-oauthlib.md`, `dep-h11.md`, `dep-pytest-microdeps.md`, `dep-small-transitives.md`, `dep-test-stack.md` consulted.
  - Missing from animepahe (studied fresh here): `dep-flet-ads.md`, `dep-user-scanner.md`, `dep-phonsint.md`, `dep-curl-cffi.md`, `dep-rich.md`, `dep-phonenumbers.md`, `dep-socksio.md`, `dep-ruff.md`, `dep-cffi.md`, `dep-pycparser.md`.
  - `httpcore` is covered inside `dep-httpx.md` (cross-referenced; animepahe has a separate `dep-httpcore.md` — our doc folds httpcore into httpx, which is acceptable since we use httpx's API, not httpcore directly).
- Each dep doc carries an "App improvement opportunities" (or equivalent) section. Where an opportunity is tied to original Sherlock `src/` code, the citation is given.
