"""Live email-validator counts — no hardcoded "120+" anywhere in the UI.

Owner rule: counts come from the engine, never a literal. holehe-v2 discovers
its validators at runtime (181 today), so Home/Onboarding/Settings must use
`email_total_label()`.
"""

from __future__ import annotations

from pathlib import Path

from core import format as core_format
from core.state import state


def test_email_total_label_prefers_state():
    state.email_total_modules = 181
    try:
        assert core_format.email_total_label() == "181"
    finally:
        state.email_total_modules = 0


def test_email_total_label_discovers_and_caches():
    core_format._EMAIL_TOTAL_CACHE.clear()
    label = core_format.email_total_label()
    assert label, "the live engine count must not be empty"
    assert label != "120", "a stale hardcoded validator count is still in play"
    assert core_format._EMAIL_TOTAL_CACHE[:] == [int(label.replace(",", ""))]


def test_no_hardcoded_120_plus_in_screens():
    offenders = [
        str(path)
        for path in (
            Path("src/screens/home_screen.py"),
            Path("src/screens/onboarding_screen.py"),
        )
        if "120+" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"hardcoded email count returned: {offenders}"
