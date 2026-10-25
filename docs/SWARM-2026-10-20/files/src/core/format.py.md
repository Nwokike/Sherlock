# Audit: `src/core/format.py`

**File:** `src/core/format.py` (102 lines)
**Scope:** single-file audit — date parsing/humanization, count formatting, dead paths, call-site census.
**Truth source:** the installed stdlib on **Python 3.14.7** (`uv run python -V`) + this repo. No third-party imports exist in this file (`calendar`, `datetime` only).
**Method:** read the file; executed every branch of `human_date` / `format_count` against the real module with ~60 inputs; grepped all call sites across `src/` and `tests/`; ran `uv run ruff check src/` (clean).
**Lint status:** `uv run ruff check src/core/format.py` → *All checks passed* (repo selects `E,F,W,UP,B,Q,C4,PERF,ERA,I,T20,DTZ,RUF,S,TRY,BLE,EM,A,SIM,RET,RSE`; only `E501,EM101-103,TRY003,BLE001,S110,SIM105,TRY300,TRY301` are ignored).

---

## 1) File role

`src/core/format.py` is the app's **presentation-layer formatting utility**: it converts machine values (counts, epoch timestamps, third-party date strings) into the strings a human reads in a card, a dialog, or a dossier.

The module docstring (`src/core/format.py:1-7`) claims two jobs:

1. "Single home for '5,203'-style rendering so cards, headers, and reports agree" (`:2-4`)
2. "Also hosts `human_date()` — the one stdlib date-parser shared by cards, dialogs, and Jinja templates" (`:5-6`)

**Reality check on the brief's premise:** the file contains **only two public functions and no size/duration code**. There is no KB/MB helper, no duration ("2h 5m") helper, no byte formatter anywhere in `src/` — the only byte arithmetic is raw (`src/core/logger_handler.py:132`, `src/core/logger_handler.py:139`, `src/services/cache_service.py:195`) and the one human-facing size string in the product ("21MB smaller") is hand-typed prose in `src/core/changelog.py:19`. So "durations, sizes" in the task brief do not exist as code and are not missing implementations of a stated contract — the module docstring only ever claimed counts + dates. If the product later needs "21 MB" / "2h 5m" strings, there is currently **no** single home for them.

**Actual surface (2 public symbols):**

| Symbol | Lines | Role |
|---|---|---|
| `_DATE_FORMATS` | `src/core/format.py:14-24` | 8 `strptime` patterns, day-precision first then month-precision |
| `format_count(value)` | `src/core/format.py:27-39` | int/float → thousands-grouped string; everything else `str()`'d |
| `human_date(value)` | `src/core/format.py:42-102` | epoch/ISO/platform date → "Apr 1, 2019" / "Apr 2019" / "2019", or `None` |

**Dependencies:** stdlib only (`calendar`, `datetime`). No flet, no third-party. `src/core/__init__.py` is **empty (0 bytes)** — nothing is re-exported; every consumer imports the module path directly (`from core.format import …`). There is no `__all__`.

---

## 2) Function census

### 2.1 `format_count` — `src/core/format.py:27-39`

| Call site | Argument type | Result |
|---|---|---|
| `src/components/targets_card.py:39` | `selected_count` (int) | `"5,203 networks selected"` |
| `src/components/targets_card.py:43` | `total_count` (int) | `"Scanning all 5,203 social networks"` |

- **Used, but by ONE component only.** The module docstring's "cards, headers, and reports agree" is **not true of counts**: the dossier/report renderers print raw counts with no grouping — `src/services/report_service.py:295` (`{{ found_count }}`), `src/services/report_service.py:677` (`str(total_sites or SITES_TOTAL_FALLBACK)`), `src/services/report_service.py:705` (`f"{total_sites or SITES_TOTAL_FALLBACK} platforms."`). A card shows "5,203 networks" while the HTML dossier shows "5203" for the same number.
- The `float` branch (`src/core/format.py:37-38`) and the `bool` branch (`src/core/format.py:33-34`) are **unreachable in production**: both call sites pass `int`.
- No test anywhere references it (`grep -rl "human_date\|format_count" tests/` → no hits).

### 2.2 `human_date` — `src/core/format.py:42-102`

