# Audit — `src/core/enrich_view.py` (149 lines)

Audited: 2026-10-22 · Truth source: installed `user-scanner` **1.5.2.3**
(`.venv\Lib\site-packages\user_scanner`) · Repo venv Python **3.14.7**

---

## 1) File role

`src/core/enrich_view.py` is a **pure view-model helper**. It converts arbitrary enrichment
mappings into `(key, label, value)` rows for Flet rendering. It performs no I/O, no network
calls, no scraping — it is a pure function over dicts.

**Public API (4 functions):**

| Function | Line | Callers |
|---|---|---|
| `enrichment_rows` | `enrich_view.py:90` | `src/components/result_card.py:271`, `src/components/profile_detail_dialog.py:867` |
| `is_link_value` | `enrich_view.py:133` | `src/components/profile_detail_dialog.py:893` |
| `truncate_value` | `enrich_view.py:139` | `src/components/profile_detail_dialog.py:912` |
| `enrichment_summary` | `enrich_view.py:147` | **none** (dead) |

**Data flow (verified):** `user_scanner` module `validate_*()` → `Result.taken(extra=…, media=…)`
→ `src/services/sherlock_service.py:328-341` (JSON-safe coercion, `ids_data = {"extra":…, "media":…}`)
→ `others` dict on the site row → `result_card.py:211` (`v2_extra = others.get("extra")`) and
`profile_detail_dialog.py:869` (`others.get("extra")`) → **this file**.

**Confirmed NOT the dead socid-extractor path** — this file is fed by the engine's *native*
`extra`/`media` payloads. But note the boundary: **only `extra` is ever passed in.** `media` is
consumed elsewhere for the avatar only (`result_card.py:216`, `main.py:1630`,
`report_service.py:525-526`) and is **never** handed to `enrichment_rows`. See D4.

The module's stated contract (`enrich_view.py:1-8`) is "never drop a field the engine returned" —
that promise is broken at the `media` boundary (D4) and at the nested-date boundary (C1/B2).

---

## 2) Engine key-contract verification (real keys from the installed modules)

Read directly from `.venv/Lib/site-packages/user_scanner/user_scan/`:

**`social/instagram.py` (`validate_instagram`, :10-73)**
```python
extra["fullname"], extra["follower_count"], extra["following_count"],
extra["post_count"], extra["bio"]
media["avatar"]
```

**`dev/github.py` (`validate_github`, :6-135)**
```python
extra["name"], extra["bio"], extra["company"], extra["location"], extra["website"],
extra["email"], extra["followers"], extra["following"], extra["twitter"],
extra["public_repos"], extra["created_at"], extra["links"], extra["organizations"]
media["avatar"]
# note github.py:60-63:  extra["links"] = ", ".join(unique_links)   # ONE comma-joined string
```

**`social/x.py` (`validate_x`, :4-60)**
```python
extra["name"], extra["bio"], extra["location"], extra["created_at"], extra["followers"],
extra["following"], extra["protected"], extra["tweets"]
media["avatar"]
```

**`social/tiktok.py` (`validate_tiktok`, :9-105)**
```python
extra["username"], extra["name"], extra["user_id"], extra["bio"], extra["followers"],
extra["following"], extra["likes"], extra["verified"], extra["private"]
media["avatar"]
```

**`social/reddit.py` (`validate_reddit`, :51-212; `_profile` :168-192)**
```python
extra["id"]            # "t2_<numeric>"
extra["display_name"], extra["bio"], extra["created"]   # _created_at() -> "%Y-%m-%d" string
extra[label] = value   # dynamic labels from a label->value map (:185)
extra[label] = True    # dynamic boolean flags (:189)
extra["nsfw"]
```

**`music/spotify.py` (`validate_spotify`, :4-51)**
```python
extra["name"], extra["created_at"], extra["timezone"], extra["bio"],
extra["pronouns"], extra["is_pro"], extra["is_plus"]
media["image"]          # <-- the only module that uses media["image"]
```

