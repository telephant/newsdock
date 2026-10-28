"""TC-5, TC-6, TC-7 (AC-2, AC-3, AC-4, AC-5, AC-7): scoped agent repos (Docker)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.agents_repo import SqlAgentsRepo
from newsdock_api.adapters.subscriptions_repo import SqlSubscriptionsRepo
from newsdock_api.domain.agents import ALL, AgentScope, make_key
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


class World:
    """Users A and B, A's agent a1, B's agent b1, and an ownerless agent o1."""

    def __init__(self, engine: Engine) -> None:
        self.agents = SqlAgentsRepo(engine)
        self.subs = SqlSubscriptionsRepo(engine)
        self.user_a = self._user(engine, "a@x.io")
        self.user_b = self._user(engine, "b@x.io")
        self.a = AgentScope(everything=False, owner_id=self.user_a)
        self.b = AgentScope(everything=False, owner_id=self.user_b)
        self.a1 = self.agents.create_agent("a1", make_key(), self.user_a).id
        self.b1 = self.agents.create_agent("b1", make_key(), self.user_b).id
        self.o1 = self.agents.create_agent("o1", make_key(), None).id

    @staticmethod
    def _user(engine: Engine, email: str) -> str:
        with engine.begin() as conn:
            return str(
                conn.execute(
                    text(
                        "INSERT INTO users (email, password_hash, role) "
                        "VALUES (:e, 'x', 'viewer') RETURNING id"
                    ),
                    {"e": email},
                ).scalar_one()
            )


@pytest.fixture()
def world(engine: Engine) -> World:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE agents CASCADE"))
        conn.execute(text("TRUNCATE users CASCADE"))
    return World(engine)


def _names(world: World, scope: AgentScope) -> list[str]:
    return sorted(a.name for a in world.agents.list_agents(scope))


# TC-17 (AC-11): the quota counts every agent a user owns, disabled ones included
def test_count_owned_counts_all_statuses_per_owner(world: World) -> None:
    assert world.agents.count_owned(world.user_a) == 1
    assert world.agents.count_owned(world.user_b) == 1
    world.agents.create_agent("a2", make_key(), world.user_a)
    assert world.agents.set_status(world.a1, "disabled", world.a)
    assert world.agents.count_owned(world.user_a) == 2  # the disabled one counts
    assert world.agents.count_owned(world.user_b) == 1  # other users are unaffected
    assert world.agents.count_owned("00000000-0000-0000-0000-000000000000") == 0


# TC-5: creator recorded; listing follows the scope (AC-2, AC-3, AC-5)
def test_creator_is_recorded_and_listing_follows_the_scope(world: World) -> None:
    assert _names(world, world.a) == ["a1"]
    assert _names(world, world.b) == ["b1"]
    assert _names(world, ALL) == ["a1", "b1", "o1"]


def test_full_listing_carries_the_creator_and_marks_ownerless(world: World) -> None:
    by_name = {a.name: a for a in world.agents.list_agents(ALL)}
    assert by_name["a1"].owner_id == world.user_a
    assert by_name["a1"].owner_email == "a@x.io"
    assert by_name["o1"].owner_id is None and by_name["o1"].owner_email is None


def test_keys_in_a_scoped_listing_belong_to_visible_agents_only(world: World) -> None:
    (mine,) = world.agents.list_agents(world.a)
    assert mine.name == "a1" and len(mine.keys) == 1


def test_an_own_scope_with_no_agents_is_empty_not_everything(world: World) -> None:
    nobody = AgentScope(
        everything=False, owner_id="00000000-0000-0000-0000-000000000000"
    )
    assert world.agents.list_agents(nobody) == []


# TC-6: scoped writes on a foreign or ownerless agent change nothing (AC-4, AC-5)
def test_foreign_and_ownerless_agents_cannot_be_written_by_scope(world: World) -> None:
    for target in (world.a1, world.o1):
        foreign = world.b
        assert not world.agents.agent_visible(target, foreign)
        assert world.agents.add_key(target, make_key(), foreign) is None
        assert not world.agents.set_status(target, "disabled", foreign)
    owned_key = next(
        k.key_id
        for a in world.agents.list_agents(ALL)
        if a.name == "a1"
        for k in a.keys
    )
    assert not world.agents.revoke_key(world.a1, owned_key, world.b)
    statuses = {a.name: a.status for a in world.agents.list_agents(ALL)}
    assert statuses == {"a1": "active", "b1": "active", "o1": "active"}
    still = next(a for a in world.agents.list_agents(ALL) if a.name == "a1")
    assert len(still.keys) == 1 and still.keys[0].revoked_at is None


def test_the_owning_scope_and_the_full_scope_can_write(world: World) -> None:
    assert world.agents.agent_visible(world.a1, world.a)
    new_key = world.agents.add_key(world.a1, make_key(), world.a)
    assert new_key is not None
    assert world.agents.set_status(world.a1, "disabled", world.a)
    assert world.agents.revoke_key(world.a1, new_key, world.a)
    # the full scope reaches everyone, including the ownerless agent
    assert world.agents.set_status(world.o1, "disabled", ALL)
    assert world.agents.agent_visible(world.o1, ALL)


def test_unknown_and_malformed_ids_are_simply_not_visible(world: World) -> None:
    assert not world.agents.agent_visible("not-a-uuid", ALL)
    assert not world.agents.set_status("not-a-uuid", "disabled", ALL)
    assert world.agents.add_key("not-a-uuid", make_key(), ALL) is None


# TC-7: subscriptions follow the agent's visibility (AC-7)
def test_subscription_listing_and_delete_follow_the_scope(world: World) -> None:
    sub_a = world.subs.create(world.a1, {"domain": "a.org"})
    sub_b = world.subs.create(world.b1, {"text": "fed"})

    assert [s.id for s in world.subs.list_visible(world.a)] == [sub_a.id]
    assert sorted(s.agent_name for s in world.subs.list_visible(ALL)) == ["a1", "b1"]

    assert not world.subs.delete_visible(sub_b.id, world.a)  # B's: looks absent
    assert world.subs.exists(sub_b.id)
    assert not world.subs.delete_visible("not-a-uuid", ALL)
    assert world.subs.delete_visible(sub_a.id, world.a)
    assert world.subs.delete_visible(sub_b.id, ALL)  # the full scope reaches B's
    assert world.subs.list_visible(ALL) == []


def test_ownerless_agents_subscriptions_are_for_the_full_scope_only(
    world: World,
) -> None:
    sub_o = world.subs.create(world.o1, {})
    assert world.subs.list_visible(world.a) == []
    assert not world.subs.delete_visible(sub_o.id, world.a)
    assert [s.id for s in world.subs.list_visible(ALL)] == [sub_o.id]
