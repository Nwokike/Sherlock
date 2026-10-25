# Audit report: tests/test_services.py (Sherlock-V3)

**File audited:** /home/maikel/.zcode/workspace/default/Sherlock-V3/tests/test_services.py (48 lines, 7 test functions)
**Scope:** THIS FILE ONLY. No files were modified. Supporting reads: src/services/{sherlock,email,phone}_service.py, tests/conftest.py, tests/test_storage_resilience.py (sibling), tests/test_services_all_modes.py (sibling), src/main.py:1081.
**Test run result:** 6 passed, 1 failed; the failure (`test_sherlock_search_returns_progress`) hit the 60s pytest-timeout, so the suite takes ~63s and fails in CI.
**pytest config:** pyproject.toml [tool.pytest.ini_options] — pythonpath=["src"], addopts "-ra -q", timeout=60, strict_markers; markers "live" / "asyncio".

---

## 1) File role

Docstring: `"Service contract tests for Sherlock-V2."` Imports three services and two helpers:

```python
from services.email_service import EmailService, validate_email     # tests/test_services.py:4
from services.phone_service import PhoneService                     # tests/test_services.py:5
from services.sherlock_service import SherlockService, parse_usernames  # tests/test_services.py:6
```

Conftest inserts `src/` on sys.path (tests/conftest.py:6), so `services.*` resolves to `src/services/*`. The file is a smoke-level contract/sanity suite: instantiate each service, assert `is_available`, plus trivial unit checks on `validate_email` and `parse_usernames`, and two `load_sites()` smoke tests. It does not exercise `search()`, `cancel()`, `run_hudson()`, proxy handling, or any network-dependent path with mocks.

---

## 2) What is actually asserted (with paste), contract vs tautology

### 2.1 `test_sherlock_service_available` — tests/test_services.py:9-11
```python
svc = SherlockService()
assert svc.is_available is True
```
Tautology. `SherlockService.is_available` is hardcoded `return True` (src/services/sherlock_service.py:97-98). The constructor takes `*args/**kwargs` and never fails. Asserts nothing about real availability, site data, or the user-scanner wrapper.

### 2.2 `test_email_service_available` — tests/test_services.py:14-16
```python
svc = EmailService()
assert svc.is_available is True
```
Tautology. `EmailService.is_available` hardcoded `return True` (src/services/email_service.py:189-191).

### 2.3 `test_phone_service_available` — tests/test_services.py:19-21
```python
svc = PhoneService()
assert svc.is_available is True
```
Tautology. `PhoneService.is_available` hardcoded `return True` (src/services/phone_service.py:113-115).

**Summary:** 3 of 7 tests are pure tautologies. They would pass even if every service were completely broken.

### 2.4 `test_validate_email` — tests/test_services.py:24-26
```python
assert validate_email("a@b.com") is True
assert validate_email("not-an-email") is False
```
Real behavior, but minimal. `validate_email` delegates to `user_scanner.core.helpers.is_valid_email` with a regex fallback (src/services/email_service.py:28-34). Only one valid and one invalid case; no boundary cases (empty string, bare `@`, subdomains, uppercase, TLD length, IP literals). Also not covered: `EmailService.search` raises `ValueError` for invalid email (email_service.py:212-213).

### 2.5 `test_parse_usernames` — tests/test_services.py:29-32
```python
assert parse_usernames("a b c") == ["a", "b", "c"]
assert parse_usernames("a,b,c") == ["a", "b", "c"]
assert parse_usernames("") == []
```
Real behavior, but shallow. `parse_usernames` (sherlock_service.py:59-72) dedupes, splits on comma-or-whitespace, strips. Untested: duplicates (`"a a a"`), mixed separators (`"a, b c"`), whitespace-only input, leading/trailing whitespace, trailing comma, single username.

### 2.6 `test_sherlock_search_returns_progress` — tests/test_services.py:35-40
```python
import asyncio
svc = SherlockService()
asyncio.run(svc.load_sites())
assert svc._modules is not None
assert len(svc._modules) > 0
```
Real intent (smoke that site modules load), but:
- Asserts **private** attribute `svc._modules` instead of the public return value of `load_sites()` or `total_modules` (no such public property exists on SherlockService — a gap itself).
- **Hangs >60s in this environment** (and failed CI-style): `load_sites()` → `load_user_modules()` → `_load_modules_tolerant` execs a corrupt `baliga.cpython-314.pyc` in the venv's user_scanner package and never returns (src/services/user_scanner_compat.py:76). The pytest-timeout of 60s fired. Non-hermetic, slow, and environment-fragile.
- `load_sites` default mode is "username" (sherlock_service.py:100); email mode and the `_modules_mode` cache key are not asserted here (they are in test_services_all_modes.py:13-24).