**Tree-wide `media[...]` key census (all 2000+ modules):**
`avatar` × 1848, `banner` × 31, `image` × 11, `avatar_url` × 4, `snapcode`, `profile_image`,
`header`, `gravatar_url`, `cover`, `avatar_full` (× 1 each).

### Contract verdicts

| `enrich_view.py` assumption | Reality | Verdict |
|---|---|---|
| `_extractor` (`:16`, `:100`, `:114`, `:129`) | **Zero hits** in the whole `user_scanner` package and zero in `src/` outside this file | **hallucinated / unreachable** (D2) |
| reserved `"photo"` (`:16`) | No `media["photo"]` / `extra["photo"]` anywhere in user_scanner | **hallucinated** (D3) |
| reserved `"image"`, `"avatar"` (`:16`) | Real *media* keys, but `media` is never passed in, and no module puts them in `extra` | **effectively dead** (D4) |
| reserved set completeness | Missing the 7 other real media aliases (`avatar_url`, `profile_image`, `banner`, `cover`, `header`, `gravatar_url`, `avatar_full`, `snapcode`) | **incomplete** (D4) |
| `_DATE_HINTS` (`:24-33`) vs real date keys | Engine uses `created_at` (github/x/spotify) and `created` (reddit) → both contain `"created"` ✓ | **correct for the real date keys** |
| `_DATE_HINTS` false positives | `"time"` matches **`timezone`** (spotify), `timestamp`, `timeline`, `runtime`, `lifetime`; `"date"` matches `candidate`; `"since"` matches `sunshine`; `"born"` matches `newborn` | **too loose** (C10) |
| value types | Engine encodes booleans as **strings** (`tiktok.py:76-80` → `"true"`/`"false"`; `github.py:38` → `str(bool)`) or real bools (`reddit.py:189` → `True`), counts as strings (`github.py:37-39`), epochs as `"%Y-%m-%d"` strings (`reddit.py:200`) | `_stringify` handles these correctly ✓ |
| key types | `sherlock_service.py:339-340` coerces all keys to `str` before this module sees them | `enrich_view.py:120` `str(key)` is defensive but effectively unnecessary — however it is **not** harmless (see C5) |

**Bottom line:** the file hardcodes almost nothing, so the *engine* contract is largely respected
*by accident*. But every one of the four names it *does* own (`_extractor`, `photo`, `image`,
`avatar`) is either hallucinated or unreachable for the installed engine.

---

## 3) Correctness findings

**C1 — Nested date keys are never humanized (MEDIUM).** `enrich_view.py:120-121` computes
`low = str(key).lower()` from the **top-level** key only, then `:122-126` applies `is_date` to
*every* leaf flattened out of that value. `_flatten` (`:51-69`) recurses but the hint is never
recomputed per leaf. Verified:
```
enrichment_rows({'nested': {'created_at': '2019-04-01'}})
→ [('nested', 'Nested Created At', '2019-04-01')]     # raw ISO, not "Jan 1, 2020"
```
Fix: move the hint test into `_flatten`, where the leaf key is known.

**C2 — Values are stringified *before* `human_date`, defeating its numeric branch (MEDIUM).**
`enrich_view.py:122` calls `_flatten` (which returns already-stringified text) and `:124` then
passes that **string** to `human_date`. `human_date`'s int/float branch (`src/core/format.py:54-59`)
is therefore **unreachable from this file**. Consequences (verified in the repo venv):
```
human_date('1553548800')    -> 'Mar 2019'      # 10-digit int string still works (format.py:66)
human_date('1553548800.0')  -> None            # float epoch -> raw epoch leaks into the UI
```
Fix: pass the raw value to `human_date`, or normalise `"<digits>.0"` before the call.

