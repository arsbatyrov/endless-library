from datetime import datetime, timedelta

from app.services.loans import LOAN_PERIOD_DAYS, MAX_ACTIVE_LOANS
from tests.api.helpers import create_book, create_reader, issue_loan


def copies_of(client, book_id: int) -> int:
    return client.get(f"/books/{book_id}").json()["copies_available"]


# ---------- выдача ----------


def test_issue_book_returns_201_and_loan(client):
    book = create_book(client, copies_available=2)
    reader = create_reader(client)

    response = issue_loan(client, book["id"], reader["id"])

    assert response.status_code == 201
    loan = response.json()
    assert loan["book_id"] == book["id"]
    assert loan["reader_id"] == reader["id"]
    assert loan["returned_at"] is None


def test_loan_is_due_in_the_agreed_period(client):
    book = create_book(client)
    reader = create_reader(client)

    loan = issue_loan(client, book["id"], reader["id"]).json()

    issued = datetime.fromisoformat(loan["issued_at"])
    due = datetime.fromisoformat(loan["due_at"])
    assert due - issued == timedelta(days=LOAN_PERIOD_DAYS)


def test_issue_book_decreases_copies_visible_through_books_api(client):
    book = create_book(client, copies_available=2)
    reader = create_reader(client)

    issue_loan(client, book["id"], reader["id"])

    assert copies_of(client, book["id"]) == 1


def test_issue_book_without_copies_returns_409(client):
    book = create_book(client, copies_available=0)
    reader = create_reader(client)

    response = issue_loan(client, book["id"], reader["id"])

    assert response.status_code == 409
    assert response.json() == {"detail": "No copies available"}


def test_issue_book_over_limit_returns_409(client):
    """Сам расчёт границы лимита проверен unit-тестами, здесь только код ответа."""
    book = create_book(client, copies_available=10)
    reader = create_reader(client)
    for _ in range(MAX_ACTIVE_LOANS):
        assert issue_loan(client, book["id"], reader["id"]).status_code == 201

    response = issue_loan(client, book["id"], reader["id"])

    assert response.status_code == 409
    assert copies_of(client, book["id"]) == 10 - MAX_ACTIVE_LOANS


def test_issue_book_for_unknown_book_returns_404(client):
    reader = create_reader(client)

    assert issue_loan(client, 999, reader["id"]).status_code == 404


def test_issue_book_for_unknown_reader_returns_404(client):
    book = create_book(client)

    assert issue_loan(client, book["id"], 999).status_code == 404


def test_issue_book_with_missing_field_returns_422(client):
    book = create_book(client)

    response = client.post("/loans", json={"book_id": book["id"]})

    assert response.status_code == 422


def test_issue_book_with_wrong_type_returns_422(client):
    response = client.post("/loans", json={"book_id": "abc", "reader_id": 1})

    assert response.status_code == 422


# ---------- возврат ----------


def test_return_book_returns_200_with_zero_fine_when_on_time(client):
    book = create_book(client)
    reader = create_reader(client)
    loan = issue_loan(client, book["id"], reader["id"]).json()

    response = client.post(f"/loans/{loan['id']}/return")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == loan["id"]
    assert body["returned_at"] is not None
    assert body["fine"] == 0


def test_return_book_restores_copy(client):
    book = create_book(client, copies_available=1)
    reader = create_reader(client)
    loan = issue_loan(client, book["id"], reader["id"]).json()
    assert copies_of(client, book["id"]) == 0

    client.post(f"/loans/{loan['id']}/return")

    assert copies_of(client, book["id"]) == 1


def test_return_book_twice_returns_409_and_does_not_add_copy(client):
    book = create_book(client, copies_available=1)
    reader = create_reader(client)
    loan = issue_loan(client, book["id"], reader["id"]).json()
    client.post(f"/loans/{loan['id']}/return")

    second = client.post(f"/loans/{loan['id']}/return")

    assert second.status_code == 409
    assert second.json() == {"detail": "Book already returned"}
    assert copies_of(client, book["id"]) == 1


def test_return_unknown_loan_returns_404(client):
    response = client.post("/loans/999/return")

    assert response.status_code == 404


# ---------- сценарий целиком ----------


def test_full_lifecycle_second_reader_gets_the_book_after_return(client):
    book = create_book(client, copies_available=1)
    first, second = create_reader(client), create_reader(client)

    first_loan = issue_loan(client, book["id"], first["id"]).json()
    refused = issue_loan(client, book["id"], second["id"])
    client.post(f"/loans/{first_loan['id']}/return")
    accepted = issue_loan(client, book["id"], second["id"])

    assert refused.status_code == 409
    assert accepted.status_code == 201
    assert copies_of(client, book["id"]) == 0
