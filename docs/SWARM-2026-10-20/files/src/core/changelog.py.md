# Audit: `src/core/changelog.py`

**File:** `src/core/changelog.py` (39 lines)
**Scope:** single-file audit — behaviour of `notes_for()`, coupling to `constants.APP_VERSION` / `update_dialog`, dict-order dependence, dead paths, false claims, concrete fix + missing test.
**Truth sources:** `version.json`, `pyproject.toml`, `src/core/constants.py`, `src/components/update_dialog.py`, `src/services/update_service.py`, `tests/` (9 files, 51 tests collected).
**Method:** read the file; live-verified every `notes_for()` input with the repo venv (`.venv/Scripts/python.exe`); grepped the whole repo for `changelog|notes_for|CHANGELOG`; traced the only call site; read `version.json` / `pyproject.toml` for version facts; ran `ruff check` + `ruff format --check` on the file (both clean).

---

## 1) File role + version.json facts

`src/core/changelog.py` is the **offline mirror of the release notes**. It holds one module-level dict, `CHANGELOG` (:5-34), mapping a version string to a bullet-list string, plus one accessor `notes_for(version)` (:37-39). It has no imports at all — pure data + a 2-line lookup.

**The dict** (:5-34) holds four entries, newest-first by insertion order:

| Key | Lines | First bullet |
|---|---|---|
| `"2.3.0"` | 6-13 | Username permutations: scan separator variants with one toggle |
| `"2.2.0"` | 14-20 | 5,200+ platforms: Maigret 0.6.6 database doubled |
| `"2.1.0"` | 21-26 | Full dependency squeeze and 3,300+ platform polish |
| `"2.0.0"` | 27-33 | Dual-Mode OSINT: Username & Email search |

Live-verified insertion order: `['2.3.0', '2.2.0', '2.1.0', '2.0.0']` — **descending by version**. That ordering is the load-bearing invariant for `:39` and is asserted nowhere (see C2).

**The accessor** (:37-39) is three lines:

```python
def notes_for(version: str) -> str:
    """Changelog entry for a version, falling back to the latest entry."""
    return CHANGELOG.get(version) or next(iter(CHANGELOG.values()), "")
```

### version.json / version facts (all in sync today)

| Source | Version | Build |
|---|---|---|
| `version.json:2-3` | `"2.3.0"` | `build_number: 13` |
| `pyproject.toml:3, :19` | `"2.3.0"` | `build_number = 13` |
| `src/core/constants.py:17-18` | `APP_VERSION = "2.3.0"` | `APP_BUILD_NUMBER = 13` |

Other `version.json` facts that matter to this file: `type: "update"` (:4), `title: "Sherlock 2.3 is here!"` (:5 — note the **short** form "2.3", not the "2.3.0" key used in `CHANGELOG`), `release_notes` (:6, a Markdown superset of the bundled 2.3.0 entry), `mandatory: false` (:7), and `github_url`/`playstore_url` (:8-9).

### Coupling map

- **Only call site:** `src/components/update_dialog.py:21` (`from core.changelog import notes_for`) and `:206` — `notes_for(APP_VERSION)` inside the *"You're up to date"* branch (:196-217), rendered under the heading `f"✓ Latest version · v{APP_VERSION}"` (:202) and the label `"What's New:"` (:203).
- **The "update available" branch does NOT use this module** — it renders the server's `release_notes` straight from the fetched `version.json` (`update_dialog.py:184`). So `changelog.py` only ever feeds the *up-to-date* dialog. That bounds the blast radius: one panel, one call site.
- **The freshness gate is `build_number`, not the version string** (`src/services/update_service.py:83-87`: `if not isinstance(server_build, int) or server_build <= APP_BUILD_NUMBER: return None`). `version.json`'s `"version"` string is **display-only**. Consequence: the version *string* can drift from `APP_VERSION` without any update machinery noticing — and `changelog.py` is keyed on that string.
- **V3 bump scenario (the one that matters).** The owner bumps `constants.APP_VERSION` → `"3.0.0"`, `APP_BUILD_NUMBER` → 14, `pyproject.toml` → `3.0.0`, `version.json` → `build_number: 14`. If no `"3.0.0"` key is added to `CHANGELOG`, then `notes_for("3.0.0")` falls through to `:39` and returns the **`"2.3.0"` entry**. The up-to-date dialog then renders *"✓ Latest version · v3.0.0"* and *"What's New:"* followed by the **2.3.0 bullets**. The user has no way to tell the notes are for the previous release. This is the exact failure the sibling `update_service.py.md` K4 flagged from the other side — **CONFIRMED here from this side, and worse than described (see N1).**
- **Cross-repo wrinkle (context, not a bug in this file):** `constants.UPDATE_CONFIG_URL` (:25-27) points at `raw.githubusercontent.com/Nwokike/Sherlock-**V2**/main/version.json`, while `version.json:8` points at `Nwokike/Sherlock` (no `-V2`). The live-notes source and the bundled-notes source live in different repos, so the V3 release notes must be pushed to two places.

