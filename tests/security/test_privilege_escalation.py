"""AUTH-017, criteria 2 and 3: nobody can do more than their role allows, whatever they send.

Criterion 2 (reader): somebody else's loans (id substitution and path tricks), creating accounts, changing roles
(also their own), changing books, readers and loans: 403 every time.
Criterion 3 (librarian): creating a librarian or an admin, sending a higher role or extra fields while creating a
reader, touching staff accounts: refused, and the role is never raised.
"""

import json
from datetime import UTC, datetime

import pytest

from app.models import Book, Loan, Reader, User
from app.services import loans as loan_service
from tests.factories import make_book, make_reader, make_user
from tests.security.conftest import PASSWORD, auth

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
BOOK = {"title": "Dune", "author": "Frank Herbert", "total_copies": 1}
READER_BODY = {"name": "Ann Lee", "email": "ann@example.com"}


def account_body(**overrides) -> dict:
    body = {"username": "newbie", "password": PASSWORD, "role": "reader"}
    body.update(overrides)
    return body


def counts(db) -> tuple[int, int, int, int]:
    db.expire_all()
    return (
        db.query(Book).count(),
        db.query(Reader).count(),
        db.query(User).count(),
        db.query(Loan).count(),
    )


# ---------- criterion 2: the reader ----------


def test_a_reader_cannot_read_the_loans_of_any_other_card(
    client, db, reader_account, other_reader_card
):
    book = make_book(db, copies=5)
    loan_service.issue_book(db, book.id, other_reader_card.id, NOW)
    headers = auth(reader_account)

    for card_id in [other_reader_card.id, 999999, 0, 2**31 - 1] + list(range(1, 12)):
        if card_id == reader_account.reader_id:
            continue
        response = client.get(f"/readers/{card_id}/loans", headers=headers)
        assert response.status_code in (403, 422), (card_id, response.status_code)
        assert "book_id" not in response.text, card_id


def test_a_reader_can_read_only_their_own_loans(client, db, reader_account, other_reader_card):
    book = make_book(db, copies=5)
    mine = loan_service.issue_book(db, book.id, reader_account.reader_id, NOW)
    loan_service.issue_book(db, book.id, other_reader_card.id, NOW)

    response = client.get(
        f"/readers/{reader_account.reader_id}/loans", headers=auth(reader_account)
    )

    assert [loan["id"] for loan in response.json()] == [mine.id]


@pytest.mark.parametrize(
    "path_template",
    [
        "/readers/{other}/loans/",
        "//readers/{other}/loans",
        "/readers/{other}/loans?reader_id={own}",
        "/readers/{other}/loans?readerId={own}&id={own}",
        "/readers/{other}/../{own}/loans",
        "/readers/{own}%2f..%2f{other}/loans",
        "/readers/{other}/loans%00",
        "/readers/%{hex}/loans",
        "/readers/0{other}/loans",
        "/readers/{other}.0/loans",
        "/readers/{other};x/loans",
        "/readers/+{other}/loans",
        "/READERS/{other}/loans",
    ],
)
def test_path_tricks_do_not_expose_somebody_elses_loans(
    client, db, reader_account, other_reader_card, path_template
):
    book = make_book(db, copies=5)
    loan_service.issue_book(db, book.id, other_reader_card.id, NOW)
    path = path_template.format(
        other=other_reader_card.id,
        own=reader_account.reader_id,
        hex=f"{ord(str(other_reader_card.id)):x}",
    )

    response = client.get(path, headers=auth(reader_account), follow_redirects=True)

    assert response.status_code != 200 or response.json() == [], (path, response.status_code)
    assert "book_id" not in response.text


def test_extra_headers_cannot_pretend_to_be_another_reader(
    client, db, reader_account, other_reader_card
):
    book = make_book(db, copies=5)
    loan_service.issue_book(db, book.id, other_reader_card.id, NOW)
    headers = {
        **auth(reader_account),
        "X-Reader-Id": str(other_reader_card.id),
        "X-User-Id": "1",
        "X-Forwarded-User": "root",
        "X-Original-URL": f"/readers/{reader_account.reader_id}/loans",
    }

    response = client.get(f"/readers/{other_reader_card.id}/loans", headers=headers)

    assert response.status_code == 403


