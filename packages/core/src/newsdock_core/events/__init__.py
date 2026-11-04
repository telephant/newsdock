"""GDELT 2.0 Events row parsing: one 61-column TSV line → CleanEvent or DlqMessage.

Column map checked against real rows from six slots (spec events-mentions, T-01).
0-based indexes, with the 1-based GDELT number in brackets:
0 [1] GLOBALEVENTID, 1 [2] SQLDATE, 5-7 and 12 [6-8, 13] Actor1 code, name, country,
type1, 15-17 and 22 [16-18, 23] Actor2, 25 [26] IsRootEvent, 26-28 [27-29] CAMEO
code, base, root, 29 [30] QuadClass, 30 [31] GoldsteinScale, 31-33 [32-34]
NumMentions, NumSources, NumArticles, 34 [35] AvgTone, 52-54 and 56-57 [53-55, 57-58]
ActionGeo name, country, ADM1, lat, long, 59 [60] DATEADDED, 60 [61] SOURCEURL.
"""

from datetime import UTC, datetime

from newsdock_core.contracts import (
    Actor,
    CleanEvent,
    DlqMessage,
    DlqReason,
    Geo,
)
from newsdock_core.urls import normalize_url, url_hash

EVENT_COLUMN_COUNT = 61


def _text(value: str) -> str | None:
    value = value.strip()
    return value or None


def _opt_float(value: str) -> float | None:
    value = value.strip()
    return float(value) if value else None


def _opt_int(value: str) -> int | None:
    value = value.strip()
    return int(value) if value else None


def _actor(columns: list[str], first: int, type1: int) -> Actor:
    return Actor(
        code=_text(columns[first]),
        name=_text(columns[first + 1]),
        country=_text(columns[first + 2]),
        type1=_text(columns[type1]),
    )


def _geo(columns: list[str]) -> Geo | None:
    geo = Geo(
        name=_text(columns[52]),
        country=_text(columns[53]),
        adm1=_text(columns[54]),
        lat=_opt_float(columns[56]),
        lon=_opt_float(columns[57]),
    )
    return geo if geo.model_dump(exclude_none=True) else None


def parse_event_row(*, slot: str, row_no: int, line: str) -> CleanEvent | DlqMessage:
    """Parse one raw Events line; never raises, odd errors become `bad_field`."""

    def dlq(reason: DlqReason) -> DlqMessage:
        return DlqMessage(
            reason=reason, slot=slot, row_no=row_no, line=line, kind="events"
        )

    columns = line.split("\t")
    if len(columns) != EVENT_COLUMN_COUNT:
        return dlq(DlqReason.bad_column_count)

    event_id = columns[0].strip()
    if not event_id.isdigit():
        return dlq(DlqReason.missing_event_id)

    url = columns[60].strip()
    if not url:
        return dlq(DlqReason.missing_url)

    try:
        event_date = datetime.strptime(columns[1], "%Y%m%d").replace(tzinfo=UTC).date()
        date_added = datetime.strptime(columns[59], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        cameo_code = columns[26].strip()
        if not cameo_code:
            return dlq(DlqReason.bad_field)
        return CleanEvent(
            event_id=int(event_id),
            event_date=event_date,
            actor1=_actor(columns, 5, 12),
            actor2=_actor(columns, 15, 22),
            is_root=columns[25].strip() == "1",
            cameo_code=cameo_code,
            cameo_base=_text(columns[27]),
            cameo_root=_text(columns[28]),
            quad_class=_opt_int(columns[29]),
            goldstein=_opt_float(columns[30]),
            num_mentions=int(columns[31]),
            num_sources=int(columns[32]),
            num_articles=int(columns[33]),
            avg_tone=_opt_float(columns[34]),
            geo=_geo(columns),
            date_added=date_added,
            source_url=normalize_url(url),
            source_url_hash=url_hash(url),
        )
    except (ValueError, IndexError):
        return dlq(DlqReason.bad_field)
