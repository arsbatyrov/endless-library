"""Описание ошибок в OpenAPI: контракт должен перечислять все коды ответа, которые API реально возвращает.

Без этого документация обещает только 200/201/204 и 422, а клиенты получают ещё 404 и 409.
Проверяет это контрактный тест Schemathesis (tests/contract).
"""

from app.schemas import ErrorResponse, StatusResponse

BAD_REQUEST = {
    400: {"model": ErrorResponse, "description": "Тело запроса не является корректным JSON"}
}
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Объект не найден"}}
CONFLICT = {
    409: {"model": ErrorResponse, "description": "Нарушено бизнес-правило или уникальность"}
}
NOT_READY = {503: {"model": StatusResponse, "description": "База данных недоступна"}}
