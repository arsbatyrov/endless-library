# Образ API. Сборка: docker build -t library-api .

# ---- этап 1: зависимости в отдельном виртуальном окружении ----
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# Сначала только requirements.txt: пока он не менялся, Docker берёт этот слой из кэша.
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- этап 2: итоговый образ (без pip-кэша и лишнего) ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Подтягиваем исправления безопасности для пакетов ОС: базовый образ может отставать от репозитория Debian
# (сканер Trivy в CI находил так уязвимость в libpcre2). Кэш apt удаляем, чтобы образ не рос.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Работаем не от root: при взломе приложения у процесса меньше прав.
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app ./app
# Миграции лежат в образе: накатываются командой `alembic upgrade head` (отдельный шаг, не при старте API).
COPY migrations ./migrations
COPY alembic.ini .
USER app

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]

# Адрес базы задаётся переменной окружения DATABASE_URL при запуске контейнера.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
