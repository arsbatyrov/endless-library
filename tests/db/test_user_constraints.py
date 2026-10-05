"""AUTH-001: database constraints of the account tables (`users`, `refresh_tokens`).

Like tests/db/test_constraints.py, these tests go straight to the database (bypassing the application) and check that
PostgreSQL itself rejects invalid accounts: it is the last line of defence if application code, a script or a manual edit gets it wrong.
Requirement: AUTH-001 (acceptance criteria 2, 3 and 4 plus the supporting rules).
"""

from datetime import UTC, datetime, timedelta

import psycopg.errors as pg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError

from app.models import Reader, RefreshToken, User
from tests.factories import make_reader, make_user

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def new_user(**overrides) -> User:
    values = {"username": "ann", "password_hash": "x", "role": "admin", "reader_id": None}
    values.update(overrides)
    return User(**values)


def violation(db, entity=None):
    """Commit and return the PostgreSQL error that the database raised."""
    if entity is not None:
        db.add(entity)
    with pytest.raises((IntegrityError, DataError)) as error:
        db.commit()
    return error.value.orig


# ---------- username (criterion 2) ----------


def test_username_is_unique_without_regard_to_case(db):
    make_user(db, username="Ann")

    error = violation(db, new_user(username="ann"))

    assert isinstance(error, pg.UniqueViolation)
    assert error.diag.constraint_name == "users_username_lower_key"


def test_exact_duplicate_username_is_rejected(db):
    make_user(db, username="ann")

    error = violation(db, new_user(username="ann"))

    assert isinstance(error, pg.UniqueViolation)


def test_usernames_that_differ_by_more_than_case_are_both_allowed(db):
    make_user(db, username="ann")
    make_user(db, username="ann2")

    assert db.query(User).count() == 2


def test_username_longer_than_the_column_is_rejected(db):
    error = violation(db, new_user(username="a" * 65))

    assert isinstance(error, pg.StringDataRightTruncation)


@pytest.mark.parametrize("column", ["username", "password_hash", "role"])
def test_required_user_columns_are_not_null(db, column):
    error = violation(db, new_user(**{column: None}))

    assert isinstance(error, pg.NotNullViolation)
    assert error.diag.column_name == column


def test_is_active_cannot_be_null(db):
    """Plain SQL: through the ORM an explicit None would be replaced by the application default (True)."""
    with pytest.raises(IntegrityError) as error:
        db.execute(
            text(
                "INSERT INTO users (username, password_hash, role, is_active, created_at) "
                "VALUES ('x', 'h', 'admin', NULL, now())"
            )
        )

    assert isinstance(error.value.orig, pg.NotNullViolation)
    assert error.value.orig.diag.column_name == "is_active"


# ---------- role and the link to a reader (criterion 3) ----------


def test_role_must_be_one_of_the_known_roles(db):
    error = violation(db, new_user(role="root"))

    assert isinstance(error, pg.CheckViolation)
    assert error.diag.constraint_name == "users_role_check"


def test_reader_account_without_a_reader_is_rejected(db):
    error = violation(db, new_user(role="reader", reader_id=None))

    assert isinstance(error, pg.CheckViolation)
    assert error.diag.constraint_name == "users_reader_link_check"


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_staff_account_with_a_reader_is_rejected(db, role):
    reader = make_reader(db)

    error = violation(db, new_user(role=role, reader_id=reader.id))

    assert isinstance(error, pg.CheckViolation)
    assert error.diag.constraint_name == "users_reader_link_check"


def test_valid_role_and_reader_combinations_are_accepted(db):
    reader = make_reader(db)
    make_user(db, role="reader", username="r", reader=reader)
    make_user(db, role="librarian", username="l")
    make_user(db, role="admin", username="a")

    roles = sorted(user.role for user in db.query(User))

    assert roles == ["admin", "librarian", "reader"]


def test_account_for_an_unknown_reader_is_rejected(db):
    error = violation(db, new_user(role="reader", reader_id=999))

    assert isinstance(error, pg.ForeignKeyViolation)
    assert error.diag.constraint_name == "users_reader_id_fkey"


# ---------- one account per reader (criterion 4) ----------


