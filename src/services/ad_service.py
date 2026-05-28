"""AdMob service — banner and interstitial ads.

Direct port of SpanInsight's production AdService pattern.
Uses test Ad IDs until Play Store launch.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

import flet as ft

logger = logging.getLogger(__name__)

try:
    import flet_ads as fta

    _HAS_ADS = True
except ImportError:
    _HAS_ADS = False


class AdService:
    """Manages AdMob banner and interstitial ads."""

    USE_TEST_IDS = False

    BANNER_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/9214589741"
    INTERSTITIAL_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/1033173712"

    BANNER_ID_ANDROID_PROD = "ca-app-pub-5679949845754640/5131365762"
    INTERSTITIAL_ID_ANDROID_PROD = "ca-app-pub-5679949845754640/2758003779"

    def __init__(self, page: ft.Page):
        self.page = page
        self.interstitial = None
        self._on_close: Optional[Callable] = None

    @property
    def banner_id(self) -> str:
        if self.USE_TEST_IDS:
            return self.BANNER_ID_ANDROID_TEST
        return self.BANNER_ID_ANDROID_PROD

    @property
    def interstitial_id(self) -> str:
        if self.USE_TEST_IDS:
            return self.INTERSTITIAL_ID_ANDROID_TEST
        return self.INTERSTITIAL_ID_ANDROID_PROD

    def _is_mobile(self) -> bool:
        try:
            return self.page.platform.is_mobile()
        except Exception:
            return False

    def get_banner_ad(self) -> ft.Control:
        """Return a banner ad control, or empty container on desktop."""
        if not _HAS_ADS or not self._is_mobile():
            return ft.Container(width=0, height=0)
        try:
            ad = fta.BannerAd(
                unit_id=self.banner_id,
                width=320,
                height=50,
                on_error=lambda e: None,
            )
            return ft.Container(
                content=ad,
                width=320,
                height=50,
                alignment=ft.Alignment.CENTER,
            )
        except Exception:
            return ft.Container(width=0, height=0)

    async def preload_interstitial(self, on_close: Optional[Callable] = None):
        """Pre-load an interstitial ad for later display."""
        self._on_close = on_close
        if not _HAS_ADS or not self._is_mobile():
            return
        try:
            self.interstitial = fta.InterstitialAd(
                unit_id=self.interstitial_id,
                on_load=lambda e: None,
                on_error=lambda e: None,
                on_close=self._handle_close,
            )
        except Exception:
            self.interstitial = None

    async def _handle_close(self, e):
        if self._on_close:
            if asyncio.iscoroutinefunction(self._on_close):
                await self._on_close()
            else:
                self._on_close()
        await self.preload_interstitial(on_close=self._on_close)

    async def show_interstitial(self) -> bool:
        """Show a preloaded interstitial. Returns True if shown."""
        if self.interstitial:
            try:
                await self.interstitial.show()
                return True
            except Exception:
                return False
        return False

    async def show_rewarded_interstitial(self, on_close: Callable) -> bool:
        """Show a rewarded interstitial ad, triggering on_close when closed."""
        if not _HAS_ADS or not self._is_mobile():
            if asyncio.iscoroutinefunction(on_close):
                await on_close()
            else:
                on_close()
            return True

        try:
            async def _show(e):
                await e.control.show()

            async def _close(e):
                self._active_rewarded_ad = None
                if asyncio.iscoroutinefunction(on_close):
                    await on_close()
                else:
                    on_close()

            self._active_rewarded_ad = fta.InterstitialAd(
                unit_id=self.interstitial_id,
                on_load=lambda e: self.page.run_task(_show, e),
                on_close=lambda e: self.page.run_task(_close, e),
                on_error=lambda e: logger.error(
                    "Rewarded Interstitial error: %s", e.data
                ),
            )
            return True
        except Exception as err:
            logger.error("Failed to trigger rewarded interstitial: %s", err)
            if asyncio.iscoroutinefunction(on_close):
                await on_close()
            else:
                on_close()
            return False
