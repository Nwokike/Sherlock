"""Username permutation — separator/case variants for broader OSINT sweeps.

Same handle often exists under different separators ("john.doe" vs
"john_doe"). Variants are capped and never include the original — the
caller joins them onto the primary target. All variants must pass the
same shape rule as the Home gate (letters, numbers, _ . -).
"""

from __future__ import annotations

import re

# Hard cap: each variant multiplies the scan length (one full site sweep
# per handle), so permutations stay a deliberate opt-in, not a surprise.
MAX_VARIANTS = 5

_SHAPE_RE = re.compile(r"[A-Za-z0-9_.\-]+")
# Source separators: only real ones ("": joining is a swap TARGET, not a
# source — "" in any string is True and would wrap every character).
_SOURCE_SEPARATORS = ("_", "-", ".")
_SEPARATORS = (*_SOURCE_SEPARATORS, "")


def permute_username(name: str, max_variants: int = MAX_VARIANTS) -> list[str]:
    """Return up to max_variants separator or pattern variants of ``name``.

    Supports both combinatorial bracketed patterns (via user-scanner
    core.patterns) and intelligent separator normalization (unifying hybrid
    delimiters like john.doe_smith -> john_doe_smith).
    """
    base = (name or "").strip()
    if not base or len(base) > 64:
        return []

    # If pattern syntax (e.g. user[0-9]) is present, expand patterns from user_scanner
    if "[" in base and "]" in base:
        try:
            from user_scanner.core.patterns import expand_patterns

            variants = []
            for candidate in expand_patterns(base):
                if candidate != base and candidate not in variants:
                    variants.append(candidate)
                    if len(variants) >= max_variants:
                        return variants
            if variants:
                return variants
        except Exception:
            pass

    if not _SHAPE_RE.fullmatch(base):
        return []

    seen: set[str] = {base.lower()}
    variants: list[str] = []

    # 1. First prioritize fully-unified separator variants (most valuable)
    # e.g. john.doe_smith -> john_doe_smith, john.doe.smith, john-doe-smith, johndoesmith
    has_any_sep = any(s in base for s in _SOURCE_SEPARATORS)
    if has_any_sep:
        for target in _SEPARATORS:
            unified = base
            for s in _SOURCE_SEPARATORS:
                unified = unified.replace(s, target)
            if unified and unified.lower() not in seen and _SHAPE_RE.fullmatch(unified):
                seen.add(unified.lower())
                variants.append(unified)
                if len(variants) >= max_variants:
                    return variants

    # 2. Individual separator substitutions
    for sep in _SOURCE_SEPARATORS:
        if sep in base:
            swapped = base.replace(sep, "\x00")
            for target in _SEPARATORS:
                if target == sep:
                    continue
                candidate = swapped.replace("\x00", target)
                if candidate and candidate.lower() not in seen and _SHAPE_RE.fullmatch(candidate):
                    seen.add(candidate.lower())
                    variants.append(candidate)
                    if len(variants) >= max_variants:
                        return variants

    return variants
