"""AUTH-020: an admin can change an account's role to any role.

Rules: any role to any role; to `reader` needs a reader card (404 if missing, 409 if it already has an account, 422 if
not sent); from `reader` to staff the link to the card is removed (the card stays); the last active admin cannot be
demoted; a librarian may not send `role` or `reader_id` at all. The change is immediate, sessions stay valid.
"""

import pytest

from app.auth.tokens import create_access_token
from app.models import Reader, RefreshToken, User
from tests.api.helpers import (
    create_book,  # noqa: F401  (documents that book rights follow the role)
)
from tests.factories import make_reader, make_user

PASSWORD = "correct horse"


@pytest.fixture
def client(anonymous_client):
    """These tests check who may do what: they start WITHOUT a login."""
    return anonymous_client


def auth(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture
def admin(db):
    return make_user(db, role="admin", username="root", password=PASSWORD)


@pytest.fixture
def second_admin(db):
    return make_user(db, role="admin", username="root2", password=PASSWORD)


@pytest.fixture
def librarian(db):
    return make_user(db, role="librarian", username="lib", password=PASSWORD)


@pytest.fixture
def reader_account(db):
    return make_user(db, role="reader", username="rita", password=PASSWORD)


def patch(client, actor, target, **body):
    return client.patch(f"/users/{target.id}", json=body, headers=auth(actor))


# ---------- any role to any role ----------


def test_librarian_to_admin(client, admin, librarian):
    response = patch(client, admin, librarian, role="admin")

    assert response.status_code == 200
    assert response.json()["role"] == "admin" and response.json()["reader_id"] is None


def test_admin_to_librarian_when_another_admin_exists(client, admin, second_admin):
    response = patch(client, admin, second_admin, role="librarian")

    assert response.status_code == 200 and response.json()["role"] == "librarian"


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_reader_to_staff_removes_the_link_to_the_card_and_keeps_the_card(
    client, db, admin, reader_account, role
):
    card_id = reader_account.reader_id

    response = patch(client, admin, reader_account, role=role)

    assert response.status_code == 200
    assert response.json()["role"] == role and response.json()["reader_id"] is None
    db.expire_all()
    assert reader_account.reader_id is None
    assert db.get(Reader, card_id) is not None


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_staff_to_reader_with_a_free_card(client, db, admin, librarian, role):
    card = make_reader(db)
    if role == "admin":
        librarian.role = "admin"
        db.commit()

    response = patch(client, admin, librarian, role="reader", reader_id=card.id)

    assert response.status_code == 200
    assert response.json()["role"] == "reader" and response.json()["reader_id"] == card.id


def test_the_card_can_be_reused_by_another_account_after_the_first_became_staff(
    client, db, admin, reader_account, librarian
):
    card_id = reader_account.reader_id
    patch(client, admin, reader_account, role="librarian")

    response = patch(client, admin, librarian, role="reader", reader_id=card_id)

    assert response.status_code == 200 and response.json()["reader_id"] == card_id


def test_the_change_keeps_the_login_the_password_and_the_status(client, db, admin, librarian):
    before = (
        librarian.username,
        librarian.password_hash,
        librarian.is_active,
        librarian.created_at,
    )

    patch(client, admin, librarian, role="admin")

    db.expire_all()
    assert (
        librarian.username,
        librarian.password_hash,
        librarian.is_active,
        librarian.created_at,
    ) == before
    assert (
        client.post("/auth/login", json={"username": "lib", "password": PASSWORD}).status_code
        == 200
    )


def test_a_role_and_a_status_can_change_together(client, admin, librarian):
    response = patch(client, admin, librarian, role="admin", is_active=False)

    assert (response.json()["role"], response.json()["is_active"]) == ("admin", False)


def test_the_same_role_is_a_harmless_no_op(client, admin, librarian):
    assert patch(client, admin, librarian, role="librarian").status_code == 200


def test_a_reader_may_be_confirmed_as_a_reader_of_the_same_card(client, admin, reader_account):
    response = patch(
        client, admin, reader_account, role="reader", reader_id=reader_account.reader_id
    )

    assert response.status_code == 200 and response.json()["reader_id"] == reader_account.reader_id


# ---------- the card rules for a reader ----------


def test_to_reader_without_a_card_is_422_and_nothing_changes(client, db, admin, librarian):
    response = patch(client, admin, librarian, role="reader")

    assert response.status_code == 422
    db.expire_all()
    assert librarian.role == "librarian" and librarian.reader_id is None


def test_to_reader_with_a_missing_card_is_404(client, db, admin, librarian):
    response = patch(client, admin, librarian, role="reader", reader_id=999999)

    assert response.status_code == 404
    db.expire_all()
    assert librarian.role == "librarian"


def test_to_reader_with_a_card_that_already_has_an_account_is_409(
    client, db, admin, librarian, reader_account
):
    response = patch(client, admin, librarian, role="reader", reader_id=reader_account.reader_id)

    assert response.status_code == 409
    assert "already has an account" in response.json()["detail"]
    db.expire_all()
    assert librarian.role == "librarian" and librarian.reader_id is None


def test_a_reader_cannot_be_moved_to_another_card_by_this_endpoint(
    client, db, admin, reader_account
):
    other = make_reader(db)
    old_card = reader_account.reader_id

    response = patch(client, admin, reader_account, role="reader", reader_id=other.id)

    assert response.status_code == 422
    db.expire_all()
    assert reader_account.reader_id == old_card


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_a_card_cannot_be_sent_together_with_a_staff_role(client, db, admin, reader_account, role):
    card = make_reader(db)

    response = patch(client, admin, reader_account, role=role, reader_id=card.id)

    assert response.status_code == 422
    db.expire_all()
    assert reader_account.role == "reader"


def test_a_card_alone_cannot_be_given_to_a_staff_account(client, db, admin, librarian):
    card = make_reader(db)

    response = patch(client, admin, librarian, reader_id=card.id)

    assert response.status_code == 422
    db.expire_all()
    assert librarian.reader_id is None


def test_a_card_race_between_the_check_and_the_save_is_a_409_not_a_crash(
    client, db, admin, librarian, monkeypatch
):
    """Two admins link the same card at the same moment: the database's unique index decides, the answer is 409."""
    from app.services import users as user_service

    taken = make_user(db, role="reader", username="first")
    monkeypatch.setattr(user_service, "_card_has_account", lambda db, card_id: False)

    response = patch(client, admin, librarian, role="reader", reader_id=taken.reader_id)

    assert response.status_code == 409
    db.expire_all()
    assert librarian.role == "librarian" and librarian.reader_id is None


# ---------- the last active admin ----------


@pytest.mark.parametrize("role", ["librarian", "reader"])
def test_the_only_admin_cannot_be_demoted_to_any_role(client, db, admin, role):
    card = make_reader(db)
    body = {"role": role, **({"reader_id": card.id} if role == "reader" else {})}

    response = patch(client, admin, admin, **body)

    assert response.status_code == 409
    db.expire_all()
    assert admin.role == "admin" and admin.reader_id is None


def test_an_admin_may_step_down_to_a_reader_when_another_admin_exists(
    client, db, admin, second_admin
):
    card = make_reader(db)

    response = patch(client, admin, admin, role="reader", reader_id=card.id)

    assert response.status_code == 200 and response.json()["role"] == "reader"


def test_a_disabled_admin_does_not_count_as_the_other_one(client, db, admin):
    make_user(db, role="admin", username="sleeping", active=False)

    assert patch(client, admin, admin, role="librarian").status_code == 409


# ---------- who may do it ----------


@pytest.mark.parametrize(
    "body",
    [
        {"role": "admin"},
        {"role": "reader"},
        {"role": "librarian"},
        {"role": "reader", "reader_id": 1},
        {"reader_id": 1},
    ],
)
def test_a_librarian_may_not_send_a_role_or_a_card(client, db, librarian, reader_account, body):
    response = client.patch(f"/users/{reader_account.id}", json=body, headers=auth(librarian))

    assert response.status_code == 403
    db.expire_all()
    assert reader_account.role == "reader"


def test_a_reader_may_not_change_any_role_even_their_own(client, db, reader_account):
    response = patch(client, reader_account, reader_account, role="admin")

    assert response.status_code == 403
    db.expire_all()
    assert reader_account.role == "reader"


def test_anonymous_is_401(client, librarian):
    assert client.patch(f"/users/{librarian.id}", json={"role": "admin"}).status_code == 401


# ---------- the change is immediate and sessions stay valid ----------


def test_a_promoted_librarian_may_at_once_create_staff_with_the_same_token(
    client, admin, librarian
):
    headers = auth(librarian)
    body = {"username": "newbie", "password": PASSWORD, "role": "librarian"}
    assert client.post("/users", json=body, headers=headers).status_code == 403

    patch(client, admin, librarian, role="admin")

    assert client.post("/users", json=body, headers=headers).status_code == 201


def test_a_demoted_admin_loses_the_rights_at_once_with_the_same_token(
    client, db, admin, second_admin
):
    headers = auth(second_admin)
    assert client.get("/users", headers=headers).status_code == 200
    card = make_reader(db)

    patch(client, admin, second_admin, role="reader", reader_id=card.id)

    assert client.get("/users", headers=headers).status_code == 403
    assert (
        client.get(f"/readers/{card.id}", headers=headers).status_code == 200
    )  # now their own card


def test_a_reader_made_a_librarian_may_at_once_change_books(client, admin, reader_account):
    headers = auth(reader_account)
    book = {"title": "Dune", "author": "Frank Herbert", "copies_available": 1}
    assert client.post("/books", json=book, headers=headers).status_code == 403

    patch(client, admin, reader_account, role="librarian")

    assert client.post("/books", json=book, headers=headers).status_code == 201


def test_a_role_change_does_not_end_the_sessions_of_the_account(client, db, admin, librarian):
    client.post("/auth/login", json={"username": "lib", "password": PASSWORD})
    client.cookies.clear()  # the cookie of the librarian stays only in the database
    token_rows = db.query(RefreshToken).filter_by(user_id=librarian.id).count()

    patch(client, admin, librarian, role="admin")

    db.expire_all()
    rows = db.query(RefreshToken).filter_by(user_id=librarian.id).all()
    assert len(rows) == token_rows == 1
    assert all(row.revoked_at is None for row in rows)


def test_the_new_role_is_visible_in_the_profile_and_the_list(client, admin, librarian):
    patch(client, admin, librarian, role="admin")

    listing = client.get("/users", headers=auth(admin)).json()
    me = client.get("/auth/me", headers=auth(librarian)).json()

    assert {u["username"]: u["role"] for u in listing}["lib"] == "admin"
    assert me["role"] == "admin"


# ---------- validation ----------


@pytest.mark.parametrize(
    "body",
    [
        {"reader_id": None},
        {"role": "reader", "reader_id": "1"},
        {"role": "reader", "reader_id": 0},
        {"role": "reader", "reader_id": -1},
        {"role": "reader", "reader_id": 2**31},
        {"role": "reader", "reader_id": 1.5},
        {"role": "reader", "reader_id": True},
        {"role": "Admin"},
        {"role": None},
        {"role": 1},
    ],
)
def test_invalid_bodies_are_422(client, db, admin, librarian, body):
    assert client.patch(f"/users/{librarian.id}", json=body, headers=auth(admin)).status_code == 422
    db.expire_all()
    assert librarian.role == "librarian"


def test_a_422_never_echoes_input(client, admin, librarian):
    response = client.patch(
        f"/users/{librarian.id}", json={"role": "secret-role-value"}, headers=auth(admin)
    )

    assert response.status_code == 422
    assert "secret-role-value" not in response.text


def test_the_response_never_contains_a_secret(client, admin, librarian):
    response = patch(client, admin, librarian, role="admin")

    assert set(response.json()) == {
        "id",
        "username",
        "role",
        "reader_id",
        "is_active",
        "created_at",
        "last_login_at",
    }
    assert librarian.password_hash not in response.text


def test_a_missing_account_is_404(client, admin):
    assert (
        client.patch("/users/999999", json={"role": "admin"}, headers=auth(admin)).status_code
        == 404
    )


def test_the_card_checks_come_after_the_permission_check(client, db, librarian, reader_account):
    """A librarian must not learn which cards exist or are taken from the answers of this endpoint."""
    taken = client.patch(
        f"/users/{reader_account.id}",
        json={"role": "reader", "reader_id": reader_account.reader_id},
        headers=auth(librarian),
    )
    missing = client.patch(
        f"/users/{reader_account.id}",
        json={"role": "reader", "reader_id": 999999},
        headers=auth(librarian),
    )

    assert (taken.status_code, missing.status_code) == (403, 403)
    assert User.__name__