### 2.7 `test_phone_search_returns_progress` — tests/test_services.py:43-48
```python
import asyncio
svc = PhoneService()
asyncio.run(svc.load_sites())
assert svc._modules is not None
assert len(svc._modules) == 5
```
Same private-attr coupling (`svc._modules`). Additionally **hardcodes the module count to 5**: brittle — any change to phonsint's module set breaks the test without a contract change. Phone modules load fine here (test passed), unlike sherlock's.

---

## 3) Coverage analysis

### 3.1 Services covered vs the 12 in src/services/

`src/services/` contains 12 modules (excluding `__init__.py`):

| Service | Covered by test_services.py? | What is exercised |
|---|---|---|
| ad_service.py | No | — |
| cache_service.py | No | — |
| email_service.py | **Yes** | construction, `is_available`, `validate_email` |
| enrich_service.py | No | — |
| http_client.py | No | — |
| phone_service.py | **Yes** | construction, `is_available`, `load_sites()` count |
| report_service.py | No | — |
| scan_notify.py | No | — |
| sherlock_service.py | **Yes** | construction, `is_available`, `parse_usernames`, `load_sites()` |
| storage_service.py | No (covered by sibling test_storage_resilience.py) | — |
| update_service.py | No | — |
| user_scanner_compat.py | No | — |

**Coverage: 3 of 12 services.** Nine services have zero coverage in this file. Notably everything `search()`-related (the core of each service) is unexercised end-to-end: no `on_progress` capture, no `SearchProgress`/`EmailSearchProgress`/`PhoneSearchProgress` bucket assertions, no empty-input `RuntimeError` (sherlock_service.py:142-143), no invalid-email `ValueError` (email_service.py:212-213).

### 3.2 Known untested bugs this file could catch but doesn't

- **Hudson `input()` deadlock** (sherlock_service.py:286 / email_service.py:414): `run_hudson()` redirects stdout and calls `hudson.run_hudson_scan`, which can block on `input()`. Never tested; there is no test that `run_hudson` is non-deadlocking under captured stdout or that it degrades to `"Hudson check failed: ..."` (sherlock_service.py:287-289).
- **Cancel no-op paths:** `SherlockService.cancel()` (sherlock_service.py:292-293), `EmailService.cancel()` (email_service.py:429-445), `PhoneService.cancel()` (phone_service.py:240-256) are never invoked — including calling `cancel()` on an idle service, which should be a safe no-op.
- **Proxy staleness:** `set_proxy_manager` is called only-if-proxy (email_service.py:261-266: `if proxy: set_proxy_manager(...)`). Never tested that a proxy set on one search doesn't leak into a later proxy-less search, or that env restore (`restore()`, email_service.py:243-248) actually runs.
- **Email domain cap** (src/main.py:1081 `generated[:5]`): main.py caps generated probe addresses at 5; not asserted anywhere in this file.

### 3.3 How it compares to the sibling with regression value

Per context, `test_storage_resilience.py` is the only test file with genuine regression value: it uses `tmp_path`, `monkeypatch`, failure injection (`os.replace` raising `PermissionError` 3x then always), retry/roundtrip assertions, and singleton identity — all fast and hermetic.

`test_services.py` is **weaker, not in the same class**: no `tmp_path`, no `monkeypatch`, no failure injection, no `search()` invocation, 3 tautologies, private-attr assertions, one test that hangs >60s, and coverage of only 3/12 services. Its regression value is near zero; the hanging test actively hurts CI (suite takes ~63s and fails).

---

## 4) Proposed improvements (concrete sketches)

All sketches reference /home/maikel/.zcode/workspace/default/Sherlock-V3/tests/test_services.py unless noted.

### 4.1 Drop or replace the three tautologies (tests/test_services.py:9-21)
`is_available` is hardcoded `True` in all three services (sherlock_service.py:97-98, email_service.py:189-191, phone_service.py:113-115). Either delete these tests or assert something constructive, e.g. construction succeeds and cancellation primitive exists:

```python
def test_sherlock_service_constructs():
    svc = SherlockService()
    assert isinstance(svc._thread_cancel, threading.Event)
    assert svc._modules is None
```

### 4.2 Strengthen test_validate_email (tests/test_services.py:24-26)
Add boundary cases and force the fallback path via monkeypatch (user_scanner helper may be absent):

```python
@pytest.mark.parametrize("valid", ["a@b.com", "User@Example.COM", "a@b.co.uk"])
def test_validate_email_valid(valid):
    assert validate_email(valid) is True

@pytest.mark.parametrize("invalid", ["", "not-an-email", "@b.com", "a@", "a@b", "a@b.c"])
def test_validate_email_invalid(invalid):
    assert validate_email(invalid) is False

def test_validate_email_invalid_raises_in_search(monkeypatch):
    # ensure EmailService.search rejects malformed input (email_service.py:212-213)
    ...
```

