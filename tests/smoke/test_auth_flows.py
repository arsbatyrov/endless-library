"""AUTH-018: sign-in, rights, token refresh and sign-out on the deployed cluster, all through the Ingress.

These tests work on any deploy (with or without demo accounts): the reader they need is created by the administrator
from the Secret and disabled afterwards (there is no way to delete an account, by design).
"""

import uuid

import httpx2 as httpx
import pytest

from tests.smoke.conftest import SMOKE_URL

READER_PASSWORD = "smoke-reader-" + uuid.uuid4().hex[:12]


@pytest.fixture
def reader_account(api):
    """A reader card with an account; returns (login, password). Cleaned up: the account is disabled, the card removed."""
    suffix = uuid.uuid4().hex[:10]
    card = api.post(
        "/readers", json={"name": f"Smoke Reader {suffix}", "email": f"smoke.{suffix}@example.com"}
    )
    assert card.status_code == 201, card.text
    login = f"smoke-{suffix}"
    created = api.post(
        "/users",
        json={
            "username": login,
            "password": READER_PASSWORD,
            "role": "reader",
            "reader_id": card.json()["id"],
        },
    )
    assert created.status_code == 201, created.text
    yield login, READER_PASSWORD
    api.patch(f"/users/{created.json()['id']}", json={"is_active": False})
    api.delete(
        f"/readers/{card.json()['id']}"
    )  # refused while the account exists; the card is then left (harmless)


def sign_in(client: httpx.Client, login: str, password: str) -> httpx.Response:
    return client.post("/api/auth/login", json={"username": login, "password": password})


def test_a_request_without_a_token_gets_401_and_the_admin_gets_data(api):
    anonymous = httpx.get(f"{SMOKE_URL}/api/books", timeout=15)

    assert anonymous.status_code == 401
    assert api.get("/books").status_code == 200


def test_a_reader_is_refused_what_staff_may_do_and_may_read_the_catalogue(reader_account):
    login, password = reader_account
    with httpx.Client(base_url=SMOKE_URL, timeout=15) as client:
        token = sign_in(client, login, password).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        assert client.get("/api/auth/me", headers=headers).json()["role"] == "reader"
        assert client.get("/api/books", headers=headers).status_code == 200
        assert client.get("/api/readers", headers=headers).status_code == 403
        assert client.get("/api/users", headers=headers).status_code == 403
        assert (
            client.post(
                "/api/books",
                json={"title": "x", "author": "y", "copies_available": 1},
                headers=headers,
            ).status_code
            == 403
        )


def test_a_reader_opens_their_own_card_and_not_another(reader_account, api):
    login, password = reader_account
    with httpx.Client(base_url=SMOKE_URL, timeout=15) as client:
        token = sign_in(client, login, password).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        own_id = client.get("/api/auth/me", headers=headers).json()["reader_id"]

        assert client.get(f"/api/readers/{own_id}", headers=headers).status_code == 200
        assert client.get(f"/api/readers/{own_id + 100000}", headers=headers).status_code == 403


def test_the_refresh_token_is_replaced_on_every_refresh_and_the_old_one_is_dead(admin_credentials):
    username, password = admin_credentials
    with httpx.Client(base_url=SMOKE_URL, timeout=15) as client:
        sign_in(client, username, password)
        first_cookie = client.cookies.get("refresh_token")

        assert client.post("/api/auth/refresh").status_code == 200
        second_cookie = client.cookies.get("refresh_token")
        assert second_cookie and second_cookie != first_cookie

        # The stolen first token is refused, and the reuse ends the whole family: the second one dies too.
        with httpx.Client(
            base_url=SMOKE_URL, timeout=15, cookies={"refresh_token": first_cookie}
        ) as thief:
            assert thief.post("/api/auth/refresh").status_code == 401
        assert client.post("/api/auth/refresh").status_code == 401


def test_sign_out_ends_the_session_through_the_ingress(admin_credentials):
    username, password = admin_credentials
    with httpx.Client(base_url=SMOKE_URL, timeout=15) as client:
        sign_in(client, username, password)
        saved = client.cookies.get("refresh_token")

        assert client.post("/api/auth/logout").status_code == 204

        with httpx.Client(
            base_url=SMOKE_URL, timeout=15, cookies={"refresh_token": saved}
        ) as after:
            assert after.post("/api/auth/refresh").status_code == 401


def test_responses_of_the_auth_endpoints_are_not_cacheable(admin_credentials):
    username, password = admin_credentials
    response = httpx.post(
        f"{SMOKE_URL}/api/auth/login", json={"username": username, "password": password}, timeout=15
    )

    assert "no-store" in response.headers["cache-control"]
