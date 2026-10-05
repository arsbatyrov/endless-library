"""AUTH-007: existing endpoints are closed by login and by role (acceptance criteria 1-6).

Rules: no token or a bad token gives 401; reader may only read the catalogue (books list, one book, popular);
librarian and admin may do everything on books, readers and loans; health, readiness and the documentation stay open.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.tokens import create_access_token
from tests.factories import make_reader, make_user


@pytest.fixture
def client(anonymous_client):
    """These tests check sign-in, roles and access errors: they start WITHOUT a login."""
    return anonymous_client


BOOK = {"title": "Dune", "author": "Frank Herbert", "total_copies": 2}
READER = {"name": "Ann Lee", "email": "ann@example.com"}
LOAN = {"book_id": 1, "reader_id": 1}

# (method, path, json body). Ids do not need to exist: the check happens before the handler runs.
CATALOGUE_READS = [
    ("GET", "/books", None),
    ("GET", "/books/1", None),
    ("GET", "/books/popular", None),
]
BOOK_WRITES = [
    ("POST", "/books", BOOK),
    ("PUT", "/books/1", BOOK),
    ("DELETE", "/books/1", None),
]
READER_ENDPOINTS = [
    ("POST", "/readers", READER),
    ("GET", "/readers", None),
    ("GET", "/readers/1", None),
    ("GET", "/readers/1/loans", None),
    ("PUT", "/readers/1", READER),
    ("DELETE", "/readers/1", None),
]
LOAN_ENDPOINTS = [
    ("POST", "/loans", LOAN),
    ("POST", "/loans/1/return", None),
]
STAFF_ONLY = BOOK_WRITES + READER_ENDPOINTS + LOAN_ENDPOINTS
EVERYTHING = CATALOGUE_READS + STAFF_ONLY
OPEN_ENDPOINTS = ["/health", "/ready", "/docs", "/openapi.json"]


def ident(case):
    return f"{case[0]} {case[1]}"


def call(client, case, token=None):
    method, path, body = case
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, path, json=body, headers=headers)


def token_for(db, role):
    user = make_user(db, role=role)
    return create_access_token(user.id, user.role)


# ---------- criterion 1: no token ----------


@pytest.mark.parametrize("case", EVERYTHING, ids=ident)
def test_no_token_is_401_with_a_bearer_challenge(client, case):
    response = call(client, case)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_the_popular_route_that_only_answers_405_is_closed_too(client, db, method):
    assert client.request(method, "/books/popular").status_code == 401

    token = token_for(db, "admin")
    response = client.request(
        method, "/books/popular", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 405


@pytest.mark.parametrize(
    "case", [("POST", "/books", {"title": 1}), ("POST", "/readers", {}), ("POST", "/loans", {})]
)
def test_invalid_body_without_a_token_is_401_not_422(client, case):
    assert call(client, case).status_code == 401


def test_nothing_is_created_without_a_token(client, db):
    from app.models import Book

    call(client, ("POST", "/books", BOOK))

    assert db.query(Book).count() == 0


# ---------- criterion 2: bad tokens ----------


def test_expired_token_is_401(client, db):
    user = make_user(db, role="admin")
    token = create_access_token(user.id, user.role, now=datetime.now(UTC) - timedelta(minutes=16))

    assert call(client, ("GET", "/books", None), token).status_code == 401


def test_garbage_token_is_401(client):
    assert call(client, ("GET", "/books", None), "not.a.jwt").status_code == 401


def test_token_signed_with_another_secret_is_401(client, db):
    user = make_user(db, role="admin")
    forged = jwt.encode(
        {"sub": str(user.id), "role": "admin", "iat": 1, "exp": 4102444800, "jti": "x"},
        "some-other-secret-that-is-long-enough-0123456789",
        algorithm="HS256",
    )

    assert call(client, ("GET", "/books", None), forged).status_code == 401


def test_token_with_the_none_algorithm_is_401(client, db):
    user = make_user(db, role="admin")
    unsigned = jwt.encode(
        {"sub": str(user.id), "role": "admin", "iat": 1, "exp": 4102444800, "jti": "x"},
        None,
        algorithm="none",
    )

    assert call(client, ("GET", "/books", None), unsigned).status_code == 401


def test_a_token_cannot_raise_its_own_role(client, db):
    """The role inside the token is ignored: the database decides."""
    user = make_user(db, role="reader")
    from app.auth.config import load_jwt_secret

    claims = {
        "sub": str(user.id),
        "role": "admin",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": 4102444800,
        "jti": "x",
    }
    token = jwt.encode(claims, load_jwt_secret(), algorithm="HS256")

    assert call(client, ("POST", "/books", BOOK), token).status_code == 403


# ---------- criterion 3: reader ----------


@pytest.mark.parametrize("case", CATALOGUE_READS, ids=ident)
def test_reader_may_read_the_catalogue(client, db, case):
    response = call(client, case, token_for(db, "reader"))

    assert response.status_code not in (401, 403)


# The exceptions: a reader may open their OWN card and its loans (AUTH-008, AUTH-019). The test reader owns card 1.
NOT_FOR_READERS = [
    case
    for case in STAFF_ONLY
    if case[:2] not in (("GET", "/readers/1"), ("GET", "/readers/1/loans"))
]


@pytest.mark.parametrize("case", NOT_FOR_READERS, ids=ident)
def test_reader_is_forbidden_everywhere_else(client, db, case):
    response = call(client, case, token_for(db, "reader"))

    assert response.status_code == 403
    assert "www-authenticate" not in response.headers


def test_forbidden_does_not_run_the_handler(client, db):
    from app.models import Book

    call(client, ("POST", "/books", BOOK), token_for(db, "reader"))

    assert db.query(Book).count() == 0


def test_invalid_body_from_a_reader_is_403_not_422(client, db):
    assert (
        call(client, ("POST", "/books", {"title": 1}), token_for(db, "reader")).status_code == 403
    )


def test_reader_actually_receives_the_catalogue(client, db):
    admin = token_for(db, "admin")
    call(client, ("POST", "/books", BOOK), admin)

    response = call(client, ("GET", "/books", None), token_for(db, "reader"))

    assert response.status_code == 200
    assert [b["title"] for b in response.json()] == ["Dune"]


def test_forbidden_and_unauthorized_have_different_bodies(client, db):
    forbidden = call(client, ("POST", "/books", BOOK), token_for(db, "reader"))
    unauthorized = call(client, ("POST", "/books", BOOK))

    assert forbidden.json() != unauthorized.json()


# ---------- criterion 4: librarian and admin ----------


@pytest.mark.parametrize("role", ["librarian", "admin"])
@pytest.mark.parametrize("case", EVERYTHING, ids=ident)
def test_staff_is_allowed_everywhere(client, db, role, case):
    response = call(client, case, token_for(db, role))

    assert response.status_code not in (401, 403)


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_staff_can_really_create_a_book_and_a_reader(client, db, role):
    token = token_for(db, role)

    assert call(client, ("POST", "/books", BOOK), token).status_code == 201
    assert call(client, ("POST", "/readers", READER), token).status_code == 201


# ---------- criterion 5: disabled after the token was issued ----------


def test_disabled_user_is_refused_at_once(client, db):
    user = make_user(db, role="admin")
    token = create_access_token(user.id, user.role)
    assert call(client, ("GET", "/books", None), token).status_code == 200

    user.is_active = False
    db.commit()

    assert call(client, ("GET", "/books", None), token).status_code == 401


def test_demoted_user_loses_the_rights_at_once(client, db):
    user = make_user(db, role="admin")
    token = create_access_token(user.id, user.role)
    assert call(client, ("POST", "/books", BOOK), token).status_code == 201

    reader_card = make_reader(db)  # a reader account must be linked to a reader card
    user.role = "reader"
    user.reader_id = reader_card.id
    db.commit()

    assert call(client, ("POST", "/books", BOOK), token).status_code == 403


# ---------- criterion 6: open endpoints ----------


@pytest.mark.parametrize("path", OPEN_ENDPOINTS)
def test_health_readiness_and_docs_need_no_token(client, path):
    response = client.get(path)

    assert response.status_code not in (401, 403)


def test_open_endpoints_also_work_with_a_bad_token(client):
    response = client.get("/health", headers={"Authorization": "Bearer garbage"})

    assert response.status_code == 200


# ---------- there is no way to switch the protection off ----------


@pytest.mark.parametrize("value", ["false", "0", "off", "no", ""])
def test_no_environment_variable_opens_the_endpoints(client, monkeypatch, value):
    monkeypatch.setenv("AUTH_REQUIRED", value)

    assert client.get("/books").status_code == 401
    assert client.get("/readers").status_code == 401
    assert client.post("/loans", json=LOAN).status_code == 401
