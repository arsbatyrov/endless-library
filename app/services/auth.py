"""Authentication service: check a login and a password (AUTH-004)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, verify_password
from app.models import User

_dummy_hash: str | None = None


def _get_dummy_hash() -> str:
    """A real hash of a throwaway password, used to spend the same time when the login does not exist."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("dummy-password-for-timing-equalisation")
    return _dummy_hash


def authenticate(db: Session, username: str, password: str) -> User | None:
    """The user if the login and password are right and the account is active, otherwise None.

    Every failure takes the same path and the same time:
    - the password check (the slow part) runs even when the login does not exist (against a dummy hash) and
      even when the account is disabled, so the speed of the answer reveals nothing;
    - the caller must answer all failures with the same status and body.
    The login is matched without regard to case, as the database's unique index does.
    """
    user = db.scalar(select(User).where(func.lower(User.username) == func.lower(username)))
    stored_hash = user.password_hash if user is not None else _get_dummy_hash()
    password_matches = verify_password(password, stored_hash)
    if user is None or not password_matches or not user.is_active:
        return None
    return user
