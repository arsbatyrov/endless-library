"""AUTH-009: user management, POST/GET /users, PATCH /users/{id}, POST /users/{id}/reset-password (criteria 1-9).

Who may do what: an admin manages everybody; a librarian manages only reader accounts; a reader manages nobody.
"""

import pytest

from app.auth.passwords import verify_password
from app.auth.refresh_tokens import issue_refresh_token
from app.auth.tokens import create_access_token
from app.models import RefreshToken, User
from tests.factories import make_reader, make_user


@pytest.fixture
def client(anonymous_client):
    """These tests check sign-in, roles and access errors: they start WITHOUT a login."""
    return anonymous_client


PASSWORD = "correct horse"
NEW_PASSWORD = "battery staple"
USER_FIELDS = {"id", "username", "role", "reader_id", "is_active", "created_at", "last_login_at"}


def auth(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def new_account(**overrides) -> dict:
    body = {"username": "newbie", "password": PASSWORD, "role": "librarian"}
    body.update(overrides)
    return body


@pytest.fixture
def admin(db):
    return make_user(db, role="admin", username="root", password=PASSWORD)


@pytest.fixture
def librarian(db):
    return make_user(db, role="librarian", username="lib", password=PASSWORD)


@pytest.fixture
def reader_account(db):
    return make_user(db, role="reader", username="rita", password=PASSWORD)


def count_users(db) -> int:
    db.expire_all()
    return db.query(User).count()


# ---------- criterion 1: admin creates accounts ----------


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_admin_creates_a_staff_account(client, db, admin, role):
    response = client.post("/users", json=new_account(role=role), headers=auth(admin))

    assert response.status_code == 201
    body = response.json()
    assert set(body) == USER_FIELDS
    assert body["username"] == "newbie"
    assert body["role"] == role
    assert body["reader_id"] is None
    assert body["is_active"] is True
    assert body["last_login_at"] is None


def test_admin_creates_a_reader_account_linked_to_a_card(client, db, admin):
    card = make_reader(db)

    response = client.post(
        "/users", json=new_account(role="reader", reader_id=card.id), headers=auth(admin)
    )

    assert response.status_code == 201
    assert response.json()["reader_id"] == card.id


def test_response_never_contains_the_password_or_its_hash(client, db, admin):
    response = client.post("/users", json=new_account(), headers=auth(admin))

    created = db.query(User).filter_by(username="newbie").one()
    assert PASSWORD not in response.text
    assert created.password_hash not in response.text
    assert "password" not in response.text.lower()


def test_password_is_stored_as_an_argon2_hash(client, db, admin):
    client.post("/users", json=new_account(), headers=auth(admin))

    created = db.query(User).filter_by(username="newbie").one()
    assert created.password_hash.startswith("$argon2id$")
    assert verify_password(PASSWORD, created.password_hash)


def test_new_account_can_sign_in(client, admin):
    client.post("/users", json=new_account(), headers=auth(admin))

    login = client.post("/auth/login", json={"username": "newbie", "password": PASSWORD})

    assert login.status_code == 200


# ---------- criterion 2: librarian ----------


def test_librarian_creates_a_reader_account(client, db, librarian):
    card = make_reader(db)

    response = client.post(
        "/users", json=new_account(role="reader", reader_id=card.id), headers=auth(librarian)
    )

    assert response.status_code == 201


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_librarian_cannot_create_staff(client, db, librarian, role):
    before = count_users(db)

    response = client.post("/users", json=new_account(role=role), headers=auth(librarian))

    assert response.status_code == 403
    assert count_users(db) == before


def test_librarian_cannot_probe_cards_by_asking_for_staff(client, librarian):
    """The 403 for a forbidden role comes before any check of the card."""
    response = client.post(
        "/users", json=new_account(role="admin", reader_id=999999), headers=auth(librarian)
    )

    assert response.status_code == 403


# ---------- criterion 3: reader and anonymous ----------


def reader_calls(target_id):
    return [
        ("POST", "/users", new_account()),
        ("GET", "/users", None),
        ("PATCH", f"/users/{target_id}", {"is_active": False}),
        ("POST", f"/users/{target_id}/reset-password", {"new_password": NEW_PASSWORD}),
    ]


def test_reader_is_forbidden_everywhere_in_users(client, db, reader_account, admin):
    for method, path, body in reader_calls(admin.id):
        response = client.request(method, path, json=body, headers=auth(reader_account))
        assert response.status_code == 403, (method, path)
    assert db.query(User).count() == 2


def test_anonymous_is_401_everywhere_in_users(client, admin):
    for method, path, body in reader_calls(admin.id):
        response = client.request(method, path, json=body)
        assert response.status_code == 401, (method, path)
        assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_body_without_a_token_is_401_not_422(client):
    assert client.post("/users", json={}).status_code == 401


def test_invalid_body_from_a_reader_is_403_not_422(client, reader_account):
    assert client.post("/users", json={}, headers=auth(reader_account)).status_code == 403


def test_disabled_admin_is_refused_at_once(client, db, admin):
    headers = auth(admin)
    other = make_user(db, role="admin", username="second")
    admin.is_active = False
    db.commit()

    assert client.get("/users", headers=headers).status_code == 401
    assert other.is_active


# ---------- criterion 4: reader accounts and cards ----------


def test_reader_account_without_a_card_is_422(client, admin):
    response = client.post("/users", json=new_account(role="reader"), headers=auth(admin))

    assert response.status_code == 422


def test_reader_account_with_a_missing_card_is_404(client, admin):
    response = client.post(
        "/users", json=new_account(role="reader", reader_id=999999), headers=auth(admin)
    )

    assert response.status_code == 404


def test_card_that_already_has_an_account_is_409(client, db, admin, reader_account):
    before = count_users(db)

    response = client.post(
        "/users",
        json=new_account(role="reader", reader_id=reader_account.reader_id),
        headers=auth(admin),
    )

    assert response.status_code == 409
    assert "already has an account" in response.json()["detail"]
    assert count_users(db) == before


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_staff_account_must_not_have_a_card(client, db, admin, role):
    card = make_reader(db)

    response = client.post(
        "/users", json=new_account(role=role, reader_id=card.id), headers=auth(admin)
    )

    assert response.status_code == 422


# ---------- criterion 5: login and password rules ----------


@pytest.mark.parametrize("taken", ["root", "ROOT", "Root"])
def test_taken_login_is_409_ignoring_case(client, db, admin, taken):
    before = count_users(db)

    response = client.post("/users", json=new_account(username=taken), headers=auth(admin))

    assert response.status_code == 409
    assert response.json()["detail"] == "This login is already taken"
    assert count_users(db) == before


@pytest.mark.parametrize("password", ["", "short", "1234567"])
def test_short_password_is_422(client, db, admin, password):
    before = count_users(db)

    response = client.post("/users", json=new_account(password=password), headers=auth(admin))

    assert response.status_code == 422
    assert count_users(db) == before


def test_password_of_8_characters_is_accepted(client, admin):
    response = client.post("/users", json=new_account(password="12345678"), headers=auth(admin))

    assert response.status_code == 201


def test_password_longer_than_128_is_422(client, admin):
    response = client.post("/users", json=new_account(password="x" * 129), headers=auth(admin))

    assert response.status_code == 422


def test_password_equal_to_the_login_is_422_ignoring_case(client, admin):
    response = client.post(
        "/users",
        json=new_account(username="administrator", password="ADMINISTRATOR"),
        headers=auth(admin),
    )

    assert response.status_code == 422


def test_422_never_echoes_the_password(client, admin):
    response = client.post("/users", json=new_account(password="pw-zq7"), headers=auth(admin))

    assert response.status_code == 422
    assert "pw-zq7" not in response.text


def test_422_for_a_wrong_type_never_echoes_the_password(client, admin):
    response = client.post(
        "/users",
        json=new_account(password="secret-that-must-not-leak", role=5),
        headers=auth(admin),
    )

    assert response.status_code == 422
    assert "secret-that-must-not-leak" not in response.text


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"username": "x"},
        {"username": "x", "password": PASSWORD},
        new_account(username=""),
        new_account(username="x" * 65),
        new_account(username="a\u0000b"),
        new_account(role="superuser"),
        new_account(role=None),
        new_account(username=5),
    ],
)
def test_invalid_bodies_are_422(client, db, admin, body):
    before = count_users(db)

    assert client.post("/users", json=body, headers=auth(admin)).status_code == 422
    assert count_users(db) == before


