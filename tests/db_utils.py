"""Общие помощники для тестов, которым нужна работа с PostgreSQL и миграциями."""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

ROOT = Path(__file__).resolve().parent.parent


def _require_test_database(url: URL) -> None:
    """Защита: разрушительные операции допустимы только на базах, имя которых кончается на _test."""
    if not url.database or not url.database.endswith("_test"):
        raise RuntimeError(f"Refusing to touch database {url.database!r}: name must end with '_test'")


def ensure_database(url: URL) -> None:
    """Создаёт базу, если её ещё нет. Если сервер недоступен, останавливает запуск тестов."""
    _require_test_database(url)
    # connect_timeout: если база недоступна (например, Docker остановлен), тесты должны
    # быстро остановиться с понятным сообщением, а не висеть на сетевом таймауте.
    admin_engine = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    try:
        with admin_engine.connect() as conn:
            exists = conn.scalar(
                text("select 1 from pg_database where datname = :name"),
                {"name": url.database},
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    except OperationalError as exc:
        pytest.exit(
            "Cannot connect to PostgreSQL. Is the database running? "
            f"Start it with: docker compose up -d db\n\n{exc}",
            returncode=3,
        )
    finally:
        admin_engine.dispose()


def reset_schema(url: URL) -> None:
    """Полностью очищает базу: удаляет все таблицы (и alembic_version)."""
    _require_test_database(url)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def alembic_config(url: URL) -> Config:
    """Настройки Alembic, направленные на указанную базу (а не на DATABASE_URL из окружения)."""
    config = Config(str(ROOT / "alembic.ini"))
    # В .ini-файлах символ % означает подстановку, поэтому его нужно удваивать.
    url_text = url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", url_text)
    return config