| Call site | Input | `None` handling |
|---|---|---|
| `src/core/enrich_view.py:124` | `text` (already `str()`-ed by `_stringify`, `src/core/enrich_view.py:84`) | `if human:` → keeps raw (`:125-126`) ✔ |
| `src/services/report_service.py:56` | Jinja filter arg | `value is None → ""` (`:54-55`), else `human_date(value) or str(value)` ✔ |
| `src/services/report_service.py:86` | `text = str(v)` (`:84`) | `human_date(text) or text` ✔ |
| `src/components/profile_detail_dialog.py:804` | `raw_date = _stringify(join_date)` (`:796`) | `human_date(raw_date) or raw_date` ✔ |

- **All four call sites guard `None` correctly** — the "returns None → keep the raw string" contract (`:49-50`) is honoured everywhere.
- **All four call sites pre-stringify**, so the `int`/`float` epoch branch (`src/core/format.py:54-59`) is **dead in production**; only the 10-digit *string* branch (`src/core/format.py:66-68`) is live for epoch data. The int/float branch survives only for direct API users/tests.
- No tests reference it.

### 2.3 Dead / unreachable code paths (summary)

| Path | Lines | Status |
|---|---|---|
| `isinstance(value, (int, float))` epoch branch | `:54-59` | unreachable from all 4 call sites (they stringify) |
| `float` branch of `format_count` | `:37-38` | unreachable (both callers pass int) |
| `bool` branch of `format_count` | `:33-34` | unreachable (both callers pass int) |
| `year_only` early-return | `:94-96` | never fires for its stated purpose (bare years are caught earlier at `:64-65`); it fires **only** on compact ISO dates, where it returns garbage → see **B1** |
| `Z` → `+00:00` rewrite | `:71-72` | redundant on Python ≥ 3.11 (`fromisoformat` accepts `Z` natively); project requires ≥ 3.14 |
| `month_precision` computed from the leaked loop var `fmt` | `:88` | computed even when the loop found nothing (dead assignment, discarded by the `dt is None` guard at `:98-99`); also depends on a leaked loop variable (an empty `_DATE_FORMATS` would raise `NameError`) |

### 2.4 Unused exports

**None.** Both public functions have live call sites. `src/core/__init__.py` is empty, so there is no re-export surface to prune. There is, however, **no `__all__`**, so `calendar` and `datetime` (module-level imports) are also star-importable — cosmetic only.

---

## 3) Bugs (severity-ordered)

### B1 — MEDIUM — Compact/basic ISO dates are returned raw, because precision is inferred by counting hyphens

`src/core/format.py:92-96`

```python
parts = candidate.split("-")
month_precision = len(parts) == 2
year_only = len(parts) == 1
if year_only:
    return candidate
```

`datetime.fromisoformat` (`:75`) also accepts the **basic** ISO form `YYYYMMDD` and `YYYYMMDDTHHMMSS`, which contain **no hyphen**. So `len(parts) == 1` does not mean "year only" — it means "either a bare year or a compact date". Verified on Python 3.14.7:

```
human_date("20190401")      -> '20190401'        # parsed as 2019-04-01, then returned raw
human_date("20190401T120000") -> '20190401T120000'
```

Expected: `"Apr 1, 2019"`. The user sees a machine timestamp on the card/dossier.

The branch was clearly written for a bare year (`"2019"` → `"2019"`), but bare years never reach it: `str.isdigit()` (`:63`) catches all-digit 4-char strings in 1900–2100 at `:64-65` and returns early. So **the branch has no valid purpose and its only effect is to corrupt compact dates.**

**Fix:** infer precision from the *shape of the original text*, not from hyphen count — e.g. `re.fullmatch(r"\d{4}", text)` → year-only; `re.fullmatch(r"\d{4}-\d{2}", text)` → month precision; `re.fullmatch(r"\d{8}", text)` → full date. Or normalise the compact form (`YYYYMMDD`) into the extended form before parsing.

---

### B2 — MEDIUM — `human_date` can raise `ValueError` on Unicode digit input (crashes the render path)

`src/core/format.py:63-66`