---

## 2) Confirmed issues

### C1 · **High** — `:39` fallback ignores the requested version entirely and always returns the newest entry

`CHANGELOG.get(version) or next(iter(CHANGELOG.values()), "")` — when the key is absent the function **discards `version` completely** and returns the first value in dict order (today: the `"2.3.0"` entry). It is not a "nearest match" fallback; it is an unconditional "give me the newest notes".

Live-verified (repo venv, `sys.path.insert(0,'src')`):

| call | returned entry | correct? |
|---|---|---|
| `notes_for("2.3.0")` | `2.3.0` | yes (exact key) |
| `notes_for("2.3")` | `2.3.0` | yes — but only by coincidence (see N2) |
| `notes_for("2.2.0")` | `2.2.0` | yes (exact key) |
| **`notes_for("2.2")`** | **`2.3.0`** | **NO — should be `2.2.0`** |
| `notes_for("2.10")` | `2.3.0` | fallback, version-agnostic |
| `notes_for("2.1.0")` | `2.1.0` | yes (exact key) |
| `notes_for("2.3.1")` | `2.3.0` | fallback, version-agnostic |
| `notes_for("3.0.0")` | `2.3.0` | **NO — the V3 stale-notes case** |
| `notes_for("")` | `2.3.0` | fallback, version-agnostic |

### C2 · **High** — `:39` depends on dict *insertion order*, which is an unwritten, untested invariant

`next(iter(CHANGELOG.values()))` returns the **first-inserted** value, not the highest-version value. The module currently happens to be authored newest-first (:6, :14, :21, :27), so the two coincide *today*. Two concrete ways this breaks:

