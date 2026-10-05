"""Password hashing and the password policy (AUTH-002).

Passwords are never stored: only a salted argon2id hash is. Argon2id is deliberately slow and memory-hungry, which makes
guessing passwords from a leaked database expensive. Every hash gets its own random salt, so two accounts with the same
password have different hashes.

This module is pure logic: no database, no HTTP. The endpoints that use it come with later tickets (login, user management).
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 8
# An upper limit protects the server: hashing a huge password would be a cheap way to load it.
MAX_PASSWORD_LENGTH = 128

# argon2-cffi defaults: argon2id with the library's recommended cost parameters.
_hasher = PasswordHasher()


class PasswordPolicyError(ValueError):
    """A password breaks the policy. `code` is a stable machine-readable reason (for API errors and tests)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_password_policy(password: str, username: str | None = None) -> None:
    """Raise PasswordPolicyError if the password is not acceptable.

    Rules: at least 8 and at most 128 characters (characters, not bytes), and not equal to the login.
    Logins are case-insensitive, so the comparison with the login ignores case.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            "too_short", f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            "too_long", f"Password must be at most {MAX_PASSWORD_LENGTH} characters long"
        )
    if username is not None and password.casefold() == username.casefold():
        raise PasswordPolicyError("same_as_username", "Password must not be the same as the login")


def hash_password(password: str) -> str:
    """Return the salted argon2id hash of the password (a self-describing string that includes the salt and parameters)."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """True only if the password matches the hash. Never raises: a broken or unknown hash simply does not match."""
    if not isinstance(password_hash, str):
        return False
    # A stored password can never be longer than the maximum, so a longer attempt cannot match.
    # Refuse it before the expensive computation.
    if len(password) > MAX_PASSWORD_LENGTH:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        # VerificationError covers a wrong password (VerifyMismatchError is its subclass) and a damaged hash;
        # InvalidHashError is an unknown or malformed hash string.
        return False
