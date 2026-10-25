# Audit report — `tests/test_cross_scan.py` (67 lines)

**Scope:** this file only. Read-only audit; nothing modified.

**Reference material:** companion audit `docs/SWARM-2026-10-20/files/src/services/user_scanner_compat.py.md` (the app-side adapter under test), upstream `user-scanner 1.5.2.3` (`cross_scan.py:82-184`, `_scope` at `:187-207`, `_named_targets` at `:413-452`), app callers `src/services/sherlock_service.py:221-243` and `src/services/email_service.py:366-396`. Tests run: `8 passed in 0.46s` (pytest 9.1.1, Python 3.14.9).

---

## 1) File role

`tests/test_cross_scan.py` is the cross-scan engine test module. Its docstring ("pivot extraction, confidence scoring, budget split") is accurate: it covers `CrossScanConfig` defaults, `rank_usernames` preference ordering, `_split_budget`, `_sweep_targets`, `Result.extra` confidence carriage, and a single import-smoke test for `run_cross_scan_async`. It does **not** contain a single end-to-end test of the app's cross-scan path (`run_cross_scan_async` actually executing pivots).

---

## 2) What is actually asserted

Key assertions, verbatim, grouped by test:

| Test (line) | Assertions | Nature |
|---|---|---|
| `test_cross_scan_config_defaults` `:19-24` | `cfg.links == "all"`, `cfg.emails == "verified"`, `cfg.depth == 1`, `cfg.sweep == 3` | Contract (upstream dataclass defaults) |
| `test_rank_usernames_prefers_handles` `:27-34` | Pivot LINK/HANDLE/VERIFIED; `ranked[0] == "handleguy"` | Contract (PivotKind rank ordering) |
| `test_split_budget_gives_both_kinds_a_slot` `:37-40` | `_split_budget(2, 5, 5) == (1, 1)` | Contract (budget sharing) |
| `test_split_budget_zero_budget` `:43-44` | `_split_budget(0, 5, 5) == (0, 0)` | Contract (boundary) |
| `test_sweep_targets_respects_budget` `:47-50` | 10 pivots, budget 3 → `len(taken) == 3` | Contract |
| `test_sweep_targets_zero_budget_returns_empty` `:53-55` | `_sweep_targets([...], 0) == []` | Contract (boundary) |
| `test_result_carries_confidence_in_extra` `:58-61` | `r.extra["confidence"] == "confirmed"`; `r.is_found() is True` | Contract (Result.extra) |
| `test_cross_scan_importable_from_compat` `:64-67` | `from services.user_scanner_compat import run_cross_scan_async`; `callable(...)` | Smoke (importability only) |

**Contract vs tautology:** All 8 tests are genuine contract tests of upstream internals. None are tautologies. However, only `:64-67` even touches the app surface (`services.user_scanner_compat`), and it asserts **callability**, not behaviour — so every assertion in the file can pass while the app's cross-scan is critically broken. There is zero coverage of: scope propagation, `run_cross_scan_async` execution, the app's `CrossScanConfig(modules=..., categories=...)` wiring, stdout capture of upstream's cross-scan `print()` calls, or confidence-key propagation through the app's callback chain.

---

## 3) Layer analysis

**The file tests upstream private helpers, not the app's `run_cross_scan_async` wrapper path.**

- Lines 4-9 import from `user_scanner.core.cross_scan`: `CrossScanConfig`, `_split_budget`, `_sweep_targets` — all **upstream private** symbols (the underscore prefix is literal).
- Line 65-67 imports `run_cross_scan_async` from `services.user_scanner_compat` but only asserts `callable(...)`. It never *calls* it, never passes a `CrossScanConfig`, never checks `modules`/`categories`/`scope`, never verifies `selected` site filtering, never captures stdout.
- The sibling compat audit establishes that the app's cross-scan is critically broken: `user_scanner_compat.py:492` hard-codes `scope=None`; `CrossScanConfig.modules`/`.categories` are never populated by either caller (`sherlock_service.py:224-229`, `email_service.py:375-380`); the caller's `selected` site selection never reaches the sweep (`user_scanner_compat.py` has no `selected` parameter at `:386-398`). Result: each pivot sweeps all 2,521 modules (~7,497 module requests at `depth=1, sweep=3`) regardless of user site selection — a multi-minute silent stall that ships **untested**, because this file asserts the upstream helpers instead of this app-side wiring.
- The app imports 12 upstream private functions from `core.cross_scan` (`user_scanner_compat.py:400-414`). Asserting those privates in tests locks the app to upstream internals and gives a false sense of coverage: the private helpers work fine upstream; the *app's re-implementation* drops upstream's `_scope()`/`_email_scope()` scoping, and nothing in this file catches that gap.

So the layer tested = **upstream's private API**. The layer that needs testing = **the app's wrapper path** (`services.user_scanner_compat.run_cross_scan_async` + its `cross_scan_enabled` branch in the services). The file covers neither app caller.

---

## 4) Proposed improvements

### 4.1 One test that FAILS today against the scope=None bug

