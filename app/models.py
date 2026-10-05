from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    TypeDecorator,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Дата-время, которое всегда хранится в UTC и всегда читается с часовым поясом.

    PostgreSQL отдаёт время в часовом поясе текущего соединения (оно зависит от настроек
    сервера). Этот тип приводит прочитанное значение к UTC, чтобы расчёты (например,
    штраф) не зависели от настроек базы. Дату без часового пояса сохранить нельзя.
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
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.astimezone(UTC)


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


class User(Base):
    """Login account (AUTH-001). Roles: reader, librarian, admin.

    The rules are enforced by the database itself (see the constraints below), not only by the application:
    - the role must be one of the three known values;
    - a reader account is linked to a reader card (reader_id), staff accounts (librarian, admin) have no card;
    - one account per reader card;
    - the login is unique without regard to case ("Ann" and "ann" are the same login).
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('reader', 'librarian', 'admin')", name="users_role_check"),
        # "role is reader" must be equivalent to "reader_id is set"
        CheckConstraint(
            "(role = 'reader') = (reader_id IS NOT NULL)", name="users_reader_link_check"
        ),
        UniqueConstraint("reader_id", name="users_reader_id_key"),
        Index("users_username_lower_key", text("lower(username)"), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    # RESTRICT (the default): a reader card that has an account cannot be deleted by accident.
    reader_id: Mapped[int | None] = mapped_column(ForeignKey("readers.id"))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    reader: Mapped[Reader | None] = relationship()
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class RefreshToken(Base):
    """Server-side record of a refresh token (AUTH-001). Only the hash of the token is stored, never the token itself."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="refresh_tokens_token_hash_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Deleting a user deletes their tokens.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    # None: the token is still valid; a value means it was revoked at that moment.
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
