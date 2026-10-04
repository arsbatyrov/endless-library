from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.openapi_responses import NOT_READY
from app.routers import books, loans, readers
from app.schemas import StatusResponse
from app.services.errors import BusinessRuleError, NotFoundError

# Таблицы здесь не создаются: структурой базы управляют миграции (alembic upgrade head).
app = FastAPI(title="Library API")
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


# Две разные проверки для Kubernetes:
# /health ("liveness") отвечает на вопрос «процесс жив?»: не трогает базу, иначе из-за сбоя базы
#   Kubernetes перезапускал бы здоровые поды API.
# /ready ("readiness") отвечает на «можно ли слать сюда запросы?»: проверяет связь с базой.
#   Пока не готов, под выводится из балансировки, но не перезапускается.
@app.get("/health", response_model=StatusResponse)
def health():
    return {"status": "ok"}


@app.get("/ready", response_model=StatusResponse, responses={**NOT_READY})
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "database unavailable"})
    return {"status": "ready"}
