# Audit report: tests/test_services_all_modes.py (72 lines)

**Repo:** /home/maikel/.zcode/workspace/default/Sherlock-V3
**Audited file (read-only, not modified):** tests/test_services_all_modes.py
**Supporting code read:** src/services/sherlock_service.py, src/services/email_service.py, src/services/phone_service.py, src/services/user_scanner_compat.py, tests/conftest.py, tests/test_phone_mode_parity.py (sibling, for comparison only)

## 1) File role

The module docstring claims "Service contract tests across all three engine modes (username/email/phone)". It imports the three real service facades (no mocks) and defines 9 test functions:

- L11-16 `test_sherlock_load_sites_populates_mode_catalog` — SherlockService username mode
- L19-23 `test_sherlock_load_sites_email_mode` — SherlockService email mode
- L26-27 `test_email_service_available`
- L30-45 `test_email_skip_password_recovery_filters_loud`
- L48-51 `test_phone_service_load_sites`
- L54-58 `test_phone_result_mapping_registered`
- L60-62 `test_site_result_has_confidence_badge_field`
- L65-67 `test_hudson_methods_exist`
- L70-72 `test_cross_scan_service_methods_wired`

It is a smoke/import-level suite: it never calls `SherlockService.search`, `EmailService.search`, or `PhoneService.search`, never drives `run_username_scan`/`run_email_scan`/`run_phone_scan`, and never asserts on a populated `SearchProgress`/`EmailSearchProgress`/`PhoneSearchProgress`. It is therefore NOT a behavioral test of any mode despite the docstring.

## 2) What is actually asserted (contract vs tautology)

Pasted assertions with analysis:

**L14** `assert total > 2000` — data-dependent snapshot, not a contract. Depends on user-scanner shipping >2000 username modules; breaks if upstream trims/adds modules. Also reads the instance cache (`self._modules`), so the value is only meaningful on a fresh instance.

**L15-16** `assert svc._modules is not None` / `assert svc._modules_mode == "username"` — genuine but shallow wiring checks. `_modules_mode == mode` is set unconditionally at sherlock_service.py:114 whenever a reload happens, so it partly asserts its own assignment.

**L22** `assert 100 < total < 500` — another fragile data-bound snapshot for email modules (sherlock_service.py:109-111).

**L23** `assert svc._modules_mode == "email"` — wiring check only.

**L27** `assert EmailService().is_available is True` — **tautology**: `is_available` literally `return True` at email_service.py:190-191 (same for sherlock_service.py:97-98 and phone_service.py:113-115). Asserts nothing about the service working.

**L37-44** `test_email_skip_password_recovery_filters_loud` — rebuilds the loud/kept partition itself from `load_email_modules()` + `is_loud_user(...)`:
```python
loud  = [m for m in mods if is_loud_user(get_site_name_user(m[1]), is_email=True)]
kept  = [m for m in mods if not is_loud_user(get_site_name_user(m[1]), is_email=True)]
```
**L44** `assert len(kept) <= len(mods)` — **tautology**: `kept` is constructed as a subset of `mods`.
**L45** `assert all(m not in kept for m in loud)` — **tautology**: `loud` and `kept` are complementary partitions of the same list.
The test never calls `EmailService.search(..., skip_password_recovery=True)`, so the actual service branch (email_service.py:220-228) that applies this filter is never exercised.

**L51** `assert total == 5` — hardcoded exact count of phonsint modules. Data-dependent/fragile: adding one phonsint module breaks the test; it asserts nothing about scanning behavior. `PhoneService.search` is never called.

**L56-58** `test_phone_result_mapping_registered`:
```python
r = PhoneResult(name="facebook", category="Social", exists=True)
assert r.exists is True
assert r.name == "facebook"
```
Pure dataclass construction echo — **tautology**. The real mapping logic (`PhoneService._map_result`, phone_service.py:50-85) and its `unavailable`/`rate_limit` fields are never tested.

**L61-62** `test_site_result_has_confidence_badge_field`:
```python
sr = SiteResult(site_name="github", status="Claimed", badge="confirmed")
assert sr.badge == "confirmed"
```
Again pure construction echo. The actual badge logic — `SherlockService._badge_for` (sherlock_service.py:75-87) and the confidence override in `_map_username_result` (sherlock_service.py:342-345: `badge = str(confidence).lower()`) — is never tested. The test name promises confidence-badge behavior that it does not cover.

