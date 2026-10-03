from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Book, Loan, Reader
from app.services.errors import BusinessRuleError, NotFoundError
from app.services.fines import calculate_fine

LOAN_PERIOD_DAYS = 14
MAX_ACTIVE_LOANS = 3


def count_active_loans(db: Session, reader_id: int) -> int:
    stmt = select(func.count()).select_from(Loan).where(
        Loan.reader_id == reader_id, Loan.returned_at.is_(None)
    )
    return db.scalar(stmt)


def get_active_loans(db: Session, reader_id: int) -> list[Loan]:
    stmt = (
        select(Loan)
        .where(Loan.reader_id == reader_id, Loan.returned_at.is_(None))
        .order_by(Loan.id)
    )
    return list(db.scalars(stmt))


def issue_book(db: Session, book_id: int, reader_id: int, now: datetime) -> Loan:
    reader = db.get(Reader, reader_id)
    if reader is None:
        raise NotFoundError("Reader not found")
    # FOR UPDATE блокирует строку книги до конца транзакции: параллельный запрос на ту же книгу
    # подождёт, а потом прочитает уже актуальное число экземпляров. Без блокировки два запроса
    # могли бы одновременно увидеть «остался 1 экземпляр» и оба выдать его.
    # populate_existing: перечитать значения из базы, а не взять устаревшие из памяти сессии.
    book = db.get(Book, book_id, with_for_update=True, populate_existing=True)
    if book is None:
        raise NotFoundError("Book not found")

    if book.copies_available <= 0:
        raise BusinessRuleError("No copies available")
    if count_active_loans(db, reader_id) >= MAX_ACTIVE_LOANS:
        raise BusinessRuleError(f"Reader already has {MAX_ACTIVE_LOANS} active loans")

    loan = Loan(
        book=book,
        reader=reader,
        issued_at=now,
        due_at=now + timedelta(days=LOAN_PERIOD_DAYS),
    )
    book.copies_available -= 1
    db.add(loan)
    db.commit()
    db.refresh(loan)
    return loan


def return_book(db: Session, loan_id: int, now: datetime) -> tuple[Loan, int]:
    """Возвращает книгу. Результат: (выдача, размер штрафа)."""
    # Блокируем выдачу: два одновременных возврата не смогут оба пройти проверку ниже.
    loan = db.get(Loan, loan_id, with_for_update=True, populate_existing=True)
    if loan is None:
        raise NotFoundError("Loan not found")
    if loan.returned_at is not None:
        raise BusinessRuleError("Book already returned")

    # Книгу тоже блокируем: счётчик экземпляров меняют и выдача, и возврат.
    book = db.get(Book, loan.book_id, with_for_update=True, populate_existing=True)
    loan.returned_at = now
    book.copies_available += 1
    fine = calculate_fine(loan.due_at, now)
    db.commit()
    db.refresh(loan)
    return loan, fine


def ensure_book_has_no_loans(db: Session, book_id: int) -> None:
    stmt = select(func.count()).select_from(Loan).where(Loan.book_id == book_id)
    if db.scalar(stmt) > 0:
        raise BusinessRuleError("Book has loan history and cannot be deleted")


def ensure_reader_has_no_loans(db: Session, reader_id: int) -> None:
    stmt = select(func.count()).select_from(Loan).where(Loan.reader_id == reader_id)
    if db.scalar(stmt) > 0:
        raise BusinessRuleError("Reader has loan history and cannot be deleted")
