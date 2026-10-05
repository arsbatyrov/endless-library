"""AUTH-019: a reader can open their own reader card (and only their own).

Same rule as the loans of a card (AUTH-008): the link between the account and the card is read from the database;
another card gives 403 whether or not it exists, so card numbers cannot be probed.
"""

import pytest

from app.auth.tokens import create_access_token
from app.models import Reader
from tests.factories import make_reader, make_user


@pytest.fixture
def client(anonymous_client):
    """These tests check access rules: they start WITHOUT a login."""
    return anonymous_client


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


# ---------- criterion 1: the own card ----------


def test_reader_opens_their_own_card(client, card, reader_user):
    response = client.get(f"/readers/{card.id}", headers=headers_for(reader_user))

    assert response.status_code == 200
    assert response.json() == {"id": card.id, "name": "Own card", "email": card.email}


def test_the_answer_is_the_same_as_staff_gets(client, db, card, reader_user):
    staff = make_user(db, role="librarian")

    own = client.get(f"/readers/{card.id}", headers=headers_for(reader_user))
    seen_by_staff = client.get(f"/readers/{card.id}", headers=headers_for(staff))

    assert own.json() == seen_by_staff.json()


def test_the_card_comes_from_the_database_not_from_the_token(
    client, db, card, other_card, reader_user
):
    headers = headers_for(reader_user)
    assert client.get(f"/readers/{card.id}", headers=headers).status_code == 200

    reader_user.reader_id = other_card.id
    db.commit()

    assert client.get(f"/readers/{card.id}", headers=headers).status_code == 403
    assert client.get(f"/readers/{other_card.id}", headers=headers).status_code == 200


# ---------- criterion 2: other cards ----------


def test_another_card_is_403(client, other_card, reader_user):
    response = client.get(f"/readers/{other_card.id}", headers=headers_for(reader_user))

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}
    assert "Someone else" not in response.text


def test_a_missing_card_looks_the_same_as_an_existing_foreign_one(client, other_card, reader_user):
    existing = client.get(f"/readers/{other_card.id}", headers=headers_for(reader_user))
    missing = client.get("/readers/999999", headers=headers_for(reader_user))

    assert (existing.status_code, existing.text) == (missing.status_code, missing.text)


def test_two_readers_cannot_open_each_others_cards(client, db, card, other_card, reader_user):
    other_user = make_user(db, role="reader", reader=other_card)

    assert (
        client.get(f"/readers/{other_card.id}", headers=headers_for(reader_user)).status_code == 403
    )
    assert client.get(f"/readers/{card.id}", headers=headers_for(other_user)).status_code == 403
    assert client.get(f"/readers/{card.id}", headers=headers_for(reader_user)).status_code == 200
    assert (
        client.get(f"/readers/{other_card.id}", headers=headers_for(other_user)).status_code == 200
    )


def test_an_invalid_id_is_422_not_a_leak(client, reader_user):
    assert client.get("/readers/abc", headers=headers_for(reader_user)).status_code == 422


# ---------- criterion 3: everything else stays closed ----------


def test_a_reader_still_cannot_list_all_readers(client, reader_user):
    assert client.get("/readers", headers=headers_for(reader_user)).status_code == 403


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_a_reader_still_cannot_change_readers_not_even_their_own_card(
    client, db, card, reader_user, method
):
    path = "/readers" if method == "POST" else f"/readers/{card.id}"
    body = {"name": "Changed", "email": "changed@example.com"} if method != "DELETE" else None

    response = client.request(method, path, json=body, headers=headers_for(reader_user))

    assert response.status_code == 403
    db.expire_all()
    assert db.get(Reader, card.id).name == "Own card"


def test_the_loans_of_the_own_card_still_work(client, card, reader_user):
    assert (
        client.get(f"/readers/{card.id}/loans", headers=headers_for(reader_user)).status_code == 200
    )


# ---------- criterion 5: staff and anonymous ----------


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_staff_opens_any_card_and_gets_404_for_a_missing_one(client, db, card, role):
    staff = make_user(db, role=role)

    assert client.get(f"/readers/{card.id}", headers=headers_for(staff)).status_code == 200
    assert client.get("/readers/999999", headers=headers_for(staff)).status_code == 404


def test_no_token_is_401(client, card):
    response = client.get(f"/readers/{card.id}")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_no_token_with_an_invalid_id_is_401_not_422(client):
    assert client.get("/readers/abc").status_code == 401


def test_a_disabled_reader_is_refused_at_once(client, db, card, reader_user):
    headers = headers_for(reader_user)
    reader_user.is_active = False
    db.commit()

    assert client.get(f"/readers/{card.id}", headers=headers).status_code == 401
