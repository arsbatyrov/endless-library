"""Помощники для API-тестов: создают данные через сам API."""


def create_book(client, **overrides) -> dict:
    payload = {"title": "Test book", "author": "Test author", "year": 2000, "copies_available": 1}
    payload.update(overrides)
    response = client.post("/books", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


_reader_counter = 0


def create_reader(client, **overrides) -> dict:
    global _reader_counter
    _reader_counter += 1
    payload = {"name": "Test reader", "email": f"api-reader{_reader_counter}@example.com"}
    payload.update(overrides)
    response = client.post("/readers", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def issue_loan(client, book_id: int, reader_id: int):
    """Возвращает сам ответ, а не JSON: так тест может проверить и код ответа."""
    return client.post("/loans", json={"book_id": book_id, "reader_id": reader_id})
