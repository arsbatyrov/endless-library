from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Пока None: книга на руках у читателя.
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    book: Mapped[Book] = relationship(back_populates="loans")
    reader: Mapped[Reader] = relationship(back_populates="loans")
