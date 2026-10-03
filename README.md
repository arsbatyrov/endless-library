# Library API

Учебный проект: REST API библиотеки (FastAPI + SQLAlchemy + PostgreSQL), на котором отрабатываем тестирование.

## Первый запуск

```powershell
# 1. Окружение и зависимости
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Настройки (затем поменяйте пароль в .env)
copy .env.example .env

# 3. База данных в Docker и структура таблиц
docker compose up -d db
alembic upgrade head

# 4. Сервер
uvicorn app.main:app --reload
```

Документация API (Swagger): http://127.0.0.1:8000/docs

## Тесты

Нужна запущенная база (`docker compose up -d db`). Тесты используют отдельную базу
`<имя>_test`, сами создают её и накатывают миграции; рабочая база не затрагивается.

```powershell
pytest                    # все тесты + покрытие
pytest -m "not db"        # только тесты без базы (быстро, без Docker)
pytest tests/concurrency  # только тесты гонок
```

Устройство тестов:

| Папка | Что проверяет |
|---|---|
| `tests/unit` | логика сервисов и штраф |
| `tests/api` | HTTP-эндпоинты: коды ответов, формат, ошибки |
| `tests/db` | ограничения самой базы (уникальность, внешние ключи, NOT NULL) в обход приложения |
| `tests/migrations` | цепочка миграций: накат с нуля, откат, совпадение с моделями |
| `tests/concurrency` | гонки: одновременные запросы к одним данным |

## Миграции

```powershell
alembic revision --autogenerate -m "описание"   # создать миграцию по изменениям моделей
alembic upgrade head                            # применить
alembic downgrade -1                            # откатить последнюю
alembic check                                   # есть ли расхождения моделей и миграций
```
