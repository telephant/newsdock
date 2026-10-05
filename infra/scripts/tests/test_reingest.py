"""TC-6: re-ingesting a slot via process_slot(force=True) keeps the count (Docker).

Lives in infra/scripts/tests because it crosses apps (ingester → processor →
sink), which app-local tests must not do (DR-7).
"""

import io
import subprocess
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_core.contracts import RawMessage
from newsdock_db.engine import make_engine
from newsdock_db.models import Article
from newsdock_ingester.domain.cycle import Ingester
from newsdock_ingester.domain.ports import SlotState
from newsdock_processor.domain.route import CLEAN_TOPIC, route
from newsdock_sink.adapters.db import SqlArticleWriter
from newsdock_sink.domain.writer import SinkItem, process_batch
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "packages" / "core" / "tests" / "fixtures"
PROJECT = "newsdock-reingest-test"
SLOT = "20261004081500"
BASE = "http://x"


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


@pytest.fixture(scope="module")
def clean_db() -> Iterator[str]:
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
    mp.undo()
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
    engine.dispose()
    yield url
    _compose("down", "-v", "--remove-orphans")


class NullDlq:
    def send(self, key: str, message: object) -> None:
        raise AssertionError(f"unexpected dlq message for {key}")


def _count(url: str) -> int:
    engine = make_engine(url)
    with Session(engine) as session:
        n = session.scalar(select(func.count()).select_from(Article))
    engine.dispose()
    return int(n or 0)


# TC-6: re-ingest via process_slot(force=True) leaves the count unchanged
def test_reingest_is_idempotent_end_to_end(clean_db: str) -> None:
    lines = (FIXTURES / "gkg_sample.tsv").read_text().splitlines()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{SLOT}.gkg.csv", "\n".join(lines))
    zip_bytes = buf.getvalue()

    published: list[RawMessage] = []

    class Source:
        def fetch_index(self) -> str | None:
            return None

        def fetch_gkg(self, url: str) -> bytes | None:
            return zip_bytes

    class Collect:
        def publish(self, key: str, message: RawMessage) -> None:
            published.append(message)

        def flush(self) -> None:
            pass

    class MemRepo:
        def __init__(self) -> None:
            self.states: dict[str, SlotState] = {}

        def get(self, slot: str) -> SlotState | None:
            return self.states.get(slot)

        def pending(self, max_attempts: int) -> list[SlotState]:
            return []

        def save(self, state: SlotState) -> None:
            self.states[state.slot] = state

    engine = make_engine(clean_db)
    writer = SqlArticleWriter(engine)

    def run_pipeline() -> None:
        published.clear()
        ingester = Ingester(Source(), Collect(), MemRepo(), base_url=BASE)
        assert ingester.process_slot(SLOT, force=True)
        routed = [route(m) for m in published]
        batch = [
            SinkItem(key=r.key, value=r.value.encode())
            for r in routed
            if r.topic == CLEAN_TOPIC
        ]
        process_batch(batch, writer, NullDlq())

    run_pipeline()
    first = _count(clean_db)
    assert first == 20
    run_pipeline()  # re-ingest the same slot
    assert _count(clean_db) == first
    engine.dispose()
