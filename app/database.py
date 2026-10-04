import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Читает файл .env. Переменные, уже заданные в окружении, имеют приоритет над файлом.
load_dotenv()

# Адрес базы обязателен: запасного варианта нет, чтобы приложение не запустилось
# молча не на той базе.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env "
        "(or set the environment variable) and start the database: docker compose up -d db"
    )

# pool_pre_ping: перед выдачей соединения из пула SQLAlchemy проверяет, что оно живо, а мёртвое
# заменяет новым. Без этого после перезапуска базы первый запрос на «протухшем» соединении падал бы с 500.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей-таблиц."""


def get_db():
    """Выдаёт эндпоинту сессию и закрывает её после ответа."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
