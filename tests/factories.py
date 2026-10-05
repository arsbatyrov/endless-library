"""Маленькие помощники для подготовки данных в тестах.

В теста видна только значимая часть («книга с 0 экземпляров»),
а не пять строк подготовки.
"""

from itertools import count

from app.auth.passwords import hash_password
from app.models import Book, Reader, User

_counter = count(1)


def make_book(db, copies: int = 1, title: str = "Test book") -> Book:
    book = Book(title=title, author="Test author", copies_available=copies)
    db.add(book)
    db.commit()
    return book


def make_reader(db, name: str = "Test reader") -> Reader:
    # email уникален, поэтому у каждого читателя свой номер
    reader = Reader(name=name, email=f"reader{next(_counter)}@example.com")
    db.add(reader)
    db.commit()
    return reader


def make_user(
    db,
    role: str = "admin",
    username: str | None = None,
    reader=None,
    active: bool = True,
    password: str | None = None,
) -> User:
    """Account for tests. Without `password` the hash is a placeholder (data-model tests); with it, a real argon2id hash."""
    if role == "reader" and reader is None:
        reader = make_reader(db)
    user = User(
        username=username or f"user{next(_counter)}",
        password_hash=hash_password(password) if password is not None else "not-a-real-hash",
        role=role,
        reader_id=reader.id if reader is not None else None,
        is_active=active,
    )
    db.add(user)
    db.commit()
    return user
