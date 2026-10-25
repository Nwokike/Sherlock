# Dependency Audit: `ruff` (0.17.1) — Sherlock V3

> **Auditor:** dependency-audit subagent (Sherlock-V3 swarm, 2026-10-20)
> **Scope:** live lint state of `/home/maikel/.zcode/workspace/default/Sherlock-V3/`
> **Source of truth:** the installed `.venv` in the V3 tree (no external docs, no training-data assumptions)
> **Mutations:** none. No app file, `pyproject.toml`, or config was modified. All runs were read-only.

---

## 1) Installed Verification

Both invocation paths agree:

```console
$ .venv/Scripts/ruff.exe --version
ruff 0.17.1

$ .venv/Scripts/python.exe -m ruff --version
ruff 0.17.1
```

| Item | Value |
| :--- | :--- |
| Version | `0.17.1` (matches `pyproject.toml` dev pin `ruff>=0.17.1`) |
| Binary | `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Scripts/ruff.exe` (26,256,176 bytes) |
| Python wrapper | `python -m ruff` resolves to the same 0.17.1 binary — the two entry points are consistent |
| Config discovered | `pyproject.toml` (V3 root) — ruff found it and applied it (verified via `ruff config`, `--show-settings`) |
| Runtime baseline | `.python-version` = `3.14`; `requires-python = ">=3.14"` |

**Inferred target-version (important, see §4/R1).** Ruff is *already* operating at py314 even though
`[tool.ruff] target-version` is absent:

```console
$ .venv/Scripts/ruff.exe check --show-settings src/main.py | grep -i target
linter.unresolved_target_version    = 3.14
linter.per_file_target_version      = {}
formatter.unresolved_target_version = 3.14
formatter.per_file_target_version   = {}
analyze.target_version              = 3.14
```

Ruff derives `target-version` from `project.requires-python` (`>=3.14` → `py314`) when the setting is
not set explicitly. The `pyupgrade` (`UP`) rules are therefore already evaluating against the 3.14
grammar/target — **not** against an older default.

---

## 2) Live Lint Run (exact output)

### 2.1 `ruff check . --statistics` — the CI lint gate

```console
$ cd /home/maikel/.zcode/workspace/default/Sherlock-V3
$ .venv/Scripts/ruff.exe check . --statistics
All checks passed!
EXIT_CODE=0
```

**Result: clean. Zero violations across every rule code in the 21-prefix select set.**
Re-verified with `--no-cache` (identical, still `All checks passed!`, exit 0) to rule out a stale
`.ruff_cache` masking a real failure. There is no violation table to report.

### 2.2 `ruff format --check .` — the CI format gate

```console
$ .venv/Scripts/ruff.exe format --check .
39 files would be reformatted, 73 files already formatted
EXIT_CODE=1
```

**Result: FAILS (exit 1).** 39 of 112 files are not `ruff format`-clean: **21 Python files** and
**18 Markdown files**.

