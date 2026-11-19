"""UpdateService — checks version.json on GitHub for app updates and announcements.

Pings the raw version.json hosted on GitHub.
Supports both version updates (with platform-specific install options)
and announcement/cross-promotion campaigns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.constants import (
    APP_BUILD_NUMBER,
    APP_VERSION,
    GITHUB_RELEASES_URL,
    PLAY_STORE_URL,
    UPDATE_CONFIG_URL,
)

logger = logging.getLogger("UpdateService")


def _safe_https_url(value: object, default: str | None) -> str | None:
    """Allow only https:// URLs for update/install links, else the default."""
    if isinstance(value, str) and value.startswith("https://"):
        return value
    return default


def _safe_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


@dataclass
class UpdateInfo:
    version: str
    build_number: int
    type: str  # "update" or "announcement"
    title: str
    release_notes: str
    mandatory: bool
    github_url: str
    playstore_url: str
    action_url: str | None = None

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "build_number": self.build_number,
            "type": self.type,
            "title": self.title,
            "release_notes": self.release_notes,
            "mandatory": self.mandatory,
            "github_url": self.github_url,
            "playstore_url": self.playstore_url,
            "action_url": self.action_url,
        }


class UpdateService:
    """Service to query GitHub for remote version and announcement metadata."""

    def __init__(self, config_url: str = UPDATE_CONFIG_URL):
        self.config_url = config_url

    async def check_for_update(self) -> dict | None:
        """Fetch remote config. Returns dict if a newer build exists, else None."""
        try:
            # Shared pooled client (P5-1): proxy-aware via state.proxy_url,
            # per-request timeout keeps the fast-fail update semantics.
            from services.http_client import get_client

            resp = await get_client().get(self.config_url, timeout=4.0)
            if resp.status_code != 200:
                logger.debug("Update check returned status %s", resp.status_code)
                return None

            data = resp.json()
            if not isinstance(data, dict):
                return None

            server_build = data.get("build_number", 0)
            # Policy: announcements are gated on build_number like updates
            # (prevents remote announcement spam on every launch).
            if not isinstance(server_build, int) or server_build <= APP_BUILD_NUMBER:
                return None
            raw_type = data.get("type")
            safe_type = raw_type if raw_type in ("update", "announcement") else "update"
            if safe_type == "announcement":
                default_title = "Announcement"
            else:
                default_title = (
                    f"Version {_safe_text(data.get('version'), '')} Available!"
                )
            info = UpdateInfo(
                version=_safe_text(data.get("version"), APP_VERSION)[:50],
                build_number=int(server_build),
                type=safe_type,
                title=_safe_text(data.get("title"), default_title)[:500],
                release_notes=_safe_text(data.get("release_notes"), "")[:10000],
                mandatory=data.get("mandatory") is True,
                github_url=_safe_https_url(data.get("github_url"), GITHUB_RELEASES_URL),
                playstore_url=_safe_https_url(
                    data.get("playstore_url"), PLAY_STORE_URL
                ),
                action_url=_safe_https_url(data.get("action_url"), None),
            )
            logger.info(
                "New update/announcement found: build %s (current: %s)",
                server_build,
                APP_BUILD_NUMBER,
            )
            return info.to_dict()

        except Exception as ex:
            logger.debug("Update check failed (expected if offline): %s", ex)

        return None
