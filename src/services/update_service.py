"""UpdateService — checks version.json on GitHub for app updates and announcements.

Pings the raw version.json hosted on GitHub.
Supports both version updates (with platform-specific install options)
and announcement/cross-promotion campaigns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from core.constants import (
    APP_BUILD_NUMBER,
    APP_VERSION,
    GITHUB_RELEASES_URL,
    PLAY_STORE_URL,
    UPDATE_CONFIG_URL,
)

logger = logging.getLogger("UpdateService")


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
            async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
                resp = await client.get(self.config_url)
                if resp.status_code != 200:
                    logger.debug("Update check returned status %s", resp.status_code)
                    return None

                data = resp.json()
                if not isinstance(data, dict):
                    return None

                server_build = data.get("build_number", 0)
                if (
                    not isinstance(server_build, int)
                    or server_build <= APP_BUILD_NUMBER
                ):
                    return None
                info = UpdateInfo(
                    version=str(data.get("version", APP_VERSION)),
                    build_number=int(server_build),
                    type=str(data.get("type", "update")),
                    title=str(
                        data.get(
                            "title",
                            f"Version {data.get('version', '')} Available!"
                            if data.get("type") != "announcement"
                            else "Announcement",
                        )
                    ),
                    release_notes=str(data.get("release_notes", "")),
                    mandatory=bool(data.get("mandatory", False)),
                    github_url=str(data.get("github_url", GITHUB_RELEASES_URL)),
                    playstore_url=str(data.get("playstore_url", PLAY_STORE_URL)),
                    action_url=data.get("action_url"),
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