```python
if text.isdigit():
    if len(text) == 4 and 1900 <= int(text) <= 2100:
        ...
    if len(text) == 10 and 31_536_000 <= int(text) <= 4_102_444_800:
```

`str.isdigit()` is `True` for non-decimal Unicode digits (e.g. `U+00B2 SUPERSCRIPT TWO`) that `int()` **rejects**. Verified:

```
human_date("²²²²") -> ValueError: invalid literal for int() with base 10: '²²²²'
```

This is an uncaught exception inside a function whose whole job is to survive junk, and it is called straight from four render paths (`src/core/enrich_view.py:124`, `src/services/report_service.py:56`, `src/services/report_service.py:86`, `src/components/profile_detail_dialog.py:804`) — the module docstring's "never crash a render on a bad count" (`:5`) and the function's "never render a wrong date on a guess" (`:49-50`) both promise the opposite.

Note the same class of input is *not* a crash: `"０１９９"` (full-width digits) → `None`, because `len != 4/10` in that shape. The crash needs exactly 4 or 10 superscript characters.

**Fix:** `text.isascii() and text.isdigit()` (or `text.isdecimal()`, which is `False` for superscripts), and/or wrap the two `int()` conversions in `try/except ValueError`.

---

### B3 — MEDIUM — Ambiguous slash dates are silently resolved day-first, producing wrong dates for US-format sources

`src/core/format.py:19-20` — `"%d/%m/%Y"` is tried **before** `"%m/%d/%Y"`, so every date that is valid in both orders is read as day/month:

```
human_date("05/04/2019") -> 'Apr 5, 2019'    # US-format source meant May 4
human_date("04/05/2019") -> 'Apr 5, 2019'    # US-format source meant May 4
human_date("12/31/2019") -> 'Dec 31, 2019'   # only unambiguous ones land right
```

Enrichment data comes from third-party platform scrapers ("whatever shape the platform uses" — `:45-46`), and US-style `MM/DD/YYYY` is common. The function then renders a **wrong date**, which is precisely what `:49-50` says it will never do.

**Fix:** pick one order and drop the other, or refuse ambiguous slash dates (return `None` → callers keep the raw string), or accept an explicit `dayfirst`/locale argument.

---

### B4 — LOW/MEDIUM — The docstring's headline example is factually wrong, and the same instant renders two different ways

`src/core/format.py:43`

```python
"""Humanize a profile date ("2019-04-01T12:00:00Z" -> "Apr 2019").
```

Verified actual behaviour:

```
human_date("2019-04-01T12:00:00Z") -> 'Apr 1, 2019'      # NOT "Apr 2019"
```

And the same instant expressed as an epoch renders **month-precision**:

```
human_date(1557836800)      -> 'May 2019'
human_date("1557836800")    -> 'May 2019'
human_date("2019-05-01")    -> 'May 1, 2019'
```

So output shape depends on the *encoding* of the input, not on the instant. The claim "Precision is preserved honestly" (`:47-48`) is violated: an epoch carries full second precision and even the day, yet only "May 2019" is shown, while the same day as an ISO string shows "May 1, 2019".

This also contradicts the shipped product copy in `version.json` — "Join/created dates render as 'Apr 2019' on cards, dossiers, and reports" — which only holds for epoch-style inputs, not for the ISO strings the same function accepts.

**Fix:** make the epoch path day-precise (`"May 1, 2019"`) so one instant ⇒ one string, and correct the docstring at `:43` (and the release-note text).

---

### B5 — LOW/MEDIUM — Three different timezone policies in one function; offsets are never normalised

| Path | Line | Zone used |
|---|---|---|
| epoch int/float | `:57`, `:67` | `fromtimestamp(value, datetime.UTC)` → **UTC** wall clock |
| ISO with offset | `:75` → `:100-102` | the **source offset's** wall clock, offset never applied |
| `strptime` fallback | `:82-84` | forced to **UTC** via `.replace(tzinfo=datetime.UTC)` |

Verified consequence — the same UTC instant class lands in different months depending on encoding:

```
human_date("2019-04-01T00:30:00+02:00") -> 'Apr 1, 2019'   # UTC instant = 2019-03-31 22:30Z
human_date("2019-04-01T00:30:00Z")      -> 'Apr 1, 2019'
```

