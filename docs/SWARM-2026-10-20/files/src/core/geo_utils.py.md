# Audit — `src/core/geo_utils.py` (205 lines)

**Verdict up front:** this module is a 100%-dead pycountry wrapper. `pycountry` is not installed, so `_PYCOUNTRY_AVAILABLE` is permanently `False` and **every public function returns `None`**. The shipped UI degrades silently (raw location text, no flag emoji, no site country badge). Recommendation: **replace-with-engine-fields** (drop pycountry, keep a dependency-free flag-from-code helper) — details in §4.

---

## 1) File role + degraded-mode reality

### Role
`src/core/geo_utils.py:1` — *"Geographic intelligence utilities powered by pycountry."* It exposes three public helpers:

| Symbol | Line | Purpose |
|---|---|---|
| `CountryInfo` (frozen dataclass) | `src/core/geo_utils.py:100-109` | `name, flag, alpha_2, alpha_3, official_name, subdivision` |
| `get_country_by_tag(tag)` | `src/core/geo_utils.py:112-129` | 2-letter site tag (`'us'`, `'ng'`) → `CountryInfo` |
| `get_site_country(tags)` | `src/core/geo_utils.py:132-139` | first matching country from a site's tag tuple |
| `resolve_location(loc_str)` | `src/core/geo_utils.py:142-205` | free-text profile location → `CountryInfo` (+ subdivision) |

Plus a two-tier cache: `lru_cache` on the public functions (`src/core/geo_utils.py:112, 132, 142`) over an L2 JSON disk cache (`src/core/geo_utils.py:25-35, 56-97`) backed by `services.cache_service.load_geo_cache` / `save_geo_cache`.

### The dependency is absent — verified three ways
- `.venv/Scripts/python.exe -c "importlib.util.find_spec('pycountry')"` → **NOT INSTALLED** (`flet`, `user_scanner`, `phonsint` all resolve).
- `pyproject.toml` `[project].dependencies` = `flet`, `flet-ads`, `user-scanner`, `phonsint` only — **no `pycountry`**.
- `uv.lock` → **no `pycountry` entry**.

So `src/core/geo_utils.py:12-19` always takes the `except ImportError` branch: `_PYCOUNTRY_AVAILABLE = False` (`:11`), `pycountry = None` (`:19`), and the identity shim `remove_accents` (`:21-22`) is installed.

### What the UI actually gets today (degraded mode)
Every public entry point returns `None` unconditionally:
- `get_country_by_tag` → `None` via the guard at `src/core/geo_utils.py:115-116`.
- `get_site_country` → `None` (its loop at `:135-138` only ever calls a function that returns `None`).
- `resolve_location` → `None` via the guard at `src/core/geo_utils.py:145-146`.

Resulting user-visible behaviour (all three fallbacks were already written by the callers, so nothing crashes and nothing goes empty):

| Surface | Call site | Rendered today | Should be (with pycountry) |
|---|---|---|---|
| Profile dossier "Location" row | `src/components/profile_detail_dialog.py:780-781` | raw engine string, **no flag** (`loc_display = loc_text`) | `🇳🇬 Lagos, Nigeria` |
| Result card location line | `src/components/result_card.py:333-336` | raw engine string, **no flag** | `🇳🇬 Lagos, Nigeria` |
| Result card site-country badge | `src/components/result_card.py:564-570` | **never rendered** (`site_geo` is always `None`) | `🇬🇧` next to the site name |
| Sites screen country chips | `src/screens/sites_screen.py:489-492` | bare code `GB` (its own docstring: *"falls back to the bare code"*) | `🇬🇧 GB` |

**The degraded mode is entirely silent in the UI.** The only signal is `logger.warning("pycountry library not available: %s", err)` at `src/core/geo_utils.py:18`, emitted once at import into the log file. Nothing tells the user that the flag feature is off, and nothing tells the developer that the module is a no-op. The *content* (the location string itself) is never lost — only the emoji decoration and the country metadata are.

### Cache layer: also inert
`src/core/geo_utils.py:60` guards the disk-cache load with `if _PYCOUNTRY_AVAILABLE:` → that branch is never entered, so `_DISK_CACHE` stays `{}` (`:59`) for the life of the process. Consequently `cache/geo_cache.json` is **never written by Sherlock** — the geo layer of `src/services/cache_service.py:424-463` is unreachable from the app.

