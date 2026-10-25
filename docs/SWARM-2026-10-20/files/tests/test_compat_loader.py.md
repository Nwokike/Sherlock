# Audit report: tests/test_compat_loader.py + tests/test_sites_catalog.py

**Audited as one unit.** `tests/test_compat_loader.py` (51 lines) and `tests/test_sites_catalog.py` (39 lines).
Repo layout note: sources live under `src/` (not top-level `services/`/`core/`), and `tests/conftest.py` inserts `src/` onto `sys.path`, so the `services.*` / `core.*` imports in both files resolve to `src/services/…` and `src/core/…`.
Key supporting files read: `src/services/user_scanner_compat.py`, `src/services/phone_service.py`, `src/services/sherlock_service.py`, `src/core/constants.py`, `src/core/state.py`.

---

## 1) Files' roles

**`tests/test_compat_loader.py`** — "Tolerant module loader + compat driver shape tests."
- Exercises the public loader wrappers (`load_user_modules`, `load_email_modules`, `load_phone_modules`) on `services/user_scanner_compat.py`.
- Exercises the private tolerant loader `_load_modules_tolerant` directly with a synthetic broken/good module tree.
- Smoke-tests the three async scan drivers (`run_username_scan`, `run_email_scan`, `run_cross_scan_async`) are callable.
- Smoke-tests `PhoneService.cancel()` returns `None` after setting `PhoneService._thread_cancel`.

**`tests/test_sites_catalog.py`** — "Mode-aware module catalog tests (username / email / phone switching)."
- `SherlockService().load_sites(mode=MODE_USERNAME)` then checks `state.sites_total`, `state.sites_cache`, `state.sites_tag_index`.
- `PhoneService().load_sites()` then checks `len(state.sites_cache) == 5`.
- `EmailService().load_sites(mode=MODE_EMAIL)` then checks `100 < state.sites_total < 500`.
- Two trivial state-default checks: `MODE_PHONE == "phone"` and `state.selected_sites == []`.

Both files assert against the **app's service facades** (`SherlockService`, `EmailService`, `PhoneService`) and the **compat loader wrappers**, not against upstream user-scanner/phonsint directly — with one notable exception (see §3).

---

## 2) What is actually asserted (key assertions, with file:line)

### test_compat_loader.py

| Test (line) | Assertion(s) |
|---|---|
| `test_load_user_modules_returns_pairs` (8) | `len(mods) > 2000`; `mods[0]` is `(cat: str, mod)` where `mod` has `__name__` (9–13) |
| `test_load_email_modules_returns_pairs` (16) | `len(mods) > 100` (18) |
| `test_load_phone_modules_five_modules` (21) | `len(mods) == 5` (23); `{c.lower() for c,_ in mods} == {"auth","crm","shopping","social"}` (24–25) |
| `test_tolerant_loader_skips_broken_file` (28) | `_load_modules_tolerant(bad_tree)` returns exactly 1 module (boom.py skipped, fine.py kept) (36–37); `_load_modules_tolerant(good_tree)` is truthy (38) |
| `test_drivers_are_coroutines` (41) | `run_username_scan`, `run_email_scan`, `run_cross_scan_async` are all `callable` (43) |
| `test_cancel_event_stops_driver` (46) | `PhoneService().cancel()` returns `None` after `svc._thread_cancel.set()` (49–51) |

### test_sites_catalog.py

| Test (line) | Assertion(s) |
|---|---|
| `test_load_catalog_username` (13) | `total == state.sites_total` (15); `state.sites_cache` truthy (16); `state.sites_tag_index` truthy (17) |
| `test_load_catalog_phone_swaps_names` (20) | `len({n.lower() for n in state.sites_cache}) == 5` (24) |
| `test_load_catalog_email` (27) | `100 < state.sites_total < 500` (29) |
| `test_state_has_phone_mode_constant` (32) | `MODE_PHONE == "phone"` (34–35) |
| `test_selected_sites_default_empty` (38) | `state.selected_sites == []` (39) |

---

## 3) Tautology / contract analysis

