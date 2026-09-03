"""AdMob service — banner and interstitial ads with UMP consent.

Registration model (verified against flet 0.86.5 source):
- ``InterstitialAd`` and ``ConsentManager`` are ``ft.Service`` objects.
  They self-register with the page's ServiceRegistry at construction time,
  but ONLY when a page context is active (``Service.init()`` suppresses the
  ``RuntimeError`` when ``ft.context.page`` is unset). All construction in
  this module happens inside ``page.run_task`` coroutines or event handlers,
  both of which carry the page context (``run_task`` sets the context var
  before ``run_coroutine_threadsafe``, and the Handle created by
  ``call_soon_threadsafe`` captures the caller's context — verified
  empirically against Python 3.14).
- Flet's session runs ``unregister_services()`` after EVERY event and drops
  any service whose refcount fell to <=3. ``page.services.append(...)`` is
  the documented keep-alive (official flet-ads consent example and
  spaninsight both use it), so the app-lifetime ConsentManager and the
  in-flight interstitials are appended there and removed once spent.

No silent failures: every gate, error, and skip reason is logged (project
policy — we log every error, we never swallow).
"""

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

    # Flip to True ONLY for a local diagnostic build: Google's test units are
    # served to every device, so a filled test banner proves the whole
    # pipeline (build → control → native request) and isolates "no fill" to
    # the production unit / AdMob console side. Never ship with True.
    USE_TEST_IDS = False

    INTERSTITIAL_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/1033173712"
    INTERSTITIAL_ID_ANDROID_PROD = "ca-app-pub-5679949845754640/2758003779"

    def __init__(self, page: ft.Page):
        self.page = page
        self.interstitial = None
        self._shown_interstitial = None
        self._on_close: Callable | None = None
        self._can_request_ads: bool = True
        self._consent_manager = None
        self._privacy_options_required: bool | None = None
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
            logger.info("AdService: flet_ads not available — ads disabled this build")
            self._can_request_ads = False
            return
        if not self._is_mobile():
            logger.info("AdService: non-mobile platform — consent flow skipped")
            self._can_request_ads = True
            return
        try:
            self._consent_manager = fta.ConsentManager()
            # Keep-alive: Flet's refcount GC unregisters unreferenced services
            # after every event (page.py ServiceRegistry.unregister_services).
            if self._consent_manager not in self.page.services:
                self.page.services.append(self._consent_manager)
            await self._consent_manager.request_consent_info_update()
            await self._consent_manager.load_and_show_consent_form_if_required()
            self._can_request_ads = await self._consent_manager.can_request_ads()
            try:
                status = await self._consent_manager.get_privacy_options_requirement_status()
                self._privacy_options_required = (
                    status == fta.PrivacyOptionsRequirementStatus.REQUIRED
                )
                logger.info("AdService: consent status=%s can_request_ads=%s", status, self._can_request_ads)
            except Exception as exc:
                logger.warning("AdService: privacy-requirement probe failed: %s", exc)
            if not self._can_request_ads:
                logger.warning("AdService: UMP says ads cannot be requested — interstitials disabled this session")
        except Exception as e:
            logger.warning("AdService: UMP consent flow failed, defaulting to allow ads: %s", e)
            self._can_request_ads = True

    async def show_privacy_options(self) -> str:
        """Open the UMP privacy options form if regulation requires it.

        Returns an honest outcome for the UI to surface — never a silent
        no-op:
        * ``"form_shown"`` — the form opened.
        * ``"not_required"`` — region is unregulated; there is nothing to
          manage, but the user is told exactly that.
        * ``"no_manager"`` — consent service never started (ads unavailable).
        * ``"error:<message>"`` — something failed; details also logged.
        """
        if not self._consent_manager:
            logger.warning("AdService: privacy options requested but consent manager is missing")
            return "no_manager"
        try:
            status = await self._consent_manager.get_privacy_options_requirement_status()
        except Exception as e:
            logger.warning("AdService: privacy options status check failed: %s", e)
            return f"error:{e}"
        if status != fta.PrivacyOptionsRequirementStatus.REQUIRED:
            logger.info("AdService: privacy options form not required (status=%s)", status)
            return "not_required"
        try:
            await self._consent_manager.show_privacy_options_form()
            self._can_request_ads = await self._consent_manager.can_request_ads()
            logger.info("AdService: privacy options form shown, can_request_ads=%s", self._can_request_ads)
            return "form_shown"
        except Exception as e:
            logger.warning("AdService: privacy options form failed to open: %s", e)
            return f"error:{e}"

    # ── Interstitial Ads ──────────────────────────────────────────────────

    async def preload_interstitial(self, on_close: Callable | None = None):
        """Pre-load an interstitial ad for later display."""
        self._on_close = on_close
        if self._is_shutting_down:
            logger.info("AdService: preload skipped — shutting down")
            return
        if not _HAS_ADS or not self._is_mobile():
            logger.info("AdService: preload skipped — flet_ads missing or non-mobile")
            return
        if not self._can_request_ads:
            logger.info("AdService: preload skipped — consent gate closed")
            return
        try:
            ad = fta.InterstitialAd(
                unit_id=self.interstitial_id,
                on_load=lambda e: logger.info("InterstitialAd loaded"),
                on_error=lambda e: logger.warning(
                    "InterstitialAd load error: %s", getattr(e, "data", e)
                ),
                on_close=self._handle_close,
            )
        except Exception as exc:
            logger.warning("AdService: failed to construct InterstitialAd: %s", exc)
            return
        self.interstitial = ad
        if ad not in self.page.services:
            self.page.services.append(ad)
        logger.info("AdService: interstitial preloaded (unit=%s)", self.interstitial_id)

    async def _handle_close(self, e):
        if self._shown_interstitial is not None:
            _release_service(self.page.services, self._shown_interstitial)
            self._shown_interstitial = None
        if self._on_close:
            if asyncio.iscoroutinefunction(self._on_close):
                await self._on_close()
            else:
                self._on_close()

    async def show_interstitial(self) -> bool:
        """Show an interstitial — preloaded when ready, else a fresh
        self-loading instance (the same proven pattern as spaninsight's
        fallback path). Returns True when a show was triggered."""
        if not _HAS_ADS or not self._is_mobile() or not self._can_request_ads:
            logger.info(
                "AdService: interstitial skipped — ads unavailable or consent gate closed"
            )
            return False
        if self.interstitial is not None:
            ad_to_show = self.interstitial
            self.interstitial = None
            # Strong ref until on_close: without it Flet's service GC can
            # unregister the ad mid-display (it runs after every UI event).
            self._shown_interstitial = ad_to_show
            try:
                await ad_to_show.show()
                logger.info("InterstitialAd shown (preloaded instance)")
                return True
            except Exception as e:
                logger.warning("AdService: preloaded interstitial show failed: %s", e)
                self._shown_interstitial = None
                _release_service(self.page.services, ad_to_show)
                # The finally block restocks the next preloaded ad; don't also
                # queue a fresh one — one failure must not produce two live
                # ads (back-to-back interstitials for one search).
                return False
            finally:
                if not self._is_shutting_down:
                    await self.preload_interstitial(on_close=self._on_close)

        # Fresh self-loading instance — constructed here so the service
        # registers under the event-handler page context, then shows itself
        # the moment the native side finishes loading (spaninsight pattern).
        try:
            async def _show(e):
                await e.control.show()
                logger.info("InterstitialAd shown (fresh instance)")

            ad = fta.InterstitialAd(
                unit_id=self.interstitial_id,
                on_load=lambda e: self.page.run_task(_show, e),
                on_error=lambda e: logger.warning(
                    "InterstitialAd load error: %s", getattr(e, "data", e)
                ),
                on_close=self._handle_close,
            )
        except Exception as e:
            logger.warning("AdService: fresh interstitial construction failed: %s", e)
            return False
        self._shown_interstitial = ad
        if ad not in self.page.services:
            self.page.services.append(ad)
        logger.info("AdService: fresh interstitial queued — it will show on load")
        return True

    async def close(self):
        self._is_shutting_down = True
        for ad in (self.interstitial, self._shown_interstitial):
            if ad is not None:
                _release_service(self.page.services, ad)
        self.interstitial = None
        self._shown_interstitial = None


def _release_service(services: list, item) -> None:
    """Drop a spent service from the keep-alive list so Flet's service GC can
    unregister it; harmless if it is already gone."""
    try:
        services.remove(item)
    except ValueError:
        pass
