"""Parse GDELT's lastupdate.txt index (format: `size md5 url` per line)."""

import re
from dataclasses import dataclass

_SLOT_RE = re.compile(r"(\d{14})\.gkg\.csv\.zip$")


@dataclass(frozen=True)
class GkgIndexEntry:
    slot: str
    md5: str
    url: str


def parse_lastupdate(text: str) -> GkgIndexEntry | None:
    """Return the GKG entry of the newest slot, or None when absent."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        match = _SLOT_RE.search(parts[2])
        if match:
            return GkgIndexEntry(slot=match.group(1), md5=parts[1], url=parts[2])
    return None
