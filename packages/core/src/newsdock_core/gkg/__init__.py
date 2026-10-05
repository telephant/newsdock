"""GKG row parsing: one 27-column TSV line → CleanArticle or DlqMessage.

Column map verified against real rows in docs/research.md §2 (1-based):
1 GKGRECORDID · 2 DATE · 4 SourceCommonName · 5 DocumentIdentifier ·
8 V1Themes · 9 V2EnhancedThemes · 13 V2Persons · 15 V2Orgs · 16 V2Tone ·
27 Extras XML (<PAGE_TITLE>, <PAGE_PRECISEPUBTIMESTAMP>).
"""

import re
from datetime import UTC, datetime

from newsdock_core.contracts import CleanArticle, DlqMessage, DlqReason, Tone
from newsdock_core.urls import normalize_url, url_hash

GKG_COLUMN_COUNT = 27

_TITLE_RE = re.compile(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", re.S)
_PRECISE_TS_RE = re.compile(
    r"<PAGE_PRECISEPUBTIMESTAMP>(\d{14})</PAGE_PRECISEPUBTIMESTAMP>"
)


def _parse_ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def _strip_offsets(field: str) -> list[str]:
    """'Name,offset;…' or 'CODE;…' → unique names in first-seen order."""
    out: list[str] = []
    for part in field.split(";"):
        if not part:
            continue
        head, sep, tail = part.rpartition(",")
        name = head if sep and tail.isdigit() else part
        if name and name not in out:
            out.append(name)
    return out


def _published_at(extras: str, date_col: str) -> datetime:
    """Precise publish timestamp when present and parseable, else col 2 (R-3)."""
    match = _PRECISE_TS_RE.search(extras)
    if match:
        try:
            return _parse_ts(match.group(1))
        except ValueError:
            pass
    return _parse_ts(date_col)


def parse_row(*, slot: str, row_no: int, line: str) -> CleanArticle | DlqMessage:
    """Parse one raw GKG line; never raises — unexpected errors become `bad_field`."""

    def dlq(reason: DlqReason) -> DlqMessage:
        return DlqMessage(reason=reason, slot=slot, row_no=row_no, line=line)

    columns = line.split("\t")
    if len(columns) != GKG_COLUMN_COUNT:
        return dlq(DlqReason.bad_column_count)

    url = columns[4].strip()
    if not url:
        return dlq(DlqReason.missing_url)

    extras = columns[26]
    title_match = _TITLE_RE.search(extras)
    title = title_match.group(1).strip() if title_match else ""
    if not title:
        return dlq(DlqReason.missing_title)

    try:
        tone_values = columns[15].split(",")
        tone = Tone(
            tone=float(tone_values[0]),
            positive=float(tone_values[1]),
            negative=float(tone_values[2]),
            polarity=float(tone_values[3]),
            word_count=int(tone_values[6]),
        )
        return CleanArticle(
            url_hash=url_hash(url),
            gkg_record_id=columns[0],
            slot=slot,
            url=normalize_url(url),
            title=title,
            domain=columns[3] or None,
            published_at=_published_at(extras, columns[1]),
            themes=_strip_offsets(columns[8] or columns[7]),
            persons=_strip_offsets(columns[12]),
            orgs=_strip_offsets(columns[14]),
            tone=tone,
        )
    except (ValueError, IndexError):
        return dlq(DlqReason.bad_field)
