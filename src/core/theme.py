"""Sherlock design system — gold brand identity with Material 3.

Colors derived from Sherlock's logo: Khaki-Gold primary, Caramel-Gold accent.
Dark mode uses deep slate surfaces. Glass pattern for premium cards.
"""

from __future__ import annotations

import flet as ft


class AppColors:
    """Sherlock brand palette — gold detective identity."""

    # ─── BRAND PRIMARY (Gold) ────────────────────────────────────────────────
    PRIMARY = "#A68E59"  # Khaki-Gold (Logo Color A)
    PRIMARY_LIGHT = "#CD995F"  # Caramel-Gold (Logo Color B)
    PRIMARY_DARK = "#8A7347"  # Deep Gold
    ACCENT = "#0EA5E9"  # Sky Blue accent

    # ─── STATUS ─────────────────────────────────────────────────────────────
    SUCCESS = "#2E7D32"  # Clean Material Green
    WARNING = "#F9A825"  # Amber Gold
    ERROR = "#D32F2F"  # Red
    GREY = "#9E9E9E"  # Neutral grey for inactive chips

    # ─── LOG TERMINAL (Diagnostic Activity) ──────────────────────────────────
    TERMINAL_BG = "#0D0D0D"  # Monospace terminal background
    TERMINAL_GREEN = "#A6E22E"  # Monokai green terminal text

    # ─── DARK MODE (Premium Neutral Slate) ──────────────────────────────────
    DARK_BG_1 = "#0F1114"  # Deep Slate-Black
    DARK_BG_2 = "#121518"  # Slate Surface
    DARK_SURFACE = "#1A1D22"  # Card Background
    DARK_SURFACE_2 = "#252A30"  # Dialog Background
    DARK_BORDER = "#2E3339"  # Outline / Divider
    DARK_TEXT = "#ECEFF1"  # Primary Text
    DARK_TEXT_DIM = "#90A4AE"  # Secondary text

    # ─── LIGHT MODE (Clean Neutral) ─────────────────────────────────────────
    LIGHT_BG = "#FAFAFA"  # Clean warm background
    LIGHT_SURFACE = "#FFFFFF"  # White Cards
    LIGHT_SURFACE_2 = "#F5F5F5"  # Soft focus surface
    LIGHT_BORDER = "#E0E0E0"  # Soft divider
    LIGHT_TEXT = "#000000"  # Pure black — maximum contrast
    LIGHT_TEXT_DIM = "#424242"  # Dark grey for secondary text

    @staticmethod
    def _resolve_page(page: ft.Page | None) -> ft.Page | None:
        if page is not None:
            return page
        try:
            from flet import context as flet_context

            return flet_context.page
        except Exception:
            return None


def is_dark_mode(page: ft.Page | None = None) -> bool:
    """Check if the page is in dark mode (explicit or system)."""
    if page is None:
        try:
            from flet import context as flet_context

            page = flet_context.page
        except Exception:
            page = None
    if page is None:
        from core.state import state

        return getattr(state, "theme_mode", None) != ft.ThemeMode.LIGHT
    return (
        page.theme_mode == ft.ThemeMode.DARK
        or (
            page.theme_mode in (ft.ThemeMode.SYSTEM, None)
            and page.platform_brightness == ft.Brightness.DARK
        )
    )


# ─── Glass Pattern (DDGS style) ────────────────────────────────────────

DARK_GLASS_BG = ft.Colors.with_opacity(0.05, ft.Colors.WHITE)
DARK_GLASS_BORDER = ft.Colors.with_opacity(0.10, ft.Colors.WHITE)
LIGHT_GLASS_BG = ft.Colors.with_opacity(0.04, ft.Colors.BLACK)
LIGHT_GLASS_BORDER = ft.Colors.with_opacity(0.08, ft.Colors.BLACK)


def adaptive_glass_bg(page: ft.Page | None = None) -> str:
    """Card background for current theme."""
    if not is_dark_mode(page):
        return LIGHT_GLASS_BG
    return DARK_GLASS_BG


def adaptive_glass_border(page: ft.Page | None = None) -> str:
    """Card border for current theme."""
    if not is_dark_mode(page):
        return LIGHT_GLASS_BORDER
    return DARK_GLASS_BORDER


# ─── Styles ────────────────────────────────────────────────────────────


class AppStyles:
    @staticmethod
    def brand_gradient(page: ft.Page | None = None):
        """Clean neutral background gradient."""
        is_dark = is_dark_mode(page)
        if is_dark:
            return ft.LinearGradient(
                begin=ft.Alignment.TOP_CENTER,
                end=ft.Alignment.BOTTOM_CENTER,
                colors=[AppColors.DARK_BG_1, AppColors.DARK_BG_2],
            )
        return ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=["#F5F5F5", AppColors.LIGHT_BG],
        )


