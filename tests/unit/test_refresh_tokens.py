"""AUTH-004: issuing a refresh token. Only the hash is stored; the token itself lives only in the user's cookie.

If the database leaks, hashes cannot be used to act as the user (a refresh token is a password for 7 days).
"""

import hashlib
from datetime import UTC, datetime, timedelta

from app.auth.refresh_tokens import REFRESH_TOKEN_LIFETIME, hash_refresh_token, issue_refresh_token
from app.models import RefreshToken
from tests.factories import make_user

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def test_refresh_token_lives_for_7_days():
    assert REFRESH_TOKEN_LIFETIME == timedelta(days=7)


def test_hash_is_sha256_in_hex():
    assert hash_refresh_token("abc") == hashlib.sha256(b"abc").hexdigest()
    assert len(hash_refresh_token("abc")) == 64  # fits the column


def test_issuing_stores_only_the_hash(db):
    user = make_user(db)

    token = issue_refresh_token(db, user, now=NOW)
    db.commit()

    row = db.query(RefreshToken).one()
    assert row.token_hash == hash_refresh_token(token)
    assert token not in (row.token_hash, str(row.user_id))
    assert row.user_id == user.id


def test_row_expires_after_the_lifetime_and_is_not_revoked(db):
    user = make_user(db)

    issue_refresh_token(db, user, now=NOW)
    db.commit()

    row = db.query(RefreshToken).one()
    assert row.expires_at == NOW + REFRESH_TOKEN_LIFETIME
    assert row.created_at is not None
    assert row.revoked_at is None


def test_tokens_are_random_and_long_enough(db):
    user = make_user(db)

    first, second = issue_refresh_token(db, user), issue_refresh_token(db, user)
    db.commit()

    assert first != second
    assert len(first) >= 43  # 32 random bytes in urlsafe base64
    assert db.query(RefreshToken).count() == 2
