"""Refresh tokens: long-lived credentials that let the browser obtain new access tokens (AUTH-004).

The token itself is a random string that exists only in the user's cookie. The database stores **only its SHA-256 hash**,
so a leaked database cannot be used to act as a user for the next 7 days. (A fast hash is correct here: the token is
256 bits of randomness, so it cannot be guessed, unlike a human-chosen password.)
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

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
