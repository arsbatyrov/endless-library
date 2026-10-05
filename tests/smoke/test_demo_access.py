"""AUTH-021: the demo accounts on the deployed cluster (after `DEMO=1 bash k8s/deploy.sh`).

Skipped unless SMOKE_DEMO=1: a normal deploy has NO demo accounts and these tests must not look for them. The CI job
runs a separate deploy with DEMO=1 and then these tests.
"""

import os
import subprocess

import httpx2 as httpx
import pytest
from playwright.sync_api import expect

from app.demo import DEMO_ACCOUNTS
from tests.smoke.conftest import CONTEXT, SMOKE_URL, cluster_secret
from tests.ui.pages import App

pytestmark = pytest.mark.skipif(
    os.environ.get("SMOKE_DEMO") != "1", reason="set SMOKE_DEMO=1 after a DEMO=1 deploy"
)


def sign_in(client: httpx.Client, username: str, password: str) -> dict:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, f"{username}: {response.status_code} {response.text}"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def web():
    with httpx.Client(base_url=f"{SMOKE_URL}/api", timeout=15) as client:
        yield client


def test_every_demo_account_signs_in_through_the_ingress_with_its_role(web):
    for account in DEMO_ACCOUNTS:
        headers = sign_in(web, account.username, account.password)

        me = web.get("/auth/me", headers=headers).json()

        assert (me["username"], me["role"]) == (account.username, account.role)


def test_the_rights_of_the_three_demo_roles_differ_as_designed(web):
    admin = sign_in(web, "admin", "admin12345")
    librarian = sign_in(web, "librarian", "librarian12345")
    reader = sign_in(web, "reader", "reader12345")

    assert web.get("/users", headers=admin).status_code == 200
    assert web.get("/readers", headers=librarian).status_code == 200
    assert web.get("/readers", headers=reader).status_code == 403
    assert web.get("/books", headers=reader).status_code == 200
    assert (
        web.post(
            "/books", json={"title": "x", "author": "y", "copies_available": 1}, headers=reader
        ).status_code
        == 403
    )


def test_the_demo_reader_opens_their_own_card_and_not_another(web):
    headers = sign_in(web, "reader", "reader12345")
    me = web.get("/auth/me", headers=headers).json()

    own = web.get(f"/readers/{me['reader_id']}", headers=headers)
    other = web.get(f"/readers/{me['reader_id'] + 100000}", headers=headers)

    assert own.status_code == 200 and own.json()["email"] == "demo.reader@example.com"
    assert other.status_code == 403


def test_the_secret_follows_the_demo_administrator(web):
    assert cluster_secret("endless-library-admin", "password") == "admin12345"


def test_the_api_warns_at_startup_that_demo_accounts_are_enabled():
    logs = subprocess.run(
        [
            "kubectl",
            "--context",
            CONTEXT,
            "-n",
            "endless-library",
            "logs",
            "-l",
            "app=api",
            "--tail=3000",
            "--prefix=false",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    ).stdout

    assert "DEMO_ACCOUNTS=true" in logs


def test_the_demo_administrator_signs_in_on_the_real_site(page):
    app = App(page).open()

    page.get_by_test_id("login-username").fill("admin")
    page.get_by_test_id("login-password").fill("admin12345")
    page.get_by_test_id("login-submit").click()

    expect(page.get_by_test_id("current-user")).to_have_text("admin")
    expect(app.tab("users")).to_be_visible()


def test_a_wrong_demo_password_is_still_refused(web):
    response = web.post("/auth/login", json={"username": "admin", "password": "admin"})

    assert response.status_code in (401, 422)
