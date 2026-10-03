import pytest

from tests.api.helpers import create_book, create_reader, issue_loan


def test_create_reader_returns_201_and_reader_with_id(client):
    response = client.post("/readers", json={"name": "Иван", "email": "ivan@example.com"})

    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "Иван", "email": "ivan@example.com"}


def test_create_reader_with_duplicate_email_returns_409(client):
    create_reader(client, email="same@example.com")

    response = client.post("/readers", json={"name": "Другой", "email": "same@example.com"})

    assert response.status_code == 409
    assert len(client.get("/readers").json()) == 1


def test_failed_duplicate_does_not_break_following_requests(client):
    """После отката неудачной вставки (409) сессия должна оставаться рабочей."""
    create_reader(client, email="same@example.com")
    client.post("/readers", json={"name": "Дубль", "email": "same@example.com"})

    response = client.post("/readers", json={"name": "Новый", "email": "new@example.com"})

    assert response.status_code == 201


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "email": "a@b.co"},  # пустое имя
        {"name": "N"},  # нет email
        {"email": "a@b.co"},  # нет имени
        {"name": "N", "email": "not-an-email"},  # email без @
        {"name": "N", "email": "a@b"},  # нет домена верхнего уровня
        {"name": "N", "email": "a b@c.co"},  # пробел в email
    ],
)
def test_create_reader_rejects_invalid_payload_with_422(client, payload):
    response = client.post("/readers", json=payload)

    assert response.status_code == 422


def test_get_reader_returns_it(client):
    reader = create_reader(client)

    response = client.get(f"/readers/{reader['id']}")

    assert response.status_code == 200
    assert response.json() == reader


def test_get_unknown_reader_returns_404(client):
    response = client.get("/readers/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Reader not found"}


def test_list_readers_returns_all_ordered_by_id(client):
    first = create_reader(client)
    second = create_reader(client)

    assert client.get("/readers").json() == [first, second]


def test_put_updates_reader(client):
    reader = create_reader(client)

    response = client.put(
        f"/readers/{reader['id']}", json={"name": "Новое имя", "email": reader["email"]}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Новое имя"


def test_put_with_own_email_is_not_a_conflict(client):
    reader = create_reader(client, email="mine@example.com")

    response = client.put(
        f"/readers/{reader['id']}", json={"name": "Same", "email": "mine@example.com"}
    )

    assert response.status_code == 200


def test_put_with_email_of_another_reader_returns_409(client):
    create_reader(client, email="taken@example.com")
    other = create_reader(client, email="other@example.com")

    response = client.put(
        f"/readers/{other['id']}", json={"name": "N", "email": "taken@example.com"}
    )

    assert response.status_code == 409
    assert client.get(f"/readers/{other['id']}").json()["email"] == "other@example.com"


def test_put_unknown_reader_returns_404(client):
    response = client.put("/readers/999", json={"name": "N", "email": "n@example.com"})

    assert response.status_code == 404


def test_delete_reader_returns_204_then_404(client):
    reader = create_reader(client)

    first = client.delete(f"/readers/{reader['id']}")
    second = client.delete(f"/readers/{reader['id']}")

    assert first.status_code == 204
    assert second.status_code == 404


def test_delete_reader_with_loan_history_returns_409(client):
    book = create_book(client)
    reader = create_reader(client)
    issue_loan(client, book["id"], reader["id"])

    response = client.delete(f"/readers/{reader['id']}")

    assert response.status_code == 409
    assert client.get(f"/readers/{reader['id']}").status_code == 200


# ---------- /readers/{id}/loans ----------


def test_reader_loans_lists_only_books_on_hands(client):
    book = create_book(client, copies_available=3)
    reader = create_reader(client)
    returned = issue_loan(client, book["id"], reader["id"]).json()
    still_on_hands = issue_loan(client, book["id"], reader["id"]).json()
    client.post(f"/loans/{returned['id']}/return")

    response = client.get(f"/readers/{reader['id']}/loans")

    assert response.status_code == 200
    assert [loan["id"] for loan in response.json()] == [still_on_hands["id"]]


def test_reader_loans_is_empty_for_new_reader(client):
    reader = create_reader(client)

    assert client.get(f"/readers/{reader['id']}/loans").json() == []


def test_reader_loans_for_unknown_reader_returns_404(client):
    response = client.get("/readers/999/loans")

    assert response.status_code == 404
