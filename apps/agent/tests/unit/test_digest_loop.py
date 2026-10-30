"""Digest entry: hourly loop, heartbeat, --once (TC-19; AC-13)."""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

import pytest
from newsdock_agent import digest
from newsdock_agent.config import Settings
from newsdock_agent.domain.digest import DigestCycle
from newsdock_agent.domain.loop import Unauthorized


class ClockLike(Protocol):
    now: datetime
    sleeps: list[float]

    def __call__(self) -> datetime: ...

    def sleep(self, seconds: float) -> None: ...


class FakeCycle:
    def __init__(self, clock: ClockLike, fail_on: dict[int, Exception] | None = None):
        self.clock = clock
        self.fail_on = fail_on or {}
        self.times: list[datetime] = []

    def run_once(self, now: datetime) -> None:
        self.times.append(now)
        error = self.fail_on.get(len(self.times))
        if error is not None:
            raise error


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("NEWSDOCK_CONFIG_FILE", "NEWSDOCK_AGENT_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NEWSDOCK_AGENT_HEARTBEAT_FILE", str(tmp_path / "healthy"))


# ---- TC-19: cadence ----------------------------------------------------------------


def test_tc19_one_cycle_at_start_then_one_per_interval(clock: ClockLike) -> None:
    cycle = FakeCycle(clock)
    start = clock.now
    beats: list[int] = []
    digest.run_loop(
        cycle,
        clock=clock,
        sleep=clock.sleep,
        interval_seconds=3600,
        heartbeat=lambda: beats.append(1),
        max_cycles=3,
    )
    assert cycle.times == [
        start,
        start + timedelta(hours=1),
        start + timedelta(hours=2),
    ]
    assert clock.sleeps == [3600, 3600]  # between cycles, none after the last
    assert len(beats) == 4  # once at start, then after every cycle


def test_tc19_a_failing_cycle_is_logged_and_the_loop_continues(
    clock: ClockLike, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    cycle = FakeCycle(clock, fail_on={2: RuntimeError("api down")})
    beats: list[int] = []
    digest.run_loop(
        cycle,
        clock=clock,
        sleep=clock.sleep,
        interval_seconds=3600,
        heartbeat=lambda: beats.append(1),
        max_cycles=3,
    )
    assert len(cycle.times) == 3  # the failure on run 2 did not stop run 3
    assert any("will retry" in r.getMessage() for r in caplog.records)
    assert len(beats) == 4  # the heartbeat is written after a failed pass too


def test_tc19_a_rejected_key_is_named_in_the_log(
    clock: ClockLike, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR)
    cycle = FakeCycle(clock, fail_on={1: Unauthorized("http://api/mcp")})
    digest.run_loop(
        cycle,
        clock=clock,
        sleep=clock.sleep,
        interval_seconds=3600,
        heartbeat=lambda: None,
        max_cycles=1,
    )
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "401" in messages and "NEWSDOCK_AGENT_API_KEY" in messages


# ---- --once and the wiring --------------------------------------------------


def test_tc19_once_runs_exactly_one_cycle_and_returns_zero(clock: ClockLike) -> None:
    cycle = FakeCycle(clock)
    code = digest.run_cli(
        cycle, once=True, clock=clock, sleep=clock.sleep, interval_seconds=3600,
        heartbeat=lambda: None,
    )  # fmt: skip
    assert code == 0 and len(cycle.times) == 1 and clock.sleeps == []


def test_tc19_once_returns_one_when_the_cycle_fails(clock: ClockLike) -> None:
    cycle = FakeCycle(clock, fail_on={1: RuntimeError("boom")})
    code = digest.run_cli(
        cycle, once=True, clock=clock, sleep=clock.sleep, interval_seconds=3600,
        heartbeat=lambda: None,
    )  # fmt: skip
    assert code == 1 and len(cycle.times) == 1


def test_build_cycle_takes_its_parameters_from_the_settings() -> None:
    cycle = digest.build_cycle(Settings())
    assert isinstance(cycle, DigestCycle)
    params = cycle._params
    assert params.page_size == 200  # batch_limit, the API's page maximum
    assert params.skip_prefixes[:2] == ("TAX_", "WB_")
    assert (params.max_themes, params.stories_per_theme) == (8, 3)


def test_main_once_wires_settings_and_writes_the_heartbeat(
    clock: ClockLike, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cycle = FakeCycle(clock)
    monkeypatch.setattr(digest, "build_cycle", lambda settings: cycle)
    assert digest.main(["--once"]) == 0
    assert len(cycle.times) == 1
    beat = tmp_path / "healthy"
    assert beat.read_text() == str(Settings().digest_heartbeat_max_age_seconds)


def test_main_warns_when_no_api_key_is_set(
    clock: ClockLike, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(digest, "build_cycle", lambda settings: FakeCycle(clock))
    digest.main(["--once"])
    assert any("NEWSDOCK_AGENT_API_KEY" in r.getMessage() for r in caplog.records)
