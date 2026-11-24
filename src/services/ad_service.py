"""AdMob service — banner and interstitial ads with UMP consent.

Registration model (verified against the installed flet 1.0.4 source):
- ``InterstitialAd`` and ``ConsentManager`` are ``ft.Service`` objects.
  ``Service.__post_init__`` self-registers with the page's ServiceRegistry
  (``flet/controls/services/service.py:54``), but only when a page context is
  active. All construction here happens inside ``page.run_task`` coroutines
  or event handlers, both of which carry that context.
- Flet's session runs ``unregister_services()`` after EVERY event and drops
  any service whose refcount fell to <=3 on Python 3.14
  (``flet/controls/page.py:251-265``). ``page.services.append(...)`` is the
  keep-alive, so the app-lifetime ConsentManager and the live interstitial
  are appended there and removed once spent.

Interstitial model (verified against the shipped Dart,
``flutter/flet_ads/lib/src/interstitial.dart``):
- There is ONE ``static InterstitialAd? _interstitialAd`` (line 10). Every
  instance's ``init()`` calls ``InterstitialAd.load`` and on load OVERWRITES
  that static (line 44). ``show()`` is ``_interstitialAd?.show()`` (line 58):
  it displays whichever ad loaded LAST, and silently no-ops when null.
- Therefore this service keeps exactly ONE live instance at a time. Two
  instances would show an ad whose callbacks belong to the other control,
  leak keep-alive refs, and report a show that never happened.
- ``onAdFailedToShowFullScreenContent`` fires ``error`` and disposes, and
  does NOT fire ``close`` (lines 30-33), so the error path must release and
  restock too.
- A real display is confirmed by ``open`` / ``impression`` (lines 28-29).
  The cooldown is stamped ONLY on that confirmation, so a no-op or failed
  show never burns the window.

Owner's revenue rules (all his apps):
- Ads are the income. Consent is gathered and the form is shown where
  regulation requires it, but the answer NEVER gates serving: a user who
  rejects still gets ads.
- Every major action fires an interstitial; the cooldown between them is
  one hour; concurrent major actions share the one already shown.

No silent failures: every gate, error, and skip reason is logged (project
policy — we log every error, we never swallow).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import flet as ft

from components.banner_ad import clear_banner_pool

logger = logging.getLogger(__name__)

# The one AdService instance for this session. Lives HERE, not in the
# entry module: when the entry runs as `__main__`, `from main import ...`
# re-imports a SECOND module object, so a dict kept in the entry module is
# invisible to UI modules — and the export/history/graph interstitials would
# silently never fire (lost revenue).
AD_SERVICE_REF: dict = {}

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

    # Owner policy: one interstitial per hour of active use. Every major
    # action still fires one — the cooldown only stops back-to-back stacking
    # (a search immediately followed by an export), which AdMob treats as a
    # violation risk. Nothing is discarded: the preloaded ad simply waits.
    INTERSTITIAL_MIN_INTERVAL_SEC = 3600.0

    # A show that produces neither an impression nor an error is a native
    # no-op (the static ad was null). Without this watchdog the slot would
    # stay "in flight" forever and every later action would be skipped.
    SHOW_CONFIRM_TIMEOUT_SEC = 10.0
    # A queued show waits for on_load. If the native request hangs and fires
    # neither on_load nor on_error, _show_pending would wedge EVERY later
    # major action for the session — persistent income loss. Recover the slot.
    LOAD_CONFIRM_TIMEOUT_SEC = 15.0

    def __init__(self, page: ft.Page):
        self.page = page
        # The ONE live interstitial (loading, loaded, or on screen).
        self.interstitial = None
        # The instance a show was last attempted on (telemetry + close path).
        self._shown_interstitial = None
        self._on_close: Callable | None = None
        # Telemetry only. Owner rule: the consent answer never gates serving,
        # so nothing in the show/preload path reads this.
        self._can_request_ads: bool = True
        self._consent_manager = None
        self._privacy_options_required: bool | None = None
        self._is_shutting_down: bool = False
        # None = never shown this session. NOT 0.0: time.monotonic() can be
        # small right after boot (container runners), and a 0.0 sentinel would
        # then read as "shown 0.7s ago" and block every show.
        self._last_interstitial_at: float | None = None
        # Per-instance lifecycle, all reset when a new instance is created.
        self._ad_generation: int = 0
        self._ad_loaded: bool = False
        self._show_pending: bool = False
        self._show_in_flight: bool = False
        self._impression_recorded: bool = False

    @property
    def interstitial_id(self) -> str:
        if self.USE_TEST_IDS:
            return self.INTERSTITIAL_ID_ANDROID_TEST
        return self.INTERSTITIAL_ID_ANDROID_PROD

    @property
    def can_request_ads(self) -> bool:
        """Personalization verdict for the Settings row.

        Telemetry-only by owner rule: the consent answer NEVER gates serving.
        """
        return self._can_request_ads

    def _is_mobile(self) -> bool:
        try:
            return self.page.platform.is_mobile()
        except Exception:
            return False

    # ── Consent Management (UMP) ──────────────────────────────────────────

    async def gather_consent(self):
        """Run the UMP consent flow. Only shows UI in regulated regions.

        The result is recorded for telemetry and NEVER gates ad serving:
        a user who rejects consent still gets ads (owner rule, all his apps).
        """
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
                status = (
                    await self._consent_manager.get_privacy_options_requirement_status()
                )
                self._privacy_options_required = (
                    status == fta.PrivacyOptionsRequirementStatus.REQUIRED
                )
            except Exception as exc:
                logger.warning("AdService: privacy-requirement probe failed: %s", exc)
            # Logged, not enforced: serving continues either way.
            logger.info(
                "AdService: consent recorded (can_request_ads=%s) — serving ads "
                "regardless, per owner policy",
                self._can_request_ads,
            )
        except Exception as e:
            logger.warning(
                "AdService: UMP consent flow failed, serving ads anyway: %s", e
            )
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
            logger.warning(
                "AdService: privacy options requested but consent manager is missing"
            )
            return "no_manager"
        try:
            status = (
                await self._consent_manager.get_privacy_options_requirement_status()
            )
        except Exception as e:
            logger.warning("AdService: privacy options status check failed: %s", e)
            return f"error:{e}"
        if status != fta.PrivacyOptionsRequirementStatus.REQUIRED:
            logger.info(
                "AdService: privacy options form not required (status=%s)", status
            )
            return "not_required"
        try:
            await self._consent_manager.show_privacy_options_form()
            self._can_request_ads = await self._consent_manager.can_request_ads()
            logger.info(
                "AdService: privacy options form shown (can_request_ads=%s, "
                "serving continues regardless)",
                self._can_request_ads,
            )
            return "form_shown"
        except Exception as e:
            logger.warning("AdService: privacy options form failed to open: %s", e)
            return f"error:{e}"

    # ── Interstitial Ads ──────────────────────────────────────────────────

    def _new_interstitial(self):
        """Create THE one live instance, with generation-bound callbacks.

        Every callback captures its generation and the ad object itself, so a
        late event from a spent instance can never release or restock the
        current one (the Dart static makes cross-instance events routine).
        """
        self._ad_generation += 1
        gen = self._ad_generation
        self._ad_loaded = False
        self._show_pending = False
        self._show_in_flight = False
        self._impression_recorded = False
        try:
            ad = fta.InterstitialAd(
                unit_id=self.interstitial_id,
                on_load=lambda e, g=gen: self._on_ad_loaded(g),
                on_error=lambda e, g=gen: self._on_ad_error(g, e),
                on_open=lambda e, g=gen: self._on_ad_confirmed(g, "open"),
                on_impression=lambda e, g=gen: self._on_ad_confirmed(g, "impression"),
                on_close=self._handle_close,
            )
        except Exception as exc:
            logger.warning("AdService: failed to construct InterstitialAd: %s", exc)
            return None
        try:
            if ad not in self.page.services:
                self.page.services.append(ad)
        except Exception as exc:
            logger.warning("AdService: could not register interstitial: %s", exc)
            return None
        self.interstitial = ad
        return ad

    def _on_ad_loaded(self, gen: int) -> None:
        if gen != self._ad_generation or self.interstitial is None:
            return
        self._ad_loaded = True
        logger.info("InterstitialAd loaded (generation %d)", gen)
        if self._show_pending:
            self._show_pending = False
            self._begin_show(self.interstitial)

    def _on_ad_confirmed(self, gen: int, kind: str) -> None:
        """A real display happened — this is what stamps the cooldown."""
        if gen != self._ad_generation:
            return
        if not self._impression_recorded:
            self._impression_recorded = True
            self._last_interstitial_at = time.monotonic()
            logger.info(
                "InterstitialAd %s confirmed — next interstitial in %.0f min",
                kind,
                self.INTERSTITIAL_MIN_INTERVAL_SEC / 60.0,
            )

    def _on_ad_error(self, gen: int, e) -> None:
        """Failed load OR failed show (Dart fires 'error' for both, no close)."""
        logger.warning("InterstitialAd error: %s", getattr(e, "data", e))
        if gen != self._ad_generation:
            return
        ad = self.interstitial
        self._release_ad(ad)
        self._restock()

    def _release_ad(self, ad) -> None:
        if ad is None:
            return
        _release_service(self.page.services, ad)
        if self.interstitial is ad:
            self.interstitial = None
        if self._shown_interstitial is ad:
            self._shown_interstitial = None
        self._ad_loaded = False
        self._show_pending = False
        self._show_in_flight = False

    def _restock(self) -> None:
        if self._is_shutting_down or not _HAS_ADS or not self._is_mobile():
            return
        if self.interstitial is None:
            self._new_interstitial()

    def _begin_show(self, ad) -> None:
        """Invoke show() and arm the no-op watchdog. Never blocks the action."""
        self._shown_interstitial = ad
        self._show_in_flight = True
        try:
            self.page.run_task(self._show_and_confirm, ad, self._ad_generation)
        except Exception as exc:
            logger.warning("AdService: could not schedule interstitial show: %s", exc)
            self._release_ad(ad)
            self._restock()

    async def _show_and_confirm(self, ad, gen: int) -> None:
        try:
            await ad.show()
        except Exception as exc:
            logger.warning("AdService: interstitial show failed: %s", exc)
            if gen == self._ad_generation:
                self._release_ad(ad)
                self._restock()
            return
        # show() returning does NOT mean an ad appeared: the Dart call is
        # `_interstitialAd?.show()`. Wait for the impression/open confirmation.
        try:
            await asyncio.sleep(self.SHOW_CONFIRM_TIMEOUT_SEC)
        except asyncio.CancelledError:
            return
        if gen != self._ad_generation or self._impression_recorded:
            return
        logger.warning(
            "AdService: interstitial show produced no impression — native no-op; "
            "releasing the slot so the next action can earn"
        )
        self._release_ad(ad)
        self._restock()

    async def preload_interstitial(self, on_close: Callable | None = None):
        """Pre-load THE interstitial for the next major action."""
        if on_close is not None:
            self._on_close = on_close
        if self._is_shutting_down:
            logger.info("AdService: preload skipped — shutting down")
            return
        if not _HAS_ADS or not self._is_mobile():
            logger.info("AdService: preload skipped — flet_ads missing or non-mobile")
            return
        if self.interstitial is not None:
            # One instance only: a second would overwrite the Dart static and
            # steal the first one's callbacks.
            return
        if self._new_interstitial() is not None:
            logger.info(
                "AdService: interstitial preloaded (unit=%s)", self.interstitial_id
            )

    async def _handle_close(self, e):
        ad = getattr(e, "control", None) or self._shown_interstitial
        self._release_ad(ad)
        self._restock()
        if self._on_close:
            if asyncio.iscoroutinefunction(self._on_close):
                await self._on_close()
            else:
                self._on_close()

    async def show_interstitial(self) -> bool:
        """Fire an interstitial for a major action. Returns True when a show
        was triggered (queued counts — it displays the moment it loads).

        Owner rule: no consent gate. A rejection never stops an ad.
        """
        if not _HAS_ADS or not self._is_mobile():
            logger.info(
                "AdService: interstitial skipped — ads unavailable on this build"
            )
            return False
        if self._is_shutting_down:
            return False
        # Concurrent major actions share the one already going out.
        if self._show_pending or self._show_in_flight:
            logger.info("AdService: interstitial skipped — one is already on its way")
            return False
        if self._last_interstitial_at is not None:
            elapsed = time.monotonic() - self._last_interstitial_at
            if elapsed < self.INTERSTITIAL_MIN_INTERVAL_SEC:
                logger.info(
                    "AdService: interstitial skipped — %.0f min since the last one "
                    "(cooldown %.0f min)",
                    elapsed / 60.0,
                    self.INTERSTITIAL_MIN_INTERVAL_SEC / 60.0,
                )
                # Deliberately NOT stamped: a burst must not keep deferring
                # the window, and a skip is not an impression.
                return False

        if self.interstitial is not None and self._ad_loaded:
            self._begin_show(self.interstitial)
            return True

        # Not loaded yet (or nothing preloaded): queue the show on load rather
        # than calling show() on an ad that would silently no-op.
        if self.interstitial is None and self._new_interstitial() is None:
            return False
        self._show_pending = True
        self._shown_interstitial = self.interstitial
        logger.info("AdService: fresh interstitial queued — it will show on load")
        # A hung native request that fires neither on_load nor on_error must
        # not wedge every later major action for the session.
        try:
            self.page.run_task(self._watch_load, self._ad_generation)
        except Exception as exc:
            logger.warning("AdService: could not arm load watchdog: %s", exc)
        return True

    async def _watch_load(self, gen: int) -> None:
        try:
            await asyncio.sleep(self.LOAD_CONFIRM_TIMEOUT_SEC)
        except asyncio.CancelledError:
            return
        if gen != self._ad_generation or not self._show_pending:
            return
        logger.warning(
            "AdService: interstitial load produced no callback — releasing the "
            "slot so the next major action can earn"
        )
        self._release_ad(self.interstitial)
        self._restock()

    async def close(self):
        self._is_shutting_down = True
        for ad in (self.interstitial, self._shown_interstitial):
            if ad is not None:
                _release_service(self.page.services, ad)
        self.interstitial = None
        self._shown_interstitial = None
        self._ad_loaded = False
        self._show_pending = False
        self._show_in_flight = False
        # Banners live in a module pool independent of this service; torn-down
        # pages must not keep their controls (and their baked-in theme colors).
        clear_banner_pool()


def _release_service(services: list, item) -> None:
    """Drop a spent service from the keep-alive list so Flet's service GC can
    unregister it; harmless if it is already gone."""
    try:
        services.remove(item)
    except ValueError:
        pass


def fire_major_action_interstitial() -> None:
    """Fire the interstitial for a major action — the owner's revenue rule.

    Every major action calls this; the service's own cooldown decides whether
    an ad actually goes out, so concurrent actions share one. Resolves the
    session's AdService lazily so UI modules without a controller reference
    can use the same single entry point. Never raises into the caller and
    never blocks the action.
    """
    try:
        from core.tasks import spawn

        service = AD_SERVICE_REF.get("service")
        if service is None:
            return
        spawn(service.show_interstitial(), name="interstitial")
    except Exception as exc:
        logger.warning("AdService: major-action interstitial failed: %s", exc)
