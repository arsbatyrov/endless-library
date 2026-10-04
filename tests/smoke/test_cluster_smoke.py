"""Дымовые тесты стенда в кластере: приложение доступно через Ingress и работает целиком.

Путь запроса: браузер -> Ingress (Traefik) -> Service web -> nginx -> Service api -> API -> Service db -> Postgres.
"""

from playwright.sync_api import expect


def test_liveness_and_readiness_are_green_through_ingress(api):
    health = api.get("/health")
    ready = api.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


def test_api_error_reaches_client_from_the_api_not_from_a_proxy(api):
    """404 с JSON и полем detail приходит от API (а не страница ошибки nginx или Ingress)."""
    response = api.get("/books/999999999")

    assert response.status_code == 404
    assert "detail" in response.json()


def test_ui_opens_with_all_sections(app):
    app.open()

    expect(app.page.get_by_role("heading", name="Библиотека", level=1)).to_be_visible()
    for section in ("books", "readers", "loans"):
        expect(app.tab(section)).to_be_visible()
    expect(app.tab("books")).to_have_attribute("aria-selected", "true")


def test_book_created_through_api_is_visible_in_the_ui(app, api, unique_title, created_books):
    created = api.post(
        "/books",
        json={"title": unique_title, "author": "Smoke Tester", "year": 2024, "copies_available": 2},
    )
    assert created.status_code == 201
    created_books.append(created.json()["id"])

    app.open()

    expect(app.books.row(unique_title)).to_contain_text("Smoke Tester")


def test_book_added_in_the_ui_is_saved_in_the_database(app, api, unique_title, created_books):
    """Полный круг: форма в браузере -> API -> Postgres, затем перезагрузка страницы возвращает данные."""
    app.open()
    app.books.add(unique_title, "Smoke Tester", year=2024, copies=1)
    expect(app.books.row(unique_title)).to_be_visible()

    # id нужен для уборки: находим книгу по названию через API
    found = [b for b in api.get("/books").json() if b["title"] == unique_title]
    assert len(found) == 1, "книга должна сохраниться ровно один раз"
    created_books.append(found[0]["id"])

    app.page.reload()
    expect(app.books.row(unique_title)).to_be_visible()
