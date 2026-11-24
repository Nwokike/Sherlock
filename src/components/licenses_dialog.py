"""Open-source licenses — the Settings row's dependency license list.

flet 1.1.2 ships no license page, so this builds one from
`importlib.metadata`: versions come from the installed packages and license
text from each package's own metadata (never invented here).
"""

from __future__ import annotations

import importlib.metadata as md

import flet as ft

from core import tokens

# The app's own runtime stack (direct dependencies + the engines they pull in
# that we actually exercise). Names are distribution names for metadata lookup.
_PACKAGES = (
    "flet",
    "flet-ads",
    "flet-notifications",
    "maigret",
    "holehe-v2",
    "socid-extractor",
    "curl-cffi",
    "httpx",
    "reportlab",
    "networkx",
    "xmind",
    "pyvis",
    "jinja2",
    "pycountry",
    "pillow",
    "lxml",
    "aiohttp",
)


def _rows() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for name in _PACKAGES:
        try:
            meta = md.metadata(name)
        except md.PackageNotFoundError:
            continue
        license_text = (meta.get("License-Expression") or "").strip()
        if not license_text:
            license_text = " ".join((meta.get("License") or "").split())
        if not license_text:
            classifiers = [
                c.split("::")[-1].strip()
                for c in (meta.get_all("Classifier") or [])
                if c.startswith("License")
            ]
            license_text = classifiers[0] if classifiers else "See upstream project"
        rows.append(
            (meta.get("Name", name), meta.get("Version", "?"), license_text)
        )
    return rows


def build_licenses_dialog(page: ft.Page) -> ft.AlertDialog:
    controls: list[ft.Control] = []
    for name, version, license_text in _rows():
        controls.append(
            ft.Column(
                controls=[
                    ft.Text(
                        f"{name} {version}",
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(
                        license_text,
                        size=tokens.FONT_XS,
                        color=ft.Colors.with_opacity(
                            tokens.OPACITY_DIM, ft.Colors.ON_SURFACE
                        ),
                    ),
                ],
                spacing=0,
            )
        )
    body = ft.Column(
        controls=controls or [ft.Text("No package metadata available.")],
        spacing=tokens.SPACE_MD,
        scroll=ft.ScrollMode.AUTO,
        width=tokens.DIALOG_WIDTH_LG,
    )
    return ft.AlertDialog(
        modal=False,
        title=ft.Row(
            controls=[
                ft.Icon(ft.Icons.GAVEL_ROUNDED, color=ft.Colors.PRIMARY),
                ft.Text(
                    "Open-source licenses",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        content=ft.Container(content=body, width=tokens.DIALOG_WIDTH_LG),
        actions=[ft.TextButton("Close", on_click=lambda e: page.pop_dialog())],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def show_licenses_dialog(page: ft.Page) -> None:
    page.show_dialog(build_licenses_dialog(page))
