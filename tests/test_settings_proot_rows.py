"""Settings proot-parity rows + the richer `_setting_row` contract.

proot-distro's settings helper shows a live value, makes the WHOLE row
tappable (ink + chevron), and stacks the control under the label on narrow
screens. Sherlock's row used to need a small button and carried no value.
"""

from __future__ import annotations

import flet as ft
from flet.components.component import Component, Renderer

from core.state import state
from screens.settings_screen import SettingsScreen, _setting_row
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethods, ControllerMethodsCtx


def _nodes(comp) -> list:
    """Expand a rendered component tree the way the other screen tests do."""
    out: list = []
    root = Renderer().render(
        lambda: ControllerMethodsCtx(
            ControllerMethods(), lambda: AppStateCtx(state, comp)
        )
    )

    def expand(node):
        out.append(node)
        if isinstance(node, Component):
            node.before_update()
            built = getattr(node, "_b", None)
            if built is not None:
                expand(built)
        elif isinstance(node, list):
            for item in node:
                expand(item)
        else:
            for child in getattr(node, "controls", None) or []:
                expand(child)
            content = getattr(node, "content", None)
            if content is not None and not isinstance(content, str):
                expand(content)

    expand(root)
    return out


def _texts(nodes) -> list[str]:
    return [
        n.value for n in nodes if hasattr(n, "value") and isinstance(n.value, str)
    ]


def _icons(nodes) -> list:
    return [n.icon for n in nodes if isinstance(n, ft.Icon)]


def test_settings_keeps_only_the_complete_system_rows():
    texts = _texts(_nodes(lambda: SettingsScreen()))
    assert any("Notifications" in t for t in texts)
    assert any("Privacy & Ads" in t for t in texts)
    for stripped in (
        "Help & shortcuts",
        "Open-source licenses",
        "Privacy policy",
        "Terms of service",
        "Show the intro again",
        "Exit app",
    ):
        assert not any(stripped in t for t in texts), f"stripped row returned: {stripped}"


def test_setting_row_with_on_tap_is_tappable_and_inked():
    tapped: list = []
    row = _setting_row(
        ft.Icons.NOTIFICATIONS_ROUNDED,
        "Notifications",
        "Scan progress lives in the OS shade",
        value="Allowed",
        on_tap=lambda e: tapped.append(1),
    )
    assert row.on_click is not None, "a navigation row must be tappable"
    assert row.ink is True, "a tappable row needs ink feedback"
    row.on_click(None)
    assert tapped == [1]


def test_setting_row_shows_a_chevron_when_it_navigates():
    row = _setting_row(
        ft.Icons.HELP_OUTLINE_ROUNDED,
        "Help & shortcuts",
        "How searches work",
        on_tap=lambda e: None,
    )
    assert ft.Icons.CHEVRON_RIGHT_ROUNDED in _icons(_nodes(lambda: row))


def test_setting_row_still_accepts_no_trailing_control():
    row = _setting_row(ft.Icons.DONE, "Nothing else", "No control")
    assert row is not None