**C3 — `_MAX_VALUE_LEN` is never enforced inside this module (LOW-MEDIUM).** The comment at
`enrich_view.py:18-21` claims "A value longer than this is truncated for display … Bounded so a
data-URI or token-shaped bio cannot blow up a card or a dialog layout", but `enrichment_rows`
never calls `truncate_value`. The bound exists only because the two consumers happen to truncate
(`result_card.py:277` caps at 90 chars; `profile_detail_dialog.py:912` calls `truncate_value`).
`enrichment_rows` itself returns unbounded strings — e.g. a list value is joined into **one**
unbounded row (`enrich_view.py:66`, `:82-83`). The claim should be enforced here or the comment
corrected.

**C4 — `skip` matching is exact and top-level-only (LOW).** `enrich_view.py:113` compares the
raw top-level key against the caller's set. Nested copies of a skipped key still render, and the
caller sets contain names the engine never emits:
- `profile_detail_dialog.py:838-863` skips `"is_verified"`, but the engine emits **`"verified"`**
  (`instagram.py`, `tiktok.py:76`) → "Verified: Yes" is rendered again in "All Profile Fields".
- it skips `"posts"` / `"posts_count"`, but the engine emits **`"post_count"`** (`instagram.py:57`)
  → duplicate of the metric strip.
- `result_card.py:34-57` has the same drift plus `"followerCount"` / `"followingCount"`
  (camelCase) which the engine never emits.
No aliasing/normalisation layer exists in this file to bridge the gap.

**C5 — The empty-value merge rule is asymmetric and undocumented (LOW).** `enrich_view.py:106-108`:
```python
if v in (None, "", [], {}) and k in merged:
    continue
merged[k] = v
```
Sources are merged `(extras, enrich)` (`:103`), so: the **second** source wins for non-empty
values, but the **first** source wins when the second is empty. The docstring (`:97-98`) only
documents the first half ("overlapping keys keep the enrichment value"). Also `v in (...)` uses
`__eq__`, so `0` and `False` are correctly *not* treated as empty — but an empty value in the
**first** source is still stored (the key is not yet in `merged`) and later renders as a
`"—"` row instead of being dropped.

**C6 — No dedup, no ordering guarantee (LOW).** `enrich_view.py:110-130` keeps dict-insertion
order (extras keys first, then enrich keys) and two distinct top-level keys can produce the
**same label** (`"a_b"` and `"aB"` → both `"A B"`), producing duplicate "All Profile Fields"
labels in the dialog.

**C7 — `"true"`/`"false"` strings are rewritten to "Yes"/"No" (LOW).** `enrich_view.py:84-87`.
Correct for the engine's boolean encoding, but a genuine string value `"false"` (a tag, a
username) is silently rewritten — and the dialog's copy action then copies the **rewritten**
text, not the raw value (`profile_detail_dialog.py:906-913`).

**C8 — Sets render non-deterministically (LOW, theoretical).** `enrich_view.py:78-83` joins a set
in iteration order. The engine never produces sets (`sherlock_service.py:333-337` coerces to
`str`/`list`/`dict`), so this is latent only.

**C9 — `is_link_value` cannot detect the engine's canonical multi-URL field (LOW-MEDIUM).**
`enrich_view.py:133-136` requires no space in the value, but `github.py:60-63` stores
`extra["links"] = ", ".join(unique_links)` — one comma-separated string. Such a value is never
recognised as a link, so it is rendered as dead text instead of a tappable row.

**C10 — Date-hint substring matching is too loose (LOW).** `enrich_view.py:24-33` + `:121`.
`"time"` matches `timezone` (a real spotify key), `timestamp`, `timeline`, `runtime`,
`lifetime`, `sometimes`; `"date"` matches `candidate`; `"since"` matches `sunshine`; `"born"`
matches `newborn`. Any such key whose value happens to parse as a date is silently rewritten
into a date. Suggest token-boundary matching (split the key on `_`/`-`/case boundaries) rather
than substring matching.

**Good behaviour confirmed:** `enrichment_rows(None, None)` → `[]` (no crash); the
`isinstance(source, dict)` guards (`:104`) tolerate non-dict inputs; `enrichment_rows` with
non-str keys cannot raise (the `str(key)` at `:120` and the `str(key)` in the row tuple at `:127`
are correct defensive choices).

