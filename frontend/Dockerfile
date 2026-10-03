# Образ фронтенда. Сборка (из папки frontend): docker build -t library-web .

# ---- этап 1: сборка статических файлов ----
FROM node:24-alpine AS build
WORKDIR /app
# Сначала только манифесты: пока зависимости не менялись, слой npm ci берётся из кэша.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- этап 2: nginx отдаёт сборку и проксирует /api в API ----
FROM nginx:alpine
# Подтягиваем исправления безопасности для пакетов ОС: базовый образ может отставать от репозитория Alpine
# (сканер Trivy в CI находил так уязвимости в libexpat и pcre2).
RUN apk upgrade --no-cache

# Файлы из templates обрабатываются при старте: ${API_UPSTREAM} подставляется из переменной окружения.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
ENV API_UPSTREAM=http://api:8000

EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