```python
# tests/test_cross_scan.py — addition (would FAIL today)
import asyncio
from unittest.mock import AsyncMock, patch

from user_scanner.core.cross_scan import CrossScanConfig
from user_scanner.core.pivots import Pivot, PivotKind
from user_scanner.core.result import Result

from services.user_scanner_compat import run_cross_scan_async


def _taken(username, site):
    r = Result.taken()
    return r.update(username=username, site_name=site, category="Social", is_email=False)


async def test_cross_scan_respects_selected_sites_and_passes_modules():
    # User selected exactly one site; cross-scan must not sweep all 2,521 modules.
    selected = {"github"}
    all_user_modules = [("github", object())]  # 1 module
    all_email_modules = []
    cfg = CrossScanConfig(links="all", emails="verified", sweep=3, depth=1)
    emitted = []

    async def on_result(item):
        emitted.append(item)

    with patch("services.user_scanner_compat.run_username_scan", new=AsyncMock()) as sweep_mock:
        await run_cross_scan_async(
            initial_results=[_taken("jane", "github")],
            all_user_modules=all_user_modules,
            all_email_modules=all_email_modules,
            cross_config=cfg,
            on_result=on_result,
            cancel_event=asyncio.Event(),
            timeout=5,
            concurrency=5,
            allow_loud=False,
            no_nsfw=False,
            proxy=None,
            selected=selected,           # ← not accepted today → TypeError / ignored
        )

    # Assert the sweep was scoped to the selected module set, not all_user_modules.
    swept_module_sets = {call.kwargs.get("modules") or call.args[1] for call in sweep_mock.call_args_list}
    assert swept_module_sets == {all_user_modules} or all(
        len(mods) == 1 for mods in swept_module_sets
    )
```

This fails today in two ways: (1) `run_cross_scan_async` has no `selected` parameter, and (2) even if accepted, `user_scanner_compat.py:475` passes `all_user_modules` (all 2,521) instead of the scoped set, and `:492` hard-codes `scope=None` → `_named_targets` skips site filtering entirely.

### 4.2 Additional concrete test sketches

| # | Test sketch | What it catches | Cite |
|---|---|---|---|
| A | `test_cross_scan_config_populates_modules_categories` — construct `CrossScanConfig(modules=("github",), categories=("Social",))` and assert `.modules == ("github",)`, `.categories == ("Social",)`. | Locks in that `modules`/`categories` are real fields the compat must read (currently read nowhere). | `cross_scan.py:60-79` |
| B | `test_run_cross_scan_async_emits_scope_to_named_targets` — mock `_named_targets` inside the compat module; assert it is called with a non-`None` `scope` when `CrossScanConfig(modules=..., categories=...)` is set, and `None` when unset. | Directly targets `user_scanner_compat.py:492` (`scope=None` hard-coded). | `:492` |
| C | `test_run_cross_scan_async_sweeps_scoped_modules_not_all` — mock `run_username_scan`; assert the module list passed to the sweep equals the scoped subset (or `all_user_modules` only when `scope is None`). | The `:475-485` sweep passes all modules unscoped. | `:475-485` |
| D | `test_cross_scan_stdout_not_polluted` — capture `sys.stdout` around `_sweep_targets`/`_email_targets` calls inside a compat run; assert empty. Upstream prints unconditionally (`cross_scan.py:341-388`). | B-5: upstream `print()` leaks into the Flet process console; no `contextlib.redirect_stdout` exists in the compat file. | `user_scanner_compat.py:448,457`; B-5 |
| E | `test_confidence_key_propagates_through_callback` — run a tiny cross-scan with a found hit; assert `on_result` receives `(..., r)` where `r.extra["confidence"]` is set (`_apply_confidence` at `user_scanner_compat.py:548,551`). | Confidence keys reach the app's callback chain; currently `_apply_confidence` scores only `is_found()` hits and the returned list can diverge from what `on_result` emitted (N-6). | `:548,551`; N-6 |
| F | `test_run_cross_scan_async_accepts_selected_parameter` — inspect signature; assert `selected` is a parameter and that passing a non-empty set filters the sweep. | The caller's `selected` set (`sherlock_service.py:148`) never reaches the sweep. | `:386-398`; N-1 |

### 4.3 Structural recommendation

Replace the upstream-private imports at lines 4-9 with tests of the **app's public wrapper**. Keep one or two upstream-helper tests only if the app genuinely delegates to them (it does not — it re-implements `run_cross_scan`). The compat imports 12 upstream private symbols (`user_scanner_compat.py:400-414`); tests should not lock the app to those internals. Instead, assert behaviour through `run_cross_scan_async`'s public parameters (`cross_config`, `selected`, `on_result`, `cancel_event`) and stub out upstream calls.

---

## 5) Verdict

**The file passes all 8 tests but tests the wrong layer.** Every assertion is a valid contract test of upstream's private helpers (`_split_budget`, `_sweep_targets`, `rank_usernames`, `CrossScanConfig` defaults, `Result.extra`), and `test_cross_scan_importable_from_compat` (`:64-67`) is merely an import smoke test — it asserts `callable(run_cross_scan_async)` and never exercises the app's cross-scan path.

Consequently the app's critically broken cross-scan ships untested: `scope=None` hard-coded at `user_scanner_compat.py:492`, `CrossScanConfig.modules`/`.categories` never populated by either caller (`sherlock_service.py:224-229`, `email_service.py:375-380`), and the caller's `selected` site selection never forwarded (the compat signature at `:386-398` has no `selected` parameter). Each pivot sweeps all 2,521 modules regardless of user selection — exactly the behaviour the sibling audit flags as Critical (B-4 / N-1) — and nothing in `tests/test_cross_scan.py` would catch it.

**Recommended immediate change:** add `test_cross_scan_respects_selected_sites_and_passes_modules` (section 4.1), which fails today, plus the supporting assertions in 4.2 (scope propagation, stdout capture, confidence-key propagation, `selected` parameter acceptance). Until such a test exists and passes against the app's wrapper path, the cross-scan scope bug is not covered by the test suite.

Citations: `tests/test_cross_scan.py:4-9,19-24,27-34,37-40,43-44,47-50,53-55,58-61,64-67`; `user_scanner_compat.py:386-398,400-414,475-485,492,548,551`; `sherlock_service.py:221-243,148`; `email_service.py:366-396,375-380`; upstream `cross_scan.py:60-79,82-184,187-207,341-388,413-452`.
