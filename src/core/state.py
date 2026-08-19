"""Observable application state."""

from __future__ import annotations

import flet as ft


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

    # --- History ---
    history: list | None = None

    # --- Settings state ---
    nsfw_enabled: bool = True
    ignore_exclusions: bool = False
    timeout: int = 30
    selected_sites: list[str] | None = None
    use_local_db: bool = True
    db_sync_status: str = "Idle"
    custom_manifest: str = ""

    # --- Updates ---
    update_available_version: str | None = None

    def __init__(self):
        # Collections must be assigned in __init__ so the Observable
        # __setattr__ auto-wraps them into ObservableList / ObservableDict
        # (use_state initial values wouldn't trigger wrapping otherwise).
        self.history = []
        self.last_results = {}
        self.selected_sites = []
        self.search_targets = []
        self.target_results = {}
        self.update_available_version = None
        self.search_error = None

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


state = AppState()