Also note the awareness inconsistency: `fromisoformat` may return a **naive** datetime (`"2019-04-01T12:00:00"` → naive, verified), while the epoch path is aware and the `strptime` path is forced aware. Nothing compares them today, so it cannot raise — but it is a landmine for any future subtraction/comparison inside this module.

**Fix:** normalise once at the top (`dt = dt.astimezone(datetime.UTC)` when aware), pick one policy, document it.

---

### B6 — LOW — Millisecond / microsecond epoch values are silently dropped

`src/core/format.py:56`, `:66` — the guard admits only `31_536_000 … 4_102_444_800` **seconds** (1971-01-01 … 2100-01-01).

```
human_date(1557836800000)   -> None      # 2019-04-12 in ms
human_date("1557836800000") -> None      # same, stringified by the callers
```

JS `Date.now()`, PHP `time()*1000`, and several scraper stacks emit milliseconds; the user then sees the raw 13-digit number on the card. The docstring only promises "unix seconds" (`:46`), so this is contract-conformant but a real coverage gap.

**Fix:** detect magnitude before the range check — `>= 1e17` → ns, `>= 1e14` → µs, `>= 1e11` → ms — and scale to seconds.

Related coverage gaps, all verified `None` today (each is a plausible platform shape):

```
human_date("April 1, 2019")              -> None   # "%B %d, %Y" missing
human_date("Apr 1, 2019")                -> None   # "%b %d, %Y" missing
human_date("2019.04.01")                 -> None   # "%Y.%m.%d" missing
human_date("01-Apr-2019")                -> None   # "%d-%b-%Y" missing
human_date("Mon, 01 Apr 2019 00:00:00 +0000") -> None   # RFC 2822 — very common in mail/PH headers
human_date("Sat, 01 Apr 2019 00:00:00 GMT")   -> None
```

---

### B7 — LOW — `format_count`'s bool handling contradicts its own docstring

`src/core/format.py:30-34`

```python
"""… Bools are returned as-is ("True"/"False" would be a lie for a count); …"""
if isinstance(value, bool):
    return str(value)
```

The code returns literally `"True"` / `"False"` — exactly the value the docstring calls "a lie". The sentence is self-contradictory: "returned as-is" and "True/False would be a lie" cannot both hold when the return type is `str`.

```
format_count(True)  -> 'True'
format_count(False) -> 'False'
```

(Unreachable today — both call sites pass `int` — but it is the documented public behaviour and the doc is what the next integrator will read.)

**Fix:** return `""` / `"0"` / `"1"`, or reword the docstring to say "bools are stringified verbatim because '1'/'0' would misrepresent them".

---

### B8 — LOW — `format_count` silently drops thousands grouping for numeric strings

`src/core/format.py:39` — anything that is not `int`/`float` is `str()`'d verbatim.

```
format_count("5203") -> '5203'      # expected '5,203'
format_count("5,203") -> '5,203'
format_count(" 5203 ") -> ' 5203 '
```

The docstring says "ints/floats get grouping, non-numeric input passes through as-is" (`:4-5`), so it is technically conformant — but a digit string is numeric input that silently loses the one feature this function exists to provide. Cheap fix: attempt `int(text)` / `float(text)` for `str` inputs first.

---

### B9 — LOW — `format_count` float path rounds silently and prints non-numbers

`src/core/format.py:38`

```
format_count(5203.75)      -> '5,203.8'    # 0.75 rounded up; a "count" is never fractional
format_count(2.675)        -> '2.7'        # binary float, not '2.68'
format_count(0.05)         -> '0.1'
format_count(float("nan")) -> 'nan'
format_count(float("inf")) -> 'inf'
```

**Verified clean:** negative zero is safe (`format_count(-0.0)` → `'0'` — no `-0` output); very large ints group correctly (`format_count(10**30)` → `'1,000,000,000,000,000,000,000,000,000,000'`); negatives keep the sign (`-1234567` → `'-1,234,567'`).

**Locale:** there is **no** comma-vs-dot bug here. Python's `","` format spec is locale-independent (only the `n` spec consults `LC_NUMERIC`), so grouping is always ASCII `,` regardless of the OS locale. The only locale exposure is cosmetic: a German/French UI shows Western `5,203`.

