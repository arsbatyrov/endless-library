"""AUTH-017, criterion 7: no password, hash or token ever appears where it must not.

A whole scripted session runs against the API (sign-in, failures of every kind, accounts created, listed, changed,
password changed and reset, refresh, logout, locked login) while EVERY response and EVERY log line is collected. Then
each secret is searched for everywhere.

Where each secret may legitimately appear:
- an access token: only in the body of a successful login or refresh (and in the request that uses it);
- a refresh token: only in the Set-Cookie header of a successful login or refresh;
- a password: only in the request that carries it;
- a password hash and the JWT secret: nowhere.
"""

import pytest

from app.auth.refresh_tokens import COOKIE_NAME, hash_refresh_token
from app.auth.tokens import (
    get_user_for_token,  # noqa: F401  (the token format the search relies on)
)
from app.main import app
from app.models import User
from tests.factories import make_reader, make_user
from tests.security.conftest import PASSWORD, secret

NEW_PASSWORD = "battery staple"
RESET_PASSWORD = "reset by the admin"
CREATED_PASSWORD = "created for the newcomer"


class Recorder:
    """Wraps the test client and remembers every response (body and headers) together with the request path."""

    def __init__(self, client):
        self.client = client
        self.responses: list = []

    def request(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        self.responses.append((method, path, response))
        return response

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def patch(self, path, **kwargs):
        return self.request("PATCH", path, **kwargs)


@pytest.fixture
def session(client, db, redis_cache):
    """Runs the scripted session and returns what it produced: the recorder, the issued secrets and the accounts."""
    make_user(db, role="admin", username="root", password=PASSWORD)
    librarian = make_user(db, role="librarian", username="lib", password=PASSWORD)
    make_user(db, role="reader", username="rita", password=PASSWORD)
    card = make_reader(db, name="Newcomer")
    web = Recorder(client)
    access_tokens: list[str] = []
    refresh_tokens: list[str] = []

    def sign_in(username, password=PASSWORD):
        client.cookies.clear()
        response = web.post("/auth/login", json={"username": username, "password": password})
        if response.status_code == 200:
            access_tokens.append(response.json()["access_token"])
            refresh_tokens.append(client.cookies.get(COOKIE_NAME))
        return response

    def headers(token):
        return {"Authorization": f"Bearer {token}"}

    # failures of every kind
    web.post("/auth/login", json={"username": "root", "password": "wrong guess one"})
    web.post("/auth/login", json={"username": "ghost", "password": "wrong guess two"})
    web.post("/auth/login", content=b"{", headers={"Content-Type": "application/json"})
    web.post(
        "/auth/login", content=bytes([255, 254]), headers={"Content-Type": "application/json"}
    )  # 400
    web.post("/auth/login", json={"username": "root"})
    web.get("/auth/me")
    web.get("/auth/me", headers=headers("not.a.token"))

    # the administrator works
    root = sign_in("root").json()["access_token"]
    web.get("/auth/me", headers=headers(root))
    web.post(
        "/users",
        json={
            "username": "newcomer",
            "password": CREATED_PASSWORD,
            "role": "reader",
            "reader_id": card.id,
        },
        headers=headers(root),
    )
    web.post(
        "/users",
        json={"username": "short", "password": "pw-short", "role": "librarian"},  # 8 chars, valid
        headers=headers(root),
    )
    web.post(
        "/users",
        json={"username": "x", "password": "tiny", "role": "librarian"},
        headers=headers(root),
    )  # 422
    web.post(
        "/users",
        json={"username": "root", "password": CREATED_PASSWORD, "role": "admin"},
        headers=headers(root),
    )  # 409
    listing = web.get("/users", headers=headers(root))
    web.patch(f"/users/{librarian.id}", json={"is_active": True}, headers=headers(root))
    web.post(
        f"/users/{librarian.id}/reset-password",
        json={"new_password": RESET_PASSWORD},
        headers=headers(root),
    )
    web.post(
        f"/users/{librarian.id}/reset-password",
        json={"new_password": "tiny"},
        headers=headers(root),
    )  # 422
    web.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=headers(root),
    )
    web.post(
        "/auth/password",
        json={"current_password": "wrong current", "new_password": NEW_PASSWORD},
        headers=headers(root),
    )

    # the librarian (with the reset password) refreshes, is refused something, signs out
    sign_in("lib", RESET_PASSWORD)
    web.post("/auth/refresh")
    web.post(
        "/users",
        json={"username": "evil", "password": "attackers choice", "role": "admin"},
        headers=headers(access_tokens[-1]),
    )
    web.get("/books", headers=headers(access_tokens[-1]))
    web.post("/auth/refresh", headers={"Origin": "https://evil.example"})
    old = client.cookies.get(COOKIE_NAME)
    web.post("/auth/refresh")
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, old, path="/auth")
    web.post("/auth/refresh")  # a replayed token: theft detected
    web.post("/auth/logout")

    # a locked login
    for _ in range(5):
        web.post("/auth/login", json={"username": "rita", "password": "locking attempt"})
    web.post("/auth/login", json={"username": "rita", "password": PASSWORD})

    # the places that describe the system
    web.get("/openapi.json")
    web.get("/metrics")
    web.get("/health")

    db.expire_all()
    hashes = [u.password_hash for u in db.query(User).all()]
    return {
        "web": web,
        "access": access_tokens,
        "refresh": refresh_tokens,
        "hashes": hashes,
        "listing": listing,
    }


