"""TC-24 (AC-8): migration 0010 and the ORM model for `password_resets` (Docker)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from newsdock_db.engine import make_engine
from newsdock_db.metadata import metadata
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]


def _config() -> Config:
    return Config(str(ROOT / "infra" / "migrations" / "alembic.ini"))


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


def test_migration_0010_creates_the_table_with_its_key_cascade_index_and_grants(
    engine: Engine,
) -> None:
    command.upgrade(_config(), "0009")
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT to_regclass('password_resets')")).scalar() is None
        )

    command.upgrade(_config(), "0010")

    with engine.connect() as conn:
        columns = {
            name: (kind, notnull)
            for name, kind, notnull in conn.execute(
                text(
                    "SELECT attname, format_type(atttypid, atttypmod), attnotnull "
                    "FROM pg_attribute WHERE attrelid = 'password_resets'::regclass "
                    "AND attnum > 0 AND NOT attisdropped"
                )
            )
        }
        assert columns == {
            "user_id": ("uuid", True),
            "code_hash": ("text", True),
            "expires_at": ("timestamp with time zone", True),
            "attempts": ("integer", True),
            "created_at": ("timestamp with time zone", True),
        }
        primary_key = (
            conn.execute(
                text(
                    "SELECT a.attname FROM pg_index i JOIN pg_attribute a "
                    "ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey) "
                    "WHERE i.indrelid = 'password_resets'::regclass AND i.indisprimary"
                )
            )
            .scalars()
            .all()
        )
        assert primary_key == ["user_id"]  # one open code per user
        cascade = conn.execute(
            text(
                "SELECT confdeltype FROM pg_constraint WHERE conrelid = "
                "'password_resets'::regclass AND contype = 'f'"
            )
        ).scalar_one()
        assert cascade == "c"  # ON DELETE CASCADE
        index = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE tablename = 'password_resets' "
                "AND indexname = 'ix_password_resets_expires_at'"
            )
        ).scalar_one()
        assert "(expires_at)" in index
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            allowed = conn.execute(
                text("SELECT has_table_privilege('api_rw', 'password_resets', :p)"),
                {"p": privilege},
            ).scalar_one()
            assert allowed, privilege


def test_a_second_code_row_for_the_same_user_is_refused_by_the_key(
    engine: Engine,
) -> None:
    command.upgrade(_config(), "head")
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
        uid = conn.execute(
            text(
                "INSERT INTO users (email, password_hash, role) "
                "VALUES ('a@example.com', 'x', 'viewer') RETURNING id"
            )
        ).scalar_one()
    insert = text(
        "INSERT INTO password_resets "
        "(user_id, code_hash, expires_at, created_at) "
        "VALUES (:u, :h, now(), now())"
    )
    with engine.begin() as conn:
        conn.execute(insert, {"u": uid, "h": "one"})
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(insert, {"u": uid, "h": "two"})


def test_attempts_default_to_zero(engine: Engine) -> None:
    command.upgrade(_config(), "head")
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
        uid = conn.execute(
            text(
                "INSERT INTO users (email, password_hash, role) "
                "VALUES ('b@example.com', 'x', 'viewer') RETURNING id"
            )
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO password_resets "
                "(user_id, code_hash, expires_at, created_at) "
                "VALUES (:u, 'h', now(), now())"
            ),
            {"u": uid},
        )
        attempts = conn.execute(
            text("SELECT attempts FROM password_resets")
        ).scalar_one()
    assert attempts == 0


def test_the_orm_model_matches_the_migration(engine: Engine) -> None:
    command.upgrade(_config(), "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), metadata)
    assert diff == [], f"schema drift between models and migrations: {diff}"


def test_head_is_0010(engine: Engine) -> None:
    command.upgrade(_config(), "head")
    with engine.connect() as conn:
        version = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert version == "0010"
