"""AdMob service — banner and interstitial ads with UMP consent."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

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
        self._on_close: Callable | None = None
        self._can_request_ads: bool = True
        self._consent_manager = None
        self._is_shutting_down: bool = False

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

    # ── Consent Management (UMP) ──────────────────────────────────────────

    async def gather_consent(self):
        """Run UMP consent flow. Only shows UI in regulated regions (EEA/UK)."""
        if not _HAS_ADS:
            self._can_request_ads = True
            return
        try:
            if not self.page.platform.is_mobile():
                self._can_request_ads = True
                return
        except Exception:
            self._can_request_ads = True
            return
        try:
            self._consent_manager = fta.ConsentManager()
            if hasattr(self.page, "services") and self._consent_manager not in self.page.services:
                self.page.services.append(self._consent_manager)
            await self._consent_manager.request_consent_info_update()
            await self._consent_manager.load_and_show_consent_form_if_required()
            self._can_request_ads = await self._consent_manager.can_request_ads()
        except Exception as e:
            logger.warning("UMP consent flow failed, defaulting to allow ads: %s", e)
            self._can_request_ads = True

    async def show_privacy_options(self):
        """Show privacy options form if required by regulation (GDPR)."""
        if not self._consent_manager:
            return
        try:
            status = await self._consent_manager.get_privacy_options_requirement_status()
            if status == fta.PrivacyOptionsRequirementStatus.REQUIRED:
                await self._consent_manager.show_privacy_options_form()
                self._can_request_ads = await self._consent_manager.can_request_ads()
        except Exception:
            pass

    def get_banner_ad(self) -> ft.Control:
        """Return a banner ad control, or empty container on desktop."""
        if not _HAS_ADS or not self._is_mobile() or not self._can_request_ads:
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

    async def preload_interstitial(self, on_close: Callable | None = None):
        """Pre-load an interstitial ad for later display."""
        self._on_close = on_close
        if not _HAS_ADS or not self._is_mobile() or not self._can_request_ads:
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
        if not self._is_shutting_down:
            await self.preload_interstitial(on_close=self._on_close)

    async def show_interstitial(self) -> bool:
        """Show a preloaded interstitial. Returns True if shown."""
        if self.interstitial and self._can_request_ads:
            try:
                await self.interstitial.show()
                return True
            except Exception:
                return False
        return False

    async def close(self):
        self._is_shutting_down = True
        self.interstitial = None