# ─── Material 3 Themes ─────────────────────────────────────────────────


class AppTheme:
    @staticmethod
    def get_light_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=AppColors.PRIMARY,
                on_primary=ft.Colors.WHITE,
                primary_container=ft.Colors.with_opacity(0.12, AppColors.PRIMARY),
                on_primary_container=AppColors.PRIMARY,
                secondary=AppColors.ACCENT,
                on_secondary=ft.Colors.WHITE,
                surface=AppColors.LIGHT_BG,
                on_surface=AppColors.LIGHT_TEXT,
                surface_container=AppColors.LIGHT_SURFACE,
                surface_container_highest=AppColors.LIGHT_SURFACE_2,
                on_surface_variant=AppColors.LIGHT_TEXT_DIM,
                error=AppColors.ERROR,
                on_error=ft.Colors.WHITE,
                outline=AppColors.LIGHT_BORDER,
                outline_variant=AppColors.LIGHT_SURFACE_2,
            ),
            font_family="Outfit",
            visual_density=ft.VisualDensity.COMFORTABLE,
            scrollbar_theme=ft.ScrollbarTheme(
                thumb_color=AppColors.PRIMARY,
                thickness=4,
                radius=4,
            ),
            snackbar_theme=ft.SnackBarTheme(
                behavior=ft.SnackBarBehavior.FLOATING,
                shape=ft.RoundedRectangleBorder(radius=12),
                bgcolor=AppColors.DARK_SURFACE_2,
            ),
            tab_bar_theme=ft.TabBarTheme(
                indicator_size=ft.TabBarIndicatorSize.TAB,
                label_color=AppColors.PRIMARY,
                divider_color=ft.Colors.TRANSPARENT,
            ),
            card_theme=ft.CardTheme(
                elevation=1,
                shape=ft.RoundedRectangleBorder(radius=12),
            ),
            chip_theme=ft.ChipTheme(
                show_checkmark=True,
                shape=ft.RoundedRectangleBorder(radius=20),
            ),
            page_transitions=ft.PageTransitionsTheme(
                android=ft.PageTransitionTheme.CUPERTINO,
                ios=ft.PageTransitionTheme.CUPERTINO,
            ),
        )

    @staticmethod
    def get_dark_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=AppColors.PRIMARY,
                on_primary=ft.Colors.WHITE,
                primary_container=ft.Colors.with_opacity(0.15, AppColors.PRIMARY_LIGHT),
                on_primary_container=AppColors.PRIMARY_LIGHT,
                secondary=AppColors.ACCENT,
                on_secondary=ft.Colors.WHITE,
                surface=AppColors.DARK_BG_1,
                on_surface=AppColors.DARK_TEXT,
                surface_container=AppColors.DARK_SURFACE,
                surface_container_highest=AppColors.DARK_SURFACE_2,
                on_surface_variant=AppColors.DARK_TEXT_DIM,
                error=AppColors.ERROR,
                on_error=ft.Colors.WHITE,
                outline=AppColors.DARK_BORDER,
                outline_variant=AppColors.DARK_SURFACE_2,
            ),
            font_family="Outfit",
            visual_density=ft.VisualDensity.COMFORTABLE,
            scrollbar_theme=ft.ScrollbarTheme(
                thumb_color=AppColors.PRIMARY,
                thickness=4,
                radius=4,
            ),
            snackbar_theme=ft.SnackBarTheme(
                behavior=ft.SnackBarBehavior.FLOATING,
                shape=ft.RoundedRectangleBorder(radius=12),
                bgcolor=AppColors.DARK_SURFACE_2,
            ),
            tab_bar_theme=ft.TabBarTheme(
                indicator_size=ft.TabBarIndicatorSize.TAB,
                label_color=AppColors.PRIMARY,
                divider_color=ft.Colors.TRANSPARENT,
            ),
            card_theme=ft.CardTheme(
                elevation=2,
                shape=ft.RoundedRectangleBorder(radius=12),
            ),
            chip_theme=ft.ChipTheme(
                show_checkmark=True,
                shape=ft.RoundedRectangleBorder(radius=20),
            ),
            page_transitions=ft.PageTransitionsTheme(
                android=ft.PageTransitionTheme.CUPERTINO,
                ios=ft.PageTransitionTheme.CUPERTINO,
            ),
        )
