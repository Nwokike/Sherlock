"""Settings proot-parity rows + the richer `_setting_row` contract.

proot-distro's settings helper shows a live value, makes the WHOLE row
tappable (ink + chevron), and stacks the control under the label on narrow
screens. Sherlock's row used to need a small button and carried no value.
"""

from __future__ import annotations

import flet as ft
from flet.components.component import Component, Renderer
from flet.components.hooks.use_effect import EffectHook
from flet.controls.context import _context_page

from core.state import state
from screens.settings_screen import (
    SettingsScreen,
    _set_button_disabled,
    _setting_row,
)
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


def _rendered_settings_component(page) -> Component:
    """Render Settings with a real page context, without mounting a session."""
    token = _context_page.set(page)
    try:
        root = Renderer().render(
            lambda: ControllerMethodsCtx(
                ControllerMethods(), lambda: AppStateCtx(state, lambda: SettingsScreen())
            )
        )

        def find(node):
            if isinstance(node, Component):
                if getattr(node.fn, "__name__", None) == "SettingsScreen":
                    return node
                node.before_update()
                return find(getattr(node, "_b", None))
            if isinstance(node, (list, tuple)):
                for item in node:
                    found = find(item)
                    if found is not None:
                        return found
                return None
            for child in getattr(node, "controls", None) or []:
                found = find(child)
                if found is not None:
                    return found
            content = getattr(node, "content", None)
            if content is not None and not isinstance(content, str):
                return find(content)
            return None

        component = find(root)
        assert component is not None
        component.before_update()
        return component
    finally:
        _context_page.reset(token)


def test_settings_unmount_clears_only_its_own_resize_handler(fake_page):
    component = _rendered_settings_component(fake_page)
    cleanup_effect = next(
        hook
        for hook in component._state.hooks
        if isinstance(hook, EffectHook) and hook.deps == []
    )
    cleanup = cleanup_effect.setup()
    assert callable(cleanup)
    assert fake_page.on_resize is not None

    cleanup()
    assert fake_page.on_resize is None

    # A later screen may already have installed its own callback. Settings
    # cleanup must not erase that newer owner's handler.
    component = _rendered_settings_component(fake_page)
    cleanup_effect = next(
        hook
        for hook in component._state.hooks
        if isinstance(hook, EffectHook) and hook.deps == []
    )
    def replacement(_e):
        return None

    fake_page.on_resize = replacement
    cleanup_effect.setup()()
    assert fake_page.on_resize is replacement


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


def test_frozen_settings_button_is_never_mutated_or_updated():
    class Button:
        def __init__(self):
            self.disabled = False
            self.updates = 0

        def update(self):
            self.updates += 1

    frozen = Button()
    frozen._frozen = True
    _set_button_disabled(frozen, True)
    assert frozen.disabled is False
    assert frozen.updates == 0

    live = Button()
    _set_button_disabled(live, True)
    assert live.disabled is True
    assert live.updates == 1


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
