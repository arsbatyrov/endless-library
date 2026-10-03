import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (регистрирует таблицы в Base)
from app.database import Base


@pytest.fixture
def db():
    """Чистая база SQLite в памяти и сессия на каждый тест.

    После теста база исчезает, поэтому тесты не влияют друг на друга
    и не трогают library.db.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        yield session
    engine.dispose()