---

### B10 — LOW — Leaked loop variable makes `month_precision` fragile and partly dead

`src/core/format.py:88` — `month_precision = fmt in ("%B %Y", "%b %Y", "%Y-%m")` is evaluated **after** the `for fmt in _DATE_FORMATS:` loop. Two problems:

- If no format matched, `fmt` still holds the last element (`"%Y-%m"`) and `month_precision` is computed as `True` — the value is then discarded by the `dt is None` guard at `:98-99`, so it is a **dead assignment on the failure path**.
- The value depends on a loop variable leaked out of the `for`. If `_DATE_FORMATS` were ever emptied, `fmt` would be unbound → `NameError` instead of a clean `None`.

**Fix:** assign `month_precision` inside the loop, right before `break` (`:85-86`).

---

### B11 — INFO — Redundant `Z` rewrite

`src/core/format.py:71-72` — `datetime.fromisoformat` has accepted a trailing `Z` since **Python 3.11**, and `pyproject.toml` sets `requires-python = ">=3.14"` (verified runtime: 3.14.7). The manual `Z` → `+00:00` substitution is therefore dead code that costs an extra string copy on every parse and suggests (incorrectly) that `Z` is unsupported.

---

### B12 — INFO — Ruff `DTZ007` is currently satisfied only by the chained `.replace(tzinfo=…)` shape

`src/core/format.py:80-87`. The repo selects the whole `DTZ` rule family. Ruff **does not** flag the current code, because the `strptime` result is immediately chained with `.replace(tzinfo=datetime.UTC)` (`:82-84`) — verified:

```
$ printf 'import datetime\nx = datetime.datetime.strptime("2019-04-01", "%%Y-%%m-%%d").replace(tzinfo=datetime.UTC)\n' | uv run ruff check --isolated --select DTZ --stdin-filename probe.py -
All checks passed!

$ printf 'import datetime\nx = datetime.datetime.strptime("2019-04-01", "%%Y-%%m-%%d")\n' | uv run ruff check --isolated --select DTZ --stdin-filename probe.py -
DTZ007 Naive datetime constructed using `datetime.datetime.strptime()` without %z
```

So the fix-up at `:82-84` is not merely stylistic — it is what keeps `DTZ007` green. Any refactor that splits the chain (`dt = strptime(...)` on one line, `.replace(...)` on the next) turns into a lint failure. Worth a one-line comment so the coupling is not broken by accident. Note the `%B`/`%b` patterns (`:18`, `:21`) are LC_TIME-sensitive while the output uses `calendar.month_abbr` (`:58`, `:68`, `:101-102`), which is English-only — consistent today because Python does not set `LC_TIME`, but the two would diverge if anything ever called `locale.setlocale(LC_TIME, …)`.

---

## 4) Improvements

