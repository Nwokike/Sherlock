"""AdMob service — banner and interstitial ads."""

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
    USE_TEST_IDS = True

    BANNER_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/9214589741"
    INTERSTITIAL_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/1033173712"

    BANNER_ID_ANDROID_PROD = ""
    INTERSTITIAL_ID_ANDROID_PROD = ""

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

    def get_standard_banner_ad(self) -> ft.Control | None:
        if not _HAS_ADS or not self._is_mobile():
            return None
        try:
            ad = fta.BannerAd(
                unit_id=self.banner_id,
                width=320,
                height=100,
                on_error=lambda e: None,
            )
            return ft.Container(
                content=ft.Column(
                    [
                        ad,
                        ft.Text(
                            "This app is 100% free. Ads help support the developer.",
                            size=11,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=5,
                ),
                width=320,
                alignment=ft.Alignment.CENTER,
                padding=ft.Padding(0, 10, 0, 10),
            )
        except Exception:
            return None

    async def preload_interstitial(self, on_close: Optional[Callable] = None):
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
        if self.interstitial:
            try:
                await self.interstitial.show()
                return True
            except Exception:
                return False
        return False
