from datetime import datetime
from typing import Annotated, Literal

from fastapi import Path
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

# Столбцы id и счётчики в базе имеют тип integer (32 бита). Без верхней границы число побольше доходило бы до
# SQL и давало 500 вместо понятной ошибки 422 (это нашёл Schemathesis).
INT32_MAX = 2_147_483_647


# PostgreSQL не хранит символ NUL (\u0000) в тексте: без запрета он дошёл бы до базы и дал бы 500.
# Запрет записан шаблоном (pattern), чтобы он попал и в OpenAPI-контракт, а не только работал внутри сервера.
NO_NUL = r"^[^\u0000]*$"


def _json_integer(value):
    """Целое по правилам JSON Schema: 5 и 5.0 подходят, а true/false и строки нет."""
    if isinstance(value, bool):
        raise ValueError("Input should be an integer, not a boolean")
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def json_int(ge: int, le: int):
    """Целое число с границами. Границы стоят ВНУТРИ Annotated, до валидатора: если поставить их снаружи,
    pydantic теряет их в OpenAPI (пишет несуществующие ключевые слова ge/le), и контракт обещает больше,
    чем сервер принимает. Это тоже нашёл Schemathesis."""
    return Annotated[int, Field(ge=ge, le=le), BeforeValidator(_json_integer)]


Year = json_int(ge=0, le=2100)
Copies = json_int(ge=0, le=INT32_MAX)
# id в теле запроса и в адресе: положительное число в пределах integer
EntityId = json_int(ge=1, le=INT32_MAX)
PathId = Annotated[int, Path(ge=1, le=INT32_MAX)]


class ErrorResponse(BaseModel):
    """Тело ошибки 404/409: причина строкой."""

    detail: str


class StatusResponse(BaseModel):
    """Ответ проверок состояния (/health, /ready)."""

    status: str


class BookCreate(BaseModel):
    """Что клиент присылает при создании книги (без id).

    strict: типы не приводятся «по-дружески». Иначе false принималось бы как число 0, а "5" как 5;
    такие запросы нарушают контракт, и их нужно отклонять (это нашёл Schemathesis).
    Исключение сделано сознательно: целое число вида 5.0 допустимо по спецификации JSON Schema (см. _json_integer).
    """

    model_config = ConfigDict(strict=True)

    title: str = Field(min_length=1, max_length=200, pattern=NO_NUL)
    author: str = Field(min_length=1, max_length=200, pattern=NO_NUL)
    year: Year | None = None
    copies_available: Copies = 1


class BookRead(BookCreate):
    """Что мы отдаём в ответе (с id)."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class PopularBook(BaseModel):
    """Книга в рейтинге популярности: сама книга и сколько раз её выдавали."""

    book: BookRead
    loans: int


class LoginRequest(BaseModel):
    """Credentials. Strict types and length limits: an overlong password must never reach the (expensive) hashing."""

    model_config = ConfigDict(strict=True)

    username: str = Field(min_length=1, max_length=64, pattern=NO_NUL)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the access token expires


class MeResponse(BaseModel):
    """The signed-in user's own profile. Never contains the password hash."""

    id: int
    username: str
    role: str
    reader_id: int | None


class PasswordChangeRequest(BaseModel):
    """Length limits keep an overlong password away from the (expensive) hashing; the policy is checked in the service."""

    model_config = ConfigDict(strict=True)

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(max_length=128)


Username = Annotated[str, Field(min_length=1, max_length=64, pattern=NO_NUL)]
Role = Literal["reader", "librarian", "admin"]


class UserCreate(BaseModel):
    """A new account. The password policy (length, not equal to the login) is checked by the service."""

    model_config = ConfigDict(strict=True)

    username: Username
    password: str = Field(min_length=8, max_length=128)
    role: Role
    reader_id: EntityId | None = None  # required for role=reader, forbidden for the others


class UserRead(BaseModel):
    """An account as shown to staff. Never contains the password or its hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: Role
    reader_id: int | None
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class UserUpdate(BaseModel):
    """Partial update: only the fields that are sent change. At least one is required; null is not a value."""

    # minProperties tells API clients (and the contract tests) that an empty object is not a valid update.
    model_config = ConfigDict(strict=True, json_schema_extra={"minProperties": 1})

    # `= Field(default=None)` without `| None`: the field may be omitted, but an explicit null is refused.
    is_active: bool = Field(default=None)
    role: Role = Field(default=None)
    # Needed when an account becomes a reader (the card to link); refused for the other roles. Admins only.
    reader_id: EntityId = Field(default=None)

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("Send at least one of: is_active, role, reader_id")
        return self


class PasswordReset(BaseModel):
    model_config = ConfigDict(strict=True)

    new_password: str = Field(min_length=8, max_length=128)


class ReaderCreate(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str = Field(min_length=1, max_length=200, pattern=NO_NUL)
    # Пробельные символы перечислены явно, без \s: в Python, Rust и ECMAScript \s означает разные наборы символов,
    # а контракт (OpenAPI) читают клиенты на разных языках.
    email: str = Field(
        pattern=r"^[^@ \t\r\n\f\v\u0000]+@[^@ \t\r\n\f\v\u0000]+\.[^@ \t\r\n\f\v\u0000]+$",
        max_length=200,
    )


class ReaderRead(ReaderCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class LoanCreate(BaseModel):
    model_config = ConfigDict(strict=True)

    book_id: EntityId
    reader_id: EntityId


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
