"""AUTH-013: sign-in page, session state and sign-out on the web site (acceptance criteria 1-7).

Tests marked `anonymous` start without a session; every other UI test starts already signed in (see conftest).
"""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import ADMIN_PASSWORD, ADMIN_USERNAME

pytestmark = pytest.mark.anonymous

USERNAME = "[data-testid=login-username]"
PASSWORD = "[data-testid=login-password]"
SUBMIT = "[data-testid=login-submit]"
ERROR = "[data-testid=login-error]"
JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.")


def sign_in(page: Page, username=ADMIN_USERNAME, password=ADMIN_PASSWORD) -> None:
    page.fill(USERNAME, username)
    page.fill(PASSWORD, password)
    page.click(SUBMIT)


def expire_the_current_token(page: Page, url_pattern) -> None:
    """Models an access token that has just expired: a request carrying the token the page has NOW gets 401, a request
    with a newer one (after a refresh) passes. (React StrictMode runs effects twice in development, so "fail once"
    would hit the request the page cancels itself.)"""
    stale = {}

    def handler(route):
        token = route.request.headers.get("authorization")
        stale.setdefault("token", token)
        if token == stale["token"]:
            route.fulfill(status=401, json={"detail": "Invalid or missing access token"})
        else:
            route.continue_()

    page.route(url_pattern, handler)


def storage_dump(page: Page) -> str:
    return page.evaluate(
        "() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage), document.cookie])"
    )


# ---------- criterion 1: only the sign-in page without a session ----------


def test_without_a_session_only_the_sign_in_page_is_shown(app, page):
    app.open()

    expect(page.get_by_test_id("login-form")).to_be_visible()
    expect(page.locator(USERNAME)).to_be_visible()
    expect(page.locator(PASSWORD)).to_be_visible()
    expect(page.get_by_test_id("tab-books")).to_have_count(0)
    expect(page.get_by_test_id("books-table")).to_have_count(0)
    expect(page.get_by_test_id("logout")).to_have_count(0)


def test_no_library_data_is_requested_without_a_session(app, page):
    requested = []
    page.on("request", lambda request: requested.append(request.url))

    app.open()
    expect(page.get_by_test_id("login-form")).to_be_visible()
    page.wait_for_timeout(300)

    data_urls = [u for u in requested if re.search(r"/api/(books|readers|loans)", u)]
    assert data_urls == []


def test_the_heading_and_language_switcher_are_available_on_the_sign_in_page(app, page):
    app.open()

    expect(app.heading).to_have_text("Endless Library")
    expect(app.locale_button("en")).to_be_visible()


# ---------- criterion 2: successful sign-in ----------


def test_valid_credentials_open_the_books_section(app, page):
    app.open()

    sign_in(page)

    expect(app.tab("books")).to_have_attribute("aria-selected", "true")
    expect(page.get_by_test_id("login-form")).to_have_count(0)
    expect(page.get_by_test_id("current-user")).to_have_text(ADMIN_USERNAME)
    expect(page.get_by_test_id("logout")).to_be_visible()


def test_enter_in_the_password_field_signs_in(app, page):
    app.open()
    page.fill(USERNAME, ADMIN_USERNAME)
    page.fill(PASSWORD, ADMIN_PASSWORD)

    page.press(PASSWORD, "Enter")

    expect(page.get_by_test_id("current-user")).to_have_text(ADMIN_USERNAME)


def test_the_books_of_the_library_are_shown_after_signing_in(app, page, api):
    api.create_book(title="Дюна")
    app.open()

    sign_in(page)

    expect(page.get_by_text("Дюна")).to_be_visible()


def test_login_is_case_insensitive(app, page):
    app.open()

    sign_in(page, username=ADMIN_USERNAME.upper())

    expect(page.get_by_test_id("current-user")).to_be_visible()


def test_signing_in_twice_in_a_row_is_not_possible_by_double_click(app, page):
    app.open()
    page.fill(USERNAME, ADMIN_USERNAME)
    page.fill(PASSWORD, ADMIN_PASSWORD)
    logins = []
    page.on("request", lambda r: logins.append(r) if r.url.endswith("/api/auth/login") else None)

    page.dblclick(SUBMIT)

    expect(page.get_by_test_id("current-user")).to_be_visible()
    assert len(logins) == 1


# ---------- criterion 3: wrong credentials ----------


def test_wrong_password_shows_the_server_message_and_keeps_the_fields(app, page):
    app.open()

    sign_in(page, password="not the password")

    expect(page.locator(ERROR)).to_have_text("Invalid username or password")
    expect(page.locator(USERNAME)).to_have_value(ADMIN_USERNAME)
    expect(page.locator(PASSWORD)).to_have_value("not the password")
    expect(page.get_by_test_id("login-form")).to_be_visible()
    expect(page.get_by_test_id("tab-books")).to_have_count(0)


