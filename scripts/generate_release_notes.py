"""Generate release_notes.md from the in-app changelog.

Single source of truth: src/core/changelog.py keyed by APP_VERSION — the same
entry the app's "What's New" dialog shows. The CI release job consumes this
file as the GitHub release body, so a release is never a placeholder again
(proot-distro app.yml pattern).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.changelog import notes_for
from core.constants import APP_NAME


def _markdown_list(notes: str) -> str:
    """The app stores bullets as '• ' for its own row renderer; GitHub needs '- '.

    Continuation lines stay as-is so they join their bullet instead of starting
    a new paragraph.
    """
    lines: list[str] = []
    for raw in notes.splitlines():
        if raw.startswith("• "):
            lines.append("- " + raw[2:])
        elif raw.startswith("•"):
            lines.append("- " + raw[1:].lstrip())
        else:
            lines.append(raw)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--output", default="release_notes.md")
    args = parser.parse_args()

    notes = _markdown_list(notes_for(args.version))
    body = f"# {APP_NAME} {args.version} (build {args.build})\n\n{notes}\n"
    Path(args.output).write_text(body, encoding="utf-8")
    print(body)  # noqa: T201 — CI echoes the notes into the build log
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
