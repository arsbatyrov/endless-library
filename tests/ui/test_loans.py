"""Раздел «Выдачи»: выдача, возврат, ограничения и пометка просрочки."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from playwright.sync_api import expect

from tests.ui.dates import ru_date


def test_issue_button_is_disabled_until_a_book_is_chosen(app, api):
    api.create_book(title="Книга")
    api.create_reader(name="Иван")
    app.open()
    loans = app.go_to_loans()

    expect(loans.pick_reader_hint).to_be_visible()
    expect(loans.form).to_have_count(0)
    loans.select_reader("Иван")
    expect(loans.empty).to_be_visible()
    expect(loans.issue_button).to_be_disabled()
    loans.choose_book("Книга")
    expect(loans.issue_button).to_be_enabled()


def test_issue_book_creates_a_loan_with_due_date_and_decreases_copies(app, api):
    api.create_book(title="Книга", copies=2)
    reader = api.create_reader(name="Иван")
    app.open()
    loans = app.go_to_loans()
    loans.select_reader("Иван")

    loans.issue("Книга")

    expect(loans.notice).to_contain_text("выдана")
    expect(loans.rows).to_have_count(1)
    loan = api.active_loans(reader["id"])[0]
    due = datetime.fromisoformat(loan["due_at"].replace("Z", "+00:00"))
    issued = datetime.fromisoformat(loan["issued_at"].replace("Z", "+00:00"))
    assert due - issued == timedelta(days=14)
    expect(loans.row("Книга").get_by_test_id("loan-due")).to_contain_text(ru_date(loan["due_at"]))
    expect(loans.row("Книга").get_by_test_id("loan-issued")).to_have_text(
        ru_date(loan["issued_at"])
    )
    expect(loans.book_option("Книга")).to_have_text(re.compile(r"в наличии: 1"))
    expect(loans.overdue_marks).to_have_count(0)


def test_book_without_free_copies_cannot_be_issued(app, api):
    book = api.create_book(title="Последняя", copies=1)
    api.issue_loan(book["id"], api.create_reader(name="Первый")["id"])
    api.create_reader(name="Второй")
    app.open()
    loans = app.go_to_loans()
    loans.select_reader("Второй")

    loans.issue("Последняя")

    expect(loans.action_error).to_have_text("No copies available")
    expect(loans.rows).to_have_count(0)


@pytest.mark.parametrize(
    "already_on_hands, accepted",
    [(2, True), (3, False)],
    ids=["третья книга ещё можно", "четвёртую нельзя"],
)
def test_reader_limit_of_three_books(app, api, already_on_hands, accepted):
    book = api.create_book(title="Книга", copies=10)
    reader = api.create_reader(name="Иван")
    for _ in range(already_on_hands):
        api.issue_loan(book["id"], reader["id"])
    app.open()
    loans = app.go_to_loans()
    loans.select_reader("Иван")
    expect(loans.rows).to_have_count(already_on_hands)

    loans.issue("Книга")

    if accepted:
        expect(loans.rows).to_have_count(already_on_hands + 1)
        expect(loans.action_error).to_have_count(0)
    else:
        expect(loans.action_error).to_contain_text("3 active loans")
        expect(loans.rows).to_have_count(already_on_hands)


def test_return_book_shows_zero_fine_and_restores_the_copy(app, api):
    book = api.create_book(title="Книга", copies=1)
    reader = api.create_reader(name="Иван")
    api.issue_loan(book["id"], reader["id"])
    app.open()
    loans = app.go_to_loans()
    loans.select_reader("Иван")
    expect(loans.book_option("Книга")).to_have_text(re.compile(r"в наличии: 0"))

    loans.return_book("Книга")

    expect(loans.notice).to_contain_text("возвращена")
    expect(loans.notice).to_contain_text("Штраф: 0")
    expect(loans.rows).to_have_count(0)
    expect(loans.book_option("Книга")).to_have_text(re.compile(r"в наличии: 1"))
    assert api.active_loans(reader["id"]) == []


def test_changing_the_reader_clears_messages_and_shows_only_their_books(app, api):
    book = api.create_book(title="Книга", copies=2)
    api.issue_loan(book["id"], api.create_reader(name="Иван")["id"])
    api.create_reader(name="Анна")
    app.open()
    loans = app.go_to_loans()
    loans.select_reader("Иван")
    expect(loans.rows).to_have_count(1)
    loans.issue("Книга")
    expect(loans.notice).to_be_visible()

    loans.select_reader("Анна")

    expect(loans.empty).to_be_visible()
    expect(loans.notice).to_have_count(0)
    expect(loans.action_error).to_have_count(0)


@pytest.mark.parametrize(
    "offset, overdue",
    [
        (timedelta(days=13, hours=23), False),
        (timedelta(days=14, hours=1), True),
    ],
    ids=["за час до срока: не просрочено", "через час после срока: просрочено"],
)
def test_overdue_mark_follows_the_browser_clock(page, app, api, offset, overdue):
    """Срок возврата 14 дней; время браузера подменяем и проверяем границу срока."""
    book = api.create_book(title="Книга")
    reader = api.create_reader(name="Иван")
    api.issue_loan(book["id"], reader["id"])
    page.clock.install(time=datetime.now(UTC) + offset)
    app.open()
    loans = app.go_to_loans()

    loans.select_reader("Иван")

    expect(loans.rows).to_have_count(1)
    expect(loans.overdue_marks).to_have_count(1 if overdue else 0)
