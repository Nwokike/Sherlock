"""Design system — brand-customized Solarized Light & Monokai themes."""

import flet as ft


class AppColors:
    # ─── BRAND LOGO DOMINANT COLORS ──────────────────────────────────────────
    # Logo Color A (Khaki / Olive-Gold / Bronze-Green): #A68E59
    # Logo Color B (Caramel-Gold / Ochre-Tan): #CD995F

    # ─── SOLARIZED LIGHT PALETTE (Overhauled to Pure White Background) ────────
    LIGHT_BG = "#FFFFFF"  # Pure White Background (100% clean & glare-free)
    LIGHT_SURFACE = "#F3F4F6"  # Soft Slate-Grey (Clean sand surface container)
    LIGHT_TEXT = "#1E293B"  # Deep Slate-Black (Crisp high-contrast body text)
    LIGHT_TEXT_DIM = "#64748B"  # Slate-Grey (Muted label text)
    # Bluish primary/variant replaced by Caramel-Gold (Color B) variations:
    LIGHT_PRIMARY = "#CD995F"  # Caramel-Gold (Logo Color B)
    LIGHT_PRIMARY_VARIANT = "#B58248"  # Darker Caramel-Gold (Logo Color B variation)
    LIGHT_HIGHLIGHT = "#A68E59"  # Khaki-Gold (Logo Color A)

    # ─── MONOKAI PALETTE (Pinkish/Bluish colors replaced by Logo colors) ─────
    DARK_BG = "#272822"  # Classic Monokai Dark Charcoal Background
    DARK_SURFACE = "#1E1F1C"  # Monokai Dark Slate (Deeper Card Background)
    DARK_TEXT = "#F8F8F2"  # Monokai Chalk White (Body Text)
    # Pinkish primary replaced by Khaki-Gold (Color A) variation:
    DARK_PRIMARY = "#C2A96F"  # Brighter Khaki-Gold (Logo Color A variation)
    # Bluish variant replaced by Caramel-Gold (Color B) variation:
    DARK_PRIMARY_VARIANT = "#E3AE74"  # Brighter Caramel-Gold (Logo Color B variation)
    DARK_TEXT_DIM = "#75715E"  # Monokai Muted Gray (Classic Comments/Secondary Text)
    DARK_HIGHLIGHT = "#CD995F"  # Caramel-Gold (Logo Color B)

    # ─── Global Semantic colors ──────────────────────────────────────────────
    SUCCESS = "#A6E22E"  # Monokai Green
    WARNING = "#FD971F"  # Monokai Orange
    # Pinkish Error replaced by deep Khaki-Gold variation:
    ERROR = "#8C7747"  # Deep Khaki-Gold (Logo Color A variation)
    DIVIDER = "#D3C6A2"  # Solarized Base1 / Light Divider
    DARK_DIVIDER = "#49483E"  # Monokai Divider (slate)


class AppTheme:
    @staticmethod
    def get_dark_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=AppColors.DARK_PRIMARY,
                primary_container=AppColors.DARK_PRIMARY_VARIANT,
                secondary=AppColors.DARK_PRIMARY_VARIANT,
                secondary_container=AppColors.DARK_PRIMARY_VARIANT,
                tertiary=AppColors.DARK_PRIMARY,
                tertiary_container=AppColors.DARK_PRIMARY_VARIANT,
                surface=AppColors.DARK_BG,
                on_surface=AppColors.DARK_TEXT,
                on_surface_variant=AppColors.DARK_TEXT_DIM,
                error=AppColors.ERROR,
                on_primary=AppColors.DARK_BG,
                on_secondary=AppColors.DARK_BG,
                on_tertiary=AppColors.DARK_BG,
                surface_container_highest=AppColors.DARK_SURFACE,
                outline=AppColors.DARK_DIVIDER,
            ),
        )

    @staticmethod
    def get_light_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=AppColors.LIGHT_PRIMARY,
                primary_container=AppColors.LIGHT_PRIMARY_VARIANT,
                secondary=AppColors.LIGHT_PRIMARY_VARIANT,
                secondary_container=AppColors.LIGHT_PRIMARY_VARIANT,
                tertiary=AppColors.LIGHT_PRIMARY,
                tertiary_container=AppColors.LIGHT_PRIMARY_VARIANT,
                surface=AppColors.LIGHT_BG,
                on_surface=AppColors.LIGHT_TEXT,
                on_surface_variant=AppColors.LIGHT_TEXT_DIM,
                error=AppColors.ERROR,
                on_primary=AppColors.LIGHT_BG,
                on_secondary=AppColors.LIGHT_BG,
                on_tertiary=AppColors.LIGHT_BG,
                surface_container_highest=AppColors.LIGHT_SURFACE,
                outline=AppColors.DIVIDER,
            ),
        )