**Cross-file note on the "version guard is always unknown" claim:** `src/services/cache_service.py:430-434` `_pycountry_version()` returns `"unknown"` today via its `ImportError` branch, and the guard at `src/services/cache_service.py:446-447` compares that against the stored `__pycountry__` tag. The guard is *not* what blocks caching — a cache written now would store `"unknown"` and read back `"unknown"` (match). The blocker is that `save_geo_cache` is never reached (`src/core/geo_utils.py:92-94` is dead). The guard only misfires in the hypothetical case of a cache written while pycountry was missing and read after it was installed.

**The 4096 trim direction is real but latent.** `src/services/cache_service.py:459` keeps `list(lookup.items())[:4096]` — the **oldest** 4096 by insertion order — while `src/core/geo_utils.py:82` (`store[key] = new_val`) **appends** newest at the end. Once the cache is full, every freshly resolved location is trimmed away on save and re-resolved on the next launch. Moot today (save never called); it would bite the moment pycountry is installed. Fix direction: keep the **last** N (or evict oldest explicitly), in `cache_service.py:459`, not here.

---

## 2) Consumer census

`grep -rn "geo_utils" src/ tests/` → exactly **three** importers, no tests, no other references:

| # | Importer | Imported symbols | Use sites |
|---|---|---|---|
| 1 | `src/components/profile_detail_dialog.py:15` | `resolve_location` | `:780` (call), `:781` (render) |
| 2 | `src/components/result_card.py:20` | `get_site_country`, `resolve_location` | `:333` / `:564` (calls), `:335` / `:565-570` (render) |
| 3 | `src/screens/sites_screen.py:487` | `get_country_by_tag` (function-local import inside `_country_chip_label`) | `:489` (call), `:490-492` (render) |

`grep -rln "geo" tests/` → **empty**. There is not a single test exercising this module, which is exactly why the always-`None` behaviour was never caught.

Related stale artifact: `pyproject.toml:55-58` — the `[tool.flet.cleanup]` block still lists `pycountry/locales/**/LC_MESSAGES/*.mo` and `pycountry/locales/**/*.po`. pycountry is not a dependency, so these bundler cleanup rules are vestigial leftovers of a dependency that has since been removed.

---

## 3) Dead code (line ranges)

Because `_PYCOUNTRY_AVAILABLE` is a module-level constant that is always `False`, the following ranges **can never execute**:

| Range | What it is | Why it is dead |
|---|---|---|
| `src/core/geo_utils.py:21-22` | `remove_accents` identity shim | only caller is `:167`, unreachable — `resolve_location` returns at `:145` |
| `src/core/geo_utils.py:38-41` | `_country_to_row()` | only caller is `:78`, itself dead |
| `src/core/geo_utils.py:44-53` | `_row_to_country()` | only caller is `:154`, itself dead |
| `src/core/geo_utils.py:60-66` | disk-cache load (`from services.cache_service import load_geo_cache`) | guarded by `if _PYCOUNTRY_AVAILABLE:` at `:60` |
| `src/core/geo_utils.py:70-97` | `_record_disk_hit()` in full — incl. the rate-limited flush (`:83-90`) and `save_geo_cache` (`:92-94`) | only caller is `:204`, unreachable |
| `src/core/geo_utils.py:117-128` | `pycountry.countries.get(alpha_2=...)` block | guarded out at `:115` |
| `src/core/geo_utils.py:132-139` | `get_site_country()` body | every `get_country_by_tag` call returns `None` |
| `src/core/geo_utils.py:146-205` | the entire body of `resolve_location` after the `:145` guard: candidate build (`:156-163`), fuzzy match loop (`:165-200`), disk persist (`:204`) | guarded out at `:145` |
| `src/core/geo_utils.py:167` | `remove_accents(cand)` | unreachable |
| `src/core/geo_utils.py:171` | `pycountry.countries.search_fuzzy(clean)` | unreachable |
| `src/core/geo_utils.py:186` | `pycountry.subdivisions.search_fuzzy(clean)` | unreachable |

**Net live code:** the import block (`:3-22`), the module constants (`:29-35`), `_load_disk_cache` returning `{}` (`:56-59, 67`), the dataclass (`:100-109`), the three `lru_cache` wrappers and their one-line guards. **Every line of actual logic in this file is unreachable.** The module is 205 lines of which ~20 do anything, and those 20 return `None`/`{}`.

The three flagged pycountry call sites (`:118`, `:171`, `:186`) are therefore **never executed** — but see §4.1: the API usage itself is *correct*, so the file would work as written the moment pycountry is installed.

---

## 4) Delete / replace / add-pycountry — recommendation

### 4.1 API correctness (verified against the real pycountry, not from memory)
Since pycountry is absent locally, I downloaded the current release (**26.2.16**) from PyPI into a temp dir and executed the exact calls against it (no project files touched):

