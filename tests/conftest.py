import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

# ---------------------------------------------------------------------------
# Адрес ТЕСТОВОЙ базы. Это нужно сделать до импорта приложения: app.database
# читает DATABASE_URL при импорте, и в тестах он должен указывать на <имя>_test.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
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

# Защита: тесты стирают данные, поэтому работают только с базой, имя которой кончается на _test.
if not TEST_URL.database.endswith("_test"):
    pytest.exit("Refusing to run: test database name must end with '_test'", returncode=2)

os.environ["DATABASE_URL"] = TEST_URL.render_as_string(hide_password=False)

# Импорты приложения только после подмены DATABASE_URL (поэтому E402).
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402, F401  (регистрирует таблицы в Base)
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


def pytest_collection_modifyitems(items):
    """Автоматически помечает маркером `db` все тесты, которым нужна база (через фикстуры).

    Тесты без базы можно запускать отдельно и без Docker: pytest -m "not db"
    """
    for item in items:
        if "db" in item.fixturenames:
            item.add_marker(pytest.mark.db)


def _prepare_test_database() -> None:
    """Создаёт тестовую базу, если её нет, и накатывает на чистую схему все миграции."""
    # connect_timeout: если база недоступна (например, Docker остановлен), тесты должны
    # быстро остановиться с понятным сообщением, а не висеть на сетевом таймауте.
    admin_engine = create_engine(
        TEST_URL.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    try:
        with admin_engine.connect() as conn:
            exists = conn.scalar(
                text("select 1 from pg_database where datname = :name"),
                {"name": TEST_URL.database},
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{TEST_URL.database}"'))
    except OperationalError as exc:
        pytest.exit(
            "Cannot connect to PostgreSQL. Is the database running? "
            f"Start it with: docker compose up -d db\n\n{exc}",
            returncode=3,
        )
    finally:
        admin_engine.dispose()

    # Чистый лист: сносим всё и применяем миграции с нуля. Так каждый запуск тестов
    # заодно проверяет, что цепочка миграций применяется на пустой базе.
    engine = create_engine(TEST_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")


@pytest.fixture(scope="session")
def engine():
    """Один раз за весь запуск: готовая тестовая база со схемой из миграций."""
    _prepare_test_database()
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
