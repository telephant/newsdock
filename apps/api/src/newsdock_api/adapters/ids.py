"""UUID-shaped id guard: a malformed id is 'absent', never a database error."""

from uuid import UUID


def as_uuid(value: str) -> str | None:
    try:
        return str(UUID(value))
    except ValueError:
        return None
