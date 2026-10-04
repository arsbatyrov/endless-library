"""Страница документации (/docs) и схема (/openapi.json) за префиксом /api.

Снаружи API виден под /api (nginx отрезает префикс). Если приложение об этом не знает, страница документации
просит схему по адресу без префикса, получает вместо неё страницу сайта и показывает
«Unable to render this definition».
"""

from fastapi.testclient import TestClient

from app.main import app


def test_docs_page_without_a_prefix_asks_for_the_schema_at_the_root(client):
    html = client.get("/docs").text

    assert "url: '/openapi.json'" in html


def test_docs_page_behind_a_prefix_asks_for_the_schema_at_the_public_path():
    """Когда приложение знает свой внешний префикс (root_path), адрес схемы на странице включает его."""
    html = TestClient(app, root_path="/api").get("/docs").text

    assert "url: '/api/openapi.json'" in html
    assert "url: '/openapi.json'" not in html


def test_schema_behind_a_prefix_lists_the_public_server_address():
    """В схеме указан адрес сервера /api: кнопка «Try it out» в Swagger шлёт запросы на /api/books, а не /books."""
    schema = TestClient(app, root_path="/api").get("/openapi.json").json()

    assert schema["servers"] == [{"url": "/api"}]


def test_routes_still_work_when_the_prefix_is_removed_by_the_proxy(client):
    """nginx передаёт нам /books (без /api): приложение с root_path обязано отвечать на такие адреса."""
    response = TestClient(app, root_path="/api").get("/books/popular")

    assert response.status_code == 200
