"""TC-1 (AC-1) and TC-2 (AC-8): migration 0007 and the owner FK (Docker)."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from newsdock_api.adapters.agents_repo import SqlAgentsRepo
from newsdock_api.domain.agents import make_key
from newsdock_db.engine import make_engine
from newsdock_db.metadata import metadata
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]


def _config() -> Config:
    return Config(str(ROOT / "infra" / "migrations" / "alembic.ini"))


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


def _insert_agent(engine: Engine, name: str, owner_id: str | None = None) -> str:
    key = make_key()
    with engine.begin() as conn:
        agent_id = str(
            conn.execute(
                text("INSERT INTO agents (name) VALUES (:n) RETURNING id"), {"n": name}
            ).scalar_one()
        )
        if owner_id is not None:
            conn.execute(
                text("UPDATE agents SET owner_id = :o WHERE id = :a"),
                {"o": owner_id, "a": agent_id},
            )
        conn.execute(
            text(
                "INSERT INTO api_keys (agent_id, prefix, key_hash) VALUES (:a, :p, :h)"
            ),
            {"a": agent_id, "p": key.prefix, "h": key.key_hash},
        )
    return key.prefix


# TC-1: legacy agents and their keys survive the additive migration (AC-1)
def test_migration_keeps_legacy_agents_and_keys(engine: Engine) -> None:
    command.upgrade(_config(), "0006")
    prefixes = [
        _insert_agent(engine, "demo-financial"),
        _insert_agent(engine, "push-live"),
    ]

    command.upgrade(_config(), "0007")

    with engine.connect() as conn:
        owners = conn.execute(
            text("SELECT name, owner_id FROM agents ORDER BY name")
        ).all()
    assert owners == [("demo-financial", None), ("push-live", None)]
    repo = SqlAgentsRepo(engine)
    for prefix in prefixes:
        found = repo.find_key(prefix)
        assert found is not None and found.usable

    command.upgrade(_config(), "head")  # idempotent


# TC-2: deleting the owner orphans the agent; nothing else is lost (AC-8)
def test_deleting_the_owner_orphans_the_agent(engine: Engine) -> None:
    command.upgrade(_config(), "head")
    with engine.begin() as conn:
        user_id = str(
            conn.execute(
                text(
                    "INSERT INTO users (email, password_hash, role) "
                    "VALUES ('a@x.io', 'x', 'viewer') RETURNING id"
                )
            ).scalar_one()
        )
    prefix = _insert_agent(engine, "owned-agent", owner_id=user_id)
    with engine.begin() as conn:
        agent_id = conn.execute(
            text("SELECT id FROM agents WHERE name = 'owned-agent'")
        ).scalar_one()
        conn.execute(
            text("INSERT INTO agent_cursors (agent_id, seq) VALUES (:a, 5)"),
            {"a": agent_id},
        )
        conn.execute(
            text("INSERT INTO subscriptions (agent_id, filter) VALUES (:a, :f)"),
            {"a": agent_id, "f": json.dumps({"q": "x"})},
        )

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})

    with engine.connect() as conn:
        owner = conn.execute(
            text("SELECT owner_id FROM agents WHERE id = :a"), {"a": agent_id}
        ).scalar_one()
        counts = [
            conn.execute(
                text(f"SELECT count(*) FROM {t} WHERE agent_id = :a"), {"a": agent_id}
            ).scalar_one()
            for t in ("api_keys", "agent_cursors", "subscriptions")
        ]
    assert owner is None
    assert counts == [1, 1, 1]
    found = SqlAgentsRepo(engine).find_key(prefix)
    assert found is not None and found.usable


# the hand-written migration and the ORM model do not drift (TC-34 for 0007)
def test_model_matches_migration(engine: Engine) -> None:
    command.upgrade(_config(), "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), metadata)
    assert diff == [], f"schema drift between models and migrations: {diff}"
