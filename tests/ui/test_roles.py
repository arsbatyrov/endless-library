"""AUTH-014: the interface shows only what the role allows (acceptance criteria 1-5).

reader: the catalogue and the ranking (read only) and their own loans; librarian: catalogue, readers and loans;
admin: everything, including the users. Sections are addressable by `#books`, `#readers`, `#loans`, `#users`;
asking for a section the role does not have redirects to an allowed one without any request to the API for it.
Every test here starts anonymous and signs in as the role it needs with the `as_role` fixture.
"""

import re
from datetime import UTC, datetime

import pytest
from playwright.sync_api import Page, expect
from sqlalchemy import text

from tests.ui.conftest import ADMIN_USERNAME

pytestmark = pytest.mark.anonymous

ALL_SECTIONS = ["books", "readers", "loans", "users"]


def visible_tabs(page: Page) -> list[str]:
    ids = page.locator('[role="tab"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))"
    )
    return [i.removeprefix("tab-") for i in ids]


def record_requests(page: Page) -> list[str]:
    seen: list[str] = []
    page.on(
        "request", lambda r: seen.append(r.url.split("/api", 1)[1]) if "/api/" in r.url else None
    )
    return seen


# ---------- criterion 1: reader ----------


def test_reader_sees_only_the_catalogue_and_their_loans(app, page, as_role):
    as_role("reader")
    app.open()

    expect(app.tab("books")).to_be_visible()
    assert visible_tabs(page) == ["books", "loans"]


def test_reader_sees_the_catalogue_and_the_ranking(app, page, as_role, api):
    book = api.create_book(title="Дюна")
    other = api.create_reader(name="Someone")
    api.issue_loan(book["id"], other["id"])
    as_role("reader")

    app.open()

    expect(app.books.row("Дюна")).to_be_visible()
    expect(page.get_by_test_id("popular-item")).to_have_count(1)


def test_reader_has_no_buttons_to_change_the_catalogue(app, page, as_role, api):
    api.create_book(title="Дюна")
    as_role("reader")

    app.open()
    expect(app.books.row("Дюна")).to_be_visible()

    expect(page.get_by_test_id("books-add")).to_have_count(0)
    expect(page.get_by_test_id("book-edit")).to_have_count(0)
    expect(page.get_by_test_id("book-delete")).to_have_count(0)
    expect(page.get_by_role("columnheader", name="Действия")).to_have_count(0)


def test_reader_sees_a_catalogue_without_actions_even_when_it_is_empty(app, page, as_role):
    as_role("reader")

    app.open()

    expect(page.get_by_test_id("books-empty")).to_be_visible()
    expect(page.get_by_test_id("books-add")).to_have_count(0)


def test_reader_sees_only_their_own_loans(app, page, as_role, api):
    mine = api.create_book(title="Моя книга")
    theirs = api.create_book(title="Чужая книга")
    card = as_role("reader")["reader_id"]
    other = api.create_reader(name="Someone else")
    api.issue_loan(mine["id"], card)
    api.issue_loan(theirs["id"], other["id"])

    app.open()
    app.tab("loans").click()

    expect(page.get_by_test_id("loan-row")).to_have_count(1)
    expect(page.get_by_test_id("loan-book")).to_have_text("Моя книга")
    expect(page.get_by_text("Чужая книга")).to_have_count(0)


def test_reader_loans_have_no_return_or_issue_controls(app, page, as_role, api):
    book = api.create_book(title="Моя книга")
    card = as_role("reader")["reader_id"]
    api.issue_loan(book["id"], card)

    app.open()
    app.tab("loans").click()

    expect(page.get_by_test_id("loan-row")).to_have_count(1)
    expect(page.get_by_test_id("loan-return")).to_have_count(0)
    expect(page.get_by_test_id("loans-reader")).to_have_count(0)
    expect(page.get_by_test_id("loan-form")).to_have_count(0)
    expect(page.get_by_test_id("loans-issue")).to_have_count(0)


def test_reader_with_no_loans_sees_a_friendly_empty_state(app, page, as_role):
    as_role("reader")

    app.open()
    app.tab("loans").click()

    expect(page.get_by_test_id("my-loans-empty")).to_have_text("У вас нет книг на руках")


def test_reader_loans_show_the_due_date_and_overdue_mark(app, page, as_role, api, ui_stack):
    book = api.create_book(title="Моя книга")
    card = as_role("reader")["reader_id"]
    loan = api.issue_loan(book["id"], card)
    with ui_stack.engine.begin() as conn:
        conn.execute(
            text("UPDATE loans SET due_at = :due WHERE id = :id"),
            {"due": datetime(2020, 1, 1, tzinfo=UTC), "id": loan["id"]},
        )

    app.open()
    app.tab("loans").click()

    expect(page.get_by_test_id("loan-due")).to_contain_text("01.01.2020")
    expect(page.get_by_test_id("loan-overdue")).to_be_visible()


