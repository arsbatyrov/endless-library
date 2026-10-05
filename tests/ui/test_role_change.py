"""AUTH-020: an admin changes the role of an account to any role, on the Users page.

The form offers the three roles (the current one is preselected and saving is disabled until it changes); for the
reader role it asks for a free reader card; leaving the reader role warns that the link to the card is removed. A
librarian never sees the action. The server's refusals are shown as they are.
"""

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import ADMIN_USERNAME
from tests.ui.test_accounts import (
    LAST_ADMIN_MESSAGE,
    PASSWORD,
    open_readers,
    open_users,
    reader_row,
    user_row,
)


@pytest.fixture
def librarian_session(as_role):
    return as_role("librarian")


def role_form_open(page: Page, username: str) -> None:
    user_row(page, username).get_by_test_id("user-role-change").click()
    expect(page.get_by_test_id("role-form")).to_be_visible()


def test_the_admin_has_a_change_role_button_for_every_account(app, page, api):
    api.create_account("lena", PASSWORD, "librarian")
    open_users(app)

    expect(user_row(page, "lena").get_by_test_id("user-role-change")).to_be_visible()
    expect(user_row(page, ADMIN_USERNAME).get_by_test_id("user-role-change")).to_be_visible()


def test_the_role_form_starts_with_the_current_role_and_nothing_to_save(app, page, api):
    api.create_account("lena", PASSWORD, "librarian")
    open_users(app)

    role_form_open(page, "lena")

    expect(page.get_by_test_id("role-form-role")).to_have_value("librarian")
    expect(page.get_by_test_id("role-form-submit")).to_be_disabled()
    expect(page.get_by_label("Новая роль", exact=True)).to_be_visible()


def test_a_librarian_becomes_an_admin(app, page, api):
    api.create_account("lena", PASSWORD, "librarian")
    open_users(app)
    role_form_open(page, "lena")

    page.get_by_test_id("role-form-role").select_option("admin")
    page.get_by_test_id("role-form-submit").click()

    expect(page.get_by_test_id("users-notice")).to_have_text(
        "Роль пользователя «lena» изменена: Администратор"
    )
    expect(user_row(page, "lena").get_by_test_id("user-role")).to_have_text("Администратор")
    expect(page.get_by_test_id("role-form")).to_have_count(0)


def test_an_admin_becomes_a_librarian_when_another_admin_exists(app, page, api):
    api.create_account("second", PASSWORD, "admin")
    open_users(app)
    role_form_open(page, "second")

    page.get_by_test_id("role-form-role").select_option("librarian")
    page.get_by_test_id("role-form-submit").click()

    expect(user_row(page, "second").get_by_test_id("user-role")).to_have_text("Библиотекарь")


def test_a_librarian_becomes_a_reader_with_a_free_card(app, page, api):
    api.create_account("lena", PASSWORD, "librarian")
    taken = api.create_reader(name="Чужая карточка")
    api.create_account("taken", PASSWORD, "reader", taken["id"])
    free = api.create_reader(name="Свободная карточка")
    open_users(app)
    role_form_open(page, "lena")

    expect(page.get_by_test_id("role-form-reader")).to_have_count(0)
    page.get_by_test_id("role-form-role").select_option("reader")
    options = page.get_by_test_id("role-form-reader").locator("option").all_inner_texts()
    assert any("Свободная карточка" in o for o in options)
    assert not any("Чужая карточка" in o for o in options)
    page.get_by_test_id("role-form-reader").select_option(str(free["id"]))
    page.get_by_test_id("role-form-submit").click()

    expect(user_row(page, "lena").get_by_test_id("user-role")).to_have_text("Читатель")
    expect(user_row(page, "lena").get_by_test_id("user-card")).to_have_text("Свободная карточка")


def test_a_reader_becomes_a_librarian_and_the_card_link_is_removed(app, page, api):
    card = api.create_reader(name="Анна Иванова")
    api.create_account("anna", PASSWORD, "reader", card["id"])
    open_users(app)
    role_form_open(page, "anna")

    page.get_by_test_id("role-form-role").select_option("librarian")
    expect(page.get_by_test_id("role-form-warning")).to_be_visible()
    page.get_by_test_id("role-form-submit").click()

    expect(user_row(page, "anna").get_by_test_id("user-role")).to_have_text("Библиотекарь")
    expect(user_row(page, "anna").get_by_test_id("user-card")).to_have_text("—")


def test_the_card_warning_appears_only_when_a_reader_leaves_the_reader_role(app, page, api):
    api.create_account("lena", PASSWORD, "librarian")
    open_users(app)
    role_form_open(page, "lena")

    page.get_by_test_id("role-form-role").select_option("admin")

    expect(page.get_by_test_id("role-form-warning")).to_have_count(0)


def test_a_reader_without_a_chosen_card_is_reported_under_the_card_field(app, page, api):
    api.create_account("lena", PASSWORD, "librarian")
    api.create_reader(name="Свободная")
    open_users(app)
    role_form_open(page, "lena")

    page.get_by_test_id("role-form-role").select_option("reader")
    page.get_by_test_id("role-form-submit").click()

    expect(page.get_by_test_id("role-form-error-reader_id")).to_have_text(
        "A reader account must be linked to a reader card"
    )
    expect(page.get_by_test_id("role-form")).to_be_visible()


