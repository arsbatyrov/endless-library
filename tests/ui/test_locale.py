"""Выбор языка интерфейса (ru/en): переключатель, запоминание выбора и перевод всех текстов.

Тексты, которые приходят с сервера (сообщения об ошибках 404, 409, 422), намеренно не переводятся:
они показываются как есть, и эти тесты их не проверяют.
"""

import re
from datetime import UTC, datetime

import pytest
from playwright.sync_api import expect

from tests.ui.dates import ru_date


def en_date(iso: str) -> str:
    """Дата в английском формате интерфейса: дд/мм/гггг в UTC."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC).strftime("%d/%m/%Y")


def add_book(app, title: str, author: str) -> None:
    """Добавление книги в любом языке интерфейса: поля ищем по data-testid, а не по русским подписям."""
    app.books.add_button.click()
    app.page.get_by_test_id("book-form-title").fill(title)
    app.page.get_by_test_id("book-form-author").fill(author)
    app.page.get_by_test_id("book-form-submit").click()


def add_reader(app, name: str, email: str) -> None:
    app.readers.add_button.click()
    app.page.get_by_test_id("reader-form-name").fill(name)
    app.page.get_by_test_id("reader-form-email").fill(email)
    app.page.get_by_test_id("reader-form-submit").click()


# ---------- выбор и запоминание ----------


def test_russian_browser_gets_the_russian_interface_by_default(app):
    app.open()

    expect(app.heading).to_have_text("Библиотека")
    expect(app.page.locator("html")).to_have_attribute("lang", "ru")
    expect(app.page).to_have_title("Библиотека")
    expect(app.locale_button("ru")).to_have_attribute("aria-pressed", "true")
    expect(app.locale_button("en")).to_have_attribute("aria-pressed", "false")


def test_english_browser_gets_the_english_interface_by_default(browser, base_url):
    context = browser.new_context(locale="en-US", base_url=base_url)
    try:
        page = context.new_page()
        page.goto("/")

        expect(page.get_by_role("heading", level=1)).to_have_text("Library")
        expect(page.locator("html")).to_have_attribute("lang", "en")
    finally:
        context.close()


def test_switching_to_english_translates_the_page_frame(app):
    app.open()

    app.set_locale("en")

    expect(app.heading).to_have_text("Library")
    expect(app.page.locator("html")).to_have_attribute("lang", "en")
    expect(app.page).to_have_title("Library")
    expect(app.tab("books")).to_have_text("Books")
    expect(app.tab("readers")).to_have_text("Readers")
    expect(app.tab("loans")).to_have_text("Loans")
    expect(app.locale_button("en")).to_have_attribute("aria-pressed", "true")
    expect(app.page.get_by_role("tablist")).to_have_accessible_name("Sections")


def test_switching_back_to_russian_restores_russian_texts(app):
    app.open()
    app.set_locale("en")

    app.set_locale("ru")

    expect(app.heading).to_have_text("Библиотека")
    expect(app.tab("books")).to_have_text("Книги")
    expect(app.page.get_by_role("tablist")).to_have_accessible_name("Разделы")


def test_choice_is_remembered_after_reload(app):
    app.open()
    app.set_locale("en")

    app.page.reload()

    expect(app.heading).to_have_text("Library")
    expect(app.locale_button("en")).to_have_attribute("aria-pressed", "true")


def test_choice_overrides_the_browser_language(app):
    """Выбранный вручную язык сильнее языка браузера (браузер здесь русский)."""
    app.open()
    app.set_locale("en")
    app.page.reload()

    expect(app.page.locator("html")).to_have_attribute("lang", "en")


def test_language_stays_when_switching_between_sections(app):
    app.open()
    app.set_locale("en")

    app.go_to_readers()
    expect(app.page.get_by_role("heading", name="Readers", level=2)).to_be_visible()
    app.go_to_loans()
    expect(app.page.get_by_role("heading", name="Loans", level=2)).to_be_visible()


# ---------- разделы ----------


def test_books_section_in_english(app, api):
    api.create_book(title="Dune", author="Frank Herbert", year=1965, copies=2)
    app.open()
    app.set_locale("en")

    expect(app.page.get_by_role("heading", name="Books", level=2)).to_be_visible()
    expect(app.books.add_button).to_have_text("Add book")
    headers = app.books.table.get_by_role("columnheader")
    expect(headers).to_have_text(["Title", "Author", "Year", "In stock", "Actions"])
    row = app.books.row("Dune")
    expect(row.get_by_test_id("book-edit")).to_have_text("Edit")
    expect(row.get_by_test_id("book-edit")).to_have_accessible_name("Edit “Dune”")
    expect(row.get_by_test_id("book-delete")).to_have_text("Delete")


def test_empty_states_in_english(app):
    app.open()
    app.set_locale("en")

    expect(app.books.empty).to_have_text("There are no books yet")
    app.go_to_readers()
    expect(app.readers.empty).to_have_text("There are no readers yet")
    app.go_to_loans()
    expect(app.loans.pick_reader_hint).to_have_text(
        "Choose a reader to see their books and issue a new one"
    )


def test_book_form_in_english(app):
    app.open()
    app.set_locale("en")

    form = app.books.open_add_form()

    expect(app.page.get_by_role("heading", name="New book", level=3)).to_be_visible()
    expect(app.page.get_by_label("Title", exact=True)).to_be_visible()
    expect(app.page.get_by_label("Author", exact=True)).to_be_visible()
    expect(app.page.get_by_label("Year of publication", exact=True)).to_be_visible()
    expect(app.page.get_by_label("Number of copies", exact=True)).to_be_visible()
    expect(form.submit_button).to_have_text("Save")
    expect(form.cancel_button).to_have_text("Cancel")


def test_reader_form_and_table_in_english(app, api):
    api.create_reader(name="Ann", email="ann@example.com")
    app.open()
    app.set_locale("en")
    app.go_to_readers()

    expect(app.page.get_by_test_id("readers-table").get_by_role("columnheader")).to_have_text(
        ["Name", "Email", "Actions"]
    )
    app.readers.open_add_form()
    expect(app.page.get_by_role("heading", name="New reader", level=3)).to_be_visible()
    expect(app.page.get_by_label("Name", exact=True)).to_be_visible()


def test_loans_section_in_english(app, api):
    api.create_book(title="Dune", author="Frank Herbert", copies=3)
    api.create_reader(name="Ann")
    app.open()
    app.set_locale("en")
    loans = app.go_to_loans()

    expect(app.page.get_by_label("Reader", exact=True)).to_be_visible()
    app.page.get_by_test_id("loans-reader").select_option(index=1)
    expect(loans.empty).to_have_text("The reader has no books on loan")
    expect(app.page.get_by_role("heading", name="Issue a book", level=3)).to_be_visible()
    expect(loans.book_option("Dune")).to_have_text("Dune — Frank Herbert (in stock: 3)")
    expect(loans.issue_button).to_have_text("Issue")


def test_popular_books_block_in_english(app, api):
    book = api.create_book(title="Dune", copies=2)
    reader = api.create_reader(name="Ann")
    api.issue_loan(book["id"], reader["id"])
    app.open()
    app.set_locale("en")

    expect(app.books.popular.get_by_role("heading", name="Popular books")).to_be_visible()
    expect(app.books.popular_items.first).to_contain_text("loans")


# ---------- сообщения интерфейса ----------


def test_notice_is_translated_when_the_language_changes(app):
    """Уже показанное сообщение тоже переводится при смене языка (в состоянии хранится ключ, а не готовый текст)."""
    app.open()
    app.books.add("Дюна", "Фрэнк Герберт")
    expect(app.books.notice).to_have_text("Книга «Дюна» добавлена")

    app.set_locale("en")

    expect(app.books.notice).to_have_text("Book “Дюна” added")


def test_notices_in_english(app):
    app.open()
    app.set_locale("en")

    add_book(app, "Dune", "Frank Herbert")
    expect(app.books.notice).to_have_text("Book “Dune” added")
    app.books.delete("Dune")
    expect(app.books.notice).to_have_text("Book “Dune” deleted")
    app.go_to_readers()
    add_reader(app, "Ann", "ann@example.com")
    expect(app.readers.notice).to_have_text("Reader “Ann” added")


def test_load_failure_message_in_english(app):
    app.page.route("**/api/books", lambda route: route.abort())
    # язык выставляем до первой загрузки страницы
    app.page.add_init_script("window.localStorage.setItem('library.locale', 'en')")

    app.open()

    expect(app.books.load_error).to_contain_text("Could not load books:")
    expect(app.books.retry_button).to_have_text("Retry")


def test_loading_text_in_english(app):
    from tests.ui.network import HeldRequests

    app.page.add_init_script("window.localStorage.setItem('library.locale', 'en')")
    held = HeldRequests(app.page, "**/api/books")

    app.open()

    expect(app.books.loading).to_have_text("Loading…")
    held.release()


@pytest.mark.parametrize(
    "code, expected_text",
    [("ru", "просрочено"), ("en", "overdue")],
)
def test_overdue_mark_is_translated(page, app, api, code, expected_text):
    from datetime import timedelta

    book = api.create_book(title="Книга")
    reader = api.create_reader(name="Иван")
    api.issue_loan(book["id"], reader["id"])
    page.clock.install(time=datetime.now(UTC) + timedelta(days=15))
    app.open()
    app.set_locale(code)
    loans = app.go_to_loans()

    app.page.get_by_test_id("loans-reader").select_option(index=1)

    expect(loans.overdue_marks).to_have_text(re.compile(expected_text))


# ---------- формат дат ----------


def test_dates_follow_the_language(app, api):
    book = api.create_book(title="Book", copies=2)
    reader = api.create_reader(name="Ann")
    loan = api.issue_loan(book["id"], reader["id"])
    app.open()
    loans = app.go_to_loans()
    loans.select_reader("Ann")

    expect(loans.row("Book").get_by_test_id("loan-due")).to_contain_text(ru_date(loan["due_at"]))

    app.set_locale("en")

    expect(loans.row("Book").get_by_test_id("loan-due")).to_contain_text(en_date(loan["due_at"]))
    expect(loans.row("Book").get_by_test_id("loan-issued")).to_have_text(en_date(loan["issued_at"]))


def test_issue_notice_shows_the_date_in_the_current_language(app, api):
    api.create_book(title="Book", copies=2)
    api.create_reader(name="Ann")
    app.open()
    loans = app.go_to_loans()
    loans.select_reader("Ann")
    loans.issue("Book")
    expect(loans.notice).to_contain_text("выдана, вернуть до")

    app.set_locale("en")

    expect(loans.notice).to_contain_text("issued, due ")
    expect(loans.notice).to_contain_text("/")  # дд/мм/гггг
