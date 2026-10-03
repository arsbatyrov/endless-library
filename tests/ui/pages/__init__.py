"""Page Object: классы страниц приложения.

Правило: в них живут локаторы и действия пользователя («добавить книгу»), а проверки
(`expect`) остаются в тестах. Тогда при смене вёрстки правится одно место, а тест читается
как сценарий.
"""

from tests.ui.pages.app import App
from tests.ui.pages.books import BookForm, BooksPage
from tests.ui.pages.loans import LoansPage
from tests.ui.pages.readers import ReaderForm, ReadersPage

__all__ = ["App", "BookForm", "BooksPage", "LoansPage", "ReaderForm", "ReadersPage"]
