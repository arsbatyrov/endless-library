"""Redis недоступен или сломался: приложение обязано продолжать работать (без кэша, но верно)."""

import time

import redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.cache import cache
from tests.api.helpers import create_book, create_reader, issue_loan


def _broken(*args, **kwargs):
    raise RedisConnectionError("connection lost")


def test_works_without_redis_configured(client):
    """Кэш выключен (REDIS_URL не задан): все ответы приходят из базы."""
    book = create_book(client, title="No cache")

    response = client.get("/books")

    assert cache.enabled is False
    assert response.status_code == 200
    assert response.json() == [book]


def test_works_when_redis_is_unreachable_and_does_not_hang(client, monkeypatch):
    """Настроен адрес, по которому Redis не отвечает. Запросы должны быть успешными и быстрыми:
    короткие таймауты не дают упавшему Redis тормозить каждый запрос."""
    dead = redis.Redis.from_url(
        "redis://127.0.0.1:1/0",
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
        decode_responses=True,
    )
    monkeypatch.setattr(cache, "client", dead)
    book = create_book(client, title="Redis is down")

    started = time.monotonic()
    response = client.get("/books")
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert response.json() == [book]
    assert elapsed < 3, f"запрос с недоступным Redis занял {elapsed:.1f} с"


def test_a_redis_error_in_the_middle_of_a_request_does_not_break_it(
    client, redis_cache, monkeypatch
):
    book = create_book(client)
    monkeypatch.setattr(redis_cache.client, "get", _broken)
    monkeypatch.setattr(redis_cache.client, "set", _broken)

    response = client.get(f"/books/{book['id']}")

    assert response.status_code == 200
    assert response.json() == book


def test_loan_succeeds_even_if_redis_fails_after_the_commit(client, redis_cache, monkeypatch):
    """Выдача книги важнее кэша: сбой Redis при сбросе кэша не должен превращать успешную выдачу в ошибку."""
    book = create_book(client, copies_available=1)
    reader = create_reader(client)
    monkeypatch.setattr(redis_cache.client, "delete", _broken)
    monkeypatch.setattr(redis_cache.client, "exists", _broken)

    response = issue_loan(client, book["id"], reader["id"])

    assert response.status_code == 201
