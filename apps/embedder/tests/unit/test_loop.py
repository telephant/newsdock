"""TC-3 (AC-3), TC-19 (AC-4) and the worker pass rules (AC-2, AC-4, AC-11)."""

from collections.abc import Callable

from newsdock_embedder.domain.loop import (
    DbUnavailable,
    EmbedderUnavailable,
    EmbedWorker,
    Outcome,
    PassResult,
    Row,
    run,
)
from newsdock_embedder.domain.selection import Backoff, SkipList

MODEL = "m1"


class FakeRepo:
    """Rows that still need an embedding; `store` removes them."""

    def __init__(self, titles: dict[str, str]) -> None:
        self.pending = dict(titles)  # url_hash -> title, newest first
        self.stored: dict[str, tuple[list[float], str]] = {}
        self.exclude_seen: list[frozenset[str]] = []
        self.fail_db = False
        self.refuse_store: set[str] = set()
        self.events: list[str] = []  # order of invalidate / next_batch calls
        self.invalidated: list[str] = []
        self.cleared = 0
        self.fail_invalidate = False

    def invalidate_stale(self, model: str) -> int:
        self.events.append("invalidate")
        if self.fail_invalidate:
            raise DbUnavailable("db down")
        self.invalidated.append(model)
        return self.cleared

    def next_batch(self, limit: int, exclude: frozenset[str]) -> list[Row]:
        self.events.append("next_batch")
        if self.fail_db:
            raise DbUnavailable("db down")
        self.exclude_seen.append(exclude)
        rows = [Row(k, t) for k, t in self.pending.items() if k not in exclude]
        return rows[:limit]

    def store(self, url_hash: str, vector: list[float], model: str) -> bool:
        if url_hash in self.refuse_store:
            return False
        self.stored[url_hash] = (vector, model)
        self.pending.pop(url_hash, None)
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


def worker(
    repo: FakeRepo, embedder: FakeEmbedder, batch: int = 2, max_failures: int = 3
) -> EmbedWorker:
    return EmbedWorker(
        repo,
        embedder,
        model=MODEL,
        batch_size=batch,
        skip=SkipList(max_failures=max_failures, max_entries=100),
    )


# TC-3: nothing to embed means no request to Ollama
def test_an_idle_pass_sends_no_request() -> None:
    repo, embedder = FakeRepo({}), FakeEmbedder()
    result = worker(repo, embedder).run_pass()
    assert result == PassResult("idle")
    assert embedder.calls == []
    assert repo.stored == {}


def test_a_pass_embeds_one_batch_and_stores_each_vector_with_the_model() -> None:
    repo = FakeRepo({"h1": "one", "h2": "three", "h3": "fifteen chars!!"})
    embedder = FakeEmbedder()
    result = worker(repo, embedder, batch=2).run_pass()
    assert result == PassResult("embedded", embedded=2)
    assert embedder.calls == [["one", "three"]]
    assert repo.stored == {"h1": ([3.0], MODEL), "h2": ([5.0], MODEL)}
    assert "h3" in repo.pending  # the next pass takes it


def test_repeated_passes_end_idle_and_a_further_pass_sends_nothing() -> None:
    repo = FakeRepo({f"h{i}": f"t{i}" for i in range(5)})
    embedder = FakeEmbedder()
    w = worker(repo, embedder, batch=2)
    outcomes = [w.run_pass().outcome for _ in range(4)]
    assert outcomes == ["embedded", "embedded", "embedded", "idle"]
    calls_before = len(embedder.calls)
    assert w.run_pass().outcome == "idle"
    assert len(embedder.calls) == calls_before  # TC-3: second pass, no request


# AC-4: Ollama down leaves every row untouched
def test_an_unavailable_embedder_leaves_rows_untouched() -> None:
    repo = FakeRepo({"h1": "one"})
    embedder = FakeEmbedder()
    embedder.unavailable = True
    result = worker(repo, embedder).run_pass()
    assert result == PassResult("unavailable")
    assert repo.stored == {} and repo.pending == {"h1": "one"}


def test_a_db_error_is_reported_not_raised() -> None:
    repo = FakeRepo({"h1": "one"})
    repo.fail_db = True
    assert worker(repo, FakeEmbedder()).run_pass() == PassResult("db_unavailable")


