"""TC-28: the Alembic project gets its URL only through newsdock_db (DR-9)."""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def test_env_py_uses_newsdock_db_and_never_reads_the_environment() -> None:
    text = (MIGRATIONS / "env.py").read_text()
    assert "newsdock_db.config" in text
    assert "newsdock_db.metadata" in text
    assert "os.environ" not in text and "getenv" not in text


def test_baseline_revision_is_0001_and_forward_only() -> None:
    text = (MIGRATIONS / "versions" / "0001_baseline.py").read_text()
    assert 'revision: str = "0001"' in text
    assert "CREATE EXTENSION IF NOT EXISTS vector" in text
    assert "def downgrade" in text


def test_events_mentions_revision_is_0011_and_forward_only() -> None:
    text = (MIGRATIONS / "versions" / "0011_events_mentions.py").read_text()
    assert 'revision: str = "0011"' in text
    assert 'down_revision: str | None = "0010"' in text
    assert "def downgrade" in text
    assert "ForeignKey" not in text  # ADR-0033: joined by url_hash, no foreign key


def test_article_bodies_revision_is_0012_and_forward_only() -> None:
    text = (MIGRATIONS / "versions" / "0012_article_bodies.py").read_text()
    assert 'revision: str = "0012"' in text
    assert 'down_revision: str | None = "0011"' in text
    assert "def downgrade" in text
    assert "halfvec" in text.lower()
