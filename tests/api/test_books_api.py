import pytest

from tests.api.helpers import create_book, create_reader, issue_loan

# ---------- создание ----------


def test_create_book_returns_201_and_book_with_id(client):
    response = client.post(
        "/books",
        json={"title": "Война и мир", "author": "Толстой", "year": 1869, "copies_available": 2},
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "title": "Война и мир",
        "author": "Толстой",
        "year": 1869,
        "copies_available": 2,
    }


def test_create_book_uses_defaults_for_optional_fields(client):
    response = client.post("/books", json={"title": "Идиот", "author": "Достоевский"})

    assert response.status_code == 201
    assert response.json()["year"] is None
    assert response.json()["copies_available"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "", "author": "X"},  # пустое название
        {"title": "T", "author": ""},  # пустой автор
        {"author": "X"},  # нет названия
        {"title": "T"},  # нет автора
        {"title": "T", "author": "X", "copies_available": -1},  # отрицательное количество
        {"title": "T", "author": "X", "year": 2101},  # год больше допустимого
        {"title": "T", "author": "X", "year": "не число"},  # неверный тип
        {"title": "T" * 201, "author": "X"},  # слишком длинное название
    ],
)
def test_create_book_rejects_invalid_payload_with_422(client, payload):
    response = client.post("/books", json=payload)

    assert response.status_code == 422


def test_invalid_create_does_not_save_anything(client):
    client.post("/books", json={"title": "", "author": "X"})

    assert client.get("/books").json() == []


# ---------- чтение ----------


def test_get_book_returns_it(client):
    book = create_book(client, title="Мастер и Маргарита")

    response = client.get(f"/books/{book['id']}")

    assert response.status_code == 200
    assert response.json() == book


def test_get_unknown_book_returns_404(client):
    response = client.get("/books/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Book not found"}


def test_get_book_with_non_numeric_id_returns_422(client):
    response = client.get("/books/abc")

    assert response.status_code == 422


def test_list_books_is_empty_at_start(client):
    response = client.get("/books")

    assert response.status_code == 200
    assert response.json() == []


def test_list_books_returns_all_ordered_by_id(client):
    first = create_book(client, title="A")
    second = create_book(client, title="B")

    response = client.get("/books")

    assert response.json() == [first, second]


def test_get_is_safe_and_idempotent(client):
    book = create_book(client)

    first = client.get(f"/books/{book['id']}")
    second = client.get(f"/books/{book['id']}")

    assert first.json() == second.json() == book
    assert len(client.get("/books").json()) == 1


# ---------- изменение (PUT) ----------


def test_put_replaces_all_fields(client):
    book = create_book(client, title="Old", author="Old", year=1990, copies_available=1)
    new_data = {"title": "New", "author": "New", "year": 2020, "copies_available": 7}

    response = client.put(f"/books/{book['id']}", json=new_data)

    assert response.status_code == 200
    assert response.json() == {"id": book["id"], **new_data}
    assert client.get(f"/books/{book['id']}").json() == {"id": book["id"], **new_data}


def test_put_is_idempotent(client):
    book = create_book(client)
    new_data = {"title": "New", "author": "New", "year": 2020, "copies_available": 7}

    first = client.put(f"/books/{book['id']}", json=new_data)
    second = client.put(f"/books/{book['id']}", json=new_data)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(client.get("/books").json()) == 1


def test_put_unknown_book_returns_404(client):
    response = client.put("/books/999", json={"title": "T", "author": "A"})

    assert response.status_code == 404


def test_put_with_invalid_payload_returns_422_and_keeps_book_unchanged(client):
    book = create_book(client, title="Keep me")

    response = client.put(f"/books/{book['id']}", json={"title": "", "author": "A"})

    assert response.status_code == 422
    assert client.get(f"/books/{book['id']}").json()["title"] == "Keep me"


# ---------- удаление ----------


def test_delete_book_returns_204_and_book_is_gone(client):
    book = create_book(client)

    response = client.delete(f"/books/{book['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/books/{book['id']}").status_code == 404


def test_delete_is_idempotent_for_state_but_second_call_returns_404(client):
    book = create_book(client)
    client.delete(f"/books/{book['id']}")

    second = client.delete(f"/books/{book['id']}")

    assert second.status_code == 404
    assert client.get("/books").json() == []


def test_delete_book_with_loan_history_returns_409(client):
    book = create_book(client)
    reader = create_reader(client)
    issue_loan(client, book["id"], reader["id"])

    response = client.delete(f"/books/{book['id']}")

    assert response.status_code == 409
    assert client.get(f"/books/{book['id']}").status_code == 200
