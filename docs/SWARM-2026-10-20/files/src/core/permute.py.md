# Audit — `src/core/permute.py` (51 lines)

Audited: 2026-10-22 · Truth source: `user-scanner 1.5.2.3` (`.venv/Lib/site-packages/user_scanner`) · Read-only, no files modified.

---

## 1) File role

`src/core/permute.py` is a **pure-string helper** with exactly one public function:

```python
def permute_username(name: str) -> list[str]:   # src/core/permute.py:24
```

It takes one handle and returns up to `MAX_VARIANTS = 5` (`src/core/permute.py:15`) **separator-swapped** variants of it (`john.doe` → `john_doe`, `john-doe`, `johndoe`). It does **not** generate case variants, digit/appended variants, or any combinatorial pattern.

### Consumer census (complete)

| Consumer | Location | Notes |
|---|---|---|
| Only importer | `src/main.py:991` (`from core.permute import permute_username`) | lazy import inside the scan function |
| Call site | `src/main.py:993-995` | `scan_query = ",".join([target_clean, *variants])` |
| Result handoff | `src/main.py:1003-1004` → `src/services/sherlock_service.py:130` `search()` | engine re-splits on `,` via `parse_usernames` (`src/services/sherlock_service.py:59-73`) |
| Toggle UI | `src/screens/settings_screen.py:788-800` ("Username Permutations" switch, Scan Parameters) | handler `_toggle_permute` at `:575-577` |
| Persistence | `src/core/constants.py:58` `STORAGE_PERMUTE` → restored at `src/main.py:780-782` → flag `src/core/state.py:124` | default `False` |
| **home_screen chips** | **none** | `src/screens/home_screen.py:801-950` builds the username-mode chip row (Scope / Timeout / Load from file / Loud / Validate proxy / Hudson / Recursive / Cross-Scan / Adult / Disabled Sites) — **no permutation chip, no pattern chip** |
| Unit tests | **none** | `grep -rln "permute" tests/` → empty. A 51-line pure function with zero tests (also flagged in `docs/SWARM-2026-10-20/deps/pytest.md:390`). |

**Surface vs. promise.** `version.json:6` (2.3 release notes) says *"One toggle scans separator variants: john.doe → john_doe, john-doe, johndoe"*, and the settings subtitle (`src/screens/settings_screen.py:794`) repeats it. That promise is **only** reachable from Settings → Scan Parameters; the discovery surface of `src/screens/home_screen.py` never mentions it. The advertised example also only holds for `.`-containing input — see **C4**.

---

## 2) Correctness audit

### C1 — [HIGH] `MAX_VARIANTS = 5` silently drops the *most valuable* variant

`src/core/permute.py:15`, `src/core/permute.py:48-49`. The cap returns the first 5 candidates in emission order, and emission order is **not** "best first" — it is "first separator source wins" (see C2/C4). Uncapped truth vs. capped result (computed against the exact algorithm, then confirmed by running the shipped function):

| Input | Full candidate set (6) | Shipped output (5) | Silently dropped |
|---|---|---|---|
| `john._doe` | `john.-doe, john..doe, john.doe, john__doe, john-_doe, john_doe` | first 5 | **`john_doe`** — the fully-unified form |
| `john_doe.` | `john-doe., john.doe., johndoe., john_doe_, john_doe-, john_doe` | first 5 | **`john_doe`** |
| `john.doe_smith` | `… , john_doe_smith, john-doe_smith, johndoe_smith` | first 5 | **`johndoe_smith`** |

The dropped candidate is in every case the *normalised* handle — i.e. the single most likely real account. `src/main.py:996-999` logs only `"Permute: +N handle variant(s) joined the scan"`, and the UI never shows the list, so **the user cannot tell that variants were discarded**. There is no "capped" signal anywhere.

### C2 — [HIGH] Only ONE separator *type* is normalised per variant → hybrid-heavy output

`src/core/permute.py:38-44`. The outer loop iterates over separator *characters* and the inner loop replaces **all occurrences of that one character**. A handle containing two different separators therefore yields mostly hybrids that keep the second separator intact:

```
permute_username("john.doe_smith") -> ['john.doe-smith', 'john.doe.smith', 'john.doesmith',
                                       'john_doe_smith', 'john-doe_smith']
```

`john.doe-smith` (only `_` swapped) is ranked **above** `john_doe_smith` (both unified) and above `john.doe.smith`. The feature's quality is inversely proportional to how interesting the input is.

### C3 — [MED] A doubled separator never yields the single-separator form

`src/core/permute.py:40`. `replace` is global per separator *type*, so collapse-to-one is never enumerated:

