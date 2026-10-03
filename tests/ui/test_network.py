"""Поведение интерфейса при сбоях и необычных ответах API.

Здесь ответы сервера подменяются прямо в браузере (`page.route`): так можно проверить то, что
настоящий сервер выдаёт редко или не выдаёт вовсе (ошибка 500, обрыв связи, чужой текст ошибки).
"""

import json

from playwright.sync_api import Route, expect

from tests.ui.network import HeldRequests

BOOKS_URL = "**/api/books"


def fail_with_500(route: Route) -> None:
    route.fulfill(
        status=500, content_type="application/json", body=json.dumps({"detail": "Сбой сервера"})
    )


# ---------- загрузка списка ----------


def test_server_error_on_loading_shows_error_block_and_retry_recovers(page, app, api):
    api.create_book(title="Книга из базы")
    page.route(BOOKS_URL, fail_with_500)
    app.open()

    expect(app.books.load_error).to_contain_text("Сбой сервера")
    expect(app.books.table).to_have_count(0)

    page.unroute(BOOKS_URL)  # «сервер починили»
    app.books.retry_button.click()

    expect(app.books.load_error).to_have_count(0)
    expect(app.books.row("Книга из базы")).to_be_visible()


def test_lost_connection_on_loading_shows_error_block(page, app):
    page.route(BOOKS_URL, lambda route: route.abort())

    app.open()

    expect(app.books.load_error).to_contain_text("Не удалось загрузить книги")
    expect(app.books.retry_button).to_be_visible()


def test_empty_response_shows_empty_state_even_if_server_has_data(page, app, api):
    api.create_book(title="Есть на сервере")
    page.route(BOOKS_URL, lambda route: route.fulfill(json=[]))

    app.open()

    expect(app.books.empty).to_be_visible()


def test_loading_state_is_visible_while_the_response_is_pending(page, app, api):
    api.create_book(title="Медленная книга")
    pending = HeldRequests(page, BOOKS_URL)  # запрос «зависает», пока тест его не отпустит

    app.open()

    expect(app.books.loading).to_be_visible()
    expect(app.books.table).to_have_count(0)
    pending.release()
    expect(app.books.loading).to_have_count(0)
    expect(app.books.row("Медленная книга")).to_be_visible()


# ---------- сбои при сохранении и удалении ----------


def test_lost_connection_on_save_shows_message_and_keeps_the_form(page, app, api):
    page.route(
        BOOKS_URL,
        lambda route: route.abort() if route.request.method == "POST" else route.continue_(),
    )
    app.open()
    form = app.books.open_add_form()

    form.fill(title="Не дойдёт", author="Автор").submit()

    expect(form.error).to_have_text("Не удалось связаться с сервером")
    expect(form.title).to_have_value("Не дойдёт")  # введённое не потеряно
    assert api.books() == []


def test_server_error_on_delete_shows_message_and_keeps_the_book(page, app, api):
    book = api.create_book(title="Не удалится")
    page.route(f"**/api/books/{book['id']}", fail_with_500)
    app.open()

    app.books.delete("Не удалится")

    expect(app.books.action_error).to_have_text("Сбой сервера")
    expect(app.books.row("Не удалится")).to_be_visible()


def test_field_error_is_taken_from_the_response_not_hardcoded(page, app):
    """Интерфейс показывает под полем текст из ответа 422 (по loc), а не свой: важно для перевода сообщений."""
    body = {
        "detail": [
            {"type": "x", "loc": ["body", "title"], "msg": "Нужно указать название", "input": ""}
        ]
    }
    page.route(
        BOOKS_URL,
        lambda route: (
            route.fulfill(status=422, json=body)
            if route.request.method == "POST"
            else route.continue_()
        ),
    )
    app.open()
    form = app.books.open_add_form()

    form.fill(title="x", author="y").submit()

    expect(form.field_error("title")).to_have_text("Нужно указать название")
    expect(form.field_error("author")).to_have_count(0)
