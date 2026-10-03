import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Строка подключения. Берётся из переменной окружения DATABASE_URL,
# а если её нет, используется локальный файл SQLite. На этапе 2 здесь будет PostgreSQL.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///library.db")

# check_same_thread нужен только для SQLite: FastAPI может обрабатывать запрос в другом потоке.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

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
