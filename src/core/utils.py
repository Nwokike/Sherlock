"""Shared utilities — banner ads, snackbar helpers."""

from __future__ import annotations

import logging

import flet as ft

logger = logging.getLogger(__name__)


def get_banner_ad(unit_id: str, width: int = 320, height: int = 50) -> ft.Control:
    """Instantiate flet_ads.BannerAd safely.

    If flet_ads fails to load gracefully returns an empty ft.Container()
    instead of crashing the view.
    """
    try:
        import flet_ads as fta

        return fta.BannerAd(unit_id=unit_id, width=width, height=height)
    except Exception as e:
        logger.warning("Failed to load BannerAd (using safe fallback Container): %s", e)
        return ft.Container()
