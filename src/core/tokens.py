"""Design tokens — Sherlock premium design system.

Token contract:
- All values are unitless numbers in logical pixels.
- Radius tokens are plain ints for `border_radius=` / `RoundedRectangleBorder(radius=…)`
  — NOT `ft.BorderRadius` objects.
- `ANIM_*` are milliseconds for `ft.Animation(ms, curve)`.
- `OPACITY_*` are 0-1 floats for `ft.Colors.with_opacity(opacity, color)`.
- Radii/shadow depth on cards maps to `ft.Card(elevation=…)`; `ft.Container`
  has no `elevation` in flet 1.0.4 (use `shadow=` / `ft.BoxShadow`).

Only tokens with at least one live consumer are exported — dead tokens are
deleted, not parked.
"""

# ─── TYPOGRAPHY ──────────────────────────────────────────────────────────────

FONT_XS = 11
FONT_SM = 12
FONT_MD = 14
FONT_LG = 16
FONT_XL = 20
FONT_XXL = 26

# ─── SPACING & PADDING ──────────────────────────────────────────────────────
SPACE_XXS = 2
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_XXXL = 48

# ─── BORDER RADII ───────────────────────────────────────────────────────────
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16
RADIUS_XL = 20
RADIUS_FULL = 999

# ─── ICON DIMENSIONS ────────────────────────────────────────────────────────
ICON_SM = 18
ICON_MD = 22
ICON_FEATURE = 56  # onboarding / empty-state hero icons
ICON_EMPTY = 48  # empty-state icon (rendered inside a 96px circle backdrop)
RESULT_ICON = 20  # result card status icon

# ─── ANIMATION DURATIONS (ms) ───────────────────────────────────────────────
ANIM_FAST = 120
ANIM_SLOW = 350

# ─── COMPONENT DIMENSIONS ──────────────────────────────────────────────────
PROGRESS_BAR_HEIGHT = 4
ICON_BACKDROP = 36  # circular icon backdrop (36x36)
ICON_BACKDROP_RADIUS = 18
MESSAGE_MAX_WIDTH = 320
BORDER_WIDTH_DEFAULT = 1
DIALOG_WIDTH_LG = 420
DIALOG_HEIGHT_LG = 480

# ─── OPACITY ────────────────────────────────────────────────────────────────
OPACITY_SUBTLE = 0.05
OPACITY_LIGHT = 0.08
OPACITY_MEDIUM = 0.12
OPACITY_DIM = 0.50
OPACITY_MUTED = 0.35

__all__ = [
    "ANIM_FAST",
    "ANIM_SLOW",
    "BORDER_WIDTH_DEFAULT",
    "DIALOG_HEIGHT_LG",
    "DIALOG_WIDTH_LG",
    "FONT_LG",
    "FONT_MD",
    "FONT_SM",
    "FONT_XL",
    "FONT_XS",
    "FONT_XXL",
    "ICON_BACKDROP",
    "ICON_BACKDROP_RADIUS",
    "ICON_EMPTY",
    "ICON_FEATURE",
    "ICON_MD",
    "ICON_SM",
    "MESSAGE_MAX_WIDTH",
    "OPACITY_DIM",
    "OPACITY_LIGHT",
    "OPACITY_MEDIUM",
    "OPACITY_MUTED",
    "OPACITY_SUBTLE",
    "PROGRESS_BAR_HEIGHT",
    "RADIUS_FULL",
    "RADIUS_LG",
    "RADIUS_MD",
    "RADIUS_SM",
    "RADIUS_XL",
    "RESULT_ICON",
    "SPACE_LG",
    "SPACE_MD",
    "SPACE_SM",
    "SPACE_XL",
    "SPACE_XS",
    "SPACE_XXS",
    "SPACE_XXXL",
]
