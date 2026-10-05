"""AUTH-003, criterion 5: the server decides by the data in the database, not by what the token says.

A token is a snapshot made at login. Between login and the request the user may have been disabled or demoted;
the token must not keep old rights alive for its remaining 15 minutes.
"""

import pytest

from app.auth.tokens import TokenError, create_access_token, get_user_for_token
from tests.factories import make_user


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-not-for-production-0123456789abcdef")


def test_active_user_is_returned_for_a_valid_token(db):
    user = make_user(db, role="librarian")

    found = get_user_for_token(db, create_access_token(user.id, user.role))

    assert found.id == user.id


def test_role_is_taken_from_the_database_not_from_the_token(db):
    user = make_user(db, role="admin")
    token = create_access_token(user.id, "admin")  # the token says admin
    user.role = "librarian"  # ... but the user was demoted afterwards
    db.commit()

    found = get_user_for_token(db, token)

    assert found.role == "librarian"


def test_disabled_user_is_rejected_even_with_an_unexpired_token(db):
    user = make_user(db, role="reader")
    token = create_access_token(user.id, "reader")
    user.is_active = False
    db.commit()

    with pytest.raises(TokenError) as error:
        get_user_for_token(db, token)

    assert error.value.code == "user_inactive"


def test_token_of_a_deleted_user_is_rejected(db):
    user = make_user(db, role="librarian")
    token = create_access_token(user.id, "librarian")
    db.delete(user)
    db.commit()

    with pytest.raises(TokenError) as error:
        get_user_for_token(db, token)

    assert error.value.code == "user_not_found"


def test_invalid_token_is_rejected_before_the_database_is_asked(db):
    with pytest.raises(TokenError) as error:
        get_user_for_token(db, "not-a-token")

    assert error.value.code == "invalid"


def test_reenabled_user_gets_access_again(db):
    user = make_user(db, role="reader", active=False)
    token = create_access_token(user.id, "reader")
    with pytest.raises(TokenError):
        get_user_for_token(db, token)

    user.is_active = True
    db.commit()

    assert get_user_for_token(db, token).id == user.id