```
permute_username("john..doe") -> ['john__doe', 'john--doe', 'johndoe']   # "john.doe" unreachable
permute_username("john__doe") -> ['john-doe', 'john.doe', 'johndoe']     # "john_doe" unreachable
```

### C4 — [MED] Output order depends on which separator the input happens to use

`src/core/permute.py:20-21`, `src/core/permute.py:38-44`. The target order is fixed `("_", "-", ".", "")` but the target equal to the *source* is skipped (`src/core/permute.py:42-43`), which shifts the emitted sequence:

```
"john.doe" -> ['john_doe',  'john-doe',  'johndoe']
"john_doe" -> ['john-doe',  'john.doe',  'johndoe']
"john-doe" -> ['john_doe',  'john.doe',  'johndoe']
```

The documented order in `version.json:6` and `src/screens/settings_screen.py:794` (`john_doe, john-doe, johndoe`) therefore holds **only** for `.`-containing input. The docstring (`src/core/permute.py:25-29`) promises no ordering at all, so there is no contract.

### C5 — [MED] Silent no-op for separator-free handles

`src/core/permute.py:38-39` (the `if sep in base` guard). `permute_username("johndoe") -> []`. That is correct behaviour, but `src/main.py:994` (`if variants:`) logs **nothing** in the empty case and the settings copy gives no hint, so the user toggles the feature and sees zero change with no explanation. Most handles are separator-free.

### C6 — [MED] ASCII-only: any non-ASCII character kills the whole handle

`src/core/permute.py:17`, `src/core/permute.py:32`. `[A-Za-z0-9_.\-]+` is ASCII-only:

```
permute_username("josé")    -> []
permute_username("joão.doe")-> []
```

One accented character rejects the entire handle, even though the permutation only ever touches ASCII separators. This is *consistent* with the Home gate (`src/screens/home_screen.py:608`), so the whole username mode is ASCII-only — but the module docstring (`src/core/permute.py:1-7`) sells "broader OSINT sweeps" and never mentions the ASCII ceiling. International handles are precisely the population that benefits from separator sweeps.

### C7 — [LOW] Whitespace rule diverges from the Home gate (cross-file)

The Home gate validates the **collapsed** string: `src/screens/home_screen.py:606-608` does `re.sub(r"\s+", "", query)` before `re.fullmatch(r"[A-Za-z0-9_.\-]+", collapsed)`. `src/core/permute.py:32` validates the **raw** string (only `.strip()` at `:31`). `src/main.py:892` passes `username.strip()` — never collapsed. Result: `"john doe"` passes the gate (collapsed to `johndoe`), reaches `permute_username`, and returns `[]` (internal space fails the shape). The engine then splits it anyway: `src/services/sherlock_service.py:60` splits on whitespace when there is no comma → two bogus targets `john` and `doe`. The comma-join only saves this path when variants exist.

### C8 — [LOW] Non-`str` input raises `AttributeError`

`src/core/permute.py:31`. `(name or "")` covers `None` and `""` but not other types: `permute_username(["a"])` → `AttributeError: 'list' object has no attribute 'strip'`. Not reachable from `src/main.py:993` (always a `str`), but it is an unguarded public API.

### C9 — [LOW] The second shape check is near-dead code

`src/core/permute.py:45` — `_SHAPE_RE.fullmatch(candidate)`. The candidate is built from shape-valid characters plus one of `_ - .` or `""`, so the check can **only** ever fail for the empty string (the one case where every source separator is removed):

```
permute_username("___") -> ['---', '...']     # the "" candidate was correctly rejected here
```

So it is not fully dead — it is a single-purpose empty-string guard wearing the costume of a general validator. It is also the only thing preventing `""` from reaching `src/main.py:995`'s comma-join (which would produce a stray empty target).

### C10 — [INFO] Case handling: the `lower()` dedup is a no-op today, and the docstring over-promises

`src/core/permute.py:1` advertises *"separator/case variants"*; the function only ever produces separator variants, and `src/core/permute.py:27-28` explains why case variants are deliberately skipped. The case-insensitive dedup at `src/core/permute.py:35` and `src/core/permute.py:45-46` (`.lower()`) is therefore equivalent to exact dedup today, because case is never mutated — it only becomes meaningful if case variants are ever added. Meanwhile the engine's own dedup is **case-sensitive** (`src/services/sherlock_service.py:66-73`, exact `seen` set), so the extra strictness is not required for correctness at the engine level. The docstring/behaviour mismatch should be fixed by editing `src/core/permute.py:1` to say "separator variants".

