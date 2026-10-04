"""Фикстуры дымовых тестов развёрнутого стенда (кластер Kubernetes).

В отличие от tests/ui, здесь НЕ поднимаются свои серверы и базы: тесты ходят по HTTP в уже работающее
приложение (по умолчанию http://127.0.0.1:8080, вход в локальный кластер kind через Ingress).
Поэтому данные в стенде настоящие, и каждый тест убирает за собой то, что создал.

Запуск: pytest tests/smoke -m smoke --no-cov
Другой адрес стенда: SMOKE_BASE_URL=http://host:port
"""

import os
import uuid

import httpx2 as httpx
import pytest

from tests.ui.pages import App

SMOKE_URL = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:8080").rstrip("/")


@pytest.fixture(scope="session")
def base_url():
    """Адрес стенда: pytest-playwright откроет относительные адреса (page.goto('/')) относительно него."""
    return SMOKE_URL


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1000, "height": 700},
        "locale": "ru-RU",
        "timezone_id": "UTC",
    }


@pytest.fixture
def api():
    """HTTP-клиент к API через тот же вход, что и у пользователя: Ingress -> nginx -> API."""
    with httpx.Client(base_url=f"{SMOKE_URL}/api", timeout=10) as client:
        yield client


@pytest.fixture
def unique_title():
    """Уникальное название: в стенде могут лежать чужие данные, пересечений быть не должно."""
    return f"smoke-{uuid.uuid4().hex[:10]}"


@pytest.fixture
def created_books(api):
    """Список id книг, созданных тестом: после теста они удаляются, даже если тест упал."""
    ids: list[int] = []
    yield ids
    for book_id in ids:
        api.delete(f"/books/{book_id}")


@pytest.fixture
def app(page):
    return App(page)
