"""AUTH-013: signing in and out on the deployed site (Ingress -> nginx -> API), as a user does it."""

import re

import httpx2 as httpx
from playwright.sync_api import expect

from tests.smoke.conftest import SMOKE_URL
from tests.ui.pages import App


def test_the_site_shows_only_the_sign_in_page_without_a_session(page):
    App(page).open()

    expect(page.get_by_test_id("login-form")).to_be_visible()
    expect(page.get_by_test_id("tab-books")).to_have_count(0)


def test_the_data_endpoints_are_closed_without_a_token_through_the_ingress():
    for path in ("/api/books", "/api/readers", "/api/users"):
        assert httpx.get(f"{SMOKE_URL}{path}", timeout=10).status_code == 401, path


def test_the_first_admin_signs_in_and_out_on_the_real_site(page, admin_credentials):
    username, password = admin_credentials
    app = App(page).open()

    page.get_by_test_id("login-username").fill(username)
    page.get_by_test_id("login-password").fill(password)
    page.get_by_test_id("login-submit").click()

    expect(page.get_by_test_id("current-user")).to_have_text(username)
    expect(app.tab("books")).to_have_attribute("aria-selected", "true")

    page.reload()  # the session survives a reload through the refresh cookie (path /api/auth behind nginx)
    expect(page.get_by_test_id("current-user")).to_have_text(username)

    page.get_by_test_id("logout").click()
    expect(page.get_by_test_id("login-form")).to_be_visible()
    status = page.evaluate("async () => (await fetch('/api/books')).status")
    assert status == 401


def test_a_wrong_password_is_refused_on_the_real_site(page, admin_credentials):
    username, _ = admin_credentials
    App(page).open()

    page.get_by_test_id("login-username").fill(username)
    page.get_by_test_id("login-password").fill("definitely not the password")
    page.get_by_test_id("login-submit").click()

    expect(page.get_by_test_id("login-error")).to_have_text(
        re.compile("Invalid username or password")
    )
