# Audit — `src/services/enrich_service.py` (33 lines)

**Audit date:** 2026-10-22
**Scope:** this file only. Other files are referenced solely to establish the call-site census and the dead-code extent.
**Truth source:** installed dependencies. `user-scanner 1.5.2.3` is installed; **`socid-extractor` is absent** from `pyproject.toml` (`pyproject.toml:6-12` → `flet`, `flet-ads`, `user-scanner>=1.5.2.3`, `phonsint>=0.1.0`) and absent from the venv (`site-packages` contains `user_scanner` / `user_scanner-1.5.2.3.dist-info` and no `socid*`; `find . -iname "*socid*"` returns nothing).

---

## 1) File role + content

**Role:** a placeholder service class for a *profile-enrichment* engine (socid-extractor-style profile scraping / "mutations"). It exists only so the app can import and render without that dependency. It is **not** a working implementation of anything.

### Full current content

```python
 1  """Profile enrichment service — STUB for M1 (socid-extractor not in V2 deps).
 2
 3  V2 does not ship socid-extractor. Enrichment becomes a no-op; module
 4  `extra`/`media` fields from user-scanner/phonsint cover most of it in M2.
 5  """
 6
 7  from __future__ import annotations
 8
 9  from typing import Any
10
11
12  class EnrichService:
13      def __init__(self, *args: Any, **kwargs: Any) -> None:
14          self._available = False
15
16      @property
17      def is_available(self) -> bool:
18          return False
19
20      def extract(self, page_html: str) -> dict:
21          return {}
22
23      def get_mutations(self, url: str) -> list[tuple[str, dict]]:
24          return []
25
26      async def enrich_url(self, url: str, **kwargs: Any) -> dict:
27          return {}
28
29      async def enrich_url_with_mutations(self, url: str, **kwargs: Any) -> dict:
30          return {}
31
32      async def batch_enrich(self, *args: Any, **kwargs: Any) -> dict:
33          return {}
```

### Class outline (all 5 methods are no-ops)

| Member | Line | Signature | Returns | Called anywhere? |
|---|---|---|---|---|
| `__init__` | `:13-14` | `(*args, **kwargs)` | — | yes, `main.py:517` (`EnrichService()`, no args) |
| `is_available` (property) | `:16-18` | `-> bool` | literal `False` | yes, `main.py:968,1183,1410-1411` |
| `extract` | `:20-21` | `(page_html: str) -> dict` | `{}` | **no call sites anywhere** |
| `get_mutations` | `:23-24` | `(url: str) -> list[tuple[str, dict]]` | `[]` | **no call sites anywhere** |
| `enrich_url` | `:26-27` | `async (url, **kwargs) -> dict` | `{}` | yes, `main.py:1200` (inside dead worker) |
| `enrich_url_with_mutations` | `:29-30` | `async (url, **kwargs) -> dict` | `{}` | yes, `main.py:1198` (inside dead worker) |
| `batch_enrich` | `:32-33` | `async (*args, **kwargs) -> dict` | `{}` | **no call sites anywhere** |

`ruff check src/services/enrich_service.py` → **"All checks passed!"**. There is no mechanical lint signal that this file is dead; that is why it survived.

---

## 2) Call-site census

Full-repo grep for `EnrichService|enrich_service|enrich_url|enrich_url_with_mutations|batch_enrich|get_mutations` (excluding `.venv`/`.git`):

### Live code references (all inside `src/main.py`)

| Site | Code | Reachable? |
|---|---|---|
| `src/main.py:87` | `from services.enrich_service import EnrichService` | import always runs |
| `src/main.py:120` | `self.enrich_service: EnrichService | None = None` | always |
| `src/main.py:517` | `self.enrich_service = EnrichService()` | always (constructor never raises) |
| `src/main.py:968` | `if self.enrich_service and self.enrich_service.is_available:` | **never true** → `:969-975` never runs |
| `src/main.py:1183` | `if not self.enrich_service or not self.enrich_service.is_available: return` | **always true** → `_drain_enrich_queue` returns at its 3rd line |
| `src/main.py:1198` | `self.enrich_service.enrich_url_with_mutations` | never reached |
| `src/main.py:1200` | `self.enrich_service.enrich_url` | never reached |
| `src/main.py:1215-1220` | `await fn(url, timeout=…, cookies=…, user_agent=…)` | never reached |
| `src/main.py:1410-1411` | `and self.enrich_service.is_available` | **never true** → `:1412-1419` never runs |

