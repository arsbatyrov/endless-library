# Library API

[![CI](https://github.com/arsbatyrov/library-api/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/arsbatyrov/library-api/actions/workflows/ci.yml)
[![Security](https://github.com/arsbatyrov/library-api/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/arsbatyrov/library-api/actions/workflows/security.yml)
[![Publish images](https://github.com/arsbatyrov/library-api/actions/workflows/publish.yml/badge.svg?branch=main)](https://github.com/arsbatyrov/library-api/actions/workflows/publish.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

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

## Kubernetes (локальный кластер)

Приложение можно развернуть в локальном кластере [kind](https://kind.sigs.k8s.io/) (Kubernetes внутри Docker).
Нужны Docker, `kind`, `kubectl`; скрипт запускается в Git Bash (на Windows) или в обычной оболочке Linux/macOS.

```bash
kind create cluster --config k8s/kind-config.yaml   # один раз: кластер library
bash k8s/deploy.sh                                   # сборка образов, загрузка в кластер, развёртывание
# Интерфейс: http://127.0.0.1:8090   API: http://127.0.0.1:8090/api/health
pytest tests/smoke -m smoke --no-cov                 # дымовые тесты и проверки устойчивости
kind delete cluster --name library                   # убрать всё
```

| Файл | Что это |
|---|---|
| `k8s/kind-config.yaml` | Кластер: образ узла v1.34.0, вход на порт 8090 вашего компьютера |
| `k8s/base/` | Namespace, ConfigMap, база (StatefulSet с постоянным томом), API и web (Deployment, 2 реплики, пробы) |
| `k8s/migrate-job.yaml` | Job с миграциями (`alembic upgrade head`), новый при каждом деплое |
| `k8s/ingress/` | Входной контроллер Traefik и правило Ingress |
| `k8s/deploy.sh` | Развёртывание целиком; пароль базы генерируется и хранится только в Secret кластера |

Что проверяют `tests/smoke`: приложение открывается через Ingress, данные из браузера доходят до базы,
плавное обновление API не теряет запросы, данные переживают перезапуск базы, при недоступной базе API
выводится из балансировки (readiness), но не перезапускается (liveness). В CI это задание
«Kubernetes (kind cluster smoke tests)».

## Кэш и популярные книги (Redis)

Redis ускоряет чтение книг (`GET /books`, `GET /books/{id}`, TTL 60 с) и хранит счётчики выдач для
`GET /books/popular?limit=5`. Источник правды остаётся Postgres: без Redis приложение работает, только медленнее.

```powershell
docker compose up -d redis                     # Redis на 127.0.0.1:6379
# в .env добавьте: REDIS_URL=redis://127.0.0.1:6379/0   (см. .env.example; без переменной кэш выключен)
```

- Заголовок ответа `X-Cache: HIT` или `MISS` показывает, взят ответ из кэша или из базы.
- Запись (создание, изменение, удаление книги, выдача, возврат) сбрасывает нужные записи кэша.
- Если Redis недоступен, запросы идут в Postgres (короткие таймауты 0,5 с), готовность API (`/ready`) от Redis не зависит.
- Тесты кэша (маркер `redis`) работают на отдельной базе Redis №15 и очищают её; рабочую (№0) не трогают.
  Адрес можно сменить переменной `REDIS_TEST_URL`. Без Redis: `pytest -m "not redis"`.

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

## Безопасность и сопровождение

- **Dependabot** (`.github/dependabot.yml`): раз в неделю открывает pull request с обновлениями зависимостей
  (Python, npm, GitHub Actions, базовые образы Docker); мелкие обновления собраны в один PR на экосистему.
- **Проверки безопасности** (`.github/workflows/security.yml`): `pip-audit`, `npm audit`, сканер образов Trivy.
  Запускаются на каждый PR, на `main` и раз в неделю; для слияния не обязательны (новая уязвимость в чужой
  библиотеке не должна блокировать несвязанные изменения), красный результат сигнал обновить зависимость.
- **CodeQL**: статический анализ кода на уязвимости (результаты на вкладке Security репозитория).
- **Secret scanning и push protection**: GitHub блокирует отправку распознанных ключей и токенов.
- Все GitHub Actions закреплены по хешу коммита (с комментарием о версии), хеши обновляет Dependabot.
- В образах при сборке обновляются пакеты ОС (`apt-get upgrade` / `apk upgrade`): так закрываются исправленные уязвимости базового образа.

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
