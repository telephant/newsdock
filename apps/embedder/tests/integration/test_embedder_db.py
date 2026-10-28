"""TC-2, TC-4, TC-5, TC-12 (worker half): the embedder against real Postgres (Docker).

Ollama is the deterministic `FakeOllama` behind an `httpx.MockTransport`; the
database is a real pgvector Postgres on a side port.
"""

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from newsdock_db.engine import make_engine
from newsdock_embedder.adapters.db import SqlEmbedRepo
from newsdock_embedder.adapters.ollama import OllamaDocumentEmbedder
from newsdock_embedder.domain.loop import EmbedWorker
from newsdock_embedder.domain.selection import SkipList
from newsdock_embedding.testing import FakeOllama
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
MODEL = "nomic-embed-text"
PREFIX = "search_document: "


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def clean(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))


def insert(engine: Engine, count: int, *, start: int = 0) -> list[str]:
    """Insert `count` canonical articles in order (rising seq); returns their titles."""
    titles = []
    with engine.begin() as conn:
        for i in range(start, start + count):
            title = f"Headline number {i}"
            titles.append(title)
            conn.execute(
                text(
                    "INSERT INTO articles (url_hash, gkg_record_id, slot, url, title, "
                    "published_at) VALUES (:k, 'r', '20261028120000', :u, :t, now())"
                ),
                {"k": f"h{i:04d}", "u": f"https://e.com/{i}", "t": title},
            )
    return titles


def make_worker(
    engine: Engine,
    fake: FakeOllama,
    *,
    batch: int = 32,
    model: str = MODEL,
    dimension: int = 768,
) -> EmbedWorker:
    client = httpx.Client(transport=fake.transport())
    embedder = OllamaDocumentEmbedder(
        url="http://ollama.test:11434",
        model=model,
        dimension=dimension,
        prefix=PREFIX,
        timeout=5.0,
        client=client,
    )
    return EmbedWorker(
        SqlEmbedRepo(engine),
        embedder,
        model=model,
        batch_size=batch,
        skip=SkipList(max_failures=3, max_entries=100),
    )


def state(engine: Engine) -> list[tuple[str, int | None, str | None]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT url_hash, vector_dims(embedding), embedding_model "
                "FROM articles ORDER BY url_hash"
            )
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]


# TC-2 (AC-2)
def test_a_pass_embeds_a_new_article_with_the_model_name(engine: Engine) -> None:
    insert(engine, 1)
    fake = FakeOllama()
    result = make_worker(engine, fake).run_pass()
    assert (result.outcome, result.embedded) == ("embedded", 1)
    assert state(engine) == [("h0000", 768, MODEL)]
    sent = json.loads(fake.requests[0].content)
    assert sent == {"model": MODEL, "input": [PREFIX + "Headline number 0"]}


# TC-4 (AC-4): Ollama down, inserts still succeed, rows stay empty, recovery fills them
def test_ollama_down_leaves_rows_empty_and_recovery_embeds_them(
    engine: Engine,
) -> None:
    fake = FakeOllama(mode="refuse")
    worker = make_worker(engine, fake)
    insert(engine, 3)  # the sink's side of the world is unaffected
    assert worker.run_pass().outcome == "unavailable"
    assert state(engine) == [(f"h000{i}", None, None) for i in range(3)]

    fake.mode = "ok"
    assert worker.run_pass().outcome == "embedded"
    assert state(engine) == [(f"h000{i}", 768, MODEL) for i in range(3)]


# TC-5 (AC-5): backfill until idle, newest first
def test_backfill_embeds_everything_newest_first(engine: Engine) -> None:
    titles = insert(engine, 120)
    fake = FakeOllama()
    worker = make_worker(engine, fake, batch=32)
    outcomes = []
    while True:
        outcome = worker.run_pass().outcome
        outcomes.append(outcome)
        if outcome == "idle":
            break
    assert outcomes == ["embedded"] * 4 + ["idle"]
    assert all(dims == 768 and model == MODEL for _, dims, model in state(engine))
    first_batch = json.loads(fake.requests[0].content)["input"]
    assert first_batch == [PREFIX + t for t in reversed(titles[-32:])]  # newest first


# TC-12, worker half (AC-11): a changed model re-embeds rows from the old one
def test_rows_from_another_model_are_re_embedded(engine: Engine) -> None:
    insert(engine, 5)
    make_worker(engine, FakeOllama(), model="old-model").run_pass()
    assert {m for _, _, m in state(engine)} == {"old-model"}

    fake = FakeOllama()
    worker = make_worker(engine, fake, model="new-model")
    assert worker.run_pass().embedded == 5
    assert {m for _, _, m in state(engine)} == {"new-model"}
    assert worker.run_pass().outcome == "idle"  # and then it is done


# a wrong-length vector is never stored and never crashes the worker
def test_wrong_length_vectors_are_not_stored(engine: Engine) -> None:
    insert(engine, 2)
    result = make_worker(engine, FakeOllama(dimension=10)).run_pass()
    assert (result.embedded, result.skipped) == (0, 2)
    assert state(engine) == [("h0000", None, None), ("h0001", None, None)]
