"""The body status names are fixed (design-detail section 2) and match the migration."""

from pathlib import Path

from newsdock_extractor.domain.status import FINAL_STATUSES, BodyStatus

ROOT = Path(__file__).resolve().parents[4]


def test_the_statuses_are_exactly_the_designed_names() -> None:
    assert [s.value for s in BodyStatus] == [
        "pending",
        "ok",
        "blocked_robots",
        "blocked_address",
        "http_error",
        "not_html",
        "too_large",
        "no_text",
        "failed",
    ]


def test_every_status_but_pending_is_final() -> None:
    assert set(BodyStatus) - FINAL_STATUSES == {BodyStatus.pending}


def test_the_names_equal_the_ones_the_migration_allows() -> None:
    migration = (ROOT / "infra/migrations/versions/0012_article_bodies.py").read_text()
    for status in BodyStatus:
        assert f"'{status.value}'" in migration, status