> **Snapshot note:** these counts are an as-of-audit snapshot. A concurrent sibling dependency-audit
> agent wrote `docs/SWARM-2026-10-20/deps/pytest-timeout.md` into the same directory *during* this
> audit; it is also unformatted, so a re-run now reports **40 files would be reformatted, 75 already
> formatted**. This report file itself is format-clean (`ruff format --check` → "1 file already
> formatted"), so it does not contribute to the failure count. The **21 Python** files listed below
> are stable and unaffected by the docs churn.

#### 2.2.1 The 21 Python files (would be reformatted)

Diff line count = `+`/`-` lines ruff would rewrite.

| Diff lines | File |
| ---: | :--- |
| 157 | `src/services/email_service.py` |
| 147 | `src/services/sherlock_service.py` |
| 121 | `src/services/user_scanner_compat.py` |
| 117 | `src/main.py` |
| 108 | `src/services/phone_service.py` |
| 71 | `src/screens/home_screen.py` |
| 46 | `src/app_shell.py` |
| 33 | `src/screens/results_screen.py` |
| 27 | `src/screens/settings_screen.py` |
| 21 | `tests/test_phone_mode_parity.py` |
| 16 | `src/services/storage_service.py` |
| 12 | `src/services/cache_service.py` |
| 7 | `tests/test_services_all_modes.py` |
| 7 | `tests/test_cross_scan.py` |
| 6 | `tests/test_imports.py` |
| 5 | `tests/test_services.py` |
| 5 | `tests/test_compat_loader.py` |
| 4 | `src/services/report_service.py` |
| 3 | `tests/test_storage_resilience.py` |
| 3 | `tests/test_sites_catalog.py` |
| 3 | `src/core/constants.py` |

63 Python files exist under `src/` + `tests/`; 42 are already clean, 21 are not.

Representative examples (verbatim `ruff format --diff` output):

```diff
--- src/core/constants.py
+++ src/core/constants.py
@@ -103,4 +103,3 @@
 # ── Email OSINT constants ─────────────────────────────────────────────
 # Validator names skipped by the "No Password Recovery" setting are
 # derived at scan time from user-scanner's loud-module list.
-
```

(trailing blank line) — the low-diff-count files are mostly trailing-newline/EOF whitespace. The
high-diff-count files (`email_service.py`, `sherlock_service.py`, `user_scanner_compat.py`,
`main.py`, `phone_service.py`) are real re-wrapping: ruff's Black-compatible line-breaking differs
from how those long call chains were hand-wrapped.

#### 2.2.2 The 18 Markdown files (would be reformatted)

Ruff 0.17.1 formats Python code blocks embedded in Markdown, and this is **not** preview-gated —
verified by running both modes and getting an identical result (18 files either way):

```console
$ .venv/Scripts/ruff.exe format --check --no-preview docs/
18 files would be reformatted, 31 files already formatted
$ .venv/Scripts/ruff.exe format --check docs/
18 files would be reformatted, 31 files already formatted
```

| Group | Files |
| :--- | :--- |
| `docs/reference/` (11) | `dep-cffi.md`, `dep-curl-cffi.md`, `dep-flet-ads.md`, `dep-httpx.md`, `dep-phonenumbers.md`, `dep-phonsint.md`, `dep-pycparser.md`, `dep-pytest-stack.md`, `dep-rich.md`, `dep-small-transitives.md`, `dep-user-scanner.md` |
| `docs/SWARM-2026-10-20/deps/` (7) | `httpx.md`, `phonenumbers.md`, `phonsint.md`, `pycparser.md`, `rich.md`, `socksio.md`, `user-scanner.md` |

Example (the failure is ruff re-wrapping a fenced Python snippet, e.g. normalising continuation
indent and collapsing hand-aligned trailing comments):

```diff
-     kwargs["timeout"] = global_timeout     # ← overwrites the app's explicit Timeout
+     kwargs["timeout"] = global_timeout  # ← overwrites the app's explicit Timeout
```

### 2.3 `# noqa` audit (RUF100 / dangling suppressions)

**Result: 0 stale or dangling `# noqa` directives.**

| Probe | Command | RUF100 count |
| :--- | :--- | ---: |
| Project config (authoritative) | `ruff check . --statistics` | 0 — "All checks passed!" |
| Cache-bypass | `ruff check . --no-cache --statistics` | 0 |
| Config preserved + RUF100 forced on | `ruff check . --extend-select RUF100 --statistics` | 0 |
| RUF100 + the rules it references | `ruff check . --select RUF100,F401,S324,S301,S105,DTZ005,DTZ007 --statistics` | 0 |
| **RUF100 in isolation** | `ruff check . --select RUF100 --statistics` | **7 (all false positives — see below)** |

The isolated run reports `7 RUF100 unused-noqa`. This is a **measurement artifact, not a defect**:
selecting only `RUF100` disables `F401`, `S324`, `S301`, `S105`, `DTZ005`, `DTZ007`, so every
`# noqa` that references one of them looks "unused" because the rule it suppresses is switched off.
As soon as the referenced rules are enabled (every probe above), all 7 directives are confirmed
**live** — each one suppresses a real diagnostic that would otherwise fire.

The complete set of 7 suppressions in the project, all justified:

| File:line | Directive | Suppresses | Justification |
| :--- | :--- | :--- | :--- |
| `src/screens/history_screen.py:50` | `# noqa: DTZ007` | naive `strptime` | deliberate naive-local parse; comment says so |
| `src/screens/history_screen.py:59` | `# noqa: DTZ005` | `datetime.now()` | deliberate naive-local arithmetic |
| `src/core/constants.py:48` | `# noqa: S105` | hardcoded-password false positive | storage **key name**, not a secret |
| `src/services/cache_service.py:187` | `# noqa: S301` | `pickle.loads` | intentional local-cache deserialization |
| `src/services/report_service.py:531` | `# noqa: S324` | `hashlib.md5` | Gravatar API mandates MD5 |
| `tests/test_imports.py:6` | `# noqa: F401` | unused import | deliberate import-smoke assertion |
| `tests/test_imports.py:10` | `# noqa: F401` | unused import | deliberate import-smoke assertion |

No `# noqa` should be removed, and no blanket `RUF100` cleanup is warranted. **Caveat for future
auditors:** do not run `ruff check --select RUF100` in isolation on this repo — it will report 7
phantom violations.

### 2.4 Repository/CI state observed

- **No `.github/` directory** — V3 has no CI workflow file of its own. The applicable gate is the
  owner standard from `docs/reference/dep-ruff.md` §5.3 item 4: `ruff check . --statistics` **and**
  `ruff format --check .`. Lint passes; **format fails**.
- **The repository has zero commits** (`git log` → `fatal: your current branch 'master' does not have
  any commits yet`; `git ls-files` → 0 tracked files). `src/`, `tests/`, and `docs/` are all
  untracked (`?? src/`, `?? tests/`, `?? docs/`). This matters for the `.md` findings: a CI checkout
  would not see `docs/` until it is committed, but a local `ruff format --check .` fails today.
- `docs/reference/dep-ruff.md` still points its "Installed Version / Binary / Package Location"
  header at **Sherlock-V2** paths (`Sherlock-V2\.venv\Scripts\ruff.exe`, `Sherlock-V2\.venv\Lib\site-packages\ruff`).
  The binary path in the live V3 tree is `Sherlock-V3\.venv\Scripts\ruff.exe`. The doc's §4 analysis
  of the *original* Sherlock config remains accurate and is the correct comparison baseline for §3.

---

## 3) Config Comparison vs. Owner Standard

Owner standard = `docs/reference/dep-ruff.md` §4.1 (verbatim original Sherlock `pyproject.toml:98-125`)
and §5.2 (the target config the standard prescribes for the V-family trees).

Live config = `Sherlock-V3/pyproject.toml:86-100`.

| Setting | Owner standard (§5.2 target) | Live V3 config | Match? |
| :--- | :--- | :--- | :--- |
| `[tool.ruff] target-version` | `"py314"` | **absent** | **MISSING** (but see below — no behavioural gap) |
| `lint.select` | 21 prefixes: `E F W UP B Q C4 PERF ERA I T20 DTZ RUF S TRY BLE EM A SIM RET RSE` | identical 21 prefixes, same order | **EXACT MATCH** |
| `lint.ignore` | `E501, EM101, EM102, EM103, TRY003, BLE001, S110, SIM105, TRY300, TRY301` | identical 10 codes, same grouping | **EXACT MATCH** (owner rationale comments stripped) |
| `lint.per-file-ignores["tests/**"]` | `["S101"]` | `["S101"]` | **EXACT MATCH** |
| `lint.per-file-ignores["src/services/scan_notify.py"]` | §5.3-3: add *only* if the file mirrors a foreign API's parameter name | `["A002"]` | **CORRECT AND LIVE** (verified below) |
| `[tool.ruff.format]` section | `quote-style="double"`, `indent-style="space"`, `line-ending="auto"` | **absent** | **MISSING** (all three are ruff defaults → no behavioural gap) |
| `lint.fixable` / `unfixable` / `extend-select` | not set | not set | MATCH |
| `lint.exclude` | not set | not set | MATCH (so `docs/` **is** in scope for both `check` and `format`) |

### 3.1 `target-version = "py314"` — missing but behaviourally neutral

`target-version` is absent from the live `pyproject.toml`, but ruff already resolves it to **3.14**
from `requires-python = ">=3.14"` (§1). Therefore:

- `UP` (pyupgrade) rules are **already** evaluated against py314 semantics — e.g. `UP007`
  (`Union` → `X | Y`), `UP006` (`List` → `list`), `UP045` (`Optional[X]` → `X | None`) all resolve as
  if `target-version = "py314"` were set. There is no hidden "old Python" degradation.
- The `ruff format` engine likewise runs at 3.14 (`formatter.unresolved_target_version = 3.14`).
- **No rule-code difference exists** between the live config and a config with the line added.

The gap is therefore **explicitness and drift-resistance**, not correctness. It matters because
`requires-python` is a *packaging* constraint that may legitimately be relaxed later (e.g. widening
install support to `>=3.12` for a wider device matrix). That single edit would silently downgrade
ruff's target to py312 and *re-enable* pyupgrade rules (and formatter target) that are currently
inert, producing a wave of new lint failures in `src/` — without anyone touching the ruff config.
Pinning `target-version = "py314"` decouples the lint target from the install floor.

### 3.2 The `A002` per-file-ignore is genuinely required (not stale config)

Owner §5.3-3 says the `scan_notify.py` ignore should exist only if the file mirrors a foreign API's
parameter name. In V3 it does, and the ignore is **load-bearing**. Proof — running the rule with the
per-file-ignore overridden away:

```console
$ .venv/Scripts/ruff.exe check src/services/scan_notify.py --select A002 --config "lint.per-file-ignores={}"
A002 Function argument `id` is shadowing a Python builtin
   --> src\services\scan_notify.py:152:28
    |
152 |     async def cancel(self, id: int) -> None:
    |                            ^^
153 |         self.cancelled.append(id)
    |
Found 1 error.
```

The file mirrors the `flet_notifications.show(id=...)` / `cancel(id=...)` signature at
`src/services/scan_notify.py:352` (`id=CHANNEL_PROGRESS`), `:365` (`id=CHANNEL_RESULT`), `:495` and
`:506` (`id=_ACTION_CANCEL` / `id=_ACTION_VIEW`), and `:537` (`NotificationAction(id=...)`).
**Keep this ignore.** Note also that a project-wide `--select A002` sweep is clean
(`ruff check src --select A002` → "All checks passed!"), so the ignore is correctly scoped to the
one file rather than suppressing the rule repo-wide.

### 3.3 `[tool.ruff.format]` section

The three settings the owner standard prescribes (`quote-style="double"`, `indent-style="space"`,
`line-ending="auto"`) are **ruff 0.17.1's defaults**, confirmed via `ruff config format` (default
`indent-style: space`, `quote-style: double`, `line-ending: auto`, `line-length: 88`). Adding them
changes no behaviour; it only pins the intent so a future ruff default change cannot silently
reformat the codebase. `line-length` is not pinned anywhere in the owner standard either — it stays
at the Black-compatible 88, which is what `E501`'s ignore already assumes.

