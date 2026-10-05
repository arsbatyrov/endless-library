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

ORIGINAL_TABLES = {"books", "readers", "loans"}  # first migration (d7cd327419d1)
ACCOUNT_TABLES = {"users", "refresh_tokens"}  # AUTH-001 (5b0e3f9c1a42)
APP_TABLES = ORIGINAL_TABLES | ACCOUNT_TABLES
ORIGINAL_REVISION = "d7cd327419d1"


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


def describe_schema(engine, tables=None) -> dict:
    """Описание схемы в виде простых значений, которые можно сравнивать через ==.

    Объекты типов SQLAlchemy сравнивать нельзя (два одинаковых INTEGER() не равны),
    поэтому типы приводим к тексту.
    """
    inspector = inspect(engine)
    schema = {}
    for name in sorted(tables or APP_TABLES):
        schema[name] = {
            "columns": [
                (c["name"], str(c["type"]), c["nullable"], c["default"])
                for c in inspector.get_columns(name)
            ],
            "primary_key": inspector.get_pk_constraint(name)["constrained_columns"],
            "foreign_keys": sorted(
                (
                    tuple(fk["constrained_columns"]),
                    fk["referred_table"],
                    tuple(fk["referred_columns"]),
                )
                for fk in inspector.get_foreign_keys(name)
            ),
            "unique": sorted(
                tuple(u["column_names"]) for u in inspector.get_unique_constraints(name)
            ),
            "checks": sorted(
                (c["name"], c["sqltext"]) for c in inspector.get_check_constraints(name)
            ),
            "indexes": sorted(
                (
                    i["name"],
                    tuple(i["column_names"]),
                    tuple(i.get("expressions") or ()),
                    i["unique"],
                )
                for i in inspector.get_indexes(name)
            ),
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
    assert len(first["users"]["checks"]) == 2
    assert "users_username_lower_key" in [index[0] for index in first["users"]["indexes"]]

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


# ---------- AUTH-001: account tables ----------


def test_account_migration_creates_the_agreed_columns(config, migration_engine):
    """Criterion 1: after the migration the tables exist with exactly the agreed columns."""
    command.upgrade(config, "head")

    inspector = inspect(migration_engine)
    users = [c["name"] for c in inspector.get_columns("users")]
    tokens = [c["name"] for c in inspector.get_columns("refresh_tokens")]

    assert users == [
        "id",
        "username",
        "password_hash",
        "role",
        "reader_id",
        "is_active",
        "created_at",
        "last_login_at",
    ]
    assert tokens == ["id", "user_id", "token_hash", "expires_at", "revoked_at", "created_at"]


def test_account_migration_defines_the_database_rules(config, migration_engine):
    """The rules of criteria 2-4 live in the schema (checked in detail by tests/db/test_user_constraints.py)."""
    command.upgrade(config, "head")

    schema = describe_schema(migration_engine, ACCOUNT_TABLES)

    assert [name for name, _ in schema["users"]["checks"]] == [
        "users_reader_link_check",
        "users_role_check",
    ]
    assert schema["users"]["unique"] == [("reader_id",)]
    # the case-insensitive login rule is a unique index over lower(username)
    lower_index = [i for i in schema["users"]["indexes"] if i[0] == "users_username_lower_key"]
    assert len(lower_index) == 1
    _, columns, expressions, unique = lower_index[0]
    assert unique is True
    assert columns == (None,)  # an expression, not a plain column
    assert expressions == ("lower(username::text)",)
    assert schema["refresh_tokens"]["unique"] == [("token_hash",)]


def test_downgrading_the_account_migration_restores_the_previous_schema_exactly(
    config, migration_engine
):
    """Criterion 5: after the rollback the tables are gone and the schema equals the one before the migration."""
    command.upgrade(config, ORIGINAL_REVISION)
    before = describe_schema(migration_engine, ORIGINAL_TABLES)
    command.upgrade(config, "head")
    assert table_names(migration_engine) == APP_TABLES | {"alembic_version"}

    command.downgrade(config, ORIGINAL_REVISION)

    assert table_names(migration_engine) == ORIGINAL_TABLES | {"alembic_version"}
    assert describe_schema(migration_engine, ORIGINAL_TABLES) == before


def test_account_migration_does_not_change_the_existing_tables(config, migration_engine):
    command.upgrade(config, ORIGINAL_REVISION)
    before = describe_schema(migration_engine, ORIGINAL_TABLES)

    command.upgrade(config, "head")

    assert describe_schema(migration_engine, ORIGINAL_TABLES) == before


def test_check_constraints_in_models_match_the_migrated_database(config, migration_engine):
    """Alembic's autogenerate does not compare CHECK constraints, so test_models_and_migrations_are_in_sync
    cannot notice a rule that exists in the migration but was dropped from the model (or the other way round).
    This test compares them by name for every table."""
    from sqlalchemy import CheckConstraint

    command.upgrade(config, "head")
    inspector = inspect(migration_engine)

    for table in Base.metadata.sorted_tables:
        in_model = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
        in_database = {c["name"] for c in inspector.get_check_constraints(table.name)}
        assert in_model == in_database, (
            f"{table.name}: model {sorted(in_model)} vs database {sorted(in_database)}"
        )
