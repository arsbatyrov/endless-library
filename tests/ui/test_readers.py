"""Раздел «Читатели»."""

import pytest
from playwright.sync_api import expect


def test_add_reader_shows_it_in_the_list(app, api):
    app.open()
    app.go_to_readers()

    app.readers.add("Иван Петров", "ivan@example.com")

    expect(app.readers.notice).to_contain_text("Иван Петров")
    expect(app.readers.row("Иван Петров")).to_contain_text("ivan@example.com")
    assert [reader["email"] for reader in api.readers()] == ["ivan@example.com"]


def test_duplicate_email_is_rejected_and_form_stays_open(app, api):
    api.create_reader(name="Иван", email="ivan@example.com")
    app.open()
    app.go_to_readers()

    app.readers.add("Другой Иван", "ivan@example.com")

    expect(app.readers.form.error).to_contain_text("already exists")
    expect(app.readers.form.root).to_be_visible()
    expect(app.readers.form.field_error("email")).to_have_count(0)  # это не ошибка конкретного поля
    expect(app.readers.rows).to_have_count(1)
    assert len(api.readers()) == 1


@pytest.mark.parametrize(
    "name, email, failing_field",
    [
        ("", "valid@example.com", "name"),
        ("Имя", "not-an-email", "email"),
        ("Имя", "a@b", "email"),
        ("Имя", "a b@c.co", "email"),
    ],
    ids=["пустое имя", "email без @", "email без домена верхнего уровня", "email с пробелом"],
)
def test_invalid_reader_is_rejected_with_error_under_the_field(
    app, api, name, email, failing_field
):
    app.open()
    app.go_to_readers()
    form = app.readers.open_add_form()

    form.fill(name, email).submit()

    expect(form.field_error(failing_field)).to_be_visible()
    expect(app.readers.rows).to_have_count(0)
    assert api.readers() == []


def test_editing_a_reader_keeping_the_same_email_is_not_a_conflict(app, api):
    api.create_reader(name="Иван", email="ivan@example.com")
    app.open()
    app.go_to_readers()

    form = app.readers.open_edit_form("Иван")
    expect(form.email).to_have_value("ivan@example.com")
    form.fill(name="Иван Сергеевич").submit()

    expect(app.readers.notice).to_contain_text("сохранены")
    expect(app.readers.row("Иван Сергеевич")).to_contain_text("ivan@example.com")


def test_changing_email_to_another_readers_email_is_a_conflict(app, api):
    api.create_reader(name="Иван", email="ivan@example.com")
    api.create_reader(name="Анна", email="anna@example.com")
    app.open()
    app.go_to_readers()

    form = app.readers.open_edit_form("Иван")
    form.fill(email="anna@example.com").submit()

    expect(form.error).to_contain_text("already exists")
    form.cancel_button.click()
    expect(app.readers.row("Иван")).to_contain_text("ivan@example.com")


def test_delete_reader_after_confirmation(app, api):
    api.create_reader(name="Удаляемый")
    app.open()
    app.go_to_readers()

    app.readers.delete("Удаляемый")

    expect(app.readers.notice).to_contain_text("удалён")
    expect(app.readers.rows).to_have_count(0)
    assert api.readers() == []


def test_cancelling_delete_keeps_the_reader(app, api):
    api.create_reader(name="Остаётся")
    app.open()
    app.go_to_readers()

    app.readers.request_delete("Остаётся")
    app.readers.cancel_delete("Остаётся")

    expect(app.readers.row("Остаётся")).to_be_visible()
    assert len(api.readers()) == 1


def test_reader_with_loan_history_cannot_be_deleted(app, api):
    book = api.create_book()
    reader = api.create_reader(name="С историей")
    api.issue_loan(book["id"], reader["id"])
    app.open()
    app.go_to_readers()

    app.readers.delete("С историей")

    expect(app.readers.action_error).to_contain_text("loan history")
    expect(app.readers.row("С историей")).to_be_visible()
    assert len(api.readers()) == 1
