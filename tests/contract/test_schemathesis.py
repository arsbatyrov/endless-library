"""Контрактные тесты: Schemathesis читает OpenAPI-схему нашего API и САМ придумывает запросы.

Для каждой операции он генерирует сотни входов (граничные числа, пустые и огромные строки, неверные типы,
лишние поля, битый JSON) и проверяет, что ответ соответствует схеме: код описан в контракте, тело подходит
под описанную модель, нет ошибок 500, некорректные запросы отклоняются, а корректные принимаются.

Что он уже нашёл в этом проекте (всё исправлено, у каждого пункта есть обычный тест в
tests/api/test_contract_regressions_api.py):
- false принималось как число 0 в полях-числах;
- id больше 2147483647 давал 500 (ошибка SQL) вместо 422;
- коды 400, 404, 409, 503 не были описаны в контракте;
- границы полей терялись в OpenAPI (ge/le вместо minimum/maximum);
- регулярка email по-разному читалась в Python и по стандарту JSON Schema;
- PUT/DELETE /books/popular отвечали 422, а не 405.

По умолчанию набор запросов одинаков при каждом запуске (derandomize), поэтому тест не «мигает» в CI.
Режим исследования ищет новое случайным перебором и с большим числом примеров:
    SCHEMATHESIS_EXPLORE=500 pytest tests/contract/test_schemathesis.py -m contract --no-cov
(число это количество запросов на каждую операцию). Найденное исправьте и закрепите обычным тестом.
"""

import os

import pytest
import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis.specs.openapi.checks import allow_header_conformance
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.auth.tokens import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models import User

schema = schemathesis.openapi.from_asgi("/openapi.json", app)
AUTH: dict = {}  # filled by the fixture below: the administrator's access token


@schema.auth(refresh_interval=None, retry_on=[])
class AdminToken:
    """Adds the administrator's bearer token to every generated request (it becomes part of the case)."""

    def get(self, case, context):
        return AUTH.get(
            "token", "not-set-yet"
        )  # collection runs before the fixture creates the admin

    def set(self, case, data, context):
        case.headers = case.headers or {}
        case.headers["Authorization"] = f"Bearer {data}"


@pytest.fixture(scope="module", autouse=True)
def isolated_app(engine):
    """Приложение работает на тестовой базе; каждый запрос получает свою сессию (как в реальной работе).

    Данные между запросами накапливаются: так Schemathesis натыкается на уже существующие записи
    (например, повторный email даёт 409) и на реальные id.
    """
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    factory = sessionmaker(bind=engine, autoflush=False)

    def override():
        with factory() as session:
            yield session

    # The contract is checked WITH the protection on and as an administrator, so Schemathesis also verifies that a request
    # without a token is rejected (the OpenAPI schema declares the bearer scheme).
    with factory() as session:
        admin = User(username="contract-admin", password_hash="not-a-real-hash", role="admin")
        session.add(admin)
        session.commit()
        AUTH["token"] = create_access_token(admin.id, admin.role)

    previous = os.environ.get("AUTH_REQUIRED")
    os.environ["AUTH_REQUIRED"] = "true"
    app.dependency_overrides[get_db] = override
    yield
    app.dependency_overrides.clear()
    if previous is None:
        os.environ.pop("AUTH_REQUIRED", None)
    else:
        os.environ["AUTH_REQUIRED"] = previous


EXPLORE = int(os.getenv("SCHEMATHESIS_EXPLORE", "0"))


@schema.parametrize()
@settings(
    max_examples=EXPLORE or 100,
    derandomize=not EXPLORE,
    deadline=None,
    # Тесты работают на общей базе, а не на данных, которые строит сам Hypothesis: эти проверки здесь не нужны.
    suppress_health_check=list(HealthCheck),
)
def test_api_conforms_to_its_openapi_contract(case):
    # Одно осознанное исключение: у ответа 405 заголовок Allow перечисляет не все методы адреса.
    # Starlette регистрирует по одному маршруту на метод и в Allow попадает только первый подходящий.
    # Это ограничение фреймворка, на клиентов оно не влияет.
    case.call_and_validate(excluded_checks=[allow_header_conformance])
