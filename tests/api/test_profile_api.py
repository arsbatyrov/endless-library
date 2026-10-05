"""AUTH-006: GET /auth/me and POST /auth/password (acceptance criteria 1-4).

Also covers the bearer-token dependency that both endpoints use (missing, malformed, expired, disabled user).
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.passwords import verify_password
from app.auth.refresh_tokens import issue_refresh_token
from app.auth.tokens import create_access_token
from app.models import RefreshToken, User
from tests.factories import make_user


@pytest.fixture
def client(anonymous_client):
    """These tests check sign-in, roles and access errors: they start WITHOUT a login."""
    return anonymous_client


PASSWORD = "correct horse"
NEW_PASSWORD = "battery staple"


def bearer(user: User, **kwargs) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role, **kwargs)}"}


def change(client, headers, current=PASSWORD, new=NEW_PASSWORD):
    return client.post(
        "/auth/password", headers=headers, json={"current_password": current, "new_password": new}
    )


@pytest.fixture
def user(db):
    return make_user(db, role="librarian", username="ann", password=PASSWORD)


# ---------- criterion 1: profile ----------


def test_me_returns_login_role_and_reader_link(client, user):
    response = client.get("/auth/me", headers=bearer(user))

    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "username": "ann",
        "role": "librarian",
        "reader_id": None,
    }


def test_me_of_a_reader_includes_the_reader_card(client, db):
    reader_user = make_user(db, role="reader", username="rita", password=PASSWORD)

    response = client.get("/auth/me", headers=bearer(reader_user))

    assert response.json()["reader_id"] == reader_user.reader_id
    assert response.json()["reader_id"] is not None


def test_me_never_contains_the_password_hash(client, user):
    response = client.get("/auth/me", headers=bearer(user))

    assert user.password_hash not in response.text
    assert "password" not in response.text.lower()


def test_me_shows_the_role_from_the_database_not_from_the_token(client, db, user):
    headers = bearer(user)
    user.role = "admin"
    db.commit()

    assert client.get("/auth/me", headers=headers).json()["role"] == "admin"


# ---------- bearer token handling (shared dependency) ----------


def test_no_token_is_401_with_a_bearer_challenge(client):
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Bearer ", "Basic abc", "bearer", "Token abc", "Bearer a b", "Bearer not.a.jwt"],
)
def test_malformed_authorization_header_is_401(client, header):
    response = client.get("/auth/me", headers={"Authorization": header})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_expired_token_is_401(client, user):
    headers = bearer(user, now=datetime.now(UTC) - timedelta(minutes=16))

    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_token_signed_with_another_secret_is_401(client, user):
    forged = jwt.encode(
        {"sub": str(user.id), "role": "admin", "iat": 1, "exp": 4102444800, "jti": "x"},
        "some-other-secret-that-is-long-enough-0123456789",
        algorithm="HS256",
    )

    assert client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_token_of_a_deleted_user_is_401(client, db, user):
    headers = bearer(user)
    db.delete(user)
    db.commit()

    assert client.get("/auth/me", headers=headers).status_code == 401


def test_token_of_a_disabled_user_is_401_at_once(client, db, user):
    headers = bearer(user)
    assert client.get("/auth/me", headers=headers).status_code == 200
    user.is_active = False
    db.commit()

    assert client.get("/auth/me", headers=headers).status_code == 401


def test_all_token_failures_have_the_same_body(client, user):
    missing = client.get("/auth/me")
    garbage = client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    expired = client.get(
        "/auth/me", headers=bearer(user, now=datetime.now(UTC) - timedelta(days=1))
    )

    assert len({missing.text, garbage.text, expired.text}) == 1


# ---------- criterion 2: successful change ----------


def test_change_returns_204_and_the_new_password_works(client, db, user):
    response = change(client, bearer(user))

    assert response.status_code == 204
    assert response.content == b""
    db.expire_all()
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert not verify_password(PASSWORD, user.password_hash)


def test_login_works_with_the_new_password_only(client, user):
    change(client, bearer(user))

    old = client.post("/auth/login", json={"username": "ann", "password": PASSWORD})
    new = client.post("/auth/login", json={"username": "ann", "password": NEW_PASSWORD})

    assert old.status_code == 401
    assert new.status_code == 200


def test_change_revokes_all_refresh_tokens_of_the_user(client, db, user):
    issue_refresh_token(db, user)
    issue_refresh_token(db, user)
    db.commit()

    change(client, bearer(user))

    db.expire_all()
    rows = db.query(RefreshToken).all()
    assert len(rows) == 2
    assert all(row.revoked_at is not None for row in rows)


def test_change_does_not_revoke_tokens_of_other_users(client, db, user):
    other = make_user(db, role="admin", username="bob", password=PASSWORD)
    issue_refresh_token(db, other)
    db.commit()

    change(client, bearer(user))

    db.expire_all()
    assert db.query(RefreshToken).filter_by(user_id=other.id).one().revoked_at is None


def test_refresh_cookie_stops_working_after_the_change(client, user):
    client.post("/auth/login", json={"username": "ann", "password": PASSWORD})
    token = client.post("/auth/refresh").json()["access_token"]

    change(client, {"Authorization": f"Bearer {token}"})

    assert client.post("/auth/refresh").status_code == 401


def test_change_clears_the_refresh_cookie(client, user):
    response = change(client, bearer(user))

    header = response.headers["set-cookie"].lower()
    assert header.startswith("refresh_token=")
    assert "path=/auth" in header


def test_change_with_a_password_of_the_maximum_length(client, user):
    assert change(client, bearer(user), new="x" * 128).status_code == 204


def test_change_with_a_password_of_the_minimum_length(client, user):
    assert change(client, bearer(user), new="x" * 8).status_code == 204


# ---------- criterion 3: wrong current password ----------


def test_wrong_current_password_is_401_and_nothing_changes(client, db, user):
    old_hash = user.password_hash
    issue_refresh_token(db, user)
    db.commit()

    response = change(client, bearer(user), current="wrong password")

    assert response.status_code == 401
    db.expire_all()
    assert user.password_hash == old_hash
    assert db.query(RefreshToken).one().revoked_at is None


def test_wrong_current_password_does_not_clear_the_cookie(client, user):
    response = change(client, bearer(user), current="wrong password")

    assert "set-cookie" not in response.headers


def test_wrong_current_password_error_does_not_echo_passwords(client, user):
    response = change(client, bearer(user), current="wrong password", new=NEW_PASSWORD)

    assert "wrong password" not in response.text
    assert NEW_PASSWORD not in response.text


# ---------- criterion 4: password policy ----------


@pytest.mark.parametrize("new", ["", "short", "1234567"])
def test_too_short_new_password_is_422(client, db, user, new):
    old_hash = user.password_hash

    response = change(client, bearer(user), new=new)

    assert response.status_code == 422
    db.expire_all()
    assert user.password_hash == old_hash


def test_new_password_equal_to_the_old_one_is_422(client, db, user):
    old_hash = user.password_hash

    response = change(client, bearer(user), new=PASSWORD)

    assert response.status_code == 422
    db.expire_all()
    assert user.password_hash == old_hash


def test_new_password_equal_to_the_login_ignoring_case_is_422(client, db):
    long_login = make_user(db, role="admin", username="administrator", password=PASSWORD)

    response = change(client, bearer(long_login), new="ADMINISTRATOR")

    assert response.status_code == 422


def test_overlong_new_password_is_422(client, user):
    assert change(client, bearer(user), new="x" * 129).status_code == 422


def test_policy_errors_do_not_echo_the_passwords(client, user):
    response = change(client, bearer(user), new="short")

    assert response.status_code == 422
    assert "short" not in response.text.replace("too short", "")
    assert PASSWORD not in response.text


def test_missing_fields_are_422(client, user):
    response = client.post(
        "/auth/password", headers=bearer(user), json={"current_password": PASSWORD}
    )

    assert response.status_code == 422
    assert PASSWORD not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {"current_password": 123, "new_password": NEW_PASSWORD},
        {"current_password": "", "new_password": NEW_PASSWORD},
    ],
)
def test_wrong_types_or_empty_current_password_are_422(client, user, payload):
    assert client.post("/auth/password", headers=bearer(user), json=payload).status_code == 422


def test_change_requires_a_token(client, user):
    response = client.post(
        "/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_a_user_can_change_only_their_own_password(client, db, user):
    other = make_user(db, role="admin", username="bob", password=PASSWORD)
    other_hash = other.password_hash

    change(client, bearer(user))

    db.expire_all()
    assert other.password_hash == other_hash