| Call site | Verdict | Evidence |
|---|---|---|
| `src/core/geo_utils.py:118` `pycountry.countries.get(alpha_2=tag.strip().upper())` | **correct** | returns `United States`; `c.flag == '🇺🇸'`, `c.official_name == 'United States of America'`; a missing code returns `None` (handled by the `if c:` at `:119`) |
| `src/core/geo_utils.py:171` `pycountry.countries.search_fuzzy(clean)` | **correct** | `search_fuzzy('Nigeria')` → `['Nigeria']`; `ExistingCountries.search_fuzzy` exists in `pycountry/db.py` |
| `src/core/geo_utils.py:186` `pycountry.subdivisions.search_fuzzy(clean)` | **correct** | `search_fuzzy('Lagos')` → `[('Lagos','Nigeria','NG','🇳🇬'), ('Los Lagos','Chile',…)]`; `Subdivision.country` exists and carries `.flag`/`.alpha_2` |
| `src/core/geo_utils.py:14` `from pycountry import remove_accents` | **correct** | public export confirmed; `remove_accents('Cote d Ivoire')` → `'Cote d Ivoire'` |

So there are **no hallucinated APIs** in this file. The `getattr(c, "flag", "")` defensiveness (`:122`, `:175`, `:192`) is unnecessary on modern pycountry but harmless. The only real logic weakness is semantic, not API-level: `search_fuzzy` on a bare free-text location guesses — `resolve_location("Paris, Texas")` would resolve to **France**, and `search_fuzzy` on a city name can pick the wrong country entirely. Fuzzy matching a user-supplied free-text field into a country is a correctness hazard, not just a nicety.

### 4.2 Does the engine already provide this? — yes, for the location string
Grepping the installed engine (`.venv/Lib/site-packages/user_scanner/user_scan/`, **2536 site modules**):
- Many modules set `extra["location"]` **natively** from the target profile, e.g. `user_scan/community/academy.py:40-41` (`extra["location"] = str(user_obj["location"])`), the same pattern in dozens of sibling modules, and `user_scan/adult/chaturbate.py:82-83`.
- `user_scanner/core/result.py:95` defines `self.extra: dict[str, str | bool | int] = {}`; `:106-118` normalises keys; `:179` exports `extra` in the result dict; `CSV_FIELDS` at `:23` includes `extra`.

**Conclusion:** the location *string* that `resolve_location` tries to interpret is already present, verbatim, in the engine payload — the consumer reads it at `src/components/result_card.py:331` (`_merged_profile.get("location")`) and `src/components/profile_detail_dialog.py:779`. What `geo_utils` adds on top is exactly **one flag emoji** (plus alpha-2/3 and an official name, which are used nowhere except the tooltip at `src/components/result_card.py:570`).

What the engine does **not** provide is a tag→country mapping for the *site* badge (`src/components/result_card.py:564`) and the country chips (`src/screens/sites_screen.py:489`). Grepping `user_scanner/core/*.py` for `country` finds no such field — the engine only knows the site's 2-letter *tag*.

### 4.3 Options weighed

| Option | Verdict |
|---|---|
| **add-pycountry** | Works and the API usage is correct, but: (a) it re-adds a third-party dep to a dependency list the owner deliberately slimmed (`pyproject.toml` deps = flet, flet-ads, user-scanner, phonsint; the swarm recently *removed* reportlab/pillow/svglib for the same reason); (b) the owner directive is a **maximal one-to-one wrap of the installed packages**, not a licence to add new ones; (c) the whole fuzzy-matching feature it buys is unreliable for free-text locations (`"Paris, Texas"` → France); (d) it does not actually fix the cache defect at `src/services/cache_service.py:459`. |
| **delete** | Behaviour-preserving (the feature never worked), zero risk, removes 205 lines of dead code. But it permanently drops a *possible* flag badge on site cards/chips that the engine cannot supply. |
| **replace-with-engine-fields** ✅ | Keeps the one genuinely useful artefact (the flag emoji for a 2-letter ISO code) **without any dependency**, and takes the location string straight from the engine. |

### 4.4 ✅ RECOMMENDATION: replace-with-engine-fields (drop pycountry, keep a dependency-free flag helper)

**Keep the flag, drop the library.** A flag emoji for a 2-letter ISO 3166-1 alpha-2 code is *computable* — no country database required:

```python
def flag_for_alpha2(code: str) -> str:
    c = (code or "").strip().upper()
    if len(c) != 2 or not c.isascii() or not c.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - 65) for ch in c)   # regional indicator symbols
```

