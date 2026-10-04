"""Блок «Популярные книги» в разделе «Книги»."""

import json

from playwright.sync_api import expect


def test_popular_block_is_empty_until_books_are_issued(app, api):
    api.create_book(title="Никто не брал")

    app.open()

    expect(app.books.popular_empty).to_be_visible()
    expect(app.books.popular_items).to_have_count(0)


def test_popular_books_are_listed_by_number_of_loans(app, api):
    rare = api.create_book(title="Редкая", copies=5)
    hit = api.create_book(title="Хит", copies=5)
    readers = [api.create_reader(name=f"Читатель {n}") for n in range(3)]
    api.issue_loan(rare["id"], readers[0]["id"])
    for reader in readers:
        api.issue_loan(hit["id"], reader["id"])

    app.open()

    expect(app.books.popular_items).to_have_count(2)
    expect(app.books.popular_items.nth(0)).to_contain_text("Хит")
    expect(app.books.popular_items.nth(0).get_by_test_id("popular-loans")).to_have_text("3")
    expect(app.books.popular_items.nth(1)).to_contain_text("Редкая")
    expect(app.books.popular_items.nth(1).get_by_test_id("popular-loans")).to_have_text("1")


def test_issue_through_the_ui_is_reflected_in_popular_books(app, api):
    api.create_book(title="Книга", copies=2)
    api.create_reader(name="Иван")
    app.open()
    loans = app.go_to_loans()
    loans.select_reader("Иван")
    loans.issue("Книга")
    expect(loans.notice).to_contain_text("выдана")

    app.go_to_books()

    expect(app.books.popular_items).to_have_count(1)
    expect(app.books.popular_items.first.get_by_test_id("popular-loans")).to_have_text("1")


def test_popular_failure_does_not_break_the_books_list(app, api):
    """Рейтинг вспомогательный: если он недоступен, список книг должен остаться рабочим."""
    api.create_book(title="Книга")
    app.page.route(
        "**/api/books/popular*",
        lambda route: route.fulfill(
            status=500, content_type="application/json", body=json.dumps({"detail": "boom"})
        ),
    )

    app.open()

    expect(app.books.popular_error).to_be_visible()
    expect(app.books.row("Книга")).to_be_visible()
