"""Ограничения самой базы данных: «второй рубеж» защиты.

Приложение уже проверяет эти правила (схемы Pydantic, сервис), поэтому из API до базы
такие данные обычно не доходят. Здесь мы идём в обход приложения, напрямую в базу, и
убеждаемся, что PostgreSQL отклоняет некорректные данные сам. Это страховка на случай
ошибки в коде, нового сервиса, ручной правки данных или скрипта миграции.
"""

from datetime import UTC, datetime

import psycopg.errors as pg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError

from app.models import Book, Loan, Reader
from tests.factories import make_book, make_reader

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_database_rejects_duplicate_reader_email(db):
    db.add(Reader(name="A", email="dup@example.com"))
    db.commit()
    db.add(Reader(name="B", email="dup@example.com"))

    with pytest.raises(IntegrityError) as error:
        db.commit()

    assert isinstance(error.value.orig, pg.UniqueViolation)
    assert error.value.orig.diag.constraint_name == "readers_email_key"


def test_database_rejects_loan_for_unknown_book(db):
    reader = make_reader(db)
    db.add(Loan(book_id=999, reader_id=reader.id, issued_at=NOW, due_at=NOW))

    with pytest.raises(IntegrityError) as error:
        db.commit()

    assert isinstance(error.value.orig, pg.ForeignKeyViolation)
    assert error.value.orig.diag.constraint_name == "loans_book_id_fkey"


def test_database_rejects_loan_for_unknown_reader(db):
    book = make_book(db)
    db.add(Loan(book_id=book.id, reader_id=999, issued_at=NOW, due_at=NOW))

    with pytest.raises(IntegrityError) as error:
        db.commit()

    assert isinstance(error.value.orig, pg.ForeignKeyViolation)
    assert error.value.orig.diag.constraint_name == "loans_reader_id_fkey"


def test_database_rejects_title_longer_than_column(db):
    db.add(Book(title="x" * 201, author="Author"))

    with pytest.raises(DataError) as error:
        db.commit()

    assert isinstance(error.value.orig, pg.StringDataRightTruncation)


@pytest.mark.parametrize(
    "entity, missing_column",
    [
        (lambda: Book(title=None, author="Author"), "title"),
        (lambda: Book(title="Title", author=None), "author"),
        (lambda: Reader(name=None, email="a@example.com"), "name"),
        (lambda: Reader(name="Name", email=None), "email"),
    ],
    ids=["book.title", "book.author", "reader.name", "reader.email"],
)
def test_database_rejects_null_in_required_column(db, entity, missing_column):
    db.add(entity())

    with pytest.raises(IntegrityError) as error:
        db.commit()

    assert isinstance(error.value.orig, pg.NotNullViolation)
    assert error.value.orig.diag.column_name == missing_column


def test_database_rejects_loan_without_due_date(db):
    book, reader = make_book(db), make_reader(db)
    db.add(Loan(book_id=book.id, reader_id=reader.id, issued_at=NOW, due_at=None))

    with pytest.raises(IntegrityError) as error:
        db.commit()

    assert isinstance(error.value.orig, pg.NotNullViolation)
    assert error.value.orig.diag.column_name == "due_at"


@pytest.mark.parametrize("table", ["books", "readers"])
def test_database_blocks_deleting_rows_that_loans_refer_to(db, table):
    """Даже если приложение не остановит удаление, база не даст создать «висящие» выдачи."""
    book, reader = make_book(db), make_reader(db)
    db.add(Loan(book_id=book.id, reader_id=reader.id, issued_at=NOW, due_at=NOW))
    db.commit()

    with pytest.raises(IntegrityError) as error:
        db.execute(text(f"DELETE FROM {table}"))  # напрямую SQL, без ORM

    assert isinstance(error.value.orig, pg.ForeignKeyViolation)


def test_defaults_are_applied_by_the_application_not_by_the_database(db):
    """Фиксируем текущее поведение: значения по умолчанию (default=1) задаёт SQLAlchemy.

    Строка, вставленная голым SQL без copies_available, в базе не получит значения 1
    и будет отклонена. Если позже мы добавим server_default, этот тест нужно будет
    осознанно изменить.
    """
    with pytest.raises(IntegrityError) as error:
        db.execute(text("INSERT INTO books (title, author) VALUES ('T', 'A')"))

    assert isinstance(error.value.orig, pg.NotNullViolation)
    assert error.value.orig.diag.column_name == "copies_available"