This reproduces exactly what `pycountry`'s `.flag` property returns (verified: pycountry gives `'🇺🇸'` for `US`), in three lines, with zero dependencies and zero I/O. It also removes the whole `resolve_location` fuzzy-matching hazard.

Note one nuance to preserve: the helper must be fed only *real* country tags. `sites_screen` already builds its country row from the engine's 2-letter tag index (`src/screens/sites_screen.py:495`, `:400-403`), so restricting to tags present in `state.sites_tags_map` keeps pycountry's "unknown code → no flag" behaviour without a country list.

**Concrete fix sketch (file:line of every consumer to touch):**

1. `src/core/geo_utils.py` — replace the whole file (or keep it) with a dependency-free module exporting:
   - `flag_for_alpha2(code: str) -> str` (above), and
   - keep `get_country_by_tag(tag)` **as a thin wrapper** so `sites_screen` needs no change, or touch `sites_screen` directly.
   Delete: the pycountry import block (`:11-22`), the disk-cache layer (`:25-35, 56-97`), `resolve_location` (`:142-205`), and the `CountryInfo` dataclass (`:100-109`) if the name/alpha fields are no longer needed. If `CountryInfo` is kept for the tooltip at `src/components/result_card.py:570`, populate `name` from the tag itself (`"GB"`) rather than a database.

2. `src/components/result_card.py:20` — change the import to the new helper.
   - `src/components/result_card.py:333-336` — **delete** the `resolve_location` call; render `str(location)` directly (this is already the current fallback, so no visual regression). Optionally prefix a flag if the engine also supplied a 2-letter country code in `extra`.
   - `src/components/result_card.py:564-570` — replace `get_site_country(tuple(tags))` with `flag_for_alpha2(<first 2-letter tag in tags>)`; this **re-enables** the badge that has never rendered.

3. `src/components/profile_detail_dialog.py:15` — change the import; `src/components/profile_detail_dialog.py:780-781` — delete the `resolve_location` call, render `_stringify(location)` (current behaviour).

4. `src/screens/sites_screen.py:487-492` — replace `get_country_by_tag(code)` with `flag_for_alpha2(code)`; the chip becomes `🇬🇧 GB` again, matching the docstring at `:486`.

5. `src/services/cache_service.py:424-463` — if the geo module is reduced to a pure flag helper, the whole geo cache layer (`_GEO_MIN_TS_KEY`, `_GEO_MAX_ENTRIES`, `_pycountry_version`, `load_geo_cache`, `save_geo_cache`) becomes unreferenced and should be deleted. If it is kept for any reason, fix the trim direction at `src/services/cache_service.py:459` to keep the **last** 4096 entries, not the first.

6. `pyproject.toml:57-58` — remove the two vestigial `pycountry/locales/...` cleanup rules (no longer any pycountry in the bundle).

7. Tests: add at least one unit test for `flag_for_alpha2` (round-trip `US` → `🇺🇸`, `GB` → `🇬🇧`, `"XX"` → `""`) — the module currently has **zero** test coverage, which is how a permanently-`None` module survived.

---

## 5) Verdict

- **Correct APIs, wrong dependency.** Every pycountry call in this file (`:118`, `:171`, `:186`) is a valid, verified pycountry 26.2.16 API. There are no hallucinated APIs here.
- **The module is entirely dead code.** `pycountry` is absent from the venv, `pyproject.toml` and `uv.lock`; `_PYCOUNTRY_AVAILABLE` is `False` forever, so all three public functions return `None` and every logic line (≈185 of 205) is unreachable (§3 table).
- **The UI is silently degraded, not broken.** Locations still render (engine-supplied), country chips show bare codes, and the site-country badge never appears. The only symptom is one log warning at `src/core/geo_utils.py:18`.
- **The engine already carries the location string** in `extra["location"]` (`user_scanner/core/result.py:95,106-118`; e.g. `user_scan/community/academy.py:40-41`), so the free-text resolver adds a guess-prone fuzzy match rather than information.
- **Recommendation: replace-with-engine-fields.** Reduce the module to a dependency-free `flag_for_alpha2()` (regional-indicator computation, no DB), take location text straight from the engine, and delete the pycountry import, the inert disk-cache layer, the unreachable geo cache in `cache_service.py:424-463`, and the vestigial `pyproject.toml:57-58` cleanup rules. This restores the intended flag badge on result cards and country chips, removes the fuzzy-match misclassification risk, and honours the slim-dependency directive. **Do not add pycountry.**
