import os

import pytest
from sqlalchemy.engine import make_url

from tests.db_utils import ensure_database, reset_schema


@pytest.fixture
def migration_url():
    """Пустая база, отдельная от основной тестовой: тесты миграций ломают и пересоздают схему.

    К этому моменту DATABASE_URL уже указывает на <имя>_test (см. tests/conftest.py),
    отсюда получаем <имя>_migrations_test.
    """
    url = make_url(os.environ["DATABASE_URL"])
    base_name = url.database.removesuffix("_test")
    url = url.set(database=f"{base_name}_migrations_test")

    ensure_database(url)
    reset_schema(url)
    return url
