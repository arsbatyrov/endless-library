"""Маленькие помощники для подготовки данных в тестах.

В теста видна только значимая часть («книга с 0 экземпляров»),
а не пять строк подготовки.
"""

from itertools import count

from app.models import Book, Reader

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
