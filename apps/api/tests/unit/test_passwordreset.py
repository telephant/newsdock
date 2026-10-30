"""TC-19 (AC-2): reset codes, their keyed hash and the mail text (pure rules)."""

import hmac
from datetime import UTC, datetime, timedelta

import pytest
from newsdock_api.domain.passwordreset import (
    CODE_PATTERN,
    DUMMY_USER_ID,
    code_expiry,
    hash_code,
    matches,
    new_code,
    reset_mail,
)

SECRET = "test-reset-secret-0123456789abcdef0123"
USER = "11111111-1111-1111-1111-111111111111"
OTHER_USER = "22222222-2222-2222-2222-222222222222"


def test_a_code_is_always_six_digits_including_leading_zeros() -> None:
    codes = [new_code() for _ in range(3000)]
    assert all(CODE_PATTERN.fullmatch(c) for c in codes)
    assert len(set(codes)) > 2500  # not constant, not a tiny set
    assert any(c.startswith("0") for c in codes)  # zero padding, not an int cast


def test_the_code_comes_from_the_secrets_module_over_a_million_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[int] = []

    def fake_randbelow(upper: int) -> int:
        seen.append(upper)
        return 7

    monkeypatch.setattr("secrets.randbelow", fake_randbelow)
    assert new_code() == "000007"
    assert seen == [10**6]


@pytest.mark.parametrize(
    "value,ok",
    [
        ("012345", True),
        ("999999", True),
        ("12345", False),
        ("1234567", False),
        ("12345a", False),
        (" 123456", False),
        ("123456\n", False),  # `$` would accept a trailing newline; fullmatch must not
        ("١٢٣٤٥٦", False),  # Arabic-Indic digits: `\d` would accept them
        ("", False),
    ],
)
def test_the_code_shape_is_exactly_six_ascii_digits(value: str, ok: bool) -> None:
    assert bool(CODE_PATTERN.fullmatch(value)) is ok


def test_the_hash_is_hex_sha256_sized_and_deterministic() -> None:
    first = hash_code(SECRET, USER, "123456")
    assert first == hash_code(SECRET, USER, "123456")
    assert len(first) == 64 and all(c in "0123456789abcdef" for c in first)


def test_the_hash_depends_on_secret_user_and_code() -> None:
    base = hash_code(SECRET, USER, "123456")
    assert hash_code(SECRET + "x", USER, "123456") != base
    assert hash_code(SECRET, OTHER_USER, "123456") != base
    assert hash_code(SECRET, USER, "123457") != base


def test_matches_is_true_only_for_the_right_triple() -> None:
    stored = hash_code(SECRET, USER, "123456")
    assert matches(stored, SECRET, USER, "123456")
    assert not matches(stored, SECRET, USER, "654321")
    assert not matches(stored, SECRET, OTHER_USER, "123456")  # a row cannot be replayed
    assert not matches(stored, SECRET + "x", USER, "123456")


@pytest.mark.parametrize("stored", ["", "abc", "z" * 64, "0" * 63, "é" * 64])
def test_matches_never_raises_on_odd_stored_values(stored: str) -> None:
    assert matches(stored, SECRET, USER, "123456") is False


def test_matches_uses_a_constant_time_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    real = hmac.compare_digest

    def spy(a: str, b: str) -> bool:
        calls.append((a, b))
        return bool(real(a, b))

    monkeypatch.setattr("hmac.compare_digest", spy)
    matches(hash_code(SECRET, USER, "123456"), SECRET, USER, "123456")
    assert len(calls) == 1


def test_the_dummy_user_id_hashes_like_any_other() -> None:
    # unknown emails are compared against this to keep the timing similar
    assert len(hash_code(SECRET, DUMMY_USER_ID, "000000")) == 64


def test_expiry_adds_the_lifetime() -> None:
    now = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
    assert code_expiry(now, 15) == now + timedelta(minutes=15)


def test_the_mail_has_the_code_the_lifetime_and_no_link() -> None:
    subject, body = reset_mail("042042", 15)
    assert subject == "newsdock: your password reset code"
    assert "042042" in body and "15 minutes" in body
    assert "ignore" in body.lower()
    assert "http" not in body.lower() and "www." not in body.lower()
    assert "@" not in body  # no address, no user name


def test_the_mail_says_one_minute_in_the_singular() -> None:
    body = reset_mail("123456", 1)[1]
    assert "valid for 1 minute." in body
    assert "1 minutes" not in body
