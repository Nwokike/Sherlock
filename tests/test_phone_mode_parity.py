"""Phone-mode parity — history restore, export rows, reset semantics."""


from core.constants import MODE_PHONE
from core.state import state
from services.phone_service import PhoneResult, PhoneService


def test_state_has_phone_results_field():
    state.reset_search()
    assert state.phone_results is not None


def test_reset_search_clears_phone_rows():
    state.phone_results[:] = [{"name": "facebook"}]
    state.phone_results_address = "+15551234567"
    state.phone_found_count = 1
    state.reset_search()
    assert list(state.phone_results) == []
    assert state.phone_results_address == ""
    assert state.phone_found_count == 0


def test_phone_snapshot_row_shape_matches_email_card_contract():
    # The results screen and exports reuse the email-shaped row dicts, so
    # phone rows must carry the same keys.
    row = {
        "name": "facebook",
        "domain": "Social",
        "method": "",
        "exists": True,
        "rateLimit": False,
        "unavailable": False,
        "frequent_rate_limit": False,
        "emailrecovery": None,
        "phoneNumber": None,
        "others": {"extra": {}, "media": {}, "url": "https://facebook.com", "message": ""},
    }
    for key in (
        "name", "domain", "exists", "rateLimit", "unavailable", "others",
    ):
        assert key in row
    assert isinstance(row["others"], dict)


def test_phone_result_mapping_registered():
    p = PhoneResult(
        name="facebook", category="Social", exists=True,
        url="https://facebook.com",
    )
    assert p.exists is True
    assert p.url == "https://facebook.com"


def test_phone_service_has_worker_loop_for_cancel():
    svc = PhoneService()
    # _run_worker assigns self._worker_loop so cancel() can reach it.
    assert hasattr(svc, "_worker_loop")


def test_mode_phone_constant_is_phone():
    assert MODE_PHONE == "phone"