### 3.1 Real contracts (good)
- **`test_tolerant_loader_skips_broken_file`** (test_compat_loader.py:28–38) is the strongest test in the unit: it genuinely verifies the tolerant-loader contract — a raising module is skipped while a valid module in the same directory is still imported. This is the only test that exercises failure handling.
- **`test_load_user_modules_*` / `test_load_email_modules_*` / `test_load_phone_modules_*`** (test_compat_loader.py:8–25) exercise the **public app wrappers** (`load_user_modules`, `load_email_modules`, `load_phone_modules`), not upstream internals. This matches the design intent that `user_scanner_compat` is the single upstream-touching module.
- **`test_drivers_are_coroutines`** (test_compat_loader.py:41–44) touches the public driver names.

### 3.2 Asserts app internals / privates instead of the public contract
- **`test_tolerant_loader_skips_broken_file`** (test_compat_loader.py:28–38) calls the **private** `compat._load_modules_tolerant` directly (name with leading underscore). This mirrors the sibling-audit warning about `test_cross_scan.py` asserting upstream privates (`_split_budget`, `_sweep_targets`): here the app's own private loader is asserted rather than the public `load_*_modules` wrappers. If `_load_modules_tolerant` is refactored (e.g. folded into the wrappers), this test breaks despite the public contract being unchanged.
- **`test_cancel_event_stops_driver`** (test_compat_loader.py:46–51) reaches into `PhoneService._thread_cancel` (private attribute, line 49) and asserts `cancel()` returns `None` — which is true by construction (`cancel` has no return statement). It does not verify that an in-flight scan actually stops.

### 3.3 Tautologies / self-fulfilling assertions
- **`test_load_phone_modules_five_modules`** (test_compat_loader.py:21–25) — **flagged self-fulfilling in the brief.** `cats` is computed from the very `mods` returned by `load_phone_modules()`, then compared to a hardcoded set `{"auth","crm","shopping","social"}`. This is circular: it asserts that phonsint's current on-disk category layout matches a literal the test author copied from that same layout. It is not an independent contract; it pins the current directory structure. Same class of issue as the phone parity test flagged in the brief.
- **`test_load_catalog_username`** (test_sites_catalog.py:13–17): `total == state.sites_total` where `total` is the return value of `load_sites()` and `state.sites_total` is set *by that same call* (`phone_service.py:101`, `sherlock_service.py:116`). Both sides derive from the same load — tautological; it cannot detect a loader that returns a wrong count while also mis-writing state.
- **`test_load_catalog_phone_swaps_names`** (test_sites_catalog.py:20–24): `names` is built from `state.sites_cache`, which `PhoneService().load_sites()` just populated from the same modules it loaded (phone_service.py:103). Count == 5 is circular and hardcoded to phonsint's current 5 modules.

### 3.4 Weak / mismatched assertions
- **`test_drivers_are_coroutines`** (test_compat_loader.py:41–44): test name implies coroutine functions, but asserts only `callable`. `run_username_scan` etc. are `async def` (user_scanner_compat.py:116, 220, 299, 386), but `callable` passes for any function/class — it does not verify `inspect.iscoroutinefunction`.
- **`test_load_catalog_email`** (test_sites_catalog.py:27–29): loose range `100 < total < 500` instead of the known exact count (220 email modules per context). Passes even if the catalog regresses to 101 or 499.
- **`test_load_user_modules_returns_pairs`** (test_compat_loader.py:8–13): `len(mods) > 2000` instead of exact 2,521 (context: 2,521 username modules). Same under-detection problem.
- **`test_state_has_phone_mode_constant`** (test_sites_catalog.py:32–35) and **`test_selected_sites_default_empty`** (test_sites_catalog.py:38–39): trivial state-default assertions, not catalog behavior; they test `core/constants.py` and `core/state.py` defaults, which belong elsewhere if kept at all.

---

## 4) Missing assertions (gaps)

Per the audit dimensions, none of the following are covered by either file:

