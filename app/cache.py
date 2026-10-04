"""Кэш на Redis: ускоряет чтение книг и хранит счётчики популярности.

Принципы:
- Источник правды всегда Postgres. Redis только ускоряет: потеряли Redis, получили медленнее, но не неверно.
- Шаблон cache-aside: читаем из кэша, при промахе идём в базу и кладём результат в кэш.
  При любом изменении данных запись в кэше удаляется (инвалидация), а ещё у каждой записи есть TTL,
  поэтому даже забытая инвалидация не оставит устаревшие данные навсегда.
- Redis не обязателен: если REDIS_URL не задан или Redis недоступен, приложение работает без кэша.
  Таймауты короткие, чтобы упавший Redis не тормозил каждый запрос.
"""

import json
import logging
import os

import redis
from dotenv import load_dotenv
from redis.exceptions import RedisError

from app.metrics import CACHE_REQUESTS

load_dotenv()

logger = logging.getLogger("endless_library.cache")

DEFAULT_TTL_SECONDS = 60
# Счётчик популярности живёт дольше, но не вечно: если Redis пропустил увеличение (был недоступен),
# через это время счётчик пересоберётся из базы и ошибка исправится сама.
POPULAR_TTL_SECONDS = 300
SOCKET_TIMEOUT_SECONDS = 0.5

BOOKS_LIST_KEY = "books:list"
POPULAR_KEY = "books:popular"


def book_key(book_id: int) -> str:
    return f"books:{book_id}"


class Cache:
    """Тонкая обёртка над Redis, которая не роняет приложение при сбоях Redis."""

    def __init__(self, client: redis.Redis | None = None, ttl: int = DEFAULT_TTL_SECONDS):
        self.client = client
        self.ttl = ttl

    @classmethod
    def from_url(cls, url: str | None) -> "Cache":
        if not url:
            return cls(None)
        client = redis.Redis.from_url(
            url,
            socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
            socket_timeout=SOCKET_TIMEOUT_SECONDS,
            decode_responses=True,
        )
        return cls(client)

    @property
    def enabled(self) -> bool:
        return self.client is not None

    # ---- обычный кэш: JSON по ключу с TTL ----

    def get_json(self, key: str):
        """Значение из кэша или None (промах, кэш выключен или Redis недоступен)."""
        if self.client is None:
            return None
        try:
            raw = self.client.get(key)
        except RedisError as exc:
            logger.warning("cache read failed for %s: %s", key, exc)
            CACHE_REQUESTS.labels("error").inc()
            return None
        CACHE_REQUESTS.labels("miss" if raw is None else "hit").inc()
        return None if raw is None else json.loads(raw)

    def set_json(self, key: str, value) -> None:
        if self.client is None:
            return
        try:
            self.client.set(key, json.dumps(value), ex=self.ttl)
        except RedisError as exc:
            logger.warning("cache write failed for %s: %s", key, exc)

    def delete(self, *keys: str) -> None:
        if self.client is None:
            return
        try:
            self.client.delete(*keys)
        except RedisError as exc:
            logger.warning("cache delete failed for %s: %s", keys, exc)

    def invalidate_book(self, book_id: int) -> None:
        """Книга изменилась (или изменился её остаток): забываем и её карточку, и общий список."""
        self.delete(book_key(book_id), BOOKS_LIST_KEY)

    def invalidate_books_list(self) -> None:
        self.delete(BOOKS_LIST_KEY)

    # ---- популярность: счётчик выдач в отсортированном множестве (sorted set) ----

    def record_loan(self, book_id: int) -> None:
        """Увеличивает счётчик выдач книги. Если счётчика ещё нет, он пересоберётся из базы при чтении."""
        if self.client is None:
            return
        try:
            # Увеличиваем, только если счётчик уже собран: иначе первая же выдача создала бы
            # «неполный» счётчик (с единицей), и чтение приняло бы его за настоящий.
            if self.client.exists(POPULAR_KEY):
                self.client.zincrby(POPULAR_KEY, 1, str(book_id))
                self.client.expire(POPULAR_KEY, POPULAR_TTL_SECONDS)
        except RedisError as exc:
            logger.warning("popularity counter update failed: %s", exc)

    def popular_counts(self) -> dict[int, int] | None:
        """Счётчики {id книги: число выдач} или None, если их нет в Redis (тогда считаем по базе)."""
        if self.client is None:
            return None
        try:
            items = self.client.zrange(POPULAR_KEY, 0, -1, withscores=True)
        except RedisError as exc:
            logger.warning("popularity counter read failed: %s", exc)
            return None
        return {int(member): int(score) for member, score in items} or None

    def store_popular(self, counts: dict[int, int]) -> None:
        """Сохраняет пересчитанные по базе счётчики."""
        if self.client is None or not counts:
            return
        try:
            pipe = self.client.pipeline()
            pipe.delete(POPULAR_KEY)
            pipe.zadd(POPULAR_KEY, {str(book_id): count for book_id, count in counts.items()})
            pipe.expire(POPULAR_KEY, POPULAR_TTL_SECONDS)
            pipe.execute()
        except RedisError as exc:
            logger.warning("popularity counter store failed: %s", exc)


# Общий экземпляр приложения. В тестах подменяется (см. tests/conftest.py, фикстура redis_cache).
cache = Cache.from_url(os.getenv("REDIS_URL"))
