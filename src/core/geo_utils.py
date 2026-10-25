"""Country-flag helpers — dependency-free.

The engine supplies location strings and 2-letter site tags natively
(`Result.extra["location"]`, site tag indexes); the only value this module
adds is the flag emoji for an ISO 3166-1 alpha-2 code, which is computable
from regional-indicator symbols with no country database.
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=512)
def flag_for_alpha2(code: str) -> str:
    """Flag emoji for a 2-letter ISO 3166-1 alpha-2 code, else ''.

    Computes regional-indicator symbols (U+1F1E6..U+1F1FF) — the same
    string pycountry's `.flag` property returns, with zero dependencies.
    """
    c = (code or "").strip().upper()
    if len(c) != 2 or not c.isascii() or not c.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - 65) for ch in c)


@lru_cache(maxsize=512)
def first_country_tag(tags: tuple[str, ...]) -> str:
    """First tag in the tuple that looks like a 2-letter country code."""
    for t in tags:
        tag = (t or "").strip().lower()
        if len(tag) == 2 and tag.isascii() and tag.isalpha():
            return tag
    return ""
