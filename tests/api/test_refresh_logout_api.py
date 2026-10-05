"""AUTH-005: POST /auth/refresh and POST /auth/logout (acceptance criteria 1-5).

A refresh token is a password for 7 days, so the interesting properties are: it works once (rotation), reusing an
old one is treated as theft, and logout really ends access.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.auth.refresh_tokens import COOKIE_NAME, hash_refresh_token
from app.auth.tokens import decode_access_token
from app.models import RefreshToken
from tests.factories import make_user


@pytest.fixture
def client(anonymous_client):
    """These tests check sign-in, roles and access errors: they start WITHOUT a login."""
    return anonymous_client


PASSWORD = "correct horse"


def login(client, username="ann"):
    response = client.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return response


def current_token(client) -> str:
    return client.cookies.get(COOKIE_NAME)


def set_token(client, token: str):
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, token, path="/auth")


def clears_cookie(response) -> bool:
    header = response.headers.get("set-cookie", "")
    return header.startswith(f"{COOKIE_NAME}=") and (
        "Max-Age=0" in header or "expires=" in header.lower()
    )


def row_for(db, token: str) -> RefreshToken:
    db.expire_all()
    return db.query(RefreshToken).filter_by(token_hash=hash_refresh_token(token)).one()


@pytest.fixture
def user(db):
    return make_user(db, role="librarian", username="ann", password=PASSWORD)


# ---------- criterion 1: rotation ----------


def test_refresh_returns_a_new_access_token_and_a_new_cookie(client, user):
    login(client)
    old_token = current_token(client)

    response = client.post("/auth/refresh")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}
    assert body["expires_in"] == 15 * 60
    assert decode_access_token(body["access_token"]).user_id == user.id
    assert current_token(client) not in (None, old_token)


def test_new_cookie_keeps_the_protective_attributes(client, user):
    login(client)

    header = client.post("/auth/refresh").headers["set-cookie"].lower()

    assert "httponly" in header
    assert "samesite=lax" in header
    assert "path=/auth" in header
    assert f"max-age={7 * 24 * 3600}" in header


def test_old_token_is_revoked_and_new_one_is_stored_as_a_hash(client, db, user):
    login(client)
    old_token = current_token(client)

    client.post("/auth/refresh")

    new_token = current_token(client)
    assert row_for(db, old_token).revoked_at is not None
    new_row = row_for(db, new_token)
    assert new_row.revoked_at is None
    assert new_row.user_id == user.id
    assert new_token not in new_row.token_hash


def test_a_chain_of_refreshes_keeps_working(client, user):
    login(client)

    for _ in range(3):
        assert client.post("/auth/refresh").status_code == 200


def test_refresh_does_not_extend_the_old_token_in_place(client, db, user):
    login(client)
    old_token = current_token(client)
    old_expiry = row_for(db, old_token).expires_at

    client.post("/auth/refresh")

    assert row_for(db, old_token).expires_at == old_expiry


# ---------- criterion 2: reuse of a replaced token = theft ----------


def test_replaced_token_is_rejected(client, user):
    login(client)
    old_token = current_token(client)
    client.post("/auth/refresh")

    set_token(client, old_token)
    response = client.post("/auth/refresh")

    assert response.status_code == 401
    assert clears_cookie(response)


def test_reuse_revokes_every_token_of_that_user(client, db, user):
    login(client)
    stolen = current_token(client)
    client.post("/auth/refresh")
    legitimate = current_token(client)

    set_token(client, stolen)
    client.post("/auth/refresh")

    assert row_for(db, legitimate).revoked_at is not None
    set_token(client, legitimate)
    assert client.post("/auth/refresh").status_code == 401


def test_reuse_does_not_touch_other_users(client, db, user):
    other = make_user(db, role="admin", username="bob", password=PASSWORD)
    client.post("/auth/login", json={"username": "bob", "password": PASSWORD})
    bobs_token = current_token(client)
    client.cookies.clear()
    login(client)
    stolen = current_token(client)
    client.post("/auth/refresh")

    set_token(client, stolen)
    client.post("/auth/refresh")

    assert row_for(db, bobs_token).revoked_at is None
    assert row_for(db, bobs_token).user_id == other.id


# ---------- criterion 3: missing, unknown, expired ----------


def test_missing_cookie_is_401(client, user):
    response = client.post("/auth/refresh")

    assert response.status_code == 401
    assert clears_cookie(response)


def test_unknown_token_is_401(client, user):
    set_token(client, "not-a-token-we-issued")

    response = client.post("/auth/refresh")

    assert response.status_code == 401
    assert clears_cookie(response)


def test_empty_cookie_is_401(client, user):
    set_token(client, "")

    assert client.post("/auth/refresh").status_code == 401


def test_expired_token_is_401(client, db, user):
    login(client)
    token = current_token(client)
    row = row_for(db, token)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    response = client.post("/auth/refresh")

    assert response.status_code == 401
    assert clears_cookie(response)


def test_token_expiring_in_the_future_still_works(client, db, user):
    login(client)
    row = row_for(db, current_token(client))
    row.expires_at = datetime.now(UTC) + timedelta(seconds=30)
    db.commit()

    assert client.post("/auth/refresh").status_code == 200


def test_all_refresh_failures_look_the_same(client, db, user):
    """Missing, unknown and expired tokens give the same status and body."""
    bodies = []

    bodies.append(client.post("/auth/refresh"))
    set_token(client, "garbage")
    bodies.append(client.post("/auth/refresh"))
    client.cookies.clear()
    login(client)
    row = row_for(db, current_token(client))
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    db.commit()
    bodies.append(client.post("/auth/refresh"))

    assert {r.status_code for r in bodies} == {401}
    assert len({r.text for r in bodies}) == 1


# ---------- criterion 5: disabled user ----------


def test_disabled_user_cannot_refresh(client, db, user):
    login(client)
    user.is_active = False
    db.commit()

    response = client.post("/auth/refresh")

    assert response.status_code == 401
    assert clears_cookie(response)


def test_disabled_user_gets_no_new_token_row(client, db, user):
    login(client)
    user.is_active = False
    db.commit()

    client.post("/auth/refresh")

    assert db.query(RefreshToken).count() == 1


def test_role_in_the_new_access_token_comes_from_the_database(client, db, user):
    login(client)
    user.role = "admin"
    db.commit()

    token = client.post("/auth/refresh").json()["access_token"]

    assert decode_access_token(token).role == "admin"


# ---------- criterion 4: logout ----------


def test_logout_returns_204_revokes_the_token_and_clears_the_cookie(client, db, user):
    login(client)
    token = current_token(client)

    response = client.post("/auth/logout")

    assert response.status_code == 204
    assert response.content == b""
    assert clears_cookie(response)
    assert row_for(db, token).revoked_at is not None


def test_token_does_not_work_after_logout(client, user):
    login(client)
    token = current_token(client)
    client.post("/auth/logout")

    set_token(client, token)

    assert client.post("/auth/refresh").status_code == 401


def test_logout_twice_is_still_204(client, user):
    login(client)
    token = current_token(client)
    client.post("/auth/logout")

    set_token(client, token)

    assert client.post("/auth/logout").status_code == 204


def test_logout_without_a_cookie_is_204(client):
    response = client.post("/auth/logout")

    assert response.status_code == 204
    assert clears_cookie(response)


def test_logout_with_an_unknown_token_is_204(client):
    set_token(client, "garbage")

    assert client.post("/auth/logout").status_code == 204


def test_logout_ends_only_the_current_session(client, db, user):
    login(client)
    first = current_token(client)
    client.cookies.clear()
    login(client)
    second = current_token(client)

    client.post("/auth/logout")

    assert row_for(db, second).revoked_at is not None
    assert row_for(db, first).revoked_at is None


def test_logout_keeps_the_original_revocation_time(client, db, user):
    login(client)
    token = current_token(client)
    client.post("/auth/logout")
    first_time = row_for(db, token).revoked_at

    set_token(client, token)
    client.post("/auth/logout")

    assert row_for(db, token).revoked_at == first_time


def test_logout_of_a_replaced_token_does_not_revoke_other_tokens(client, db, user):
    """Unlike refresh, logout with an old token is harmless: it must not be treated as theft."""
    login(client)
    old = current_token(client)
    client.post("/auth/refresh")
    new = current_token(client)

    set_token(client, old)
    client.post("/auth/logout")

    assert row_for(db, new).revoked_at is None


# ---------- cookie path behind the proxy ----------


def test_cleared_cookie_uses_the_same_path_as_the_issued_one(client, user):
    """A cookie is deleted only when the path matches the one it was set with."""
    login(client)

    header = client.post("/auth/logout").headers["set-cookie"].lower()

    assert "path=/auth" in header
    assert "httponly" in header


def test_cleared_cookie_follows_the_public_prefix(db, user):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app, root_path="/api") as proxied:
            header = proxied.post("/auth/logout").headers["set-cookie"].lower()
    finally:
        app.dependency_overrides.clear()

    assert "path=/api/auth" in header


# ---------- the endpoints do not leak or accept input ----------


def test_refresh_ignores_a_request_body(client, user):
    login(client)

    assert client.post("/auth/refresh", json={"refresh_token": "x"}).status_code == 200


def test_responses_never_contain_the_token_or_its_hash(client, user):
    login(client)
    token = current_token(client)

    response = client.post("/auth/refresh")

    assert token not in response.text
    assert hash_refresh_token(token) not in response.text
