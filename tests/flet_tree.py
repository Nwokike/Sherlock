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

    Recurses through `controls` (list children), `content`
    (single child), `actions` (dialog/appbar button lists), and the
    single-child chrome slots `leading` / `title` / `trailing` /
    `icon` / `appbar` — i.e. covers Container, Column, Row,
    ListView, GridView, FilledButton, IconButton, AppBar,
    CupertinoAppBar, AlertDialog, and View.appbar. `str` slots
    (StrOrControl titles, str button content) are skipped here and
    handled by button_label / callers.
    """
    yield c
    children = getattr(c, "controls", None) or []
    if isinstance(children, list):
        for ch in children:
            yield from walk(ch)
    content = getattr(c, "content", None)
    if content is not None and not isinstance(content, str):
        yield from walk(content)
    for attr in ("leading", "title", "trailing", "icon", "appbar"):
        v = getattr(c, attr, None)
        if v is not None and not isinstance(v, str):
            yield from walk(v)
    actions = getattr(c, "actions", None) or []
    if isinstance(actions, list):
        for a in actions:
            yield from walk(a)


_BUTTON_TYPES: tuple[type, ...] = tuple(
    t
    for t in (
        getattr(ft, "FilledButton", None),
        getattr(ft, "FilledTonalButton", None),
        getattr(ft, "OutlinedButton", None),
        getattr(ft, "TextButton", None),
        getattr(ft, "ElevatedButton", None),
    )
    if isinstance(t, type)
)


def walk_buttons(root: Any) -> Iterable[Any]:
    """Yield every button-like control in the tree."""
    for c in walk(root):
        if isinstance(c, _BUTTON_TYPES):
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
    """Extract a button's label text.

    Handles str content (ft.TextButton("Close")), ft.Text content,
    and Row/Container-wrapped Text (descendant values joined).
    """
    content = getattr(btn, "content", None)
    if content is None:
        text = getattr(btn, "text", None)
        return text if isinstance(text, str) else ""
    if isinstance(content, str):
        return content
    if isinstance(content, ft.Text):
        return content.value or ""
    parts = [t.value or "" for t in walk(content) if isinstance(t, ft.Text)]
    return " ".join(p for p in parts if p).strip()


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
