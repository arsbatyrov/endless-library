from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (импорт нужен, чтобы модели зарегистрировались в Base)
from app.database import Base, engine
from app.routers import books, loans, readers
from app.services.errors import BusinessRuleError, NotFoundError


@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте создаём таблицы, если их ещё нет. Позже заменим на миграции.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Library API", lifespan=lifespan)
app.include_router(books.router)
app.include_router(readers.router)
app.include_router(loans.router)


# Сервисы не знают про HTTP: их исключения превращаем в ответы здесь.
@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(BusinessRuleError)
async def business_rule_handler(request: Request, exc: BusinessRuleError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/health")
def health():
    return {"status": "ok"}