1. **Replace hyphen-counting with a shape regex** (`src/core/format.py:92-96`) — one `re.fullmatch` per shape (`\d{4}`, `\d{4}-\d{2}`, `\d{8}`, `\d{4}-\d{2}-\d{2}`, …) fixes B1 and removes the need for the special-case early return at `:96`.
2. **Normalise the zone once** (`src/core/format.py:57`, `:75`, `:82-84`) — convert every aware result to UTC before extracting month/day, so the rendered date cannot depend on the source's offset (B5).
3. **One rendering rule per instant** — make the epoch path day-precise so `"2019-05-01"` and `1557836800` render identically, then fix the docstring at `:43` (B4).
4. **Accept ms/µs epochs** (`src/core/format.py:56`, `:66`) by magnitude detection, and decide a policy for pre-1970 negative epochs (currently `-1` → `None`).
5. **Widen `_DATE_FORMATS`** (`src/core/format.py:14-24`) with the shapes real platforms emit: `"%B %d, %Y"`, `"%b %d, %Y"`, `"%Y.%m.%d"`, `"%d-%m-%Y"`, `"%d-%b-%Y"`, plus RFC 2822 via `email.utils.parsedate_to_datetime` for mail/PH header dates.
6. **Harden the numeric guards** (`src/core/format.py:63-66`) with `isascii()`/`isdecimal()` and a `try/except ValueError` — the function must never raise (B2).
7. **Make `format_count` total** (`src/core/format.py:27-39`): normalise digit strings (B8), decide the bool policy (B7), and either drop the float branch or round explicitly with a documented rule (B9).
8. **Add tests** — `tests/` contains **zero** references to `human_date` / `format_count`, yet this is the one module whose correctness is defined by input-shape tolerance. Minimum matrix = the ~60 inputs exercised in this audit (ISO variants, offsets, `Z`, compact ISO, epoch s/ms, slash orders, long month names, `"0"`, `""`, `None`, `True`, `dict`/`list`, superscripts).
9. **Apply `format_count` where counts are rendered** — `src/services/report_service.py:295`, `:677`, `:705` print ungrouped counts, so cards and dossiers disagree today. Either route them through `format_count` or drop the "cards, headers, and reports agree" claim from the module docstring (`src/core/format.py:2-4`).
10. **Add `__all__ = ["format_count", "human_date"]`** (`src/core/format.py:9`) to make the public surface explicit, and consider populating the empty `src/core/__init__.py`.
11. **If sizes/durations are ever needed**, this is the natural home for `format_size`/`format_duration` — but note nothing in `src/` formats them today (`src/core/logger_handler.py:132`, `:139`, `src/services/cache_service.py:195` do raw arithmetic; `src/core/changelog.py:19` hardcodes "21MB smaller"), so the module's "single home" claim covers counts and dates only.

---

## 5) Verdict

**SOUND CORE, ROUGH EDGES — no release blocker, three reachable correctness bugs.**

The two functions do what their names promise for the shapes the app actually receives today, and all four call sites correctly handle the `None` return (`src/core/enrich_view.py:124-126`, `src/services/report_service.py:54-56`, `:84-86`, `src/components/profile_detail_dialog.py:804`). The module is stdlib-only, lint-clean, and free of hallucinated APIs.

Against that, the module's own stated contract is violated three times:

| # | Severity | Contract broken | Where |
|---|---|---|---|
| B1 | MEDIUM | "one stdlib date-parser" | compact ISO `20190401` → raw garbage (`:92-96`) |
| B2 | MEDIUM | "never crash a render" | `ValueError` on superscript digits (`:63-64`) |
| B3 | MEDIUM | "never render a wrong date on a guess" | `05/04/2019` → Apr 5 (day-first bias, `:19-20`) |
| B4 | LOW/MED | docstring example is wrong | `:43` says "Apr 2019", code returns "Apr 1, 2019" |
| B5 | LOW/MED | one rendering policy | 3 timezone policies (`:57`, `:75`, `:82-84`) |
| B6 | LOW | "platform formats" coverage | ms epochs and RFC 2822 dates → `None` |
| B7 | LOW | docstring vs code | bool → `"True"` (`:30-34`) |
| B8 | LOW | "single home for grouping" | `"5203"` → `"5203"` (`:39`) |
| B9 | LOW | float sanity | `nan`/`inf`/rounding (`:38`) |
| B10 | LOW | code hygiene | leaked loop var `fmt` (`:88`) |
| B11 | INFO | dead code | redundant `Z` rewrite (`:71-72`) |
| B12 | INFO | lint coupling | `DTZ007` stays green only because of the chained `.replace()` (`:82-84`) |

**Not blocking 2.3.0** — no current production input shape reaches B1–B3 (the live data path is ISO-with-offset strings, unix-second strings, or free text, all handled). **But fix B1, B2 and B3 before adding more platform extractors**, because every new extractor widens exactly the input distribution this module is supposed to absorb. B4 (docstring + `version.json` claim) and B9/B10 are cheap and should ride along.

**Also worth noting for the swarm:** the brief assumed this file holds duration and size formatting. It does not — and nothing else in `src/` does either. If a KB/MB or "2h 5m" helper is expected, it is still to be written; today the only user-facing size string is hand-typed prose at `src/core/changelog.py:19`.

**Verification note:** every behaviour quoted above was executed against the installed module on Python 3.14.7 via `uv run python`; `uv run ruff check src/` passes clean. No file was modified.
