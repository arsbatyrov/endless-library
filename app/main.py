import logging
import os
import time

from fastapi import Depends, FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.config import load_jwt_secret
from app.database import get_db
from app.logging_config import new_request_id, request_id_var, setup_logging
from app.metrics import HTTP_DURATION, HTTP_REQUESTS, UNMEASURED_PATHS
from app.openapi_responses import NOT_READY
from app.routers import auth, books, loans, readers
from app.schemas import StatusResponse
from app.services.errors import BusinessRuleError, NotFoundError

# Fail fast: without a strong JWT secret the application must not start (there is no fallback value).
load_jwt_secret()

setup_logging()
access_logger = logging.getLogger("endless_library.access")

# Таблицы здесь не создаются: структурой базы управляют миграции (alembic upgrade head).
# API_ROOT_PATH: под каким префиксом приложение видно СНАРУЖИ. За nginx это /api: он отрезает префикс и
# передаёт нам /docs, но страница документации должна просить схему по внешнему адресу /api/openapi.json,
# иначе её запрос попадёт не в API (а в страницу сайта) и Swagger покажет «Unable to render this definition».
# Напрямую (порт 8000, без nginx) переменная не задаётся: префикса нет.
app = FastAPI(title="Endless Library API", root_path=os.getenv("API_ROOT_PATH", ""))
app.include_router(auth.router)
app.include_router(books.router)
app.include_router(readers.router)
app.include_router(loans.router)


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    """Для каждого запроса: идентификатор (X-Request-ID), метрики Prometheus и одна строка JSON-лога."""
    request_id = new_request_id(request.headers.get("X-Request-ID"))
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    status_code = 500  # если обработчик упадёт с исключением, запрос всё равно будет учтён как 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        if request.url.path not in UNMEASURED_PATHS:
            duration = time.perf_counter() - started
            # Шаблон маршрута (/books/{book_id}), а не настоящий адрес: иначе у метрики было бы бесконечно много значений.
            route = request.scope.get("route")
            route_path = route.path if route is not None else "unmatched"
            HTTP_REQUESTS.labels(request.method, route_path, str(status_code)).inc()
            HTTP_DURATION.labels(request.method, route_path).observe(duration)
            access_logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "route": route_path,
                    "status": status_code,
                    "duration_ms": round(duration * 1000, 1),
                },
            )
        request_id_var.reset(token)


# By default a 422 error repeats the rejected input. For the sign-in form that would copy the password into the
# response (and into any log that records responses), so the input is left out for the /auth endpoints.
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    if "/auth/" in request.url.path:
        errors = [
            {key: value for key, value in error.items() if key != "input"} for error in errors
        ]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


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


# Метрики для Prometheus. Не входит в публичный контракт (include_in_schema=False) и наружу не отдаётся:
# nginx в образе web закрывает /api/metrics, а Prometheus читает этот адрес прямо у подов внутри кластера.
@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
