"""Observable application state."""

import flet as ft


@ft.observable
class AppState:
    is_loading: bool = False
    is_searching: bool = False
    current_username: str = ""
    theme_mode: ft.ThemeMode = ft.ThemeMode.LIGHT
    last_results: dict = {}
    last_results_username: str = ""
    history: list = []
    total_sites_checked: int = 0
    found_count: int = 0
    not_found_count: int = 0
    error_count: int = 0

    # Settings states
    nsfw_enabled: bool = True
    ignore_exclusions: bool = False
    timeout: int = 30
    selected_sites: list[str] = []
    use_local_db: bool = True
    db_sync_status: str = "Idle"

    def __init__(self):
        self.history = []
        self.last_results = {}
        self.selected_sites = []


state = AppState()
