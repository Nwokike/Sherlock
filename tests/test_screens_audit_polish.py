"""Comprehensive tests for Screen-by-Screen audit polish, engine synchronization, and modern UI controls."""

from flet.components.component import Component, Renderer

from core.constants import APP_BUILD_NUMBER, APP_VERSION, MODE_EMAIL, MODE_USERNAME
from core.state import state
from screens.history_screen import HistoryScreen
from screens.home_screen import HomeScreen
from screens.onboarding_screen import _SLIDES, OnboardingScreen
from screens.results_screen import ResultsScreen
from screens.settings_screen import SettingsScreen
from screens.sites_screen import CATEGORY_TAGS, SitesScreen
from services.sherlock_service import SearchProgress, SiteResult
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethods, ControllerMethodsCtx


def _mount_screen(comp_fn):
    methods = ControllerMethods()
    renderer = Renderer()
    root_comp = renderer.render(
        lambda: ControllerMethodsCtx(methods, lambda: AppStateCtx(state, comp_fn))
    )

    def expand(node):
        if isinstance(node, Component):
            node.before_update()
            if getattr(node, "_b", None) is not None:
                yield from expand(node._b)
        elif isinstance(node, list):
            for item in node:
                yield from expand(item)
        else:
            yield node
            for ch in getattr(node, "controls", None) or []:
                yield from expand(ch)
            content = getattr(node, "content", None)
            if content is not None:
                yield from expand(content)
            for attr in (
                "actions",
                "leading",
                "trailing",
                "title",
                "subtitle",
                "label",
                "segments",
            ):
                val = getattr(node, attr, None)
                if val is not None:
                    yield from expand(val)

    return list(expand(root_comp))


def _extract_texts(nodes) -> list[str]:
    return [str(n.value) for n in nodes if hasattr(n, "value") and n.value is not None]


# ── 1. OnboardingScreen Tests ──────────────────────────────────────────


def test_onboarding_slide_copy_and_disclaimer():
    slide3 = _SLIDES[2]
    assert "PDF dossiers" in slide3["body"]
    assert "XMind mind maps" in slide3["body"]
    assert "Excel" not in slide3["body"]

    nodes = _mount_screen(lambda: OnboardingScreen())
    texts = _extract_texts(nodes)
    assert any("responsible OSINT use" in t for t in texts)
    assert any("Terms of Service" in t for t in texts)


# ── 2. HomeScreen Tests ────────────────────────────────────────────────


def test_home_screen_features_copy_and_quick_chips():
    # Username mode chips
    state.search_mode = MODE_USERNAME
    state.scan_depth = "all"
    state.nsfw_enabled = True
    state.recursive_search = False
    state.ignore_exclusions = False

    nodes = _mount_screen(lambda: HomeScreen())
    texts = _extract_texts(nodes)

    assert any("PDF dossiers" in t for t in texts)
    assert any("XMind mind maps" in t for t in texts)
    assert any("Scope: All 3.3k" in t for t in texts)
    assert any("Adult Sites: ON" in t for t in texts)
    assert any("Recursive: OFF" in t for t in texts)
    assert any("Disabled Sites: OFF" in t for t in texts)

    # Email mode chips
    state.search_mode = MODE_EMAIL
    state.email_method_filter = "all"
    state.use_curl_cffi = True
    state.no_password_recovery = False

    nodes_email = _mount_screen(lambda: HomeScreen())
    texts_email = _extract_texts(nodes_email)
    assert any("Method: All" in t for t in texts_email)
    assert any("Stealth: Chrome 124" in t for t in texts_email)
    assert any("PW Recovery: ON" in t for t in texts_email)


# ── 3. ResultsScreen Tests ─────────────────────────────────────────────


def test_results_screen_stable_stat_cards():
    state.reset_search()
    state.search_mode = MODE_USERNAME
    state.current_username = "alice"

    found_site = SiteResult(
        site_name="GitHub",
        url_user="https://github.com/alice",
        url_main="https://github.com",
        status="Claimed",
        http_status="200",
        query_time=0.4,
        tags=["coding"],
    )
    not_found_site = SiteResult(
        site_name="Reddit",
        url_user=None,
        url_main="https://reddit.com",
        status="Available",
        http_status="404",
        query_time=0.2,
        tags=["social"],
    )

    prog = SearchProgress(
        username="alice",
        total_sites=3302,
        checked_sites=2,
        found=[found_site],
        not_found=[not_found_site],
        errors=[],
        is_running=False,
    )
    state.search_progress = prog

    nodes = _mount_screen(lambda: ResultsScreen())
    texts = _extract_texts(nodes)
    # Stat cards should reflect 1 found, 1 not found, 3302 total
    assert "1" in texts
    assert "3302" in texts


# ── 4. SettingsScreen Tests ────────────────────────────────────────────


def test_settings_screen_all_engine_parameters_and_segmented_enrichment():
    state.enrichment_mode = "full"
    nodes = _mount_screen(lambda: SettingsScreen())
    texts = _extract_texts(nodes)

    # Check Build Number displayed in About card
    expected_version_str = f"Version {APP_VERSION} (Build {APP_BUILD_NUMBER})"
    assert any(expected_version_str in t for t in texts)

    # Check Email parameters
    assert any("Detection Method Filter" in t for t in texts)
    assert any("Stealth TLS (curl-cffi)" in t for t in texts)
    assert any("Email Concurrency" in t for t in texts)

    # Check Maigret scan parameters
    assert any("Recursive OSINT Search" in t for t in texts)
    assert any("Profile Data Extraction" in t for t in texts)
    assert any("Include Adult Sites" in t for t in texts)
    assert any("Include Disabled Sites" in t for t in texts)
    assert any("Request Retries" in t for t in texts)
    assert any("DNS Resolver Mode" in t for t in texts)
    assert any("Network Concurrency" in t for t in texts)

    # Check Enrichment SegmentedButton options rendered
    assert any("Basic" in t for t in texts)
    assert any("Full" in t for t in texts)


# ── 5. SitesScreen Tests ───────────────────────────────────────────────


def test_sites_screen_category_chips_and_empty_state():
    state.sites_cache = ["GitHub", "Twitter", "Reddit"]
    state.sites_tags_map = {
        "GitHub": ["coding"],
        "Twitter": ["social"],
        "Reddit": ["social"],
    }
    state.sites_total = 3
    state.sites_version += 1

    nodes = _mount_screen(lambda: SitesScreen())
    texts = _extract_texts(nodes)

    # Check category chip labels are rendered
    for _, chip_label in CATEGORY_TAGS:
        assert any(chip_label in t for t in texts)


# ── 6. HistoryScreen Tests ─────────────────────────────────────────────


def test_history_screen_render():
    state.history = [
        {
            "query": "torvalds",
            "mode": MODE_USERNAME,
            "found": 42,
            "total": 3302,
            "timestamp": "2026-09-01 12:00",
        },
        {
            "query": "user@example.com",
            "mode": MODE_EMAIL,
            "found": 5,
            "total": 121,
            "timestamp": "2026-09-01 11:30",
        },
    ]

    nodes = _mount_screen(lambda: HistoryScreen())
    texts = _extract_texts(nodes)

    assert any("torvalds" in t for t in texts)
    assert any("user@example.com" in t for t in texts)
    assert any("42/3302 matches" in t for t in texts)
