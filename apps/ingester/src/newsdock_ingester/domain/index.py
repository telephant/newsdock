"""Parse GDELT's lastupdate.txt index (format: `size md5 url` per line)."""

import re
from dataclasses import dataclass

_FILE_RE = re.compile(r"(\d{14})\.(gkg\.csv|export\.CSV|mentions\.CSV)\.zip$")
_KIND_BY_SUFFIX = {
    "gkg.csv": "gkg",
    "export.CSV": "events",
    "mentions.CSV": "mentions",
}


@dataclass(frozen=True)
class IndexEntry:
    slot: str
    kind: str  # gkg | events | mentions
    md5: str
    url: str


GkgIndexEntry = IndexEntry  # the GKG entry keeps its old name for existing callers


def parse_index(text: str) -> list[IndexEntry]:
    """Every recognised file of the newest slot, in the order the index lists them."""
    entries: list[IndexEntry] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        match = _FILE_RE.search(parts[2])
        if match:
            entries.append(
                IndexEntry(
                    slot=match.group(1),
                    kind=_KIND_BY_SUFFIX[match.group(2)],
                    md5=parts[1],
                    url=parts[2],
                )
            )
    return entries


def parse_lastupdate(text: str) -> IndexEntry | None:
    """Return the GKG entry of the newest slot, or None when absent."""
    for entry in parse_index(text):
        if entry.kind == "gkg":
            return entry
    return None