### 3.4 The 21 Python files are not `ruff format`-clean — a real CI gap

The owner standard's prescribed CI runs **both** gates (§5.3-4). The lint gate passes; the format
gate fails with exit 1 across 21 tracked-intent Python files. This is the single most actionable
finding in this audit. The mismatch between "lint clean" and "format dirty" is expected: `E501` is
ignored (per the owner standard, §4.2-1) precisely *because* `ruff format` owns line length, but
the formatter has evidently never been run over the V3 tree.

---

## 4) Concrete Recommendations

Ordered by CI-blocking severity. None of these have been applied.

**R1 — Run `ruff format .` over `src/` and `tests/` (fixes the failing CI gate).**
`ruff format --check .` currently exits 1. The fix is a single command that rewrites the 21 Python
files (and, if `docs/` is in scope, the 18 Markdown files). The 3 top files — `email_service.py`,
`sherlock_service.py`, `user_scanner_compat.py` — account for 425 of the ~875 changed lines, so
expect a substantial but purely mechanical diff. Recommended sequence: (a) `ruff format src tests`
first, (b) re-run `ruff check . --statistics` to confirm the reformat introduced no new lint
violation (it should not — `ruff format` is lint-neutral, and `E501` is ignored), (c) re-run the
test suite, since the rewrite touches `phone_service.py` and `user_scanner_compat.py` behaviour-
adjacent call chains.

