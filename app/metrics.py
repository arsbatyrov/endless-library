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
    "endless_library_http_requests_total",
    "HTTP requests handled by the API",
    ["method", "path", "status"],
)
HTTP_DURATION = Histogram(
    "endless_library_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
CACHE_REQUESTS = Counter(
    "endless_library_cache_requests_total",
    "Redis cache lookups by result: hit, miss or error (Redis unavailable)",
    ["result"],
)
LOGIN_GUARD_FAILURES = Counter(
    "endless_library_login_guard_failures_total",
    "Times the brute-force protection of the login could not work (it fails open): redis_error or not_configured",
    ["reason"],
)
# AUTH-016: sign-ins and token refreshes. The only label is the RESULT (a handful of values): never a login, a user or
# an address, which would make the number of series unbounded and put personal data into Prometheus.
AUTH_LOGINS = Counter(
    "endless_library_auth_logins_total",
    "Login attempts by result: success, failure (wrong password, unknown or disabled login) or locked (too many failures)",
    ["result"],
)
AUTH_REFRESH = Counter(
    "endless_library_auth_refresh_total",
    "Refresh-token exchanges by result: ok or rejected (missing, unknown, expired, replaced, or the user is disabled)",
    ["result"],
)
# Every series exists from the start, at 0: a graph or a rate() over a series that has not occurred yet would be empty.
for _result in ("success", "failure", "locked"):
    AUTH_LOGINS.labels(_result)
for _result in ("ok", "rejected"):
    AUTH_REFRESH.labels(_result)

LOANS_ISSUED = Counter("endless_library_loans_issued_total", "Books issued to readers")
LOANS_RETURNED = Counter("endless_library_loans_returned_total", "Books returned by readers")
FINES_CHARGED = Counter(
    "endless_library_fines_charged_total", "Total amount of fines charged on returns"
)

# Служебные адреса не считаем: проверки Kubernetes и сам сбор метрик шли бы каждые несколько секунд
# и заглушили бы реальный трафик пользователей.
UNMEASURED_PATHS = frozenset({"/health", "/ready", "/metrics"})
