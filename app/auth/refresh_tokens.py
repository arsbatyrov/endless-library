"""Refresh tokens: long-lived credentials that let the browser obtain new access tokens (AUTH-004).

The token itself is a random string that exists only in the user's cookie. The database stores **only its SHA-256 hash**,
so a leaked database cannot be used to act as a user for the next 7 days. (A fast hash is correct here: the token is
256 bits of randomness, so it cannot be guessed, unlike a human-chosen password.)
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import RefreshToken, User

REFRESH_TOKEN_LIFETIME = timedelta(days=7)
COOKIE_NAME = "refresh_token"


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_refresh_token(db: Session, user: User, now: datetime | None = None) -> str:
    """Create a refresh token for the user, store its hash (the caller commits) and return the token itself."""
    now = now or datetime.now(UTC)
    token = secrets.token_urlsafe(32)  # 256 bits of randomness
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(token),
            expires_at=now + REFRESH_TOKEN_LIFETIME,
            created_at=now,
        )
    )
    return token


def _revoke_all(db: Session, user_id: int, now: datetime) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )


def rotate_refresh_token(
    db: Session, token: str, now: datetime | None = None
) -> tuple[User, str] | None:
    """Exchange a valid refresh token for a new one (rotation). Returns (user, new token) or None.

    None covers every failure (unknown, expired, revoked, disabled user), so the caller answers them all the same way.
    A token that was already replaced or revoked is presented again: that means a copy of it exists somewhere it
    should not, so every token of that user is revoked and both the thief and the owner must sign in again.
    """
    now = now or datetime.now(UTC)
    row = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token))
    )
    if row is None:
        return None
    if row.revoked_at is not None:
        _revoke_all(db, row.user_id, now)
        db.commit()
        return None
    if row.expires_at <= now:
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None

    # Claim the token with one conditional UPDATE: of two simultaneous requests with the same token only one wins.
    claimed = db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == row.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        _revoke_all(db, row.user_id, now)
        db.commit()
        return None
    new_token = issue_refresh_token(db, user, now)
    db.commit()
    return user, new_token


def revoke_refresh_token(db: Session, token: str, now: datetime | None = None) -> None:
    """Logout: revoke this one token. Unknown or already revoked tokens are ignored (logout is idempotent)."""
    db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(token), RefreshToken.revoked_at.is_(None)
        )
        .values(revoked_at=now or datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    db.commit()
