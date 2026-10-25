"""Centralized regenerable cache service for the `.flet/storage/cache/` tier.

Flet exposes three storage tiers (see .flet/README.md):
  data/   — durable (storage.json, synced DBs)
  cache/  — regenerable, OS-purgeable on device (this service's home)
  temp/   — throwaway scratch

Everything written here must be cheap to rebuild after an OS purge and must
NEVER hold the only copy of user data. Two cache layers live here:

  1. avatars/  — on-device profile images keyed by sha256(url)
  2. reports/  — pre-rendered report bytes keyed by a hash of the
                 found-URL set + scan signature, so re-export is 0 ms

All file writes are atomic (tmp + os.replace) so a mid-write crash or an
OS purge can never leave a half-written cache entry behind.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SHA256_BLOCK = 1 << 16  # 64 KB streaming blocks


def _cache_root() -> Path:
    from services.storage_service import get_cache_dir

    return Path(get_cache_dir())


def _write_atomic(path: Path, writer: Any) -> bool:
    """Write through a unique temp file then os.replace; returns success.

    `writer` is a callable receiving the open temp file handle. Keeping the
    temp file inside the same directory guarantees an atomic same-filesystem
    rename on every platform we ship. The temp name is unique per writer
    (mkstemp) so concurrent writers to the same destination cannot interleave.
    """
    import tempfile

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_s = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as fh:
                writer(fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_s, path)
            return True
        finally:
            try:
                os.unlink(tmp_s)
            except OSError:
                pass
    except Exception as exc:
        logger.warning("Cache write failed for %s: %s", path, exc)
        return False


# ── Layer 1: Avatar Image Cache ────────────────────────────────────────────


def avatar_cache_path(url: str) -> Path:
    """Deterministic on-device path for a remote avatar URL."""
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return _cache_root() / "avatars" / f"{key}.png"


def ensure_cached_avatar(url: str) -> str:
    """Return a local file path for the avatar if cached, else the URL.

    Synchronous by design — callers just need an `src` string for ft.Image.
    The download that populates the cache happens in the background (see
    schedule_avatar_download); this read is a pure existence check.
    """
    if not url or not isinstance(url, str) or not url.startswith("http"):
        return url or ""
    try:
        p = avatar_cache_path(url)
        if p.is_file() and p.stat().st_size > 0:
            return str(p)
    except OSError:
        pass
    return url


_AVATAR_MAX_BYTES = 5 * 1024 * 1024  # 5 MB — avatars are small CDN images
_AVATAR_CHUNK = 64 * 1024


async def schedule_avatar_download(url: str) -> None:
    """Fetch an avatar to the cache in the background (fire-and-forget).

    Streams the body with a 5 MB cap so a malicious/oversized response can
    never balloon memory; inherits the shared-client timeout (slow-network
    tolerant). Failures are silent — the UI always has the remote URL fallback.
    """
    if not url or not isinstance(url, str) or not url.startswith("https://"):
        return
    try:
        from user_scanner.core.pdf_generator import is_safe_media_url

        if not is_safe_media_url(url):
            logger.info("Avatar download rejected by SSRF guard: %s", url[:80])
            return
    except Exception:
        pass
    dest = avatar_cache_path(url)
    if dest.is_file() and dest.stat().st_size > 0:
        return
    try:
        from services.http_client import get_client

        async with get_client().stream(
            "GET", url, headers={"User-Agent": "Sherlock/2.x"}
        ) as resp:
            if resp.status_code != 200:
                # Visible, not swallowed (owner rule): routine CDN misses
                # land at INFO; real failures raise into the warning below.
                logger.info(
                    "Avatar not cached (HTTP %s): %s", resp.status_code, url[:80]
                )
                return
            raw_len = resp.headers.get("content-length")
            if raw_len and raw_len.isdigit() and int(raw_len) > _AVATAR_MAX_BYTES:
                logger.info("Avatar not cached (oversize %s B): %s", raw_len, url[:80])
                return
            buf = bytearray()
            async for chunk in resp.aiter_bytes(_AVATAR_CHUNK):
                buf += chunk
                if len(buf) > _AVATAR_MAX_BYTES:
                    logger.info("Avatar not cached (exceeds 5 MB): %s", url[:80])
                    return
            if not buf:
                logger.info("Avatar not cached (empty body): %s", url[:80])
                return
            data = bytes(buf)
            # Validate image magic bytes: PNG, JPEG, GIF, WEBP
            is_png = data.startswith(b"\x89PNG\r\n\x1a\n")
            is_jpeg = data.startswith(b"\xff\xd8\xff")
            is_gif = data.startswith(b"GIF8")
            is_webp = data.startswith(b"RIFF") and b"WEBP" in data[:16]
            if not (is_png or is_jpeg or is_gif or is_webp):
                logger.info("Avatar not cached (invalid image magic bytes): %s", url[:80])
                return
        _write_atomic(dest, lambda fh: fh.write(data))
    except Exception as exc:
        logger.warning("Avatar download failed for %s: %s", url[:80], exc)


# ── Layer 2: Pre-Rendered Report Cache ─────────────────────────────────────


def _safe_name_component(raw: str) -> str:
    """Flatten a query/mode string into a filesystem-safe cache key chunk."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw.strip().lower())
    return cleaned[:48] or "unknown"


