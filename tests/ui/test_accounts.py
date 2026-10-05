"""AUTH-015: managing accounts on the site (acceptance criteria 1-5).

The admin works in "Users": a table with Create, Disable or Enable, Reset password. A librarian works in "Readers":
a card without an account has "Create account" (only the role reader is offered), a card with one shows the login and
the status with the same Disable/Enable and Reset password. Dangerous actions ask for confirmation, server errors are
shown under the field they belong to as the server wrote them, and success messages follow the interface language.
"""

import httpx2 as httpx
import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import ADMIN_USERNAME

PASSWORD = "correct horse"
NEW_PASSWORD = "battery staple"
LAST_ADMIN_MESSAGE = "The last active administrator cannot be disabled or demoted"


@pytest.fixture
def can_sign_in(ui_stack):
    def check(username: str, password: str) -> bool:
        response = httpx.post(
            f"{ui_stack.api_url}/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        return response.status_code == 200

    return check


def user_row(page: Page, username: str):
    return page.get_by_test_id("user-row").filter(has_text=username)


def fill_account(page: Page, username=None, password=None, role=None, reader=None) -> None:
    if username is not None:
        page.get_by_test_id("account-form-username").fill(username)
    if password is not None:
        page.get_by_test_id("account-form-password").fill(password)
    if role is not None:
        page.get_by_test_id("account-form-role").select_option(role)
    if reader is not None:
        page.get_by_test_id("account-form-reader").select_option(str(reader))


def open_users(app) -> None:
    app.open()
    app.tab("users").click()
    expect(app.page.get_by_test_id("users-table")).to_be_visible()


# ---------- criterion 1: the admin's table and buttons ----------


def test_the_table_shows_login_role_and_status_with_the_buttons(app, page, api):
    api.create_account("lena", PASSWORD, "librarian")
    open_users(app)

    row = user_row(page, "lena")

    expect(row.get_by_test_id("user-role")).to_have_text("Библиотекарь")
    expect(row.get_by_test_id("user-status")).to_have_text("Активен")
    expect(row.get_by_test_id("user-disable")).to_be_visible()
    expect(row.get_by_test_id("user-reset")).to_be_visible()
    expect(page.get_by_test_id("users-add")).to_be_visible()


def test_a_disabled_account_offers_enable_instead_of_disable(app, page, api):
    account = api.create_account("lena", PASSWORD, "librarian")
    api.set_account_active(account["id"], False)
    open_users(app)

    row = user_row(page, "lena")

    expect(row.get_by_test_id("user-status")).to_have_text("Отключён")
    expect(row.get_by_test_id("user-enable")).to_be_visible()
    expect(row.get_by_test_id("user-disable")).to_have_count(0)


def test_the_table_shows_the_reader_card_of_a_reader_account(app, page, api):
    card = api.create_reader(name="Анна Иванова")
    api.create_account("anna", PASSWORD, "reader", card["id"])
    open_users(app)

    expect(user_row(page, "anna").get_by_test_id("user-card")).to_have_text("Анна Иванова")


# ---------- creating an account ----------


@pytest.mark.parametrize(
    ("role", "label"), [("librarian", "Библиотекарь"), ("admin", "Администратор")]
)
def test_admin_creates_a_staff_account(app, page, can_sign_in, role, label):
    open_users(app)

    page.get_by_test_id("users-add").click()
    fill_account(page, "newbie", PASSWORD, role)
    page.get_by_test_id("account-form-submit").click()

    expect(page.get_by_test_id("users-notice")).to_have_text("Пользователь «newbie» создан")
    expect(user_row(page, "newbie").get_by_test_id("user-role")).to_have_text(label)
    expect(page.get_by_test_id("account-form")).to_have_count(0)
    assert can_sign_in("newbie", PASSWORD)


def test_admin_creates_a_reader_account_linked_to_a_card(app, page, api, can_sign_in):
    api.create_reader(name="Анна Иванова")
    card = api.create_reader(name="Борис Петров")
    open_users(app)

    page.get_by_test_id("users-add").click()
    fill_account(page, "boris", PASSWORD, "reader", card["id"])
    page.get_by_test_id("account-form-submit").click()

    expect(user_row(page, "boris").get_by_test_id("user-card")).to_have_text("Борис Петров")
    assert can_sign_in("boris", PASSWORD)


def test_the_card_list_offers_only_cards_without_an_account(app, page, api):
    api.create_reader(name="Свободная карточка")
    taken = api.create_reader(name="Занятая карточка")
    api.create_account("taken", PASSWORD, "reader", taken["id"])
    open_users(app)

    page.get_by_test_id("users-add").click()
    page.get_by_test_id("account-form-role").select_option("reader")

    options = page.get_by_test_id("account-form-reader").locator("option").all_inner_texts()
    assert any("Свободная карточка" in o for o in options)
    assert not any("Занятая карточка" in o for o in options)


def test_the_card_field_appears_only_for_the_reader_role(app, page):
    open_users(app)
    page.get_by_test_id("users-add").click()

    expect(page.get_by_test_id("account-form-reader")).to_have_count(0)
    fill_account(page, role="reader")
    expect(page.get_by_test_id("account-form-reader")).to_be_visible()
    fill_account(page, role="admin")
    expect(page.get_by_test_id("account-form-reader")).to_have_count(0)


# ---------- criterion 2: server errors under the fields ----------


def test_a_short_password_is_reported_under_the_password_field(app, page, can_sign_in):
    open_users(app)
    page.get_by_test_id("users-add").click()

    fill_account(page, "newbie", "short", "librarian")
    page.get_by_test_id("account-form-submit").click()

    expect(page.get_by_test_id("account-form-error-password")).to_have_text(
        "String should have at least 8 characters"
    )
    assert not can_sign_in("newbie", "short")


@pytest.mark.parametrize("taken", [ADMIN_USERNAME, ADMIN_USERNAME.upper()])
def test_a_taken_login_is_reported_under_the_login_field(app, page, taken):
    open_users(app)
    page.get_by_test_id("users-add").click()

    fill_account(page, taken, PASSWORD, "librarian")
    page.get_by_test_id("account-form-submit").click()

    expect(page.get_by_test_id("account-form-error-username")).to_have_text(
        "This login is already taken"
    )


def test_a_password_equal_to_the_login_is_refused_under_the_password_field(app, page):
    open_users(app)
    page.get_by_test_id("users-add").click()

    fill_account(page, "administrator", "ADMINISTRATOR", "librarian")
    page.get_by_test_id("account-form-submit").click()

    expect(page.get_by_test_id("account-form-error-password")).to_contain_text("login")


def test_a_reader_without_a_card_is_reported_under_the_card_field(app, page, api):
    api.create_reader(name="Анна Иванова")
    open_users(app)
    page.get_by_test_id("users-add").click()

    fill_account(page, "boris", PASSWORD, "reader")
    page.get_by_test_id("account-form-submit").click()

    expect(page.get_by_test_id("account-form-error-reader_id")).to_have_text(
        "A reader account must be linked to a reader card"
    )


def test_the_typed_values_are_kept_after_an_error(app, page):
    open_users(app)
    page.get_by_test_id("users-add").click()

    fill_account(page, "newbie", "short", "librarian")
    page.get_by_test_id("account-form-submit").click()
    expect(page.get_by_test_id("account-form-error-password")).to_be_visible()

    expect(page.get_by_test_id("account-form-username")).to_have_value("newbie")
    expect(page.get_by_test_id("account-form-password")).to_have_value("short")
    expect(page.get_by_test_id("account-form-role")).to_have_value("librarian")


def test_the_form_can_be_cancelled_and_the_password_field_is_masked(app, page):
    open_users(app)
    page.get_by_test_id("users-add").click()

    assert page.get_by_test_id("account-form-password").get_attribute("type") == "password"
    assert (
        page.get_by_test_id("account-form-password").get_attribute("autocomplete") == "new-password"
    )
    page.get_by_test_id("account-form-cancel").click()

    expect(page.get_by_test_id("account-form")).to_have_count(0)


def test_the_form_fields_are_labelled(app, page):
    open_users(app)
    page.get_by_test_id("users-add").click()

    expect(page.get_by_label("Логин", exact=True)).to_be_visible()
    expect(page.get_by_label("Пароль", exact=True)).to_be_visible()
    expect(page.get_by_label("Роль", exact=True)).to_be_visible()


def test_the_password_is_never_shown_in_the_page_after_creating(app, page):
    open_users(app)
    page.get_by_test_id("users-add").click()

    fill_account(page, "newbie", "visible-secret-9", "librarian")
    page.get_by_test_id("account-form-submit").click()
    expect(page.get_by_test_id("users-notice")).to_be_visible()

    assert "visible-secret-9" not in page.locator("body").inner_text()
    assert "visible-secret-9" not in page.content()


# ---------- disabling and enabling: a confirmation for the dangerous one ----------


def test_disabling_asks_for_confirmation_and_can_be_cancelled(app, page, api):
    account = api.create_account("lena", PASSWORD, "librarian")
    open_users(app)
    requests = []
    page.on(
        "request",
        lambda r: (
            requests.append(r.method) if r.url.endswith(f"/api/users/{account['id']}") else None
        ),
    )

    user_row(page, "lena").get_by_test_id("user-disable").click()
    expect(page.get_by_test_id("user-disable-question")).to_contain_text("lena")
    page.get_by_test_id("user-disable-cancel").click()

    expect(user_row(page, "lena").get_by_test_id("user-status")).to_have_text("Активен")
    assert "PATCH" not in requests


def test_confirming_disables_the_account_and_it_cannot_sign_in(app, page, api, can_sign_in):
    api.create_account("lena", PASSWORD, "librarian")
    open_users(app)

    user_row(page, "lena").get_by_test_id("user-disable").click()
    page.get_by_test_id("user-disable-confirm").click()

    expect(user_row(page, "lena").get_by_test_id("user-status")).to_have_text("Отключён")
    expect(page.get_by_test_id("users-notice")).to_have_text("Пользователь «lena» отключён")
    assert not can_sign_in("lena", PASSWORD)


def test_enabling_needs_no_confirmation(app, page, api, can_sign_in):
    account = api.create_account("lena", PASSWORD, "librarian")
    api.set_account_active(account["id"], False)
    open_users(app)

    user_row(page, "lena").get_by_test_id("user-enable").click()

    expect(user_row(page, "lena").get_by_test_id("user-status")).to_have_text("Активен")
    expect(page.get_by_test_id("users-notice")).to_have_text("Пользователь «lena» включён")
    assert can_sign_in("lena", PASSWORD)


# ---------- criterion 4: the last active admin ----------


def test_the_last_active_admin_cannot_be_disabled(app, page):
    open_users(app)

    user_row(page, ADMIN_USERNAME).get_by_test_id("user-disable").click()
    page.get_by_test_id("user-disable-confirm").click()

    expect(page.get_by_test_id("users-action-error")).to_have_text(LAST_ADMIN_MESSAGE)
    expect(user_row(page, ADMIN_USERNAME).get_by_test_id("user-status")).to_have_text("Активен")
    expect(page.get_by_test_id("users-notice")).to_have_count(0)


def test_the_refusal_message_is_not_translated(app, page):
    open_users(app)

    user_row(page, ADMIN_USERNAME).get_by_test_id("user-disable").click()
    page.get_by_test_id("user-disable-confirm").click()

    assert page.locator("html").get_attribute("lang") == "ru"
    expect(page.get_by_test_id("users-action-error")).to_have_text(LAST_ADMIN_MESSAGE)


def test_with_a_second_admin_the_first_may_be_disabled(app, page, api):
    api.create_account("second", PASSWORD, "admin")
    open_users(app)

    user_row(page, "second").get_by_test_id("user-disable").click()
    page.get_by_test_id("user-disable-confirm").click()

    expect(user_row(page, "second").get_by_test_id("user-status")).to_have_text("Отключён")
    # now the first admin is the last one
    user_row(page, ADMIN_USERNAME).get_by_test_id("user-disable").click()
    page.get_by_test_id("user-disable-confirm").click()
    expect(page.get_by_test_id("users-action-error")).to_have_text(LAST_ADMIN_MESSAGE)


# ---------- resetting a password ----------


def test_reset_password_opens_a_form_and_cancel_closes_it(app, page, api):
    api.create_account("lena", PASSWORD, "librarian")
    open_users(app)

    user_row(page, "lena").get_by_test_id("user-reset").click()
    expect(page.get_by_test_id("user-reset-form")).to_be_visible()
    page.get_by_test_id("user-reset-cancel").click()

    expect(page.get_by_test_id("user-reset-form")).to_have_count(0)


def test_reset_password_sets_the_new_one(app, page, api, can_sign_in):
    api.create_account("lena", PASSWORD, "librarian")
    open_users(app)

    user_row(page, "lena").get_by_test_id("user-reset").click()
    page.get_by_test_id("user-reset-password").fill(NEW_PASSWORD)
    page.get_by_test_id("user-reset-submit").click()

    expect(page.get_by_test_id("users-notice")).to_have_text("Пароль пользователя «lena» сброшен")
    expect(page.get_by_test_id("user-reset-form")).to_have_count(0)
    assert can_sign_in("lena", NEW_PASSWORD)
    assert not can_sign_in("lena", PASSWORD)


def test_a_short_password_in_the_reset_form_is_reported_under_the_field(
    app, page, api, can_sign_in
):
    api.create_account("lena", PASSWORD, "librarian")
    open_users(app)

    user_row(page, "lena").get_by_test_id("user-reset").click()
    page.get_by_test_id("user-reset-password").fill("short")
    page.get_by_test_id("user-reset-submit").click()

    expect(page.get_by_test_id("user-reset-error")).to_have_text(
        "String should have at least 8 characters"
    )
    expect(page.get_by_test_id("user-reset-form")).to_be_visible()
    assert can_sign_in("lena", PASSWORD)


def test_the_reset_password_field_is_masked_and_labelled(app, page, api):
    api.create_account("lena", PASSWORD, "librarian")
    open_users(app)

    user_row(page, "lena").get_by_test_id("user-reset").click()

    assert page.get_by_test_id("user-reset-password").get_attribute("type") == "password"
    assert (
        page.get_by_test_id("user-reset-password").get_attribute("autocomplete") == "new-password"
    )
    expect(page.get_by_label("Новый пароль", exact=True)).to_be_visible()


def test_a_reset_for_a_disabled_account_keeps_it_disabled(app, page, api, can_sign_in):
    account = api.create_account("lena", PASSWORD, "librarian")
    api.set_account_active(account["id"], False)
    open_users(app)

    user_row(page, "lena").get_by_test_id("user-reset").click()
    page.get_by_test_id("user-reset-password").fill(NEW_PASSWORD)
    page.get_by_test_id("user-reset-submit").click()

    expect(page.get_by_test_id("users-notice")).to_be_visible()
    expect(user_row(page, "lena").get_by_test_id("user-status")).to_have_text("Отключён")
    assert not can_sign_in("lena", NEW_PASSWORD)


# ---------- criterion 5: messages in both languages, other failures ----------


def test_success_messages_follow_the_interface_language(app, page):
    open_users(app)
    page.get_by_test_id("users-add").click()
    fill_account(page, "newbie", PASSWORD, "librarian")
    page.get_by_test_id("account-form-submit").click()
    expect(page.get_by_test_id("users-notice")).to_have_text("Пользователь «newbie» создан")

    app.set_locale("en")

    expect(page.get_by_test_id("users-notice")).to_have_text("User “newbie” created")


def test_the_page_and_the_form_are_translated(app, page):
    open_users(app)
    app.set_locale("en")

    expect(page.get_by_test_id("users-add")).to_have_text("Create user")
    page.get_by_test_id("users-add").click()
    expect(page.get_by_label("Username", exact=True)).to_be_visible()
    expect(page.get_by_label("Password", exact=True)).to_be_visible()
    expect(page.get_by_label("Role", exact=True)).to_be_visible()
    expect(page.get_by_test_id("account-form-role")).to_contain_text("Librarian")


def test_a_403_on_an_action_shows_the_server_message_and_keeps_the_table(app, page, api):
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

    user_row(page, "lena").get_by_test_id("user-disable").click()
    page.get_by_test_id("user-disable-confirm").click()

    expect(page.get_by_test_id("users-action-error")).to_have_text("Not enough permissions")
    expect(user_row(page, "lena")).to_be_visible()
    expect(page.get_by_test_id("users-add")).to_be_visible()


def test_a_network_failure_while_creating_is_reported_and_the_form_stays(app, page):
    open_users(app)
    page.get_by_test_id("users-add").click()
    fill_account(page, "newbie", PASSWORD, "librarian")
    page.route(
        "**/api/users",
        lambda route: route.abort() if route.request.method == "POST" else route.continue_(),
    )

    page.get_by_test_id("account-form-submit").click()

    expect(page.get_by_test_id("account-form-error")).to_have_text(
        "Не удалось связаться с сервером"
    )
    expect(page.get_by_test_id("account-form-username")).to_have_value("newbie")


def test_the_users_list_load_error_has_a_retry(app, page):
    app.open()
    page.route("**/api/users", lambda route: route.fulfill(status=500, json={"detail": "boom"}))

    app.tab("users").click()

    expect(page.get_by_test_id("users-error")).to_contain_text("boom")
    page.unroute("**/api/users")
    page.get_by_test_id("users-retry").click()
    expect(page.get_by_test_id("users-table")).to_be_visible()


# ---------- criterion 3: the librarian works in "Readers" ----------


@pytest.fixture
def librarian_session(as_role):
    return as_role("librarian")


def reader_row(page: Page, name: str):
    return page.get_by_test_id("reader-row").filter(has_text=name)


def open_readers(app) -> None:
    app.open()
    app.tab("readers").click()
    expect(app.page.get_by_test_id("readers-table")).to_be_visible()


def test_a_card_without_an_account_offers_create_account(app, page, api, librarian_session):
    api.create_reader(name="Анна Иванова")
    open_readers(app)

    expect(reader_row(page, "Анна Иванова").get_by_test_id("reader-create-account")).to_be_visible()


def test_a_card_with_an_account_shows_the_login_and_status_instead(
    app, page, api, librarian_session
):
    card = api.create_reader(name="Анна Иванова")
    api.create_account("anna", PASSWORD, "reader", card["id"])
    open_readers(app)

    row = reader_row(page, "Анна Иванова")

    expect(row.get_by_test_id("reader-account")).to_contain_text("anna")
    expect(row.get_by_test_id("reader-account")).to_contain_text("Активен")
    expect(row.get_by_test_id("reader-create-account")).to_have_count(0)


def test_the_form_offers_only_the_reader_role_and_the_fixed_card(app, page, api, librarian_session):
    api.create_reader(name="Анна Иванова")
    open_readers(app)

    reader_row(page, "Анна Иванова").get_by_test_id("reader-create-account").click()

    options = page.get_by_test_id("account-form-role").locator("option").all_inner_texts()
    assert options == ["Читатель"]
    expect(page.get_by_test_id("account-form-role")).to_be_disabled()  # nothing else to choose
    expect(page.get_by_test_id("account-form-card")).to_contain_text("Анна Иванова")
    expect(page.get_by_test_id("account-form-reader")).to_have_count(0)


def test_the_librarian_creates_a_reader_account_from_the_card(
    app, page, api, librarian_session, can_sign_in
):
    api.create_reader(name="Анна Иванова")
    open_readers(app)

    reader_row(page, "Анна Иванова").get_by_test_id("reader-create-account").click()
    fill_account(page, "anna", PASSWORD)
    page.get_by_test_id("account-form-submit").click()

    expect(page.get_by_test_id("readers-notice")).to_have_text("Пользователь «anna» создан")
    expect(reader_row(page, "Анна Иванова").get_by_test_id("reader-account")).to_contain_text(
        "anna"
    )
    assert can_sign_in("anna", PASSWORD)


def test_the_librarian_gets_the_server_errors_under_the_fields(app, page, api, librarian_session):
    api.create_reader(name="Анна Иванова")
    open_readers(app)
    reader_row(page, "Анна Иванова").get_by_test_id("reader-create-account").click()

    fill_account(page, "anna", "short")
    page.get_by_test_id("account-form-submit").click()
    expect(page.get_by_test_id("account-form-error-password")).to_be_visible()
    fill_account(page, ADMIN_USERNAME, PASSWORD)
    page.get_by_test_id("account-form-submit").click()

    expect(page.get_by_test_id("account-form-error-username")).to_have_text(
        "This login is already taken"
    )


def test_the_librarian_disables_enables_and_resets_a_reader_account(
    app, page, api, librarian_session, can_sign_in
):
    card = api.create_reader(name="Анна Иванова")
    api.create_account("anna", PASSWORD, "reader", card["id"])
    open_readers(app)
    row = reader_row(page, "Анна Иванова")

    row.get_by_test_id("user-disable").click()
    page.get_by_test_id("user-disable-confirm").click()
    expect(row.get_by_test_id("reader-account")).to_contain_text("Отключён")
    assert not can_sign_in("anna", PASSWORD)

    row.get_by_test_id("user-enable").click()
    expect(row.get_by_test_id("reader-account")).to_contain_text("Активен")

    row.get_by_test_id("user-reset").click()
    page.get_by_test_id("user-reset-password").fill(NEW_PASSWORD)
    page.get_by_test_id("user-reset-submit").click()
    expect(page.get_by_test_id("readers-notice")).to_have_text("Пароль пользователя «anna» сброшен")
    assert can_sign_in("anna", NEW_PASSWORD)


def test_staff_accounts_are_never_shown_to_the_librarian(app, page, api, librarian_session):
    card = api.create_reader(name="Анна Иванова")
    api.create_account("anna", PASSWORD, "reader", card["id"])
    open_readers(app)

    body = page.locator("body").inner_text()

    assert ADMIN_USERNAME not in body
    assert "Администратор" not in body


def test_the_librarian_has_no_users_section_but_manages_accounts_here(app, page, librarian_session):
    app.open()

    expect(app.tab("users")).to_have_count(0)
    expect(app.tab("readers")).to_be_visible()


def test_the_account_buttons_are_labelled_for_screen_readers(app, page, api, librarian_session):
    card = api.create_reader(name="Анна Иванова")
    api.create_reader(name="Борис Петров")
    api.create_account("anna", PASSWORD, "reader", card["id"])
    open_readers(app)

    expect(page.get_by_role("button", name="Создать аккаунт для «Борис Петров»")).to_be_visible()
    expect(page.get_by_role("button", name="Отключить «anna»")).to_be_visible()
    expect(page.get_by_role("button", name="Сбросить пароль «anna»")).to_be_visible()


def test_the_admin_also_sees_the_account_column_on_the_readers_page(app, page, api):
    card = api.create_reader(name="Анна Иванова")
    api.create_account("anna", PASSWORD, "reader", card["id"])
    api.create_reader(name="Борис Петров")
    open_readers(app)

    expect(reader_row(page, "Анна Иванова").get_by_test_id("reader-account")).to_contain_text(
        "anna"
    )
    expect(reader_row(page, "Борис Петров").get_by_test_id("reader-create-account")).to_be_visible()


def test_the_readers_page_works_in_english(app, page, api, librarian_session):
    api.create_reader(name="Анна Иванова")
    open_readers(app)

    app.set_locale("en")

    expect(page.get_by_role("columnheader", name="Account")).to_be_visible()
    expect(page.get_by_role("button", name="Create account for “Анна Иванова”")).to_be_visible()


def test_a_reader_card_with_an_account_cannot_be_deleted_and_the_reason_is_shown(app, page, api):
    card = api.create_reader(name="Анна Иванова")
    api.create_account("anna", PASSWORD, "reader", card["id"])
    open_readers(app)

    reader_row(page, "Анна Иванова").get_by_test_id("reader-delete").click()
    page.get_by_test_id("reader-delete-confirm").click()

    expect(page.get_by_test_id("readers-action-error")).to_be_visible()
    expect(reader_row(page, "Анна Иванова")).to_be_visible()