- **Owner appends `"3.0.0"` at the bottom** (natural reflex: "add a new block"; and the existing entries read top-down newest→oldest, so appending preserves the *reading* order of the file's own history). Then `notes_for("3.0.0")` → key exists → correct; **but** `notes_for("2.3")`, `notes_for("2.2")`, `notes_for("")` and every unknown version all return the **2.3.0** entry, and if the owner later adds `"3.0.0"` at the bottom and bumps `APP_VERSION` to `"3.0.0"`, that exact key path is fine — while `notes_for("3.0")` still returns 2.3.0's notes. The *silent* failure is that `notes_for` never resolves a *prefix* to the right release.
- **Owner prepends `"3.0.0"` at the top** (the other natural choice). Then the fallback is correct for `3.0.0` but `notes_for("2.2")` now returns the **3.0.0** notes — a *newer* release's notes displayed for an older release.

**Every ordering yields at least one wrong answer.** The ordering is a contract with no enforcement: no test, no assertion, no comment saying "newest first" (the module docstring :1-3 does not mention it).

### C3 · **Medium** — `:3` "guarded by tests" is **FALSE**

Repo-wide grep for `changelog|notes_for|CHANGELOG` (excluding `.venv`) returns hits **only** under `src/`:
`src/components/app_header.py:34,93` (docstring/tooltip only), `src/components/update_dialog.py:5,21,206`, `src/core/changelog.py` itself, `src/screens/settings_screen.py:1410` (tooltip only).

`grep -rn "notes_for|changelog|CHANGELOG|version.json" tests/` → **ZERO hits**. `tests/` contains 9 files / **51 collected tests** (`test_compat_loader.py` 6, `test_cross_scan.py` 8, `test_imports.py` 5, `test_phone_mode_parity.py` 6, `test_services.py` 7, `test_services_all_modes.py` 9, `test_sites_catalog.py` 5, `test_storage_resilience.py` 5). **No test anywhere exercises this module.** The comment is a wish, stated as a fact.

### C4 · **Medium** — `:38` docstring is wrong about what the fallback does

> `"""Changelog entry for a version, falling back to the latest entry."""`

The code does **not** fall back to "the latest entry" — it falls back to the **first-inserted** entry, which equals "the latest" only while the dict is authored newest-first. If the order ever changes, the docstring silently becomes a lie while the code keeps working "fine". The docstring is the only statement of intent in the file, and it describes an invariant the implementation does not enforce. It should say *"the newest release"* and be backed by code that computes the newest by **version**, not by position.

### C5 · **Low** — `:1-3` module docstring: "One line per release" is inaccurate

Every entry is a **six-line** bullet block (:6-13, :14-20, :21-26, :27-33), not one line. If "one line per release" meant "one *entry* per release", the wording is ambiguous; as written it is a factually wrong description of the data that a maintainer might act on (and compress).

---

## 3) NEW issues

### N1 · **High** — the fallback returns *newer* notes for an *older* version (worse than the sibling framing)

The sibling audits framed the bug as "bump `APP_VERSION` without adding a key → stale notes shown as current". That is one symptom. The deeper defect: `notes_for("2.2")` returns the **2.3.0** notes today, *before any version bump*. The function cannot answer "what changed in 2.2?" for **any** version that is not an exact key — it always answers "what's newest". `notes_for("2.2")` and `notes_for("2.3.0")` are indistinguishable. Today only `APP_VERSION` is passed, so this is latent; the moment a second consumer appears (an in-app release-history browser, a "release notes for the version you downgraded from", or a server-supplied version string), it returns plausible, confidently wrong content with no error.

### N2 · **Medium** — there is **no prefix matching at all**; the brief's "prefix matching" dimension is refuted

The audit brief lists *prefix matching ("2.3" matching "2.3.0")* as a behaviour to check. Implementation detail: **there is no prefix logic in this file.** `"2.3"` returns the 2.3.0 entry *only* because the fallback happens to be the newest entry and the newest entry happens to be 2.3.0. Proof it is coincidence: `notes_for("2.2")` — also a prefix of a real key — returns the **2.3.0** entry, not 2.2.0's. A naive test `assert notes_for("2.3") == CHANGELOG["2.3.0"]` passes today **and would still pass after a V3 bump** (fallback → `"3.0.0"` → still not 2.3.0, actually it would fail — but for the wrong reason). Any test must pin the *rule*, not one lucky input.

### N3 · **Medium** — `or` makes an **empty-string entry** indistinguishable from a **missing key**

`CHANGELOG.get(version) or next(...)` — `or` is a *falsy* test, not a *presence* test. If any entry's value is `""` (a placeholder for "notes not written yet", a release with no user-visible changes, or an accidental empty string during a content edit), the exact-match lookup is **discarded** and the fallback fires. Correct semantics are `CHANGELOG[version] if version in CHANGELOG else <fallback>`. Currently latent — no entry is empty — but it is the kind of bug that only shows up after a content edit, far from its cause.

### N4 · **Low** — `next(iter(...), "")` guards only an *empty dict*, and the empty result renders as a broken panel

The `""` default only triggers when `CHANGELOG` itself is empty. If a refactor empties the dict, `notes_for` returns `""` and `update_dialog.py:203-210` renders a bare `"What's New:"` label above an **empty** `ft.Markdown` body — no error, no fallback text, a visibly broken panel. An explicit placeholder ("Release notes unavailable") would be better than `""`.

### N5 · **Low** — the `version` parameter advertises a contract the implementation cannot honour

`notes_for(version: str)` (:37) reads as "notes for *this* version". The implementation can only deliver that for an **exact** key; for everything else it silently substitutes the newest. The parameter is the single most load-bearing input in the file (it is what a version bump breaks) and it is the one thing the fallback throws away.

### N6 · **Low** — stale factual claims shipped in the user-facing notes

`:12` advertises **"• 386 tests"** in the 2.3.0 What's-New panel; this repo collects **51 tests** across 9 files. `:19` claims **"229 tests"** for 2.2.0. Both are user-visible strings rendered by `update_dialog.py:206` and neither matches the shipped repository. Low severity (historical release notes), but they are false claims in the product surface, and the "386" figure appears nowhere else in the repo (`grep -rn "386"` → only `changelog.py:12` and an unrelated `sites_screen.py:737` line-number reference).

### N7 · **Low** — the bundled notes and `version.json`'s `release_notes` are two unsynchronised sources of truth

The same 2.3.0 release exists in two places with **different content**:
- `version.json:6` additionally mentions *"Pasted values auto-extract into the engine's multi-target list"*, *"HTML dossier gains a custom Jinja date filter alongside the core CSS base"*, *"ISO, unix, and platform-specific formats parsed; unreadable values stay raw"*.
- `changelog.py:6-13` additionally mentions *"Email scans retry once through rate limits; cancels now always land"* (as one combined bullet) and *"database stats header"*.

There is no cross-check and no shared source; two writers, two formats, no test. This is the same class of drift the "guarded by tests" comment (:3) pretends to prevent. Also note `version.json:5` titles the release *"Sherlock 2.3 is here!"* — the **short** form — while `CHANGELOG` is keyed on the **full** form `"2.3.0"`. The short/full mismatch is already in the repo, so any version-string parsing in this module must tolerate it (the proposed fix does).

### N8 · **Low** — `notes_for` is called with exactly one value, so its generality is currently dead

Only `update_dialog.py:206` calls it, always with `APP_VERSION` ("2.3.0", an exact key). The `version` parameter currently has exactly one value in the entire codebase — the fallback branch of `:39` is the *only* code path that ever exercises a non-exact key, and today nothing reaches it (the "2.3"/"2.2" rows of C1's table are hypothetical). In other words: **the file's entire error-handling path is dead code in production, and it is wrong the moment it is not.**

### Clean bills of health (checked, no issue)

- `:5` `CHANGELOG: dict[str, str]` — module-level annotation is evaluated at runtime; `dict[str, str]` needs Python ≥ 3.9 and `pyproject.toml:6` sets `requires-python = ">=3.14"`, `.python-version` = `3.14`. Fine.
- `ruff check src/core/changelog.py` → **All checks passed!** (rule set includes `S`, `TRY`, `EM`, `RET`, `SIM`, `PERF`, `RUF` per `pyproject.toml:86-96`); `ruff format --check` → already formatted.
- No imports, no I/O, no network, no flet surface — nothing to verify against the installed flet 1.0.4.
- `CHANGELOG` is never mutated anywhere in the repo (grep: only reads at `:39` and the import at `update_dialog.py:21`) — no cache-invalidation or mutation-order concern.
- The "update available" path correctly uses the **server's** `release_notes` (`update_dialog.py:184`) and is untouched by this module — so a server-provided newer release does not hit the fallback. Correct separation.
- Docstring ":1-2 … shown by the update dialog when the app is up to date — works fully offline" is **accurate**: `update_dialog.py:196-217` is the only consumer, and the bundled dict needs no network.

---

## 4) Proposed fix (code)

### 4a. Drop-in replacement for `changelog.py:37-39`

Replace the current two-line body with a **version-ordered** lookup that resolves prefixes and never depends on dict position. `_vkey` turns `"2.3"` → `(2, 3)` and `"2.3.0"` → `(2, 3, 0)`, so `(2,3) < (2,3,0) <= (2,3,1)` and the comparison is well-ordered (a missing patch level is "below" the full triple, which is the desired "at or below" semantics).

```python
def _vkey(version: str) -> tuple[int, ...]:
    """Sortable version key: '2.3' -> (2, 3), '2.3.0' -> (2, 3, 0)."""
    return tuple(int(part) for part in version.split("."))


def notes_for(version: str) -> str:
    """Changelog entry for `version`.

    Falls back to the nearest release at or below it, chosen by version
    number (never by dict position): '2.3' -> '2.3.0', '2.3.1' -> '2.3.0',
    '2.4.0' -> '2.3.0'. Returns '' only if CHANGELOG is empty.
    """
    if version in CHANGELOG:
        return CHANGELOG[version]
    try:
        target = _vkey(version)
    except ValueError:
        return CHANGELOG[min(CHANGELOG, key=_vkey)] if CHANGELOG else ""
    at_or_below = [v for v in CHANGELOG if _vkey(v) <= target]
    if not at_or_below:
        return CHANGELOG[min(CHANGELOG, key=_vkey)] if CHANGELOG else ""
    return CHANGELOG[max(at_or_below, key=_vkey)]
```

Properties this buys:

| input | before | after |
|---|---|---|
| `"2.3.0"` | `2.3.0` | `2.3.0` (exact) |
| `"2.3"` | `2.3.0` (coincidence) | `2.3.0` (rule) |
| `"2.2"` | **`2.3.0`** ✗ | `2.2.0` ✓ |
| `"2.3.1"` | `2.3.0` | `2.3.0` ✓ |
| `"3.0.0"` | `2.3.0` (position) | `2.3.0` (**version**-ordered — same answer, correct reason) |
| `""` | `2.3.0` | `2.3.0` (fallback, ordered) |

The `version in CHANGELOG` presence check also fixes **N3** (an empty-string entry is no longer treated as missing).

### 4b. The part that actually stops the V3 stale-notes case

**The 4a fix alone does NOT solve the V3 scenario.** With `APP_VERSION = "3.0.0"` and no `"3.0.0"` key, `notes_for("3.0.0")` still returns the `"2.3.0"` entry (it is the nearest release *at or below* 3.0.0) — and `update_dialog.py:202` still headlines it *"✓ Latest version · v3.0.0"*. **The stale-notes mislabelling is a dialog problem, not a lookup problem**, and it needs one extra change at the call site (outside this file):

```python
# src/components/update_dialog.py:201-203
exact = APP_VERSION in CHANGELOG
headline = f"✓ Latest version · v{APP_VERSION}" if exact else f"✓ v{APP_VERSION} is up to date"
label = "What's New:" if exact else f"Latest release notes (v{latest_release()}):"
```

i.e. **either** add a `"3.0.0"` key to `CHANGELOG` when bumping (the cheap, correct-by-default path — the docstring at :1-3 already asks for this, it just isn't enforced), **or** have the dialog distinguish "notes for this version" from "the newest notes we know about". Recommended: do both — the lookup fix stops the *wrong-notes* class of bug, the dialog guard stops the *mislabelled-notes* class.

### 4c. The missing test (new file `tests/test_changelog.py`)

`tests/conftest.py:5` already puts `src/` on `sys.path`, so the imports below work as-is. `pyproject.toml:99` sets `"tests/**" = ["S101"]`, so bare asserts are fine.

```python
"""Changelog lookup semantics — see src/core/changelog.py."""

from core.changelog import CHANGELOG, notes_for
from core.constants import APP_VERSION


def test_notes_for_exact_key():
    assert notes_for("2.2.0") == CHANGELOG["2.2.0"]


def test_notes_for_resolves_prefix_and_patch_to_nearest_at_or_below():
    assert notes_for("2.3") == CHANGELOG["2.3.0"]      # prefix of a release
    assert notes_for("2.2") == CHANGELOG["2.2.0"]      # prefix of an OLDER release
    assert notes_for("2.3.1") == CHANGELOG["2.3.0"]    # patch below the newest
    assert notes_for("2.1") == CHANGELOG["2.1.0"]


def test_notes_for_unknown_version_uses_newest_release_not_first_inserted(monkeypatch):
    """Guards the V3 bump: the fallback must be version-ordered.

    Reversing the dict makes the current implementation (changelog.py:39,
    `next(iter(CHANGELOG.values()))`) return the OLDEST entry and fail here.
    """
    import core.changelog as changelog

    newest = max(changelog.CHANGELOG, key=lambda v: tuple(int(p) for p in v.split(".")))
    monkeypatch.setattr(
        changelog, "CHANGELOG", dict(reversed(list(changelog.CHANGELOG.items())))
    )
    assert changelog.notes_for("99.0.0") == changelog.CHANGELOG[newest]


def test_changelog_covers_the_shipping_app_version():
    """Makes the 'guarded by tests' claim at changelog.py:3 actually true."""
    assert APP_VERSION in CHANGELOG, (
        f"changelog.py has no entry for APP_VERSION={APP_VERSION}; "
        "the up-to-date dialog will show stale release notes"
    )
```

Against the **current** implementation:

- `test_notes_for_resolves_prefix_and_patch_to_nearest_at_or_below` → **FAILS** on `notes_for("2.2")` (returns `2.3.0`) → catches N1.
- `test_notes_for_unknown_version_uses_newest_release_not_first_inserted` → **FAILS** (reversed dict makes `next(iter(...))` yield `"2.0.0"`) → catches C2/C1.
- `test_notes_for_exact_key` → passes today (regression guard).
- `test_changelog_covers_the_shipping_app_version` → passes today, and is the **exact** test that would go red the moment `constants.APP_VERSION` is bumped to `"3.0.0"` without a matching `CHANGELOG` key → turns the false claim at `:3` into a real guard.

### 4d. Optional: an explicit "latest known release" helper

If the dialog is to distinguish "these are *this* release's notes" from "these are the newest notes we ship", give it an explicit API rather than making it reason about the fallback:

```python
def latest_release() -> str:
    """Newest release in the bundled changelog, by version (not position)."""
    return max(CHANGELOG, key=_vkey) if CHANGELOG else ""
```

### 4e. Optional: fix the docstring while in there

```python
"""Bundled changelog shown by the update dialog when the app is up to
date — works fully offline. One entry per release, newest version first;
keep the entry for the current APP_VERSION in sync when bumping
(`tests/test_changelog.py` enforces this)."""
```

and correct `:38` to `"""Changelog entry for `version`, else the nearest release at or below it."""` — which is what the fixed implementation actually does.

---

## 5) Verdict

**No — the file is not otherwise perfect.** It is 39 lines, lint-clean, import-free, and free of flet/version API misuse, but it contains **one High-severity behavioural defect** that the owner will hit on the V3 bump, plus a **second High-severity defect** (dict-order dependence) that makes the file's correctness a coincidence of how the dict happens to be written today.

Summary of the verdict:

- **Behaviour (dimension 1).** `notes_for()` is exact-match-only in practice; the fallback discards the requested version and returns the newest entry. There is **no prefix matching** (the brief's premise is refuted — `"2.3"` matching `"2.3.0"` is coincidence, and `"2.2"` proves it). Missing-key behaviour is "silently show the newest notes", which is the worst available option because it is plausible-looking and unlabelable. **Fail.**
- **Coupling (dimension 2).** One call site (`update_dialog.py:206`), one consumer panel, all versions in sync today (`2.3.0` / build 13 across `version.json`, `pyproject.toml`, `constants.py`). The update gate is `build_number`, so the version string can drift without tripping anything. After the V3 bump without a `CHANGELOG` key, the up-to-date dialog will headline *"✓ Latest version · v3.0.0"* over the **2.3.0** bullets — silent, plausible, wrong. **Fail (must be fixed before the V3 bump ships).**
- **Concrete fix (dimension 3).** §4a (version-ordered nearest-at-or-below lookup, 4a) + §4c (three regression tests, two of which fail today). Note the honest caveat in §4b: the lookup fix alone does **not** stop the stale-notes mislabelling — the dialog needs a one-line guard, or the owner must add the `CHANGELOG` key (which §4c's third test now enforces). **Fixable in ~15 lines + one small test file.**
- **Verdict (dimension 4).** **Not perfect.** 2 confirmed High, 2 confirmed Medium, 1 confirmed Low, plus 8 new findings. The file is *small and legible*, which is exactly why the defects went unnoticed: the whole thing is one dict and one `or` expression, and the `or` is load-bearing in a way the docstring does not describe. The single most valuable change is the **test file** — three tests, two of which fail against today's code, and one of which turns the false ":3 guarded by tests" comment into a true guard that fires on the very next version bump.

**Priority order for the owner:** (1) add `tests/test_changelog.py` from §4c — it turns the 2.3.0 bump into a red test instead of a silent lie; (2) apply the §4a lookup fix; (3) add the `CHANGELOG` key on every version bump (now enforced) **and** apply the §4b dialog guard so a future missing key degrades to "Latest release notes (v2.3.0)" instead of "What's New:" over the wrong bullets; (4) fix the `:3` and `:38` docstrings to match the code.
