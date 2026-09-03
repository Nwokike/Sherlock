"""Observable application state."""

from __future__ import annotations

import flet as ft

from core.constants import MODE_USERNAME

_ENRICHMENT_CAP = 200


@ft.observable
class AppState:
    # --- Top-level flags ---
    is_loading: bool = False
    is_searching: bool = False
    is_first_launch: bool = True
    has_accepted_terms: bool = False
    # Device connectivity (ft.Connectivity service). Only the connectivity
    # handlers in main.py mutate this — UI gates (offline banner, search
    # gate) re-render reactively when it flips.
    is_online: bool = True

    # --- Search mode ---
    # "username" (sherlock-project) or "email" (holehe)
    search_mode: str = MODE_USERNAME

    # --- Current search ---
    current_username: str = ""
    active_username: str = ""
    search_targets: list[str] | None = None
    target_results: dict | None = None  # {username: SearchProgress}
    search_progress: object | None = None  # SearchProgress | None — keep untyped
    progress_version: int = 0
    search_error: str | None = None

    # --- Theme ---
    theme_mode: ft.ThemeMode = ft.ThemeMode.LIGHT

    # --- Last results ---
    last_results: dict | None = None
    last_results_username: str = ""
    total_sites_checked: int = 0
    found_count: int = 0
    not_found_count: int = 0
    error_count: int = 0

    # --- Email OSINT results ---
    # Stores list of holehe result dicts for the last email search
    email_results: list | None = None
    email_results_address: str = ""
    email_found_count: int = 0
    email_not_found_count: int = 0
    email_rate_limited_count: int = 0
    email_unavailable_count: int = 0
    email_total_modules: int = 0

    # --- Profile enrichment ---
    # {url_or_site_name: {field: value, ...}} from socid-extractor
    # Capped at _ENRICHMENT_CAP via set_enrichment() to avoid long-session growth.
    enrichments: dict | None = None

    # --- History & Result Cache ---
    history: list | None = None
    # {f"{mode}:{query.lower()}": {found: [...], not_found: [...], errors: [...], ...}}
    results_cache: dict | None = None

    # --- Settings state ---
    nsfw_enabled: bool = True
    ignore_exclusions: bool = False
    timeout: int = 15
    email_timeout: int = 10
    email_concurrency: int = 12
    email_only_found: bool = False
    email_method_filter: str = "all"
    proxy_url: str = ""
    enrichment_mode: str = "full"
    no_password_recovery: bool = False
    selected_sites: list[str] | None = None
    use_local_db: bool = True
    custom_manifest: str = ""
    scan_depth: str = "all"
    recursive_search: bool = False
    extract_info: bool = True
    max_connections: int = 50
    retries: int = 0
    dns_resolver: str = "threaded"
    use_curl_cffi: bool = True
    safe_search: bool = False

    # --- Site database ---
    # Total sites in the active site database (0 until first load lands).
    sites_total: int = 0
    # Bumped after every successful site-database load so screens
    # subscribed to it (e.g. SitesScreen) re-render when names arrive.
    sites_version: int = 0
    # Warm copy of site names persisted to storage — lets the Sites
    # screen render before (or if) a fresh load finishes.
    sites_cache: list | None = None
    # Map of site_name -> list of category/country tags
    sites_tags_map: dict | None = None
    # Inverted index {tag -> [site names]} built after each DB load —
    # powers O(1) category chip filtering in SitesScreen.
    sites_tag_index: dict | None = None

    # --- Update & Announcement ---
    update_available: bool = False
    update_data: dict | None = None

    def __init__(self):
        # Collections must be assigned in __init__ so the Observable
        # __setattr__ auto-wraps them into ObservableList / ObservableDict
        # (use_state initial values wouldn't trigger wrapping otherwise).
        self.history = []
        self.results_cache = {}
        self.last_results = {}
        self.selected_sites = []
        self.search_targets = []
        self.target_results = {}
        self.sites_cache = []
        self.sites_tags_map = {}
        self.email_results = []
        self.enrichments = {}
        self.update_data = None
        self.search_error = None

    def set_cached_result(self, mode: str, query: str, data: dict) -> None:
        """Store search results with an LRU cap of 30 queries."""
        key = f"{mode}:{query.strip().lower()}"
        if len(self.results_cache) >= 30:
            oldest = next(iter(self.results_cache))
            del self.results_cache[oldest]
        self.results_cache[key] = data

    def get_cached_result(self, mode: str, query: str) -> dict | None:
        """Get cached search results for a specific query and mode."""
        key = f"{mode}:{query.strip().lower()}"
        return self.results_cache.get(key)

    def set_enrichment(self, url: str, data: dict) -> None:
        """Add an enrichment with LRU-ish cap at _ENRICHMENT_CAP entries."""
        if len(self.enrichments) >= _ENRICHMENT_CAP:
            # Drop oldest key (dict keeps insertion order in 3.7+)
            oldest = next(iter(self.enrichments))
            del self.enrichments[oldest]
        self.enrichments[url] = data

    def reset_search(self) -> None:
        """Clear all search-related state. Called on app start, cancel, etc.

        Mutates assigned collections in place so existing
        ObservableList/ObservableDict wrappers stay attached to this state
        and downstream subscribers keep working.
        """
        self.is_searching = False
        self.search_progress = None
        self.progress_version = 0
        self.search_error = None
        self.active_username = ""
        self.is_online = True
        self.search_targets.clear()
        self.target_results.clear()
        self.email_results.clear()
        self.enrichments.clear()


state = AppState()