**L66-67** `test_hudson_methods_exist`:
```python
assert callable(SherlockService.run_hudson)
assert callable(EmailService.run_hudson)
```
`callable()` on a defined method is trivially True; the methods are never invoked. `run_hudson` shells out to `user_scanner.core.hudson.run_hudson_scan` with stdout capture (sherlock_service.py:276-290, email_service.py:414-427) — i.e. the "hudson prompt"/network surface is never tested, and `PhoneService` has no `run_hudson` at all (asymmetry across modes goes unasserted).

**L72** `assert hasattr(svc, "_run")` — **tautology**: `_run` is defined at sherlock_service.py:169; `hasattr` on an existing method cannot fail. The cross-scan round inside `_run` (sherlock_service.py:221-243, gated on `app_state.cross_scan_enabled`) is never exercised.

No assertion anywhere touches `SearchProgress.is_cancelled`, `EmailSearchProgress.rate_limited`/`unavailable`, `PhoneSearchProgress.errors`, or the email domain derivation.

## 3) Per-mode coverage

| Mode | What the file actually does | Real service exercised? | Gaps |
|------|----------------------------|-------------------------|------|
| **Username** (L11-16) | `SherlockService().load_sites(mode="username")`; checks count > 2000, `_modules`, `_modules_mode` | `load_sites` only | No `search()`, no `SearchProgress` buckets (found/not_found/errors), no cancellation behavior. Known untested bug: `is_cancelled` is effectively always False on the returned progress — sherlock_service.py:249 sets `is_running = False` in `finally`, then the post-loop at sherlock_service.py:161-167 only sets `is_cancelled=True` when `is_running` is still True, so that branch is dead on the returned `last_prog` (sibling audit flag: sherlock_service.py:161-167). |
| **Email** (L19-23, L26-27, L30-45) | `load_sites(mode="email")`; `is_available`; standalone partition of `load_email_modules()` via `is_loud_user` | `load_email_modules`/`is_loud_user` only, **not** `EmailService.search` | Never exercises `EmailService.search`, `EmailSearchProgress`, rate-limited classification (`_is_rate_limited` email_service.py:64-71), or unavailable classification (`_map_result` email_service.py:152-160: `rate_limit=rate, unavailable=not rate`). The "email domain cap" surface (`_domain_from` email_service.py:74-81, incl. the speculative `f"{dotted}.com"` fallback) is untested. |
| **Phone** (L48-58) | `PhoneService().load_sites() == 5`; direct `PhoneResult` construction | `load_sites` only | **`PhoneService.search` / `run_phone_scan` are never called** — the phone branch does not exercise the real service at all. `PhoneSearchProgress` has no `rate_limited`/`unavailable` lists (phone_service.py:38-47), only `errors`, unlike EmailSearchProgress which has both (email_service.py:52-61) — inconsistent cross-mode contract, untested. `_map_result` rate_limit/unavailable mapping (phone_service.py:72-73) untested. |

Cross-scan (`_run`, cross-scan rounds at sherlock_service.py:221-243) is asserted only via `hasattr(svc, "_run")` — not behaviorally.

## 4) Proposed improvements

Concrete sketches (assertions to add; all should monkeypatch/fake the low-level scan drivers so tests stay offline and deterministic):

**a) Email rate-limited + unavailable classification (closes the biggest gap)**
```python
def test_email_search_rate_limited_classification(monkeypatch):
    svc = EmailService()
    async def fake_scan(email, modules, on_result, cancel, **kw):
        on_result(("result", "Social", "leakedsite", FakeResult(status=TAKEN, reason="429 too many requests")))
        on_result(("result", "Social", "deadsite",   FakeResult(status=ERROR,  reason="connection timeout")))
    monkeypatch.setattr("services.email_service.run_email_scan", fake_scan)  # or patch user_scanner_compat.run_email_scan
    prog = asyncio.run(svc.search("victim@example.com"))
    assert any(r.rate_limit and not r.available for r in prog.rate_limited)
    assert any(r.unavailable and not r.rate_limit for r in prog.unavailable)
    assert prog.checked_modules == prog.total_modules
```
Also assert `EmailResult.exists is None` for both buckets (email_service.py:154-156). Add a domain test: `_domain_from` returns `host` from a URL, `name.replace("_",".")` otherwise, `f"{dotted}.com"` fallback (email_service.py:74-81).