def test_username_of_the_maximum_length_is_accepted(client, admin):
    assert (
        client.post("/users", json=new_account(username="x" * 64), headers=auth(admin)).status_code
        == 201
    )


# ---------- criterion 9: list ----------


def test_admin_lists_everybody(client, db, admin, librarian, reader_account):
    response = client.get("/users", headers=auth(admin))

    assert response.status_code == 200
    assert [u["username"] for u in response.json()] == ["root", "lib", "rita"]
    assert all(set(u) == USER_FIELDS for u in response.json())


def test_librarian_lists_only_readers(client, db, admin, librarian, reader_account):
    response = client.get("/users", headers=auth(librarian))

    assert response.status_code == 200
    assert [u["username"] for u in response.json()] == ["rita"]


def test_list_never_contains_hashes(client, db, admin, reader_account):
    response = client.get("/users", headers=auth(admin))

    assert "argon2" not in response.text
    assert "password" not in response.text.lower()
    assert admin.password_hash not in response.text


def test_list_shows_disabled_accounts_too(client, db, admin, reader_account):
    reader_account.is_active = False
    db.commit()

    users = {u["username"]: u for u in client.get("/users", headers=auth(admin)).json()}

    assert users["rita"]["is_active"] is False


# ---------- criterion 6: PATCH ----------