def test_a_rejected_vector_is_skipped_and_counted() -> None:
    repo = FakeRepo({"h1": "good", "h2": "bad"})
    embedder = FakeEmbedder()
    embedder.bad = {"bad"}
    result = worker(repo, embedder).run_pass()
    assert result == PassResult("embedded", embedded=1, skipped=1)
    assert set(repo.stored) == {"h1"}


def test_a_title_rejected_three_times_stops_blocking_the_queue() -> None:
    repo = FakeRepo({"h1": "bad", "h2": "next"})
    embedder = FakeEmbedder()
    embedder.bad = {"bad"}
    w = worker(repo, embedder, batch=1, max_failures=3)
    for _ in range(3):
        assert w.run_pass().skipped == 1  # h1 fails each time, head of the queue
    result = w.run_pass()  # now h1 is excluded, h2 gets its turn
    assert result == PassResult("embedded", embedded=1)
    assert "h2" in repo.stored and "h1" not in repo.stored
    assert frozenset({"h1"}) in repo.exclude_seen


def test_a_guarded_store_that_matches_no_row_is_not_counted() -> None:
    repo = FakeRepo({"h1": "one", "h2": "two"})
    repo.refuse_store = {"h1"}  # changed by someone else meanwhile
    result = worker(repo, FakeEmbedder()).run_pass()
    assert result == PassResult("embedded", embedded=1)


# F-1 (found at verify): vectors of another model are cleared once, at the start,
# so the "no vector yet" queue (a partial index) finds them without scanning
def test_other_model_vectors_are_cleared_once_before_the_first_batch() -> None:
    repo, embedder = FakeRepo({"h1": "one"}), FakeEmbedder()
    repo.cleared = 5
    w = worker(repo, embedder)
    w.run_pass()
    w.run_pass()
    assert repo.invalidated == [MODEL]  # once, with the configured model
    assert repo.events[:2] == ["invalidate", "next_batch"]
    assert repo.events.count("invalidate") == 1


def test_the_clearing_is_retried_while_the_database_is_down() -> None:
    repo, embedder = FakeRepo({"h1": "one"}), FakeEmbedder()
    repo.fail_invalidate = True
    w = worker(repo, embedder)
    assert w.run_pass() == PassResult("db_unavailable")
    assert "next_batch" not in repo.events  # no work before the clearing succeeded
    repo.fail_invalidate = False
    assert w.run_pass() == PassResult("embedded", embedded=1)
    assert repo.invalidated == [MODEL]


# TC-19: the loop keeps its heartbeat while Ollama is down and backs off to a cap
class ScriptedWorker:
    def __init__(self, outcomes: list[Outcome]) -> None:
        self._outcomes = outcomes
        self.passes = 0

    def run_pass(self) -> PassResult:
        outcome = self._outcomes[self.passes]
        self.passes += 1
        return PassResult(outcome)


def drive(outcomes: list[Outcome]) -> tuple[list[float], int]:
    scripted = ScriptedWorker(outcomes)
    sleeps: list[float] = []
    beats = 0

    def beat() -> None:
        nonlocal beats
        beats += 1

    stop: Callable[[], bool] = lambda: scripted.passes >= len(outcomes)  # noqa: E731
    run(
        scripted,
        poll_interval=10.0,
        backoff=Backoff(base=5.0, cap=60.0),
        sleep=sleeps.append,
        beat=beat,
        should_stop=stop,
    )
    return sleeps, beats


def test_heartbeat_every_pass_and_backoff_grows_to_its_cap_while_down() -> None:
    sleeps, beats = drive(["unavailable"] * 6)
    assert beats == 6
    assert sleeps == [5.0, 10.0, 20.0, 40.0, 60.0, 60.0]


def test_idle_sleeps_the_poll_interval_and_embedded_does_not_sleep() -> None:
    sleeps, beats = drive(["embedded", "embedded", "idle"])
    assert sleeps == [10.0]
    assert beats == 3


def test_recovery_resets_the_backoff() -> None:
    sleeps, _ = drive(["unavailable", "unavailable", "embedded", "unavailable"])
    assert sleeps == [5.0, 10.0, 5.0]


def test_a_db_outage_backs_off_like_an_ollama_outage() -> None:
    sleeps, _ = drive(["db_unavailable", "db_unavailable"])
    assert sleeps == [5.0, 10.0]
