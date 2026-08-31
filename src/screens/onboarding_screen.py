"""OnboardingScreen — first-launch 3-slide introduction to Sherlock.

Premium onboarding with swipe gestures, animated dots, and gradient backdrop.
@ft.component — reads/writes observable state via AppStateCtx.
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft
from flet import Control

from core import tokens
from core.constants import STORAGE_ONBOARDING_DONE
from core.theme import AppColors

logger = logging.getLogger("OnboardingScreen")

_SLIDES = [
    {
        "icon": ft.Icons.PERSON_SEARCH_ROUNDED,
        "color": AppColors.PRIMARY,
        "title": "Hunt Across\n400+ Networks",
        "body": (
            "Scan major social platforms simultaneously — GitHub, X, "
            "Instagram, TikTok, Reddit, Spotify, and more — to find active "
            "accounts by username in seconds."
        ),
    },
    {
        "icon": ft.Icons.ALTERNATE_EMAIL_ROUNDED,
        "color": AppColors.ACCENT,
        "title": "Email OSINT\nMade Easy",
        "body": (
            "Switch to Email mode to check 120+ platforms at once. "
            "Uncover masked recovery emails, phone hints, full names, "
            "account creation dates, and more."
        ),
    },
    {
        "icon": ft.Icons.DOWNLOAD_ROUNDED,
        "color": AppColors.PRIMARY,
        "title": "Premium\nData Exports",
        "body": (
            "Export complete scanning reports as beautifully formatted "
            "Excel, CSV, or Text lists — directly to your device in one tap."
        ),
    },
]


def _build_slide(s: dict) -> ft.Column:
    return ft.Column(
        [
            ft.Container(
                content=ft.Icon(s["icon"], size=tokens.ICON_FEATURE, color=s["color"]),
                width=tokens.ICON_FEATURE + 54,
                height=tokens.ICON_FEATURE + 54,
                border_radius=(tokens.ICON_FEATURE + 54) // 2,
                bgcolor=ft.Colors.with_opacity(tokens.OPACITY_LIGHT, s["color"]),
                alignment=ft.Alignment.CENTER,
            ),
            ft.Container(height=tokens.SPACE_XL),
            ft.Text(
                s["title"],
                size=tokens.FONT_XXL,
                weight=ft.FontWeight.W_800,
                text_align=ft.TextAlign.CENTER,
                color=ft.Colors.ON_SURFACE,
                font_family="Outfit",
            ),
            ft.Container(height=tokens.SPACE_MD),
            ft.Text(
                s["body"],
                size=tokens.FONT_MD,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align=ft.TextAlign.CENTER,
                font_family="Outfit",
            ),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=0,
    )


@ft.component
def OnboardingScreen() -> Control:
    from state.app_state import AppStateCtx
    from state.controller_ctx import ControllerMethodsCtx

    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page_idx, set_page_idx = ft.use_state(0)

    is_last = page_idx == len(_SLIDES) - 1

    async def _finish():
        from flet import context

        page = context.page
        try:
            if controller.set_onboarding_done:
                await controller.set_onboarding_done()
            else:
                from services.storage_service import StorageService

                storage = StorageService(page)
                await storage.set(STORAGE_ONBOARDING_DONE, "true")
                await storage.flush()
        except Exception:
            pass
        state.has_accepted_terms = True
        state.is_first_launch = False

    def _on_next(e=None):
        if is_last:
            asyncio.create_task(_finish())
        else:
            set_page_idx(page_idx + 1)

    def _on_skip(e):
        asyncio.create_task(_finish())

    def _on_swipe(e: ft.DragEndEvent):
        if e.primary_velocity is not None:
            if e.primary_velocity < -200 and not is_last:
                set_page_idx(min(page_idx + 1, len(_SLIDES) - 1))
            elif e.primary_velocity > 200 and page_idx > 0:
                set_page_idx(page_idx - 1)

    # Dot indicators
    dots = []
    for i in range(len(_SLIDES)):
        is_active = i == page_idx
        dots.append(
            ft.Container(
                width=24 if is_active else 8,
                height=8,
                border_radius=4,
                bgcolor=ft.Colors.PRIMARY
                if is_active
                else ft.Colors.with_opacity(tokens.OPACITY_LIGHT, ft.Colors.ON_SURFACE),
                animate=ft.Animation(tokens.ANIM_SLOW, "easeOut"),
            )
        )

    return ft.Container(
        expand=True,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=[
                ft.Colors.SURFACE,
                ft.Colors.with_opacity(0.06, AppColors.PRIMARY),
            ],
        ),
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                # Top bar — Skip button
                ft.Container(
                    padding=ft.Padding(
                        tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, 0
                    ),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton(
                                "Skip",
                                on_click=_on_skip,
                                style=ft.ButtonStyle(
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ),
                        ],
                    ),
                ),
                # Middle — swipeable slide content fills all remaining space
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment.CENTER,
                    content=ft.GestureDetector(
                        content=ft.Container(
                            content=_build_slide(_SLIDES[page_idx]),
                            alignment=ft.Alignment.CENTER,
                            padding=ft.Padding(tokens.SPACE_XL, 0, tokens.SPACE_XL, 0),
                        ),
                        on_horizontal_drag_end=_on_swipe,
                    ),
                ),
                # Bottom — dots + CTA button pinned to bottom
                ft.Container(
                    padding=ft.Padding(
                        tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_XXL
                    ),
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=tokens.SPACE_LG,
                        controls=[
                            # Dot indicators
                            ft.Row(
                                controls=dots,
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=tokens.SPACE_SM,
                            ),
                            # CTA button
                            ft.FilledButton(
                                content=ft.Text(
                                    "Get Started" if is_last else "Next",
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_600,
                                    font_family="Outfit",
                                    color=ft.Colors.WHITE,
                                ),
                                icon=ft.Icons.CHECK_ROUNDED
                                if is_last
                                else ft.Icons.ARROW_FORWARD_ROUNDED,
                                on_click=_on_next,
                                width=220,
                                height=52,
                                style=ft.ButtonStyle(
                                    shape=ft.RoundedRectangleBorder(
                                        radius=tokens.RADIUS_XL
                                    ),
                                ),
                            ),
                        ],
                    ),
                ),
            ],
        ),
    )
