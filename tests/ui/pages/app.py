from playwright.sync_api import Locator, Page

from tests.ui.pages.books import BooksPage
from tests.ui.pages.loans import LoansPage
from tests.ui.pages.readers import ReadersPage


class App:
    """Приложение целиком: вкладки и страницы разделов."""

    def __init__(self, page: Page):
        self.page = page
        self.books = BooksPage(page)
        self.readers = ReadersPage(page)
        self.loans = LoansPage(page)

    def open(self) -> "App":
        self.page.goto("/")
        return self

    def tab(self, name: str) -> Locator:
        """Вкладка по имени раздела: books, readers или loans."""
        return self.page.get_by_test_id(f"tab-{name}")

    def locale_button(self, code: str) -> Locator:
        """Кнопка выбора языка: ru или en."""
        return self.page.get_by_test_id(f"locale-{code}")

    def set_locale(self, code: str) -> None:
        self.locale_button(code).click()

    @property
    def heading(self) -> Locator:
        return self.page.get_by_role("heading", level=1)

    def go_to_books(self) -> BooksPage:
        self.tab("books").click()
        return self.books

    def go_to_readers(self) -> ReadersPage:
        self.tab("readers").click()
        return self.readers

    def go_to_loans(self) -> LoansPage:
        self.tab("loans").click()
        return self.loans
