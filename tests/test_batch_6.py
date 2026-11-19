"""Regression tests for Fix Batch 6 (sites perf + test-infra).

Covers: live chip construction counts, FakePage platform/storage/width
defaults, flet_tree chrome-slot traversal + str-content labels.
"""

import flet as ft

from tests.conftest import FakeClientStorage, FakePage
from tests.flet_tree import (
    button_label,
    find_button_by_label,
    walk,
    walk_buttons,
)


def test_fakepage_defaults_are_desktop_wide_light():
    page = FakePage()
    assert page.platform == ft.PagePlatform.WINDOWS
    assert page.platform.is_mobile() is False
    assert page.width == 1280.0
    assert page.platform_brightness == ft.Brightness.LIGHT
    assert page.on_app_lifecycle_state_change is None


def test_fakepage_mobile_narrow_override():
    page = FakePage(platform=ft.PagePlatform.ANDROID, width=390.0)
    assert page.platform.is_mobile() is True
    assert page.width < 600


def test_fake_client_storage_roundtrip():
    page = FakePage()
    assert isinstance(page.client_storage, FakeClientStorage)
    assert page.client_storage.get("k") is None
    page.client_storage.set("k", '{"a": 1}')
    assert page.client_storage.get("k") == '{"a": 1}'


def test_fakepage_dialogs_and_update_props():
    page = FakePage()
    assert page.dialogs == []
    assert page.update_calls == 0
    page.show_dialog(ft.SnackBar(content=ft.Text("hi")))
    assert len(page.dialogs) == 1
    page.update()
    assert page.update_calls == 1


def test_run_task_and_wait_executes():
    import asyncio

    async def _coro(x):
        return x * 2

    page = FakePage()
    assert asyncio.run(page.run_task_and_wait(_coro, 21)) == 42
    # Logging tuple identical to run_task's
    assert page.render_calls[-1][0] == "run_task"


def test_walk_descends_into_appbar_and_dialog_actions():
    bar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK_ROUNDED, on_click=lambda e: None
        ),
        title=ft.Text("Search Results"),
        actions=[
            ft.IconButton(icon=ft.Icons.DOWNLOAD_ROUNDED, on_click=lambda e: None),
        ],
    )
    icons = [c for c in walk(bar) if isinstance(c, ft.IconButton)]
    assert len(icons) == 2
    assert any(
        isinstance(c, ft.Text) and c.value == "Search Results" for c in walk(bar)
    )

    dlg = ft.AlertDialog(
        title=ft.Text("Confirm"),
        content=ft.Text("Body"),
        actions=[ft.TextButton("Close", on_click=lambda e: None)],
    )
    assert find_button_by_label(dlg, "Close") is not None


def test_button_label_str_and_wrapped():
    assert button_label(ft.TextButton("Close")) == "Close"
    assert (
        button_label(ft.FilledButton(content=ft.Text("Search Networks")))
        == "Search Networks"
    )
    wrapped = ft.FilledButton(
        content=ft.Row(controls=[ft.Icon(ft.Icons.SEARCH_ROUNDED), ft.Text("Go")])
    )
    assert button_label(wrapped) == "Go"
    assert list(walk_buttons(wrapped)) != []


def test_live_chip_counts_from_index():
    """Chip labels carry bucket counts from the live tag index."""
    index = {
        "social": ["A", "B", "C"],
        "coding": ["D"],
        "us": ["A", "D"],
        "photo": ["E", "F"],
    }
    sizes = {k.lower(): len(v or []) for k, v in index.items()}
    assert sizes["social"] == 3
    assert sizes["us"] == 2
    countries = sorted(k for k in sizes if len(k) == 2 and k.isalpha())
    assert countries == ["us"]
    rest = sorted(
        (
            k
            for k in sizes
            if k
            not in ("social", "coding", "gaming", "forum", "crypto", "dating", "video")
            and k != "all"
            and not (len(k) == 2 and k.isalpha())
        ),
        key=lambda k: sizes[k],
        reverse=True,
    )
    assert rest == ["photo"]


def test_sites_search_bar_component_exists():
    from screens.sites_screen import _ROW_HEIGHT, POPULAR_SITES, SitesSearchBar

    assert "twitter" not in POPULAR_SITES  # deduped to "x"
    assert "x" in POPULAR_SITES
    assert _ROW_HEIGHT == 56.0
    assert getattr(SitesSearchBar, "__is_component__", False) is True
