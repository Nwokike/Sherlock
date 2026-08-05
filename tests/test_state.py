"""Tests for the observable application state."""

import pytest
from core.state import AppState


@pytest.fixture
def app_state():
    state = AppState()
    yield state
    state.reset_search()


class TestAppState:
    def test_initial_state(self, app_state):
        assert app_state.is_loading is False
        assert app_state.is_searching is False
        assert app_state.is_first_launch is True
        assert app_state.has_accepted_terms is False
        assert app_state.current_username == ""
        assert app_state.active_username == ""
        assert app_state.history == []
        assert app_state.nsfw_enabled is True
        assert app_state.timeout == 30

    def test_search_fields(self, app_state):
        assert app_state.search_progress is None
        assert app_state.progress_version == 0
        assert app_state.target_results == {}
        assert app_state.search_error is None

    def test_reset_search(self, app_state):
        app_state.is_searching = True
        app_state.search_error = "error"
        app_state.active_username = "test"
        app_state.progress_version = 5
        app_state.target_results["test"] = object()
        app_state.search_targets.append("test")

        app_state.reset_search()

        assert app_state.is_searching is False
        assert app_state.search_error is None
        assert app_state.active_username == ""
        assert app_state.progress_version == 0
        assert len(app_state.target_results) == 0
        assert len(app_state.search_targets) == 0

    def test_history_observable(self, app_state):
        """history is an ObservableList — mutations should be tracked."""
        app_state.history.append({"username": "test", "found": 1, "total": 10})
        assert len(app_state.history) == 1
        app_state.history.clear()
        assert len(app_state.history) == 0

    def test_target_results_observable(self, app_state):
        """target_results is an ObservableDict — setitem should notify."""
        app_state.target_results["user1"] = {"found": [], "not_found": []}
        assert "user1" in app_state.target_results
        assert app_state.target_results["user1"]["found"] == []

    def test_selected_sites_observable(self, app_state):
        app_state.selected_sites.append("github")
        assert "github" in app_state.selected_sites
        app_state.selected_sites.clear()
        assert len(app_state.selected_sites) == 0


class TestAppStateObservable:
    """Verify the @ft.observable mixin works correctly."""

    def test_subscribe_and_notify(self, app_state):
        notifications = []
        app_state.subscribe(lambda sender, field: notifications.append(field))

        app_state.is_searching = True
        assert len(notifications) == 1
        assert notifications[0] == "is_searching"

    def test_collection_mutation_notifies(self, app_state):
        notifications = []
        app_state.subscribe(lambda sender, field: notifications.append(field))

        app_state.history.append({"username": "test"})
        assert len(notifications) >= 1

    def test_version_counter(self, app_state):
        app_state.progress_version = 1
        assert app_state.progress_version == 1
