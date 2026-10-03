from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401  (импорт нужен, чтобы модели попали в Base.metadata)
from app.database import DATABASE_URL, Base
from app.models import UTCDateTime

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: иначе при запуске миграций из тестов
    # Alembic отключил бы логгеры pytest.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Модели, с которыми Alembic сравнивает базу при --autogenerate.
target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):
    """Как записывать наши типы в файл миграции.

    Наш UTCDateTime записываем как обычный sa.DateTime(timezone=True): иначе миграция
    импортировала бы код приложения, и старые миграции ломались бы при его изменении.
    """
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    """Режим «оффлайн»: не подключаемся к базе, а печатаем SQL-скрипт."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Обычный режим: подключаемся к базе по DATABASE_URL (тому же, что у приложения)."""
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_item=render_item,
            compare_type=True,  # замечать смену типа колонки
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
