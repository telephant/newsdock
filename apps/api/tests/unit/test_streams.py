"""TC-13 (unit half, AC-13) and TC-17 (AC-6): stream cap and wake hub."""

import asyncio

import pytest
from newsdock_api.domain.streams import StreamLimiter, WakeHub


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---- TC-13: per-agent concurrent stream cap --------------------------------
def test_allows_n_then_denies() -> None:
    limiter = StreamLimiter(max_streams=2)
    assert limiter.try_acquire("alpha")
    assert limiter.try_acquire("alpha")
    assert not limiter.try_acquire("alpha")


def test_release_frees_a_slot_and_double_release_is_safe() -> None:
    limiter = StreamLimiter(max_streams=1)
    assert limiter.try_acquire("alpha")
    limiter.release("alpha")
    limiter.release("alpha")  # safe: never goes negative
    assert limiter.open_count("alpha") == 0
    assert limiter.try_acquire("alpha")
    assert not limiter.try_acquire("alpha")


def test_agents_are_isolated_and_zero_entries_are_dropped() -> None:
    limiter = StreamLimiter(max_streams=1)
    assert limiter.try_acquire("alpha")
    assert limiter.try_acquire("beta")
    limiter.release("alpha")
    limiter.release("beta")
    assert limiter.tracked() == 0


def test_zero_means_no_streams_allowed() -> None:
    assert not StreamLimiter(max_streams=0).try_acquire("alpha")


# ---- TC-17: wake hub -------------------------------------------------------
@pytest.mark.anyio
async def test_waiter_wakes_on_wake_all() -> None:
    hub = WakeHub()
    gen = hub.generation()
    waiter = asyncio.create_task(hub.wait(gen, timeout=5))
    await asyncio.sleep(0)
    hub.wake_all()
    assert await waiter is True


@pytest.mark.anyio
async def test_timeout_returns_false() -> None:
    hub = WakeHub()
    assert await hub.wait(hub.generation(), timeout=0.01) is False


@pytest.mark.anyio
async def test_all_waiters_wake() -> None:
    hub = WakeHub()
    gen = hub.generation()
    waiters = [asyncio.create_task(hub.wait(gen, timeout=5)) for _ in range(3)]
    await asyncio.sleep(0)
    hub.wake_all()
    assert await asyncio.gather(*waiters) == [True, True, True]


@pytest.mark.anyio
async def test_a_wake_before_the_wait_is_not_lost() -> None:
    hub = WakeHub()
    gen = hub.generation()  # the stream notes the generation, then queries...
    hub.wake_all()  # ...a notification lands while it is querying
    assert await hub.wait(gen, timeout=5) is True  # returns at once, no 5 s wait


@pytest.mark.anyio
async def test_after_a_wake_a_fresh_wait_blocks_again() -> None:
    hub = WakeHub()
    hub.wake_all()
    assert await hub.wait(hub.generation(), timeout=0.01) is False