---

## 4) Dead code

**D1 — `enrichment_summary` (`:147-149`) is unused.** `grep -rn "enrichment_summary" src/` →
only the definition. Its docstring ("most-informative first") is also wrong: it is plain
`rows[:cap]`, i.e. raw dict order — the opposite of "most-informative". Delete it, or implement
the ranking it promises.

**D2 — The `_extractor` provenance branch (`:16`, `:100`, `:114-115`, `:128-129`) is unreachable
in this engine.** `_extractor` does not exist anywhere in the installed `user-scanner` 1.5.2.3
(zero hits across the whole package) nor anywhere in `src/` outside this file. The
`"Source"` row at `:129` can therefore never be produced by the current data source.

**D3 — `"photo"` in `_RESERVED_KEYS` (`:16`) is a hallucinated key.** No `photo` key exists in
`user_scanner` (media keys are avatar/image/banner/cover/header/profile_image/avatar_url/
snapcode/gravatar_url/avatar_full).

**D4 — `media` never reaches this module, and `_RESERVED_KEYS` is therefore largely inert.**
Both consumers pass only the `extra` dict (`result_card.py:271-274` → `v2_extra`;
`profile_detail_dialog.py:867-870` → `others.get("extra")`). Consequences:
- `media["avatar"]` (1848 modules), `media["banner"]`, `media["cover"]`, `media["image"]`,
  `media["avatar_url"]` … are **dropped before this module sees them** — a direct violation of
  the module docstring ("never drop a field the engine returned").
- The reserved entries `"image"` / `"avatar"` can only ever match if a producer puts them inside
  `extra`, which no module does — so `:113` effectively never fires for them.
- The reserved set also lacks the 8 other real media aliases, so if `media` *were* wired in,
  those URLs would render as generic text rows.

**D5 — `import re` inside `_label` (`:38`)** is re-executed on every call (once per key per
row). Move it to module scope.

---

## 5) Bugs (severity-ordered)

**B1 — MEDIUM — Uncaught `ValueError` from `human_date`'s digit fast-path.**
`enrich_view.py:124` → `src/core/format.py:63-68`:
```python
if text.isdigit():
    if len(text) == 4 and 1900 <= int(text) <= 2100:   # <-- int() NOT guarded
    if len(text) == 10 and 31_536_000 <= int(text) <= ...:  # <-- int() NOT guarded
```
`str.isdigit()` is **True** for Unicode superscript/circled digits, but `int()` rejects them.
Verified on the repo venv (Python 3.14.7):
```
'²³²¹'.isdigit()      -> True
int('²³²¹')          -> ValueError: invalid literal for int() with base 10
'①②③④'.isdigit()      -> True   (also int()-hostile)
```
`human_date` catches `ValueError` around `fromisoformat`/`strptime` (format.py:76, 86) but **not**
around `int(text)`. The exception escapes `human_date` → `enrichment_rows` → the Flet card/dialog
render path.
*Reachability from this file:* the value must live under a **date-hinted** key **and** be exactly
4 or 10 characters of such digits. Low probability, but it is an unhandled crash in a UI render
path, and this file is what funnels arbitrary platform strings into it.
*Assessment of the sibling format finding:* the superscript `ValueError` **is** reachable through
`enrich_view.py:124`; the guard belongs in `format.py:64/66` (e.g. `text.isascii() and
text.isdecimal()`), but this file widens the exposure by calling the parser on arbitrary strings.
*Day-first ambiguity is also inherited:* `format.py:19` (`"%d/%m/%Y"`) precedes `:20`
(`"%m/%d/%Y"`) → verified `human_date('03/04/2019') -> 'Apr 3, 2019'` (day-first), while a
US-platform `03/04/2019` means 4 March. No current engine key emits a slash date, so the
exposure today is theoretical.

