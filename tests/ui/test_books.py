"""Раздел «Книги»: создание, изменение, удаление и ошибки."""

import pytest
from playwright.sync_api import expect

# ---------- создание ----------


def test_add_book_shows_it_in_the_list(app):
    app.open()

    app.books.add("Идиот", "Фёдор Достоевский", year=1869, copies=2)

    expect(app.books.notice).to_contain_text("Идиот")
    expect(app.books.rows).to_have_count(1)
    row = app.books.row("Идиот")
    expect(row.get_by_test_id("book-author")).to_have_text("Фёдор Достоевский")
    expect(row.get_by_test_id("book-year")).to_have_text("1869")
    expect(row.get_by_test_id("book-copies")).to_have_text("2")
    expect(app.books.form.root).to_have_count(0)


def test_added_book_is_really_saved_on_the_server(app, api):
    app.open()

    app.books.add("Мастер и Маргарита", "Михаил Булгаков", copies=1)
    expect(app.books.rows).to_have_count(1)

    assert [book["title"] for book in api.books()] == ["Мастер и Маргарита"]


def test_add_form_starts_with_one_copy_and_no_year(app):
    app.open()

    form = app.books.open_add_form()

    expect(form.copies).to_have_value("1")
    expect(form.year).to_have_value("")


def test_year_is_optional_and_shown_as_dash(app):
    app.open()

    app.books.add("Книга без года", "Аноним")

    expect(app.books.row("Книга без года").get_by_test_id("book-year")).to_have_text("—")


@pytest.mark.parametrize(
    "values, failing_field",
    [
        ({"title": "", "author": "Автор"}, "title"),
        ({"title": "Название", "author": ""}, "author"),
        ({"title": "Название", "author": "Автор", "copies": -1}, "copies_available"),
        ({"title": "Название", "author": "Автор", "copies": ""}, "copies_available"),
        ({"title": "Название", "author": "Автор", "year": 2101}, "year"),
    ],
    ids=[
        "пустое название",
        "пустой автор",
        "отрицательное число",
        "пустое число",
        "год из будущего",
    ],
)
def test_invalid_book_is_rejected_with_error_under_the_field(app, api, values, failing_field):
    app.open()
    form = app.books.open_add_form()

    form.fill(**values).submit()

    expect(form.field_error(failing_field)).to_be_visible()
    expect(form.error).to_have_text("Проверьте значения полей")
    expect(app.books.rows).to_have_count(0)
    assert api.books() == []


@pytest.mark.parametrize(
    "length, accepted",
    [(200, True), (201, False)],
    ids=["200 символов: граница допустима", "201 символ: уже нельзя"],
)
def test_title_length_boundary(app, api, length, accepted):
    app.open()
    form = app.books.open_add_form()

    form.fill(title="я" * length, author="Автор").submit()

    if accepted:
        expect(app.books.rows).to_have_count(1)
        assert len(api.books()[0]["title"]) == length
    else:
        expect(form.field_error("title")).to_be_visible()
        expect(app.books.rows).to_have_count(0)


def test_cancel_closes_the_form_without_saving(app, api):
    app.open()
    form = app.books.open_add_form()
    form.fill(title="Не сохранится", author="Автор")

    form.cancel_button.click()

    expect(form.root).to_have_count(0)
    expect(app.books.rows).to_have_count(0)
    assert api.books() == []


# ---------- изменение ----------


def test_edit_form_is_prefilled_and_saves_changes(app, api):
    api.create_book(title="Старое название", author="Автор", year=1999, copies=1)
    app.open()

    form = app.books.open_edit_form("Старое название")

    expect(form.title).to_have_value("Старое название")
    expect(form.year).to_have_value("1999")
    form.fill(title="Новое название", copies=7).submit()

    expect(app.books.notice).to_contain_text("сохранены")
    row = app.books.row("Новое название")
    expect(row.get_by_test_id("book-copies")).to_have_text("7")
    assert [book["title"] for book in api.books()] == ["Новое название"]


def test_failed_edit_keeps_the_old_values(app, api):
    api.create_book(title="Остаётся прежним", author="Автор")
    app.open()
    form = app.books.open_edit_form("Остаётся прежним")

    form.fill(title="").submit()

    expect(form.field_error("title")).to_be_visible()
    form.cancel_button.click()
    expect(app.books.row("Остаётся прежним")).to_be_visible()
    assert api.books()[0]["title"] == "Остаётся прежним"


# ---------- удаление ----------


def test_delete_requires_confirmation_and_removes_the_book(app, api):
    api.create_book(title="Удаляемая", author="Автор")
    app.open()

    app.books.delete("Удаляемая")

    expect(app.books.notice).to_contain_text("удалена")
    expect(app.books.rows).to_have_count(0)
    assert api.books() == []


def test_cancelling_delete_keeps_the_book(app, api):
    api.create_book(title="Остаётся", author="Автор")
    app.open()

    app.books.request_delete("Остаётся")
    app.books.cancel_delete("Остаётся")

    expect(app.books.row("Остаётся")).to_be_visible()
    assert len(api.books()) == 1


def test_book_with_loan_history_cannot_be_deleted(app, api):
    book = api.create_book(title="С историей", author="Автор", copies=2)
    reader = api.create_reader()
    api.issue_loan(book["id"], reader["id"])
    app.open()

    app.books.delete("С историей")

    expect(app.books.action_error).to_contain_text("loan history")
    expect(app.books.row("С историей")).to_be_visible()
    assert len(api.books()) == 1
