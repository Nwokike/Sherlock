# Dependency Audit: `packaging` (v26.3) — for Sherlock-V3 update service

## 1) Installed verification

Source of truth: `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/packaging`

| Item | Evidence (file:line) |
|---|---|
| Version `26.3` | `packaging/__init__.py:9` → `__version__ = "26.3"` |
| Dist-info | `packaging-26.3.dist-info/METADATA:2-3` → `Name: packaging` / `Version: 26.3` |
| Requires-Python | `packaging-26.3.dist-info/METADATA:6` → `>=3.9` (app requires `>=3.14`, `pyproject.toml:6` — compatible) |
| Installer | `packaging-26.3.dist-info/INSTALLER` → `uv` |
| Own dependencies | **none** (`Requires-Dist` count = 0 in METADATA) — zero transitive weight |

Core classes present and importable (verified by live execution in the app venv):

| Class | Location |
|---|---|
| `Version` | `packaging/version.py:340` |
| `InvalidVersion` (ValueError) | `packaging/version.py:124` |
| `parse()` helper | `packaging/version.py:110` |
| `VERSION_PATTERN` | `packaging/version.py:233` |
| `Specifier` | `packaging/specifiers.py:220` |
| `SpecifierSet` | `packaging/specifiers.py:766` |
| `InvalidSpecifier` | `packaging/specifiers.py:122` |
| `Requirement` | `packaging/requirements.py:35` |
| `InvalidRequirement` | `packaging/requirements.py:27` |
| `Marker` / `InvalidMarker` | `packaging/markers.py:380` / `:61` |
| `default_environment()` (PEP 508 env) | `packaging/markers.py:364` |
| `canonicalize_name` / `canonicalize_version` | `packaging/utils.py:82` / `:154` |

Live semantics check (`.venv/Scripts/python.exe`): `Version("2.10") > Version("2.9")` → `True`;
`Version("1.0") == Version("1.0.0")` → `True`; `Version("2.3.0") > Version("2.3.0rc1")` → `True`;
`"not-a-version"` and `"2.3.0-beta+build!!"` raise `InvalidVersion`. Markers work:
`Requirement('httpx>=0.24; python_version >= "3.9"')` parses fully.

**Import status in app: NEVER imported.** `grep -rn "packaging" src/ tests/ pyproject.toml` → 0 hits.
Only reverse dependency: `pytest 9.1.1 -> packaging>=22` (`uv.lock:391-397`).
`packaging` is a **dev-only transitive** — it is *not* in `pyproject.toml:7-12` runtime
`dependencies` (`flet`, `flet-ads`, `user-scanner`, `phonsint`) and *not* in `uv.lock:471-477`
project runtime deps. It is only reachable via `uv.lock:479-483` dev group (`pytest`).

## 2) App's current version-comparison code

**There is no hand-rolled version-string comparison in the app.** The update gate is an
**integer `build_number` comparison**, which cannot suffer `"2.10" < "2.9"`-class bugs.

`src/core/constants.py:17-18`
```python
APP_VERSION = "2.3.0"
APP_BUILD_NUMBER = 13
```

`src/services/update_service.py:83-87` — the entire freshness decision:
```python
            server_build = data.get("build_number", 0)
            # Policy: announcements are gated on build_number like updates
            # (prevents remote announcement spam on every launch).
            if not isinstance(server_build, int) or server_build <= APP_BUILD_NUMBER:
                return None
```
`server_build` comes from `version.json` (`"build_number": 13`, `"version": "2.3.0"`). The
`"version"` string is only ever *displayed* — `src/services/update_service.py:97`
(`version=_safe_text(data.get("version"), APP_VERSION)[:50]`) and rendered at
`src/components/update_dialog.py:162,177,202`. It is never compared, sorted, or parsed.

`src/core/changelog.py:37-39` — exact-key dict lookup, not an ordering comparison:
```python
def notes_for(version: str) -> str:
    """Changelog entry for a version, falling back to the latest entry."""
    return CHANGELOG.get(version) or next(iter(CHANGELOG.values()), "")
```
Sole caller: `src/components/update_dialog.py:206` → `notes_for(APP_VERSION)`.

