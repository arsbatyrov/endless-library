# Endless Library

[![CI](https://github.com/arsbatyrov/endless-library/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/arsbatyrov/endless-library/actions/workflows/ci.yml)
[![Security](https://github.com/arsbatyrov/endless-library/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/arsbatyrov/endless-library/actions/workflows/security.yml)
[![Publish images](https://github.com/arsbatyrov/endless-library/actions/workflows/publish.yml/badge.svg?branch=main)](https://github.com/arsbatyrov/endless-library/actions/workflows/publish.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Учебный проект Endless Library: библиотека с REST API (FastAPI + SQLAlchemy + PostgreSQL), сайтом (React) и
инфраструктурой (Docker, Kubernetes), на котором отрабатываем тестирование на всех уровнях.

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

### Язык интерфейса (ru / en)

Переключатель RU | EN в шапке меняет язык всех текстов интерфейса: заголовки, подписи, кнопки, сообщения,
формат дат (04.10.2026 или 04/10/2026). Выбор запоминается в браузере (localStorage); пока выбора нет,
берётся язык браузера (русский или английский, иначе английский). Тексты лежат в `frontend/src/i18n.ts`
(словари `ru` и `en`; пропущенный перевод не даст собрать проект). Сообщения, которые приходят с сервера
(поле `detail` в ответах об ошибках), показываются как есть и на язык интерфейса не переводятся.

## Запуск в контейнерах

Приложение целиком (API, фронтенд, миграции) собирается в образы и запускается через профиль `full`:

```powershell
docker compose --profile full up -d --build   # http://127.0.0.1:8081
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
| `ghcr.io/arsbatyrov/endless-library-api` | `latest`, `sha-<коммит>` (и `X.Y.Z` для тегов `vX.Y.Z`) |
| `ghcr.io/arsbatyrov/endless-library-web` | то же |

```powershell
docker pull ghcr.io/arsbatyrov/endless-library-api:latest
```

Образы собираются из тех же `Dockerfile`, которые проверяются в CI. Для развёртывания лучше брать тег
`sha-<коммит>` (точная версия), а не `latest`.

## Kubernetes (локальный кластер)

Приложение можно развернуть в локальном кластере [kind](https://kind.sigs.k8s.io/) (Kubernetes внутри Docker).
Нужны Docker, `kind`, `kubectl`; скрипт запускается в Git Bash (на Windows) или в обычной оболочке Linux/macOS.

```bash
kind create cluster --config k8s/kind-config.yaml   # один раз: кластер endless-library
bash k8s/deploy.sh                                   # сборка образов, загрузка в кластер, развёртывание
# Интерфейс: http://127.0.0.1:8080   API: http://127.0.0.1:8080/api/health
pytest tests/smoke -m smoke --no-cov                 # дымовые тесты и проверки устойчивости
kind delete cluster --name endless-library                   # убрать всё
```

| Файл | Что это |
|---|---|
| `k8s/kind-config.yaml` | Кластер: образ узла v1.34.0, вход на порт 8080 вашего компьютера |
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

## Наблюдаемость: метрики, логи, Grafana

- **Метрики** (`GET /metrics` у каждого пода API, формат Prometheus; наружу nginx его не отдаёт): запросы по методу,
  шаблону маршрута и коду ответа, время ответа (гистограмма), попадания и промахи кэша, число выдач, возвратов и
  сумма штрафов. Служебные адреса `/health`, `/ready`, `/metrics` не считаются.
- **Логи**: каждая запись одна строка JSON в stdout; на каждый запрос одна запись с `request_id`, `method`, `route`,
  `status`, `duration_ms`. Заголовок `X-Request-ID` принимается от клиента (только безопасные символы) или создаётся
  и возвращается в ответе: по нему находят все записи одного запроса.
- **Prometheus и Grafana** разворачиваются в кластере (`k8s/monitoring`, namespace `monitoring`) скриптом `k8s/deploy.sh`:

```bash
# Grafana: http://grafana.localhost:8080 (дашборд «Endless Library», port-forward не нужен)
kubectl --context kind-endless-library -n monitoring port-forward svc/prometheus 9090:9090   # http://127.0.0.1:9090
kubectl --context kind-endless-library -n endless-library logs deploy/api --tail=20                  # JSON-логи
```

Grafana открывается без входа (только просмотр); для правок: пользователь `admin`, пароль в Secret `grafana-admin`.
История метрик хранится в памяти пода (при его пересоздании пропадает): это учебный стенд.

## Контрактные тесты (OpenAPI)

Контракт API это его OpenAPI-схема (`/openapi.json`, `/docs`): по ней работают фронтенд и любые другие клиенты.
Две проверки в `tests/contract` (маркер `contract`, по умолчанию не запускаются, в CI это задание
«Contract tests (Schemathesis)»):

```powershell
pytest tests/contract -m contract --no-cov                       # обычный прогон, ~12 с, результат всегда одинаков
SCHEMATHESIS_EXPLORE=600 pytest tests/contract/test_schemathesis.py -m contract --no-cov   # случайный перебор
UPDATE_OPENAPI_SNAPSHOT=1 pytest tests/contract/test_openapi_snapshot.py -m contract --no-cov   # после осознанного изменения API
```

- **Schemathesis** читает схему и сам придумывает сотни запросов на каждую операцию (граничные числа, пустые и
  огромные строки, неверные типы, битый JSON) и проверяет ответы: код описан в контракте, тело подходит под
  модель, нет 500, плохие запросы отклоняются, хорошие принимаются. Он уже нашёл и помог исправить: `false` как
  число, id больше int32 (500), символ NUL в тексте (500), неописанные коды 400/404/409/503, потерянные границы
  полей в схеме. Каждая находка закреплена обычным тестом в `tests/api/test_contract_regressions_api.py`.
- **Снимок схемы** (`tests/contract/openapi.json`): любое изменение контракта делает тест красным и показывает,
  какие операции добавлены или удалены. Обновление снимка видно в diff pull request.

## Тесты

Всего 345 тестов. Нужны запущенные база и Redis (`docker compose up -d db redis`). Тесты используют отдельную базу
`<имя>_test` и базу Redis №15, сами создают и очищают их; рабочие данные не затрагиваются.

```powershell
pytest                              # основной набор + покрытие (кроме ui, smoke, contract)
pytest -m "not db and not redis"    # только тесты без инфраструктуры (быстро, без Docker)
pytest tests/concurrency            # только тесты гонок
pytest -m ui --no-cov               # UI-тесты в браузере (см. ниже)
pytest tests/contract -m contract --no-cov   # контрактные тесты по OpenAPI
pytest tests/smoke -m smoke --no-cov         # тесты развёрнутого кластера (после k8s/deploy.sh)
```

### Что и где тестируется

| Папка | Тестов | Уровень | Что проверяет | Где запускается в CI |
|---|---|---|---|---|
| `tests/unit` | 50 | модульные | логика сервисов, штраф, формат логов | Tests |
| `tests/api` | 159 | API (в памяти) | коды ответов, формат, ошибки, кэш Redis, рейтинг, метрики, регрессии контракта | Tests |
| `tests/db` | 13 | база данных | ограничения самой базы (уникальность, внешние ключи), восстановление после обрыва соединений | Tests |
| `tests/migrations` | 6 | миграции | накат с нуля, откат, совпадение с моделями | Tests |
| `tests/concurrency` | 2 | гонки | одновременные запросы к одним данным | Tests |
| `tests/contract` | 18 | контракт | Schemathesis по OpenAPI и снимок схемы | Contract tests |
| `tests/ui` | 77 | интерфейс | сценарии в настоящем браузере (Playwright), ошибки, сбои сети | UI tests |
| `tests/smoke` | 20 | развёрнутая система | Ingress, данные до базы, устойчивость (обновление без потерь, перезапуск базы и Redis), Prometheus и Grafana | Kubernetes |

Остальные проверки CI: линтер и формат (Lint), типы и сборка фронтенда (Frontend), сборка образов и проверка
через nginx (Docker images), уязвимости зависимостей и образов (Security), анализ кода (CodeQL).
Покрытие кода основным набором около 97% (порог 95%).

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
