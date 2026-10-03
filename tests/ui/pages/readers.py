from playwright.sync_api import Locator, Page


class ReaderForm:
    """Форма создания и изменения читателя."""

    def __init__(self, page: Page):
        self.root = page.get_by_test_id("reader-form")
        self.name = page.get_by_label("Имя")
        self.email = page.get_by_label("Email")
        self.submit_button = page.get_by_test_id("reader-form-submit")
        self.cancel_button = page.get_by_test_id("reader-form-cancel")
        self.error = page.get_by_test_id("reader-form-error")
        self._page = page

    def field_error(self, name: str) -> Locator:
        """Ошибка под полем: name = name или email."""
        return self._page.get_by_test_id(f"reader-form-error-{name}")

    def fill(self, name=None, email=None) -> "ReaderForm":
        for field, value in ((self.name, name), (self.email, email)):
            if value is not None:
                field.fill(str(value))
        return self

    def submit(self) -> None:
        self.submit_button.click()


class ReadersPage:
    """Раздел «Читатели»."""

    def __init__(self, page: Page):
        self.page = page
        self.add_button = page.get_by_test_id("readers-add")
        self.rows = page.get_by_test_id("reader-row")
        self.empty = page.get_by_test_id("readers-empty")
        self.loading = page.get_by_test_id("readers-loading")
        self.load_error = page.get_by_test_id("readers-error")
        self.retry_button = page.get_by_test_id("readers-retry")
        self.notice = page.get_by_test_id("readers-notice")
        self.action_error = page.get_by_test_id("readers-action-error")
        self.form = ReaderForm(page)

    def row(self, name: str) -> Locator:
        return self.rows.filter(has_text=name)

    def open_add_form(self) -> ReaderForm:
        self.add_button.click()
        return self.form

    def add(self, name: str, email: str) -> None:
        self.open_add_form().fill(name, email).submit()

    def open_edit_form(self, name: str) -> ReaderForm:
        self.row(name).get_by_test_id("reader-edit").click()
        return self.form

    def request_delete(self, name: str) -> None:
        self.row(name).get_by_test_id("reader-delete").click()

    def confirm_delete(self, name: str) -> None:
        self.row(name).get_by_test_id("reader-delete-confirm").click()

    def cancel_delete(self, name: str) -> None:
        self.row(name).get_by_test_id("reader-delete-cancel").click()

    def delete(self, name: str) -> None:
        self.request_delete(name)
        self.confirm_delete(name)
