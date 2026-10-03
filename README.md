# Library API

Учебный проект: REST API библиотеки (FastAPI + SQLAlchemy + PostgreSQL), на котором отрабатываем тестирование.

## Первый запуск

```powershell
# 1. Окружение и зависимости (для разработки: requirements-dev.txt, включает ruff)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

# 2. Настройки (затем поменяйте пароль в .env)
copy .env.example .env

# 3. База данных в Docker и структура таблиц
docker compose up -d db
alembic upgrade head

# 4. Сервер
uvicorn app.main:app --reload
```

Документация API (Swagger): http://127.0.0.1:8000/docs

## Фронтенд

React + Vite + TypeScript в папке `frontend/`. Запросы к API идут на `/api/...`,
dev-сервер Vite пересылает их в FastAPI (порт 8000), поэтому CORS не нужен.

```powershell
cd frontend
npm install
npm run dev          # http://localhost:5173 (API должен работать на :8000)
npm run build        # проверка типов и сборка
```

## Запуск в контейнерах

Приложение целиком (API, фронтенд, миграции) собирается в образы и запускается через профиль `full`:

```powershell
docker compose --profile full up -d --build   # http://127.0.0.1:8080
docker compose --profile full rm -sf api web migrate   # остановить и убрать только приложение (база остаётся)
```

- **`migrate`**: разовая задача, накатывает миграции и завершается; `api` стартует после неё.
- **`api`**: образ из `Dockerfile` (многоэтапная сборка, процесс не от root, проверка здоровья `/health`),
  наружу не опубликован.
- **`web`**: образ из `frontend/Dockerfile`: nginx отдаёт собранный интерфейс и проксирует `/api/...` в `api`
  (адрес задаётся переменной `API_UPSTREAM`).
- Обычная команда `docker compose up -d db` по-прежнему поднимает только базу.
- Рабочие зависимости образа: `requirements.txt` (прямые зависимости закреплены); тестовые и инструменты: `requirements-dev.txt`.

### Готовые образы

При каждом слиянии в `main` workflow `publish.yml` публикует образы в реестр GitHub:

| Образ | Теги |
|---|---|
| `ghcr.io/arsbatyrov/library-api` | `latest`, `sha-<коммит>` (и `X.Y.Z` для тегов `vX.Y.Z`) |
| `ghcr.io/arsbatyrov/library-web` | то же |

```powershell
docker pull ghcr.io/arsbatyrov/library-api:latest
```

Образы собираются из тех же `Dockerfile`, которые проверяются в CI. Для развёртывания лучше брать тег
`sha-<коммит>` (точная версия), а не `latest`.

## Тесты

Нужна запущенная база (`docker compose up -d db`). Тесты используют отдельную базу
`<имя>_test`, сами создают её и накатывают миграции; рабочая база не затрагивается.

```powershell
pytest                    # все тесты + покрытие (UI-тесты по умолчанию выключены)
pytest -m "not db"        # только тесты без базы (быстро, без Docker)
pytest tests/concurrency  # только тесты гонок
pytest -m ui --no-cov     # UI-тесты в браузере (см. ниже)
```

Устройство тестов:

| Папка | Что проверяет |
|---|---|
| `tests/unit` | логика сервисов и штраф |
| `tests/api` | HTTP-эндпоинты: коды ответов, формат, ошибки |
| `tests/db` | ограничения самой базы (уникальность, внешние ключи, NOT NULL) в обход приложения |
| `tests/migrations` | цепочка миграций: накат с нуля, откат, совпадение с моделями |
| `tests/concurrency` | гонки: одновременные запросы к одним данным |
| `tests/ui` | интерфейс в настоящем браузере (Playwright): сценарии, ошибки, сбои сети |

### UI-тесты

Нужны: запущенная база, Node.js и `npm ci` в папке `frontend`, браузер Chromium
(`python -m playwright install chromium`). Тесты сами поднимают API (порт 8100) и фронтенд
(порт 5180) на отдельной базе `<имя>_e2e_test` и останавливают их в конце (порты можно сменить
переменными `UI_API_PORT` и `UI_WEB_PORT`). Данные готовятся через API, проверки идут через интерфейс.

Структура: `tests/ui/pages` (Page Object: локаторы и действия), `tests/ui/test_*.py` (сценарии),
`tests/ui/network.py` (управление сетью), `tests/ui/api_client.py` (подготовка данных).

Что умеют сценарии: граничные значения (длина названия 200/201, срок возврата), сквозной путь
через интерфейс, подмена ответов API (`500`, обрыв связи, подвешенный запрос, чужой текст ошибки),
подмена часов браузера (просрочка), пример нестабильного ожидания (`test_waiting.py`).

**Если UI-тест упал**, в `test-results/artifacts/<тест>/` остаются скриншот, видео и трассировка.
Трассировку открывают командой (покажет по шагам действия, сеть, снимки страницы и DOM):

```powershell
python -m playwright show-trace test-results/artifacts/<папка-теста>/trace.zip
```

Логи серверов UI-тестов: `test-results/ui-servers/`.

## Проверка кода

Те же проверки запускаются в CI (GitHub Actions); перед коммитом их можно выполнить локально:

```powershell
ruff check .            # поиск замечаний (ruff check --fix . исправит безопасные)
ruff format .           # форматирование
```

## Лицензия

[MIT](LICENSE)

## Миграции

```powershell
alembic revision --autogenerate -m "описание"   # создать миграцию по изменениям моделей
alembic upgrade head                            # применить
alembic downgrade -1                            # откатить последнюю
alembic check                                   # есть ли расхождения моделей и миграций
```
