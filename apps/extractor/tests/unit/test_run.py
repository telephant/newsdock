"""The run loop: a heartbeat every pass, sleep only when idle, back off on outages."""

import asyncio

import pytest
from newsdock_extractor.domain.loop import DbUnavailable, PassResult, run


class ScriptedWorker:
    """`run_pass` answers from a script: a PassResult, or an exception to raise."""

    def __init__(self, script: list[PassResult | BaseException]) -> None:
        self.script = list(script)
        self.passes = 0

    async def run_pass(self) -> PassResult:
        self.passes += 1
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


class Recorder:
    def __init__(self, stop_after: int) -> None:
        self.sleeps: list[float] = []
        self.beats = 0
        self.stop_after = stop_after
        self.checks = 0

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def beat(self) -> None:
        self.beats += 1

    def should_stop(self) -> bool:
        self.checks += 1
        return self.checks > self.stop_after


def go(worker: ScriptedWorker, rec: Recorder) -> None:
    asyncio.run(
        run(
            worker,
            poll_interval=5.0,
            backoff_base=2.0,
            backoff_cap=10.0,
            sleep=rec.sleep,
            beat=rec.beat,
            should_stop=rec.should_stop,
        )
    )


def test_a_busy_pass_runs_again_at_once_and_an_idle_one_waits_the_poll_interval() -> (
    None
):
    worker = ScriptedWorker([PassResult(3), PassResult(0), PassResult(1)])
    rec = Recorder(stop_after=3)
    go(worker, rec)
    assert worker.passes == 3
    assert rec.sleeps == [5.0]  # only after the idle pass


def test_the_heartbeat_is_written_after_every_pass_even_a_failed_one() -> None:
    worker = ScriptedWorker([PassResult(1), DbUnavailable("down"), PassResult(0)])
    rec = Recorder(stop_after=3)
    go(worker, rec)
    assert rec.beats == 3


def test_a_database_outage_backs_off_growing_to_the_cap_and_then_recovers() -> None:
    down = DbUnavailable("down")
    worker = ScriptedWorker(
        [down, down, down, down, PassResult(1), down, PassResult(1)]
    )
    rec = Recorder(stop_after=7)
    go(worker, rec)
    # 2, 4, 8, then the cap 10; a good pass resets the backoff to 2 again
    assert rec.sleeps == [2.0, 4.0, 8.0, 10.0, 2.0]


def test_an_unexpected_error_in_a_pass_does_not_stop_the_worker() -> None:
    worker = ScriptedWorker([RuntimeError("bug"), PassResult(0)])
    rec = Recorder(stop_after=2)
    go(worker, rec)
    assert worker.passes == 2 and rec.beats == 2
    assert rec.sleeps[0] == 2.0  # treated like an outage: wait, then try again


def test_a_stop_request_ends_the_loop_before_the_next_pass() -> None:
    worker = ScriptedWorker([PassResult(1)])
    rec = Recorder(stop_after=0)
    go(worker, rec)
    assert worker.passes == 0


def test_cancellation_is_not_swallowed() -> None:
    worker = ScriptedWorker([asyncio.CancelledError()])
    rec = Recorder(stop_after=5)
    with pytest.raises(asyncio.CancelledError):
        go(worker, rec)
