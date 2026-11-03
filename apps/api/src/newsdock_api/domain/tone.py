"""Tone rules (spec tone-in-summary D-2, D-4, D-6): which `min_negativity` values are
valid. Pure: the standard library only.

`min_negativity` keeps articles whose `tone_neg` is at or above a value; it is checked
here, before any query runs, so the surfaces (MCP, REST, subscriptions) share one rule.
The `include` rules moved to `domain/include.py` when `events` joined the tone names
(spec events-mentions); they are re-exported here so existing imports keep working.
"""

import math

from newsdock_api.domain.include import TONE_FIELDS, InvalidInclude, parse_include

__all__ = [
    "NEGATIVITY_MAX",
    "NEGATIVITY_MIN",
    "TONE_FIELDS",
    "InvalidInclude",
    "InvalidNegativity",
    "check_min_negativity",
    "parse_include",
]

NEGATIVITY_MIN = 0.0
NEGATIVITY_MAX = 100.0


class InvalidNegativity(ValueError):
    """`min_negativity` is not a number from 0 to 100 (MCP `invalid_filter`, 422)."""


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