### C11 — [INFO] The 64-char cap duplicates the Home gate

`src/core/permute.py:32` (`len(base) > 64`) vs `src/screens/home_screen.py:606-607` (`len(collapsed) > 64`). Two hand-maintained copies of the same rule, with different inputs (raw vs. collapsed). Same for the character class: `src/core/permute.py:17` vs `src/screens/home_screen.py:608` — identical text, no shared constant.

### C12 — [INFO] The comma-join is safe

`src/main.py:995` joins with `","`; the shape rule excludes `,` from every variant, so a variant can never corrupt the join. `parse_usernames` (`src/services/sherlock_service.py:59-73`) also strips and de-duplicates, so the primary target is not scanned twice.

### C13 — [INFO] Purity / idempotence — OK

The function is pure (no I/O, no globals mutated, deterministic). Re-running it on one of its own outputs returns the same set minus the input, so no duplicated engine work (the engine dedupes anyway).

### C14 — [INFO] Cap size is 20× smaller than the engine's own budget

`MAX_VARIANTS = 5` (`src/core/permute.py:15`) vs upstream `MAX_PERMUTATIONS_LIMIT = 100` (`user_scanner/__main__.py:62`, used at `user_scanner/__main__.py:506` via `islice`).

---

## 3) Upstream `patterns.py` comparison

Installed at `.venv/Lib/site-packages/user_scanner/core/patterns.py` (6359 bytes, 237 lines). Real public surface, verbatim:

```python
# .venv/Lib/site-packages/user_scanner/core/patterns.py:178
def expand_patterns(input: str) -> Iterator[str]:
    """Expand a pattern string into all matching combinations.

    Syntax:
        [chars]      — character set, e.g. [a-z], [0-9], [abc]
        [chars]{len} — with length control, e.g. [a-z]{0-2}, [0-9]{1;3}
        \\[ \\] \\\\   — escaped literal brackets and backslash

    Examples:
        "john[a-c]"       → "johna", "johnb", "johnc"
        "john[0-9]{0-2}"  → "john", "john0", ..., "john99"
        "hello\\[world\\]" → "hello[world]"
    """
    blocks = _parse_patterns(input)
    yield from _iter_pattern(blocks)

# .venv/Lib/site-packages/user_scanner/core/patterns.py:195
def expand_patterns_random(input: str, capacity: int = 1000) -> Iterator[str]:
    """Expand a pattern string in randomized order using reservoir sampling.
    ...
    """

# .venv/Lib/site-packages/user_scanner/core/patterns.py:225
def count_patterns(input: str) -> int:
    """Return the total number of expansions for a pattern without generating them.

    Useful for showing the user how many permutations a pattern produces
    before actually expanding it (e.g. "Scanning 100 of 18,279 permutations").
    Runs in O(number of blocks) — instant even for huge patterns.
    """
```

Supporting internals: `PatternBlock` (`:7-10`), `Lexer` (`:16-40`), `_parse_charset` (`:47-78`), `_parse_lenset` (`:81-111`), `_parse_patterns` (`:123-153`), `_iter_block` (`:156-159`), `_iter_pattern` (`:162-175`).

### Verified upstream behaviour (run against the installed 1.5.2.3)

```
expand_patterns("john.doe")               -> ['john.doe']            count = 1
expand_patterns("john[0-9]{1-3}")          -> ['john0', ..., 'john99', 'john00', ...]  count = 1110
expand_patterns("john[a-c]{0-2}")          -> 13 items               count = 13
expand_patterns("john[\\-_.]{0-1}doe")     -> ['johndoe','john-doe','john.doe','john_doe']  count = 4
expand_patterns("john[._-]{0-1}doe")       -> ValueError: Missing "]" at the end of pattern
count_patterns("[a-z]{8}")                 -> 208827064576
count_patterns("x[0-9]{1-12}")             -> 1111111111110
```

### The decisive comparisons

**(a) The local feature is a strict subset of upstream — and upstream expresses it *better*.**
`"john[\-_.]{0-1}doe"` yields exactly the local feature's three variants **plus** the original, in one call, with no hand-rolled swap loop. And the two-separator case that C2/C3 get wrong is trivially correct upstream:

```
expand_patterns('john[\-_.]{0-1}doe[\-_.]{0-1}smith')
  count = 16
  -> ['john-doe-smith', 'john-doe.smith', 'john-doe_smith', 'john-doesmith',
      'john.doe-smith', 'john.doe.smith', 'john.doe_smith', 'john.doesmith',
      'john_doe-smith', 'john_doe.smith', 'john_doe_smith', 'john_doesmith',
      'johndoe-smith', 'johndoe.smith', 'johndoe_smith', 'johndoesmith']
```

