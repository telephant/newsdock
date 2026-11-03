"""Opt-in article fields (ADR-0030, ADR-0033): the names a caller may put in `include`.

The four stored GDELT tone numbers (spec tone-in-summary) and `events` (spec
events-mentions: the GDELT events an article is mentioned in). Checked here, before any
query runs, so MCP, REST and the other surfaces share one set of rules. Pure: the
standard library only.
"""

from collections.abc import Iterable

TONE_FIELDS: tuple[str, ...] = ("tone", "tone_pos", "tone_neg", "tone_polarity")
EVENTS_FIELD = "events"
BODY_FIELD = "body"  # spec body-extraction: the fetched page text
INCLUDE_NAMES: tuple[str, ...] = (*TONE_FIELDS, EVENTS_FIELD, BODY_FIELD)


class InvalidInclude(ValueError):
    """An unknown or empty field name (MCP `invalid_include`, REST 422)."""


def parse_include(raw: Iterable[str] | str | None) -> tuple[str, ...]:
    """The requested fields, deduplicated in the order first given.

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
    unknown = [name for name in names if name not in INCLUDE_NAMES]
    if unknown:
        shown = ", ".join(repr(name) for name in unknown)
        raise InvalidInclude(f"unknown include {shown}; choose from {INCLUDE_NAMES}")
    return tuple(dict.fromkeys(names))
