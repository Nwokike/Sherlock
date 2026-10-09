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


def permute_username(name: str) -> list[str]:
    """Return up to MAX_VARIANTS separator variants of ``name``.

    Separator swaps only: most platforms treat handles case-insensitively,
    so a case-folded variant would rescan the same account. The original
    name, duplicates, and shape-invalid results are excluded.
    """
    base = (name or "").strip()
    if not base or len(base) > 64 or not _SHAPE_RE.fullmatch(base):
        return []

    seen: set[str] = {base.lower()}
    variants: list[str] = []

    for sep in _SOURCE_SEPARATORS:
        if sep in base:
            swapped = base.replace(sep, "\x00")
            for target in _SEPARATORS:
                if target == sep:
                    continue
                candidate = swapped.replace("\x00", target)
                if candidate.lower() not in seen and _SHAPE_RE.fullmatch(candidate):
                    seen.add(candidate.lower())
                    variants.append(candidate)
                    if len(variants) >= MAX_VARIANTS:
                        return variants

    return variants
