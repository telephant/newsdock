"""TC-14 (AC-7), pure half: newest first, nothing older than the retention window."""

from datetime import UTC, datetime, timedelta

from newsdock_extractor.domain.picking import QueueRow, eligible, window_start

NOW = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)


def row(seq: int, age_hours: float = 1.0, *, wait_minutes: float = 0.0) -> QueueRow:
    return QueueRow(
        url_hash=f"h{seq}",
        url=f"https://site{seq}.example/{seq}",
        seq=seq,
        created_at=NOW - timedelta(hours=age_hours),
        next_attempt_at=NOW + timedelta(minutes=wait_minutes),
        attempts=0,
    )


def test_the_window_starts_retention_days_ago() -> None:
    assert window_start(NOW, retention_days=7) == NOW - timedelta(days=7)


def test_rows_come_newest_first() -> None:
    rows = [row(3), row(9), row(1), row(7)]
    assert [r.seq for r in eligible(rows, NOW, retention_days=7)] == [9, 7, 3, 1]


def test_rows_older_than_the_window_are_never_returned() -> None:
    rows = [row(1, age_hours=24 * 7 + 1), row(2, age_hours=24 * 7 - 1), row(3, 1)]
    assert [r.seq for r in eligible(rows, NOW, retention_days=7)] == [3, 2]


def test_a_row_exactly_at_the_window_edge_is_still_taken() -> None:
    edge = row(1, age_hours=24 * 7)
    assert eligible([edge], NOW, retention_days=7) == [edge]


def test_rows_waiting_for_a_retry_are_not_due_yet() -> None:
    rows = [row(1, wait_minutes=5), row(2), row(3, wait_minutes=-1)]
    assert [r.seq for r in eligible(rows, NOW, retention_days=7)] == [3, 2]


def test_the_limit_keeps_the_newest() -> None:
    rows = [row(n) for n in range(1, 11)]
    assert [r.seq for r in eligible(rows, NOW, retention_days=7, limit=3)] == [10, 9, 8]


def test_an_old_backlog_cannot_push_out_new_rows() -> None:
    old = [row(n, age_hours=100) for n in range(1, 500)]
    new = [row(1000), row(1001)]
    got = eligible(old + new, NOW, retention_days=7, limit=5)
    assert [r.seq for r in got][:2] == [1001, 1000]


def test_nothing_due_gives_an_empty_list() -> None:
    assert eligible([], NOW, retention_days=7) == []
    assert eligible([row(1, wait_minutes=60)], NOW, retention_days=7) == []
