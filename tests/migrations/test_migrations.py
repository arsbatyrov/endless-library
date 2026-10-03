"""Тесты цепочки миграций на настоящем PostgreSQL.

Проверяем не содержимое отдельных миграций (это дублировало бы их код), а три риска:
миграции не применяются, их нельзя откатить, или они разошлись с моделями.
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.database import Base
from tests.db_utils import alembic_config

APP_TABLES = {"books", "readers", "loans"}


@pytest.fixture
def config(migration_url):
    return alembic_config(migration_url)


@pytest.fixture
def migration_engine(migration_url):
    engine = create_engine(migration_url)
    yield engine
    engine.dispose()


def table_names(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def describe_schema(engine) -> dict:
    """Описание схемы в виде простых значений, которые можно сравнивать через ==.

    Объекты типов SQLAlchemy сравнивать нельзя (два одинаковых INTEGER() не равны),
    поэтому типы приводим к тексту.
    """
    inspector = inspect(engine)
    schema = {}
    for name in sorted(APP_TABLES):
        schema[name] = {
            "columns": [
                (c["name"], str(c["type"]), c["nullable"], c["default"])
                for c in inspector.get_columns(name)
            ],
            "primary_key": inspector.get_pk_constraint(name)["constrained_columns"],
            "foreign_keys": sorted(
                (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]))
                for fk in inspector.get_foreign_keys(name)
            ),
            "unique": sorted(tuple(u["column_names"]) for u in inspector.get_unique_constraints(name)),
        }
    return schema


def test_there_is_exactly_one_migration_head(config):
    """Две «головы» значат, что два разработчика создали миграции параллельно, и их надо слить."""
    heads = ScriptDirectory.from_config(config).get_heads()

    assert len(heads) == 1


def test_upgrade_from_empty_database_creates_all_tables(config, migration_engine):
    assert table_names(migration_engine) == set()

    command.upgrade(config, "head")

    assert table_names(migration_engine) == APP_TABLES | {"alembic_version"}


def test_database_is_stamped_with_the_latest_revision(config, migration_engine):
    command.upgrade(config, "head")

    head = ScriptDirectory.from_config(config).get_current_head()
    with migration_engine.connect() as conn:
        stored = conn.scalar(text("select version_num from alembic_version"))
    assert stored == head


def test_downgrade_to_base_removes_all_application_tables(config, migration_engine):
    command.upgrade(config, "head")

    command.downgrade(config, "base")

    assert table_names(migration_engine) == {"alembic_version"}


def test_upgrade_downgrade_upgrade_roundtrip_gives_the_same_schema(config, migration_engine):
    command.upgrade(config, "head")
    first = describe_schema(migration_engine)
    # Страховка от пустого сравнения: описание схемы действительно содержит ограничения.
    assert first["readers"]["unique"] == [("email",)]
    assert len(first["loans"]["foreign_keys"]) == 2

    command.downgrade(config, "base")
    command.upgrade(config, "head")

    assert table_names(migration_engine) == APP_TABLES | {"alembic_version"}
    assert describe_schema(migration_engine) == first


def test_models_and_migrations_are_in_sync(config, migration_engine):
    """Ловит забытую миграцию: модель поменяли, а миграцию не создали."""
    command.upgrade(config, "head")

    with migration_engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        differences = compare_metadata(context, Base.metadata)

    assert differences == []
