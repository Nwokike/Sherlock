"""Tests for UpdateService and UpdateDialog."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import flet as ft

from core.constants import APP_BUILD_NUMBER, APP_VERSION


class TestUpdateInfo:
    """UpdateInfo dataclass tests."""

    def test_to_dict(self):
        from services.update_service import UpdateInfo

        info = UpdateInfo(
            version="2.1.0",
            build_number=9,
            type="update",
            title="Sherlock 2.1 is here!",
            release_notes="New features",
            mandatory=True,
            github_url="https://github.com/test/repo",
            playstore_url="https://play.google.com/store/apps/details?id=ng.kiri.sherlock",
            action_url=None,
        )
        d = info.to_dict()
        assert d["version"] == "2.1.0"
        assert d["build_number"] == 9
        assert d["type"] == "update"
        assert d["mandatory"] is True
        assert (
            d["playstore_url"]
            == "https://play.google.com/store/apps/details?id=ng.kiri.sherlock"
        )


class TestUpdateService:
    """UpdateService network & version logic tests."""

    def test_instantiates(self):
        from services.update_service import UpdateService

        service = UpdateService()
        assert "raw.githubusercontent.com" in service.config_url

    def test_check_for_update_newer_build(self):
        """When remote build_number > local, return update dict."""
        from services.update_service import UpdateService

        service = UpdateService()
        mock_data = {
            "build_number": APP_BUILD_NUMBER + 1,
            "version": "2.1.0",
            "type": "update",
            "title": "Sherlock 2.1 Released!",
            "release_notes": "• Faster email scans",
            "mandatory": False,
            "github_url": "https://github.com/Nwokike/Sherlock/releases/latest",
            "playstore_url": "https://play.google.com/store/apps/details?id=ng.kiri.sherlock",
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            result = asyncio.run(service.check_for_update())

        assert result is not None
        assert result["build_number"] == APP_BUILD_NUMBER + 1
        assert result["version"] == "2.1.0"
        assert result["type"] == "update"
        assert result["release_notes"] == "• Faster email scans"

    def test_check_for_update_same_or_older_build(self):
        """When remote build_number <= local, return None."""
        from services.update_service import UpdateService

        service = UpdateService()
        mock_data = {
            "build_number": APP_BUILD_NUMBER,
            "version": APP_VERSION,
            "type": "update",
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            result = asyncio.run(service.check_for_update())

        assert result is None

    def test_check_for_update_announcement(self):
        """Announcement type with custom title and action link."""
        from services.update_service import UpdateService

        service = UpdateService()
        mock_data = {
            "build_number": APP_BUILD_NUMBER + 5,
            "version": "2.0.0",
            "type": "announcement",
            "title": "Try DDGS Search App!",
            "release_notes": "Check out our fast DuckDuckGo privacy client.",
            "mandatory": False,
            "action_url": "https://play.google.com/store/apps/details?id=ng.kiri.ddgs",
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            result = asyncio.run(service.check_for_update())

        assert result is not None
        assert result["type"] == "announcement"
        assert result["title"] == "Try DDGS Search App!"
        assert (
            result["action_url"]
            == "https://play.google.com/store/apps/details?id=ng.kiri.ddgs"
        )

    def test_check_for_update_http_error(self):
        """When HTTP status is not 200, returns None gracefully."""
        from services.update_service import UpdateService

        service = UpdateService()

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            result = asyncio.run(service.check_for_update())

        assert result is None

    def test_check_for_update_exception(self):
        """When network exception occurs (e.g. offline), returns None gracefully."""
        from services.update_service import UpdateService

        service = UpdateService()

        with patch("httpx.AsyncClient.get", side_effect=Exception("Connection failed")):
            result = asyncio.run(service.check_for_update())

        assert result is None


class TestUpdateDialog:
    """UpdateDialog component tests."""

    def test_show_update_dialog_smoke(self):
        from components.update_dialog import show_update_dialog

        class MockPage:
            def __init__(self):
                self.platform = ft.PagePlatform.ANDROID
                self.dialog = None

            def show_dialog(self, dlg):
                self.dialog = dlg

            def pop_dialog(self):
                self.dialog = None

        page = MockPage()
        update_data = {
            "version": "2.1.0",
            "build_number": 9,
            "type": "update",
            "title": "Sherlock 2.1",
            "release_notes": "• Bug fixes",
            "mandatory": False,
            "github_url": "https://github.com/Nwokike/Sherlock",
            "playstore_url": "https://play.google.com/store/apps/details?id=ng.kiri.sherlock",
        }
        show_update_dialog(page, update_data)
        assert page.dialog is not None
        assert isinstance(page.dialog, ft.AlertDialog)

    def test_show_announcement_dialog_smoke(self):
        from components.update_dialog import show_update_dialog

        class MockPage:
            def __init__(self):
                self.platform = ft.PagePlatform.LINUX
                self.dialog = None

            def show_dialog(self, dlg):
                self.dialog = dlg

            def pop_dialog(self):
                self.dialog = None

        page = MockPage()
        announcement_data = {
            "version": "2.0.0",
            "build_number": 9,
            "type": "announcement",
            "title": "New App Release",
            "release_notes": "Try our new tool!",
            "mandatory": False,
            "action_url": "https://github.com/Nwokike",
        }
        show_update_dialog(page, announcement_data)
        assert page.dialog is not None
        assert isinstance(page.dialog, ft.AlertDialog)
