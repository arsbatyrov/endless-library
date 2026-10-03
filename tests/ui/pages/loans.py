import re

from playwright.sync_api import Locator, Page


class LoansPage:
    """Раздел «Выдачи»: выбор читателя, его книги на руках и форма выдачи."""

    def __init__(self, page: Page):
        self.page = page
        self.reader_select = page.get_by_label("Читатель")
        self.pick_reader_hint = page.get_by_test_id("loans-pick-reader")
        self.form = page.get_by_test_id("loan-form")
        self.issue_button = page.get_by_test_id("loans-issue")
        self.rows = page.get_by_test_id("loan-row")
        self.empty = page.get_by_test_id("loans-empty")
        self.overdue_marks = page.get_by_test_id("loan-overdue")
        self.notice = page.get_by_test_id("loans-notice")
        self.action_error = page.get_by_test_id("loans-action-error")
        self.loading = page.get_by_test_id("loans-loading")
        self.load_error = page.get_by_test_id("loans-error")

    def select_reader(self, name: str) -> None:
        """Выбирает читателя в списке по имени (в списке подпись «Имя (email)»)."""
        label = self.reader_select.locator("option").filter(has_text=name).first.inner_text()
        self.reader_select.select_option(label=label)

    def choose_book(self, title: str) -> None:
        label = self.book_option(title).inner_text()
        self.page.get_by_label("Книга", exact=True).select_option(label=label)

    def book_option(self, title: str) -> Locator:
        """Вариант в списке книг; в подписи есть число экземпляров: «Название — Автор (в наличии: N)»."""
        return self.page.locator("#loans-book option").filter(
            has_text=re.compile(f"^{re.escape(title)} —")
        )

    def issue(self, title: str) -> None:
        self.choose_book(title)
        self.issue_button.click()

    def row(self, title: str) -> Locator:
        return self.rows.filter(has_text=title)

    def return_book(self, title: str) -> None:
        self.row(title).get_by_test_id("loan-return").click()
