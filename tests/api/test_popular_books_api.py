"""Популярные книги: счётчики выдач в Redis с пересчётом из базы (источник правды: Postgres)."""

import pytest

from app.cache import POPULAR_KEY, POPULAR_TTL_SECONDS
from tests.api.helpers import create_book, create_reader, issue_loan


def issue_times(client, book, times: int) -> None:
    """Выдаёт книгу `times` раз разным читателям (у одного читателя лимит активных выдач)."""
    for _ in range(times):
        reader = create_reader(client)
        assert issue_loan(client, book["id"], reader["id"]).status_code == 201


def test_empty_library_has_no_popular_books(client):
    response = client.get("/books/popular")

    assert response.status_code == 200
    assert response.json() == []


def test_books_are_sorted_by_number_of_loans(client):
    rare = create_book(client, title="Rare", copies_available=5)
    hit = create_book(client, title="Hit", copies_available=5)
    middle = create_book(client, title="Middle", copies_available=5)
    issue_times(client, rare, 1)
    issue_times(client, hit, 3)
    issue_times(client, middle, 2)

    popular = client.get("/books/popular").json()

    assert [(item["book"]["title"], item["loans"]) for item in popular] == [
        ("Hit", 3),
        ("Middle", 2),
        ("Rare", 1),
    ]


def test_books_with_the_same_number_of_loans_go_in_id_order(client):
    first = create_book(client, title="First", copies_available=2)
    second = create_book(client, title="Second", copies_available=2)
    issue_times(client, second, 1)
    issue_times(client, first, 1)

    titles = [item["book"]["title"] for item in client.get("/books/popular").json()]

    assert titles == ["First", "Second"]


def test_limit_restricts_the_list(client):
    for number in range(3):
        issue_times(client, create_book(client, title=f"Book {number}", copies_available=2), 1)

    assert len(client.get("/books/popular?limit=2").json()) == 2


@pytest.mark.parametrize("limit", [0, 21, -1, "many"])
def test_invalid_limit_is_rejected(client, limit):
    assert client.get(f"/books/popular?limit={limit}").status_code == 422


def test_returned_loans_still_count_as_popularity(client):
    book = create_book(client, copies_available=1)
    reader = create_reader(client)
    loan = issue_loan(client, book["id"], reader["id"]).json()
    client.post(f"/loans/{loan['id']}/return")

    assert client.get("/books/popular").json()[0]["loans"] == 1


def test_popular_book_data_is_taken_fresh_from_the_database(client, redis_cache):
    """В Redis хранятся только счётчики: правка названия видна в рейтинге сразу."""
    book = create_book(client, title="Old", copies_available=2)
    issue_times(client, book, 1)
    client.get("/books/popular")

    client.put(f"/books/{book['id']}", json={"title": "New", "author": "A", "copies_available": 2})

    assert client.get("/books/popular").json()[0]["book"]["title"] == "New"


def test_counter_is_built_from_the_database_on_first_read(client, redis_cache):
    book = create_book(client, copies_available=3)
    issue_times(client, book, 2)  # счётчика в Redis ещё нет: выдачи его не создают

    client.get("/books/popular")

    assert redis_cache.client.zscore(POPULAR_KEY, str(book["id"])) == 2


def test_next_loan_increments_the_existing_counter(client, redis_cache):
    book = create_book(client, copies_available=3)
    issue_times(client, book, 1)
    client.get("/books/popular")  # счётчик собран

    issue_times(client, book, 1)

    assert redis_cache.client.zscore(POPULAR_KEY, str(book["id"])) == 2
    assert client.get("/books/popular").json()[0]["loans"] == 2


def test_counter_is_rebuilt_after_redis_loses_its_data(client, redis_cache):
    """Redis перезапустили (данных нет): рейтинг не пропадает, а пересобирается из базы."""
    book = create_book(client, copies_available=3)
    issue_times(client, book, 2)
    client.get("/books/popular")

    redis_cache.client.flushdb()

    assert client.get("/books/popular").json()[0]["loans"] == 2


def test_counter_has_a_time_to_live_so_drift_heals_itself(client, redis_cache):
    book = create_book(client, copies_available=2)
    issue_times(client, book, 1)
    client.get("/books/popular")

    assert 0 < redis_cache.client.ttl(POPULAR_KEY) <= POPULAR_TTL_SECONDS