**Uncalled public methods:** `extract` (`:20`), `get_mutations` (`:23`), `batch_enrich` (`:32`) — **zero** call sites in `src/` or `tests/`. `tests/` contains no reference to `enrich` at all.

### Documentation references (no code impact)

- `docs/roadmap.md:38` — M1 instruction to "stub `sherlock_service`/`email_service`/`enrich_service`/…". **This is the origin of the file: it was a deliberate M1 scaffold that was never removed after the V3 non-goal was declared.**
- `docs/roadmap.md:8-9` — **Non-goals**: "no socid-extractor enrichment pipeline, no identity graph…"
- `docs/roadmap.md:32` — "socid-extractor profile enrichment (avatar/bio/followers) → **deferred**; module `extra` fields cover most of it."
- `docs/SWARM-2026-10-20/file-inventory.md:45` — inventory row (33 lines).
- `docs/SWARM-2026-10-20/deps/typing-extensions.md:52` — records `src/services/enrich_service.py:9` as the sole `Any` import site.
- `docs/SWARM-2026-10-20/deps/rich.md:190` — notes the `rich`-package grep hits here are substring matches on "enrich**ment**".

---

## 3) Dead-code extent caused by the stub

### 3a. Inside `enrich_service.py` itself — 33 / 33 lines dead

`is_available` (`:17-18`) is a hard-coded `False`, so **no method of this class can ever be observed to do anything**. The file contributes zero runtime behaviour to the app.

### 3b. `src/main.py` — ~160 lines of permanently unreachable code

| Region | Lines | What dies |
|---|---|---|
| import + attribute | `:87`, `:120`, `:517` | 3 lines |
| state attributes | `:134-137` (`_enrich_queue`, `_enriched_seen`, `_enrich_worker_task`), `:138-142` (`_enrich_gen`), `:143-144` (`_avatar_warmed`), `:162` (`_pending_enrichments`) | 14 lines |
| flusher stop-flush | `:412-417` (`state.enrichments.update(pending)` on an always-empty dict) | 6 lines |
| render flusher | `:438-447` (LRU-cap mirror of `set_enrichment`) + comment `:448-449` | 12 lines |
| worker spawn | `:965-975` (queue alloc + `is_available` guard; `:966-967` allocate an `asyncio.Queue` per search that is never drained) | 11 lines |
| **`_drain_enrich_queue`** | `:1181-1277` — the entire 97-line method (cookie read, avatar warm, `enrich_url*` call, mutation branch) | **97 lines** |
| found-URL enqueue | `:1408-1419` | 12 lines |
| state clears | `:1991`, `:2016`, `:2068` (+ `:2069-2070` `_enrich_gen`/`_enriched_seen` resets) | 5 lines |
| snapshot field | `:2184` `"enrichments": dict(state.enrichments or {})` — always `{}` | 1 line |

**Total ≈ 161 lines in `main.py` that can never execute.**

**Double-dead note:** even if `is_available` were flipped to `True`, the stub still returns `{}` (`:27`, `:30`), and the consumer's truthiness gate is `if data and gen == self._enrich_gen:` (`main.py:1221`). `{}` is falsy → still nothing is ever written. The path is dead **twice over**, and it fails *silently* (no exception, no log) — unlike the `NotImplementedError` stubs the M1 roadmap called for (`docs/roadmap.md:38`).

### 3c. `src/core/enrich_view.py` (149 lines) — **NOT dead. Keep it.**

