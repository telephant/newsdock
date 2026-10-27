"""TC-2 (AC-1): the argon2id adapter behind the PasswordHasher port."""

from argon2 import PasswordHasher as RawHasher
from newsdock_api.adapters.passwords import Argon2Hasher, make_dummy_hash
from newsdock_api.domain.accounts import hash_token, new_session_token


def test_hash_is_argon2id_and_not_the_plaintext() -> None:
    hasher = Argon2Hasher()
    stored = hasher.hash("correct horse battery")
    assert stored.startswith("$argon2id$")
    assert "correct horse battery" not in stored
    assert hasher.hash("correct horse battery") != stored  # random salt


def test_verify_accepts_the_right_password_and_rejects_others() -> None:
    hasher = Argon2Hasher()
    stored = hasher.hash("correct horse battery")
    assert hasher.verify(stored, "correct horse battery")
    assert not hasher.verify(stored, "wrong password!!")
    assert not hasher.verify(stored, "")


def test_verify_never_raises_on_garbage_hashes() -> None:
    hasher = Argon2Hasher()
    for garbage in ("", "plain", "$argon2id$broken", "h:secret", "$2b$12$abc"):
        assert hasher.verify(garbage, "whatever-password") is False


def test_needs_rehash_for_weaker_parameters_only() -> None:
    hasher = Argon2Hasher()
    weak = RawHasher(time_cost=1, memory_cost=8, parallelism=1).hash("pw-for-test")
    assert hasher.needs_rehash(weak)
    assert not hasher.needs_rehash(hasher.hash("pw-for-test"))
    assert not hasher.needs_rehash("garbage")  # unreadable: not ours to upgrade


def test_dummy_hash_is_a_real_hash_nobody_knows() -> None:
    hasher = Argon2Hasher()
    dummy = make_dummy_hash(hasher)
    assert dummy.startswith("$argon2id$")
    assert dummy != make_dummy_hash(hasher)
    assert not hasher.verify(dummy, "")


def test_session_tokens_are_random_and_hashed_with_sha256() -> None:
    first, second = new_session_token(), new_session_token()
    assert first != second and len(first) >= 43  # 32 random bytes, base64url
    digest = hash_token(first)
    assert len(digest) == 64 and digest != first
    assert hash_token(first) == digest
