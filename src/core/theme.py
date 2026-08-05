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

    @staticmethod
    def get_bg(page: ft.Page | None = None) -> str:
        resolved = AppColors._resolve_page(page)
        return AppColors.DARK_BG_1 if is_dark_mode(resolved) else AppColors.LIGHT_BG

    @staticmethod
    def get_surface(page: ft.Page | None = None) -> str:
        resolved = AppColors._resolve_page(page)
        return AppColors.DARK_SURFACE if is_dark_mode(resolved) else AppColors.LIGHT_SURFACE

    @staticmethod
    def get_surface_2(page: ft.Page | None = None) -> str:
        resolved = AppColors._resolve_page(page)
        return AppColors.DARK_SURFACE_2 if is_dark_mode(resolved) else AppColors.LIGHT_SURFACE_2

    @staticmethod
    def get_border(page: ft.Page | None = None) -> str:
        resolved = AppColors._resolve_page(page)
        return AppColors.DARK_BORDER if is_dark_mode(resolved) else AppColors.LIGHT_BORDER

    @staticmethod
    def get_text(page: ft.Page | None = None) -> str:
        resolved = AppColors._resolve_page(page)
        return AppColors.DARK_TEXT if is_dark_mode(resolved) else AppColors.LIGHT_TEXT

    @staticmethod
    def get_text_dim(page: ft.Page | None = None) -> str:
        resolved = AppColors._resolve_page(page)
        return AppColors.DARK_TEXT_DIM if is_dark_mode(resolved) else AppColors.LIGHT_TEXT_DIM

    @staticmethod
    def grey_dim(page=None) -> str:
        try:
            if page is None:
                from flet import context

                page = context.page
            return AppColors.DARK_TEXT_DIM if is_dark_mode(page) else AppColors.LIGHT_TEXT_DIM
        except Exception:
            return AppColors.LIGHT_TEXT_DIM


def is_dark_mode(page: ft.Page | None) -> bool:
    """Check if the page is in dark mode (explicit or system)."""
    if page is None:
        try:
            from flet import context as flet_context

            page = flet_context.page
        except Exception:
            return True
    if page is None:
        return True
    return page.theme_mode == ft.ThemeMode.DARK or (
        page.theme_mode == ft.ThemeMode.SYSTEM
        and page.platform_brightness == ft.Brightness.DARK
    )


# ─── Glass Pattern (DDGS style) ────────────────────────────────────────

DARK_GLASS_BG = ft.Colors.with_opacity(0.05, ft.Colors.WHITE)
DARK_GLASS_BORDER = ft.Colors.with_opacity(0.10, ft.Colors.WHITE)
LIGHT_GLASS_BG = ft.Colors.with_opacity(0.04, ft.Colors.BLACK)
LIGHT_GLASS_BORDER = ft.Colors.with_opacity(0.08, ft.Colors.BLACK)


def adaptive_glass_bg(page: ft.Page | None = None) -> str:
    """Card background for current theme."""
    if page and not is_dark_mode(page):
        return LIGHT_GLASS_BG
    return DARK_GLASS_BG


def adaptive_glass_border(page: ft.Page | None = None) -> str:
    """Card border for current theme."""
    if page and not is_dark_mode(page):
        return LIGHT_GLASS_BORDER
    return DARK_GLASS_BORDER


# ─── Styles (DDGS pattern) ─────────────────────────────────────────────


class AppStyles:
    RADIUS_SMALL = 8
    RADIUS = 12
    RADIUS_LARGE = 20

    PADDING_SMALL = 8
    PADDING = 16
    PADDING_LARGE = 24

    @staticmethod
    def section_card(title: str, icon: str, content: ft.Control, page: ft.Page | None = None) -> ft.Container:
        """Frosted card section with icon header."""
        is_dark = is_dark_mode(page)
        border_color = AppColors.DARK_BORDER if is_dark else AppColors.LIGHT_BORDER
        bg_color = AppColors.DARK_SURFACE if is_dark else AppColors.LIGHT_SURFACE

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, color=AppColors.PRIMARY, size=18),
                            ft.Text(
                                title,
                                size=14,
                                weight=ft.FontWeight.W_600,
                                font_family="Outfit",
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.Divider(
                        height=1,
                        color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                    ),
                    content,
                ],
                spacing=12,
            ),
            padding=16,
            border_radius=AppStyles.RADIUS,
            bgcolor=bg_color,
            border=ft.Border.all(1, border_color),
        )

    @staticmethod
    def glass_card(content: ft.Control, page: ft.Page | None = None) -> ft.Container:
        """Frosted glass card."""
        return ft.Container(
            content=content,
            bgcolor=adaptive_glass_bg(page),
            border=ft.Border.all(1, adaptive_glass_border(page)),
            border_radius=AppStyles.RADIUS,
        )

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
        else:
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
        )
