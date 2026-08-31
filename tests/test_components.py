"""Tests for plain-function components — full tree-walk unit tests.

These components don't use hooks, so they can be instantiated directly
without a renderer context.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__), "..", ".venv", "lib", "python3.13", "site-packages"
    ),
)

import flet as ft
from tests.flet_tree import walk_texts, walk_buttons, find_icon

from components.empty_state import EmptyState
from components.result_card import ResultCard
from components.stat_card import StatCard
from components.section_header import SectionHeader
from components.targets_card import TargetsCard


class TestEmptyState:
    def test_basic(self):
        tree = EmptyState(title="No data")
        texts = list(walk_texts(tree))
        assert any("No data" in (t.value or "") for t in texts)

    def test_with_message(self):
        tree = EmptyState(title="Empty", message="Nothing here")
        texts = list(walk_texts(tree))
        assert any("Nothing here" in (t.value or "") for t in texts)

    def test_with_action(self):
        called = []
        tree = EmptyState(
            title="Empty", action_label="Retry", on_action=lambda e: called.append(True)
        )
        buttons = list(walk_buttons(tree))
        assert len(buttons) >= 1

    def test_icon_present(self):
        tree = EmptyState(title="Empty", icon=ft.Icons.SEARCH)
        assert find_icon(tree, ft.Icons.SEARCH) is not None


class TestResultCard:
    def test_claimed(self):
        tree = ResultCard(
            site_name="GitHub", status="Claimed", url_user="https://github.com/test"
        )
        texts = list(walk_texts(tree))
        assert any("GitHub" in (t.value or "") for t in texts)
        assert find_icon(tree, ft.Icons.CHECK_CIRCLE_ROUNDED) is not None

    def test_available(self):
        tree = ResultCard(site_name="FakeSite", status="Available")
        assert find_icon(tree, ft.Icons.CANCEL_ROUNDED) is not None

    def test_waf(self):
        tree = ResultCard(site_name="Protected", status="WAF")
        assert find_icon(tree, ft.Icons.SHIELD_ROUNDED) is not None

    def test_error(self):
        tree = ResultCard(site_name="Timeout", status="Error")
        assert find_icon(tree, ft.Icons.ERROR_OUTLINE_ROUNDED) is not None

    def test_with_query_time(self):
        tree = ResultCard(site_name="GitHub", status="Claimed", query_time=0.12)
        texts = list(walk_texts(tree))
        assert any("0.12s" in (t.value or "") for t in texts)

    # --- tap-to-open (restored pre-restructure behavior) ---

    def test_tap_opens_profile_url(self):
        opened = []
        tree = ResultCard(
            site_name="GitHub",
            status="Claimed",
            url_user="https://github.com/test",
            on_open=opened.append,
        )
        assert tree.on_click is not None
        tree.on_click(None)
        assert opened == ["https://github.com/test"]

    def test_tap_triggers_on_tap(self):
        tapped = []
        tree = ResultCard(
            site_name="GitHub",
            status="Claimed",
            url_user="https://github.com/test",
            on_tap=lambda: tapped.append(True),
        )
        assert tree.on_click is not None
        tree.on_click(None)
        assert tapped == [True]

    def test_no_profile_url_is_inert(self):
        tree = ResultCard(site_name="FakeSite", status="Available")
        assert tree.on_click is None

    def test_url_without_callback_is_inert(self):
        # No on_open or on_tap supplied — calling on_click must not raise.
        tree = ResultCard(
            site_name="GitHub", status="Claimed", url_user="https://x.com/a"
        )
        if tree.on_click is not None:
            tree.on_click(None)


class TestTargetsCard:
    def test_all_networks_label(self):
        tree = TargetsCard(selected_count=0, total_count=368, on_open=lambda: None)
        texts = list(walk_texts(tree))
        assert any("All networks selected" in (t.value or "") for t in texts)
        assert any("368" in (t.value or "") for t in texts)

    def test_custom_scope_label(self):
        tree = TargetsCard(selected_count=25, total_count=368, on_open=lambda: None)
        texts = list(walk_texts(tree))
        assert any("25 networks selected" in (t.value or "") for t in texts)

    def test_fallback_label_when_total_unknown(self):
        tree = TargetsCard(selected_count=0, total_count=0, on_open=lambda: None)
        texts = list(walk_texts(tree))
        assert any("400+" in (t.value or "") for t in texts)

    def test_tap_triggers_on_open(self):
        fired = []
        tree = TargetsCard(
            selected_count=0, total_count=368, on_open=lambda e: fired.append(1)
        )
        assert tree.on_click is not None
        tree.on_click(None)
        assert fired == [1]


class TestStatCard:
    def test_renders_label_and_value(self):
        tree = StatCard(label="Found", value="5", color=ft.Colors.GREEN)
        texts = list(walk_texts(tree))
        assert any("5" in (t.value or "") for t in texts)
        assert any("Found" in (t.value or "") for t in texts)


class TestSectionHeader:
    def test_renders_text(self):
        tree = SectionHeader("PREFERENCES")
        texts = list(walk_texts(tree))
        assert any("PREFERENCES" in (t.value or "") for t in texts)


class TestProfileDetailDialog:
    def test_renders_dialog(self):
        from components.profile_detail_dialog import show_profile_detail_dialog

        class MockPage:
            def __init__(self):
                self.platform = ft.PagePlatform.ANDROID
                self.dialog = None

            def show_dialog(self, dlg):
                self.dialog = dlg

            def pop_dialog(self):
                self.dialog = None

        page = MockPage()
        show_profile_detail_dialog(
            page=page,
            site_name="GitHub",
            status="Claimed",
            mode="username",
            target_query="torvalds",
            url_user="https://github.com/torvalds",
            query_time=0.45,
            enrichment={
                "name": "Linus Torvalds",
                "bio": "Creator of Linux & Git",
                "location": "Portland, OR",
                "follower_count": 210000,
                "uid": "1024025",
            },
        )
        assert page.dialog is not None
        assert isinstance(page.dialog, ft.AlertDialog)
        texts = list(walk_texts(page.dialog))
        assert any("GitHub" in (t.value or "") for t in texts)
        assert any("Linus Torvalds" in (t.value or "") for t in texts)
        assert any("Creator of Linux & Git" in (t.value or "") for t in texts)

    def test_renders_email_dossier(self):
        from components.profile_detail_dialog import show_profile_detail_dialog

        class MockPage:
            def __init__(self):
                self.platform = ft.PagePlatform.ANDROID
                self.dialog = None

            def show_dialog(self, dlg):
                self.dialog = dlg

            def pop_dialog(self):
                self.dialog = None

        page = MockPage()
        show_profile_detail_dialog(
            page=page,
            site_name="Instagram",
            status="Claimed",
            mode="email",
            target_query="target@example.com",
            url_main="https://instagram.com",
            email_recovery="t***t@e***e.com",
            phone_number="*******1234",
            method="password recovery",
        )
        assert page.dialog is not None
        assert isinstance(page.dialog, ft.AlertDialog)
        texts = list(walk_texts(page.dialog))
        assert any("Instagram" in (t.value or "") for t in texts)
        assert any("target@example.com" in (t.value or "") for t in texts)
        assert any("t***t@e***e.com" in (t.value or "") for t in texts)
        assert any("*******1234" in (t.value or "") for t in texts)
        assert any("Detection Vector" in (t.value or "") for t in texts)


class TestAppHeader:
    def test_renders_app_header(self):
        from components.app_header import AppHeader

        tree = AppHeader(
            page=None,
            title="History",
            subtitle="Past searches",
        )
        texts = list(walk_texts(tree))
        assert any("History" in (t.value or "") for t in texts)
        assert any("Past searches" in (t.value or "") for t in texts)
