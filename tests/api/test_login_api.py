"""AUTH-004: POST /auth/login (acceptance criteria 1-6).

The most important property besides "valid credentials work" is that every kind of failure looks the same from the
outside, so the endpoint cannot be used to find out which logins exist.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth.tokens import decode_access_token
from app.main import app
from app.models import RefreshToken, User
from app.services import auth as auth_service
from tests.factories import make_user


@pytest.fixture
def client(anonymous_client):
    """These tests check sign-in, roles and access errors: they start WITHOUT a login."""
    return anonymous_client


PASSWORD = "correct horse"
FAILURE_BODY = {"detail": "Invalid username or password"}


def login(client, username="ann", password=PASSWORD, **kwargs):
    return client.post("/auth/login", json={"username": username, "password": password}, **kwargs)


def cookie_attributes(response) -> dict:
    """Set-Cookie header as {name: value} plus lower-cased flag names, for easy assertions."""
    parts = [part.strip() for part in response.headers["set-cookie"].split(";")]
    name, _, value = parts[0].partition("=")
    attributes = {"name": name, "value": value}
    for part in parts[1:]:
        key, _, val = part.partition("=")
        attributes[key.lower()] = val
    return attributes


@pytest.fixture
def user(db):
    return make_user(db, role="librarian", username="ann", password=PASSWORD)


# ---------- criterion 1: success ----------


def test_valid_credentials_return_200_and_an_access_token(client, user):
    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60


def test_access_token_identifies_the_user(client, user):
    token = login(client).json()["access_token"]

    claims = decode_access_token(token)

    assert claims.user_id == user.id
    assert claims.role == "librarian"


def test_response_never_contains_the_password_or_its_hash(client, user):
    response = login(client)

    assert PASSWORD not in response.text
    assert user.password_hash not in response.text


def test_refresh_token_arrives_in_a_protected_cookie(client, user):
    response = login(client)

    cookie = cookie_attributes(response)
    assert cookie["name"] == "refresh_token"
    assert len(cookie["value"]) >= 43
    assert "httponly" in cookie  # JavaScript on the page cannot read it
    assert cookie["samesite"].lower() == "lax"
    assert cookie["path"] == "/auth"
    assert cookie["max-age"] == str(7 * 24 * 3600)
    assert "secure" not in cookie  # plain HTTP (local development)


def test_cookie_is_secure_over_https(client, user):
    """Behind a proxy that terminates TLS, the original scheme arrives in X-Forwarded-Proto."""
    response = login(client, headers={"X-Forwarded-Proto": "https"})

    assert "secure" in cookie_attributes(response)


def test_cookie_path_follows_the_public_prefix(db, user):
    """Behind nginx the API is visible under /api, so the cookie must be sent to /api/auth/..."""
    prefixed = TestClient(app, root_path="/api")

    response = login(prefixed)

    assert cookie_attributes(response)["path"] == "/api/auth"


def test_only_the_hash_of_the_refresh_token_is_stored(client, user, db):
    response = login(client)

    cookie_token = cookie_attributes(response)["value"]
    row = db.query(RefreshToken).one()
    assert row.user_id == user.id
    assert row.token_hash == hashlib.sha256(cookie_token.encode()).hexdigest()
    assert row.token_hash != cookie_token
    assert row.revoked_at is None
    assert row.expires_at - datetime.now(UTC) > timedelta(days=6, hours=23)


def test_each_login_gets_its_own_refresh_token(client, user, db):
    first = cookie_attributes(login(client))["value"]
    second = cookie_attributes(login(client))["value"]

    assert first != second
    assert db.query(RefreshToken).count() == 2


def test_successful_login_updates_last_login_time(client, user, db):
    assert user.last_login_at is None

    login(client)

    db.refresh(user)
    assert user.last_login_at is not None
    assert datetime.now(UTC) - user.last_login_at < timedelta(minutes=1)


# ---------- criteria 2-4: every failure looks the same ----------


def failure_cases(db):
    make_user(db, role="reader", username="off", password=PASSWORD, active=False)
    return [
        ("ann", "wrong password"),  # wrong password
        ("nobody", PASSWORD),  # unknown login
        ("off", PASSWORD),  # disabled user, right password
    ]


def test_wrong_password_unknown_login_and_disabled_user_are_indistinguishable(client, user, db):
    responses = [login(client, name, password) for name, password in failure_cases(db)]

    assert [r.status_code for r in responses] == [401, 401, 401]
    assert [r.json() for r in responses] == [FAILURE_BODY] * 3
    assert len({r.headers["content-type"] for r in responses}) == 1


def test_failed_login_sets_no_cookie_and_creates_no_session(client, user, db):
    for name, password in failure_cases(db):
        response = login(client, name, password)
        assert "set-cookie" not in response.headers

    assert db.query(RefreshToken).count() == 0


def test_failed_login_does_not_update_last_login_time(client, user, db):
    login(client, "ann", "wrong password")

    db.refresh(user)
    assert user.last_login_at is None


def test_password_is_checked_in_every_failure_case(client, user, db, monkeypatch):
    """The time of the answer must not reveal whether the login exists. The costly password check therefore runs
    in all three failure cases (for an unknown login against a dummy hash), exactly once each."""
    calls = []
    real = auth_service.verify_password
    monkeypatch.setattr(auth_service, "verify_password", lambda p, h: calls.append(h) or real(p, h))

    for name, password in failure_cases(db):
        calls.clear()
        login(client, name, password)
        assert len(calls) == 1, f"{name}: password check ran {len(calls)} times"


# ---------- criterion 5: invalid input ----------


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "", "password": PASSWORD},
        {"username": "ann", "password": ""},
        {"username": "a" * 65, "password": PASSWORD},
        {"username": "ann", "password": "p" * 129},
        {"password": PASSWORD},
        {"username": "ann"},
        {},
        {"username": 123, "password": PASSWORD},
        {"username": "ann", "password": 12345678},
        {"username": None, "password": None},
        {"username": "a\u0000b", "password": PASSWORD},
    ],
    ids=[
        "empty username",
        "empty password",
        "username too long",
        "password too long",
        "no username",
        "no password",
        "empty body",
        "numeric username",
        "numeric password",
        "nulls",
        "NUL character in username",
    ],
)
def test_invalid_input_returns_422(client, payload):
    assert client.post("/auth/login", json=payload).status_code == 422


def test_validation_error_does_not_echo_the_password_back(client):
    """FastAPI normally returns the rejected input inside the error. For a login form that would copy a password
    into the response (and into any log that records responses)."""
    secret_password = "p" * 129

    response = client.post("/auth/login", json={"username": "ann", "password": secret_password})

    assert response.status_code == 422
    assert secret_password not in response.text


def test_body_that_is_not_json_is_rejected_cleanly(client):
    response = client.post(
        "/auth/login", content=b"username=ann", headers={"Content-Type": "text/plain"}
    )

    assert response.status_code == 422


# ---------- criterion 6: the login is case-insensitive ----------


@pytest.mark.parametrize("typed", ["ann", "ANN", "Ann", "aNn"])
def test_login_is_case_insensitive(client, user, typed):
    assert login(client, typed).status_code == 200


def test_login_is_matched_as_a_whole(client, user):
    assert login(client, "ann ").status_code == 401  # trailing space is a different login
    assert login(client, "an").status_code == 401


def test_password_is_case_sensitive(client, user):
    assert login(client, "ann", "Correct Horse").status_code == 401


# ---------- the account is not harmed by repeated attempts here ----------


def test_user_row_is_unchanged_by_failures(client, user, db):
    before = (user.username, user.password_hash, user.is_active, user.role)

    login(client, "ann", "nope")

    db.refresh(user)
    assert (user.username, user.password_hash, user.is_active, user.role) == before
    assert db.query(User).count() == 1