def everything(session) -> list[tuple[str, str, str, str]]:
    """(label, path, body, all headers as text) of every response."""
    out = []
    for method, path, response in session["web"].responses:
        headers = "\n".join(f"{k}: {v}" for k, v in response.headers.items())
        out.append((f"{method} {path} -> {response.status_code}", path, response.text, headers))
    return out


def test_the_session_really_exercised_the_api(session):
    codes = {response.status_code for _, _, response in session["web"].responses}

    assert {200, 201, 204, 401, 403, 409, 422, 429} <= codes
    assert len(session["access"]) >= 2 and len(session["refresh"]) >= 2
    assert len(session["hashes"]) >= 5


def test_no_password_appears_in_any_response(session):
    for label, _, body, headers in everything(session):
        for password in (
            PASSWORD,
            NEW_PASSWORD,
            RESET_PASSWORD,
            CREATED_PASSWORD,
            "wrong guess",
            "attackers choice",
        ):
            assert password not in body, (label, password)
            assert password not in headers, (label, password)


def test_no_password_hash_appears_in_any_response(session):
    for label, _, body, headers in everything(session):
        assert "$argon2" not in body and "$argon2" not in headers, label
        for value in session["hashes"]:
            assert value not in body and value not in headers, label


def test_the_jwt_secret_appears_nowhere(session):
    key = secret()
    for label, _, body, headers in everything(session):
        assert key not in body and key not in headers, label


def test_an_access_token_appears_only_in_the_body_of_a_successful_login_or_refresh(session):
    allowed_paths = {"/auth/login", "/auth/refresh"}
    for label, path, body, headers in everything(session):
        for token in session["access"]:
            assert token not in headers, label
            if token in body:
                assert path in allowed_paths and "-> 200" in label, label


def test_a_refresh_token_appears_only_in_the_set_cookie_header(session):
    for label, _, body, headers in everything(session):
        for token in session["refresh"]:
            assert token not in body, label
            other_headers = "\n".join(
                line for line in headers.splitlines() if not line.lower().startswith("set-cookie:")
            )
            assert token not in other_headers, label


def test_a_refresh_token_hash_is_not_exposed_either(session):
    for label, _, body, headers in everything(session):
        for token in session["refresh"]:
            assert hash_refresh_token(token) not in body + headers, label


def test_a_failed_request_does_not_echo_the_submitted_secrets(session):
    for label, _, body, _ in everything(session):
        if "-> 4" in label:
            for text in ("wrong guess", "attackers choice", "tiny", "pw-short", "wrong current"):
                assert text not in body, label


def test_the_users_list_has_no_secret_field_at_all(session):
    for account in session["listing"].json():
        assert set(account) == {
            "id",
            "username",
            "role",
            "reader_id",
            "is_active",
            "created_at",
            "last_login_at",
        }


def test_the_log_of_a_session_contains_no_secret(client, db, json_logs, redis_cache):
    admin = make_user(db, role="admin", username="root", password=PASSWORD)
    make_user(db, role="reader", username="rita", password=PASSWORD)
    card = make_reader(db, name="Newcomer")
    client.post("/auth/login", json={"username": "root", "password": "wrong guess one"})
    response = client.post("/auth/login", json={"username": "root", "password": PASSWORD})
    access = response.json()["access_token"]
    refresh = client.cookies.get(COOKIE_NAME)
    headers = {"Authorization": f"Bearer {access}"}
    client.post(
        "/users",
        json={
            "username": "newcomer",
            "password": CREATED_PASSWORD,
            "role": "reader",
            "reader_id": card.id,
        },
        headers=headers,
    )
    client.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=headers,
    )
    client.post("/auth/refresh")
    client.post("/auth/logout")
    for _ in range(5):
        client.post("/auth/login", json={"username": "rita", "password": "locking attempt"})
    client.get("/auth/me", headers=headers)
    db.expire_all()
    log = json_logs.raw()

    secrets_to_check = [
        PASSWORD,
        NEW_PASSWORD,
        CREATED_PASSWORD,
        "wrong guess",
        "locking attempt",
        access,
        refresh,
        hash_refresh_token(refresh),
        admin.password_hash,
        "$argon2",
        secret(),
    ]
    for value in secrets_to_check:
        assert value not in log, value
    assert "Bearer" not in log and "authorization" not in log.lower()
    assert "set-cookie" not in log.lower()


def test_the_documentation_of_the_api_describes_no_secret_value(client):
    text = client.get("/openapi.json").text

    assert secret() not in text
    assert PASSWORD not in text
    assert "$argon2" not in text
    assert app.title in text