1. **Exact module counts.** No test asserts 2,521 username / 220 email / 5 phone. Only loose bounds (`> 2000`, `> 100`) and the circular phone check. Given context says 0 of 2,521 / 220 / 5 are skipped today, exact-count tests would detect silent loader regressions.
2. **Category names / category counts.** Context says 17 username / 20 email / 4 phone categories. `test_load_phone_modules_five_modules` checks phone category *names* (circularly), but no test asserts username or email category names or counts — a catalog regression (renamed/dropped category) would go unnoticed.
3. **Loader cache behavior.** Context: the tolerant loader **discards upstream's `lru_cache`** (2.76s / 2.22s repeat loads vs ~0s upstream). No test asserts repeat-load caching, and no performance/regression test guards `test_load_user_modules` — already the suite's slowest test at 6.97s (user_scanner engine import). Without a cache test, reintroduction of `lru_cache` or its loss is invisible.
4. **Tolerant-skip logging.** `_load_modules_tolerant` logs each skip at `WARNING` (user_scanner_compat.py:80) and a summary at `INFO` (user_scanner_compat.py:82). Context: 0 of 2,521 / 220 / 5 modules are skipped today. No test verifies (a) that a skip emits a log record, or (b) that the production load skips zero modules. The synthetic skip test only covers the private loader, not the wrappers.
5. **Drivers are actual coroutines.** `test_drivers_are_coroutines` should use `inspect.iscoroutinefunction`, not `callable`.
6. **Cancel actually halts an in-flight scan.** `test_cancel_event_stops_driver` asserts `cancel() is None`; it never starts a scan and confirms it terminates.
7. **`state.sites_tag_index` shape.** `test_load_catalog_username` asserts truthiness only (17); no assertion that the inverted index maps tags to site-name lists, or that lookups return expected sites.
8. **Phone-service contract beyond count.** `test_load_catalog_phone_swaps_names` asserts `len(names) == 5` but not that names come from `get_site_name_phone` (the comment claims this but doesn't assert it).

---

## 5) Proposed improvements (concrete test sketches)

All sketches target the two files as one unit; cite `user_scanner_compat.py` / service source where the contract lives.

### 4.1 Exact module counts (replace loose bounds)

```python
def test_load_user_modules_exact_count():
    mods = compat.load_user_modules()
    assert len(mods) == 2521   # context: 2,521 username modules

def test_load_email_modules_exact_count():
    mods = compat.load_email_modules()
    assert len(mods) == 220    # context: 220 email modules

def test_load_phone_modules_exact_count():
    mods = compat.load_phone_modules()
    assert len(mods) == 5      # context: 5 phone modules
```
Cite `user_scanner_compat.py:33–58` (wrappers) and context counts. These are real, independent contracts (counts come from upstream module directories, not from the test).

### 4.2 Category contract (independent of the returned modules)

```python
EXPECTED_PHONE_CATS = {"auth", "crm", "shopping", "social"}

def test_load_phone_modules_category_names():
    mods = compat.load_phone_modules()
    assert {c.lower() for c, _ in mods} == EXPECTED_PHONE_CATS
```
Keep but source `EXPECTED_PHONE_CATS` from a single constants location so it is not self-fulfilling. Add username/email equivalents once category names are fixed in `core/constants.py` or a catalog manifest (context: 17 / 20 categories).

### 4.3 Public-wrapper contract instead of private `_load_modules_tolerant`

Retain the skip behavior but drive it through the public API where possible, plus a dedicated private-loader test clearly marked:

```python
def test_tolerant_loader_skips_broken_file_public(tmp_path):
    # point a public loader at a dir with one bad module; expect skip + log
    ...
    assert not any(mod.__name__.endswith("boom") for _, mod in mods)
```
And keep a narrow unit test for `_load_modules_tolerant` (current test_compat_loader.py:28–38) but relabel it as testing the private helper explicitly. This resolves the "asserts private instead of contract" concern raised by the sibling-audit context.

### 4.4 Tolerant-skip logging + zero-skip production invariant

```python
def test_tolerant_loader_logs_skip(caplog, tmp_path):
    (tmp_path / "boom.py").write_text("raise RuntimeError('x')")
    with caplog.at_level(logging.WARNING, logger="services.user_scanner_compat"):
        compat._load_modules_tolerant(tmp_path)
    assert any("skipped module" in r.message for r in caplog.records)

def test_production_load_skips_zero_modules():
    assert len(compat.load_user_modules()) == 2521   # 0 skips per context
    assert len(compat.load_email_modules()) == 220
    assert len(compat.load_phone_modules()) == 5
```
Cite `user_scanner_compat.py:80,82` (logging). The zero-skip test encodes the context finding that nothing is skipped today; any future skip fails loudly.

### 4.5 Loader cache / performance regression guard

```python
def test_repeat_load_is_cached_or_fast(benchmark):
    # first load warms; second should be materially faster (upstream lru_cache
    # was discarded; document current behavior, guard against slowdown)
    compat.load_user_modules()
    elapsed = benchmark(compat.load_user_modules)
    assert elapsed < 1.0   # tune to observed baseline; << 6.97s single import
```
Cite context: tolerant loader dropped upstream's `lru_cache` (2.76s/2.22s vs ~0s); `test_load_user_modules` is the suite's slowest at 6.97s. This documents current behavior and guards regressions.

### 4.6 `test_drivers_are_coroutines` — assert coroutine functions

```python
import inspect
def test_drivers_are_coroutine_functions():
    for fn in ("run_username_scan", "run_email_scan", "run_cross_scan_async"):
        assert inspect.iscoroutinefunction(getattr(compat, fn))
```
Cite `user_scanner_compat.py:116,220,299,386`. Replaces weak `callable` (test_compat_loader.py:43).

### 4.7 Cancel actually stops a scan

```python
def test_cancel_stops_inflight_scan():
    svc = PhoneService()
    svc._thread_cancel.set()   # or cancel mid-run via a real scan
    result = svc.cancel()
    assert result is None
    # stronger: run scan with cancel set and confirm on_result not flooded /
    # worker loop terminates
```
Cite `phone_service.py:240–256` (`cancel`). At minimum, drop the pretense that `assert result is None` validates cancel behavior.

### 4.8 test_sites_catalog — break tautologies

```python
def test_load_catalog_username_populates_state():
    svc = SherlockService()
    total = asyncio.run(svc.load_sites(mode=MODE_USERNAME))
    assert total == 2521
    assert state.sites_total == 2521          # independent of return value
    assert state.sites_cache                  # non-empty
    assert state.sites_tag_index              # non-empty inverted index
    # spot-check tag index shape
    for tag, names in (state.sites_tag_index or {}).items():
        assert isinstance(tag, str) and isinstance(names, list)
```
`total == state.sites_total` remains (harmless) but is supplemented by exact counts and tag-index shape. Cite `sherlock_service.py:100–128` and `core/state.py:138–149`.

```python
def test_load_catalog_phone_exact():
    total = asyncio.run(PhoneService().load_sites())
    assert total == 5
    assert state.sites_total == 5
    names = {n.lower() for n in (state.sites_cache or [])}
    assert names == {"auth","crm","shopping","social"}   # sourced from constants, not from mods
```
Replace circular `len(names) == 5` (test_sites_catalog.py:24) with exact count + name set from a single source of truth.

```python
def test_load_catalog_email_exact():
    total = asyncio.run(EmailService().load_sites(mode=MODE_EMAIL))
    assert total == 220            # replace 100 < total < 500
    assert state.sites_total == 220
```

### 4.9 Drop or relocate trivial default checks

`test_state_has_phone_mode_constant` (test_sites_catalog.py:32–35) and `test_selected_sites_default_empty` (test_sites_catalog.py:38–39) assert `core/constants.py` / `core/state.py` defaults, not catalog behavior. Either move them to a `test_core_state.py`/`test_constants.py` file or remove them from this catalog-focused test module.

---

## Verdict

The two files test the right **seams** (the app's `user_scanner_compat` wrappers and the `SherlockService`/`EmailService`/`PhoneService` facades) rather than upstream internals, which is consistent with the compat-layer design. `test_tolerant_loader_skips_broken_file` is the one genuinely valuable failure-path test.

However, as a unit they are **weak**: most assertions are loose bounds, circular/self-fulfilling (phone count/categories derived from the modules under test; `state.sites_total == total` where both come from the same call), or trivial defaults. They miss the exact module counts (2,521 / 220 / 5), category contracts, loader-cache behavior, tolerant-skip logging, the zero-skip production invariant, and a real cancel-semantics test. `test_drivers_are_coroutines` asserts `callable` where its name promises coroutine functions, and `test_tolerant_loader_skips_broken_file` asserts a private helper (`_load_modules_tolerant`) — the same private-internal smell flagged in the sibling `test_cross_scan.py` audit.

**Recommended:** rewrite the unit around exact counts and independent category constants, add logging/cache/zero-skip tests, strengthen the driver and cancel assertions, break the `state.sites_total == total` tautology, and either relocate or drop the two trivial default checks. Report written to `tests/test_compat_loader.py.md` per the required 5-section structure.
