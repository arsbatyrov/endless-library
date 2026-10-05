# Endless Library

[![CI](https://github.com/arsbatyrov/endless-library/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/arsbatyrov/endless-library/actions/workflows/ci.yml)
[![Security](https://github.com/arsbatyrov/endless-library/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/arsbatyrov/endless-library/actions/workflows/security.yml)
[![Publish images](https://github.com/arsbatyrov/endless-library/actions/workflows/publish.yml/badge.svg?branch=main)](https://github.com/arsbatyrov/endless-library/actions/workflows/publish.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Endless Library is a learning project: a library with a REST API (FastAPI + SQLAlchemy + PostgreSQL), a website
(React) and infrastructure (Docker, Kubernetes), built to practise testing on every level.

## Getting started

```powershell
# 1. Environment and dependencies (development: requirements-dev.txt, includes ruff)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

# 2. Settings (then change the password in .env)
copy .env.example .env

# 3. Database in Docker and table structure
docker compose up -d db
alembic upgrade head

# 4. Server
uvicorn app.main:app --reload
```

API documentation (Swagger): http://127.0.0.1:8000/docs

## Frontend

React + Vite + TypeScript in `frontend/`. Requests go to `/api/...`; the Vite dev server forwards them to FastAPI
(port 8000), so CORS is not needed.

```powershell
cd frontend
npm install
npm run dev          # http://localhost:5173 (the API must be running on :8000)
npm run build        # type check and build
```

### Interface language (ru / en)

The RU | EN switch in the header changes the language of all interface texts: headings, labels, buttons, messages
and the date format (04.10.2026 or 04/10/2026). The choice is remembered in the browser (localStorage); until a
choice is made, the browser language is used (Russian or English, English otherwise). Texts live in
`frontend/src/i18n.ts` (`ru` and `en` dictionaries; a missing translation breaks the build). Messages that come
from the server (the `detail` field of error responses) are shown as they are and are not translated.

## Running in containers

The whole application (API, frontend, migrations) is built into images and started with the `full` profile:

```powershell
docker compose --profile full up -d --build   # http://127.0.0.1:8081
docker compose --profile full rm -sf api web migrate   # stop and remove only the application (the database stays)
```

- **`migrate`**: a one-off task that applies migrations and exits; `api` starts after it.
- **`api`**: image from `Dockerfile` (multi-stage build, non-root process, `/health` health check), not published
  outside Docker.
- **`web`**: image from `frontend/Dockerfile`: nginx serves the built interface and proxies `/api/...` to `api`
  (the address is set by the `API_UPSTREAM` variable).
- The usual `docker compose up -d db` still starts only the database.
- Runtime dependencies of the image: `requirements.txt` (direct dependencies are pinned); test and tooling
  dependencies: `requirements-dev.txt`.

### Published images

On every merge to `main`, the `publish.yml` workflow publishes images to the GitHub registry:

| Image | Tags |
|---|---|
| `ghcr.io/arsbatyrov/endless-library-api` | `latest`, `sha-<commit>` (and `X.Y.Z` for `vX.Y.Z` tags) |
| `ghcr.io/arsbatyrov/endless-library-web` | same |

```powershell
docker pull ghcr.io/arsbatyrov/endless-library-api:latest
```

Images are built from the same `Dockerfile`s that CI checks. For deployments, prefer the `sha-<commit>` tag (an exact
version) over `latest`.

## Kubernetes (local cluster)

The application can be deployed to a local [kind](https://kind.sigs.k8s.io/) cluster (Kubernetes inside Docker).
You need Docker, `kind` and `kubectl`; the script runs in Git Bash (on Windows) or in a regular Linux/macOS shell.

```bash
kind create cluster --config k8s/kind-config.yaml   # once: the endless-library cluster
bash k8s/deploy.sh                                   # build images, load them into the cluster, deploy
# Website: http://127.0.0.1:8080   API: http://127.0.0.1:8080/api/health
pytest tests/smoke -m smoke --no-cov                 # smoke and resilience tests
kind delete cluster --name endless-library           # remove everything
```

| File | What it is |
|---|---|
| `k8s/kind-config.yaml` | Cluster: node image v1.34.0, entry through port 8080 of your computer |
| `k8s/base/` | Namespace, ConfigMap, database (StatefulSet with a persistent volume), API and web (Deployments, 2 replicas, probes) |
| `k8s/migrate-job.yaml` | Migration Job (`alembic upgrade head`), a new one on every deploy |
| `k8s/ingress/` | Traefik ingress controller and the Ingress rule |
| `k8s/deploy.sh` | Full deployment; the database password is generated and stored only in a cluster Secret |

What `tests/smoke` checks: the application opens through the Ingress, data from the browser reaches the database,
a rolling update of the API loses no requests, data survives a database restart, and when the database is
unavailable the API is taken out of load balancing (readiness) but not restarted (liveness). In CI this is the
"Kubernetes (kind cluster smoke tests)" job.

## Cache and popular books (Redis)

Redis speeds up book reads (`GET /books`, `GET /books/{id}`, TTL 60 s) and stores loan counters for
`GET /books/popular?limit=5`. Postgres remains the source of truth: without Redis the application still works, just
slower.

```powershell
docker compose up -d redis                     # Redis on 127.0.0.1:6379
# add to .env: REDIS_URL=redis://127.0.0.1:6379/0   (see .env.example; without the variable the cache is off)
```

- The `X-Cache: HIT` or `MISS` response header shows whether the answer came from the cache or the database.
- Writes (creating, updating, deleting a book, issuing, returning) invalidate the affected cache entries.
- If Redis is unavailable, requests go to Postgres (short 0.5 s timeouts); API readiness (`/ready`) does not depend
  on Redis.
- Cache tests (the `redis` marker) use a separate Redis database, number 15, and clean it; the working one (number 0)
  is never touched. The address can be changed with `REDIS_TEST_URL`. Without Redis: `pytest -m "not redis"`.

## Observability: metrics, logs, Grafana

- **Metrics** (`GET /metrics` on every API pod, Prometheus format; nginx does not expose it outside): requests by
  method, route template and status code, response time (histogram), cache hits and misses, number of loans and
  returns, and the total amount of fines. The service paths `/health`, `/ready` and `/metrics` are not counted.
- **Logs**: every record is one JSON line on stdout; each request produces one record with `request_id`, `method`,
  `route`, `status` and `duration_ms`. The `X-Request-ID` header is accepted from the client (safe characters only)
  or generated, and returned in the response: it is the key for finding all records of one request.
- **Prometheus and Grafana** are deployed to the cluster (`k8s/monitoring`, namespace `monitoring`) by
  `k8s/deploy.sh`:

```bash
# Grafana: http://grafana.localhost:8080 (the "Endless Library" dashboard, no port-forward needed)
kubectl --context kind-endless-library -n monitoring port-forward svc/prometheus 9090:9090   # http://127.0.0.1:9090
kubectl --context kind-endless-library -n endless-library logs deploy/api --tail=20          # JSON logs
```

Grafana opens without a login (view only); to edit, use the user `admin` and the password from the `grafana-admin`
Secret. Metric history is kept in the pod's memory (it is lost when the pod is recreated): this is a learning setup.

## Contract tests (OpenAPI)

The API contract is its OpenAPI schema (`/openapi.json`, `/docs`): the frontend and any other client rely on it.
There are two checks in `tests/contract` (the `contract` marker, not run by default; in CI this is the
"Contract tests (Schemathesis)" job):

```powershell
pytest tests/contract -m contract --no-cov                       # regular run, ~12 s, always the same result
SCHEMATHESIS_EXPLORE=600 pytest tests/contract/test_schemathesis.py -m contract --no-cov   # random search
UPDATE_OPENAPI_SNAPSHOT=1 pytest tests/contract/test_openapi_snapshot.py -m contract --no-cov   # after an intentional API change
```

- **Schemathesis** reads the schema and invents hundreds of requests for every operation (boundary numbers, empty
  and huge strings, wrong types, broken JSON) and checks the responses: the status code is described in the
  contract, the body matches the model, there are no 500s, bad requests are rejected and good ones are accepted.
  It has already found and helped to fix: `false` accepted as a number, ids above int32 (500), a NUL character in
  text (500), undocumented 400/404/409/503 codes, and field limits lost in the schema. Each finding is pinned by a
  regular test in `tests/api/test_contract_regressions_api.py`.
- **Schema snapshot** (`tests/contract/openapi.json`): any change of the contract turns the test red and shows which
  operations were added or removed. A snapshot update is visible in the pull request diff.

## Tests

415 tests in total. A running database and Redis are required (`docker compose up -d db redis`). Tests use a
separate database `<name>_test` and Redis database number 15, create and clean them themselves; working data is not
touched.

```powershell
pytest                              # main suite + coverage (everything except ui, smoke, contract)
pytest -m "not db and not redis"    # only tests without infrastructure (fast, no Docker)
pytest tests/concurrency            # only race-condition tests
pytest -m ui --no-cov               # browser UI tests (see below)
pytest tests/contract -m contract --no-cov   # OpenAPI contract tests
pytest tests/smoke -m smoke --no-cov         # tests of the deployed cluster (after k8s/deploy.sh)
```

### What is tested where

| Folder | Tests | Level | What it checks | Where it runs in CI |
|---|---|---|---|---|
| `tests/unit` | 86 | unit | service logic, fines, log format, password hashing and policy | Tests |
| `tests/api` | 159 | API (in memory) | status codes, format, errors, Redis cache, ranking, metrics, contract regressions | Tests |
| `tests/db` | 42 | database | the database's own constraints (uniqueness, foreign keys, account rules), recovery after dropped connections | Tests |
| `tests/migrations` | 11 | migrations | apply from scratch, rollback, match with the models | Tests |
| `tests/concurrency` | 2 | race conditions | simultaneous requests to the same data | Tests |
| `tests/contract` | 18 | contract | Schemathesis against OpenAPI and the schema snapshot | Contract tests |
| `tests/ui` | 77 | interface | scenarios in a real browser (Playwright), errors, network failures | UI tests |
| `tests/smoke` | 20 | deployed system | Ingress, data all the way to the database, resilience (update without losses, database and Redis restart), Prometheus and Grafana | Kubernetes |

Other CI checks: linter and formatting (Lint), types and frontend build (Frontend), image build and a check through
nginx (Docker images), dependency and image vulnerabilities (Security), code analysis (CodeQL). Code coverage of the
main suite is about 97% (threshold 95%).

### UI tests

Requirements: a running database, Node.js and `npm ci` in `frontend`, and the Chromium browser
(`python -m playwright install chromium`). The tests start the API (port 8100) and the frontend (port 5180) on a
separate database `<name>_e2e_test` themselves and stop them at the end (ports can be changed with the
`UI_API_PORT` and `UI_WEB_PORT` variables). Data is prepared through the API; checks go through the interface.

Structure: `tests/ui/pages` (Page Objects: locators and actions), `tests/ui/test_*.py` (scenarios),
`tests/ui/network.py` (network control), `tests/ui/api_client.py` (data preparation).

What the scenarios cover: boundary values (title length 200/201, due date), an end-to-end journey through the
interface, API response substitution (`500`, dropped connection, a hanging request, a foreign error text), browser
clock substitution (overdue loans), and an example of an unstable wait (`test_waiting.py`).

**If a UI test fails**, a screenshot, a video and a trace remain in `test-results/artifacts/<test>/`. Open the trace
with this command (it shows actions, network, page snapshots and the DOM step by step):

```powershell
python -m playwright show-trace test-results/artifacts/<test-folder>/trace.zip
```

UI test server logs: `test-results/ui-servers/`.

## Security and maintenance

- **Dependabot** (`.github/dependabot.yml`): once a week opens a pull request with dependency updates (Python, npm,
  GitHub Actions, Docker base images); minor updates are grouped into one PR per ecosystem.
- **Security checks** (`.github/workflows/security.yml`): `pip-audit`, `npm audit`, the Trivy image scanner. They run
  on every PR, on `main` and weekly; they are not required for merging (a new vulnerability in a third-party
  library must not block unrelated changes), and a red result is a signal to update the dependency.
- **CodeQL**: static code analysis for vulnerabilities (results on the repository's Security tab).
- **Secret scanning and push protection**: GitHub blocks pushes that contain recognised keys and tokens.
- All GitHub Actions are pinned by commit hash (with a version comment); Dependabot updates the hashes.
- OS packages are upgraded during image builds (`apt-get upgrade` / `apk upgrade`), which closes already fixed
  vulnerabilities of the base image.

## Agent team kit (not active)

A prepared set of role definitions (analyst, architect, developer, QA, reviewer) and process documents for building the
project with separate agents lives in [docs/agent-team/](docs/agent-team/README.md). It is stored as plain documentation
and is **not active**; see [docs/agent-team/activation.md](docs/agent-team/activation.md) for how to switch it on.

## Code checks

The same checks run in CI (GitHub Actions); you can run them locally before committing:

```powershell
ruff check .            # find issues (ruff check --fix . fixes the safe ones)
ruff format .           # formatting
```

## License

[MIT](LICENSE)

## Migrations

```powershell
alembic revision --autogenerate -m "description"   # create a migration from model changes
alembic upgrade head                               # apply
alembic downgrade -1                               # roll back the last one
alembic check                                      # are there differences between the models and the migrations
```
