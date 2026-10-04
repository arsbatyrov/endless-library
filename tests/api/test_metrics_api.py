"""Метрики Prometheus (/metrics), идентификатор запроса и строка access-лога.

Счётчики живут в памяти всего процесса и не сбрасываются между тестами, поэтому тесты сравнивают значения
ДО и ПОСЛЕ действия (прирост), а не абсолютные числа.
"""

import logging
import re

from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.database import get_db
from app.main import app
from app.services.loans import issue_book, return_book
from tests.api.helpers import create_book, create_reader, issue_loan
from tests.factories import make_book, make_reader


def sample(name: str, **labels: str) -> float:
    """Текущее значение метрики (0, если такого ряда ещё нет)."""
    return REGISTRY.get_sample_value(name, labels) or 0.0


def requests_total(method: str, path: str, status: str) -> float:
    return sample("endless_library_http_requests_total", method=method, path=path, status=status)


# ---------- эндпоинт ----------


def test_metrics_endpoint_serves_prometheus_text_format(client):
    client.get("/books")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# TYPE endless_library_http_requests_total counter" in response.text


def test_metrics_endpoint_is_not_part_of_the_public_contract(client):
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]


# ---------- HTTP-метрики ----------


def test_request_is_counted_by_route_template_not_by_real_address(client):
    before = requests_total("GET", "/books/{book_id}", "404")

    client.get("/books/777")
    client.get("/books/778")

    assert requests_total("GET", "/books/{book_id}", "404") == before + 2
    # настоящих адресов в метках быть не должно: иначе рядов данных бесконечно много
    assert "/books/777" not in client.get("/metrics").text


def test_validation_error_is_counted_with_its_status(client):
    before = requests_total("POST", "/books", "422")

    client.post("/books", json={"title": ""})

    assert requests_total("POST", "/books", "422") == before + 1


def test_unknown_address_is_counted_under_one_unmatched_label(client):
    before = requests_total("GET", "unmatched", "404")

    client.get("/no/such/page")
    client.get("/another/missing/page")

    assert requests_total("GET", "unmatched", "404") == before + 2


def test_request_duration_is_recorded(client):
    before = sample(
        "endless_library_http_request_duration_seconds_count", method="GET", path="/books"
    )

    client.get("/books")

    after = sample(
        "endless_library_http_request_duration_seconds_count", method="GET", path="/books"
    )
    assert after == before + 1


def test_service_endpoints_are_not_counted(client):
    health_before = requests_total("GET", "/health", "200")
    metrics_before = requests_total("GET", "/metrics", "200")

    client.get("/health")
    client.get("/ready")
    client.get("/metrics")

    assert requests_total("GET", "/health", "200") == health_before
    assert requests_total("GET", "/metrics", "200") == metrics_before


def test_unhandled_error_is_counted_as_500(db):
    """Падение внутри приложения (здесь: недоступна база) видно в метриках как 500."""

    def broken_session():
        raise RuntimeError("database is gone")
        yield  # noqa: B901  (делает функцию генератором, как настоящая зависимость)

    app.dependency_overrides[get_db] = broken_session
    try:
        before = requests_total("GET", "/books", "500")
        response = TestClient(app, raise_server_exceptions=False).get("/books")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert requests_total("GET", "/books", "500") == before + 1


# ---------- метрики кэша ----------


def test_cache_miss_then_hit_are_counted(client, redis_cache):
    miss_before = sample("endless_library_cache_requests_total", result="miss")
    hit_before = sample("endless_library_cache_requests_total", result="hit")

    client.get("/books")
    client.get("/books")

    assert sample("endless_library_cache_requests_total", result="miss") == miss_before + 1
    assert sample("endless_library_cache_requests_total", result="hit") == hit_before + 1


def test_redis_failure_is_counted_as_cache_error(client, redis_cache, monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError

    def broken(*args, **kwargs):
        raise RedisConnectionError("lost")

    monkeypatch.setattr(redis_cache.client, "get", broken)
    before = sample("endless_library_cache_requests_total", result="error")

    client.get("/books")

    assert sample("endless_library_cache_requests_total", result="error") == before + 1


# ---------- бизнес-метрики ----------


def test_issue_and_return_are_counted(client):
    book, reader = create_book(client), create_reader(client)
    issued_before = sample("endless_library_loans_issued_total")
    returned_before = sample("endless_library_loans_returned_total")

    loan = issue_loan(client, book["id"], reader["id"]).json()
    client.post(f"/loans/{loan['id']}/return")

    assert sample("endless_library_loans_issued_total") == issued_before + 1
    assert sample("endless_library_loans_returned_total") == returned_before + 1


def test_refused_issue_is_not_counted_as_issued(client):
    book, reader = create_book(client, copies_available=0), create_reader(client)
    before = sample("endless_library_loans_issued_total")

    assert issue_loan(client, book["id"], reader["id"]).status_code == 409

    assert sample("endless_library_loans_issued_total") == before


def test_fine_amount_is_added_to_the_fines_counter(db):
    from datetime import UTC, datetime, timedelta

    book, reader = make_book(db), make_reader(db)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    loan = issue_book(db, book.id, reader.id, now)
    before = sample("endless_library_fines_charged_total")

    _, fine = return_book(db, loan.id, loan.due_at + timedelta(days=3))

    assert fine == 30
    assert sample("endless_library_fines_charged_total") == before + 30


# ---------- идентификатор запроса ----------


def test_response_has_a_generated_request_id(client):
    response = client.get("/books")

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_each_request_gets_its_own_id(client):
    first = client.get("/books").headers["X-Request-ID"]
    second = client.get("/books").headers["X-Request-ID"]

    assert first != second


def test_safe_client_request_id_is_passed_through(client):
    response = client.get("/books", headers={"X-Request-ID": "trace-2026.10_abc"})

    assert response.headers["X-Request-ID"] == "trace-2026.10_abc"


def test_unsafe_client_request_id_is_replaced(client):
    """Значение из чужого заголовка попадает в логи: пробелы и спецсимволы там недопустимы (log injection)."""
    response = client.get("/books", headers={"X-Request-ID": "evil id; {json}"})

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_request_id_is_present_on_error_responses_too(client):
    response = client.get("/books/777", headers={"X-Request-ID": "find-me"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "find-me"


# ---------- access-лог ----------


def test_each_request_writes_one_access_log_record(client, caplog):
    with caplog.at_level(logging.INFO, logger="endless_library.access"):
        client.get("/books/777", headers={"X-Request-ID": "log-1"})

    records = [r for r in caplog.records if r.name == "endless_library.access"]
    assert len(records) == 1
    record = records[0]
    assert (record.request_id, record.method, record.path) == ("log-1", "GET", "/books/777")
    assert record.route == "/books/{book_id}"
    assert record.status == 404
    assert record.duration_ms >= 0


def test_service_endpoints_do_not_write_access_log_records(client, caplog):
    with caplog.at_level(logging.INFO, logger="endless_library.access"):
        client.get("/health")
        client.get("/metrics")

    assert [r for r in caplog.records if r.name == "endless_library.access"] == []