def test_admin_disables_and_enables_an_account(client, db, admin, librarian):
    off = client.patch(f"/users/{librarian.id}", json={"is_active": False}, headers=auth(admin))
    on = client.patch(f"/users/{librarian.id}", json={"is_active": True}, headers=auth(admin))

    assert off.status_code == 200
    assert off.json()["is_active"] is False
    assert set(off.json()) == USER_FIELDS
    assert on.json()["is_active"] is True


def test_admin_changes_the_role_between_librarian_and_admin(client, db, admin, librarian):
    up = client.patch(f"/users/{librarian.id}", json={"role": "admin"}, headers=auth(admin))
    down = client.patch(f"/users/{librarian.id}", json={"role": "librarian"}, headers=auth(admin))

    assert up.json()["role"] == "admin"
    assert down.json()["role"] == "librarian"


def test_role_and_status_can_change_together(client, db, admin, librarian):
    response = client.patch(
        f"/users/{librarian.id}", json={"role": "admin", "is_active": False}, headers=auth(admin)
    )

    assert (response.json()["role"], response.json()["is_active"]) == ("admin", False)


def test_role_change_takes_effect_at_once(client, db, admin, librarian):
    headers = auth(librarian)
    assert client.post("/users", json=new_account(), headers=headers).status_code == 403

    client.patch(f"/users/{librarian.id}", json={"role": "admin"}, headers=auth(admin))

    assert client.post("/users", json=new_account(), headers=headers).status_code == 201


def test_staff_cannot_become_a_reader(client, db, admin, librarian):
    response = client.patch(f"/users/{librarian.id}", json={"role": "reader"}, headers=auth(admin))

    assert response.status_code == 422
    db.expire_all()
    assert librarian.role == "librarian"


def test_admin_may_disable_a_reader_account(client, admin, reader_account):
    response = client.patch(
        f"/users/{reader_account.id}", json={"is_active": False}, headers=auth(admin)
    )

    assert response.status_code == 200


def test_librarian_disables_and_enables_a_reader(client, db, librarian, reader_account):
    off = client.patch(
        f"/users/{reader_account.id}", json={"is_active": False}, headers=auth(librarian)
    )
    on = client.patch(
        f"/users/{reader_account.id}", json={"is_active": True}, headers=auth(librarian)
    )

    assert off.status_code == 200 and off.json()["is_active"] is False
    assert on.status_code == 200 and on.json()["is_active"] is True


def test_librarian_cannot_change_roles(client, db, librarian, reader_account):
    response = client.patch(
        f"/users/{reader_account.id}", json={"role": "admin"}, headers=auth(librarian)
    )

    assert response.status_code == 403
    db.expire_all()
    assert reader_account.role == "reader"


def test_librarian_cannot_send_a_role_even_with_a_status_change(
    client, db, librarian, reader_account
):
    response = client.patch(
        f"/users/{reader_account.id}",
        json={"role": "reader", "is_active": False},
        headers=auth(librarian),
    )

    assert response.status_code == 403
    db.expire_all()
    assert reader_account.is_active is True


@pytest.mark.parametrize("target", ["admin", "librarian"])
def test_librarian_cannot_touch_staff_accounts(client, db, admin, librarian, target):
    other = admin if target == "admin" else make_user(db, role="librarian", username="lib2")

    response = client.patch(
        f"/users/{other.id}", json={"is_active": False}, headers=auth(librarian)
    )

    assert response.status_code == 403
    db.expire_all()
    assert other.is_active is True


def test_librarian_cannot_disable_themselves(client, db, admin, librarian):
    response = client.patch(
        f"/users/{librarian.id}", json={"is_active": False}, headers=auth(librarian)
    )

    assert response.status_code == 403


@pytest.mark.parametrize("who", ["admin", "librarian"])
def test_missing_account_is_404(client, admin, librarian, who):
    actor = admin if who == "admin" else librarian

    assert (
        client.patch("/users/999999", json={"is_active": False}, headers=auth(actor)).status_code
        == 404
    )


