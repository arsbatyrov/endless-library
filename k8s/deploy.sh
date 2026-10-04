#!/usr/bin/env bash
# Разворачивает приложение в локальном кластере kind (контекст kind-library).
# Запуск из любой папки репозитория: bash k8s/deploy.sh   (на Windows: в Git Bash)
# Повторный запуск безопасен: пересобирает образы, обновляет ресурсы и перезапускает поды.
#
# Переменные: SKIP_BUILD=1 пропустить сборку образов (если они уже собраны).
set -euo pipefail

cd "$(dirname "$0")/.."
CLUSTER=library
CONTEXT="kind-${CLUSTER}"
# Всегда указываем контекст явно: так скрипт не заденет другой кластер, даже если он выбран «по умолчанию».
k() { kubectl --context "$CONTEXT" "$@"; }

echo "== 1/6 Образы: сборка и загрузка в кластер"
if [ -z "${SKIP_BUILD:-}" ]; then
  docker build -t library-api:local .
  docker build -t library-web:local frontend
fi
# kind-узел не видит образы Docker на вашем компьютере: их нужно загрузить в него.
kind load docker-image library-api:local library-web:local --name "$CLUSTER"

echo "== 2/6 Namespace и Secret"
k apply -f k8s/base/namespace.yaml
# Secret создаётся только если его ещё нет: пароль записан и в Postgres на томе, новый пароль сломал бы вход.
# Значение генерируется случайно и нигде не хранится, кроме кластера.
if ! k -n library get secret library-db >/dev/null 2>&1; then
  password="$(openssl rand -hex 16)"
  k -n library create secret generic library-db \
    --from-literal=POSTGRES_PASSWORD="$password" \
    --from-literal=DATABASE_URL="postgresql+psycopg://library:${password}@db:5432/library"
fi

echo "== 3/6 База, API и web"
k apply -k k8s/base
k -n library rollout status statefulset/db --timeout=180s
k -n library rollout status deployment/redis --timeout=180s

echo "== 4/6 Миграции (Job)"
job="$(k create -f k8s/migrate-job.yaml -o name)"
if ! k -n library wait --for=condition=complete "$job" --timeout=180s; then
  k -n library logs "$job" || true
  exit 1
fi
k -n library logs "$job" | tail -3

echo "== 5/6 Перезапуск API и web на свежих образах"
k -n library rollout restart deployment/api deployment/web
k -n library rollout status deployment/api --timeout=180s
k -n library rollout status deployment/web --timeout=180s

echo "== 6/6 Ingress (вход в кластер)"
k apply -f k8s/ingress/traefik.yaml
k -n traefik rollout status deployment/traefik --timeout=180s
k apply -f k8s/ingress/ingress.yaml

echo
echo "Готово. Интерфейс: http://127.0.0.1:8090   API: http://127.0.0.1:8090/api/health"
