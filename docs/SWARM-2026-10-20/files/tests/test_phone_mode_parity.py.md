# Audit — `tests/test_phone_mode_parity.py`

(Led-agent audit — the dispatched agent timed out before writing; this report
was written by the lead agent from direct file reads and the sibling findings.)

## 1) File role
Six tests asserting "phone-mode parity — history restore, export rows, reset
semantics" against `core.constants.MODE_PHONE`, `core.state.state`,
`services.phone_service` (PhoneResult/PhoneService).

## 2) What is actually asserted (paste-level)
- `test_state_has_phone_results_field` (:9-11): `state.reset_search()` then
  `state.phone_results is not None` — **tautology**: the field is initialized
  to a non-None `ObservableList` in `core/state.py`; `reset_search()` re-creating
  it is the only behavior touched.
- `test_reset_search_clears_phone_rows` (:14-21): **the one genuinely useful
  test** — seeds three phone state fields and asserts `reset_search()` clears
  all three. Real contract, real value.
- `test_phone_snapshot_row_shape_matches_email_card_contract` (:24-43):
  **self-fulfilling.** It builds the `row` dict literal itself at :27-38 and
  then asserts the keys it just wrote exist (:39-42). It asserts nothing about
  the app. The comment claims "the results screen and exports reuse the
  email-shaped row dicts" but no app function is called — the contract it
  names (`main.py` `_phone_row`-shaped dicts / `results_screen` tab reads) is
  never executed.
- `test_phone_result_mapping_registered` (:46-52): constructs `PhoneResult`
  directly and asserts the two kwargs it just passed round-trip. Tautology
  (dataclass field echo). Also bypasses the real mapper `_map_result`
  (phone_service.py:50-79) where the `"https://Social"` domain bug lives.
- `test_phone_service_has_worker_loop_for_cancel` (:55-58): `hasattr(svc,
  "_worker_loop")` — but `_worker_loop` is only *assigned* inside
  `_run_worker`; a fresh `PhoneService()` has it **only if it is a declared
  class attribute**. Asserting presence via `hasattr` on a fresh instance
  proves either an always-None attribute or nothing at all; cancel()
  correctness is never exercised.
- `test_mode_phone_constant_is_phone` (:61-62): constant echo. Harmless.

## 3) The bug this file exists to catch — and misses
- **`results_screen.py:475-476` reads `active_progress.rate_limited` and
  `.unavailable`; `PhoneSearchProgress` (`src/services/phone_service.py:38-47`)
  has only `found/not_found/errors`** → live `AttributeError` on every phone
  scan, swallowed by `main.py:2322 on_error`. **No test in this file (or the
  suite) imports `results_screen` or constructs `PhoneSearchProgress` and
  touches those fields.** A 3-line test would fail today:
  `p = PhoneSearchProgress(); assert hasattr(p, "rate_limited")`.
- `PhoneSearchProgress` also lacks the email-mode contract fields the parity
  name promises (`EmailSearchProgress` has `rate_limited`/`unavailable`,
  email_service.py:52-61).
- MODE_PHONE round-trip gap: persisted by `home_screen.py:419`, restored only
  for username/email by `main.py:695` — untested (a restore test would fail
  today).

## 4) Proposed improvements (concrete)
```python
def test_phone_progress_matches_email_contract():
    from services.phone_service import PhoneSearchProgress
    from services.email_service import EmailSearchProgress
    for f in ("rate_limited", "unavailable"):          # FAILS today
        assert hasattr(PhoneSearchProgress, "__dataclass_fields__") and \
            f in PhoneSearchProgress.__dataclass_fields__

def test_phone_row_shape_matches_email_row_shape():
    from main import _phone_row, _email_row            # real producers
    pr = {"name": "facebook", "category": "Social", "exists": True, "url": "", ...}
    assert set(_phone_row(pr)) == set(_email_row({...}))  # real contract
```
Plus: a MODE_PHONE restore test (`fake storage → _load_saved_state →
state.search_mode == MODE_PHONE`, fails today), and a `_map_result` test
feeding a phonsint `Result(category="social")` asserting the card domain is a
real URL, not `"https://Social"`.

## 5) Verdict
**ISSUES FOUND — 4 of 6 tests are tautologies; the file's namesake contract
(phone rows matching the email card contract) is asserted against a literal
the test wrote itself, and the one real phone bug (missing progress fields →
AttributeError) ships with zero coverage.** Keep
`test_reset_search_clears_phone_rows`; replace the rest with the three
contract tests above.