**R2 — Decide the fate of `docs/` before committing, and exclude it if the reports are meant to stay
as-is.** Ruff 0.17.1 formats Python fenced blocks inside Markdown, and this is on by default (not
preview-gated — §2.2.2). Two clean options:
  - **(a) Format the docs too:** `ruff format docs/` — the audit reports' code snippets get
    canonicalised. This keeps `ruff format --check .` green with no config change.
  - **(b) Exclude `docs/` from ruff entirely:** add `exclude = ["docs"]` under `[tool.ruff]`. This
    also stops `ruff check .` from ever analysing code blocks inside Markdown, which is desirable
    because report snippets are illustrative, not compilable.
  Option (b) is the better fit for a `docs/` tree that is entirely prose + illustrative snippets,
  and it removes a recurring tripwire for every future audit report. Whichever is chosen, the
  decision belongs in `pyproject.toml` so it is explicit rather than accidental.

**R3 — Add the explicit `target-version = "py314"` to `pyproject.toml` (recommended, but not urgent).**
Ruff already infers 3.14 from `requires-python`, so this is a **no-op today** — no lint or format
behaviour changes, and no new violations will appear. It is still recommended because it decouples
the lint target from the packaging floor: if `requires-python` is ever relaxed to widen device
support, an unpinned target silently rewrites the meaning of the whole `UP` rule set and the
formatter's target. Suggested placement (top-level `[tool.ruff]` table, above `[tool.ruff.lint]`):

```toml
[tool.ruff]
target-version = "py314"
```