This is the most important nuance in the audit. `enrich_view.py` looks like enrichment plumbing, but it is fed by the **native** user-scanner / holehe `Result.extra` + `Result.media` path, which does not touch `EnrichService` at all:

- `src/services/sherlock_service.py:328-341` — extracts `extra` and `media` off the user-scanner result and packs `ids_data = {"extra": extra, "media": media}` (JSON-safe coercion included).
- `src/main.py:1096`, `src/main.py:1814`, `src/screens/results_screen.py:458` — carry `others` / `extra` / `media` into the row dicts.
- `src/components/result_card.py:211` `v2_extra = others.get("extra")` → `src/components/result_card.py:269-274` `enrichment_rows(enrichment, v2_extra, skip=_CARD_STYLED_KEYS)` → **live**.
- `src/components/profile_detail_dialog.py:832-871` `enrichment_rows(enrich, others.get("extra"), skip=specially_rendered)`, `:893` `is_link_value`, `:912` `truncate_value` → **live**.

So of `enrich_view.py`'s 149 lines, **146 are live** via the native path. The only dead member is `enrichment_summary` (`src/core/enrich_view.py:147-149`) — zero callers anywhere in `src/` or `tests/` — and it is dead for a reason unrelated to this stub.

### 3d. `src/services/report_service.py` — ~90 lines of enrichment branches that can never render

`enrichments` is passed in from `src/app_shell.py:301` and `src/app_shell.py:391` as `dict(app_state.enrichments or {})`, and `state.enrichments` is **always `{}`** (see 3e). Therefore:

| Region | Lines | What dies |
|---|---|---|
| shared helpers | `:66-87` (`_IDENTITY_KEYS`, `_DATE_KEYS`, `_fmt_ident`) — used only by the three blocks below | 22 lines |
| Markdown renderer | `:176`, `:189` (param + normalise), `:218-234` ("## Profile Enrichment Highlights" block) | 19 lines |
| HTML renderer | `:329`, `:344` (param + normalise), `:307-309` (`{% if enrich_rows %}` template), `:356-375` (`enrich_rows` build), `:396` (`enrich_rows=enrich_rows[:15]`) | 30 lines |
| PDF renderer | `:589`, `:610` (param + normalise), `:769-~805` ("Enrichment highlight cards" + avatar thumbnail embed) | ~30 lines |

**The Markdown, HTML and PDF dossier exporters each contain a whole "Profile Enrichment Highlights" section that can never appear in any exported file.** The PDF block even has a comment at `:788-789` saying the avatar thumbnail is "cache-warmed by the enrichment flow" — a flow that does not exist.

### 3e. `src/core/state.py` — the enrichment store is a permanently-empty dict

- `src/core/state.py:82-84` — the field `enrichments: dict | None = None`, whose comment says "from socid-extractor".
- `src/core/state.py:169` — `self.enrichments = {}` (initialised).
- `src/core/state.py:186-192` — `set_enrichment(url, data)`: **never called from anywhere**. The LRU-cap helper referenced by the comment at `src/core/state.py:83` and mirrored by hand at `src/main.py:441-447` is dead code.
- `src/core/state.py:237` — `self.enrichments.clear()` in `reset_search`.
- The only *writers* are `src/main.py:415` and `src/main.py:441`, both fed exclusively from `self._pending_enrichments`, which is written only at `src/main.py:1224` — inside the dead drain worker. **`state.enrichments` is therefore always `{}`.**

### 3f. Downstream consumers of the always-empty `state.enrichments`

| Site | Effect |
|---|---|
| `src/screens/results_screen.py:387-390` | profile dialog enrichment → always `None` |
| `src/screens/results_screen.py:725-731` | `enrichment=` kwarg to `ResultCard` → always `None` |
| `src/screens/results_screen.py:749-753` | `_username_filter_key` never appends enrichment name/fullname → search filter silently loses those terms |
| `src/screens/results_screen.py:178-195` + `:818` | `_enrichment_fingerprint` always returns `()` → the memo dependency is a constant |
| `src/app_shell.py:301`, `src/app_shell.py:391` | dossier exports receive `enrichments={}` → see 3d |
| `src/main.py:1991/1993`, `:2016`, `:2068` | clear/restore of an always-empty map |