def test_reader_loans_page_is_translated(app, page, as_role):
    as_role("reader")
    app.open()
    app.tab("loans").click()

    app.set_locale("en")

    expect(page.get_by_test_id("my-loans-empty")).to_have_text("You have no books on loan")


def test_reader_never_requests_readers_or_users(app, page, as_role, api):
    api.create_book(title="Дюна")
    as_role("reader")
    seen = record_requests(page)

    app.open()
    expect(app.books.row("Дюна")).to_be_visible()
    app.tab("loans").click()
    expect(page.get_by_test_id("my-loans-empty")).to_be_visible()

    assert not [u for u in seen if re.match(r"/(readers$|users|loans)", u)], seen
    assert any(re.match(r"/readers/\d+/loans", u) for u in seen)


# ---------- criterion 2: librarian ----------


def test_librarian_sees_catalogue_readers_and_loans_but_not_users(app, page, as_role):
    as_role("librarian")

    app.open()

    expect(app.tab("books")).to_be_visible()
    assert visible_tabs(page) == ["books", "readers", "loans"]


def test_librarian_can_change_the_catalogue(app, page, as_role, api):
    api.create_book(title="Дюна")
    as_role("librarian")

    app.open()

    expect(page.get_by_test_id("books-add")).to_be_visible()
    expect(page.get_by_test_id("book-edit")).to_be_visible()
    expect(page.get_by_test_id("book-delete")).to_be_visible()


def test_librarian_works_with_readers_and_loans(app, page, as_role, api):
    api.create_book(title="Дюна")
    reader = api.create_reader(name="Анна")
    as_role("librarian")

    app.open()
    app.tab("readers").click()
    expect(page.get_by_text("Анна")).to_be_visible()
    app.tab("loans").click()
    page.get_by_test_id("loans-reader").select_option(str(reader["id"]))

    expect(page.get_by_test_id("loan-form")).to_be_visible()


# ---------- criterion 3: admin ----------


def test_admin_sees_every_section_including_users(app, page, as_role):
    as_role("admin")

    app.open()

    expect(app.tab("users")).to_be_visible()
    assert visible_tabs(page) == ALL_SECTIONS


def test_admin_users_page_lists_the_accounts(app, page, as_role):
    as_role("admin")
    app.open()

    app.tab("users").click()

    expect(page.get_by_test_id("user-row").first).to_be_visible()
    expect(page.get_by_test_id("users-table")).to_contain_text(ADMIN_USERNAME)
    expect(page.get_by_test_id("users-table")).not_to_contain_text("argon2")


def test_users_page_shows_roles_and_status_in_the_chosen_language(app, page, as_role):
    as_role("admin")
    app.open()
    app.tab("users").click()
    expect(page.get_by_test_id("users-table")).to_contain_text("Администратор")

    app.set_locale("en")

    expect(page.get_by_test_id("users-table")).to_contain_text("Administrator")


# ---------- criterion 4: direct access to a section the role does not have ----------


@pytest.mark.parametrize(
    ("role", "hash_", "expected_tab"),
    [
        ("reader", "#readers", "books"),
        ("reader", "#users", "books"),
        ("librarian", "#users", "books"),
        ("reader", "#nonsense", "books"),
    ],
)
def test_a_forbidden_section_redirects_to_an_allowed_one(
    app, page, as_role, role, hash_, expected_tab
):
    as_role(role)
    seen = record_requests(page)

    page.goto(f"/{hash_}")

    expect(app.tab(expected_tab)).to_have_attribute("aria-selected", "true")
    expect(page).to_have_url(re.compile(rf"#{expected_tab}$"))
    assert not [u for u in seen if u.startswith(("/readers", "/users"))], seen


def test_a_reader_asking_for_users_never_causes_a_users_request(app, page, as_role):
    as_role("reader")
    seen = record_requests(page)

    page.goto("/#users")
    expect(app.tab("books")).to_have_attribute("aria-selected", "true")
    page.wait_for_timeout(300)

    assert not [u for u in seen if "/users" in u], seen


def test_an_allowed_section_opens_directly(app, page, as_role):
    as_role("librarian")

    page.goto("/#readers")

    expect(app.tab("readers")).to_have_attribute("aria-selected", "true")


def test_a_reader_may_open_their_loans_directly(app, page, as_role):
    as_role("reader")

    page.goto("/#loans")

    expect(app.tab("loans")).to_have_attribute("aria-selected", "true")


def test_admin_may_open_users_directly(app, page, as_role):
    as_role("admin")

    page.goto("/#users")

    expect(app.tab("users")).to_have_attribute("aria-selected", "true")