READER_FORBIDDEN = [
    ("POST", "/users", account_body(username="intruder", role="admin")),
    ("POST", "/users", account_body(username="intruder", role="reader")),
    ("GET", "/users", None),
    ("PATCH", "/users/{self}", {"role": "admin"}),
    ("PATCH", "/users/{self}", {"role": "librarian"}),
    ("PATCH", "/users/{self}", {"is_active": True}),
    ("PATCH", "/users/{admin}", {"is_active": False}),
    ("PATCH", "/users/{admin}", {"role": "reader"}),
    ("POST", "/users/{self}/reset-password", {"new_password": "attacker chosen"}),
    ("POST", "/users/{admin}/reset-password", {"new_password": "attacker chosen"}),
    ("POST", "/books", BOOK),
    ("PUT", "/books/{book}", BOOK),
    ("DELETE", "/books/{book}", None),
    ("GET", "/readers", None),
    ("POST", "/readers", READER_BODY),
    ("PUT", "/readers/{self_card}", READER_BODY),
    ("DELETE", "/readers/{self_card}", None),
    ("POST", "/loans", {"book_id": 1, "reader_id": 1}),
    ("POST", "/loans/1/return", None),
]


@pytest.mark.parametrize(("method", "path", "body"), READER_FORBIDDEN, ids=lambda v: str(v)[:40])
def test_a_reader_is_refused_everything_beyond_the_catalogue_and_their_loans(
    client, db, reader_account, admin, method, path, body
):
    book = make_book(db)
    path = path.format(
        self=reader_account.id, admin=admin.id, book=book.id, self_card=reader_account.reader_id
    )
    before = counts(db)

    response = client.request(method, path, json=body, headers=auth(reader_account))

    assert response.status_code == 403, response.text
    assert counts(db) == before
    db.expire_all()
    assert reader_account.role == "reader"
    assert admin.is_active and admin.role == "admin"


def test_a_reader_cannot_promote_themselves_in_any_way(client, db, reader_account):
    headers = auth(reader_account)

    attempts = [
        client.patch(f"/users/{reader_account.id}", json={"role": "admin"}, headers=headers),
        client.patch(
            f"/users/{reader_account.id}",
            json={"role": "librarian", "is_active": True},
            headers=headers,
        ),
        client.post(
            "/auth/password",
            json={"current_password": PASSWORD, "new_password": "battery staple", "role": "admin"},
            headers=headers,
        ),
    ]

    db.expire_all()
    assert reader_account.role == "reader"
    assert [a.status_code for a in attempts][:2] == [403, 403]


def test_a_reader_may_open_their_own_card_but_never_another(
    client, db, reader_account, other_reader_card
):
    headers = auth(reader_account)

    own = client.get(f"/readers/{reader_account.reader_id}", headers=headers)
    other = client.get(f"/readers/{other_reader_card.id}", headers=headers)

    assert own.status_code == 200 and own.json()["id"] == reader_account.reader_id
    assert other.status_code == 403 and "Somebody else" not in other.text


def test_the_catalogue_reads_remain_open_to_a_reader(client, db, reader_account):
    book = make_book(db)
    headers = auth(reader_account)

    assert client.get("/books", headers=headers).status_code == 200
    assert client.get(f"/books/{book.id}", headers=headers).status_code == 200
    assert client.get("/books/popular", headers=headers).status_code == 200


# ---------- criterion 3: the librarian ----------


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_a_librarian_cannot_create_staff(client, db, librarian, role):
    before = counts(db)

    response = client.post(
        "/users", json=account_body(username="staff", role=role), headers=auth(librarian)
    )

    assert response.status_code == 403
    assert counts(db) == before


def test_a_librarian_creating_a_reader_with_a_higher_role_in_the_body_is_refused(
    client, db, librarian
):
    card = make_reader(db)
    before = counts(db)

    response = client.post(
        "/users",
        json=account_body(username="sneaky", role="admin", reader_id=card.id),
        headers=auth(librarian),
    )

    assert response.status_code == 403
    assert counts(db) == before


def test_duplicate_json_keys_cannot_smuggle_a_role(client, db, librarian):
    """{"role":"reader","role":"admin"}: parsers differ on which one wins; the server must act on what it understood."""
    card = make_reader(db)
    raw = f'{{"username":"dupe","password":"{PASSWORD}","role":"reader","role":"admin","reader_id":{card.id}}}'

    response = client.post(
        "/users", content=raw, headers={**auth(librarian), "Content-Type": "application/json"}
    )

    db.expire_all()
    created = db.query(User).filter_by(username="dupe").one_or_none()
    assert created is None or created.role == "reader"
    assert response.status_code in (201, 403, 422)


