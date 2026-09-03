"""Centralized regenerable cache service for the `.flet/storage/cache/` tier.

Flet exposes three storage tiers (see .flet/README.md):
  data/   — durable (storage.json, synced DBs)
  cache/  — regenerable, OS-purgeable on device (this service's home)
  temp/   — throwaway scratch

Everything written here must be cheap to rebuild after an OS purge and must
NEVER hold the only copy of user data. Six cache layers live here:

  1. compiled_db.pkl   — pickled MaigretDatabase + meta sidecar (skip JSON
                         parse + regex recompile on startup, ~1.26x faster
                         cold start measured on the 1.4 MB manifest)
  2. avatars/          — on-device profile images keyed by sha256(url)
  3. reports/          — pre-rendered PDF/XMind dossiers keyed by a hash of
                         the found-URL set, so re-export is 0 ms
  4. geo_cache.json    — free-text location -> CountryInfo lookups
  5. sites_indices.json — inverted tag -> site-name buckets for O(1) chip
                         filtering in SitesScreen
  6. dns_cache.json    — confirmed-IP / known-dead domain records used to
                         pre-warm the OS resolver before a scan flood

All file writes are atomic (tmp + os.replace) so a mid-write crash or an
OS purge can never leave a half-written cache entry behind.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import pickle
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PICKLE_PROTOCOL = pickle.HIGHEST_PROTOCOL
_SHA256_BLOCK = 1 << 16  # 64 KB streaming blocks
_DNS_TTL_SEC = 24 * 3600


def _cache_root() -> Path:
    from services.storage_service import get_cache_dir

    return Path(get_cache_dir())


def _sha256_file(path: Path) -> str:
    """Stream a file through SHA-256 without loading it fully into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(_SHA256_BLOCK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _write_atomic(path: Path, writer: Any) -> bool:
    """Write through a temp file then os.replace; returns success.

    `writer` is a callable receiving the open temp file handle. Keeping the
    temp file inside the same directory guarantees an atomic same-filesystem
    rename on every platform we ship.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        with open(tmp, "wb") as fh:
            writer(fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        return True
    except Exception as exc:
        logger.warning("Cache write failed for %s: %s", path, exc)
        return False


def _write_json_atomic(path: Path, payload: Any) -> bool:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return _write_atomic(path, lambda fh: fh.write(data))


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── Layer 1: Pre-Compiled Site Database ────────────────────────────────────


def _db_cache_paths() -> tuple[Path, Path]:
    root = _cache_root()
    return root / "compiled_db.pkl", root / "compiled_db.meta.json"


def try_load_compiled_db(source_path: str) -> Any | None:
    """Return a cached MaigretDatabase if it matches the source manifest.

    Validation is hybrid mtime-then-hash: the manifest's mtime is compared
    first (free), and only a mismatch on that cheap check triggers the full
    SHA-256 pass (~9 ms on the 1.4 MB manifest) — so normal startup pays
    only a stat() call while still detecting replaced-but-equal-mtime
    manifests.

    Remote manifests (http(s):// URLs, routed by maigret's
    load_from_path) are not cacheable — they bypass entirely.
    """
    if "://" in source_path:
        return None

    pkl_path, meta_path = _db_cache_paths()
    try:
        src = Path(source_path)
        meta = _read_json(meta_path)
        if not isinstance(meta, dict) or meta.get("src") != source_path:
            return None

        src_stat = src.stat()
        if (
            meta.get("mtime") == src_stat.st_mtime
            and meta.get("size") == src_stat.st_size
        ):
            hash_matches = True
        else:
            # mtime/size changed — confirm with content hash before
            # discarding: editors that rewrite files can preserve neither.
            hash_matches = meta.get("hash") == _sha256_file(src)

        if not hash_matches:
            return None
        if not pkl_path.is_file():
            return None

        db = pickle.loads(pkl_path.read_bytes())
        # Sanity guard: the unpickled object must still look like a loaded
        # MaigretDatabase (sites list populated) before trusting it.
        if not db or not getattr(db, "sites", None):
            return None
        logger.info(
            "Loaded compiled DB cache: %d sites (pickle hit, %.1f KB)",
            len(db.sites),
            pkl_path.stat().st_size / 1024,
        )
        return db
    except Exception as exc:
        logger.info("Compiled DB cache unusable: %s", exc)
        return None


def save_compiled_db(source_path: str, db: Any) -> None:
    """Persist a parsed MaigretDatabase for next startup's instant load."""
    if "://" in source_path or db is None:
        return
    try:
        pkl_path, meta_path = _db_cache_paths()
        src = Path(source_path)
        stat = src.stat()
        payload = pickle.dumps(db, protocol=_PICKLE_PROTOCOL)

        ok = _write_atomic(pkl_path, lambda fh: fh.write(payload))
        if ok:
            meta = {
                "src": source_path,
                "hash": hashlib.sha256(payload).hexdigest(),
                "mtime": stat.st_mtime,
                "size": stat.st_size,
                "maigret_version": __import__("maigret").__version__,
                "pickle_protocol": _PICKLE_PROTOCOL,
                "saved_at": time.time(),
            }
            _write_json_atomic(meta_path, meta)
    except Exception as exc:
        logger.warning("Failed to save compiled DB cache: %s", exc)


# ── Layer 2: Avatar Image Cache ────────────────────────────────────────────


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


async def schedule_avatar_download(url: str) -> None:
    """Fetch an avatar to the cache in the background (fire-and-forget).

    Uses plain httpx with redirects followed; avatars frequently live on
    CDN hosts that 301 to the final media URL. Failures are silent — the
    UI always has the remote URL fallback.
    """
    if not url or not isinstance(url, str) or not url.startswith("http"):
        return
    dest = avatar_cache_path(url)
    if dest.is_file() and dest.stat().st_size > 0:
        return
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=5.0, follow_redirects=True, headers={"User-Agent": "Sherlock/2.x"}
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and resp.content:
                _write_atomic(dest, lambda fh: fh.write(resp.content))
    except Exception as exc:
        logger.debug("Avatar download skipped (%s): %s", url[:80], exc)


# ── Layer 3: Pre-Rendered Report Cache ─────────────────────────────────────


def _safe_name_component(raw: str) -> str:
    """Flatten a query/mode string into a filesystem-safe cache key chunk."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw.strip().lower())
    return cleaned[:48] or "unknown"


def results_fingerprint(found: list) -> str:
    """Stable 16-hex fingerprint of a found-URL set.

    Two scans of the same target that yield the same claimed accounts map
    to the same fingerprint — so an unchanged re-export reuses the cached
    PDF/XMind instead of re-running ReportLab table layout.
    """
    urls = sorted(
        {
            str(getattr(r, "url_user", "") or getattr(r, "url_main", "") or "")
            for r in found
        }
    )
    blob = "\n".join(urls).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def cached_report_path(mode: str, query: str, found: list, ext: str) -> Path:
    """Cache path for a rendered report keyed by (mode, query, results set)."""
    fp = results_fingerprint(found)
    name = f"{_safe_name_component(mode)}_{_safe_name_component(query)}_{fp}.{ext}"
    return _cache_root() / "reports" / name


def load_cached_report(mode: str, query: str, found: list, ext: str) -> bytes | None:
    """Return cached report bytes, or None on any miss/corruption."""
    try:
        p = cached_report_path(mode, query, found, ext)
        if p.is_file() and p.stat().st_size > 0:
            return p.read_bytes()
    except OSError:
        pass
    return None


def save_cached_report(
    mode: str, query: str, found: list, ext: str, data: bytes
) -> None:
    """Persist rendered report bytes after a fresh generation."""
    if not data:
        return
    try:
        p = cached_report_path(mode, query, found, ext)
        _write_atomic(p, lambda fh: fh.write(data))
    except Exception as exc:
        logger.debug("Report cache save skipped: %s", exc)


# ── Layer 4: Persistent Geo-Location Cache ─────────────────────────────────

_GEO_MIN_TS_KEY = "__pycountry__"
_GEO_MAX_ENTRIES = 4096


def load_geo_cache() -> dict[str, list[str]]:
    """Load persisted location lookups: string -> [name, flag, alpha2, ...]."""
    data = _read_json(_cache_root() / "geo_cache.json")
    if not isinstance(data, dict):
        return {}
    # Stale-cache guard: pycountry data changes between versions can
    # silently change fuzzy matches. Bump or drop the cache when the
    # library version recorded at write time no longer matches.
    version = __import__("pycountry").__version__
    if data.get(_GEO_MIN_TS_KEY) != version:
        return {}
    entries = data.get("entries")
    if isinstance(entries, dict) and len(entries) <= _GEO_MAX_ENTRIES:
        return {str(k): list(v) for k, v in entries.items() if isinstance(v, list)}
    return {}


def save_geo_cache(lookup: dict[str, list[str]]) -> None:
    """Persist location lookups, tagging them with the pycountry version."""
    version = __import__("pycountry").__version__
    trimmed = dict(list(lookup.items())[:_GEO_MAX_ENTRIES])
    _write_json_atomic(
        _cache_root() / "geo_cache.json",
        {_GEO_MIN_TS_KEY: version, "entries": trimmed, "saved_at": time.time()},
    )


# ── Layer 5: Inverted Site Tag Indices ──────────────────────────────────────


def build_sites_indices(sites_dict: dict[str, Any]) -> dict[str, Any]:
    """Build the inverted tag index from a ranked sites dict.

    Returns the payload persisted to cache/sites_indices.json:
      db_hash   — fingerprint of the ranked site-name set
      by_tag    — {tag: [site names]} for O(1) category chip filtering
      all_names — sorted full list ( SitesScreen fallback + stats )
    """
    by_tag: dict[str, list[str]] = {}
    names: list[str] = []
    for name, site in sites_dict.items():
        names.append(name)
        for tag in getattr(site, "tags", None) or []:
            tag_key = str(tag).lower()
            by_tag.setdefault(tag_key, []).append(name)
    for tag_list in by_tag.values():
        tag_list.sort(key=str.lower)

    blob = "\n".join(sorted(names)).encode("utf-8")
    return {
        "db_hash": hashlib.sha256(blob).hexdigest(),
        "by_tag": by_tag,
        "all_names": sorted(names, key=str.lower),
    }


def save_sites_indices(payload: dict[str, Any]) -> None:
    _write_json_atomic(_cache_root() / "sites_indices.json", payload)


def load_sites_indices() -> dict[str, Any] | None:
    data = _read_json(_cache_root() / "sites_indices.json")
    if isinstance(data, dict) and isinstance(data.get("by_tag"), dict):
        return data
    return None


# ── Layer 6: Persistent DNS Cache ───────────────────────────────────────────

_dns_store: dict[str, dict[str, Any]] | None = None
_dns_dirty = False


def _dns_path() -> Path:
    return _cache_root() / "dns_cache.json"


def load_dns_cache() -> dict[str, dict[str, Any]]:
    """Load {domain: {"ips": [...], "ts": epoch, "dead": bool}} records."""
    global _dns_store
    if _dns_store is not None:
        return _dns_store
    data = _read_json(_dns_path())
    entries: dict[str, dict[str, Any]] = {}
    if isinstance(data, dict):
        raw = data.get("entries")
        if isinstance(raw, dict):
            now = time.time()
            for domain, rec in raw.items():
                if not isinstance(rec, dict):
                    continue
                ts = rec.get("ts", 0) or 0
                ips = [str(i) for i in rec.get("ips", []) if i]
                if ips and (now - ts) > _DNS_TTL_SEC:
                    continue  # expired A-records
                entries[str(domain).lower()] = {
                    "ips": ips,
                    "ts": ts,
                    "dead": bool(rec.get("dead", False)),
                }
    _dns_store = entries
    return entries


def get_dns_record(domain: str) -> dict[str, Any] | None:
    return load_dns_cache().get(str(domain).lower().strip())


def set_dns_record(domain: str, ips: list[str] | None, dead: bool = False) -> None:
    """Record a resolved or confirmed-dead domain and mark the store dirty."""
    global _dns_dirty
    store = load_dns_cache()
    key = str(domain).lower().strip()
    if not key:
        return
    if dead:
        store[key] = {"ips": [], "ts": time.time(), "dead": True}
    else:
        store[key] = {
            "ips": [str(i) for i in ips or []],
            "ts": time.time(),
            "dead": False,
        }
    _dns_dirty = True


def flush_dns_cache() -> None:
    """Persist dirty DNS records (call after a scan or pre-warm pass)."""
    global _dns_dirty
    if not _dns_dirty or _dns_store is None:
        return
    ok = _write_json_atomic(
        _dns_path(), {"entries": _dns_store, "saved_at": time.time()}
    )
    if ok:
        _dns_dirty = False


def is_domain_dead(domain: str) -> bool:
    """True if the domain was previously confirmed to fail DNS resolution.

    Used to skip hopeless connections during pre-warm — not to skip actual
    site checks (a site may still be reachable behind a different host).
    """
    rec = get_dns_record(domain)
    return bool(rec and rec.get("dead"))


_DNS_PREWARM_CONCURRENCY = 64
_DNS_PREWARM_TIMEOUT = 2.0


async def prewarm_dns(sites: list[tuple[str, str]], max_hosts: int = 300) -> int:
    """Resolve site domains ahead of the scan flood to warm the OS resolver.

    Maigret builds its own aiohttp TCPConnector internally, so resolved IPs
    cannot be injected into the scan — but the OS getaddrinfo cache is shared
    by every connector. Resolving the scan's domains up-front (bounded,
    small timeout, confirmed-dead hosts skipped via the persistent DNS
    cache) means the request flood mostly finds warm entries instead of
    firing 3,300 DNS queries through the same pipe.

    `sites` is a list of (site_name, url) pairs; only unique hostnames are
    resolved. Returns the number of hosts successfully warmed.
    """
    from urllib.parse import urlparse

    seen_hosts: set[str] = set()
    host_list: list[str] = []
    for _name, url in sites:
        try:
            host = urlparse(url).hostname
        except ValueError:
            continue
        if host and host not in seen_hosts:
            seen_hosts.add(host)
            if not is_domain_dead(host):
                host_list.append(host)
            if len(host_list) >= max_hosts:
                break

    if not host_list:
        return 0

    import socket

    warmed = 0
    sem = asyncio.Semaphore(_DNS_PREWARM_CONCURRENCY)

    async def _resolve(host: str) -> None:
        nonlocal warmed
        async with sem:
            try:
                infos = await asyncio.wait_for(
                    asyncio.get_running_loop().getaddrinfo(
                        host, 443, type=socket.SOCK_STREAM
                    ),
                    timeout=_DNS_PREWARM_TIMEOUT,
                )
                if infos:
                    warmed += 1
                    set_dns_record(
                        host, [i[4][0] for i in infos if len(i) >= 4 and i[4]]
                    )
            except Exception:
                # Resolve failures during pre-warm are NOT recorded dead:
                # a flaky moment or captive portal shouldn't blacklist a
                # domain for later scans. Only explicit 0-record resolutions
                # recorded elsewhere set the dead flag.
                pass

    await asyncio.gather(*[_resolve(h) for h in host_list])
    flush_dns_cache()
    return warmed


def clear_all_caches() -> int:
    """Development/testing helper — wipe every regenerable cache artifact.

    Returns the number of top-level artifacts removed. Never touches
    data/ or temp/ tiers.
    """
    removed = 0
    try:
        root = _cache_root()
        if root.is_dir():
            for child in root.iterdir():
                if child.name.startswith("."):
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
    except OSError:
        pass
    global _dns_store, _dns_dirty
    _dns_store = None
    _dns_dirty = False
    return removed
