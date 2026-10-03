"""Раздел «Книги»: создание, изменение, удаление и ошибки."""

from playwright.sync_api import expect


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
