"""AUTH-005: rotation of refresh tokens at the service level (races and time handling)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import update

from app.auth.refresh_tokens import issue_refresh_token, rotate_refresh_token
from app.models import RefreshToken
from tests.factories import make_user

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def test_two_simultaneous_requests_with_one_token_cannot_both_win(db, monkeypatch):
    """The second request read the token as unused, but the first one already claimed it: treat it as reuse."""
    user = make_user(db)
    token = issue_refresh_token(db, user, now=NOW)
    db.commit()
    row = db.query(RefreshToken).one()
    stale_view = SimpleNamespace(
        id=row.id, user_id=user.id, revoked_at=None, expires_at=row.expires_at
    )
    db.execute(update(RefreshToken).values(revoked_at=NOW))  # the first request won
    db.commit()
    monkeypatch.setattr(db, "scalar", lambda *args, **kwargs: stale_view)

    result = rotate_refresh_token(db, token, now=NOW + timedelta(seconds=1))

    assert result is None
    assert db.query(RefreshToken).count() == 1  # no new token was issued


def test_token_is_valid_until_the_exact_expiry_moment(db):
    user = make_user(db)
    token = issue_refresh_token(db, user, now=NOW)
    db.commit()
    expiry = NOW + timedelta(days=7)

    assert rotate_refresh_token(db, token, now=expiry) is None


def test_token_one_second_before_expiry_is_accepted(db):
    user = make_user(db)
    token = issue_refresh_token(db, user, now=NOW)
    db.commit()

    assert (
        rotate_refresh_token(db, token, now=NOW + timedelta(days=7) - timedelta(seconds=1))
        is not None
    )
