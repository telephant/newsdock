"""GDELT 2.0 Mentions row parsing: one 16-column TSV line → CleanMention or DlqMessage.

Column map checked against real rows from six slots (spec events-mentions, T-01).
0-based indexes [1-based]: 0 [1] GLOBALEVENTID · 2 [3] MentionTimeDate · 4 [5]
MentionSourceName · 5 [6] MentionIdentifier (the URL) · 11 [12] Confidence.
"""

from datetime import UTC, datetime

from newsdock_core.contracts import CleanMention, DlqMessage, DlqReason
from newsdock_core.urls import normalize_url, url_hash

MENTION_COLUMN_COUNT = 16


def parse_mention_row(
    *, slot: str, row_no: int, line: str
) -> CleanMention | DlqMessage:
    """Parse one raw Mentions line; never raises, odd errors become `bad_field`."""

    def dlq(reason: DlqReason) -> DlqMessage:
        return DlqMessage(
            reason=reason, slot=slot, row_no=row_no, line=line, kind="mentions"
        )

    columns = line.split("\t")
    if len(columns) != MENTION_COLUMN_COUNT:
        return dlq(DlqReason.bad_column_count)

    event_id = columns[0].strip()
    if not event_id.isdigit():
        return dlq(DlqReason.missing_event_id)

    url = columns[5].strip()
    if not url:
        return dlq(DlqReason.missing_url)

    try:
        confidence = columns[11].strip()
        return CleanMention(
            event_id=int(event_id),
            url=normalize_url(url),
            url_hash=url_hash(url),
            source_name=columns[4].strip() or None,
            mention_time=datetime.strptime(columns[2], "%Y%m%d%H%M%S").replace(
                tzinfo=UTC
            ),
            confidence=int(confidence) if confidence else None,
        )
    except (ValueError, IndexError):
        return dlq(DlqReason.bad_field)
