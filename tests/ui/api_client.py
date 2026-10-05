"""Клиент API для подготовки данных в UI-тестах.

Данные создаём напрямую через API (быстро и надёжно), а проверяем через интерфейс.
Так тест не зависит от того, как именно в интерфейсе устроено создание, и не тратит время
на лишние клики.
"""

from itertools import count

import httpx2 as httpx

_email_counter = count(1)


class ApiClient:
    def __init__(self, base_url: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = httpx.Client(base_url=base_url, timeout=10, headers=headers)

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, payload: dict | None = None) -> dict:
        response = self._client.post(path, json=payload)
        assert response.status_code in (200, 201), (
            f"POST {path}: {response.status_code} {response.text}"
        )
        return response.json()

    def create_book(
        self,
        title: str = "Тестовая книга",
        author: str = "Тестовый автор",
        year: int | None = 2000,
        copies: int = 1,
    ) -> dict:
        return self._post(
            "/books", {"title": title, "author": author, "year": year, "copies_available": copies}
        )

    def create_reader(self, name: str = "Тестовый читатель", email: str | None = None) -> dict:
        email = email or f"reader{next(_email_counter)}@example.com"
        return self._post("/readers", {"name": name, "email": email})

    def issue_loan(self, book_id: int, reader_id: int) -> dict:
        return self._post("/loans", {"book_id": book_id, "reader_id": reader_id})

    def books(self) -> list[dict]:
        return self._client.get("/books").json()

    def readers(self) -> list[dict]:
        return self._client.get("/readers").json()

    def active_loans(self, reader_id: int) -> list[dict]:
        return self._client.get(f"/readers/{reader_id}/loans").json()

    def create_account(
        self, username: str, password: str, role: str = "librarian", reader_id: int | None = None
    ) -> dict:
        """Account for a person (AUTH-015). A reader account needs the id of a reader card."""
        payload = {"username": username, "password": password, "role": role, "reader_id": reader_id}
        return self._post("/users", payload)

    def accounts(self) -> list[dict]:
        return self._client.get("/users").json()

    def set_account_active(self, user_id: int, active: bool) -> None:
        response = self._client.patch(f"/users/{user_id}", json={"is_active": active})
        assert response.status_code == 200, response.text
