"""Снимок OpenAPI-схемы: любое изменение контракта должно быть осознанным.

Схема сохранена в tests/contract/openapi.json. Если вы меняете API (новый эндпоинт, поле, код ответа),
этот тест упадёт и покажет, что именно изменилось. Это защита от случайной поломки клиентов:
фронтенда, мобильного приложения, чужих интеграций.

Обновить снимок после осознанного изменения:
    UPDATE_OPENAPI_SNAPSHOT=1 pytest tests/contract/test_openapi_snapshot.py --no-cov
и проверьте diff файла openapi.json в pull request: ревьюер увидит изменение контракта.
"""

import json
import os
from pathlib import Path

from app.main import app

SNAPSHOT = Path(__file__).with_name("openapi.json")


def _render(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _operations(schema: dict) -> set[str]:
    return {
        f"{method.upper()} {path}"
        for path, methods in schema["paths"].items()
        for method in methods
    }


def test_openapi_schema_matches_the_committed_snapshot():
    current = app.openapi()
    if os.getenv("UPDATE_OPENAPI_SNAPSHOT"):
        SNAPSHOT.write_text(_render(current), encoding="utf-8", newline="\n")
    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    if current != saved:
        removed = sorted(_operations(saved) - _operations(current))
        added = sorted(_operations(current) - _operations(saved))
        raise AssertionError(
            "Контракт API изменился.\n"
            f"  удалены операции: {removed or 'нет'}\n"
            f"  добавлены операции: {added or 'нет'}\n"
            "  (возможны и изменения внутри схем: поля, коды ответов)\n"
            "Если изменение осознанное, обновите снимок: UPDATE_OPENAPI_SNAPSHOT=1 pytest "
            "tests/contract/test_openapi_snapshot.py --no-cov"
        )


def test_every_operation_documents_its_error_responses():
    """Клиент должен узнать из контракта, какие ошибки ему ждать: 404 там, где ищут по id; 409 там, где есть правила."""
    paths = app.openapi()["paths"]

    for path in ("/books/{book_id}", "/readers/{reader_id}"):
        for method in ("get", "put", "delete"):
            if method in paths[path]:
                assert "404" in paths[path][method]["responses"], f"{method.upper()} {path}"
    assert "409" in paths["/loans"]["post"]["responses"]
    assert "409" in paths["/loans/{loan_id}/return"]["post"]["responses"]
    assert "503" in paths["/ready"]["get"]["responses"]