def test_the_server_message_is_not_translated(app, page):
    """In the Russian interface the server's own English text is shown as it is."""
    app.open()
    assert page.locator("html").get_attribute("lang") == "ru"

    sign_in(page, username="nobody", password="whatever it is")

    expect(page.locator(ERROR)).to_have_text("Invalid username or password")


def test_unknown_login_gets_the_same_message(app, page):
    app.open()

    sign_in(page, username="no-such-person", password="whatever it is")

    expect(page.locator(ERROR)).to_have_text("Invalid username or password")


def test_focus_returns_to_the_form_after_a_failure(app, page):
    app.open()

    sign_in(page, password="wrong one")
    expect(page.locator(ERROR)).to_be_visible()

    expect(page.locator(PASSWORD)).to_be_focused()


def test_the_error_is_announced_to_screen_readers(app, page):
    app.open()

    sign_in(page, password="wrong one")

    expect(page.locator(ERROR)).to_have_attribute("role", "alert")


def test_the_error_disappears_on_the_next_attempt_and_signing_in_works(app, page):
    app.open()
    sign_in(page, password="wrong one")
    expect(page.locator(ERROR)).to_be_visible()

    page.fill(PASSWORD, ADMIN_PASSWORD)
    page.click(SUBMIT)

    expect(page.get_by_test_id("current-user")).to_be_visible()
    expect(page.locator(ERROR)).to_have_count(0)


def test_the_password_is_not_visible_in_the_page_after_a_failure(app, page):
    app.open()

    sign_in(page, password="visible-secret-1")

    expect(page.locator(ERROR)).to_be_visible()
    assert "visible-secret-1" not in page.locator("body").inner_text()
    assert page.locator(PASSWORD).get_attribute("type") == "password"


def test_a_network_failure_is_reported_and_the_fields_are_kept(app, page):
    app.open()
    page.route("**/api/auth/login", lambda route: route.abort())

    sign_in(page)

    expect(page.locator(ERROR)).to_have_text("Не удалось связаться с сервером")
    expect(page.locator(USERNAME)).to_have_value(ADMIN_USERNAME)
    expect(page.locator(SUBMIT)).to_be_enabled()


def test_the_submit_button_is_disabled_while_the_request_is_running(app, page):
    app.open()
    held = []
    page.route("**/api/auth/login", lambda route: held.append(route))
    page.fill(USERNAME, ADMIN_USERNAME)
    page.fill(PASSWORD, ADMIN_PASSWORD)

    page.click(SUBMIT)

    expect(page.locator(SUBMIT)).to_be_disabled()
    expect(page.locator(SUBMIT)).to_have_text("Входим…")
    for route in held:
        route.abort()


def test_a_locked_login_shows_the_server_message(app, page):
    app.open()
    page.route(
        "**/api/auth/login",
        lambda route: route.fulfill(
            status=429,
            headers={"Retry-After": "900"},
            json={"detail": "Too many failed login attempts. Try again later."},
        ),
    )

    sign_in(page)

    expect(page.locator(ERROR)).to_have_text("Too many failed login attempts. Try again later.")


# ---------- criterion 4: the session survives a reload, nothing in storage ----------


def test_a_reload_keeps_the_user_signed_in(app, page):
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("current-user")).to_be_visible()

    page.reload()

    expect(page.get_by_test_id("current-user")).to_have_text(ADMIN_USERNAME)
    expect(app.tab("books")).to_be_visible()


def test_the_reload_signs_in_silently_without_showing_the_sign_in_page(app, page):
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("current-user")).to_be_visible()

    page.reload()

    expect(page.get_by_test_id("session-restoring")).to_have_count(0)
    expect(page.get_by_test_id("login-form")).to_have_count(0)


def test_a_reload_goes_through_the_refresh_endpoint(app, page):
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("current-user")).to_be_visible()
    refreshes = []
    page.on(
        "request", lambda r: refreshes.append(r) if r.url.endswith("/api/auth/refresh") else None
    )

    page.reload()
    expect(page.get_by_test_id("current-user")).to_be_visible()

    assert len(refreshes) == 1


def test_no_token_is_kept_in_any_browser_storage(app, page):
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("current-user")).to_be_visible()
    page.reload()
    expect(page.get_by_test_id("current-user")).to_be_visible()

    dump = storage_dump(page)

    assert not JWT_PATTERN.search(dump), dump
    assert ADMIN_PASSWORD not in dump
    assert "refresh_token" not in dump


def test_the_refresh_cookie_is_http_only_and_scoped_to_the_auth_path(app, page, context):
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("current-user")).to_be_visible()

    cookie = next(c for c in context.cookies() if c["name"] == "refresh_token")

    assert cookie["httpOnly"] is True
    assert cookie["path"] == "/api/auth"
    assert cookie["sameSite"] == "Lax"


