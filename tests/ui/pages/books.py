from playwright.sync_api import Locator, Page


class BookForm:
    """Форма создания и изменения книги."""

    def __init__(self, page: Page):
        self.root = page.get_by_test_id("book-form")
        self.title = page.get_by_label("Название")
        self.author = page.get_by_label("Автор")
        self.year = page.get_by_label("Год издания")
        self.copies = page.get_by_label("Количество экземпляров")
        self.submit_button = page.get_by_test_id("book-form-submit")
        self.cancel_button = page.get_by_test_id("book-form-cancel")
        self.error = page.get_by_test_id("book-form-error")
        self._page = page

    def field_error(self, name: str) -> Locator:
        """Ошибка под полем: name = title, author, year или copies_available."""
        return self._page.get_by_test_id(f"book-form-error-{name}")

    def fill(self, title=None, author=None, year=None, copies=None) -> "BookForm":
        """Заполняет только переданные поля (пустую строку тоже можно передать, чтобы очистить поле)."""
        for field, value in (
            (self.title, title),
            (self.author, author),
            (self.year, year),
            (self.copies, copies),
        ):
            if value is not None:
                field.fill(str(value))
        return self

    def submit(self) -> None:
        self.submit_button.click()


class BooksPage:
    """Раздел «Книги»."""

    def __init__(self, page: Page):
        self.page = page
        self.add_button = page.get_by_test_id("books-add")
        self.rows = page.get_by_test_id("book-row")
        self.table = page.get_by_test_id("books-table")
        self.empty = page.get_by_test_id("books-empty")
        self.loading = page.get_by_test_id("books-loading")
        self.load_error = page.get_by_test_id("books-error")
        self.retry_button = page.get_by_test_id("books-retry")
        self.notice = page.get_by_test_id("books-notice")
        self.action_error = page.get_by_test_id("books-action-error")
        self.form = BookForm(page)

    def row(self, title: str) -> Locator:
        return self.rows.filter(has_text=title)

    def open_add_form(self) -> BookForm:
        self.add_button.click()
        return self.form

    def add(self, title: str, author: str, year=None, copies=None) -> None:
        """Полный сценарий: открыть форму, заполнить, сохранить."""
        self.open_add_form().fill(title, author, year, copies).submit()

    def open_edit_form(self, title: str) -> BookForm:
        self.row(title).get_by_test_id("book-edit").click()
        return self.form

    def request_delete(self, title: str) -> None:
        self.row(title).get_by_test_id("book-delete").click()

    def confirm_delete(self, title: str) -> None:
        self.row(title).get_by_test_id("book-delete-confirm").click()

    def cancel_delete(self, title: str) -> None:
        self.row(title).get_by_test_id("book-delete-cancel").click()

    def delete(self, title: str) -> None:
        """Удаление с подтверждением."""
        self.request_delete(title)
        self.confirm_delete(title)
