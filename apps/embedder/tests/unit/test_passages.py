"""TC-19 (AC-11), unit half: the passage pass and the round of titles then passages."""

from newsdock_embedder.domain.loop import (
    DbUnavailable,
    EmbedderUnavailable,
    PassageRow,
    PassageWorker,
    PassResult,
    Round,
)
from newsdock_embedder.domain.selection import SkipList

MODEL = "m1"


class FakePassageRepo:
    def __init__(self, passages: dict[tuple[str, int], str]) -> None:
        self.pending = dict(passages)
        self.stored: dict[tuple[str, int], tuple[list[float], str]] = {}
        self.exclude_seen: list[frozenset[str]] = []
        self.invalidated: list[str] = []
        self.cleared = 0
        self.fail_db = False

    def invalidate_stale(self, model: str) -> int:
        self.invalidated.append(model)
        return self.cleared

    def next_batch(self, limit: int, exclude: frozenset[str]) -> list[PassageRow]:
        if self.fail_db:
            raise DbUnavailable("db down")
        self.exclude_seen.append(exclude)
        rows = [
            PassageRow(k, i, t)
            for (k, i), t in self.pending.items()
            if f"{k}:{i}" not in exclude
        ]
        return rows[:limit]

    def store(self, url_hash: str, idx: int, vector: list[float], model: str) -> bool:
        self.stored[(url_hash, idx)] = (vector, model)
        self.pending.pop((url_hash, idx), None)
        return True


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.unavailable = False
        self.bad: set[str] = set()

    def embed_documents(self, titles: list[str]) -> list[list[float] | None]:
        self.calls.append(list(titles))
        if self.unavailable:
            raise EmbedderUnavailable("ollama down")
        return [None if t in self.bad else [float(len(t))] for t in titles]


def make(
    repo: FakePassageRepo, embedder: FakeEmbedder, batch: int = 2
) -> PassageWorker:
    return PassageWorker(
        repo,
        embedder,
        model=MODEL,
        batch_size=batch,
        skip=SkipList(max_failures=2, max_entries=100),
    )


def test_every_pending_passage_gets_a_vector_and_then_the_pass_is_idle() -> None:
    repo = FakePassageRepo({("a", 0): "x", ("a", 1): "yy", ("b", 0): "zzz"})
    worker = make(repo, FakeEmbedder())
    assert worker.run_pass() == PassResult("embedded", embedded=2)
    assert worker.run_pass() == PassResult("embedded", embedded=1)
    assert worker.run_pass() == PassResult("idle")
    assert set(repo.stored) == {("a", 0), ("a", 1), ("b", 0)}
    assert all(model == MODEL for _, model in repo.stored.values())


def test_stale_vectors_are_cleared_once_at_start() -> None:
    repo = FakePassageRepo({})
    repo.cleared = 3
    worker = make(repo, FakeEmbedder())
    worker.run_pass()
    worker.run_pass()
    assert repo.invalidated == [MODEL]


def test_a_rejected_vector_is_skip_listed_after_repeated_failures() -> None:
    repo = FakePassageRepo({("a", 0): "bad", ("a", 1): "ok"})
    embedder = FakeEmbedder()
    embedder.bad = {"bad"}
    worker = make(repo, embedder, batch=5)
    first = worker.run_pass()
    assert (first.embedded, first.skipped) == (1, 1)
    worker.run_pass()  # second failure reaches the limit of 2
    assert repo.exclude_seen[-1] == frozenset()
    worker.run_pass()
    assert repo.exclude_seen[-1] == frozenset({"a:0"})


def test_ollama_outage_leaves_passages_untouched() -> None:
    repo = FakePassageRepo({("a", 0): "x"})
    embedder = FakeEmbedder()
    embedder.unavailable = True
    assert make(repo, embedder).run_pass().outcome == "unavailable"
    assert repo.pending == {("a", 0): "x"}


def test_database_outage_is_reported() -> None:
    repo = FakePassageRepo({})
    repo.fail_db = True
    assert make(repo, FakeEmbedder()).run_pass().outcome == "db_unavailable"


class Scripted:
    def __init__(self, *results: PassResult) -> None:
        self.results = list(results)
        self.calls = 0

    def run_pass(self) -> PassResult:
        self.calls += 1
        return self.results.pop(0)


def test_a_round_runs_titles_first_and_always_gives_passages_a_turn() -> None:
    titles = Scripted(PassResult("embedded", embedded=32))
    passages = Scripted(PassResult("embedded", embedded=5, skipped=1))
    result = Round(titles, passages).run_pass()
    assert result == PassResult("embedded", embedded=37, skipped=1)
    assert (titles.calls, passages.calls) == (1, 1)


def test_a_round_is_idle_only_when_both_are_idle() -> None:
    idle = PassResult("idle")
    assert Round(Scripted(idle), Scripted(idle)).run_pass() == idle
    only_passages = Round(Scripted(idle), Scripted(PassResult("embedded", embedded=2)))
    assert only_passages.run_pass().outcome == "embedded"


def test_an_outage_in_the_title_pass_skips_the_passage_pass() -> None:
    passages = Scripted()
    result = Round(Scripted(PassResult("unavailable")), passages).run_pass()
    assert result.outcome == "unavailable"
    assert passages.calls == 0


def test_an_outage_in_the_passage_pass_is_reported() -> None:
    result = Round(
        Scripted(PassResult("idle")), Scripted(PassResult("db_unavailable"))
    ).run_pass()
    assert result.outcome == "db_unavailable"