**R4 — Add the `[tool.ruff.format]` block from the owner standard (§5.2).** All three values are
ruff defaults, so this is likewise a no-op today, but it pins the formatting contract so a future
ruff default change cannot silently reformat 63 Python files:

```toml
[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "auto"
```

**R5 — Restore the owner-rationale comments in the `lint.ignore` list.** The live `ignore` list has
the identical code set to the original Sherlock, but the explanatory comments from
`docs/reference/dep-ruff.md` §4.1 were stripped. Those comments are the *only* in-repo record of why
`BLE001`/`S110`/`SIM105`/`TRY300`/`TRY301` are tolerated, and they are the guardrail against a
future contributor "tidying" the list back on. Re-pasting them costs nothing and preserves the
owner standard verbatim.

**R6 — Add the two-gate CI workflow.** V3 has no `.github/` directory, so neither `ruff check` nor
`ruff format --check` runs automatically. Per `docs/reference/dep-ruff.md` §5.3-4, the workflow
should be:

```yaml
      - name: Lint (ruff)
        run: uv run ruff check . --statistics
      - name: Format check (ruff)
        run: ruff format --check .
```

Note that `ruff format --check .` must be added as a **separate** step — the original Sherlock
CI (`Sherlock/.github/workflows/build-all.yml:110-111`, quoted in `dep-ruff.md` §4.4) only ran the
lint gate, which is exactly why the format drift went unnoticed.

**R7 — Do not "fix" the 7 `# noqa` directives.** They are all live and justified (§2.3). Removing
them would surface 7 real diagnostics (`DTZ007`, `DTZ005`, `S105`, `S301`, `S324`, 2× `F401`).
Also do not add a blanket `# ruff: noqa` or a repo-wide `RUF100` ignore — RUF100 is already
correctly configured and reports 0 under the project config.

**R8 — Fix the stale path header in `docs/reference/dep-ruff.md`.** Lines 5-7 point at
`Sherlock-V2\.venv\...` for the binary, package location, and dist-info path, and line 8 points at
`Sherlock-V2\pyproject.toml:24`. In the V3 tree the real paths are
`Sherlock-V3\.venv\Scripts\ruff.exe` and `Sherlock-V3\.venv\Lib\site-packages\ruff-0.17.1.dist-info`.
The §4 analysis of the original Sherlock config is still accurate and remains the right baseline.

**R9 — Gate the tree before the first commit.** The repo has zero commits and every file
(`src/`, `tests/`, `docs/`) is untracked. Running `ruff check . --statistics` and
`ruff format --check .` once, then committing the result, is cheaper than reformatting a populated
history later. Applying R1 (format) *before* the initial commit also keeps the first commit
diff-free of mechanical churn.

---

## 5) Verdict

### **ISSUES FOUND**

**Lint: PERFECT.** `ruff check . --statistics` → `All checks passed!`, exit 0, zero violations across
the full 21-prefix select set, confirmed with `--no-cache`. The `select` and `ignore` sets match the
owner standard in `docs/reference/dep-ruff.md` §4.1 **exactly** (same 21 prefixes, same 10 ignored
codes, same `tests/**` = `S101` per-file-ignore). The `src/services/scan_notify.py` = `A002`
per-file-ignore is **not** dead config — it is required and verified load-bearing (the rule fires at
`scan_notify.py:152` when the ignore is removed).

**Format: FAILING.** `ruff format --check .` → exit 1, **39 files would be reformatted**
(21 Python + 18 Markdown), 73 already formatted (40/75 as of the final re-check, because a
concurrent sibling agent added one more unformatted Markdown report — see the snapshot note in
§2.2). Under the owner standard's CI contract
(`ruff check . --statistics` **and** `ruff format --check .`), V3 currently **fails the quality
gate** on the format half. This is the one issue that must be fixed.

**Noqa hygiene: PERFECT.** 0 dangling/stale `# noqa` directives (RUF100 = 0 under the project
config). The 7 suppressions are all live and justified. The 7 hits from an isolated
`--select RUF100` run are a known false-positive mode of that probe and are *not* defects.

**Config completeness: two omissions, both behaviourally neutral today.** `target-version = "py314"`
and the `[tool.ruff.format]` block are absent, but ruff already resolves 3.14 from
`requires-python = ">=3.14"` and the three format values are ruff defaults. R3 and R4 are
recommended as drift insurance (they will not change any current lint or format outcome), not as
bug fixes.

**Action required, in order:** R1 (format `src` + `tests`) → R2 (decide `docs/` handling) →
R6 (add the CI workflow) → R3/R4 (pin target-version and format block) → R5/R8 (restore owner
comments, fix the doc's stale paths) → R9 (commit on a green tree).
