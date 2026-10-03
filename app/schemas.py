from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BookCreate(BaseModel):
    """Что клиент присылает при создании книги (без id)."""

    title: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=200)
    year: int | None = Field(default=None, ge=0, le=2100)
    copies_available: int = Field(default=1, ge=0)


class BookRead(BookCreate):
    """Что мы отдаём в ответе (с id)."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class ReaderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)


class ReaderRead(ReaderCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class LoanCreate(BaseModel):
    book_id: int
    reader_id: int


class LoanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    reader_id: int
    issued_at: datetime
    due_at: datetime
    returned_at: datetime | None


class LoanReturnRead(LoanRead):
    """Ответ при возврате: выдача плюс размер штрафа."""

    fine: int
