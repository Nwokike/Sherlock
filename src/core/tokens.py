"""Design tokens — Sherlock premium design system.

Comprehensive token system for typography, spacing, border radii, icon sizes,
animation durations, elevation, and gradient presets. All UI components
consume these tokens for visual consistency.
"""

# ─── TYPOGRAPHY ──────────────────────────────────────────────────────────────
FONT_FAMILY_PRIMARY = "Outfit"
FONT_FAMILY_MONO = "JetBrains Mono"

FONT_XS = 11
FONT_SM = 12
FONT_MD = 14
FONT_LG = 16
FONT_XL = 20
FONT_XXL = 26
FONT_HERO = 34

# ─── SPACING & PADDING ──────────────────────────────────────────────────────
SPACE_XXS = 2
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_XXL = 32
SPACE_XXXL = 48

# ─── BORDER RADII ───────────────────────────────────────────────────────────
RADIUS_XS = 6
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16
RADIUS_XL = 20
RADIUS_XXL = 24
RADIUS_FULL = 999

# ─── ICON DIMENSIONS ────────────────────────────────────────────────────────
ICON_XS = 16
ICON_SM = 18
ICON_MD = 22
ICON_LG = 26
ICON_XL = 34
ICON_FEATURE = 56  # onboarding / empty-state hero icons
ICON_EMPTY = 48  # empty-state icon inside circle backdrop
RESULT_ICON = 20  # result card status icon
STAT_NUMBER = 28  # stat card large number

# ─── ANIMATION DURATIONS (ms) ───────────────────────────────────────────────
ANIM_FAST = 120
ANIM_NORMAL = 200
ANIM_SLOW = 350
ANIM_PAGE = 300

# ─── ELEVATION ──────────────────────────────────────────────────────────────
ELEVATION_NONE = 0
ELEVATION_LOW = 1
ELEVATION_MED = 3
ELEVATION_HIGH = 6
ELEVATION_FLOAT = 12

# ─── COMPONENT DIMENSIONS ──────────────────────────────────────────────────
HEADER_HEIGHT = 56
NAV_BAR_HEIGHT = 72
SEARCH_BAR_HEIGHT = 52
TEXT_FIELD_HEIGHT = 44
CARD_MIN_HEIGHT = 60
PROGRESS_BAR_HEIGHT = 4
HERO_ICON_SIZE = 80
CTA_BUTTON_WIDTH = 280
ICON_BACKDROP = 36  # circular icon backdrop (36x36)
ICON_BACKDROP_RADIUS = 18
MESSAGE_MAX_WIDTH = 320
BORDER_WIDTH_THIN = 0.5
BORDER_WIDTH_DEFAULT = 1
BORDER_WIDTH_FOCUS = 2
DIALOG_WIDTH_LG = 420
DIALOG_HEIGHT_LG = 480

# ─── OPACITY ────────────────────────────────────────────────────────────────
OPACITY_SUBTLE = 0.05
OPACITY_LIGHT = 0.08
OPACITY_MEDIUM = 0.12
OPACITY_STRONG = 0.20
OPACITY_DIM = 0.50
OPACITY_MUTED = 0.35
OPACITY_FULL = 1.0
