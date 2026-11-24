"""Responsive rules — ONE definition of the breakpoints used across screens.

Before this module the narrow breakpoint was inlined in Settings (and nowhere
else), so a window could stack on one surface and not another. Screens call
these helpers instead. Mirrors proot-distro's `core/layout.py`.
"""

from __future__ import annotations

NARROW_BREAKPOINT = 600
MOBILE_BREAKPOINT = 650
DIALOG_GUTTER = 48


def _int_attr(page, name: str) -> int:
    try:
        return int(getattr(page, name, 0) or 0)
    except TypeError, ValueError:
        return 0


def page_width(page) -> int:
    return _int_attr(page, "width")


def page_height(page) -> int:
    return _int_attr(page, "height")


def is_narrow(page, width_limit: int = NARROW_BREAKPOINT) -> bool:
    """True when settings-style rows must stack under their label."""
    width = page_width(page)
    return bool(width and width < width_limit)


def is_mobile_layout(page) -> bool:
    """Mobile platform OR a phone-width page (the container grid's rule)."""
    platform = getattr(page, "platform", None)
    mobile = bool(platform.is_mobile()) if platform is not None else False
    return mobile or is_narrow(page, MOBILE_BREAKPOINT)


def dialog_width(
    page,
    *,
    min_width: int = 300,
    max_width: int = 380,
) -> int:
    """A dialog width that never exceeds the page (gutter) or its own cap."""
    width = page_width(page)
    if not width:
        return max_width
    return min(max_width, max(min_width, width - DIALOG_GUTTER))
