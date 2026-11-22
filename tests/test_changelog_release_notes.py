"""Changelog rendering + release-note generation (proot-distro pattern)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from core.changelog import CHANGELOG, notes_for
from core.constants import APP_VERSION

ROOT = Path(__file__).resolve().parent.parent


def test_notes_for_falls_back_to_newest_by_version_key():
    """Fallback must pick the NEWEST entry, not the first inserted."""
    newest = max(CHANGELOG, key=lambda v: tuple(int(p) for p in v.split(".")))
    assert notes_for("0.0.0-absent") == CHANGELOG[newest]


def test_current_version_has_an_entry():
    assert APP_VERSION in CHANGELOG


def test_update_dialog_renders_one_row_per_bullet():
    """Each bullet gets its own row (Markdown would collapse them)."""
    import flet as ft

    from components.update_dialog import _changelog_rows

    rows = _changelog_rows(notes_for(APP_VERSION))
    bullets = [
        ln.strip().lstrip("•").strip()
        for ln in notes_for(APP_VERSION).splitlines()
        if ln.strip().lstrip("•").strip()
    ]
    assert len(rows) == len(bullets) > 1
    texts = []
    for row in rows:
        assert isinstance(row, ft.Row)
        text = next(c for c in row.controls if isinstance(c, ft.Text))
        texts.append(text.value)
    assert texts == bullets


def test_release_notes_script_uses_the_changelog(tmp_path):
    out = tmp_path / "release_notes.md"
    subprocess.run(  # noqa: S603 — args are constants, no untrusted input
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_release_notes.py"),
            "--version",
            APP_VERSION,
            "--build",
            "13",
            "--output",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    body = out.read_text(encoding="utf-8")
    assert f"# Sherlock {APP_VERSION}" in body
    # GitHub-flavoured bullets, not the app's '• ' markers
    assert "- " in body and "• " not in body
    assert "What's New" not in body
