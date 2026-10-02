from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  (импорт нужен, чтобы модели зарегистрировались в Base)
from app.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте создаём таблицы, если их ещё нет. Позже заменим на миграции.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Library API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}
