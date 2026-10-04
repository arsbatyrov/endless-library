"""Структурные логи: одна строка = один JSON-объект.

Зачем JSON: логи читают программы (Loki, Elasticsearch, jq), а не только человек. По полям можно искать:
все запросы с request_id=..., все ответы со status>=500, медленные запросы (duration_ms).

request_id связывает все записи одного запроса. Клиент может прислать свой заголовок X-Request-ID, тогда
по одному идентификатору находятся и запись клиента, и запись сервера.
"""

import contextvars
import json
import logging
import re
import sys
import uuid
from datetime import UTC, datetime

# Идентификатор текущего запроса. contextvar: у каждого запроса своё значение, даже при параллельной работе.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# Чужой заголовок попадает в логи, поэтому принимаем только безопасные символы: иначе в него можно
# подложить перевод строки и подделать запись в логе (log injection).
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Поля, которые добавляют сами записи (logger.info("...", extra={...})); они попадают в JSON как есть.
_STANDARD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def new_request_id(incoming: str | None) -> str:
    """Берёт идентификатор клиента, если он безопасен, иначе создаёт свой."""
    if incoming and _SAFE_REQUEST_ID.match(incoming):
        return incoming
    return uuid.uuid4().hex


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        payload.update(
            {key: value for key, value in record.__dict__.items() if key not in _STANDARD_ATTRS}
        )
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging() -> None:
    """Все логи приложения (логгеры library.*) идут в stdout JSON-строками: так их забирает Kubernetes."""
    logger = logging.getLogger("library")
    if any(getattr(h, "_library_json", False) for h in logger.handlers):
        return  # уже настроено (повторный импорт, тесты)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._library_json = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
