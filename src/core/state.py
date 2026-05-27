"""Observable application state."""

import flet as ft


@ft.observable
class AppState:
    is_loading: bool = False
    is_searching: bool = False
    current_username: str = ""
    theme_mode: ft.ThemeMode = ft.ThemeMode.SYSTEM
    last_results: dict = {}
    last_results_username: str = ""
    history: list = []
    total_sites_checked: int = 0
    found_count: int = 0
    not_found_count: int = 0
    error_count: int = 0

    def __init__(self):
        self.history = []
        self.last_results = {}


state = AppState()
