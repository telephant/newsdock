"""Agent identity and API-key rules (ADR-0016): pure, no I/O.

Key format `ndk_<prefix>_<secret>`: `prefix` is a public lookup handle, `secret`
is 256 random bits. Only `prefix` and sha256(secret) are stored. A fast hash is
right here because the secret is random, not a password (ui-login uses argon2).
"""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import datetime
from typing import NamedTuple, Protocol

from pydantic import BaseModel, ConfigDict

KEY_TAG = "ndk"
PREFIX_BYTES = 4
SECRET_BYTES = 32


class Agent(BaseModel):
    """The verified caller of one request; `id` is None for the anonymous agent."""

    model_config = ConfigDict(frozen=True)

    id: str | None
    name: str

    @property
    def is_anonymous(self) -> bool:
        return self.id is None


ANONYMOUS = Agent(id=None, name="anonymous")


class RegisteredAgent(BaseModel):
    """A stored agent (always has an id, unlike the anonymous `Agent`)."""

    id: str
    name: str
    key_id: str  # the key issued together with the agent


class GeneratedKey(NamedTuple):
    prefix: str
    secret: str
    key_hash: str

    @property
    def raw(self) -> str:
        """The plaintext key; shown to the admin once, never stored."""
        return f"{KEY_TAG}_{self.prefix}_{self.secret}"


class ParsedKey(NamedTuple):
    prefix: str
    secret: str


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def make_key() -> GeneratedKey:
    prefix = secrets.token_hex(PREFIX_BYTES)
    secret = secrets.token_hex(SECRET_BYTES)
    return GeneratedKey(prefix, secret, hash_secret(secret))


def parse_key(raw: str) -> ParsedKey | None:
    parts = raw.split("_")
    if len(parts) != 3 or parts[0] != KEY_TAG or not parts[1] or not parts[2]:
        return None
    return ParsedKey(prefix=parts[1], secret=parts[2])


def verify(secret: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(secret), stored_hash)


class StoredKey(BaseModel):
    """What the registry knows about a key, looked up by its public prefix."""

    key_id: str
    agent_id: str
    agent_name: str
    key_hash: str
    revoked: bool
    agent_active: bool

    @property
    def usable(self) -> bool:
        return self.agent_active and not self.revoked


class KeySummary(BaseModel):
    """Admin listing row: never carries the secret or its hash."""

    key_id: str
    prefix: str
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class AgentSummary(BaseModel):
    agent_id: str
    name: str
    status: str
    keys: list[KeySummary]


class AgentRegistry(Protocol):
    """What the admin routes need from persistence (implemented by SqlAgentsRepo)."""

    def create_agent(self, name: str, key: GeneratedKey) -> RegisteredAgent: ...

    def add_key(self, agent_id: str, key: GeneratedKey) -> str: ...

    def revoke_key(self, agent_id: str, key_id: str) -> bool: ...

    def set_status(self, agent_id: str, status: str) -> bool: ...

    def list_agents(self) -> list[AgentSummary]: ...


class KeyLookup(Protocol):
    """What the auth middleware needs from persistence."""

    def find_key(self, prefix: str) -> StoredKey | None: ...

    def touch_key(self, key_id: str, now: datetime) -> None: ...


def authenticate(
    authorization: str | None, find_key: Callable[[str], StoredKey | None]
) -> tuple[Agent, str] | None:
    """Resolve an `Authorization: Bearer <key>` header to (agent, key_id).

    None for anything that is not a usable key; callers must not say why.
    """
    scheme, _, presented = (authorization or "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    parsed = parse_key(presented.strip())
    if parsed is None:
        return None
    stored = find_key(parsed.prefix)
    if stored is None or not verify(parsed.secret, stored.key_hash):
        return None
    if not stored.usable:
        return None
    return Agent(id=stored.agent_id, name=stored.agent_name), stored.key_id
