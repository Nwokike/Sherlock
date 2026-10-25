"""SettingsScreen — search parameters, theme, and database updates.

@ft.component — reads/writes observable state via AppStateCtx.
Premium settings with grouped cards, modern switches, and clear hierarchy.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from urllib.parse import urlparse

import flet as ft
from flet import Control

from components.app_header import AppHeader
from components.banner_ad import pooled_banner_ad
from components.section_header import SectionHeader
from core import tokens
from core.constants import (
    APP_BUILD_NUMBER,
    APP_NAME,
    APP_VERSION,
    STORAGE_ALLOW_LOUD,
    STORAGE_CHECK_DOMAINS,
    STORAGE_COOKIES_PATH,
    STORAGE_CROSS_DEPTH,
    STORAGE_CROSS_EMAILS,
    STORAGE_CROSS_LINKS,
    STORAGE_CROSS_SCAN,
    STORAGE_CROSS_SWEEP,
    STORAGE_DEEP_ENRICH,
    STORAGE_DNS_RESOLVER,
    STORAGE_EMAIL_CONCURRENCY,
    STORAGE_EMAIL_DOMAINS,
    STORAGE_EMAIL_ONLY_FOUND,
    STORAGE_EMAIL_TIMEOUT,
    STORAGE_EXCLUSIONS,
    STORAGE_EXTRACT_INFO,
    STORAGE_I2P_PROXY,
    STORAGE_LOCAL_DB,
    STORAGE_LOG_ENGINE_LOGS,
    STORAGE_MANIFEST,
    STORAGE_MAX_CONNECTIONS,
    STORAGE_NO_PASSWORD_RECOVERY,
    STORAGE_NSFW,
    STORAGE_PERMUTE,
    STORAGE_PHONE_CONCURRENCY,
    STORAGE_PROXY_FILE,
    STORAGE_PROXY_URL,
    STORAGE_RECURSIVE_SEARCH,
    STORAGE_RETRIES,
    STORAGE_SAFE_SEARCH,
    STORAGE_SCAN_DEPTH,
    STORAGE_SEARCH_KEYWORDS,
    STORAGE_SHOW_ALL_RESULTS,
    STORAGE_THEME,
    STORAGE_TIMEOUT,
    STORAGE_USE_CURL_CFFI,
    STORAGE_VERBOSE_OUTPUT,
)
from core.logger_handler import get_telemetry_snapshot, in_memory_log_handler
from core.notify import show_snack
from core.tasks import spawn
from core.theme import AppColors, is_dark_mode
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("SettingsScreen")


_PROXY_SCHEMES = ("http", "https", "socks5", "socks5h")


def _parse_proxy(value: str) -> str | None:
    """Validate a proxy URL. Returns error reason, or None if valid.

    Empty string = direct connection (valid). Rejects bare schemes
    (``http://`` with no host), unknown schemes, and out-of-range ports.
    """
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    try:
        parts = urlparse(cleaned)
    except Exception:
        return "unparseable URL"
    if parts.scheme.lower() not in _PROXY_SCHEMES:
        return "scheme must be http://, https://, socks5:// or socks5h://"
    if not parts.hostname:
        return "missing host (bare scheme is not a proxy)"
    try:
        port = parts.port
    except ValueError:
        return "invalid port"
    if port is not None and not (1 <= port <= 65535):
        return f"port {port} out of range 1-65535"
    return None


def _validate_manifest(value: str) -> str | None:
    """Validate a custom site-DB manifest. Returns error reason, or None.

    Empty = bundled DB (valid). Format-only, no network I/O: URLs are checked
    for shape (https required), local paths for existence + JSON object with
    a ``sites`` key. Reachability is left to load_sites(), which falls back
    with a log there.
    """
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    low = cleaned.lower()
    if low.startswith(("http://", "https://")):
        try:
            parts = urlparse(cleaned)
        except Exception:
            return "unparseable URL"
        if not parts.hostname:
            return "URL has no host"
        if parts.scheme.lower() == "http":
            return "use https:// for manifests (http rejected)"
        return None
    if not os.path.isfile(cleaned):
        return "file not found"
    try:
        import json

        with open(cleaned, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return "not valid JSON"
    if not isinstance(data, dict) or "sites" not in data:
        return 'JSON must be an object with a "sites" key'
    return None


@ft.component
def SettingsTextField(
    value: str,
    on_commit=None,
    *,
    hint_text: str = "",
    width: int | None = None,
):
    """A settings text field that never loses what you typed.

    `value` is the committed state, not the draft. The draft lives in local
    state and only reaches the parent on submit/blur, so a whole-screen
    re-render from some unrelated `AppState` write (a scan progress tick, a
    sites reload) cannot reset the field mid-keystroke. Same isolation
    `SitesSearchBar` already uses for the same reason.

    If the parent rejects the value (`on_commit` returns False), the draft
    snaps back to the committed state instead of holding a bad value.
    """
    draft, set_draft = ft.use_state(value or "")
    last_committed, set_last_committed = ft.use_state(value or "")

    def _commit():
        if on_commit is None:
            return
        if draft == last_committed:
            return
        if on_commit(draft) is not False:
            set_last_committed(draft)
            return
        set_draft(value or "")

    return ft.TextField(
        value=draft,
        hint_text=hint_text,
        width=width,
        border={
            ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                border_radius=tokens.RADIUS_SM,
            ),
            ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                side=ft.BorderSide(color=ft.Colors.PRIMARY),
                border_radius=tokens.RADIUS_SM,
            ),
        },
        text_size=tokens.FONT_SM,
        content_padding=tokens.SPACE_XS,
        # A TextField is editable by nature, so its contents are already
        # selectable — `selectable=` is a Text property and is rejected here.
        on_change=lambda e: set_draft(e.control.value),
        on_submit=lambda e: _commit(),
        on_blur=lambda e: _commit(),
    )


def _setting_row(
    icon: ft.IconData,
    title: str,
    subtitle: str,
    trailing: Control,
    stacked: bool = False,
) -> ft.Container:
    """Reusable settings row with icon + text + trailing control.

    On narrow screens (`stacked=True`) the trailing control moves to its
    own line below the description instead of competing for horizontal
    space — SegmentedButtons and Sliders otherwise squeeze the subtitle
    or overflow on phones. Wide layouts are unchanged.
    """
    icon_box = ft.Container(
        content=ft.Icon(
            icon,
            size=tokens.ICON_MD,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
        width=tokens.ICON_BACKDROP,
        height=tokens.ICON_BACKDROP,
        border_radius=tokens.ICON_BACKDROP_RADIUS,
        bgcolor=ft.Colors.with_opacity(tokens.OPACITY_LIGHT, ft.Colors.ON_SURFACE),
        alignment=ft.Alignment.CENTER,
    )
    text_col = ft.Column(
        controls=[
            ft.Text(
                title,
                size=tokens.FONT_MD,
                weight=ft.FontWeight.W_500,
            ),
            ft.Text(
                subtitle,
                size=tokens.FONT_XS,
                color=ft.Colors.with_opacity(tokens.OPACITY_DIM, ft.Colors.ON_SURFACE),
            ),
        ],
        spacing=tokens.SPACE_XXS,
        expand=True,
    )

    if stacked:
        # Sliders and SegmentedButtons stretch across the second line;
        # switches/buttons keep their natural size under the text indent.
        stretches = isinstance(trailing, (ft.Slider, ft.SegmentedButton))
        trailing_line = ft.Row(
            controls=[
                ft.Container(width=tokens.ICON_BACKDROP + tokens.SPACE_MD),
                (ft.Row(controls=[trailing], expand=True) if stretches else trailing),
            ],
            spacing=0,
        )
        content = ft.Column(
            controls=[
                ft.Row(
                    controls=[icon_box, text_col],
                    spacing=tokens.SPACE_MD,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                trailing_line,
            ],
            spacing=tokens.SPACE_XS,
        )
    else:
        content = ft.Row(
            controls=[icon_box, text_col, trailing],
            spacing=tokens.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    return ft.Container(
        content=content,
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_MD,
        ),
    )


def _settings_card(controls: list[Control]) -> ft.Container:
    """Grouped settings card with Material 3 surface."""
    return ft.Container(
        content=ft.Column(controls=controls, spacing=0),
        margin=ft.Margin(tokens.SPACE_XL, 0, tokens.SPACE_XL, tokens.SPACE_SM),
        border_radius=tokens.RADIUS_LG,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(
            width=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )


@ft.component
def SettingsScreen(banner: Control | None = None) -> Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    from flet import context

    try:
        page = context.page
    except Exception:
        page = None

    # Narrow screens stack each setting's control under its description —
    # one-line rows squeeze subtitles and overflow SegmentedButtons.
    narrow = bool(page and getattr(page, "width", None) and page.width < 600)
    is_mobile = bool(page and hasattr(page, "platform") and page.platform.is_mobile())
    health_running, set_health_running = ft.use_state(False)

    async def _on_theme_change(val: str):
        if page is None:
            return
        if val == "system":
            new_mode = ft.ThemeMode.SYSTEM
        elif val == "light":
            new_mode = ft.ThemeMode.LIGHT
        else:
            new_mode = ft.ThemeMode.DARK
        page.theme_mode = new_mode
        state.theme_mode = new_mode
        # Pooled banner ads freeze their glass colours at first build; clearing
        # here is what clear_banner_pool's docstring says it does on a theme
        # change (the header's theme-cycle button does the same).
        try:
            from components.banner_ad import clear_banner_pool

            clear_banner_pool()
        except Exception:
            pass
        from services.storage_service import StorageService

        storage = StorageService(page)
        await storage.set(STORAGE_THEME, val)
        await storage.flush()
        try:
            page.update()
        except Exception:
            pass

    def _create_theme_card(mode: str, label: str, icon: ft.IconData) -> ft.Container:
        curr_mode = (
            page.theme_mode
            if page and hasattr(page, "theme_mode")
            else state.theme_mode
        )
        is_sel = (
            (mode == "dark" and curr_mode == ft.ThemeMode.DARK)
            or (mode == "light" and curr_mode == ft.ThemeMode.LIGHT)
            or (
                mode == "system"
                and (curr_mode == ft.ThemeMode.SYSTEM or curr_mode is None)
            )
        )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        icon,
                        color=AppColors.PRIMARY
                        if is_sel
                        else ft.Colors.ON_SURFACE_VARIANT,
                        size=tokens.ICON_SM,
                    ),
                    ft.Text(
                        label,
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL,
                        color=AppColors.PRIMARY if is_sel else ft.Colors.ON_SURFACE,
                        font_family="Outfit",
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
            ),
            padding=ft.Padding(8, 8, 8, 8),
            border_radius=tokens.RADIUS_SM,
            border=ft.Border.all(
                1.5 if is_sel else 1,
                AppColors.PRIMARY
                if is_sel
                else ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE),
            ),
            bgcolor=(
                ft.Colors.with_opacity(0.10, AppColors.PRIMARY)
                if is_sel
                else ft.Colors.TRANSPARENT
            ),
            expand=True,
            ink=True,
            on_click=lambda e, m=mode: spawn(_on_theme_change(m)),
            animate=ft.Animation(tokens.ANIM_FAST, ft.AnimationCurve.EASE_OUT),
        )

    def _set_nsfw(val: bool):
        """Single writer for the NSFW toggle pair.

        The engine reads only ``nsfw_enabled``; ``safe_search`` is kept as a
        derived mirror so the two storage keys can never diverge.
        """
        state.nsfw_enabled = bool(val)
        state.safe_search = not bool(val)
        spawn(_persist(STORAGE_NSFW, "true" if val else "false"))
        spawn(_persist(STORAGE_SAFE_SEARCH, "false" if val else "true"))
        if controller.refresh_sites:
            spawn(controller.refresh_sites())

    def _toggle_nsfw(val: bool):
        _set_nsfw(bool(val))

    def _toggle_exclusions(val: bool):
        state.ignore_exclusions = val
        spawn(_persist(STORAGE_EXCLUSIONS, "true" if val else "false"))
        if controller.refresh_sites:
            spawn(controller.refresh_sites())

    def _toggle_local_db(val: bool):
        state.use_local_db = val
        spawn(_persist(STORAGE_LOCAL_DB, "true" if val else "false"))
        if controller.refresh_sites:
            spawn(controller.refresh_sites())

    def _on_manifest_submit(val: str) -> bool:
        raw = val or ""
        err = _validate_manifest(raw)
        if err is not None:
            show_snack(page, f"Invalid manifest: {err}.", bgcolor=AppColors.WARNING)
            return False
        val = raw.strip()
        state.custom_manifest = val
        spawn(_persist(STORAGE_MANIFEST, val))
        if controller.refresh_sites:
            spawn(controller.refresh_sites())
        return True

    def _slider_live(label_fmt: str):
        """on_change handler: update the bubble label only (no state/persist)."""

        def _live(e):
            try:
                e.control.label = label_fmt.format(int(e.control.value))
                e.control.update()
            except Exception:
                pass

        return _live

    def _slider_commit(storage_key: str, apply):
        """on_change_end handler: commit state + persist once per gesture."""

        def _commit(e):
            try:
                v = int(e.control.value)
            except (TypeError, ValueError):
                return
            apply(v)
            spawn(_persist(storage_key, str(v)))
            try:
                e.control.update()
            except Exception:
                pass

        return _commit

    def _apply_timeout(v: int):
        state.timeout = max(5, min(60, v))

    def _apply_email_timeout(v: int):
        state.email_timeout = max(10, min(60, v))

    def _apply_email_concurrency(v: int):
        state.email_concurrency = max(5, min(30, v))

    def _apply_max_connections(v: int):
        state.max_connections = max(10, min(200, v))

    def _toggle_email_only_found(val: bool):
        state.email_only_found = val
        spawn(_persist(STORAGE_EMAIL_ONLY_FOUND, "true" if val else "false"))

    def _on_proxy_change(val: str) -> bool:
        raw = val or ""
        err = _parse_proxy(raw)
        if err is not None:
            show_snack(page, f"Invalid proxy URL: {err}.", bgcolor=AppColors.WARNING)
            return False
        cleaned = raw.strip()
        state.proxy_url = cleaned
        spawn(_persist(STORAGE_PROXY_URL, cleaned))
        return True

    def _on_keywords_change(val: str):
        cleaned = (val or "").strip()
        state.search_keywords = cleaned
        spawn(_persist(STORAGE_SEARCH_KEYWORDS, cleaned))

    def _on_deep_enrich_change(val: bool):
        state.deep_enrich = bool(val)
        spawn(_persist(STORAGE_DEEP_ENRICH, "true" if val else "false"))

    def _on_cookies_change(val: str) -> bool:
        raw = (val or "").strip()
        if raw and not os.path.isfile(raw):
            show_snack(
                page, f"Cookies file not found: {raw}", bgcolor=AppColors.WARNING
            )
            return False
        state.cookies_path = raw
        spawn(_persist(STORAGE_COOKIES_PATH, raw))
        return True

    def _on_i2p_change(val: str) -> bool:
        raw = val or ""
        err = _parse_proxy(raw)
        if err is not None:
            show_snack(page, f"Invalid I2P gateway: {err}.", bgcolor=AppColors.WARNING)
            return False
        cleaned = raw.strip()
        state.i2p_proxy = cleaned
        spawn(_persist(STORAGE_I2P_PROXY, cleaned))
        return True

    def _on_check_domains_change(val: bool):
        state.check_domains = bool(val)
        spawn(_persist(STORAGE_CHECK_DOMAINS, "true" if val else "false"))

    async def _run_db_health_check(e=None):
        if health_running:
            show_snack(page, "Health check already running…")
            return
        if page is None:
            return
        if not controller.run_db_health:
            return
        set_health_running(True)
        btn = e.control if e is not None and hasattr(e, "control") else None
        if btn is not None:
            btn.disabled = True
            with contextlib.suppress(Exception):
                btn.update()
        show_snack(page, "DB health: probing 25 sites… (takes up to a minute)")
        try:
            await controller.run_db_health()
        except Exception as exc:
            logger.exception("DB health check crashed")
            show_snack(
                page, f"DB health failed: {exc}", bgcolor=AppColors.ERROR, duration=8000
            )
        finally:
            set_health_running(False)
            if btn is not None:
                btn.disabled = False
                with contextlib.suppress(Exception):
                    btn.update()

    def _toggle_no_password_recovery(val: bool):
        state.no_password_recovery = val
        spawn(_persist(STORAGE_NO_PASSWORD_RECOVERY, "true" if val else "false"))

    def _on_scan_depth_change(val: str):
        state.scan_depth = val
        spawn(_persist(STORAGE_SCAN_DEPTH, val))
        # Guarded like every other call site: a context that provides no
        # refresher would otherwise crash the toggle handler.
        if controller.refresh_sites:
            spawn(controller.refresh_sites())

    def _toggle_recursive_search(val: bool):
        state.recursive_search = val
        spawn(_persist(STORAGE_RECURSIVE_SEARCH, "true" if val else "false"))

    def _toggle_permute(val: bool):
        state.permute_enabled = val
        spawn(_persist(STORAGE_PERMUTE, "true" if val else "false"))

    def _on_log_engine_change(val: bool):
        from core.logger_handler import set_engine_logs

        state.log_engine_logs = val
        # Apply immediately — otherwise the toggle has to wait for a restart
        # to affect anything already running.
        set_engine_logs(val)
        spawn(_persist(STORAGE_LOG_ENGINE_LOGS, "true" if val else "false"))

    def _toggle_extract_info(val: bool):
        state.extract_info = val
        spawn(_persist(STORAGE_EXTRACT_INFO, "true" if val else "false"))

    def _on_retries_change(val: str):
        state.retries = int(val)
        spawn(_persist(STORAGE_RETRIES, val))

    def _on_dns_resolver_change(val: str):
        state.dns_resolver = val
        spawn(_persist(STORAGE_DNS_RESOLVER, val))

    def _toggle_allow_loud(val: bool):
        state.allow_loud = val
        spawn(_persist(STORAGE_ALLOW_LOUD, "true" if val else "false"))

    def _toggle_show_all_results(val: bool):
        state.show_all_results = val
        spawn(_persist(STORAGE_SHOW_ALL_RESULTS, "true" if val else "false"))

    def _toggle_verbose_output(val: bool):
        state.verbose_output = val
        spawn(_persist(STORAGE_VERBOSE_OUTPUT, "true" if val else "false"))

    def _toggle_cross_scan(val: bool):
        state.cross_scan_enabled = val
        spawn(_persist(STORAGE_CROSS_SCAN, "true" if val else "false"))

    def _on_cross_links_change(val: str):
        state.cross_links = val
        spawn(_persist(STORAGE_CROSS_LINKS, val))

    def _on_cross_emails_change(val: str):
        state.cross_emails = val
        spawn(_persist(STORAGE_CROSS_EMAILS, val))

    def _on_cross_depth_change(val: str):
        state.cross_depth = int(val)
        spawn(_persist(STORAGE_CROSS_DEPTH, val))

    def _on_cross_sweep_change(val: str):
        state.cross_sweep = int(val)
        spawn(_persist(STORAGE_CROSS_SWEEP, val))

    def _on_email_domains_change(val: str):
        cleaned = (val or "").strip()
        if cleaned:
            try:
                from user_scanner.core.helpers import parse_email_domain_scopes
                scopes = [x.strip() for x in cleaned.split(",") if x.strip()]
                parse_email_domain_scopes(",".join(scopes))
            except ValueError as ve:
                if page:
                    show_snack(page, str(ve), bgcolor=AppColors.ERROR, duration=6000)
                return False
        state.email_domains = cleaned
        spawn(_persist(STORAGE_EMAIL_DOMAINS, state.email_domains))
        return True

    def _apply_phone_concurrency(val: int):
        state.phone_concurrency = max(5, min(30, int(val)))

    def _on_proxy_file_change(val: str):
        state.proxy_file = (val or "").strip()
        spawn(_persist(STORAGE_PROXY_FILE, state.proxy_file))

    async def _validate_proxies():
        from core.state import state as _state

        raw = (_state.proxy_url or "").strip()
        proxies = [p.strip() for p in raw.split(",") if p.strip()] if raw else []
        if _state.proxy_file:
            try:
                from pathlib import Path as _Path

                p = _Path(_state.proxy_file)
                if p.is_file():
                    proxies.extend(
                        ln.strip()
                        for ln in p.read_text(encoding="utf-8").splitlines()
                        if ln.strip()
                    )
            except Exception as exc:
                logger.debug("proxy file read failed: %s", exc)
        if not proxies:
            show_snack(page, "No proxy URL or proxy file set", bgcolor=AppColors.WARNING)
            return
        show_snack(page, f"Validating {len(proxies)} proxy/proxies…")
        try:
            from user_scanner.core.helpers import validate_proxies

            working = await asyncio.to_thread(validate_proxies, proxies)
            if working:
                show_snack(
                    page,
                    f"{len(working)}/{len(proxies)} proxy/proxies OK",
                    bgcolor=AppColors.SUCCESS,
                )
            else:
                show_snack(page, "No proxies passed validation", bgcolor=AppColors.ERROR)
        except Exception as exc:
            show_snack(page, f"Proxy validation failed: {exc}", bgcolor=AppColors.ERROR)


    def _toggle_use_curl_cffi(val: bool):
        state.use_curl_cffi = val
        spawn(_persist(STORAGE_USE_CURL_CFFI, "true" if val else "false"))

    def _toggle_safe_search(val: bool):
        _set_nsfw(not val)

    async def _persist(key: str, value: str):
        try:
            from flet import context

            from services.storage_service import StorageService

            storage = StorageService(context.page)
            await storage.set(key, value)
            await storage.flush()
        except Exception as exc:
            logger.debug("Settings persist failed for %s: %s", key, exc)

    # ─── Cards ──────────────────────────────────────────────────────────

    # Preferences
    preferences_card = _settings_card(
        [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Container(
                                    content=ft.Icon(
                                        ft.Icons.COLOR_LENS_ROUNDED,
                                        size=tokens.ICON_MD,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                    width=tokens.ICON_BACKDROP,
                                    height=tokens.ICON_BACKDROP,
                                    border_radius=tokens.ICON_BACKDROP_RADIUS,
                                    bgcolor=ft.Colors.with_opacity(
                                        tokens.OPACITY_LIGHT, ft.Colors.ON_SURFACE
                                    ),
                                    alignment=ft.Alignment.CENTER,
                                ),
                                ft.Column(
                                    [
                                        ft.Text(
                                            "App Theme",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        ft.Text(
                                            "Choose between Light, Dark, or System",
                                            size=tokens.FONT_XS,
                                            color=ft.Colors.with_opacity(
                                                tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                                            ),
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                            ],
                            spacing=tokens.SPACE_MD,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [
                                _create_theme_card(
                                    "light", "Light", ft.Icons.LIGHT_MODE_ROUNDED
                                ),
                                _create_theme_card(
                                    "dark", "Dark", ft.Icons.DARK_MODE_ROUNDED
                                ),
                                _create_theme_card(
                                    "system",
                                    "System",
                                    ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED,
                                ),
                            ],
                            spacing=tokens.SPACE_SM,
                        ),
                    ],
                    spacing=tokens.SPACE_MD,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD
                ),
            ),
        ]
    )

    # Scan Parameters (user-scanner)
    scan_controls = [
        _setting_row(
            ft.Icons.SAVED_SEARCH_ROUNDED,
            "Recursive OSINT Search",
            "Extract discovered usernames & IDs to automatically expand search",
            ft.Switch(
                value=getattr(state, "recursive_search", False),
                on_change=lambda e: _toggle_recursive_search(e.control.value),
                active_color=ft.Colors.PRIMARY,
            ),
            stacked=narrow,
        ),
        ft.Divider(
            height=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        _setting_row(
            ft.Icons.ALTERNATE_EMAIL_ROUNDED,
            "Username Permutations",
            "Also scan separator variants of the handle (john.doe -> john_doe, john-doe, johndoe). Multiplies scan length.",
            ft.Switch(
                value=getattr(state, "permute_enabled", False),
                on_change=lambda e: _toggle_permute(e.control.value),
                active_color=ft.Colors.PRIMARY,
            ),
            stacked=narrow,
        ),
        ft.Divider(
            height=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        # No "Scan Notifications" row here on purpose. Scan progress is
        # delivered by an OS notification with a Cancel action, so the app
        # keeps working while the user is somewhere else; a scan is a
        # foreground activity that the system needs permission to show, not
        # a preference to opt into. Permission is requested the first time a
        # scan starts (main._ensure_notifications_ready), and a decline is
        # surfaced once with a route to the OS settings page.
        _setting_row(
            ft.Icons.ACCOUNT_BOX_ROUNDED,
            "Profile Data Extraction",
            "Parse claimed profile HTML for names, bios, avatars, and locations",
            ft.Switch(
                value=getattr(state, "extract_info", True),
                on_change=lambda e: _toggle_extract_info(e.control.value),
                active_color=ft.Colors.PRIMARY,
            ),
            stacked=narrow,
        ),
        ft.Divider(
            height=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        _setting_row(
            ft.Icons.SHIELD_ROUNDED,
            "Include Disabled Sites",
            "Scan unstable or broken networks (may increase false positives)",
            ft.Switch(
                value=state.ignore_exclusions,
                on_change=lambda e: _toggle_exclusions(e.control.value),
                active_color=ft.Colors.PRIMARY,
            ),
            stacked=narrow,
        ),
        ft.Divider(
            height=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        _setting_row(
            ft.Icons.BLOCK_ROUNDED,
            "Include Adult Sites",
            "Include NSFW, dating, and adult networks in scans",
            ft.Switch(
                value=state.nsfw_enabled,
                on_change=lambda e: _toggle_nsfw(e.control.value),
                active_color=ft.Colors.PRIMARY,
            ),
            stacked=narrow,
        ),
        ft.Divider(
            height=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        _setting_row(
            ft.Icons.NOTIFICATIONS_ACTIVE_ROUNDED,
            "Allow Loud Modules",
            "Permit checks that may send SMS, email, or push notifications to the target. Off by default for OPSEC.",
            ft.Switch(
                value=getattr(state, "allow_loud", False),
                on_change=lambda e: _toggle_allow_loud(e.control.value),
                active_color=ft.Colors.PRIMARY,
            ),
            stacked=narrow,
        ),
        ft.Divider(
            height=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        _setting_row(
            ft.Icons.VISIBILITY_ROUNDED,
            "Show All Results",
            "Include not-found, error and skipped platforms in result lists",
            ft.Switch(
                value=getattr(state, "show_all_results", False),
                on_change=lambda e: _toggle_show_all_results(e.control.value),
                active_color=ft.Colors.PRIMARY,
            ),
            stacked=narrow,
        ),
        ft.Divider(
            height=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        _setting_row(
            ft.Icons.ARTICLE_ROUNDED,
            "Verbose Output",
            "Show raw endpoint URLs and diagnostic detail in result cards",
            ft.Switch(
                value=getattr(state, "verbose_output", False),
                on_change=lambda e: _toggle_verbose_output(e.control.value),
                active_color=ft.Colors.PRIMARY,
            ),
            stacked=narrow,
        ),
        ft.Divider(
            height=1,
            color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
        ),
        _setting_row(
            ft.Icons.REPLAY_ROUNDED,
            "Request Retries",
            "Number of retries when a network request drops or times out",
            ft.SegmentedButton(
                segments=[
                    ft.Segment(value="0", label=ft.Text("0", size=10)),
                    ft.Segment(value="1", label=ft.Text("1", size=10)),
                    ft.Segment(value="2", label=ft.Text("2", size=10)),
                    ft.Segment(value="3", label=ft.Text("3", size=10)),
                ],
                selected=[str(getattr(state, "retries", 0))],
                on_change=lambda e: _on_retries_change(
                    e.control.selected[0] if e.control.selected else "0"
                ),
                show_selected_icon=False,
            ),
            stacked=narrow,
        ),
    ]
    if not is_mobile:
        scan_controls.extend(
            [
                ft.Divider(
                    height=1,
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE
                    ),
                ),
                _setting_row(
                    ft.Icons.DNS_ROUNDED,
                    "DNS Resolver Mode",
                    "Async (c-ares) for speed · System (Threaded) for network compat",
                    ft.SegmentedButton(
                        segments=[
                            ft.Segment(value="async", label=ft.Text("Async", size=10)),
                            ft.Segment(
                                value="threaded", label=ft.Text("System", size=10)
                            ),
                        ],
                        selected=[getattr(state, "dns_resolver", "threaded")],
                        on_change=lambda e: _on_dns_resolver_change(
                            e.control.selected[0] if e.control.selected else "threaded"
                        ),
                        show_selected_icon=False,
                    ),
                    stacked=narrow,
                ),
            ]
        )
    scan_card = _settings_card(scan_controls)

    # Email Intelligence (user-scanner + curl-cffi)
    email_card = _settings_card(
        [
            _setting_row(
                ft.Icons.SECURITY_ROUNDED,
                "Stealth TLS (curl-cffi)",
                "Chrome 131 JA3/H2 fingerprint to bypass WAF 403 blocks",
                ft.Switch(
                    value=getattr(state, "use_curl_cffi", True),
                    on_change=lambda e: _toggle_use_curl_cffi(e.control.value),
                    active_color=ft.Colors.PRIMARY,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.ALTERNATE_EMAIL_ROUNDED,
                "Email Request Timeout",
                "Max wait time per email check (user-scanner)",
                ft.Slider(
                    value=float(state.email_timeout),
                    min=5,
                    max=30,
                    divisions=5,
                    label=f"{state.email_timeout}s",
                    active_color=AppColors.PRIMARY,
                    on_change=_slider_live("{}s"),
                    on_change_end=_slider_commit(
                        STORAGE_EMAIL_TIMEOUT, _apply_email_timeout
                    ),
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.SPEED_ROUNDED,
                "Email Concurrency",
                "Parallel checks — lower is stealthier, higher is faster",
                ft.Slider(
                    value=float(getattr(state, "email_concurrency", 12)),
                    min=5,
                    max=30,
                    divisions=25,
                    label=f"{getattr(state, 'email_concurrency', 12)}",
                    active_color=AppColors.PRIMARY,
                    on_change=_slider_live("{}"),
                    on_change_end=_slider_commit(
                        STORAGE_EMAIL_CONCURRENCY, _apply_email_concurrency
                    ),
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.FILTER_ALT_ROUNDED,
                "Show Found Only",
                "Hide not-found platforms in email results",
                ft.Switch(
                    value=getattr(state, "email_only_found", False),
                    on_change=lambda e: _toggle_email_only_found(e.control.value),
                    active_color=ft.Colors.PRIMARY,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.PASSWORD_ROUNDED,
                "Skip Password Recovery",
                "Skip platforms that only expose password-recovery endpoints — faster scans, fewer recovery hints",
                ft.Switch(
                    value=state.no_password_recovery,
                    on_change=lambda e: _toggle_no_password_recovery(e.control.value),
                    active_color=ft.Colors.PRIMARY,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.TUNE_ROUNDED,
                "Search Keywords",
                "Comma-separated — matches get a KEYWORD badge on results",
                SettingsTextField(
                    value=state.search_keywords or "",
                    on_commit=_on_keywords_change,
                    hint_text="osint, investigator, security",
                    width=200,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.BOLT_ROUNDED,
                "Deep Enrichment",
                "Dig deeper on every found account (up to 3 extra API lookups each) — richer profile data; slower scans, more data usage",
                ft.Switch(
                    value=state.deep_enrich,
                    on_change=lambda e: _on_deep_enrich_change(e.control.value),
                    active_color=ft.Colors.PRIMARY,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.ALTERNATE_EMAIL_ROUNDED,
                "Email Domain Scopes",
                "In username mode, also generate emails from these providers (global, usa, uk… or a custom domain)",
                SettingsTextField(
                    value=getattr(state, "email_domains", "") or "",
                    on_commit=_on_email_domains_change,
                    hint_text="global, usa, proton.me",
                    width=200,
                ),
                stacked=narrow,
            ),
        ]
    )

    # Cross-Scan & identity pivoting (user-scanner)
    cross_scan_card = _settings_card(
        [
            _setting_row(
                ft.Icons.ALL_INCLUSIVE_ROUNDED,
                "Enable Cross-Scan",
                "After a scan, mine discovered handles, links and exposed emails and pivot across platforms",
                ft.Switch(
                    value=getattr(state, "cross_scan_enabled", False),
                    on_change=lambda e: _toggle_cross_scan(e.control.value),
                    active_color=ft.Colors.PRIMARY,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.LINK_ROUNDED,
                "Follow Links",
                "Which profile links a cross-scan may pivot from",
                ft.SegmentedButton(
                    segments=[
                        ft.Segment(value="all", label=ft.Text("All", size=10)),
                        ft.Segment(value="verified", label=ft.Text("Verified", size=10)),
                        ft.Segment(value="none", label=ft.Text("None", size=10)),
                    ],
                    selected=[getattr(state, "cross_links", "all") or "all"],
                    on_change=lambda e: _on_cross_links_change(
                        e.control.selected[0] if e.control.selected else "all"
                    ),
                    show_selected_icon=False,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.MARK_EMAIL_UNREAD_ROUNDED,
                "Harvest Emails",
                "Which exposed addresses are scanned as emails — verified only is safest",
                ft.SegmentedButton(
                    segments=[
                        ft.Segment(value="verified", label=ft.Text("Verified", size=10)),
                        ft.Segment(value="all", label=ft.Text("All", size=10)),
                        ft.Segment(value="none", label=ft.Text("None", size=10)),
                    ],
                    selected=[getattr(state, "cross_emails", "verified") or "verified"],
                    on_change=lambda e: _on_cross_emails_change(
                        e.control.selected[0] if e.control.selected else "verified"
                    ),
                    show_selected_icon=False,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.REPEAT_ROUNDED,
                "Recursion Depth",
                "Rounds of link following — each round pivots off what the previous found",
                ft.SegmentedButton(
                    segments=[
                        ft.Segment(value="1", label=ft.Text("1 round", size=10)),
                        ft.Segment(value="2", label=ft.Text("2 rounds", size=10)),
                        ft.Segment(value="3", label=ft.Text("3 rounds", size=10)),
                    ],
                    selected=[str(getattr(state, "cross_depth", 1) or 1)],
                    on_change=lambda e: _on_cross_depth_change(
                        e.control.selected[0] if e.control.selected else "1"
                    ),
                    show_selected_icon=False,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.SPEED_ROUNDED,
                "Sweep Quota",
                "Maximum pivot targets swept across every module — higher finds more, costs more",
                ft.Slider(
                    value=float(getattr(state, "cross_sweep", 3) or 3),
                    min=0,
                    max=10,
                    divisions=10,
                    label=f"{getattr(state, 'cross_sweep', 3)}",
                    active_color=AppColors.PRIMARY,
                    on_change=_slider_live("{}"),
                    on_change_end=_slider_commit(STORAGE_CROSS_SWEEP, _on_cross_sweep_change),
                ),
                stacked=narrow,
            ),
        ]
    )

    # Phone Intelligence (phonsint)
    phone_card = _settings_card(
        [
            _setting_row(
                ft.Icons.SPEED_ROUNDED,
                "Phone Concurrency",
                "Parallel phone checks — lower is stealthier, higher is faster",
                ft.Slider(
                    value=float(getattr(state, "phone_concurrency", 15) or 15),
                    min=5,
                    max=30,
                    divisions=25,
                    label=f"{getattr(state, 'phone_concurrency', 15)}",
                    active_color=AppColors.PRIMARY,
                    on_change=_slider_live("{}"),
                    on_change_end=_slider_commit(STORAGE_PHONE_CONCURRENCY, _apply_phone_concurrency),
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.PHONE_ROUNDED,
                "Silent Operation",
                "phonsint uses pre-auth endpoints only — it never sends SMS or alerts the target",
                ft.Icon(ft.Icons.VERIFIED_ROUNDED, color=AppColors.SUCCESS),
                stacked=narrow,
            ),
        ]
    )

    # Performance
    performance_card = _settings_card(
        [
            _setting_row(
                ft.Icons.TRAVEL_EXPLORE_ROUNDED,
                "Scan Scope & Depth",
                "Choose between full sweep or top Alexa-ranked networks",
                ft.SegmentedButton(
                    segments=[
                        ft.Segment(value="all", label=ft.Text("All modules", size=10)),
                        ft.Segment(value="1000", label=ft.Text("Top 1k", size=10)),
                        ft.Segment(value="500", label=ft.Text("Top 500", size=10)),
                    ],
                    selected=[state.scan_depth or "all"],
                    on_change=lambda e: _on_scan_depth_change(
                        e.control.selected[0] if e.control.selected else "all"
                    ),
                    show_selected_icon=False,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.SPEED_ROUNDED,
                "Network Concurrency",
                "Max parallel requests during username scans (10 - 100)",
                ft.Slider(
                    value=float(getattr(state, "max_connections", 50)),
                    min=10,
                    max=100,
                    divisions=9,
                    label=f"{getattr(state, 'max_connections', 50)}",
                    active_color=AppColors.PRIMARY,
                    on_change=_slider_live("{}"),
                    on_change_end=_slider_commit(
                        STORAGE_MAX_CONNECTIONS, _apply_max_connections
                    ),
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.FLASH_ON_ROUNDED,
                "Bundled Database",
                "Use the bundled upstream module catalog (faster startup)",
                ft.Switch(
                    value=state.use_local_db,
                    on_change=lambda e: _toggle_local_db(e.control.value),
                    active_color=ft.Colors.PRIMARY,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.TIMER_OUTLINED,
                "Request Timeout",
                "Maximum connection wait time per site (5s - 60s)",
                ft.Slider(
                    value=float(state.timeout),
                    min=5,
                    max=60,
                    divisions=11,
                    label=f"{state.timeout}s",
                    active_color=AppColors.PRIMARY,
                    on_change=_slider_live("{}s"),
                    on_change_end=_slider_commit(STORAGE_TIMEOUT, _apply_timeout),
                ),
                stacked=narrow,
            ),
        ]
    )

    # Custom Manifest
    manifest_card = _settings_card(
        [
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Icon(
                                ft.Icons.FOLDER_OPEN_ROUNDED,
                                size=tokens.ICON_MD,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            width=36,
                            height=36,
                            border_radius=18,
                            bgcolor=ft.Colors.with_opacity(
                                tokens.OPACITY_LIGHT, ft.Colors.ON_SURFACE
                            ),
                            alignment=ft.Alignment.CENTER,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "Custom Site-DB Manifest",
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                ),
                                ft.Text(
                                    "JSON URL or local path",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.with_opacity(
                                        tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                                    ),
                                ),
                            ],
                            spacing=tokens.SPACE_XXS,
                            expand=True,
                        ),
                    ],
                    spacing=tokens.SPACE_MD,
                ),
                padding=ft.Padding(
                    left=tokens.SPACE_LG,
                    right=tokens.SPACE_LG,
                    top=tokens.SPACE_MD,
                    bottom=tokens.SPACE_SM,
                ),
            ),
            ft.Container(
                content=SettingsTextField(
                    value=state.custom_manifest or "",
                    on_commit=_on_manifest_submit,
                    hint_text="https://raw.githubusercontent.com/.../data.json",
                ),
                padding=ft.Padding(
                    left=tokens.SPACE_LG,
                    right=tokens.SPACE_LG,
                    bottom=tokens.SPACE_MD,
                ),
            ),
        ]
    )

    # NOTE: the UMP consent form is intentionally NOT surfaced as a
    # settings entry. It appears on its own when the user's region requires
    # it (gather_consent at startup), and there is no "Manage/withdraw
    # consent" row: a revocation path mostly serves users who already
    # consented — revenue-negative by design decision (owner, 2026-09-03).

    # About & Updates
    def _open_version_dialog(e=None):
        from components.update_dialog import show_update_dialog

        show_update_dialog(page)

    about_card = _settings_card(
        [
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Image(
                            src="/icon.svg",
                            width=48,
                            height=48,
                            color=ft.Colors.WHITE if is_dark_mode(page) else None,
                        ),
                        ft.Container(height=tokens.SPACE_SM),
                        ft.Text(
                            APP_NAME,
                            size=tokens.FONT_LG,
                            weight=ft.FontWeight.W_700,
                            color=ft.Colors.ON_SURFACE,
                        ),
                        ft.Container(
                            content=ft.Text(
                                f"Version {APP_VERSION} (Build {APP_BUILD_NUMBER})",
                                size=tokens.FONT_SM,
                                color=ft.Colors.with_opacity(
                                    tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                                ),
                            ),
                            ink=True,
                            tooltip="Tap to view changelog",
                            on_click=_open_version_dialog,
                        ),
                        ft.Container(height=tokens.SPACE_XS),
                        # Selectable so the boilerplate can be long-pressed
                        # and copied. Scoped here rather than on the whole
                        # card: `selectable` on interactive rows fights their
                        # tap/scroll gestures.
                        ft.SelectionArea(
                            content=ft.Text(
                                "A UI for user-scanner & phonsint.\nUsername, Email & Phone OSINT made easy.",
                                size=tokens.FONT_SM,
                                color=ft.Colors.with_opacity(
                                    tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                                ),
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=0,
                ),
                padding=ft.Padding(
                    left=tokens.SPACE_LG,
                    right=tokens.SPACE_LG,
                    top=tokens.SPACE_XL,
                    bottom=tokens.SPACE_LG,
                ),
                alignment=ft.Alignment.CENTER,
            ),
        ]
    )

    # Extra cards: Network & Enrichment
    network_card = _settings_card(
        [
            ft.Container(
                content=SettingsTextField(
                    value=state.proxy_url or "",
                    on_commit=_on_proxy_change,
                    hint_text="socks5://127.0.0.1:1080 or http://proxy:8080 (empty = direct)",
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD
                ),
            ),
            ft.Container(
                content=SettingsTextField(
                    value=state.i2p_proxy or "",
                    on_commit=_on_i2p_change,
                    hint_text="http://127.0.0.1:4444 (empty = unused)",
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
            ft.Container(
                content=SettingsTextField(
                    value=getattr(state, "proxy_file", "") or "",
                    on_commit=_on_proxy_file_change,
                    hint_text="path/to/proxies.txt — one per line for rotation",
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
            _setting_row(
                ft.Icons.VERIFIED_ROUNDED,
                "Validate Proxies",
                "Test each proxy against a reachability endpoint before scanning",
                ft.FilledButton(
                    "Validate",
                    icon=ft.Icons.VERIFIED_ROUNDED,
                    on_click=lambda e: spawn(_validate_proxies()),
                ),
                stacked=narrow,
            ),
            ft.Container(
                content=SettingsTextField(
                    value=state.cookies_path or "",
                    on_commit=_on_cookies_change,
                    hint_text="path/to/cookies.txt — auth-gated sites",
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_MD
                ),
            ),
            # Domain-check mode uses aiodns — unavailable on Android
            # (/etc/resolv.conf), so the row only exists on desktop.
            *(
                [
                    ft.Divider(
                        height=1,
                        color=ft.Colors.with_opacity(
                            tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE
                        ),
                    ),
                    _setting_row(
                        ft.Icons.DNS_ROUNDED,
                        "Domain Checks (experimental)",
                        "DNS-only probes for protocol=dns sites (desktop)",
                        ft.Switch(
                            value=state.check_domains,
                            on_change=lambda e: _on_check_domains_change(
                                e.control.value
                            ),
                            active_color=ft.Colors.PRIMARY,
                        ),
                        stacked=narrow,
                    ),
                ]
                if not is_mobile
                else []
            ),
        ]
    )

    _TERMINAL_DISPLAY_LINES = 500

    def _open_terminal():
        if page is None:
            return
        with contextlib.suppress(Exception):
            page.pop_dialog()

        logs_list = in_memory_log_handler.get_logs()[-_TERMINAL_DISPLAY_LINES:]
        log_text = ft.Text(
            value="\n".join(logs_list)
            if logs_list
            else "No activity recorded yet.\nEngine, network, and UI logs will appear here.",
            size=tokens.FONT_XS,
            font_family="Courier New",
            color=AppColors.TERMINAL_GREEN,
            selectable=True,
        )

        async def _copy_logs(e):
            try:
                from core.shared_services import shared_clipboard

                cb = shared_clipboard(page)
                current_logs = "\n".join(in_memory_log_handler.get_logs())
                await cb.set(current_logs)
                show_snack(page, f"Copied {len(current_logs.splitlines())} log line(s)", bgcolor=AppColors.SUCCESS)
            except Exception as exc:
                logger.warning("Failed to copy logs: %s", exc)

        telemetry_text = ft.Text(
            get_telemetry_snapshot(),
            size=11,
            font_family="Courier New",
            color=AppColors.PRIMARY,
            weight=ft.FontWeight.W_600,
            expand=True,
        )

        def _refresh_telemetry(e):
            telemetry_text.value = get_telemetry_snapshot()
            cur_logs = in_memory_log_handler.get_logs()[-_TERMINAL_DISPLAY_LINES:]
            if cur_logs:
                log_text.value = "\n".join(cur_logs)
            page.update()

        def _clear_logs(e):
            in_memory_log_handler.clear_logs()
            log_text.value = "Logs cleared.\nNew activity will appear here."
            page.update()

        def _dismiss(e):
            page.pop_dialog()

        terminal_dlg = ft.AlertDialog(
            modal=False,
            title=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.TERMINAL_ROUNDED,
                        color=AppColors.PRIMARY,
                        size=tokens.ICON_MD,
                    ),
                    ft.Text(
                        "Live Activity Terminal",
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.BOLD,
                        font_family="Outfit",
                        color=AppColors.PRIMARY,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH_ROUNDED,
                        tooltip="Refresh telemetry",
                        icon_size=18,
                        icon_color=AppColors.PRIMARY,
                        on_click=_refresh_telemetry,
                    ),
                ],
                spacing=tokens.SPACE_SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Container(
                            content=ft.Row(
                                [
                                    telemetry_text,
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            padding=ft.Padding(8, 4, 8, 4),
                            border_radius=tokens.RADIUS_SM,
                            bgcolor=ft.Colors.with_opacity(0.08, AppColors.PRIMARY),
                            margin=ft.Margin(0, 0, 0, tokens.SPACE_XS),
                        ),
                        ft.Text(
                            "Real-time engine execution, network status, and diagnostic logs.",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Container(height=tokens.SPACE_XS),
                        ft.Container(
                            content=ft.ListView(
                                controls=[log_text],
                                spacing=0,
                                expand=True,
                                build_controls_on_demand=True,
                            ),
                            bgcolor=AppColors.TERMINAL_BG,
                            border=ft.Border.all(
                                1,
                                ft.Colors.with_opacity(
                                    tokens.OPACITY_LIGHT, ft.Colors.WHITE
                                ),
                            ),
                            border_radius=tokens.RADIUS_SM,
                            padding=tokens.SPACE_MD,
                            # Explicit height, not `expand`: this sits in a
                            # Column, where expand is a no-op in flet 1.0.4,
                            # so a 500-line buffer shrink-wrapped and burst
                            # out of the fixed dialog box.
                            height=260,
                        ),
                    ],
                    spacing=0,
                ),
                width=tokens.DIALOG_WIDTH_LG,
                height=tokens.DIALOG_HEIGHT_LG,
            ),
            actions=[
                ft.TextButton(
                    "Copy Logs",
                    icon=ft.Icons.COPY_ROUNDED,
                    on_click=lambda e: spawn(_copy_logs(e)),
                ),
                ft.TextButton(
                    "Clear",
                    icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                    on_click=_clear_logs,
                ),
                ft.TextButton("Close", on_click=_dismiss),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(terminal_dlg)

    log_count = len(in_memory_log_handler.get_logs())
    logs_card = _settings_card(
        [
            _setting_row(
                ft.Icons.NEWSPAPER_ROUNDED,
                "Engine Logs",
                "The OSINT engine logs on every site-check, which buries "
                "everything else in the console and terminal. Leave off while "
                "troubleshooting; turn on only when you need per-check detail.",
                ft.Switch(
                    value=getattr(state, "log_engine_logs", False),
                    # Must unwrap the ControlEvent like every other switch
                    # here: passing the handler directly stores the event
                    # object as the state value, which is always truthy, so
                    # the toggle could never be turned off.
                    on_change=lambda e: _on_log_engine_change(e.control.value),
                    active_color=ft.Colors.PRIMARY,
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.TERMINAL_ROUNDED,
                "Live Activity Terminal",
                f"{log_count} entries recorded · Real-time engine diagnostics",
                ft.FilledButton(
                    "Open Terminal",
                    icon=ft.Icons.TERMINAL_ROUNDED,
                    on_click=lambda e: _open_terminal(),
                ),
                stacked=narrow,
            ),
            ft.Divider(
                height=1,
                color=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.OUTLINE),
            ),
            _setting_row(
                ft.Icons.HEALTH_AND_SAFETY_ROUNDED,
                "Database Health Check",
                "Probe 25 random sites · flags broken ones and excludes them from scans",
                ft.FilledButton(
                    "Run Check",
                    icon=ft.Icons.SEARCH_ROUNDED,
                    on_click=lambda e: spawn(_run_db_health_check(e)),
                ),
                stacked=narrow,
            ),
        ]
    )

    content = ft.ListView(
        controls=[
            ft.Container(height=tokens.SPACE_SM),
            SectionHeader("PREFERENCES"),
            preferences_card,
            SectionHeader("SCAN PARAMETERS"),
            scan_card,
            pooled_banner_ad("settings-1"),
            SectionHeader("CROSS-SCAN & IDENTITY PIVOTS"),
            cross_scan_card,
            SectionHeader("EMAIL INTELLIGENCE"),
            email_card,
            SectionHeader("PHONE INTELLIGENCE (phonsint)"),
            phone_card,
            SectionHeader("NETWORK & PROXY"),
            network_card,
            pooled_banner_ad("settings-2"),
            SectionHeader("CONNECTION & SPEED"),
            performance_card,
            SectionHeader("CUSTOM SITE-DB MANIFEST"),
            manifest_card,
            pooled_banner_ad("settings-3"),
            SectionHeader("TROUBLESHOOTING & LOGS"),
            logs_card,
            SectionHeader("ABOUT"),
            about_card,
            ft.Container(height=tokens.SPACE_XXXL),
        ],
        spacing=0,
        expand=True,
    )

    header_controls: list[Control] = [
        AppHeader(
            page,
            title="Settings",
            subtitle="Preferences & site database",
            show_settings=False,
        ),
    ]
    if banner:
        header_controls.append(banner)

    # The ListView is the screen root and owns the scroll. The previous root
    # was a plain Column, so `expand` on the inner ListView was a no-op (flet
    # 1.0.4 ignores expand on Column children) and the whole card stack was
    # laid out at content height inside a non-scrolling Column — everything
    # below Preferences and Scan Parameters was unreachable. Header rides
    # inside the list, matching the Networks screen.
    return ft.ListView(
        controls=[
            *header_controls,
            *content.controls,
        ],
        spacing=0,
        expand=True,
    )
