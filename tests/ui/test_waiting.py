"""Ожидания: почему UI-тесты бывают нестабильными и как этого избежать.

Данные в интерфейс приходят не мгновенно: страница уже нарисована, а список книг ещё едет по сети.
Тест, который проверяет элемент «сразу», иногда успевает (на быстрой машине), а иногда нет.
Чтобы показать это без настоящей случайности, ответ API здесь «подвешивается» намеренно.
"""

import pytest
from playwright.sync_api import expect

from tests.ui.network import HeldRequests


@pytest.mark.xfail(
    strict=True,
    reason="Антипаттерн: мгновенная проверка без ожидания видит страницу раньше, чем придут данные",
)
def test_antipattern_immediate_check_does_not_wait_for_data(page, app, api):
    api.create_book(title="Книга")
    HeldRequests(page, "**/api/books")  # ответ не придёт, пока его не отпустят (а мы не отпускаем)
    app.open()

    # is_visible() отвечает «прямо сейчас» и не ждёт: данные ещё не пришли, проверка падает.
    assert app.books.table.is_visible()


def test_pattern_expect_waits_until_the_data_arrives(page, app, api):
    api.create_book(title="Книга")
    pending = HeldRequests(page, "**/api/books")
    app.open()
    expect(app.books.loading).to_be_visible()

    pending.release()

    # expect() сам ждёт (по умолчанию до 5 секунд), пока условие не станет истинным.
    expect(app.books.table).to_be_visible()
    expect(app.books.row("Книга")).to_be_visible()
