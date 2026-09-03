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
    """Manages AdMob interstitial ads and UMP consent."""

    USE_TEST_IDS = False

    INTERSTITIAL_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/1033173712"
    INTERSTITIAL_ID_ANDROID_PROD = "ca-app-pub-5679949845754640/2758003779"

    def __init__(self, page: ft.Page):
        self.page = page
        self.interstitial = None
        self._on_close: Callable | None = None
        self._can_request_ads: bool = True
        self._consent_manager = None
        self._is_shutting_down: bool = False

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
            status = (
                await self._consent_manager.get_privacy_options_requirement_status()
            )
            if status == fta.PrivacyOptionsRequirementStatus.REQUIRED:
                await self._consent_manager.show_privacy_options_form()
                self._can_request_ads = await self._consent_manager.can_request_ads()
        except Exception:
            pass

    async def preload_interstitial(self, on_close: Callable | None = None):
        """Pre-load an interstitial ad for later display.

        Service construction itself registers the ad with the page's service
        registry (Flet's supported path) — appending to `page.services` is
        both redundant and harmful: that list is never serialized and holds
        references that defeat Flet's refcount GC of spent single-use ads.
        """
        self._on_close = on_close
        if self._is_shutting_down:
            return
        if not _HAS_ADS or not self._is_mobile() or not self._can_request_ads:
            return
        try:
            req = fta.AdRequest(
                keywords=[
                    "osint",
                    "investigation",
                    "search",
                    "security",
                    "technology",
                    "privacy",
                    "developer",
                    "software",
                ]
            )
            self.interstitial = fta.InterstitialAd(
                unit_id=self.interstitial_id,
                request=req,
                on_load=lambda e: logger.info("InterstitialAd loaded successfully!"),
                on_error=lambda e: logger.warning(
                    "InterstitialAd load error: %s", getattr(e, "data", e)
                ),
                on_close=self._handle_close,
            )
        except Exception as exc:
            logger.warning("Failed to construct InterstitialAd: %s", exc)
            self.interstitial = None

    async def _handle_close(self, e):
        if self._on_close:
            if asyncio.iscoroutinefunction(self._on_close):
                await self._on_close()
            else:
                self._on_close()

    async def show_interstitial(self) -> bool:
        """Show a preloaded interstitial — on every search for maximum revenue.

        Per flet_ads docs an InterstitialAd instance is single-use. We detach
        the reference before showing (so GC can reclaim it after close) and
        preload exactly one replacement — never more.
        """
        if self.interstitial and self._can_request_ads:
            ad_to_show = self.interstitial
            self.interstitial = None
            try:
                await ad_to_show.show()
                return True
            except Exception as e:
                logger.warning("Interstitial show failed: %s", e)
                return False
            finally:
                if not self._is_shutting_down:
                    await self.preload_interstitial(on_close=self._on_close)
        return False

    async def close(self):
        self._is_shutting_down = True
        self.interstitial = None
