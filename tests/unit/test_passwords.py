"""AUTH-002: password hashing and the password policy (pure logic, no database).

Requirement: AUTH-002, acceptance criteria 1-5 (each test names the criterion it covers).
"""

import pytest

from app.auth import passwords
from app.auth.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PasswordPolicyError,
    hash_password,
    validate_password_policy,
    verify_password,
)

PASSWORD = "correct horse"


# ---------- criterion 1: hash and verify ----------


def test_hash_is_not_the_password_and_does_not_contain_it():
    password_hash = hash_password(PASSWORD)

    assert password_hash != PASSWORD
    assert PASSWORD not in password_hash


def test_hash_uses_argon2id():
    assert hash_password(PASSWORD).startswith("$argon2id$")


def test_correct_password_verifies():
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


@pytest.mark.parametrize(
    "wrong", ["wrong horse", "correct horse ", " correct horse", "Correct horse", ""]
)
def test_wrong_password_does_not_verify(wrong):
    assert verify_password(wrong, hash_password(PASSWORD)) is False


# ---------- criterion 2: salt ----------


def test_same_password_gives_different_hashes():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)

    assert first != second
    assert verify_password(PASSWORD, first) is True
    assert verify_password(PASSWORD, second) is True


# ---------- criterion 3: minimum length ----------


@pytest.mark.parametrize("length", [0, 1, MIN_PASSWORD_LENGTH - 1])
def test_password_shorter_than_the_minimum_is_rejected(length):
    with pytest.raises(PasswordPolicyError) as error:
        validate_password_policy("a" * length)

    assert error.value.code == "too_short"


def test_password_of_exactly_the_minimum_length_is_accepted():
    validate_password_policy("a" * MIN_PASSWORD_LENGTH)


def test_minimum_length_is_8_characters():
    assert MIN_PASSWORD_LENGTH == 8


def test_length_counts_characters_not_bytes():
    """Seven Cyrillic letters are 14 bytes but 7 characters: still too short. Eight are enough."""
    with pytest.raises(PasswordPolicyError) as error:
        validate_password_policy("пароль1")  # 7 characters
    assert error.value.code == "too_short"

    validate_password_policy("пароль12")  # 8 characters


# ---------- criterion 4: maximum length and password equal to the login ----------


def test_password_of_exactly_the_maximum_length_is_accepted():
    validate_password_policy("a" * MAX_PASSWORD_LENGTH)


@pytest.mark.parametrize("extra", [1, 2, 1000])
def test_password_longer_than_the_maximum_is_rejected(extra):
    with pytest.raises(PasswordPolicyError) as error:
        validate_password_policy("a" * (MAX_PASSWORD_LENGTH + extra))

    assert error.value.code == "too_long"


def test_maximum_length_is_128_characters():
    assert MAX_PASSWORD_LENGTH == 128


@pytest.mark.parametrize("password", ["librarian", "Librarian", "LIBRARIAN"])
def test_password_equal_to_the_login_is_rejected_in_any_case(password):
    """Logins are case-insensitive, so the comparison is too."""
    with pytest.raises(PasswordPolicyError) as error:
        validate_password_policy(password, username="Librarian")

    assert error.value.code == "same_as_username"


def test_password_that_only_contains_the_login_is_accepted():
    validate_password_policy("librarian-2026", username="librarian")


def test_equality_with_the_login_is_not_checked_when_there_is_no_login():
    validate_password_policy("librarian", username=None)


def test_a_policy_violation_has_a_readable_message():
    with pytest.raises(PasswordPolicyError) as error:
        validate_password_policy("short")

    assert "8" in str(error.value)


# ---------- criterion 5: broken hashes ----------


@pytest.mark.parametrize(
    "broken",
    [
        "",
        "not-a-hash",
        "$argon2id$",
        "$argon2id$v=19$m=65536,t=3,p=4$garbage$garbage",
        "$2b$12$abcdefghijklmnopqrstuuABCDEFGHIJKLMNOPQRSTUVWXYZ012345",  # a bcrypt-style hash
        "x" * 500,
    ],
)
def test_broken_or_unknown_hash_gives_false_without_an_exception(broken):
    assert verify_password(PASSWORD, broken) is False


def test_truncated_real_hash_gives_false():
    real = hash_password(PASSWORD)

    assert verify_password(PASSWORD, real[:-10]) is False


def test_tampered_real_hash_gives_false():
    real = hash_password(PASSWORD)
    tampered = real[:-4] + ("AAAA" if not real.endswith("AAAA") else "BBBB")

    assert verify_password(PASSWORD, tampered) is False


def test_missing_hash_gives_false():
    assert verify_password(PASSWORD, None) is False


# ---------- protection of the server ----------


def test_overlong_password_is_rejected_without_hashing(monkeypatch):
    """A stored password can never be longer than the maximum, so a longer attempt cannot match.
    It must be refused before the expensive hash is computed (otherwise a huge password is a cheap way to load the server)."""

    class ExplodingHasher:
        def verify(self, *args, **kwargs):
            raise AssertionError("the hasher must not be called for an overlong password")

    monkeypatch.setattr(passwords, "_hasher", ExplodingHasher())

    assert verify_password("a" * (MAX_PASSWORD_LENGTH + 1), "$argon2id$anything") is False