def test_changing_the_hash_by_hand_to_a_forbidden_section_redirects(app, page, as_role):
    as_role("reader")
    app.open()
    expect(app.tab("books")).to_be_visible()
    seen = record_requests(page)

    page.evaluate("location.hash = '#readers'")

    expect(app.tab("books")).to_have_attribute("aria-selected", "true")
    expect(page).to_have_url(re.compile(r"#books$"))
    assert not [u for u in seen if u.startswith("/readers")], seen


def test_clicking_a_tab_puts_the_section_in_the_address(app, page, as_role):
    as_role("librarian")
    app.open()

    app.tab("loans").click()

    expect(page).to_have_url(re.compile(r"#loans$"))


def test_a_reload_keeps_the_section(app, page, as_role):
    as_role("librarian")
    app.open()
    app.tab("readers").click()

    page.reload()

    expect(app.tab("readers")).to_have_attribute("aria-selected", "true")


def test_the_back_button_goes_to_the_previous_section(app, page, as_role):
    as_role("librarian")
    app.open()
    app.tab("readers").click()
    app.tab("loans").click()

    page.go_back()

    expect(app.tab("readers")).to_have_attribute("aria-selected", "true")


def test_a_deep_link_is_kept_through_signing_in(app, page, ui_stack, as_role):
    """Visiting #readers without a session shows the sign-in page, and after signing in the section opens."""
    account = as_role("librarian", inject_cookie=False)

    page.goto("/#readers")
    expect(page.get_by_test_id("login-form")).to_be_visible()
    page.fill("[data-testid=login-username]", account["username"])
    page.fill("[data-testid=login-password]", account["password"])
    page.click("[data-testid=login-submit]")

    expect(app.tab("readers")).to_have_attribute("aria-selected", "true")


def test_a_deep_link_to_a_forbidden_section_after_signing_in_redirects(app, page, as_role):
    account = as_role("reader", inject_cookie=False)

    page.goto("/#readers")
    page.fill("[data-testid=login-username]", account["username"])
    page.fill("[data-testid=login-password]", account["password"])
    page.click("[data-testid=login-submit]")

    expect(app.tab("books")).to_have_attribute("aria-selected", "true")
    assert visible_tabs(page) == ["books", "loans"]


def test_signing_out_resets_the_section(app, page, as_role):
    as_role("librarian")
    app.open()
    app.tab("readers").click()

    page.get_by_test_id("logout").click()
    expect(page.get_by_test_id("login-form")).to_be_visible()

    expect(page).to_have_url(re.compile(r"#books$"))


# ---------- criterion 5: the server refuses an action ----------


def test_a_403_on_an_action_shows_the_server_message_and_the_interface_keeps_working(
    app, page, as_role, api
):
    api.create_book(title="Дюна")
    as_role("admin")
    app.open()
    expect(app.books.row("Дюна")).to_be_visible()
    page.route(
        "**/api/books",
        lambda route: (
            route.fulfill(status=403, json={"detail": "Not enough permissions"})
            if route.request.method == "POST"
            else route.continue_()
        ),
    )

    page.get_by_test_id("books-add").click()
    page.get_by_test_id("book-form-title").fill("Новая")
    page.get_by_test_id("book-form-author").fill("Автор")
    page.get_by_test_id("book-form-submit").click()

    expect(page.get_by_test_id("book-form-error")).to_have_text("Not enough permissions")
    # still alive: the form can be closed, other actions work, the list is intact
    page.get_by_test_id("book-form-cancel").click()
    expect(app.books.row("Дюна")).to_be_visible()
    page.get_by_test_id("books-add").click()
    expect(page.get_by_test_id("book-form")).to_be_visible()


def test_a_403_on_delete_shows_the_message_and_keeps_the_list(app, page, as_role, api):
    api.create_book(title="Дюна")
    as_role("admin")
    app.open()
    expect(app.books.row("Дюна")).to_be_visible()
    page.route(
        "**/api/books/*",
        lambda route: (
            route.fulfill(status=403, json={"detail": "Not enough permissions"})
            if route.request.method == "DELETE"
            else route.continue_()
        ),
    )

    page.get_by_test_id("book-delete").click()
    page.get_by_test_id("book-delete-confirm").click()

    expect(page.get_by_test_id("books-action-error")).to_have_text("Not enough permissions")
    expect(app.books.row("Дюна")).to_be_visible()
    expect(app.tab("books")).to_be_visible()


