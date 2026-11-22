"""The Android manifest a foreground-service scan notification needs.

Mirrors the reference apps' res-guard tests: the specialUse service entry,
its subtype property, the permissions, the res_dir, and the five icon
densities must all be present or the shade notification silently fails.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DENSITIES = ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi")


def _pyproject() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def test_notification_icon_exists_in_every_density():
    for dpi in DENSITIES:
        icon = ROOT / "android_res" / f"drawable-{dpi}" / "ic_stat_sherlock.png"
        assert icon.is_file() and icon.stat().st_size > 0, f"missing {icon}"


def test_res_dir_points_at_our_android_resources():
    android = _pyproject()["tool"]["flet"]["android"]
    assert android.get("res_dir") == "android_res"


def test_foreground_service_declared_as_special_use():
    android = _pyproject()["tool"]["flet"]["android"]
    service = android["service"][
        "com.dexterous.flutterlocalnotifications.ForegroundService"
    ]
    assert service["foregroundServiceType"] == "specialUse"
    assert service["exported"] is False
    # The subtype is a <property> INSIDE the service (not application meta-data).
    assert service["property"]["android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"]
    assert "android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE" not in android["meta_data"]


def test_required_permissions_are_declared():
    perms = _pyproject()["tool"]["flet"]["android"]["permission"]
    for name in (
        "android.permission.FOREGROUND_SERVICE",
        "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
        "android.permission.POST_NOTIFICATIONS",
        "android.permission.WAKE_LOCK",
    ):
        assert perms.get(name) is True, f"{name} not declared"