### 3g. A user-facing control that provably does nothing

`src/screens/settings_screen.py:1527-1551` renders an **"Enrichment Mode"** segmented button labelled *"Basic = fast (1 req/url) · Full = richer via API mutations"*, persisted at `src/screens/settings_screen.py:486-488` to `STORAGE_ENRICHMENT_MODE` (`src/core/constants.py:47`) and loaded at `src/main.py:735-742`. Its only consumer is `src/main.py:1187` (`use_mutations = getattr(state, "enrichment_mode", "basic") == "full"`) — **inside the dead `_drain_enrich_queue`**. The user can flip a persisted setting that cannot change a single byte of output. Default is `"full"` (`src/core/state.py:103`).

### 3h. Summary of dead-line extent

| File | Lines permanently dead because of this stub |
|---|---|
| `src/services/enrich_service.py` | 33 / 33 |
| `src/main.py` | ≈ 161 |
| `src/services/report_service.py` | ≈ 90 (three renderer branches + shared helpers) |
| `src/core/state.py` | ≈ 17 (field, init, dead `set_enrichment`, clears) |
| `src/screens/results_screen.py` | ≈ 22 (3 enrichment reads + dead fingerprint helper) |
| `src/app_shell.py` | 2 (export kwargs) |
| `src/screens/settings_screen.py` | ≈ 28 (no-op toggle + handler) |
| `src/core/constants.py` | 1 (`STORAGE_ENRICHMENT_MODE`) |
| `src/core/enrich_view.py` | **0** — keep entire file (only `enrichment_summary` `:147-149` is unused, for an unrelated reason) |
| **Total** | **≈ 350 lines** |

---

## 4) Findings inside `enrich_service.py`

Every finding cites this file.

### F-1 — CRITICAL: the class is a total no-op; `is_available` is a hard-coded `False`
`src/services/enrich_service.py:17-18` returns the literal `False`. Every other member (`:21`, `:24`, `:27`, `:30`, `:33`) returns an empty container. The class therefore cannot influence a single line of app output, and the `is_available` guard it advertises is the only thing standing between the app and ~350 lines of dead code.

### F-2 — BUG (latent): `self._available` is written but never read
`src/services/enrich_service.py:14` sets `self._available = False`; `src/services/enrich_service.py:17-18` returns the literal `False` and never consults `self._available`. The attribute is dead **and misleading**: a future implementer who flips `_available = True` would see no behavioural change whatsoever. Either the property must read `self._available` or the attribute must go.

### F-3 — BUG (contract): the `{}` return is indistinguishable from "enrichment found nothing"
`src/services/enrich_service.py:27` and `:30` return `{}`, and the consumer gates on truthiness (`src/main.py:1221` `if data and gen == self._enrich_gen:`). Failure is silent — no exception, no log line. The roadmap's own M1 convention was `NotImplementedError` for engine stubs (`docs/roadmap.md:38`); this stub is a *silent* no-op, which is strictly harder to diagnose.

### F-4 — DEAD METHOD: `extract` has zero call sites
`src/services/enrich_service.py:20-21`. No caller in `src/` or `tests/`. Its parameter name `page_html` and its sync shape mirror socid-extractor's `extract(page)` — an API of a package that is **not installed** (`pyproject.toml:6-12`, absent from the venv). The contract is unverifiable against any installed dependency: a hallucinated API shape.

### F-5 — DEAD METHOD: `get_mutations` has zero call sites and no in-class caller
`src/services/enrich_service.py:23-24`. Dead twice: nothing outside calls it, and the method that was supposed to use it — `enrich_url_with_mutations` (`:29-30`) — returns `{}` without ever touching it. The return annotation `list[tuple[str, dict]]` (mutation URL → payload pairs) is a guess about socid-extractor's shape with no installed package to check it against.