def test_the_last_active_admin_cannot_be_demoted_and_the_refusal_is_shown(app, page):
    open_users(app)
    role_form_open(page, ADMIN_USERNAME)

    page.get_by_test_id("role-form-role").select_option("librarian")
    page.get_by_test_id("role-form-submit").click()

    expect(page.get_by_test_id("users-action-error")).to_have_text(LAST_ADMIN_MESSAGE)
    expect(user_row(page, ADMIN_USERNAME).get_by_test_id("user-role")).to_have_text("Администратор")


def test_the_role_form_can_be_cancelled_without_a_request(app, page, api):
    account = api.create_account("lena", PASSWORD, "librarian")
    open_users(app)
    requests = []
    page.on(
        "request",
        lambda r: (
            requests.append(r.method) if r.url.endswith(f"/api/users/{account['id']}") else None
        ),
    )
    role_form_open(page, "lena")
    page.get_by_test_id("role-form-role").select_option("admin")

    page.get_by_test_id("role-form-cancel").click()

    expect(page.get_by_test_id("role-form")).to_have_count(0)
    expect(user_row(page, "lena").get_by_test_id("user-role")).to_have_text("Библиотекарь")
    assert "PATCH" not in requests


def test_the_change_is_really_saved_on_the_server(app, page, api):
    account = api.create_account("lena", PASSWORD, "librarian")
    open_users(app)
    role_form_open(page, "lena")

    page.get_by_test_id("role-form-role").select_option("admin")
    page.get_by_test_id("role-form-submit").click()
    expect(page.get_by_test_id("users-notice")).to_be_visible()

    assert [u["role"] for u in api.accounts() if u["id"] == account["id"]] == ["admin"]


def test_an_admin_who_demotes_themselves_loses_the_admin_screens_at_once(app, page, api):
    api.create_account("second", PASSWORD, "admin")
    open_users(app)
    role_form_open(page, ADMIN_USERNAME)

    page.get_by_test_id("role-form-role").select_option("librarian")
    page.get_by_test_id("role-form-submit").click()

    expect(app.tab("users")).to_have_count(0)
    expect(app.tab("books")).to_have_attribute("aria-selected", "true")
    expect(page.get_by_test_id("current-user")).to_have_text(ADMIN_USERNAME)


def test_a_403_on_a_role_change_shows_the_server_message(app, page, api):
    api.create_account("lena", PASSWORD, "librarian")
    open_users(app)
    page.route(
        "**/api/users/*",
        lambda route: (
            route.fulfill(status=403, json={"detail": "Not enough permissions"})
            if route.request.method == "PATCH"
            else route.continue_()
        ),
    )
    role_form_open(page, "lena")

    page.get_by_test_id("role-form-role").select_option("admin")
    page.get_by_test_id("role-form-submit").click()

    expect(page.get_by_test_id("users-action-error")).to_have_text("Not enough permissions")


def test_the_role_form_and_the_notice_are_translated(app, page, api):
    api.create_account("lena", PASSWORD, "librarian")
    open_users(app)
    app.set_locale("en")

    role_form_open(page, "lena")

    expect(page.get_by_label("New role", exact=True)).to_be_visible()
    expect(page.get_by_test_id("role-form-role")).to_contain_text("Administrator")
    page.get_by_test_id("role-form-role").select_option("admin")
    page.get_by_test_id("role-form-submit").click()
    expect(page.get_by_test_id("users-notice")).to_have_text(
        "The role of “lena” was changed: Administrator"
    )


def test_the_change_role_button_has_an_accessible_name(app, page, api):
    api.create_account("lena", PASSWORD, "librarian")
    open_users(app)

    expect(page.get_by_role("button", name="Сменить роль «lena»")).to_be_visible()


def test_a_librarian_has_no_change_role_button_in_readers(app, page, api, librarian_session):
    card = api.create_reader(name="Анна Иванова")
    api.create_account("anna", PASSWORD, "reader", card["id"])
    open_readers(app)

    expect(reader_row(page, "Анна Иванова").get_by_test_id("user-disable")).to_be_visible()
    expect(reader_row(page, "Анна Иванова").get_by_test_id("user-role-change")).to_have_count(0)


def test_the_admin_can_change_the_role_of_a_reader_account_from_the_readers_page_too(
    app, page, api
):
    card = api.create_reader(name="Анна Иванова")
    api.create_account("anna", PASSWORD, "reader", card["id"])
    open_readers(app)

    reader_row(page, "Анна Иванова").get_by_test_id("user-role-change").click()
    page.get_by_test_id("role-form-role").select_option("librarian")
    page.get_by_test_id("role-form-submit").click()

    expect(page.get_by_test_id("readers-notice")).to_have_text(
        "Роль пользователя «anna» изменена: Библиотекарь"
    )
    expect(reader_row(page, "Анна Иванова").get_by_test_id("reader-create-account")).to_be_visible()
