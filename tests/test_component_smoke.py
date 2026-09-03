"""Smoke tests for @ft.component screens — verify they are components.

Full rendering requires a renderer context (tested via manual smoke).
These ensure the decorator was applied correctly.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__), "..", ".venv", "lib", "python3.14", "site-packages"
    ),
)

from screens.home_screen import HomeScreen
from screens.results_screen import ResultsScreen
from screens.history_screen import HistoryScreen
from screens.settings_screen import SettingsScreen
from screens.sites_screen import SitesScreen
from screens.onboarding_screen import OnboardingScreen
from app_shell import AppShell


class TestComponentDeco:
    def test_home_screen_is_component(self):
        assert getattr(HomeScreen, "__is_component__", False) is True
        assert callable(HomeScreen)

    def test_results_screen_is_component(self):
        assert getattr(ResultsScreen, "__is_component__", False) is True
        assert callable(ResultsScreen)

    def test_history_screen_is_component(self):
        assert getattr(HistoryScreen, "__is_component__", False) is True
        assert callable(HistoryScreen)

    def test_settings_screen_is_component(self):
        assert getattr(SettingsScreen, "__is_component__", False) is True
        assert callable(SettingsScreen)

    def test_sites_screen_is_component(self):
        assert getattr(SitesScreen, "__is_component__", False) is True
        assert callable(SitesScreen)

    def test_onboarding_screen_is_component(self):
        assert getattr(OnboardingScreen, "__is_component__", False) is True
        assert callable(OnboardingScreen)

    def test_app_shell_is_component(self):
        assert getattr(AppShell, "__is_component__", False) is True
        assert callable(AppShell)
