"""TC-20 (listener, AC-6): NOTIFY wakes the hub; reconnect wakes everyone."""

import asyncio
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.listener import NotifyListener, listen_dsn
from newsdock_api.domain.streams import WakeHub
from newsdock_db.engine import make_engine
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-push-test"


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
    url = (
        f"postgresql+psycopg://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{env.get('POSTGRES_PORT', '5433')}/{env['POSTGRES_DB']}"
    )
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", url)
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    engine = make_engine(url)
    yield engine, url
    engine.dispose()
    mp.undo()
    _compose("down", "-v", "--remove-orphans")


def _insert(engine: Engine, key: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO articles (url_hash, gkg_record_id, slot, url, title, "
                "domain, published_at, themes, persons, orgs) VALUES "
                "(:k,'x','20261014120000','https://e.com/'||:k,'t','e.com',now(),"
                "'{}','{}','{}') ON CONFLICT DO NOTHING"
            ),
            {"k": key},
        )


def test_listen_dsn_turns_a_sqlalchemy_url_into_a_psycopg_conninfo() -> None:
    dsn = listen_dsn("postgresql+psycopg://u:p%40ss@h:5433/db")
    parts = conninfo_to_dict(dsn)
    assert (parts["user"], parts["password"], parts["host"]) == ("u", "p@ss", "h")
    assert (parts["port"], parts["dbname"]) == ("5433", "db")


def test_a_notification_wakes_waiting_streams(db: tuple[Engine, str]) -> None:
    engine, url = db

    async def go() -> tuple[bool, bool]:
        hub = WakeHub()
        listener = NotifyListener(listen_dsn(url), hub, backoff=(0.05, 0.2))
        task = asyncio.create_task(listener.run())
        await listener.connected.wait()
        await asyncio.sleep(0.1)
        gen = hub.generation()
        waiters = [asyncio.create_task(hub.wait(gen, 5)) for _ in range(2)]
        await asyncio.sleep(0.05)
        await asyncio.to_thread(_insert, engine, "t20a")
        woke = all(await asyncio.gather(*waiters))
        # a no-op conflict sends nothing: a fresh wait times out
        await asyncio.to_thread(_insert, engine, "t20a")
        quiet = await hub.wait(hub.generation(), 0.5)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return woke, quiet

    woke, quiet = asyncio.run(go())
    assert woke is True
    assert quiet is False


def test_reconnect_after_a_lost_connection_wakes_everyone(
    db: tuple[Engine, str],
) -> None:
    engine, url = db

    async def go() -> tuple[int, int]:
        hub = WakeHub()
        listener = NotifyListener(listen_dsn(url), hub, backoff=(0.05, 0.2))
        task = asyncio.create_task(listener.run())
        await listener.connected.wait()
        await asyncio.sleep(0.1)
        before = hub.generation()  # includes the wake from the first connect
        with engine.begin() as conn:  # kill the listener's backend
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE query ILIKE 'LISTEN articles_new%' "
                    "AND pid <> pg_backend_pid()"
                )
            )
        listener.connected.clear()
        await asyncio.wait_for(listener.connected.wait(), 5)  # it came back
        after = hub.generation()
        # and it still works after the reconnect
        gen = hub.generation()
        waiter = asyncio.create_task(hub.wait(gen, 5))
        await asyncio.sleep(0.05)
        await asyncio.to_thread(_insert, engine, "t20b")
        assert await waiter is True
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return before, after

    before, after = asyncio.run(go())
    assert after > before  # the reconnect itself woke the streams


def test_cancelling_the_listener_is_clean(db: tuple[Engine, str]) -> None:
    _, url = db

    async def go() -> bool:
        listener = NotifyListener(listen_dsn(url), WakeHub(), backoff=(0.05, 0.2))
        task = asyncio.create_task(listener.run())
        await listener.connected.wait()
        task.cancel()
        results = await asyncio.gather(task, return_exceptions=True)
        return isinstance(results[0], asyncio.CancelledError)

    assert asyncio.run(go()) is True
