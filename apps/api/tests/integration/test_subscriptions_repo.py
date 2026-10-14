"""TC-19 (trigger), persistence half of TC-1, key_usable (Docker)."""

import subprocess
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.agents_repo import SqlAgentsRepo
from newsdock_api.adapters.subscriptions_repo import SqlSubscriptionsRepo
from newsdock_api.domain.agents import make_key
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-push-test"
NOW = datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC)
NO_SUCH_UUID = "00000000-0000-0000-0000-000000000000"


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


@pytest.fixture(scope="module")
def db() -> Iterator[tuple[Engine, str]]:
    assert _compose("up", "-d", "--wait", "postgres").returncode == 0
    env = {
        k.strip(): v.strip()
        for k, _, v in (
            line.partition("=")
            for line in (ROOT / ".env.example").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
    }
    port = env.get("POSTGRES_PORT", "5433")
    url = (
        f"postgresql+psycopg://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{port}/{env['POSTGRES_DB']}"
    )
    dsn = (
        f"host=127.0.0.1 port={port} user={env['POSTGRES_USER']} "
        f"password={env['POSTGRES_PASSWORD']} dbname={env['POSTGRES_DB']}"
    )
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", url)
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    engine = make_engine(url)
    yield engine, dsn
    engine.dispose()
    mp.undo()
    _compose("down", "-v", "--remove-orphans")


@pytest.fixture()
def repos(
    db: tuple[Engine, str],
) -> Iterator[tuple[SqlAgentsRepo, SqlSubscriptionsRepo]]:
    engine, _ = db
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE agents CASCADE"))
    yield SqlAgentsRepo(engine), SqlSubscriptionsRepo(engine)


def _agent(agents: SqlAgentsRepo, name: str) -> str:
    return agents.create_agent(name, make_key()).id


# ---- persistence (TC-1, persistence half) ------------------------------------
def test_create_list_get_delete_are_scoped_to_the_owner(
    repos: tuple[SqlAgentsRepo, SqlSubscriptionsRepo],
) -> None:
    agents, subs = repos
    alpha, beta = _agent(agents, "alpha"), _agent(agents, "beta")
    mine = subs.create(alpha, {"theme": "ECON_*", "domain": "example.com"})
    theirs = subs.create(beta, {})

    assert mine.filter == {"theme": "ECON_*", "domain": "example.com"}
    assert [s.id for s in subs.list_own(alpha)] == [mine.id]
    assert subs.get_own(alpha, mine.id) is not None
    assert subs.get_own(alpha, theirs.id) is None  # not alpha's: looks absent
    assert subs.count_own(alpha) == 1

    assert not subs.delete_own(alpha, theirs.id)
    assert subs.get_own(beta, theirs.id) is not None
    assert subs.delete_own(alpha, mine.id)
    assert subs.list_own(alpha) == []


def test_ids_that_are_not_uuids_look_absent_not_broken(
    repos: tuple[SqlAgentsRepo, SqlSubscriptionsRepo],
) -> None:
    agents, subs = repos
    alpha = _agent(agents, "alpha")
    assert subs.get_own(alpha, "not-a-uuid") is None
    assert not subs.delete_own(alpha, "not-a-uuid")
    assert not subs.exists("not-a-uuid")
    assert not subs.exists(NO_SUCH_UUID)
    assert not agents.set_status("not-a-uuid", "disabled")  # agent-platform guard
    assert not agents.key_usable("not-a-uuid")


def test_list_all_carries_agent_names_and_cascade_on_agent_delete(
    repos: tuple[SqlAgentsRepo, SqlSubscriptionsRepo], db: tuple[Engine, str]
) -> None:
    agents, subs = repos
    alpha, beta = _agent(agents, "alpha"), _agent(agents, "beta")
    subs.create(alpha, {"domain": "a.org"})
    subs.create(beta, {"text": "fed"})
    assert sorted((s.agent_name, s.filter) for s in subs.list_all()) == [
        ("alpha", {"domain": "a.org"}),
        ("beta", {"text": "fed"}),
    ]
    engine, _ = db
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM agents WHERE name = 'alpha'"))
    assert [s.agent_name for s in subs.list_all()] == ["beta"]


def test_exists_follows_delete(
    repos: tuple[SqlAgentsRepo, SqlSubscriptionsRepo],
) -> None:
    agents, subs = repos
    alpha = _agent(agents, "alpha")
    sub = subs.create(alpha, {})
    assert subs.exists(sub.id)
    subs.delete_own(alpha, sub.id)
    assert not subs.exists(sub.id)


# ---- key_usable (AC-11 support) ------------------------------------------------
def test_key_usable_follows_revocation_and_agent_status(
    repos: tuple[SqlAgentsRepo, SqlSubscriptionsRepo],
) -> None:
    agents, _ = repos
    agent = agents.create_agent("alpha", make_key())
    assert agents.key_usable(agent.key_id)
    agents.set_status(agent.id, "disabled")
    assert not agents.key_usable(agent.key_id)
    agents.set_status(agent.id, "active")
    assert agents.key_usable(agent.key_id)
    agents.revoke_key(agent.id, agent.key_id)
    assert not agents.key_usable(agent.key_id)
    assert not agents.key_usable(NO_SUCH_UUID)


# ---- TC-19: the articles trigger (ADR-0018) ------------------------------------
def _insert_sql(*hashes: str) -> str:
    values = ",".join(
        f"('{h}','x','20261014120000','https://e.com/{h}','t {h}',"
        f"'e.com',now(),'{{}}','{{}}','{{}}')"
        for h in hashes
    )
    return (
        "INSERT INTO articles (url_hash, gkg_record_id, slot, url, title, domain, "
        f"published_at, themes, persons, orgs) VALUES {values} ON CONFLICT DO NOTHING"
    )


def _notifications(dsn: str, action: str, wait: float = 1.0) -> list[str]:
    with psycopg.connect(dsn, autocommit=True) as listener:
        listener.execute("LISTEN articles_new")
        with psycopg.connect(dsn, autocommit=True) as writer:
            writer.execute(action)
        payloads = [n.payload for n in listener.notifies(timeout=wait, stop_after=10)]
    return payloads


def test_trigger_sends_one_notification_per_batch(db: tuple[Engine, str]) -> None:
    engine, dsn = db
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
    payloads = _notifications(dsn, _insert_sql("t19a", "t19b", "t19c"))
    assert len(payloads) == 1
    with engine.connect() as conn:
        top = conn.execute(text("SELECT max(seq) FROM articles")).scalar_one()
    assert payloads == [str(top)]


def test_trigger_is_silent_when_a_conflict_inserts_nothing(
    db: tuple[Engine, str],
) -> None:
    engine, dsn = db
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
        conn.execute(text(_insert_sql("t19d")))
    assert _notifications(dsn, _insert_sql("t19d")) == []


def test_trigger_notifies_only_after_commit(db: tuple[Engine, str]) -> None:
    _, dsn = db
    with psycopg.connect(dsn, autocommit=True) as listener:
        listener.execute("LISTEN articles_new")
        with psycopg.connect(dsn) as writer:  # one open transaction
            writer.execute(_insert_sql("t19e"))
            assert list(listener.notifies(timeout=0.5, stop_after=1)) == []
            writer.commit()
            time.sleep(0.2)
        assert len(list(listener.notifies(timeout=1.0, stop_after=1))) == 1


def test_sink_role_can_insert_through_the_trigger(db: tuple[Engine, str]) -> None:
    engine, dsn = db
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
    action = "SET ROLE sink_rw; " + _insert_sql("t19f", "t19g")
    assert len(_notifications(dsn, action)) == 1
