#!/usr/bin/env bash
# Разворачивает приложение в локальном кластере kind (контекст kind-endless-library).
# Запуск из любой папки репозитория: bash k8s/deploy.sh   (на Windows: в Git Bash)
# Повторный запуск безопасен: пересобирает образы, обновляет ресурсы и перезапускает поды.
#
# Переменные: SKIP_BUILD=1 пропустить сборку образов (если они уже собраны).
set -euo pipefail

cd "$(dirname "$0")/.."
CLUSTER=endless-library
CONTEXT="kind-${CLUSTER}"
# Всегда указываем контекст явно: так скрипт не заденет другой кластер, даже если он выбран «по умолчанию».
k() { kubectl --context "$CONTEXT" "$@"; }

echo "== 1/7 Образы: сборка и загрузка в кластер"
if [ -z "${SKIP_BUILD:-}" ]; then
  docker build -t endless-library-api:local .
  docker build -t endless-library-web:local frontend
fi
# kind-узел не видит образы Docker на вашем компьютере: их нужно загрузить в него.
kind load docker-image endless-library-api:local endless-library-web:local --name "$CLUSTER"

echo "== 2/7 Namespace и Secret"
k apply -f k8s/base/namespace.yaml
# Secret создаётся только если его ещё нет: пароль записан и в Postgres на томе, новый пароль сломал бы вход.
# Значение генерируется случайно и нигде не хранится, кроме кластера.
if ! k -n endless-library get secret endless-library-db >/dev/null 2>&1; then
  password="$(openssl rand -hex 16)"
  k -n endless-library create secret generic endless-library-db \
    --from-literal=POSTGRES_PASSWORD="$password" \
    --from-literal=DATABASE_URL="postgresql+psycopg://library:${password}@db:5432/library"
fi

echo "== 3/7 База, API и web"
k apply -k k8s/base
k -n endless-library rollout status statefulset/db --timeout=180s
k -n endless-library rollout status deployment/redis --timeout=180s

echo "== 4/7 Миграции (Job)"
job="$(k create -f k8s/migrate-job.yaml -o name)"
if ! k -n endless-library wait --for=condition=complete "$job" --timeout=180s; then
  k -n endless-library logs "$job" || true
  exit 1
fi
k -n endless-library logs "$job" | tail -3

echo "== 5/7 Перезапуск API и web на свежих образах"
k -n endless-library rollout restart deployment/api deployment/web
k -n endless-library rollout status deployment/api --timeout=180s
k -n endless-library rollout status deployment/web --timeout=180s

echo "== 6/7 Ingress (вход в кластер)"
k apply -f k8s/ingress/traefik.yaml
k -n traefik rollout status deployment/traefik --timeout=180s
k apply -f k8s/ingress/ingress.yaml

echo "== 7/7 Мониторинг (Prometheus и Grafana)"
k apply -f k8s/monitoring/namespace.yaml
# Пароль администратора Grafana: случайный, создаётся один раз и хранится только в кластере.
if ! k -n monitoring get secret grafana-admin >/dev/null 2>&1; then
  k -n monitoring create secret generic grafana-admin --from-literal=password="$(openssl rand -hex 12)"
fi
k apply -k k8s/monitoring
k -n monitoring rollout status deployment/prometheus --timeout=180s
k -n monitoring rollout status deployment/grafana --timeout=180s

# Правило Ingress подхватывается не мгновенно: до этого момента Traefik отвечает своим «404 page not found».
# Ждём, пока приложение реально ответит через вход, чтобы тесты после деплоя не попали в этот промежуток.
echo "Ожидание ответа через Ingress..."
for _ in $(seq 1 60); do
  if curl -fsS -o /dev/null http://127.0.0.1:8080/api/ready; then
    ready=1
    break
  fi
  sleep 2
done
if [ -z "${ready:-}" ]; then
  echo "Приложение не ответило через Ingress за 2 минуты" >&2
  exit 1
fi

echo
echo "Готово. Интерфейс: http://127.0.0.1:8080   API: http://127.0.0.1:8080/api/health"
echo "Grafana (дашборд Endless Library): http://grafana.localhost:8080"
echo "Prometheus: kubectl --context $CONTEXT -n monitoring port-forward svc/prometheus 9090:9090  ->  http://127.0.0.1:9090"
