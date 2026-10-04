"""Формат структурных логов и проверка идентификатора запроса (без базы и без HTTP)."""

import json
import logging

import pytest

from app.logging_config import JsonFormatter, new_request_id, request_id_var


def make_record(message="hello", level=logging.INFO, **extra) -> logging.LogRecord:
    logger = logging.getLogger("endless_library.test")
    return logger.makeRecord(
        "endless_library.test", level, __file__, 1, message, (), None, extra=extra
    )


def parse(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def test_record_is_one_line_of_valid_json_with_standard_fields():
    line = JsonFormatter().format(make_record("hello"))

    assert "\n" not in line
    payload = json.loads(line)
    assert payload["msg"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "endless_library.test"
    assert payload["ts"].endswith("+00:00")


def test_extra_fields_become_json_fields():
    payload = parse(make_record("request", status=404, duration_ms=1.5, route="/books/{book_id}"))

    assert payload["status"] == 404
    assert payload["duration_ms"] == 1.5
    assert payload["route"] == "/books/{book_id}"


def test_request_id_comes_from_the_current_context():
    token = request_id_var.set("abc-123")
    try:
        payload = parse(make_record())
    finally:
        request_id_var.reset(token)

    assert payload["request_id"] == "abc-123"


def test_request_id_defaults_to_dash_outside_a_request():
    assert parse(make_record())["request_id"] == "-"


def test_non_ascii_text_is_kept_readable():
    line = JsonFormatter().format(make_record("Книга «Война и мир» выдана"))

    assert "Война и мир" in line


def test_newline_in_a_message_cannot_break_the_one_record_per_line_rule():
    line = JsonFormatter().format(make_record("first\nsecond"))

    assert "\n" not in line
    assert json.loads(line)["msg"] == "first\nsecond"


def test_exception_is_included():
    logger = logging.getLogger("endless_library.test")
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logger.makeRecord(
            "endless_library.test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )

    assert "ValueError: boom" in parse(record)["exc"]


@pytest.mark.parametrize("value", ["abc", "trace-1.2_3", "A" * 64, "0123456789abcdef"])
def test_safe_request_ids_are_kept(value):
    assert new_request_id(value) == value


@pytest.mark.parametrize(
    "value",
    ["", None, "has space", "new\nline", "A" * 65, "semi;colon", '{"a":1}', "кириллица"],
)
def test_unsafe_or_missing_request_ids_are_replaced_with_a_generated_one(value):
    generated = new_request_id(value)

    assert generated != value
    assert len(generated) == 32
    assert generated.isalnum()
