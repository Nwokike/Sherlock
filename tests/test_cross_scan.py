"""Cross-scan engine tests — pivot extraction, confidence scoring, budget split."""


from user_scanner.core.confidence import Confidence
from user_scanner.core.cross_scan import (
    CrossScanConfig,
    _split_budget,
    _sweep_targets,
)
from user_scanner.core.pivots import Pivot, PivotKind, rank_usernames
from user_scanner.core.result import Result


def _taken(username, site, extra=None):
    r = Result.taken(extra=extra or {})
    return r.update(username=username, site_name=site, category="Social", is_email=False)


def test_cross_scan_config_defaults():
    cfg = CrossScanConfig()
    assert cfg.links == "all"
    assert cfg.emails == "verified"
    assert cfg.depth == 1
    assert cfg.sweep == 3


def test_rank_usernames_prefers_handles():
    pivots = [
        Pivot("linkedguy", PivotKind.LINK, "github", "bio"),
        Pivot("handleguy", PivotKind.HANDLE, "github", "login"),
        Pivot("verifiedguy", PivotKind.VERIFIED, "github", "verified_links"),
    ]
    ranked = rank_usernames(pivots)
    assert ranked[0] == "handleguy"


def test_split_budget_gives_both_kinds_a_slot():
    usernames, emails = _split_budget(2, 5, 5)
    assert usernames == 1
    assert emails == 1


def test_split_budget_zero_budget():
    assert _split_budget(0, 5, 5) == (0, 0)


def test_sweep_targets_respects_budget():
    pivots = [Pivot(f"user{i}", PivotKind.HANDLE, "github", "login") for i in range(10)]
    taken = _sweep_targets(pivots, 3)
    assert len(taken) == 3


def test_sweep_targets_zero_budget_returns_empty():
    pivots = [Pivot("user0", PivotKind.HANDLE, "github", "login")]
    assert _sweep_targets(pivots, 0) == []


def test_result_carries_confidence_in_extra():
    r = _taken("jane", "github", extra={"confidence": Confidence.CONFIRMED.value})
    assert r.extra["confidence"] == "confirmed"
    assert r.is_found() is True


def test_cross_scan_importable_from_compat():
    from services.user_scanner_compat import run_cross_scan_async

    assert callable(run_cross_scan_async)