Searches that came back empty (no comparison logic exists):
`tuple(int` / `tuple(map(int` / `map(int` → 0 hits repo-wide;
`APP_VERSION < > = !=` or `version < > =` against a string literal → 0 hits in `src/`;
`Requirement` / `SpecifierSet` / `Specifier` / `Marker` → 0 hits in `src/`.

## 3) Risk analysis + concrete recommendation

**The premise of the audit does not hold.** There is no string version comparison to fix.
`build_number` is a monotonic integer, and `isinstance(server_build, int)` rejects
non-int payloads, so malformed/attacker-supplied `version.json` cannot crash or invert the
gate. `packaging.Version` would add *no* safety here.

**Real issue found (small, but genuine) — silent changelog fallback.**
`src/core/changelog.py:39` falls back to `next(iter(CHANGELOG.values()), "")`, i.e. the
*first* dict entry, which is the newest release (`"2.3.0"`, `changelog.py:6`). If
`APP_VERSION` is bumped to e.g. `"2.4.0"` without adding a `CHANGELOG` key, the up-to-date
dialog will show the **2.3.0 release notes labelled as current**. Verified live:
`notes_for("2.3")` and `notes_for("2.10")` both return the 2.3.0 entry.
Note `packaging.Version` would *not* fix this by itself — the correct fix is a
"nearest entry ≤ current version" lookup or an explicit guard, not a parse-and-compare.

**Real issue #2 — the test guard that does not exist.**
`src/core/changelog.py:3` claims *"keep the entry for the current APP_VERSION in sync when
bumping (guarded by tests)"*. But `grep -rn "changelog|notes_for|APP_VERSION|build_number" tests/`
returns **0 hits** across all 8 test files. There is no version-consistency test. The
docstring is stale/aspirational.

**Real issue #3 — `packaging` is NOT a free runtime dependency.**
The task framing ("it's already installed") is true only for the dev/test venv. It arrives
solely through `pytest` (dev group). Sherlock-V3 is a Flet app that ships as an Android/
desktop bundle built from `pyproject.toml [project] dependencies` — those are `flet`,
`flet-ads`, `user-scanner`, `phonsint`; none of them depend on `packaging` (verified via
`importlib.metadata.requires()`). So `from packaging.version import Version` in `src/`
would be a **new runtime dependency**, requiring a `pyproject.toml` + `uv.lock` change.
It would also be a poor trade: adding a library to the shipped binary for logic the app
does not need.

### Concrete recommendation

1. **Do not adopt `packaging` for the update service.** No bug to fix; it would convert a
   dev-only transitive into a shipped runtime dependency for zero benefit. Leave
   `update_service.py:86` exactly as is.
2. **Fix the changelog fallback** — `src/core/changelog.py:37-39`. Either make it raise /
   return a neutral string on a miss, or pick the highest entry not newer than the current
   version. A 3-line helper keeps the "latest" semantics correct without a new dependency.
3. **Add the missing test** the docstring promises — a `tests/` case asserting
   `APP_VERSION in CHANGELOG` (i.e. `changelog.CHANGELOG` contains the current version key)
   and that `version.json`'s `build_number`/`version` agree with `src/core/constants.py:17-18`.
   This closes the loop that `changelog.py:3` asserts but nothing enforces.
4. **Optional cleanup**: `packaging` is an unused transitive in the app. It is legitimately
   required by `pytest`, so it must stay in the lockfile — no action needed. Just do not
   import it from `src/`.

## 4) Verdict

**ISSUES FOUND** (low severity, and *not* in the direction the audit hypothesized)

- `packaging` 26.3 itself: **PERFECT** — installed, correct, self-contained, zero own deps.
- App's version comparison: **PERFECT** — no hand-rolled string comparison exists; the gate
  is a monotonic integer at `src/services/update_service.py:86`. `packaging` is unnecessary.
- Actual defects found: (a) silent changelog fallback at `src/core/changelog.py:39`
  shows stale notes on a version bump; (b) the "guarded by tests" claim at
  `src/core/changelog.py:3` is false — no such test exists; (c) `packaging` is a
  dev-only transitive, so importing it from `src/` would *add* a runtime dependency
  rather than remove one.

**Recommendation: do not add `packaging` to the app. Fix (a) and (b) instead — no new dependency needed.**
