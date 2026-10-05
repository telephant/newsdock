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