@pytest.mark.parametrize(
    "body",
    [{}, {"is_active": "no"}, {"is_active": 1}, {"role": "root"}, {"role": 3}, {"is_active": None}],
)
def test_invalid_patch_bodies_are_422(client, admin, librarian, body):
    assert client.patch(f"/users/{librarian.id}", json=body, headers=auth(admin)).status_code == 422


def test_patch_with_an_invalid_id_is_422(client, admin):
    assert (
        client.patch("/users/abc", json={"is_active": False}, headers=auth(admin)).status_code
        == 422
    )


def test_patch_without_a_change_is_fine(client, admin, librarian):
    response = client.patch(f"/users/{librarian.id}", json={"is_active": True}, headers=auth(admin))

    assert response.status_code == 200


def test_username_and_card_cannot_be_changed_through_patch(client, db, admin, librarian):
    client.patch(
        f"/users/{librarian.id}",
        json={"is_active": True, "username": "hacked", "reader_id": 1},
        headers=auth(admin),
    )

    db.expire_all()
    assert librarian.username == "lib"
    assert librarian.reader_id is None


def test_disabling_an_account_ends_its_sessions(client, db, admin, librarian):
    issue_refresh_token(db, librarian)
    issue_refresh_token(db, librarian)
    other_token = issue_refresh_token(db, admin)
    db.commit()
    headers = auth(librarian)

    client.patch(f"/users/{librarian.id}", json={"is_active": False}, headers=auth(admin))

    db.expire_all()
    mine = db.query(RefreshToken).filter_by(user_id=librarian.id).all()
    assert len(mine) == 2 and all(row.revoked_at is not None for row in mine)
    assert db.query(RefreshToken).filter_by(user_id=admin.id).one().revoked_at is None
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert (
        client.post("/auth/login", json={"username": "lib", "password": PASSWORD}).status_code
        == 401
    )
    assert other_token


def test_enabling_an_account_lets_it_sign_in_again(client, db, admin, librarian):
    client.patch(f"/users/{librarian.id}", json={"is_active": False}, headers=auth(admin))
    client.patch(f"/users/{librarian.id}", json={"is_active": True}, headers=auth(admin))

    assert (
        client.post("/auth/login", json={"username": "lib", "password": PASSWORD}).status_code
        == 200
    )


# ---------- criterion 7: the last active admin ----------


def test_the_only_admin_cannot_be_disabled(client, db, admin):
    response = client.patch(f"/users/{admin.id}", json={"is_active": False}, headers=auth(admin))

    assert response.status_code == 409
    db.expire_all()
    assert admin.is_active is True


def test_the_only_admin_cannot_be_demoted(client, db, admin):
    response = client.patch(f"/users/{admin.id}", json={"role": "librarian"}, headers=auth(admin))

    assert response.status_code == 409
    db.expire_all()
    assert admin.role == "admin"


def test_the_only_admin_cannot_be_disabled_and_demoted_in_one_request(client, admin):
    response = client.patch(
        f"/users/{admin.id}", json={"role": "librarian", "is_active": False}, headers=auth(admin)
    )

    assert response.status_code == 409


def test_with_two_admins_one_can_be_disabled_but_not_the_last_one(client, db, admin):
    second = make_user(db, role="admin", username="second", password=PASSWORD)

    first = client.patch(f"/users/{second.id}", json={"is_active": False}, headers=auth(admin))
    last = client.patch(f"/users/{admin.id}", json={"is_active": False}, headers=auth(admin))

    assert first.status_code == 200
    assert last.status_code == 409


def test_disabled_admins_do_not_count(client, db, admin):
    make_user(db, role="admin", username="sleeping", active=False)

    response = client.patch(f"/users/{admin.id}", json={"role": "librarian"}, headers=auth(admin))

    assert response.status_code == 409


def test_an_admin_may_step_down_when_another_active_admin_exists(client, db, admin):
    make_user(db, role="admin", username="second", password=PASSWORD)

    response = client.patch(f"/users/{admin.id}", json={"role": "librarian"}, headers=auth(admin))

    assert response.status_code == 200


def test_changing_a_non_admin_never_hits_the_rule(client, db, admin, librarian):
    assert (
        client.patch(
            f"/users/{librarian.id}", json={"is_active": False}, headers=auth(admin)
        ).status_code
        == 200
    )


def test_a_disabled_last_admin_can_be_enabled(client, db, admin):
    """Re-enabling must work even though disabling the last one is refused (a disabled admin is simply inactive)."""
    other = make_user(db, role="admin", username="second", active=False)

    assert (
        client.patch(
            f"/users/{other.id}", json={"is_active": True}, headers=auth(admin)
        ).status_code
        == 200
    )