def test_the_403_message_is_not_translated(app, page, as_role, api):
    api.create_book(title="Дюна")
    as_role("admin")
    app.open()
    expect(app.books.row("Дюна")).to_be_visible()
    page.route(
        "**/api/books/*",
        lambda route: (
            route.fulfill(status=403, json={"detail": "Not enough permissions"})
            if route.request.method == "DELETE"
            else route.continue_()
        ),
    )

    page.get_by_test_id("book-delete").click()
    page.get_by_test_id("book-delete-confirm").click()

    assert page.locator("html").get_attribute("lang") == "ru"
    expect(page.get_by_test_id("books-action-error")).to_have_text("Not enough permissions")


def test_a_403_makes_the_interface_adopt_the_role_the_server_now_knows(
    app, page, as_role, ui_stack, api
):
    """The role changed on the server after the page was opened: the first refusal updates what the page shows."""
    account = as_role("admin")
    card = api.create_reader(name="Читатель E2E")
    app.open()
    expect(app.tab("users")).to_be_visible()
    with ui_stack.engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET role = 'reader', reader_id = :card WHERE id = :id"),
            {"card": card["id"], "id": account["id"]},
        )

    app.tab("users").click()  # the server answers 403: a reader may not list users

    expect(app.tab("users")).to_have_count(0)
    expect(app.tab("books")).to_have_attribute("aria-selected", "true")
    assert visible_tabs(page) == ["books", "loans"]
    expect(page.get_by_test_id("books-add")).to_have_count(0)


def test_a_load_error_with_403_shows_the_message_and_a_retry(app, page, as_role):
    as_role("librarian")
    app.open()
    page.route(
        "**/api/readers",
        lambda route: route.fulfill(status=403, json={"detail": "Not enough permissions"}),
    )

    app.tab("readers").click()

    expect(page.get_by_test_id("readers-error")).to_contain_text("Not enough permissions")
    expect(page.get_by_test_id("readers-retry")).to_be_visible()
    expect(app.tab("books")).to_be_visible()


def test_the_signed_in_user_is_still_shown_after_a_403(app, page, as_role, api):
    api.create_book(title="Дюна")
    account = as_role("admin")
    app.open()
    expect(app.books.row("Дюна")).to_be_visible()
    page.route(
        "**/api/books/*",
        lambda route: (
            route.fulfill(status=403, json={"detail": "Not enough permissions"})
            if route.request.method == "DELETE"
            else route.continue_()
        ),
    )

    page.get_by_test_id("book-delete").click()
    page.get_by_test_id("book-delete-confirm").click()
    expect(page.get_by_test_id("books-action-error")).to_be_visible()

    expect(page.get_by_test_id("current-user")).to_have_text(account["username"])
    expect(page.get_by_test_id("logout")).to_be_visible()


# ---------- AUTH-019: the reader sees their own card ----------


def test_the_reader_sees_their_own_card_above_the_loans(app, page, as_role, api):
    card = as_role("reader")["reader_id"]
    api.create_book(title="Дюна")

    app.open()
    app.tab("loans").click()

    expect(page.get_by_test_id("my-card-name")).to_have_text("Читатель E2E")
    expect(page.get_by_test_id("my-card-email")).to_contain_text("@example.com")
    assert card


def test_the_card_is_fetched_by_its_id_and_the_readers_list_is_never_requested(app, page, as_role):
    card_id = as_role("reader")["reader_id"]
    seen = record_requests(page)

    app.open()
    app.tab("loans").click()
    expect(page.get_by_test_id("my-card-name")).to_be_visible()

    assert f"/readers/{card_id}" in seen
    assert "/readers" not in seen


def test_the_card_block_is_translated(app, page, as_role):
    as_role("reader")
    app.open()
    app.tab("loans").click()
    expect(page.get_by_test_id("my-card")).to_contain_text("Моя карточка")

    app.set_locale("en")

    expect(page.get_by_test_id("my-card")).to_contain_text("My card")
    expect(page.get_by_test_id("my-card")).to_contain_text("Name")


def test_a_failing_card_request_shows_an_error_with_a_retry_and_keeps_the_loans(app, page, as_role):
    card_id = as_role("reader")["reader_id"]
    page.route(
        f"**/api/readers/{card_id}",
        lambda route: route.fulfill(status=500, json={"detail": "boom"}),
    )
    app.open()
    app.tab("loans").click()

    expect(page.get_by_test_id("my-card-error")).to_contain_text("boom")
    expect(page.get_by_test_id("my-loans-empty")).to_be_visible()
    page.unroute(f"**/api/readers/{card_id}")
    page.get_by_test_id("my-card-retry").click()
    expect(page.get_by_test_id("my-card-name")).to_be_visible()


def test_staff_do_not_get_the_own_card_block_on_the_loans_page(app, page, as_role):
    as_role("librarian")
    app.open()

    app.tab("loans").click()

    expect(page.get_by_test_id("my-card")).to_have_count(0)
