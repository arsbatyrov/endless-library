"""AUTH-008: a reader sees only their own loans (acceptance criteria 1-4).

A reader account is linked to a reader card (`reader_id`). The only reader-visible data besides the catalogue is the
list of active loans of that same card.
"""

from datetime import UTC, datetime

import pytest

from app.auth.tokens import create_access_token
from app.models import Reader
from app.services import loans as loan_service
from tests.factories import make_book, make_reader, make_user


@pytest.fixture
def client(anonymous_client):
    """These tests check sign-in, roles and access errors: they start WITHOUT a login."""
    return anonymous_client


NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def headers_for(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture
def card(db):
    return make_reader(db, name="Own card")


@pytest.fixture
def other_card(db):
    return make_reader(db, name="Someone else")


@pytest.fixture
def reader_user(db, card):
    return make_user(db, role="reader", reader=card)


# ---------- criterion 1: own loans ----------


def test_reader_sees_own_active_loans(client, db, card, reader_user):
    book = make_book(db, copies=2)
    loan = loan_service.issue_book(db, book.id, card.id, NOW)

    response = client.get(f"/readers/{card.id}/loans", headers=headers_for(reader_user))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [loan.id]
    assert response.json()[0]["reader_id"] == card.id


def test_reader_without_loans_gets_an_empty_list(client, card, reader_user):
    response = client.get(f"/readers/{card.id}/loans", headers=headers_for(reader_user))

    assert response.status_code == 200
    assert response.json() == []


def test_returned_loans_are_not_listed(client, db, card, reader_user):
    book = make_book(db, copies=2)
    returned = loan_service.issue_book(db, book.id, card.id, NOW)
    loan_service.return_book(db, returned.id, NOW)
    active = loan_service.issue_book(db, book.id, card.id, NOW)

    response = client.get(f"/readers/{card.id}/loans", headers=headers_for(reader_user))

    assert [item["id"] for item in response.json()] == [active.id]


def test_loans_of_other_readers_never_appear_in_the_list(client, db, card, other_card, reader_user):
    book = make_book(db, copies=3)
    mine = loan_service.issue_book(db, book.id, card.id, NOW)
    loan_service.issue_book(db, book.id, other_card.id, NOW)

    response = client.get(f"/readers/{card.id}/loans", headers=headers_for(reader_user))

    assert [item["id"] for item in response.json()] == [mine.id]


# ---------- criterion 2: somebody else's card ----------


def test_other_readers_loans_are_403(client, db, other_card, reader_user):
    book = make_book(db)
    loan_service.issue_book(db, book.id, other_card.id, NOW)

    response = client.get(f"/readers/{other_card.id}/loans", headers=headers_for(reader_user))

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}


def test_a_card_that_does_not_exist_is_403_not_404(client, reader_user):
    """A reader must not be able to find out which card numbers exist."""
    response = client.get("/readers/999999/loans", headers=headers_for(reader_user))

    assert response.status_code == 403


def test_existing_and_missing_foreign_cards_look_the_same(client, other_card, reader_user):
    existing = client.get(f"/readers/{other_card.id}/loans", headers=headers_for(reader_user))
    missing = client.get("/readers/999999/loans", headers=headers_for(reader_user))

    assert (existing.status_code, existing.text) == (missing.status_code, missing.text)


def test_two_readers_cannot_see_each_others_loans(client, db, card, other_card, reader_user):
    other_user = make_user(db, role="reader", reader=other_card)

    assert (
        client.get(f"/readers/{other_card.id}/loans", headers=headers_for(reader_user)).status_code
        == 403
    )
    assert (
        client.get(f"/readers/{card.id}/loans", headers=headers_for(other_user)).status_code == 403
    )
    assert (
        client.get(f"/readers/{card.id}/loans", headers=headers_for(reader_user)).status_code == 200
    )
    assert (
        client.get(f"/readers/{other_card.id}/loans", headers=headers_for(other_user)).status_code
        == 200
    )


def test_the_card_comes_from_the_database_not_from_the_token(
    client, db, card, other_card, reader_user
):
    """Re-linking the account to another card takes effect at once, with the same token."""
    headers = headers_for(reader_user)
    assert client.get(f"/readers/{card.id}/loans", headers=headers).status_code == 200

    reader_user.reader_id = other_card.id
    db.commit()

    assert client.get(f"/readers/{card.id}/loans", headers=headers).status_code == 403
    assert client.get(f"/readers/{other_card.id}/loans", headers=headers).status_code == 200


# ---------- criterion 3: the rest of the readers section ----------


def test_reader_cannot_list_all_readers(client, reader_user):
    assert client.get("/readers", headers=headers_for(reader_user)).status_code == 403


def test_reader_cannot_open_another_readers_card(client, other_card, reader_user):
    assert (
        client.get(f"/readers/{other_card.id}", headers=headers_for(reader_user)).status_code == 403
    )


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_reader_cannot_change_readers_even_their_own_card(client, db, card, reader_user, method):
    path = "/readers" if method == "POST" else f"/readers/{card.id}"
    body = {"name": "New name", "email": "new@example.com"} if method != "DELETE" else None

    response = client.request(method, path, json=body, headers=headers_for(reader_user))

    assert response.status_code == 403
    db.expire_all()
    assert db.get(Reader, card.id).name == "Own card"


def test_reader_cannot_issue_or_return_loans_for_themselves(client, db, card, reader_user):
    book = make_book(db)
    headers = headers_for(reader_user)

    assert (
        client.post(
            "/loans", json={"book_id": book.id, "reader_id": card.id}, headers=headers
        ).status_code
        == 403
    )
    loan = loan_service.issue_book(db, book.id, card.id, NOW)
    assert client.post(f"/loans/{loan.id}/return", headers=headers).status_code == 403


# ---------- criterion 4: staff ----------


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_staff_sees_loans_of_any_reader(client, db, card, other_card, role):
    staff = make_user(db, role=role)
    book = make_book(db, copies=2)
    first = loan_service.issue_book(db, book.id, card.id, NOW)
    second = loan_service.issue_book(db, book.id, other_card.id, NOW)

    one = client.get(f"/readers/{card.id}/loans", headers=headers_for(staff))
    two = client.get(f"/readers/{other_card.id}/loans", headers=headers_for(staff))

    assert [i["id"] for i in one.json()] == [first.id]
    assert [i["id"] for i in two.json()] == [second.id]


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_staff_gets_404_for_a_missing_card(client, db, role):
    staff = make_user(db, role=role)

    assert client.get("/readers/999999/loans", headers=headers_for(staff)).status_code == 404


# ---------- order of checks and the switch ----------


def test_no_token_is_401(client, card):
    response = client.get(f"/readers/{card.id}/loans")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_no_token_with_an_invalid_id_is_401_not_422(client):
    assert client.get("/readers/abc/loans").status_code == 401


def test_reader_with_an_invalid_id_gets_422_and_learns_nothing(client, reader_user):
    response = client.get("/readers/abc/loans", headers=headers_for(reader_user))

    assert response.status_code == 422


def test_disabled_reader_is_refused_at_once(client, db, card, reader_user):
    headers = headers_for(reader_user)
    reader_user.is_active = False
    db.commit()

    assert client.get(f"/readers/{card.id}/loans", headers=headers).status_code == 401


def test_reader_card_is_not_created_or_changed_by_reading(client, db, card, reader_user):
    before = db.query(Reader).count()

    client.get(f"/readers/{card.id}/loans", headers=headers_for(reader_user))

    assert db.query(Reader).count() == before