def test_duplicate_json_keys_in_the_other_order_cannot_smuggle_a_role_either(client, db, librarian):
    card = make_reader(db)
    raw = f'{{"username":"dupe","password":"{PASSWORD}","role":"admin","role":"reader","reader_id":{card.id}}}'

    client.post(
        "/users", content=raw, headers={**auth(librarian), "Content-Type": "application/json"}
    )

    db.expire_all()
    created = db.query(User).filter_by(username="dupe").one_or_none()
    assert created is None or created.role == "reader"


@pytest.mark.parametrize(
    "extra",
    [
        {"is_admin": True},
        {"is_superuser": True},
        {"admin": True},
        {"permissions": ["*"]},
        {"is_active": False},
        {"id": 1},
        {"password_hash": "$argon2id$v=19$m=65536,t=3,p=4$AAAA$BBBB"},
        {"created_at": "2000-01-01T00:00:00Z"},
        {"last_login_at": "2000-01-01T00:00:00Z"},
        {"roles": ["admin"]},
        {"Role": "admin"},
        {"user": {"role": "admin"}},
        {"__proto__": {"role": "admin"}},
        {"constructor": {"role": "admin"}},
    ],
)
def test_extra_fields_cannot_raise_the_role_or_set_internal_values(client, db, librarian, extra):
    card = make_reader(db)

    response = client.post(
        "/users",
        json=account_body(username="mass", role="reader", reader_id=card.id, **extra),
        headers=auth(librarian),
    )

    db.expire_all()
    created = db.query(User).filter_by(username="mass").one_or_none()
    if created is not None:  # extra fields were ignored, never obeyed
        assert response.status_code == 201
        assert created.role == "reader"
        assert created.is_active is True
        assert created.id != 1
        assert (
            created.password_hash.startswith("$argon2id$") and "AAAA" not in created.password_hash
        )
        assert created.created_at.year >= 2024
        assert created.last_login_at is None
    else:
        assert response.status_code in (403, 422)


def test_a_role_in_a_different_case_or_type_is_not_understood_as_a_higher_one(
    client, db, librarian
):
    card = make_reader(db)

    for role in ("Admin", "ADMIN", " admin", "admin ", ["admin"], {"name": "admin"}, 1, True, None):
        response = client.post(
            "/users",
            json=account_body(username="casey", role=role, reader_id=card.id),
            headers=auth(librarian),
        )
        assert response.status_code in (403, 422), (role, response.status_code)

    db.expire_all()
    assert db.query(User).filter_by(username="casey").count() == 0


def test_a_librarian_cannot_promote_a_reader_or_themselves(client, db, librarian, reader_account):
    for target in (reader_account, librarian):
        response = client.patch(
            f"/users/{target.id}", json={"role": "admin"}, headers=auth(librarian)
        )
        assert response.status_code == 403

    db.expire_all()
    assert reader_account.role == "reader"
    assert librarian.role == "librarian"


def test_a_librarian_cannot_touch_staff_accounts(client, db, librarian, admin):
    other = make_user(db, role="librarian", username="lib2", password=PASSWORD)
    headers = auth(librarian)

    for target in (admin, other, librarian):
        assert (
            client.patch(
                f"/users/{target.id}", json={"is_active": False}, headers=headers
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/users/{target.id}/reset-password",
                json={"new_password": "attacker chosen"},
                headers=headers,
            ).status_code
            == 403
        )

    db.expire_all()
    assert admin.is_active and other.is_active and librarian.is_active


def test_a_librarian_cannot_take_over_an_admin_account_by_resetting_the_password(
    client, db, librarian, admin
):
    old_hash = admin.password_hash

    client.post(
        f"/users/{admin.id}/reset-password",
        json={"new_password": "attacker chosen"},
        headers=auth(librarian),
    )

    db.expire_all()
    assert admin.password_hash == old_hash
    assert (
        client.post(
            "/auth/login", json={"username": "root", "password": "attacker chosen"}
        ).status_code
        == 401
    )


def test_a_librarian_may_still_do_their_own_work(client, db, librarian):
    card = make_reader(db)

    response = client.post(
        "/users",
        json=account_body(username="legit", role="reader", reader_id=card.id),
        headers=auth(librarian),
    )

    assert response.status_code == 201
    assert response.json()["role"] == "reader"
    assert "password" not in json.dumps(response.json()).lower()