# ---------- criterion 8: reset password ----------


def reset(client, actor, target, password=NEW_PASSWORD):
    return client.post(
        f"/users/{target.id}/reset-password", json={"new_password": password}, headers=auth(actor)
    )


@pytest.mark.parametrize("target_role", ["reader", "librarian", "admin"])
def test_admin_resets_any_password(client, db, admin, target_role):
    target = make_user(db, role=target_role, username="target", password=PASSWORD)

    response = reset(client, admin, target)

    assert response.status_code == 204
    assert response.content == b""
    db.expire_all()
    assert verify_password(NEW_PASSWORD, target.password_hash)
    assert not verify_password(PASSWORD, target.password_hash)


def test_librarian_resets_a_reader_password(client, db, librarian, reader_account):
    assert reset(client, librarian, reader_account).status_code == 204


@pytest.mark.parametrize("target", ["admin", "librarian"])
def test_librarian_cannot_reset_staff_passwords(client, db, admin, librarian, target):
    other = (
        admin
        if target == "admin"
        else make_user(db, role="librarian", username="lib2", password=PASSWORD)
    )
    old_hash = other.password_hash

    assert reset(client, librarian, other).status_code == 403
    db.expire_all()
    assert other.password_hash == old_hash


def test_new_password_works_and_the_old_one_does_not(client, db, admin, reader_account):
    reset(client, admin, reader_account)

    old = client.post("/auth/login", json={"username": "rita", "password": PASSWORD})
    new = client.post("/auth/login", json={"username": "rita", "password": NEW_PASSWORD})

    assert (old.status_code, new.status_code) == (401, 200)


def test_reset_revokes_the_refresh_tokens_of_that_user_only(client, db, admin, reader_account):
    issue_refresh_token(db, reader_account)
    issue_refresh_token(db, admin)
    db.commit()

    reset(client, admin, reader_account)

    db.expire_all()
    assert db.query(RefreshToken).filter_by(user_id=reader_account.id).one().revoked_at is not None
    assert db.query(RefreshToken).filter_by(user_id=admin.id).one().revoked_at is None


def test_reset_does_not_end_the_admins_own_session_for_other_accounts(client, db, admin, librarian):
    reset(client, admin, librarian)

    assert client.get("/users", headers=auth(admin)).status_code == 200


@pytest.mark.parametrize("password", ["", "short", "x" * 129])
def test_reset_with_a_bad_password_is_422_and_changes_nothing(
    client, db, admin, reader_account, password
):
    old_hash = reader_account.password_hash

    response = reset(client, admin, reader_account, password)

    assert response.status_code == 422
    db.expire_all()
    assert reader_account.password_hash == old_hash


def test_reset_password_equal_to_the_login_is_422_ignoring_case(client, db, admin):
    target = make_user(db, role="librarian", username="longlogin", password=PASSWORD)

    assert reset(client, admin, target, "LONGLOGIN").status_code == 422


def test_reset_to_the_same_password_is_accepted(client, admin, reader_account):
    """Unlike a self-service change, an admin reset may set any policy-conforming password."""
    assert reset(client, admin, reader_account, PASSWORD).status_code == 204


def test_reset_422_never_echoes_the_password(client, admin, reader_account):
    response = client.post(
        f"/users/{reader_account.id}/reset-password",
        json={"new_password": 12345678},
        headers=auth(admin),
    )

    assert response.status_code == 422
    assert "12345678" not in response.text


def test_reset_of_a_missing_account_is_404(client, admin):
    response = client.post(
        "/users/999999/reset-password", json={"new_password": NEW_PASSWORD}, headers=auth(admin)
    )

    assert response.status_code == 404


def test_reset_does_not_reactivate_a_disabled_account(client, db, admin, reader_account):
    reader_account.is_active = False
    db.commit()

    assert reset(client, admin, reader_account).status_code == 204
    db.expire_all()
    assert reader_account.is_active is False
    assert (
        client.post("/auth/login", json={"username": "rita", "password": NEW_PASSWORD}).status_code
        == 401
    )


def test_admin_can_reset_their_own_password(client, db, admin):
    assert reset(client, admin, admin).status_code == 204
    db.expire_all()
    assert verify_password(NEW_PASSWORD, admin.password_hash)


def test_reset_with_a_missing_field_is_422(client, admin, reader_account):
    response = client.post(
        f"/users/{reader_account.id}/reset-password", json={}, headers=auth(admin)
    )

    assert response.status_code == 422
