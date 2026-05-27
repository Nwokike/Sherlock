"""Design system — colors and themes."""

import flet as ft


class AppColors:
    PRIMARY = "#1A237E"
    PRIMARY_VARIANT = "#283593"
    SECONDARY = "#FFD54F"
    ACCENT = "#FF6F00"
    SUCCESS = "#4CAF50"
    WARNING = "#FF9800"
    ERROR = "#F44336"
    SURFACE = "#FFFFFF"
    SURFACE_VARIANT = "#F5F5F5"
    DARK_BG = "#0D0D1A"
    DARK_SURFACE = "#1A1A2E"
    DARK_SURFACE_VARIANT = "#252540"
    DARK_TEXT = "#FFFFFF"
    LIGHT_TEXT = "#1A1A1A"
    SUBTITLE = "#757575"
    DIVIDER = "#E0E0E0"
    DARK_DIVIDER = "#333355"


class AppTheme:
    @staticmethod
    def get_dark_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme_seed=AppColors.PRIMARY,
            color_scheme=ft.ColorScheme(
                primary=AppColors.PRIMARY,
                primary_container=AppColors.PRIMARY_VARIANT,
                secondary=AppColors.SECONDARY,
                surface=AppColors.DARK_SURFACE,
                surface_variant=AppColors.DARK_SURFACE_VARIANT,
                error=AppColors.ERROR,
                on_primary=ft.Colors.WHITE,
                on_secondary=ft.Colors.BLACK,
                on_surface=ft.Colors.WHITE,
                on_surface_variant=AppColors.DARK_TEXT,
                on_error=ft.Colors.WHITE,
            ),
        )

    @staticmethod
    def get_light_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme_seed=AppColors.PRIMARY,
            color_scheme=ft.ColorScheme(
                primary=AppColors.PRIMARY,
                primary_container=AppColors.PRIMARY_VARIANT,
                secondary=AppColors.SECONDARY,
                surface=AppColors.SURFACE,
                surface_variant=AppColors.SURFACE_VARIANT,
                error=AppColors.ERROR,
                on_primary=ft.Colors.WHITE,
                on_secondary=ft.Colors.BLACK,
                on_surface=AppColors.LIGHT_TEXT,
                on_surface_variant=AppColors.SUBTITLE,
                on_error=ft.Colors.WHITE,
            ),
        )
