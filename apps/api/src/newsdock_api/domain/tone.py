"""Tone rules (spec tone-in-summary D-2, D-4, D-6): which tone fields a caller may
ask for and which `min_negativity` values are valid. Pure: the standard library only.

`include` adds stored GDELT tone numbers to the articles of a list; `min_negativity`
keeps articles whose `tone_neg` is at or above a value. Both are checked here, before
any query runs, so the surfaces (MCP, REST, subscriptions) share one set of rules.
"""

import math
from collections.abc import Iterable

TONE_FIELDS: tuple[str, ...] = ("tone", "tone_pos", "tone_neg", "tone_polarity")

NEGATIVITY_MIN = 0.0
NEGATIVITY_MAX = 100.0


class InvalidInclude(ValueError):
    """An unknown or empty field name (MCP `invalid_include`, REST 422)."""


class InvalidNegativity(ValueError):
    """`min_negativity` is not a number from 0 to 100 (MCP `invalid_filter`, 422)."""


def parse_include(raw: Iterable[str] | str | None) -> tuple[str, ...]:
    """The requested tone fields, deduplicated in the order first given.

    None or empty means no extra fields. A string is a comma-separated list (REST);
    blank pieces of it are ignored. In a list every name must be a known field.
    """
    if raw is None:
        return ()
    if isinstance(raw, str):
        names = [piece.strip() for piece in raw.split(",")]
        names = [name for name in names if name]
    else:
        names = []
        for item in raw:
            if not isinstance(item, str):
                raise InvalidInclude("include names must be strings")
            names.append(item.strip())
    unknown = [name for name in names if name not in TONE_FIELDS]
    if unknown:
        shown = ", ".join(repr(name) for name in unknown)
        raise InvalidInclude(f"unknown include {shown}; choose from {TONE_FIELDS}")
    return tuple(dict.fromkeys(names))


def check_min_negativity(value: float | None) -> float | None:
    """The value unchanged if it is None or a finite number from 0 to 100."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidNegativity("min_negativity must be a number")
    if not math.isfinite(value) or not NEGATIVITY_MIN <= value <= NEGATIVITY_MAX:
        raise InvalidNegativity(
            f"min_negativity must be from {NEGATIVITY_MIN:g} to {NEGATIVITY_MAX:g}"
        )
    return value