def test_two_accounts_for_the_same_reader_are_rejected(db):
    reader = make_reader(db)
    make_user(db, role="reader", username="first", reader=reader)

    error = violation(db, new_user(username="second", role="reader", reader_id=reader.id))

    assert isinstance(error, pg.UniqueViolation)
    assert error.diag.constraint_name == "users_reader_id_key"


def test_many_staff_accounts_without_a_reader_are_allowed(db):
    """NULL is not 'the same value': several librarians and admins may exist (the uniqueness applies to real readers)."""
    for number in range(3):
        make_user(db, role="librarian", username=f"lib{number}")

    assert db.query(User).count() == 3


def test_database_blocks_deleting_a_reader_that_has_an_account(db):
    """A reader card with an account cannot disappear silently. The application must handle this case explicitly."""
    reader = make_reader(db)
    make_user(db, role="reader", reader=reader)

    with pytest.raises(IntegrityError) as error:
        db.execute(text("DELETE FROM readers"))

    assert isinstance(error.value.orig, pg.ForeignKeyViolation)


# ---------- column values and defaults ----------


def test_new_user_gets_defaults_from_the_application(db):
    user = make_user(db)

    assert user.is_active is True
    assert user.last_login_at is None
    assert user.created_at.tzinfo is not None
    assert abs(datetime.now(UTC) - user.created_at) < timedelta(minutes=1)


def test_timestamps_are_stored_in_utc(db):
    user = make_user(db)
    user.last_login_at = NOW
    db.commit()
    db.refresh(user)

    assert user.last_login_at == NOW
    assert user.last_login_at.utcoffset() == timedelta(0)


# ---------- refresh tokens ----------


def make_token(db, user, token_hash="h1", **overrides) -> RefreshToken:
    values = {"user_id": user.id, "token_hash": token_hash, "expires_at": NOW + timedelta(days=7)}
    values.update(overrides)
    token = RefreshToken(**values)
    db.add(token)
    db.commit()
    return token


def test_refresh_token_hash_must_be_unique(db):
    user = make_user(db)
    make_token(db, user, token_hash="same")

    error = violation(db, RefreshToken(user_id=user.id, token_hash="same", expires_at=NOW))

    assert isinstance(error, pg.UniqueViolation)
    assert error.diag.constraint_name == "refresh_tokens_token_hash_key"


def test_refresh_token_for_an_unknown_user_is_rejected(db):
    error = violation(db, RefreshToken(user_id=999, token_hash="h", expires_at=NOW))

    assert isinstance(error, pg.ForeignKeyViolation)
    assert error.diag.constraint_name == "refresh_tokens_user_id_fkey"


@pytest.mark.parametrize("column", ["user_id", "token_hash", "expires_at"])
def test_required_refresh_token_columns_are_not_null(db, column):
    user = make_user(db)
    values = {"user_id": user.id, "token_hash": "h", "expires_at": NOW}
    values[column] = None

    error = violation(db, RefreshToken(**values))

    assert isinstance(error, pg.NotNullViolation)
    assert error.diag.column_name == column


def test_refresh_token_is_not_revoked_by_default(db):
    token = make_token(db, make_user(db))

    assert token.revoked_at is None
    assert token.created_at.tzinfo is not None


def test_a_user_can_have_many_refresh_tokens(db):
    user = make_user(db)
    make_token(db, user, token_hash="a")
    make_token(db, user, token_hash="b")

    assert db.query(RefreshToken).filter_by(user_id=user.id).count() == 2


def test_deleting_a_user_deletes_their_refresh_tokens(db):
    user = make_user(db)
    make_token(db, user, token_hash="a")
    make_token(db, user, token_hash="b")

    db.execute(text("DELETE FROM users"))
    db.commit()

    assert db.query(RefreshToken).count() == 0


def test_deleting_a_user_keeps_other_users_tokens(db):
    gone, kept = make_user(db, username="gone"), make_user(db, username="kept")
    make_token(db, gone, token_hash="a")
    make_token(db, kept, token_hash="b")

    db.execute(text("DELETE FROM users WHERE username = 'gone'"))
    db.commit()

    assert [t.token_hash for t in db.query(RefreshToken)] == ["b"]


def test_reader_model_is_still_importable_next_to_user():
    """The account tables must not change how readers are stored (the existing tables are untouched)."""
    assert Reader.__tablename__ == "readers"