**B2 — MEDIUM — Nested date keys render raw (C1).** Proven above; the most likely real-world
miss, because a nested `{"profile": {"created_at": …}}` shape is plausible and the raw ISO
timestamp leaks into the card.

**B3 — MEDIUM — Numeric epochs bypass humanization (C2).** A float epoch renders as
`"1553548800.0"`; the human-readable form is never produced because the value is stringified
before parsing.

**B4 — LOW-MEDIUM — Unbounded row values (C3).** `enrichment_rows` can emit a single row with an
arbitrarily long string (a big bio, a comma-joined link list, a long list value). The dialog
copies the **full** value into `copy_text` (`profile_detail_dialog.py:906-913`) and the raw JSON
preview (`:919-926`) duplicates it; only the visible text is clipped.

**B5 — LOW — Duplicate rows between the metric strip and "All Profile Fields" (C4)** caused by
key-name drift (`verified` vs `is_verified`, `post_count` vs `posts_count`).

**B6 — LOW — String "false"/"true" rewritten (C7)**, and the copy action copies the rewritten
text rather than the raw value.

**B7 — LOW — Duplicate labels from different keys (C6).**

**B8 — LOW — Non-deterministic set rendering (C8).**

**B9 — INFO — `media` fields silently dropped (D4)**, contradicting the module docstring.

---

## 6) Verdict

**Verdict: LIVE, GENERIC, AND GENUINELY USED — but over-claimed and partly mis-specified.**
This file is *not* the dead socid-extractor path: it is fed by the native user-scanner
`extra` payloads, and both `result_card.py` and `profile_detail_dialog.py` call it. Its
generic-by-design approach (no hardcoded key list) is the right call and is what makes it
survive the engine's key drift.

However:

1. **Every hardcoded name it owns is wrong or unreachable for the installed engine** —
   `_extractor` (0 hits in user_scanner), `photo` (0 hits), and `image`/`avatar` (media-only, and
   media never arrives). The `_RESERVED_KEYS` mechanism is ~100% dead weight in the current path.
2. **The "never drop a field" promise fails at the `media` boundary** — every media field except
   the avatar is discarded before this module is reached.
3. **The date-humanization feature is half-implemented** — it misses nested keys (B2) and
   numeric epochs (B3), the two most likely real shapes.
4. **One real (if low-probability) crash path** is inherited from `human_date` (B1), and the
   day-first ambiguity is inherited too.
5. **One of the four exported functions is dead** (`enrichment_summary`, D1) and its docstring
   describes behaviour it does not implement.

### Recommended fixes, in value order

1. `enrich_view.py:120-126` — move the date-hint test **into `_flatten`** so it applies per leaf
   key, and pass the **raw** value to `human_date` (or strip a trailing `".0"`) so numeric epochs
   parse. Fixes B2 + B3 together.
2. `enrich_view.py:122` / `:21` — apply `truncate_value` inside `enrichment_rows` (or amend the
   comment to stop claiming a 300-char bound the module does not enforce). Fixes B4.
3. `src/core/format.py:64,66` — guard the `int()` calls with `text.isascii() and
   text.isdecimal()` (or wrap in `try/except ValueError`). Fixes B1 at the source.
4. `enrich_view.py:16,100,114-115,128-129` — delete the `_extractor` branch and `"photo"` unless a
   holehe/socid producer is (re)introduced; delete `enrichment_summary` (`:147-149`) or implement
   its ranking claim. Fixes D1/D2/D3.
5. Wire `media` into `enrichment_rows` (extend the signature to accept the media dict and add the
   8 real media aliases to the reserved set), **or** amend the module docstring to say `extra`
   only. Fixes D4/B9.
6. `enrich_view.py:133-136` — split comma-joined URL values before the link test so the engine's
   `extra["links"]` becomes tappable. Fixes C9.
7. Optional hardening: normalise keys (camel/snake aliases) before matching `skip`, and switch the
   date-hint match to token-boundary matching. Fixes C4/C10.
