import os
from pathlib import Path

import pytest
from alembic import command
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tests.db_utils import ROOT, alembic_config, ensure_database, reset_schema

# ---------------------------------------------------------------------------
# Адрес ТЕСТОВОЙ базы. Это нужно сделать до импорта приложения: app.database
# читает DATABASE_URL при импорте, и в тестах он должен указывать на <имя>_test.
# ---------------------------------------------------------------------------
load_dotenv(ROOT / ".env")

_dev_url = os.environ.get("DATABASE_URL")
if not _dev_url:
    pytest.exit(
        "DATABASE_URL is not set. Copy .env.example to .env and start the database: "
        "docker compose up -d db",
        returncode=2,
    )

TEST_URL = make_url(_dev_url)
if not TEST_URL.database.endswith("_test"):
    TEST_URL = TEST_URL.set(database=f"{TEST_URL.database}_test")

os.environ["DATABASE_URL"] = TEST_URL.render_as_string(hide_password=False)

# Кэш по умолчанию ВЫКЛЮЧЕН во всех тестах (пустое значение перебивает REDIS_URL из .env): иначе тесты
# читали бы и портили рабочий кэш и влияли друг на друга. Кэш включают только тесты с фикстурой redis_cache.
os.environ["REDIS_URL"] = ""
REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "redis://127.0.0.1:6379/15")

# Импорты приложения только после подмены DATABASE_URL (поэтому E402).
import redis  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402, F401  (регистрирует таблицы в Base)
from app.cache import cache  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

# Тесты, использующие любую из этих фикстур (напрямую или через другие), работают с базой.
DB_FIXTURES = {"engine", "migration_url"}
REDIS_FIXTURES = {"redis_cache", "redis_client"}


def pytest_collection_modifyitems(items):
    """Автоматически помечает маркером `db` все тесты, которым нужна база (через фикстуры).

    Тесты без базы можно запускать отдельно и без Docker: pytest -m "not db"
    Маркеры по папкам: tests/ui -> `ui`, tests/smoke -> `smoke`, tests/contract -> `contract`
    (по умолчанию они не запускаются: pytest -m ui, pytest tests/smoke -m smoke, pytest tests/contract -m contract).
    """
    for item in items:
        if DB_FIXTURES & set(item.fixturenames):
            item.add_marker(pytest.mark.db)
        if REDIS_FIXTURES & set(item.fixturenames):
            item.add_marker(pytest.mark.redis)
        parts = Path(str(item.fspath)).parts
        if "ui" in parts:
            item.add_marker(pytest.mark.ui)
        if "smoke" in parts:
            item.add_marker(pytest.mark.smoke)
        if "contract" in parts:
            item.add_marker(pytest.mark.contract)


@pytest.fixture(scope="session")
def engine():
    """Один раз за весь запуск: готовая тестовая база со схемой из миграций."""
    ensure_database(TEST_URL)
    # Чистый лист: сносим всё и применяем миграции с нуля. Так каждый запуск тестов
    # заодно проверяет, что цепочка миграций применяется на пустой базе.
    reset_schema(TEST_URL)
    command.upgrade(alembic_config(TEST_URL), "head")

    test_engine = create_engine(TEST_URL)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db(engine):
    """Чистая база и сессия на каждый тест.

    Перед тестом все таблицы очищаются, а счётчики id сбрасываются (RESTART IDENTITY),
    поэтому первая созданная в тесте запись всегда получает id=1.
    """
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    with Session(engine, autoflush=False) as session:
        yield session


@pytest.fixture
def client(db):
    """HTTP-клиент, подключённый к приложению, которое работает на тестовой базе `db`."""

    def override_get_db():
        yield db

    # Подмена зависимости: везде, где эндпоинт просит Depends(get_db),
    # FastAPI теперь подставит нашу тестовую сессию.
    app.dependency_overrides[get_db] = override_get_db

    yield TestClient(app)

    app.dependency_overrides.clear()


@pytest.fixture
def redis_client():
    """Подключение к ТЕСТОВОМУ Redis (база №15). Перед тестом и после него база очищается.

    Защита как у тестовой базы Postgres: рабочий кэш (база №0) трогать нельзя, поэтому номер базы 0 не принимается.
    """
    client = redis.Redis.from_url(REDIS_TEST_URL, decode_responses=True, socket_connect_timeout=2)
    if client.connection_pool.connection_kwargs.get("db", 0) == 0:
        pytest.exit(
            f"REDIS_TEST_URL={REDIS_TEST_URL} points at Redis database 0, which is the working cache. "
            "Use another database number, for example /15",
            returncode=2,
        )
    try:
        client.ping()
    except redis.RedisError:
        pytest.fail("Redis is not reachable for tests. Start it: docker compose up -d redis")
    client.flushdb()
    yield client
    client.flushdb()
    client.close()


@pytest.fixture
def redis_cache(redis_client, monkeypatch):
    """Включает кэш приложения на тестовом Redis. Возвращает тот же объект cache, что используют роутеры."""
    monkeypatch.setattr(cache, "client", redis_client)
    return cache
