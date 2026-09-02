"""Geographic intelligence utilities powered by pycountry."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)

_PYCOUNTRY_AVAILABLE = False
try:
    import pycountry
    from pycountry import remove_accents

    _PYCOUNTRY_AVAILABLE = True
except ImportError as err:
    logger.warning("pycountry library not available: %s", err)
    pycountry = None
    remove_accents = lambda s: s  # noqa: E731

# L2 disk cache (cache/geo_cache.json via cache_service) layered under the
# in-memory lru_cache: a cold launch restores past lookups instead of
# re-running pycountry fuzzy matching per string. Populated lazily on the
# first location resolve; persisted fields mirror CountryInfo.
_DISK_CACHE: dict[str, list[str]] | None = None
# Disk flushes are rate-limited: resolve_location runs ON the UI render
# path, and a file write per novel location was render-path IO. Memory
# updates stay instant; disk lags at most _GEO_FLUSH_INTERVAL.
_GEO_FLUSH_INTERVAL = 10.0
_LAST_GEO_FLUSH = [0.0]
_GEO_FLUSH_DIRTY = [False]


def _country_to_row(c: CountryInfo | None) -> list[str] | None:
    if c is None:
        return None
    return [c.name, c.flag, c.alpha_2, c.alpha_3, c.official_name, c.subdivision]


def _row_to_country(row: list[str]) -> CountryInfo:
    pad = (row + [""] * 6)[:6]
    return CountryInfo(
        name=pad[0],
        flag=pad[1],
        alpha_2=pad[2],
        alpha_3=pad[3],
        official_name=pad[4],
        subdivision=pad[5],
    )


def _load_disk_cache() -> dict[str, list[str]]:
    global _DISK_CACHE
    if _DISK_CACHE is None:
        _DISK_CACHE = {}
        if _PYCOUNTRY_AVAILABLE:
            try:
                from services.cache_service import load_geo_cache

                _DISK_CACHE = load_geo_cache()
            except Exception as exc:
                logger.debug("geo disk cache unavailable: %s", exc)
    return _DISK_CACHE


def _record_disk_hit(key: str, c: CountryInfo | None) -> None:
    """Remember a resolved (or confirmed-unresolvable) location string and
    persist at most once per flush interval. A stored empty row means
    "known unresolvable"; past successes are never downgraded to failures.
    """
    store = _load_disk_cache()
    if c is None and store.get(key):
        return  # never overwrite a past success with a failure
    row = _country_to_row(c)
    new_val = row if row is not None else []
    if store.get(key) == new_val:
        return
    store[key] = new_val
    import time as _time

    now = _time.monotonic()
    if _GEO_FLUSH_DIRTY[0] or (now - _LAST_GEO_FLUSH[0]) < _GEO_FLUSH_INTERVAL:
        _GEO_FLUSH_DIRTY[0] = True  # memory holds it; disk flushes later
        return
    _LAST_GEO_FLUSH[0] = now
    try:
        from services.cache_service import save_geo_cache

        save_geo_cache(store)
    except Exception:
        pass


@dataclass(frozen=True)
class CountryInfo:
    """Structured country intelligence."""

    name: str
    flag: str
    alpha_2: str
    alpha_3: str = ""
    official_name: str = ""
    subdivision: str = ""


@lru_cache(maxsize=512)
def get_country_by_tag(tag: str) -> CountryInfo | None:
    """Resolve a 2-letter site tag (e.g. 'us', 'ng', 'ru', 'de') to CountryInfo."""
    if not _PYCOUNTRY_AVAILABLE or not tag or len(tag.strip()) != 2:
        return None
    try:
        c = pycountry.countries.get(alpha_2=tag.strip().upper())
        if c:
            return CountryInfo(
                name=c.name,
                flag=getattr(c, "flag", ""),
                alpha_2=c.alpha_2,
                alpha_3=getattr(c, "alpha_3", ""),
                official_name=getattr(c, "official_name", c.name),
            )
    except Exception:
        pass
    return None


@lru_cache(maxsize=256)
def get_site_country(tags: tuple[str, ...]) -> CountryInfo | None:
    """Find the first matching country from a site's tags tuple."""
    for t in tags:
        c = get_country_by_tag(t)
        if c:
            return c
    return None


@lru_cache(maxsize=512)
def resolve_location(loc_str: str) -> CountryInfo | None:
    """Resolve free-text location string to CountryInfo with subdivision if known."""
    if not _PYCOUNTRY_AVAILABLE or not loc_str or not loc_str.strip():
        return None

    # L2 disk cache check — restores lookups from a previous launch without
    # re-running pycountry fuzzy matching (which scans every country name).
    # A stored empty row means "known unresolvable".
    disk = _load_disk_cache()
    if loc_str in disk:
        row = disk[loc_str]
        return _row_to_country(row) if row else None

    raw = loc_str.strip()
    candidates = [raw]
    parts = [
        p.strip()
        for p in raw.replace("/", ",").replace("-", ",").split(",")
        if p.strip()
    ]
    candidates.extend(reversed(parts))

    result: CountryInfo | None = None
    for cand in candidates:
        clean = remove_accents(cand).strip()
        if not clean:
            continue
        try:
            matches = pycountry.countries.search_fuzzy(clean)
            if matches:
                c = matches[0]
                result = CountryInfo(
                    name=c.name,
                    flag=getattr(c, "flag", ""),
                    alpha_2=c.alpha_2,
                    alpha_3=c.alpha_3,
                    official_name=getattr(c, "official_name", c.name),
                )
                break
        except Exception:
            pass

        try:
            sub_matches = pycountry.subdivisions.search_fuzzy(clean)
            if sub_matches:
                sd = sub_matches[0]
                c = sd.country
                result = CountryInfo(
                    name=c.name,
                    flag=getattr(c, "flag", ""),
                    alpha_2=c.alpha_2,
                    alpha_3=c.alpha_3,
                    official_name=getattr(c, "official_name", c.name),
                    subdivision=sd.name,
                )
                break
        except Exception:
            pass

    # Persist the outcome (success or confirmed-unresolvable) for next
    # launch — same-input lookups then cost one dict read.
    _record_disk_hit(loc_str, result)
    return result
