"""Метрики Prometheus: числа, по которым видно, как работает приложение.

Prometheus раз в несколько секунд читает адрес /metrics и запоминает значения. По истории строятся графики
(Grafana) и ищутся проблемы: «ошибок стало больше», «ответы замедлились», «кэш перестал попадать».

Правила, которые важно знать:
- Counter (счётчик) только растёт; скорость считают по разнице (rate). Histogram считает, сколько запросов уложилось
  в каждое время ответа, по нему считают перцентили (p95).
- Метки (labels) должны иметь мало разных значений. Поэтому в метке path стоит ШАБЛОН маршрута (/books/{book_id}),
  а не настоящий адрес (/books/17): иначе на каждый id появлялся бы отдельный ряд данных, и Prometheus захлебнулся бы.
"""

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "library_http_requests_total",
    "HTTP requests handled by the API",
    ["method", "path", "status"],
)
HTTP_DURATION = Histogram(
    "library_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
CACHE_REQUESTS = Counter(
    "library_cache_requests_total",
    "Redis cache lookups by result: hit, miss or error (Redis unavailable)",
    ["result"],
)
LOANS_ISSUED = Counter("library_loans_issued_total", "Books issued to readers")
LOANS_RETURNED = Counter("library_loans_returned_total", "Books returned by readers")
FINES_CHARGED = Counter("library_fines_charged_total", "Total amount of fines charged on returns")

# Служебные адреса не считаем: проверки Kubernetes и сам сбор метрик шли бы каждые несколько секунд
# и заглушили бы реальный трафик пользователей.
UNMEASURED_PATHS = frozenset({"/health", "/ready", "/metrics"})