### 4.3 Strengthen test_parse_usernames (tests/test_services.py:29-32)
```python
assert parse_usernames("a a a") == ["a"]                 # dedupe
assert parse_usernames("a, b c") == ["a", "b", "c"]      # mixed separators
assert parse_usernames("   ") == []                      # whitespace only
assert parse_usernames("  a , b ") == ["a", "b"]         # trim
assert parse_usernames("a,,") == ["a"]                   # trailing/empty items
```

### 4.4 Replace private-attr assertions with public contract (tests/test_services.py:35-48)
Instead of `svc._modules`, assert on `load_sites()` return value:

```python
def test_sherlock_load_sites_returns_count():
    svc = SherlockService()
    total = asyncio.run(svc.load_sites())
    assert isinstance(total, int) and total > 0

def test_phone_load_sites_count_stable():
    svc = PhoneService()
    total = asyncio.run(svc.load_sites())
    assert total == len(svc._modules)   # or assert total > 0; avoid magic 5
```
Also test mode switching (username vs email) and `_modules_mode` caching (sherlock_service.py:106-115), which test_services_all_modes.py already does — this file should not duplicate it, but at least assert email mode works.

### 4.5 Exercise search() end-to-end with a capturing on_progress (new tests)
Never covered. Sketch for sherlock:

```python
def test_sherlock_search_empty_raises():
    svc = SherlockService()
    with pytest.raises(RuntimeError, match="No valid usernames"):
        asyncio.run(svc.search(""))   # sherlock_service.py:142-143

def test_sherlock_search_progress_buckets(monkeypatch):
    # monkeypatch run_username_scan to feed synthetic results, capture on_progress
    # assert SearchProgress.found / not_found / errors bucketing (sherlock_service.py:190-197)
    # assert checked_sites == total_sites at end
```

Same pattern for EmailService (validate ValueError first) and PhoneService.

### 4.6 Test cancel() no-op and live paths (new tests)
```python
def test_cancel_idle_is_noop():
    for svc in (SherlockService(), EmailService(), PhoneService()):
        svc.cancel()  # must not raise
    # Sherlock: assert svc._thread_cancel.is_set()  (sherlock_service.py:292-293)
```

### 4.7 Test run_hudson without deadlocking (new tests; addresses sherlock_service.py:286)
Monkeypatch `user_scanner.core.hudson.run_hudson_scan` to print output and return, or to raise; assert captured stdout is returned and exceptions degrade to `"Hudson check failed: ..."` (sherlock_service.py:283-290). This is the concrete mitigation for the hudson `input()` deadlock risk.

### 4.8 Test proxy staleness / only-if-proxy (new tests; email_service.py:261-266)
Monkeypatch `user_scanner.core.helpers.set_proxy_manager`, record calls, run `EmailService.search` with a proxy then without; assert `set_proxy_manager` is called only when proxy is truthy and not left stale across calls. Also assert env vars are restored after the search (`restore`, email_service.py:243-248).

### 4.9 Make the suite hermetic and fast
The hanging `test_sherlock_search_returns_progress` must be fixed or removed: it loads real user_scanner modules from the venv, execs a corrupt `.pyc`, and burns the full 60s pytest-timeout (test took >60s). Options: mock `load_user_modules`, mark network/slow tests with the `live` marker and gate CI with `-m "not live"`, or replace with a fast monkeypatched version. Until fixed, this file reduces CI reliability rather than improving it.

---

## 5) Verdict

**Class: weak.** `tests/test_services.py` is a smoke test at best, not a regression suite in the class of `test_storage_resilience.py`. It covers 3 of 12 services; 3 of 7 tests are tautologies (`is_available is True` where the property hardcodes `True`); real behavior (`validate_email`, `parse_usernames`) is minimally asserted; two tests couple to private `svc._modules`; one test hangs >60s and fails under the configured pytest-timeout, making the whole file fail in CI; and `search()`, `cancel()`, `run_hudson()`, and proxy handling — including the known hudson `input()` deadlock risk at sherlock_service.py:286 — are entirely untested.

**Recommendation:** do not rely on this file for regression coverage. First, fix or remove the hanging `test_sherlock_search_returns_progress` test. Then rewrite the file to: drop tautologies, assert public contracts instead of private attrs, add boundary cases for `validate_email`/`parse_usernames`, add monkeypatched `search()` bucket tests for all three services, add `cancel()` no-op tests, add a non-deadlocking `run_hudson` test, and add a proxy-staleness/only-if-proxy test. Until then, `test_storage_resilience.py` remains the only test file here with genuine regression value.

**Citations:** tests/test_services.py:9-11, 14-16, 19-21, 24-26, 29-32, 35-40, 43-48; src/services/sherlock_service.py:59-72, 90-98, 100-128, 142-143, 276-290, 292-293; src/services/email_service.py:28-34, 189-191, 212-213, 243-248, 261-266, 414-427, 429-445; src/services/phone_service.py:113-115, 240-256; src/main.py:1081; tests/conftest.py:6; pyproject.toml:68-77; tests/test_storage_resilience.py (whole file).