**b) Password-recovery filtering through the service (replaces tautological L37-45)**
```python
def test_email_search_skip_password_recovery_excludes_loud(monkeypatch):
    svc = EmailService()
    seen = []
    async def fake_scan(email, modules, on_result, cancel, **kw):
        seen.extend(modules)
    monkeypatch.setattr("...run_email_scan", fake_scan)
    asyncio.run(svc.search("a@b.com", skip_password_recovery=True))
    assert all(not is_loud_user(get_site_name_user(m[1]), is_email=True) for m in seen)
```
This actually exercises email_service.py:220-228 instead of re-deriving the partition.

**c) Username search + cancellation (closes is_cancelled gap)**
```python
def test_search_progress_buckets_and_cancel(monkeypatch):
    svc = SherlockService()
    def fake_scan(username, modules, on_result, cancel, **kw):
        on_result(("result", "Social", "github", FakeResult(status=TAKEN)))
        cancel.set()
    monkeypatch.setattr("...run_username_scan", fake_scan)
    prog = asyncio.run(svc.search("maikel"))
    assert any(r.status == "Claimed" for r in prog.found)
    assert prog.is_cancelled is True   # currently fails: sherlock_service.py:161-167 dead after finally@249
```
Also test `_badge_for`: 429/rate → "rate", cloudflare/captcha → "bot", timeout → "dead" (sherlock_service.py:75-87), and confidence override `badge = str(confidence).lower()` (sherlock_service.py:344-345).

**d) Phone service search (currently not exercised at all)**
```python
def test_phone_search_mapping_buckets(monkeypatch):
    svc = PhoneService()
    def fake_scan(phone, region, modules, on_result, cancel, **kw):
        on_result(("result", "Social", "truecaller", FakeResult(status=TAKEN, reason=""), phone_info))
        on_result(("result", "Social", "ratelimit", FakeResult(status=ERROR, reason="429"), phone_info))
    monkeypatch.setattr("...run_phone_scan", fake_scan)
    prog = asyncio.run(svc.search("+15551234567"))
    assert any(r.exists is True for r in prog.found)
    assert any(r.rate_limit for r in prog.errors)
```
And **contract fix**: add `rate_limited` and `unavailable` lists to `PhoneSearchProgress` (phone_service.py:38-47) to match EmailSearchProgress (email_service.py:52-61), and route `_map_result` rate_limit/unavailable into those lists instead of `errors` (phone_service.py:184).

**e) Hudson invocation + mode asymmetry**
Replace `callable(...)` (L66-67) with an invocation test monkeypatching `user_scanner.core.hudson.run_hudson_scan` (capture stdout, no network) for both `SherlockService.run_hudson` and `EmailService.run_hudson`; assert `PhoneService` has no `run_hudson` (decide whether to add it for parity).

**f) Replace brittle count snapshots**
- L14 `total > 2000` and L22 `100 < total < 500`: keep as `assert total > 0` plus mode-wiring checks, or document them as snapshot assertions that must be updated when user-scanner/phonsint data changes.
- L51 `total == 5`: change to `assert total > 0` unless phonsint's 5-module count is an intentional frozen contract.

**g) Cross-scan wiring**
Replace `hasattr(svc, "_run")` (L72) with a test that `search(..., after_primary=cb)` invokes the hook (sherlock_service.py:214-218), or monkeypatch `cross_scan_enabled` and assert cross results appear in `found`.

**h) Email validation**
`validate_email` invalid input → `ValueError` (email_service.py:212-213) is untested.

## 5) Verdict

The file does NOT live up to its docstring. It touches all three modes, but only at import/load/construction time: **zero calls to any `.search()` method, zero populated progress objects, zero rate-limit/unavailable/cancellation assertions.** Roughly half the assertions are tautologies (subset-of-itself at L44, complementary-partition at L45, dataclass field echo at L56-58/L61-62, `callable` at L66-67, `hasattr` at L72, `is_available is True` at L27), and the rest are fragile data-dependent counts (L14, L22, L51).

It catches none of the known untested bugs from the sibling audits: `PhoneSearchProgress` missing `rate_limited`/`unavailable` fields, `is_cancelled` effectively always False (sherlock_service.py:161-167, dead after `finally` at line 249), the email domain derivation, or the hudson prompt surface. The phone branch does not exercise `phone_service.search` at all; the email branch never exercises rate-limited classification.

**Status: rewrite/heavily augment.** Keep L11-23 as lightweight load-sites smoke tests (with non-brittle bounds), delete or replace the tautological tests with the behavioral sketches in section 4, and add per-mode `search()` tests driven by monkeypatched scan drivers. Until then, the suite passes while the real scan paths remain unverified.