Every fully-unified form is present, the ordering is deterministic and charset-sorted (not input-dependent), and there is no arbitrary cap. C1–C4 all disappear.

**(b) Upstream is far richer than anything the app exposes.** `john[0-9]{1-3}` → 1110 permutations; `count_patterns` returns that number in O(blocks) without materialising anything. The app has **no** path to any of this: `grep -rn "expand_patterns\|count_patterns" src/` returns **nothing** — upstream's pattern engine is completely unused by the GUI.

**(c) The upstream CLI already treats the target as a pattern.** `user_scanner/__main__.py:503-511`:

```python
targets = []
for target_name in targets_found:
    username_targets = list(islice(expand_patterns_random(target_name), args.stop))
    ...
    total = count_patterns(target_name)
    if total > len(username_targets):
        print(C + f"[+] Scanning {len(username_targets)} of {total} permutations" + ...)
```

`user-scanner john.doe` and `user-scanner "john[0-9]{1-3}"` are the *same* code path. The GUI has only the first of those, hand-rolled.

**(d) Two wiring traps that MUST be handled.**

- **`capacity` is NOT an output limit.** `expand_patterns_random(pattern, capacity=5)` yields the **entire** set — measured: `list(expand_patterns_random('john[0-9]{1-3}', capacity=5))` returns **1110** items, not 5. The parameter is the reservoir *size* (`patterns.py:203-222`): the generator keeps `capacity` items in the reservoir, then yields every remaining item as it cycles them through the reservoir. The limit must be applied by the **caller** with `itertools.islice`, exactly as upstream does at `user_scanner/__main__.py:506`.
- **There is no safety ceiling.** `expand_patterns_random` consumes the *whole* pattern space, so `[a-z]{8}` (208 827 064 576) would hang the app. The app must call `count_patterns()` **first** and refuse to expand anything above its own ceiling. The local `MAX_VARIANTS = 5` (`src/core/permute.py:15`) is an accidental safety property that upstream does not provide — it must be re-implemented explicitly.
- **Syntax gotcha:** a literal `-` inside a charset is parsed as a range end (`patterns.py:62-72`), so `"john[._-]{0-1}doe"` raises `ValueError`. It must be escaped (`"john[\-_.]{0-1}doe"`, handled at `patterns.py:56-60`) or the UI will throw on ordinary user input.

**(e) Consumer-side matching already exists.** The engine already consumes comma-separated multi-target queries: `src/services/sherlock_service.py:59-73` (`parse_usernames`) → `:140-143` sets `app_state.search_targets` and loops each target with its own `SearchProgress` (`:167-180`). `src/main.py:986-999` already joins variants with `","`. So a pattern-expanded target list is a **one-line drop-in** at the join site — no new plumbing, no new dependency (user-scanner is already a direct dependency).

---

## 4) Recommendation — **both, but inverted**

**Do not delete the local feature, and do not keep it as-is.** Keep the *convenience* (the user types `john.doe`, gets separator variants without learning pattern syntax) and *replace its implementation* with upstream's engine; then add upstream's *capability* (an explicit pattern field) on the same code path.

Rationale: pure-upstream would delete a genuinely useful zero-syntax behaviour, while pure-local caps the app at 5 hand-rolled variants and permanently forgoes `john[0-9]{1-3}`. The two features share one implementation and one UI surface.

### Concrete wiring sketch (exact file:line)

1. **`src/core/permute.py` — reimplement on top of upstream (keeps the public API, `src/main.py:991` keeps working).**
   - Replace the hand-rolled swap loop (`src/core/permute.py:38-49`) with: scan `base` for separator positions → build an upstream pattern `prefix + r"[\-_.]{0-1}" + suffix` per separator → `expand_patterns(pattern)` → de-duplicate → cap. Fixes C1–C4 and the ordering inconsistency.
   - Add `expand_user_pattern(pattern: str, limit: int) -> tuple[list[str], int]`: call `count_patterns(pattern)` **first**; refuse if `> limit` ceiling; then `list(itertools.islice(expand_patterns_random(pattern), limit))`. Return `(targets, total)` so the caller can render the banner.
   - Delete `_SOURCE_SEPARATORS` / `_SEPARATORS` (`src/core/permute.py:20-21`) and the `_SHAPE_RE` duplicate (`src/core/permute.py:17`) — or keep `_SHAPE_RE` only as a *pattern-mode* gate that also admits `[ ] { } \ -` characters.
   - Raise `MAX_VARIANTS` (`src/core/permute.py:15`) to match the engine budget (upstream `MAX_PERMUTATIONS_LIMIT = 100`, `user_scanner/__main__.py:62`), or drive it from the new limit setting.

