"""Обычные тесты на дефекты контракта, найденные Schemathesis (tests/contract).

Автоматический перебор нашёл проблему, а здесь каждая зафиксирована понятным тестом: если регрессия вернётся,
имя упавшего теста сразу объяснит, что сломалось.
"""

import pytest

from app.schemas import INT32_MAX
from tests.api.helpers import create_book, create_reader


def _book_payload(**overrides) -> dict:
    payload = {"title": "T", "author": "A", "year": 2000, "copies_available": 1}
    payload.update(overrides)
    return payload


# ---------- типы чисел ----------


@pytest.mark.parametrize("field", ["copies_available", "year"])
@pytest.mark.parametrize("value", [True, False, "5", "abc", 1.5])
def test_number_fields_reject_booleans_strings_and_fractions(client, field, value):
    """false больше не принимается как 0, а "5" как 5: тип в запросе должен совпадать с контрактом."""
    response = client.post("/books", json=_book_payload(**{field: value}))

    assert response.status_code == 422, f"{field}={value!r}"


def test_integer_written_with_a_fraction_part_is_accepted(client):
    """5.0 это целое число по JSON Schema: принимается и сохраняется как 5."""
    response = client.post("/books", json=_book_payload(copies_available=5.0, year=1999.0))

    assert response.status_code == 201
    assert response.json()["copies_available"] == 5
    assert response.json()["year"] == 1999


def test_loan_ids_reject_booleans(client):
    response = client.post("/loans", json={"book_id": True, "reader_id": False})

    assert response.status_code == 422


# ---------- границы чисел: раньше 500 из-за ошибки SQL ----------


@pytest.mark.parametrize("path", ["/books/{id}", "/readers/{id}", "/readers/{id}/loans"])
@pytest.mark.parametrize("bad_id", [INT32_MAX + 1, 0, -1])
def test_ids_outside_the_allowed_range_in_the_path_return_422(client, path, bad_id):
    response = client.get(path.format(id=bad_id))

    assert response.status_code == 422


def test_largest_valid_id_is_a_normal_404_not_a_server_error(client):
    response = client.get(f"/books/{INT32_MAX}")

    assert response.status_code == 404


@pytest.mark.parametrize("field", ["book_id", "reader_id"])
def test_loan_body_ids_outside_the_range_return_422(client, field):
    book, reader = create_book(client), create_reader(client)
    payload = {"book_id": book["id"], "reader_id": reader["id"], field: INT32_MAX + 1}

    assert client.post("/loans", json=payload).status_code == 422


def test_return_with_huge_loan_id_returns_422(client):
    assert client.post(f"/loans/{INT32_MAX + 1}/return").status_code == 422


def test_copies_above_the_database_limit_are_rejected(client):
    response = client.post("/books", json=_book_payload(copies_available=INT32_MAX + 1))

    assert response.status_code == 422


# ---------- неверное тело запроса ----------


@pytest.mark.parametrize("path", ["/books", "/readers", "/loans"])
def test_body_that_is_not_text_returns_400_with_a_detail(client, path):
    """Байты, которые нельзя прочитать как текст (не UTF-8): FastAPI отвечает 400, и этот код есть в контракте."""
    not_utf8 = bytes([0x80, 0x03, 0xFF, 0xFE])

    response = client.post(path, content=not_utf8, headers={"Content-Type": "application/json"})

    assert response.status_code == 400
    assert "detail" in response.json()


@pytest.mark.parametrize("path", ["/books", "/readers", "/loans"])
def test_syntactically_broken_json_returns_422(client, path):
    """Текст, который не является JSON, это уже ошибка проверки данных (422), а не 400."""
    response = client.post(path, content=b"{not json", headers={"Content-Type": "application/json"})

    assert response.status_code == 422


# ---------- методы адреса /books/popular ----------


@pytest.mark.parametrize("method", ["put", "delete"])
def test_popular_books_address_supports_only_get(client, method):
    """Раньше PUT и DELETE уходили в маршрут /{book_id} и давали 422 («popular не число»)."""
    response = getattr(client, method)("/books/popular")

    assert response.status_code == 405
    assert response.headers["Allow"] == "GET"


# ---------- email ----------


@pytest.mark.parametrize(
    "email", ["a b@example.com", "a@b c.com", "a@b", "@b.c", "a@@b.c", "a\tb@c.d"]
)
def test_email_with_spaces_or_wrong_shape_is_rejected(client, email):
    assert client.post("/readers", json={"name": "N", "email": email}).status_code == 422


# ---------- символ NUL в тексте: PostgreSQL его не принимает, раньше был 500 ----------


@pytest.mark.parametrize(
    "path, payload",
    [
        ("/books", {"title": "a\u0000b", "author": "A"}),
        ("/books", {"title": "T", "author": "a\u0000b"}),
        ("/readers", {"name": "a\u0000b", "email": "a@b.c"}),
        ("/readers", {"name": "N", "email": "a@b.c\u0000"}),
    ],
    ids=["book-title", "book-author", "reader-name", "reader-email"],
)
def test_text_with_a_nul_character_is_rejected_not_a_server_error(client, path, payload):
    response = client.post(path, json=payload)

    assert response.status_code == 422
