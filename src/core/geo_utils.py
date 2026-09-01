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

    raw = loc_str.strip()
    candidates = [raw]
    parts = [
        p.strip()
        for p in raw.replace("/", ",").replace("-", ",").split(",")
        if p.strip()
    ]
    candidates.extend(reversed(parts))

    for cand in candidates:
        clean = remove_accents(cand).strip()
        if not clean:
            continue
        try:
            matches = pycountry.countries.search_fuzzy(clean)
            if matches:
                c = matches[0]
                return CountryInfo(
                    name=c.name,
                    flag=getattr(c, "flag", ""),
                    alpha_2=c.alpha_2,
                    alpha_3=getattr(c, "alpha_3", ""),
                    official_name=getattr(c, "official_name", c.name),
                )
        except Exception:
            pass

        try:
            sub_matches = pycountry.subdivisions.search_fuzzy(clean)
            if sub_matches:
                sd = sub_matches[0]
                c = sd.country
                return CountryInfo(
                    name=c.name,
                    flag=getattr(c, "flag", ""),
                    alpha_2=c.alpha_2,
                    alpha_3=getattr(c, "alpha_3", ""),
                    official_name=getattr(c, "official_name", c.name),
                    subdivision=sd.name,
                )
        except Exception:
            pass

    return None