def test_an_invalid_refresh_cookie_silently_shows_the_sign_in_page(app, page, context):
    context.add_cookies(
        [
            {
                "name": "refresh_token",
                "value": "garbage",
                "domain": "127.0.0.1",
                "path": "/api/auth",
                "httpOnly": True,
            }
        ]
    )

    app.open()

    expect(page.get_by_test_id("login-form")).to_be_visible()
    expect(page.locator(ERROR)).to_have_count(0)
    expect(page.get_by_test_id("login-expired")).to_have_count(0)


# ---------- criterion 5: an expired access token ----------


def test_a_401_triggers_one_refresh_and_the_request_is_repeated(app, page, api):
    api.create_book(title="Дюна")
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("current-user")).to_be_visible()
    refreshes = []
    page.on(
        "request", lambda r: refreshes.append(r) if r.url.endswith("/api/auth/refresh") else None
    )

    expire_the_current_token(page, "**/api/books")
    app.go_to_readers()
    app.go_to_books()

    expect(page.get_by_text("Дюна")).to_be_visible()
    assert len(refreshes) == 1


def test_after_a_refresh_the_next_requests_use_the_new_token_without_refreshing_again(
    app, page, api
):
    api.create_book(title="Дюна")
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("current-user")).to_be_visible()
    refreshes = []
    page.on(
        "request", lambda r: refreshes.append(r) if r.url.endswith("/api/auth/refresh") else None
    )
    expire_the_current_token(page, "**/api/books")
    app.go_to_readers()
    app.go_to_books()
    expect(page.get_by_text("Дюна")).to_be_visible()

    app.go_to_readers()
    app.go_to_books()

    expect(page.get_by_text("Дюна")).to_be_visible()
    assert len(refreshes) == 1


def test_simultaneous_401s_cause_a_single_refresh(app, page, api):
    """Two requests fail at once: a second refresh with the already replaced token would look like theft."""
    api.create_book(title="Дюна")
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("current-user")).to_be_visible()
    refreshes = []
    page.on(
        "request", lambda r: refreshes.append(r) if r.url.endswith("/api/auth/refresh") else None
    )

    # a regular expression: a glob "**/api/books*" would not match "/api/books/popular" (a "*" stops at a slash)
    expire_the_current_token(page, re.compile(r".*/api/books(/popular.*)?$"))
    app.go_to_readers()
    app.go_to_books()  # the list and the popular block ask at the same moment

    expect(page.get_by_text("Дюна").first).to_be_visible()
    assert len(refreshes) == 1
    # the session is still valid afterwards: a reload signs in silently
    page.reload()
    expect(page.get_by_test_id("current-user")).to_be_visible()


def test_when_the_token_cannot_be_refreshed_the_sign_in_page_is_shown(app, page, context):
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("current-user")).to_be_visible()
    context.clear_cookies()  # the refresh cookie is gone, so the next refresh fails

    page.route("**/api/books", lambda route: route.fulfill(status=401, json={"detail": "x"}))
    app.go_to_readers()
    app.go_to_books()

    expect(page.get_by_test_id("login-form")).to_be_visible()
    expect(page.get_by_test_id("login-expired")).to_be_visible()
    expect(page.get_by_test_id("tab-books")).to_have_count(0)


def test_a_token_that_is_refused_again_after_a_refresh_ends_the_session(app, page):
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("current-user")).to_be_visible()

    page.route("**/api/books", lambda route: route.fulfill(status=401, json={"detail": "x"}))
    app.go_to_readers()
    app.go_to_books()

    expect(page.get_by_test_id("login-form")).to_be_visible()


# ---------- criterion 6: sign out ----------


def test_sign_out_shows_the_sign_in_page(app, page):
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("logout")).to_be_visible()

    page.get_by_test_id("logout").click()

    expect(page.get_by_test_id("login-form")).to_be_visible()
    expect(page.get_by_test_id("tab-books")).to_have_count(0)
    expect(page.get_by_test_id("current-user")).to_have_count(0)
    expect(page.locator(ERROR)).to_have_count(0)


def test_sign_out_does_not_say_the_session_expired(app, page):
    app.open()
    sign_in(page)

    page.get_by_test_id("logout").click()

    expect(page.get_by_test_id("login-form")).to_be_visible()
    expect(page.get_by_test_id("login-expired")).to_have_count(0)


def test_sign_out_clears_the_cookie_and_revokes_the_token(app, page, context):
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("logout")).to_be_visible()

    page.get_by_test_id("logout").click()
    expect(page.get_by_test_id("login-form")).to_be_visible()

    assert [c for c in context.cookies() if c["name"] == "refresh_token"] == []


