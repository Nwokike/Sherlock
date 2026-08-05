"""Shared tree-walking helpers for tests.

These utilities walk the Flet control tree depth-first, recursing through
both `controls` lists and the `content` attribute used by single-content
containers like Container, FilledButton, IconButton, etc.
"""

from collections.abc import Iterable
from typing import Any

import flet as ft


def walk(c: Any) -> Iterable[Any]:
    """Yield all controls in the tree depth-first.

    Recurses through both `controls` (list children) and `content`
    (single child) attributes — i.e. covers Container, Column, Row,
    ListView, GridView, FilledButton, IconButton, etc.
    """
    yield c
    children = getattr(c, "controls", None) or []
    if isinstance(children, list):
        for ch in children:
            yield from walk(ch)
    content = getattr(c, "content", None)
    if content is not None:
        yield from walk(content)


def walk_buttons(root: Any) -> Iterable[Any]:
    """Yield every button-like control in the tree."""
    for c in walk(root):
        if isinstance(
            c,
            (ft.FilledButton, ft.OutlinedButton, ft.ElevatedButton, ft.TextButton),
        ):
            yield c


def walk_icons(root: Any) -> Iterable[Any]:
    """Yield every icon-bearing control in the tree."""
    for c in walk(root):
        if isinstance(c, ft.Icon) or (
            isinstance(c, ft.IconButton) and getattr(c, "icon", None)
        ):
            yield c


def walk_texts(root: Any) -> Iterable[Any]:
    """Yield every ft.Text in the tree."""
    for c in walk(root):
        if isinstance(c, ft.Text):
            yield c


def walk_containers(root: Any) -> Iterable[Any]:
    """Yield every ft.Container in the tree."""
    for c in walk(root):
        if isinstance(c, ft.Container):
            yield c


def button_label(btn: Any) -> str:
    """Extract a button's label text from its `content` if it's a Text."""
    content = btn.content
    if isinstance(content, ft.Text):
        return content.value or ""
    return ""


def find_button_by_label(root: Any, label_substring: str) -> Any | None:
    """Return the first button whose label contains `label_substring`."""
    for btn in walk_buttons(root):
        if label_substring in button_label(btn):
            return btn
    return None


def find_icon(root: Any, icon_name: str) -> Any | None:
    """Return the first icon-bearing control whose icon equals `icon_name`."""
    for c in walk(root):
        if isinstance(c, ft.Icon) and c.icon == icon_name:
            return c
        if isinstance(c, ft.IconButton) and getattr(c, "icon", None) == icon_name:
            return c
    return None
