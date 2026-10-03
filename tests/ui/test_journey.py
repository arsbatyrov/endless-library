"""Сквозной сценарий: весь путь пользователя только через интерфейс."""

import re

from playwright.sync_api import expect


def test_librarian_journey_add_book_and_reader_issue_and_return(app, api):
    title = "Преступление и наказание"
    app.open()

    # 1. заводим книгу и читателя
    app.go_to_books()
    app.books.add(title, "Фёдор Достоевский", year=1866, copies=1)
    expect(app.books.row(title)).to_be_visible()
    app.go_to_readers()
    app.readers.add("Родион Раскольников", "rodion@example.com")
    expect(app.readers.row("Родион")).to_be_visible()

    # 2. выдаём книгу: она на руках, свободных экземпляров не осталось
    loans = app.go_to_loans()
    loans.select_reader("Родион")
    loans.issue(title)
    expect(loans.notice).to_contain_text("выдана")
    expect(loans.row(title)).to_be_visible()
    expect(loans.book_option(title)).to_have_text(re.compile(r"в наличии: 0"))

    # 3. возвращаем: штрафа нет, книга снова в наличии
    loans.return_book(title)
    expect(loans.notice).to_contain_text("Штраф: 0")
    expect(loans.empty).to_be_visible()
    app.go_to_books()
    expect(app.books.row(title).get_by_test_id("book-copies")).to_have_text("1")

    # 4. итоговое состояние на сервере
    reader = api.readers()[0]
    assert api.active_loans(reader["id"]) == []
    assert api.books()[0]["copies_available"] == 1