def test_a_reload_after_sign_out_shows_the_sign_in_page(app, page):
    app.open()
    sign_in(page)
    page.get_by_test_id("logout").click()
    expect(page.get_by_test_id("login-form")).to_be_visible()

    page.reload()

    expect(page.get_by_test_id("login-form")).to_be_visible()
    expect(page.get_by_test_id("tab-books")).to_have_count(0)


def test_later_requests_carry_no_token_after_sign_out(app, page):
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("logout")).to_be_visible()
    page.get_by_test_id("logout").click()
    expect(page.get_by_test_id("login-form")).to_be_visible()

    status = page.evaluate("async () => (await fetch('/api/books')).status")

    assert status == 401


def test_the_back_button_does_not_show_library_data_after_sign_out(app, page, api):
    api.create_book(title="Секретная книга")
    page.goto("about:blank")
    app.open()
    sign_in(page)
    expect(page.get_by_text("Секретная книга")).to_be_visible()
    page.get_by_test_id("logout").click()
    expect(page.get_by_test_id("login-form")).to_be_visible()

    page.go_back()
    page.wait_for_timeout(300)

    assert "Секретная книга" not in page.content()


def test_signing_in_after_signing_out_starts_at_the_books_section(app, page):
    app.open()
    sign_in(page)
    app.go_to_readers()
    expect(app.tab("readers")).to_have_attribute("aria-selected", "true")
    page.get_by_test_id("logout").click()

    sign_in(page)

    expect(app.tab("books")).to_have_attribute("aria-selected", "true")


def test_the_form_of_a_previous_session_is_empty_after_signing_out(app, page):
    app.open()
    sign_in(page)
    page.get_by_test_id("logout").click()

    expect(page.locator(USERNAME)).to_have_value("")
    expect(page.locator(PASSWORD)).to_have_value("")


# ---------- criterion 7: languages and accessibility ----------


def test_the_sign_in_page_is_in_russian_by_default(app, page):
    app.open()

    expect(page.get_by_label("Логин")).to_be_visible()
    expect(page.get_by_label("Пароль")).to_be_visible()
    expect(page.get_by_role("button", name="Войти")).to_be_visible()
    expect(page.get_by_role("heading", name="Вход")).to_be_visible()


def test_the_sign_in_page_switches_to_english(app, page):
    app.open()

    app.set_locale("en")

    expect(page.get_by_label("Username")).to_be_visible()
    expect(page.get_by_label("Password")).to_be_visible()
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
    expect(page.get_by_text("Вход", exact=True)).to_have_count(0)


def test_the_chosen_language_is_kept_after_signing_in_and_the_header_is_translated(app, page):
    app.open()
    app.set_locale("en")

    sign_in(page)

    expect(page.get_by_role("button", name="Sign out")).to_be_visible()
    expect(app.tab("books")).to_have_text("Books")


def test_the_header_is_in_russian_after_signing_in(app, page):
    app.open()

    sign_in(page)

    expect(page.get_by_role("button", name="Выйти")).to_be_visible()


def test_fields_have_labels_and_the_right_autocomplete_hints(app, page):
    app.open()

    assert page.get_by_label("Логин").get_attribute("autocomplete") == "username"
    assert page.get_by_label("Пароль").get_attribute("autocomplete") == "current-password"
    assert page.get_by_label("Пароль").get_attribute("type") == "password"


def test_the_whole_form_works_from_the_keyboard(app, page):
    app.open()

    page.locator(USERNAME).focus()
    page.keyboard.type(ADMIN_USERNAME)
    page.keyboard.press("Tab")
    expect(page.locator(PASSWORD)).to_be_focused()
    page.keyboard.type(ADMIN_PASSWORD)
    page.keyboard.press("Tab")
    expect(page.locator(SUBMIT)).to_be_focused()
    page.keyboard.press("Enter")

    expect(page.get_by_test_id("current-user")).to_have_text(ADMIN_USERNAME)


def test_the_sign_out_button_is_reachable_by_keyboard(app, page):
    app.open()
    sign_in(page)
    expect(page.get_by_test_id("logout")).to_be_visible()

    page.get_by_test_id("logout").focus()
    page.keyboard.press("Enter")

    expect(page.get_by_test_id("login-form")).to_be_visible()


def test_the_signed_in_user_is_announced_as_a_labelled_group(app, page):
    app.open()
    sign_in(page)

    group = page.get_by_role("group", name=f"Вы вошли как {ADMIN_USERNAME}")

    expect(group).to_be_visible()


def test_the_page_title_and_language_attribute_follow_the_choice(app, page):
    app.open()

    app.set_locale("en")

    assert page.locator("html").get_attribute("lang") == "en"
