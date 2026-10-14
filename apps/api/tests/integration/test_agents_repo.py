"""TC-2 (AC-2) + repo behaviour behind AC-5/AC-8: registry persistence (Docker)."""

import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.agents_repo import DuplicateAgentError, SqlAgentsRepo
from newsdock_api.domain.agents import make_key
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-agents-test"
NOW = datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC)


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert _compose("up", "-d", "--wait", "postgres").returncode == 0
    env = {
        k.strip(): v.strip()
        for k, _, v in (
            line.partition("=")
            for line in (ROOT / ".env.example").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
    }
    url = (
        f"postgresql+psycopg://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{env.get('POSTGRES_PORT', '5433')}/{env['POSTGRES_DB']}"
    )
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", url)
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(url)
    yield eng
    eng.dispose()
    mp.undo()
    _compose("down", "-v", "--remove-orphans")


@pytest.fixture()
def repo(engine: Engine) -> Iterator[SqlAgentsRepo]:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE agents CASCADE"))
    yield SqlAgentsRepo(engine)


# TC-2: only prefix + hash of the secret are stored, never the plaintext key
def test_key_is_stored_hashed(repo: SqlAgentsRepo, engine: Engine) -> None:
    key = make_key()
    repo.create_agent("alpha", key)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM api_keys")).mappings().one()
        dump = " ".join(str(v) for v in row.values())
    assert row["prefix"] == key.prefix
    assert row["key_hash"] == key.key_hash
    assert key.secret not in dump and key.raw not in dump


def test_duplicate_name_is_rejected(repo: SqlAgentsRepo) -> None:
    repo.create_agent("alpha", make_key())
    with pytest.raises(DuplicateAgentError):
        repo.create_agent("alpha", make_key())


def test_find_key_returns_agent_state(repo: SqlAgentsRepo) -> None:
    key = make_key()
    agent = repo.create_agent("alpha", key)
    found = repo.find_key(key.prefix)
    assert found is not None
    assert (found.agent_id, found.agent_name) == (agent.id, "alpha")
    assert found.key_hash == key.key_hash and found.usable
    assert repo.find_key("nosuchprefix") is None


def test_revoke_and_disable_make_the_key_unusable(repo: SqlAgentsRepo) -> None:
    key = make_key()
    agent = repo.create_agent("alpha", key)
    found = repo.find_key(key.prefix)
    assert found is not None

    assert repo.set_status(agent.id, "disabled")
    after_disable = repo.find_key(key.prefix)
    assert after_disable is not None and not after_disable.usable
    assert repo.set_status(agent.id, "active")
    reenabled = repo.find_key(key.prefix)
    assert reenabled is not None and reenabled.usable

    assert repo.revoke_key(agent.id, found.key_id)
    revoked = repo.find_key(key.prefix)
    assert revoked is not None and not revoked.usable
    assert not repo.set_status("00000000-0000-0000-0000-000000000000", "disabled")


def test_second_key_and_listing_never_expose_secrets(repo: SqlAgentsRepo) -> None:
    first, second = make_key(), make_key()
    agent = repo.create_agent("alpha", first)
    repo.add_key(agent.id, second)
    (listed,) = repo.list_agents()
    assert listed.name == "alpha" and listed.status == "active"
    assert {k.prefix for k in listed.keys} == {first.prefix, second.prefix}
    assert first.secret not in repr(listed) and first.key_hash not in repr(listed)


def test_touch_key_is_throttled(repo: SqlAgentsRepo, engine: Engine) -> None:
    key = make_key()
    repo.create_agent("alpha", key)
    found = repo.find_key(key.prefix)
    assert found is not None
    repo.touch_key(found.key_id, NOW)
    repo.touch_key(found.key_id, NOW + timedelta(seconds=10))  # within a minute: no-op
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT last_used_at FROM api_keys")).scalar_one() == NOW
        )
    repo.touch_key(found.key_id, NOW + timedelta(minutes=2))
    with engine.connect() as conn:
        used = conn.execute(text("SELECT last_used_at FROM api_keys")).scalar_one()
    assert used == NOW + timedelta(minutes=2)


# AC-8 groundwork (T-06 wires it): forward-only, idempotent cursor storage
def test_cursor_only_moves_forward(repo: SqlAgentsRepo) -> None:
    agent = repo.create_agent("alpha", make_key())
    assert repo.get_cursor(agent.id) is None
    assert repo.advance_cursor(agent.id, 10) == 10
    assert repo.advance_cursor(agent.id, 4) == 10  # older ack is a no-op
    assert repo.advance_cursor(agent.id, 10) == 10  # idempotent
    assert repo.advance_cursor(agent.id, 25) == 25
    assert repo.get_cursor(agent.id) == 25


def test_api_role_can_use_the_tables(engine: Engine) -> None:
    with engine.connect() as conn:
        for table in ("agents", "api_keys", "agent_cursors"):
            for priv in ("SELECT", "INSERT", "UPDATE"):
                assert conn.execute(
                    text("SELECT has_table_privilege('api_rw', :t, :p)"),
                    {"t": table, "p": priv},
                ).scalar_one()
