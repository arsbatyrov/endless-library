from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Дата-время, которое всегда хранится в UTC и всегда читается с часовым поясом.

    SQLite не хранит часовой пояс и отдаёт «наивные» даты, из-за чего вычитание
    `now - due_at` падало бы с TypeError. Этот тип возвращает дату в UTC в любой базе.
    """

    impl = DateTime
    cache_ok = True

    def __init__(self):
        super().__init__(timezone=True)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime is not allowed, use timezone-aware UTC")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    author: Mapped[str] = mapped_column(String(200))
    year: Mapped[int | None]
    copies_available: Mapped[int] = mapped_column(default=1)

    loans: Mapped[list["Loan"]] = relationship(back_populates="book")


class Reader(Base):
    __tablename__ = "readers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True)

    loans: Mapped[list["Loan"]] = relationship(back_populates="reader")


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    reader_id: Mapped[int] = mapped_column(ForeignKey("readers.id"))
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime())
    # Пока None: книга на руках у читателя.
    returned_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    book: Mapped[Book] = relationship(back_populates="loans")
    reader: Mapped[Reader] = relationship(back_populates="loans")