### F-6 — DEAD METHOD: `batch_enrich` duplicates a concept implemented elsewhere
`src/services/enrich_service.py:32-33`. Zero call sites. Actual batching happens in `src/main.py:438-447` (the render flusher batches `self._pending_enrichments`), and `src/main.py:412-417` (the stop-flush). The name is a false affordance: a maintainer looking for "where does batching live?" finds it here and in two other places.

### F-7 — BUG (design): sync/async contract split with no I/O anywhere
`src/services/enrich_service.py:20` and `:23` are sync; `:26`, `:29`, `:32` are `async`. A service that fetches and parses remote profiles is inherently async; a sync `extract(page_html)` only makes sense for an in-process HTML parser. The split is copied from the (absent) upstream library for the sync pair and invented locally for the async trio. Since none of it will ever run, the class presents a coherent-looking API surface for a feature the roadmap explicitly excludes.

### F-8 — BUG: `__init__` silently swallows every argument
`src/services/enrich_service.py:13-14`. `*args`/`**kwargs` are accepted and discarded without inspection. The single construction site (`src/main.py:517`) passes nothing, so both are dead flexibility. A caller who writes `EnrichService(http_client=hc, timeout=30)` gets no error, no warning and no effect — a silent-misconfiguration trap. It also means the class has no injectable seam for a future real implementation.

### F-9 — MINOR: unparameterised return annotations and a near-dead import
`src/services/enrich_service.py:21`, `:27`, `:30`, `:33` are bare `dict`; `:24` is `list[tuple[str, dict]]`. Combined with the `{}`/`[]` bodies, a type checker cannot distinguish "no data" from "data of the wrong shape". `from typing import Any` at `src/services/enrich_service.py:9` exists solely for the discarded `*args/**kwargs` at `:13`, `:26`, `:29`, `:32` — i.e. it supports only dead parameters.

### F-10 — BUG: the mutation feature is unreachable even in principle
`src/services/enrich_service.py:29-30` vs `:23-24`. `enrich_url_with_mutations` is supposed to be the "Full" mode path selected by `src/main.py:1187-1200`, but it returns `{}` and never calls `get_mutations`. The user-visible "Full = richer via API mutations" promise (`src/screens/settings_screen.py:1531`) therefore has **no implementation at any layer**.

### F-11 — DOC/DRIFT: the module docstring is stale and contradicts the governing roadmap
`src/services/enrich_service.py:1-5` says "STUB for M1 (socid-extractor not in V2 deps)" and "cover most of it in M2". This is V3; M1/M2 are historical. More importantly, `docs/roadmap.md:8-9` lists "no socid-extractor enrichment pipeline" as an explicit **non-goal**, and `docs/roadmap.md:32` says the deferral is intentional because user-scanner's `extra` fields cover most of it. The file implements an explicitly excluded feature and its own docstring is the only remaining trace of the abandoned plan.

### F-12 — ARCHITECTURE: the "seam" is one-way — the app already has a working enrichment path
`src/services/enrich_service.py:20-33` duplicates, in stub form, capabilities that user-scanner 1.5.2.3 already delivers natively: `src/services/sherlock_service.py:328-341` lifts `Result.extra` + `Result.media` into `ids_data`, and `src/core/enrich_view.py:90` renders them. The roadmap's claim that "module `extra`/`media` fields … cover most of it" (`src/services/enrich_service.py:4` itself) is **verified true**. So the stub's only remaining justification would be the `extra`-fields *don't* cover part of it — but the stub adds nothing to cover it either.

---

## 5) Recommendation — **DELETE the file and every `is_available` branch**

### Rationale

