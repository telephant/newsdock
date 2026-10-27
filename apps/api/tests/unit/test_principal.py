"""Principal resolution (C-12, design-detail §2): key, admin token or session cookie."""

from datetime import UTC, datetime, timedelta

from newsdock_api.adapters.principal import PrincipalResolver
from newsdock_api.domain.accounts import (
    AdminTokenPrincipal,
    AgentPrincipal,
    Role,
    SessionInfo,
    UserPrincipal,
    hash_token,
)
from newsdock_api.domain.agents import StoredKey, make_key

NOW = datetime(2026, 10, 27, 12, 0, 0, tzinfo=UTC)
IDLE = timedelta(hours=12)
ADMIN = "admin-token-for-tests"
COOKIE = "cookie-value-1"


class Sessions:
    def __init__(self) -> None:
        self.rows: dict[str, SessionInfo] = {}
        self.touched: list[str] = []
        self.deleted: list[str] = []

    def add(self, token: str, *, role: Role = Role.VIEWER, **kw: datetime) -> None:
        self.rows[hash_token(token)] = SessionInfo(
            user_id="u1",
            email="a@x.io",
            role=role,
            last_seen_at=kw.get("last_seen_at", NOW - timedelta(seconds=5)),
            expires_at=kw.get("expires_at", NOW + timedelta(days=1)),
        )

    def find_session(self, token_hash: str) -> SessionInfo | None:
        return self.rows.get(token_hash)

    def touch_session(self, token_hash: str, now: datetime) -> None:
        self.touched.append(token_hash)

    def delete_session(self, token_hash: str) -> bool:
        self.deleted.append(token_hash)
        return self.rows.pop(token_hash, None) is not None


class Keys:
    def __init__(self) -> None:
        self.keys: dict[str, StoredKey] = {}

    def add(self, name: str, *, revoked: bool = False) -> str:
        key = make_key()
        self.keys[key.prefix] = StoredKey(
            key_id=f"k-{name}",
            agent_id=f"id-{name}",
            agent_name=name,
            key_hash=key.key_hash,
            revoked=revoked,
            agent_active=True,
        )
        return key.raw

    def find_key(self, prefix: str) -> StoredKey | None:
        return self.keys.get(prefix)

    def touch_key(self, key_id: str, now: datetime) -> None:
        pass


def make(admin: str | None = ADMIN) -> tuple[PrincipalResolver, Sessions, Keys]:
    sessions, keys = Sessions(), Keys()
    resolver = PrincipalResolver(
        sessions=sessions, keys=keys, admin_token=admin, idle=IDLE, clock=lambda: NOW
    )
    return resolver, sessions, keys


def test_no_credentials_is_anonymous() -> None:
    resolver, _, _ = make()
    assert resolver.resolve(None, None) is None


def test_a_valid_cookie_resolves_to_the_current_user_and_role() -> None:
    resolver, sessions, _ = make()
    sessions.add(COOKIE, role=Role.ADMIN)
    assert resolver.resolve(None, COOKIE) == UserPrincipal(
        user_id="u1", email="a@x.io", role=Role.ADMIN
    )


def test_unknown_or_forged_cookie_is_anonymous() -> None:
    resolver, sessions, _ = make()
    sessions.add(COOKIE)
    assert resolver.resolve(None, "forged") is None
    assert resolver.resolve(None, "") is None


def test_idle_session_is_rejected_and_removed() -> None:
    resolver, sessions, _ = make()
    sessions.add(COOKIE, last_seen_at=NOW - IDLE - timedelta(seconds=1))
    assert resolver.resolve(None, COOKIE) is None
    assert sessions.deleted == [hash_token(COOKIE)]


def test_absolute_expiry_is_rejected_and_removed() -> None:
    resolver, sessions, _ = make()
    sessions.add(COOKIE, expires_at=NOW)
    assert resolver.resolve(None, COOKIE) is None
    assert sessions.deleted == [hash_token(COOKIE)]


def test_last_seen_is_refreshed_at_most_once_a_minute() -> None:
    resolver, sessions, _ = make()
    sessions.add(COOKIE, last_seen_at=NOW - timedelta(seconds=10))
    resolver.resolve(None, COOKIE)
    assert sessions.touched == []
    sessions.add("old", last_seen_at=NOW - timedelta(minutes=5))
    resolver.resolve(None, "old")
    assert sessions.touched == [hash_token("old")]


def test_a_valid_key_resolves_to_its_agent() -> None:
    resolver, _, keys = make()
    raw = keys.add("alpha")
    principal = resolver.resolve(f"Bearer {raw}", None)
    assert isinstance(principal, AgentPrincipal)
    assert (principal.agent.name, principal.key_id) == ("alpha", "k-alpha")


def test_a_revoked_key_is_anonymous() -> None:
    resolver, _, keys = make()
    assert resolver.resolve(f"Bearer {keys.add('a', revoked=True)}", None) is None


def test_the_key_wins_over_a_cookie_and_there_is_no_fallback() -> None:
    resolver, sessions, keys = make()
    sessions.add(COOKIE)
    good, bad = keys.add("good"), keys.add("bad", revoked=True)
    assert isinstance(resolver.resolve(f"Bearer {good}", COOKIE), AgentPrincipal)
    assert resolver.resolve(f"Bearer {bad}", COOKIE) is None  # not the cookie's user


def test_admin_token_resolves_only_on_an_exact_match() -> None:
    resolver, sessions, _ = make()
    assert resolver.resolve(f"Bearer {ADMIN}", None) == AdminTokenPrincipal()
    assert resolver.resolve(f"Bearer {ADMIN}x", None) is None
    assert resolver.resolve(f"bearer {ADMIN}", None) == AdminTokenPrincipal()
    sessions.add(COOKIE)
    assert resolver.resolve(f"Bearer {ADMIN}", COOKIE) == AdminTokenPrincipal()


def test_without_a_configured_admin_token_nothing_matches_it() -> None:
    resolver, _, _ = make(admin=None)
    assert resolver.resolve("Bearer anything", None) is None
    assert resolver.resolve("Bearer ", None) is None


def test_other_schemes_are_anonymous_and_do_not_fall_back_to_the_cookie() -> None:
    resolver, sessions, _ = make()
    sessions.add(COOKIE)
    assert resolver.resolve("Basic abc", COOKIE) is None