def _result_url(r) -> str:
    """URL key for a result row — dict rows and SiteResult alike.

    User-scanner modules put the profile URL in several places, so every
    known location is checked; the first non-empty wins.
    """
    if isinstance(r, dict):
        u = r.get("url_user") or r.get("url_main") or r.get("url")
        if not u:
            others = r.get("others")
            if isinstance(others, dict):
                u = others.get("url")
                if not u:
                    extra = others.get("extra")
                    if isinstance(extra, dict):
                        u = extra.get("url")
        return str(u or "")
    u = getattr(r, "url_user", "") or getattr(r, "url_main", "") or getattr(r, "url", "")
    if not u:
        others = getattr(r, "others", None)
        if isinstance(others, dict):
            u = others.get("url") or (others.get("extra") or {}).get("url")
    return str(u or "")


def results_fingerprint(found: list, sig: str = "") -> str:
    """Stable 16-hex fingerprint of a result set.

    Two scans of the same target that yield the same claimed accounts AND the
    same scan signature map to the same fingerprint — so an unchanged re-export
    reuses the cached report instead of re-rendering it.

    `sig` carries the rest of the scan state (checked / total / not-found /
    error counts). Without it, a mid-scan export with a partially-filled
    error list would be reused as the final report once the scan completed
    with the same found set but zero errors.
    """
    urls = sorted({u for u in (_result_url(r) for r in (found or [])) if u})
    blob = ("\n".join(urls) + "\n" + str(sig or "")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def cached_report_path(
    mode: str, query: str, found: list, ext: str, sig: str = ""
) -> Path:
    """Cache path for a rendered report keyed by (mode, query, result set)."""
    fp = results_fingerprint(found, sig)
    name = (
        f"{_safe_name_component(mode)}_{_safe_name_component(query)}_{fp}.{ext}"
    )
    return _cache_root() / "reports" / name


def load_cached_report(
    mode: str, query: str, found: list, ext: str, sig: str = ""
) -> bytes | None:
    """Return cached report bytes, or None on any miss/corruption."""
    try:
        p = cached_report_path(mode, query, found, ext, sig)
        if p.is_file() and p.stat().st_size > 0:
            return p.read_bytes()
    except OSError:
        pass
    return None


def save_cached_report(
    mode: str, query: str, found: list, ext: str, data: bytes, sig: str = ""
) -> None:
    """Persist rendered report bytes after a fresh generation.

    The path MUST fold in the same `sig` the loader used — otherwise save
    and load resolve to different files and the cache can never hit.
    """
    if not data:
        return
    try:
        p = cached_report_path(mode, query, found, ext, sig)
        _write_atomic(p, lambda fh: fh.write(data))
    except Exception as exc:
        logger.debug("Report cache save skipped: %s", exc)


def clear_all_caches() -> int:
    """Development/testing helper — wipe every regenerable cache artifact.

    Returns the number of top-level artifacts removed. Never touches
    data/ or temp/ tiers.
    """
    removed = 0
    try:
        root = _cache_root()
        if root.is_dir():
            for child in list(root.iterdir()):
                if child.name.startswith(".") and not child.name.endswith(".tmp"):
                    continue
                try:
                    if child.is_dir():
                        import shutil

                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink()
                    removed += 1
                except OSError:
                    pass
            # Sweep orphan writer tmps in subdirectories (avatars, etc.).
            for tmp in root.rglob(".*.tmp"):
                try:
                    tmp.unlink()
                    removed += 1
                except OSError:
                    pass
    except OSError:
        pass
    return removed
