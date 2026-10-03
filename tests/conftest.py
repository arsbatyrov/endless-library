import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (регистрирует таблицы в Base)
from app.database import Base, get_db
from app.main import app


@pytest.fixture
def db():
    """Чистая база SQLite в памяти и сессия на каждый тест.

    После теста база исчезает, поэтому тесты не влияют друг на друга
    и не трогают library.db.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        # TestClient вызывает эндпоинты в другом потоке. Без этих двух настроек
        # поток получил бы своё, пустое соединение с «другой» базой в памяти.
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(db):
    """HTTP-клиент, подключённый к приложению, которое работает на тестовой базе `db`."""

    def override_get_db():
        yield db

    # Подмена зависимости: везде, где эндпоинт просит Depends(get_db),
    # FastAPI теперь подставит нашу тестовую сессию.
    app.dependency_overrides[get_db] = override_get_db

    # Без `with`: так не запускается lifespan, который создал бы таблицы
    # в настоящей базе library.db. Нам нужны только тестовые таблицы.
    yield TestClient(app)

    app.dependency_overrides.clear()