2. **`src/main.py:986-999` — single expansion point.** Replace the `permute_username` call with the new adapter; accept either an explicit pattern or the auto-derived separator pattern; keep the `",".join(...)` (safe per C12). Keep the log at `src/main.py:996-999` but add the total: `"Permute: +N of M handle variants"`.

3. **`src/main.py:890-899` — pattern detection.** Decide "is this a pattern?" before the shape gate (see 5). `target_clean = username.strip()` (`:892`) must be passed through unchanged (patterns contain no spaces).

4. **`src/main.py:780-782` + `src/core/state.py:124` + `src/core/constants.py:58`** — add `permute_limit: int = 100` (mirror of `STORAGE_PERMUTE`, e.g. `STORAGE_PERMUTE_LIMIT`) and restore it alongside the existing flag.

5. **`src/screens/home_screen.py:601-610` — the blocking change.** `_check_username_shape` hard-rejects `[ ] { }` because it reuses `[A-Za-z0-9_.\-]+`. A pattern like `john[0-9]{1-3}` can therefore **never be submitted**. The gate must branch: plain handle → existing rule; pattern mode → a pattern-aware rule (allow `[ ] { } -` and escape `\`).

6. **`src/screens/home_screen.py:801-950` — add the chip.** The username-mode chip row has no permutation/pattern entry, so the 2.3 release note's headline feature is undiscoverable. Add a "Pattern" / "Permutations: ON|OFF" chip next to `Recursive` (`:920-927`) / `Cross-Scan` (`:928-935`).

7. **`src/screens/settings_screen.py:788-800`** — update the copy ("Also scan separator variants…") to mention pattern support, and add a **limit stepper** (default 100 = `MAX_PERMUTATIONS_LIMIT`). The upstream banner text lives at `user_scanner/__main__.py:514-525`; mirror it as *"Scanning 100 of 1,110 permutations"* using `count_patterns`.

8. **`tests/`** — add `tests/test_permute.py`. Zero tests currently cover this module (`grep -rln permute tests/` → empty) despite it being a pure function.

### What NOT to do

- **Do not** call `expand_patterns_random(pattern, capacity=N)` expecting N outputs — it yields the whole set (measured: 1110 for a 5-capacity reservoir). Use `islice`.
- **Do not** expand a pattern without checking `count_patterns()` first — `[a-z]{8}` is 208 billion items and `expand_patterns_random` would consume all of them.
- **Do not** feed a raw user pattern to `expand_patterns` without try/except: `patterns.py:54`, `:59`, `:70`, `:87`, `:90`, `:93`, `:148` all raise `ValueError` on malformed input (e.g. `"john[._-]{0-1}doe"`). The UI must catch it and show a message.

---

## 5) Verdict

**Conditionally keep — rewrite, do not delete.**

- The file is **functionally correct** for its stated narrow job: no crashes on the app's real inputs, no duplicate scans, no comma-join corruption, correct handling of `None`/empty/whitespace/over-long handles, and the shape check at `src/core/permute.py:45` does its one real job (rejecting the empty candidate).
- It is nevertheless **strictly dominated by the dependency the app already ships**. The entire feature is one upstream call away (`expand_patterns("john[\-_.]{0-1}doe")` reproduces it exactly), and upstream additionally delivers the combinatorial syntax (`john[0-9]{1-3}` → 1110 variants), an O(blocks) pre-count (`count_patterns`), deterministic ordering, and randomised sampling — **none of which the app can do today**, and none of which the app exposes anywhere (`grep expand_patterns src/` → no hits).
- **The 2.3 release-note claim is narrower than the engine's capability.** "One toggle scans separator variants" describes a 5-variant, separator-only feature that upstream renders as a special case of a far more general system. The app is currently *less* capable than the `user-scanner` CLI it wraps, and this file is the reason.
- **Highest-value fixes, in order:** (1) replace the swap loop with upstream expansion — fixes C1–C4 at once; (2) raise/expose the cap and report "N of M"; (3) add the pattern field + `count_patterns` banner; (4) make the feature discoverable from `src/screens/home_screen.py:801-950`; (5) add `tests/test_permute.py`.

**Blocking dependency:** `src/screens/home_screen.py:608` must be taught pattern syntax before any upstream pattern can be entered — without that, the upstream engine stays unreachable from the GUI no matter how the backend is wired.
