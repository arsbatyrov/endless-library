"""Кэш книг (Redis): когда ответ берётся из кэша и когда кэш обязан сбрасываться.

Заголовок X-Cache показывает происхождение ответа: MISS (из базы) или HIT (из кэша).
Главный риск кэша не «не ускорил», а «показал устаревшее»: большинство тестов проверяют сброс.
"""

import time

from sqlalchemy import text

from app.cache import BOOKS_LIST_KEY, book_key
from tests.api.helpers import create_book, create_reader, issue_loan


def test_second_list_request_is_served_from_cache(client, redis_cache):
    create_book(client, title="Cached")

    first = client.get("/books")
    second = client.get("/books")

    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert second.json() == first.json()


def test_second_book_request_is_served_from_cache(client, redis_cache):
    book = create_book(client)

    first = client.get(f"/books/{book['id']}")
    second = client.get(f"/books/{book['id']}")

    assert (first.headers["X-Cache"], second.headers["X-Cache"]) == ("MISS", "HIT")
    assert second.json() == book


def test_missing_book_is_not_cached(client, redis_cache):
    first = client.get("/books/999")
    second = client.get("/books/999")

    assert (first.status_code, second.status_code) == (404, 404)
    assert "X-Cache" not in second.headers
    assert not redis_cache.client.exists(book_key(999))


def test_creating_a_book_resets_the_cached_list(client, redis_cache):
    create_book(client, title="First")
    assert len(client.get("/books").json()) == 1  # список теперь в кэше

    create_book(client, title="Second")
    response = client.get("/books")

    assert response.headers["X-Cache"] == "MISS"
    assert [b["title"] for b in response.json()] == ["First", "Second"]


def test_updating_a_book_resets_its_card_and_the_list(client, redis_cache):
    book = create_book(client, title="Old title")
    client.get(f"/books/{book['id']}")
    client.get("/books")

    client.put(
        f"/books/{book['id']}", json={"title": "New title", "author": "A", "copies_available": 1}
    )

    assert client.get(f"/books/{book['id']}").json()["title"] == "New title"
    assert client.get("/books").json()[0]["title"] == "New title"


def test_deleting_a_book_does_not_leave_it_in_the_cache(client, redis_cache):
    book = create_book(client)
    assert client.get(f"/books/{book['id']}").status_code == 200  # карточка в кэше

    assert client.delete(f"/books/{book['id']}").status_code == 204

    assert client.get(f"/books/{book['id']}").status_code == 404
    assert client.get("/books").json() == []


def test_issuing_a_book_resets_cached_copies_count(client, redis_cache):
    book = create_book(client, copies_available=2)
    reader = create_reader(client)
    assert client.get(f"/books/{book['id']}").json()["copies_available"] == 2  # в кэше

    issue_loan(client, book["id"], reader["id"])

    assert client.get(f"/books/{book['id']}").json()["copies_available"] == 1
    assert client.get("/books").json()[0]["copies_available"] == 1


def test_returning_a_book_resets_cached_copies_count(client, redis_cache):
    book = create_book(client, copies_available=1)
    reader = create_reader(client)
    loan = issue_loan(client, book["id"], reader["id"]).json()
    assert client.get(f"/books/{book['id']}").json()["copies_available"] == 0  # в кэше

    client.post(f"/loans/{loan['id']}/return")

    assert client.get(f"/books/{book['id']}").json()["copies_available"] == 1
    assert client.get("/books").json()[0]["copies_available"] == 1


def test_cached_entries_have_a_time_to_live(client, redis_cache):
    book = create_book(client)
    client.get("/books")
    client.get(f"/books/{book['id']}")

    for key in (BOOKS_LIST_KEY, book_key(book["id"])):
        assert 0 < redis_cache.client.ttl(key) <= redis_cache.ttl


def test_expired_entry_is_read_from_the_database_again(client, redis_cache):
    create_book(client)
    client.get("/books")

    redis_cache.client.pexpire(BOOKS_LIST_KEY, 1)  # «время жизни истекло»
    time.sleep(0.05)

    assert client.get("/books").headers["X-Cache"] == "MISS"


def test_change_bypassing_the_api_stays_invisible_until_the_entry_expires(client, redis_cache, db):
    """Известное ограничение кэша, зафиксированное тестом: изменение в обход API (прямо в базе)
    кэш не видит и показывает старое до истечения TTL. Поэтому записывать данные нужно только через API."""
    book = create_book(client, title="Before")
    client.get(f"/books/{book['id']}")

    db.execute(text("UPDATE books SET title = 'After' WHERE id = :id"), {"id": book["id"]})
    db.commit()

    assert client.get(f"/books/{book['id']}").json()["title"] == "Before"  # устарело
    redis_cache.client.delete(book_key(book["id"]))
    assert client.get(f"/books/{book['id']}").json()["title"] == "After"
