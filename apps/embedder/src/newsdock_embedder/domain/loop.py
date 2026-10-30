"""The worker pass and the loop around it (spec semantic-search D-3, AC-2..AC-5, AC-11).

Pure: the database and Ollama are ports, implemented in `adapters/`. A pass takes
one batch of canonical articles that have no vector yet (newest first), embeds their
titles in one request and stores each vector. Vectors written by another model are
cleared once, at the start, so they join that same queue; the queue is a partial
index, so finding work costs the same however many rows are already embedded.
Nothing here can fail an ingest: the worker only reads committed rows.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from newsdock_embedder.domain.selection import Backoff, SkipList

logger = logging.getLogger(__name__)

Outcome = Literal["idle", "embedded", "unavailable", "db_unavailable"]


class EmbedderUnavailable(Exception):
    """Ollama gave no usable answer for the whole batch."""


class DbUnavailable(Exception):
    """The database could not be reached."""


@dataclass(frozen=True)
class Row:
    url_hash: str
    title: str


@dataclass(frozen=True)
class PassResult:
    outcome: Outcome
    embedded: int = 0
    skipped: int = 0


class EmbedRepo(Protocol):
    def invalidate_stale(self, model: str) -> int:
        """Clear vectors written by a model other than `model`; return how many."""
        ...

    def next_batch(self, limit: int, exclude: frozenset[str]) -> list[Row]:
        """Canonical rows with no vector yet, newest first."""
        ...

    def store(self, url_hash: str, vector: list[float], model: str) -> bool:
        """Write the vector if the row still needs it; False when it no longer does."""
        ...


class DocumentEmbedder(Protocol):
    def embed_documents(self, titles: list[str]) -> list[list[float] | None]:
        """One vector per title, None for a vector that must not be stored."""
        ...


class EmbedWorker:
    def __init__(
        self,
        repo: EmbedRepo,
        embedder: DocumentEmbedder,
        *,
        model: str,
        batch_size: int,
        skip: SkipList,
    ) -> None:
        self._repo = repo
        self._embedder = embedder
        self._model = model
        self._batch_size = batch_size
        self._skip = skip
        self._prepared = False

    def run_pass(self) -> PassResult:
        try:
            if not self._prepared:  # once; retried while the database is down
                cleared = self._repo.invalidate_stale(self._model)
                self._prepared = True
                if cleared:
                    logger.info(
                        "cleared %d vectors of another model; re-embedding them",
                        cleared,
                    )
            rows = self._repo.next_batch(self._batch_size, self._skip.excluded())
            if not rows:
                return PassResult("idle")  # nothing to embed: no request to Ollama
            vectors = self._embedder.embed_documents([r.title for r in rows])
            embedded = skipped = 0
            for row, vector in zip(rows, vectors, strict=True):
                if vector is None:
                    self._skip.fail(row.url_hash)
                    skipped += 1
                    logger.warning("vector rejected for %s", row.url_hash)
                elif self._repo.store(row.url_hash, vector, self._model):
                    self._skip.forget(row.url_hash)
                    embedded += 1
        except EmbedderUnavailable as exc:
            logger.warning("ollama unavailable, rows left untouched: %s", exc)
            return PassResult("unavailable")
        except DbUnavailable as exc:
            logger.warning("database unavailable: %s", exc)
            return PassResult("db_unavailable")
        logger.info("embedded %d rows (%d skipped)", embedded, skipped)
        return PassResult("embedded", embedded=embedded, skipped=skipped)


class Passes(Protocol):
    def run_pass(self) -> PassResult: ...


def run(
    worker: Passes,
    *,
    poll_interval: float,
    backoff: Backoff,
    sleep: Callable[[float], None],
    beat: Callable[[], None],
    should_stop: Callable[[], bool],
) -> None:
    """Run passes until `should_stop`: beat after each one, back off while down.

    The heartbeat is written whether or not Ollama or the database answered: the
    worker is alive, and restarting it would not fix a dependency outage.
    """
    while True:
        result = worker.run_pass()
        beat()
        if result.outcome in ("unavailable", "db_unavailable"):
            sleep(backoff.next())
        else:
            backoff.reset()
            if result.outcome == "idle":
                sleep(poll_interval)
        if should_stop():
            return