1. **The dependency does not exist.** `socid-extractor` is absent from `pyproject.toml` and from the venv. No wiring can revive the class; `is_available` can never become `True` without inventing a dependency, which would violate the one-to-one discipline the project is built on.
2. **The roadmap forbids the feature.** `docs/roadmap.md:8-9` names "no socid-extractor enrichment pipeline" a non-goal. A stub that pretends the feature is *planned* contradicts the governing document; a stub that says "no-op" is still 33 lines of app-shaped API for an excluded feature.
3. **The data is already there.** `src/services/sherlock_service.py:328-341` → `src/components/result_card.py:211,269-274` → `src/components/profile_detail_dialog.py:832-871` renders native `extra`/`media` today. `src/core/enrich_view.py` proves the display layer needs no `EnrichService`.
4. **A "documented seam" is the weaker option.** Keeping `EnrichService` as a `Protocol`/ABC with a real probe would preserve ~350 lines of dead branches and, worse, a *user-facing no-op toggle* (`src/screens/settings_screen.py:1527-1551`) that looks live. The stub's value is zero and its cost is ~350 lines plus a phantom setting. If socid-extractor ever lands, it should arrive as a **new service** wired to the existing `state.enrichments` / `enrich_view` render path — not by reviving this file, whose API shape (`extract(page_html)`, `get_mutations(url)`) is an unverifiable guess at an absent library.

### Exact edit list

**1. Delete the file**
- `src/services/enrich_service.py` — entire file (33 lines).

**2. `src/main.py`**
- `:87` — remove `from services.enrich_service import EnrichService`
- `:120` — remove `self.enrich_service: EnrichService | None = None`
- `:134-137` — remove `_enrich_queue`, `_enriched_seen`, `_enrich_worker_task` (+ the `:134` comment)
- `:138-142` — remove `_enrich_gen` (+ its 4-line comment)
- `:143-144` — remove `_avatar_warmed` (+ its comment)
- `:162` — remove `self._pending_enrichments: dict[str, dict] = {}`; update the `:155-160` flusher comment that says "progress ticks + enrichment batches"
- `:412-417` — remove the `pending` flush in `_stop_render_flusher`; update the `:407-410` docstring
- `:438-449` — remove the `if self._pending_enrichments:` block + its two trailing comment lines
- `:965-975` — remove the queue init and the `is_available` worker-spawn block
- `:1181-1277` — **delete the whole `_drain_enrich_queue` method** (97 lines)
- `:1408-1419` — remove the "Stream newly discovered found URLs into the enrichment queue" block
- `:1991`, `:2016`, `:2068-2070` — remove `state.enrichments.clear()` / `self._enrich_gen += 1` / `self._enriched_seen.clear()` (keep `:1992-1993` only if `state.enrichments` is kept per item 5 below; otherwise remove the restore too)
- `:2184` — remove the `"enrichments": ...` snapshot field

**3. `src/core/state.py`**
- `:82-84` — remove the "Profile enrichment" comment + `enrichments: dict | None = None`
- `:169` — remove `self.enrichments = {}`
- `:186-192` — remove `set_enrichment()` (already uncalled)
- `:237` — remove `self.enrichments.clear()`
- `:9` — `_ENRICHMENT_CAP` becomes unused → remove (check `src/main.py:443` import goes with it)

**4. `src/screens/results_screen.py`**
- `:387-390` — remove the `enrich = state.enrichments.get(...)` lookup and pass `enrichment=None`
- `:725-731` — remove the `enrichment=...` kwarg
- `:749-753` — remove the enrichment name/fullname append in `_username_filter_key`
- `:178-195` — remove `_enrichment_fingerprint` (its only caller at `:818` then goes too)
- `:818` — remove the fingerprint from the memo dependency tuple

**5. `src/app_shell.py`**
- `:301`, `:391` — remove the `enrichments=dict(app_state.enrichments or {})` kwargs

**6. `src/services/report_service.py`**
- `:66-87` — remove `_IDENTITY_KEYS`, `_DATE_KEYS`, `_fmt_ident`
- `:176`, `:189` — remove the Markdown renderer's `enrichments` param + normalise
- `:218-234` — remove the Markdown "Profile Enrichment Highlights" block
- `:307-309` — remove the HTML `{% if enrich_rows %}` template section
- `:329`, `:344` — remove the HTML renderer's `enrichments` param + normalise
- `:356-375` — remove the HTML `enrich_rows` build
- `:396` — remove `enrich_rows=enrich_rows[:15]`
- `:589`, `:610` — remove the PDF renderer's `enrichments` param + normalise
- `:769-~805` — remove the PDF "Enrichment highlight cards" block

