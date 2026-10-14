"""TC-3 (AC-2): API-key format, parsing, hashing and verification."""

import hashlib
import hmac
from typing import Any

import pytest
from newsdock_api.domain.agents import (
    ANONYMOUS,
    Agent,
    GeneratedKey,
    StoredKey,
    authenticate,
    hash_secret,
    make_key,
    parse_key,
    verify,
)


def test_make_key_format_and_entropy() -> None:
    key = make_key()
    assert key.raw == f"ndk_{key.prefix}_{key.secret}"
    assert "_" not in key.prefix and "_" not in key.secret
    assert len(key.secret) >= 64  # hex of >= 32 random bytes
    assert make_key().secret != key.secret


def test_hash_is_sha256_of_secret_only() -> None:
    key = make_key()
    assert key.key_hash == hashlib.sha256(key.secret.encode()).hexdigest()
    assert key.key_hash == hash_secret(key.secret)
    assert key.secret not in key.key_hash


def test_parse_round_trip() -> None:
    key = make_key()
    parsed = parse_key(key.raw)
    assert parsed is not None
    assert (parsed.prefix, parsed.secret) == (key.prefix, key.secret)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "ndk",
        "ndk_",
        "ndk__",
        "ndk_abc",
        "ndk_abc_",
        "xyz_abc_def",
        "ndk_a_b_c",
        "Bearer x",
    ],  # fmt: skip
)
def test_parse_rejects_malformed(raw: str) -> None:
    assert parse_key(raw) is None


def test_verify_accepts_right_and_rejects_wrong_secret() -> None:
    key = make_key()
    assert verify(key.secret, key.key_hash)
    assert not verify(make_key().secret, key.key_hash)
    assert not verify("", key.key_hash)


def test_verify_uses_constant_time_compare(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    real = hmac.compare_digest

    def spy(a: str, b: str) -> bool:
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr("newsdock_api.domain.agents.hmac.compare_digest", spy)
    key = make_key()
    assert verify(key.secret, key.key_hash)
    assert calls


def test_anonymous_agent() -> None:
    assert ANONYMOUS == Agent(id=None, name="anonymous")
    assert ANONYMOUS.is_anonymous
    assert not Agent(id="1", name="alpha").is_anonymous


# T-05: header → agent resolution (pure; backs AC-3/AC-4/AC-5)
def _stored(key: GeneratedKey, **kw: Any) -> StoredKey:
    base: dict[str, Any] = dict(
        key_id="k1", agent_id="a1", agent_name="alpha",
        key_hash=key.key_hash,
        revoked=False, agent_active=True,
    )  # fmt: skip
    base.update(kw)
    return StoredKey(**base)


def test_authenticate_accepts_a_valid_bearer_key() -> None:
    key = make_key()
    found = authenticate(f"Bearer {key.raw}", lambda prefix: _stored(key))
    assert found is not None
    agent, key_id = found
    assert (agent.id, agent.name, key_id) == ("a1", "alpha", "k1")


@pytest.mark.parametrize("header", [None, "", "Bearer", "Basic x", "Bearer junk"])
def test_authenticate_rejects_missing_or_malformed(header: str | None) -> None:
    assert authenticate(header, lambda prefix: pytest.fail("no lookup")) is None


def test_authenticate_rejects_unknown_wrong_revoked_disabled() -> None:
    key = make_key()
    raw = f"Bearer {key.raw}"
    assert authenticate(raw, lambda p: None) is None
    assert authenticate(raw, lambda p: _stored(make_key())) is None  # wrong secret
    assert authenticate(raw, lambda p: _stored(key, revoked=True)) is None
    assert authenticate(raw, lambda p: _stored(key, agent_active=False)) is None