**7. `src/screens/settings_screen.py`**
- `:486-488` — remove `_on_enrichment_mode_change`
- `:1527-1551` — remove the "Enrichment Mode" card (**UX-visible**: the setting disappears from the UI; it is a no-op today, so this is a strict improvement — but it is a product-visible change and should be called out in the release notes)

**8. `src/core/constants.py`**
- `:47` — remove `STORAGE_ENRICHMENT_MODE`

**9. `src/core/enrich_view.py` — keep the file; delete only the unused helper**
- `:147-149` — remove `enrichment_summary` (zero callers; unrelated to this stub)
- **Keep** `:36-144` (`_label`, `_flatten`, `_stringify`, `enrichment_rows`, `is_link_value`, `truncate_value`) — all live via the native `extra`/`media` path.

### Do NOT touch (live native enrichment path)
- `src/services/sherlock_service.py:328-341`
- `src/components/result_card.py:206-290` and `src/components/profile_detail_dialog.py:505-520, 825-920`
- `src/core/enrich_view.py:36-144`
- `src/services/cache_service.py:354-366`

### Verification after the edit
- `grep -rn "EnrichService\|enrich_service\|enrich_url\|batch_enrich\|get_mutations\|state.enrichments\|enrichment_mode\|STORAGE_ENRICHMENT_MODE\|enrichment_summary\|_IDENTITY_KEYS\|_fmt_ident" src/ tests/` → expect **zero** hits.
- `grep -rn "enrichment_rows\|enrich_view" src/` → expect hits only in `result_card.py` and `profile_detail_dialog.py` (the native path).
- `ruff check src/` and `pytest` must stay green; `main.py` loses ~161 lines, `report_service.py` ~90, `settings_screen.py` ~28.

---

## 6) Verdict

**DELETE `src/services/enrich_service.py` and every `is_available` branch it holds up.**

The file is not an unfinished feature — it is a **finished rejection** that was never cleaned up. Its dependency is absent by design (`socid-extractor` is in neither `pyproject.toml` nor the venv), the governing roadmap lists the feature as an explicit non-goal (`docs/roadmap.md:8-9, 32`), and the data it was supposed to produce already arrives natively from user-scanner's `extra`/`media` fields (`src/services/sherlock_service.py:328-341` → `src/core/enrich_view.py:90` → `src/components/result_card.py:271`). Its own docstring (`src/services/enrich_service.py:4`) states the replacement plan was already implemented.

Its concrete harm today is measurable: **≈ 350 lines** of permanently dead code across 7 files, **three dossier exporters** (Markdown `:218-234`, HTML `:356-375`, PDF `:769-~805` in `src/services/report_service.py`) that ship an "Profile Enrichment Highlights" section that can never render, a `state.enrichments` store (`src/core/state.py:82-84`) that is permanently `{}` behind an uncalled `set_enrichment()` helper (`:186-192`), a dead `_enrichment_fingerprint` memo dependency (`src/screens/results_screen.py:178-195`), and a **user-facing "Enrichment Mode" toggle** (`src/screens/settings_screen.py:1527-1551`) that is persisted to disk and provably cannot change any output.

Two internal defects compound the dead weight and are worth fixing in the delete itself rather than preserving: the `_available` attribute is written at `src/services/enrich_service.py:14` but never read by the property at `:17-18` (so the "seam" cannot actually be opened), and three of the five public methods (`:20`, `:23`, `:32`) have **zero call sites in the entire repository** — `extract`, `get_mutations` and `batch_enrich` are pure API fiction, with `get_mutations`'s `list[tuple[str, dict]]` shape (`src/services/enrich_service.py:23`) verifiable against nothing, since no installed package defines it.

Keep `src/core/enrich_view.py` — it is fed by the native path and must survive the deletion.
