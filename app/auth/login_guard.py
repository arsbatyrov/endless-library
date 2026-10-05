"""Brute-force protection of the login (AUTH-010).

Five failed logins in a row for one login lock that login for 15 minutes. The counter lives in Redis, per login
(not per IP address), and the same rule applies to logins that do not exist, so the answer never reveals which
logins exist.

The protection FAILS OPEN: if Redis is unavailable or not configured, signing in keeps working without the lock
(availability matters more) and the failure is logged and counted in a metric.
"""

import hashlib
import logging
from collections.abc import Callable

import redis
from redis.exceptions import RedisError

from app.cache import cache
from app.metrics import LOGIN_GUARD_FAILURES

logger = logging.getLogger("endless_library.auth")

MAX_FAILED_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60

# INCR and EXPIRE in one atomic step: a process that dies between two separate commands would leave a counter
# without an expiry, which would lock the login for ever. The window starts at the first failure; reaching the limit
# restarts it, so the lock lasts the full window counted from the last failure that caused it.
_RECORD_FAILURE = """
local count = redis.call('INCR', KEYS[1])
if count == 1 or count >= tonumber(ARGV[2]) then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return count
"""


class LoginGuard:
    def __init__(
        self,
        get_client: Callable[[], redis.Redis | None],
        max_attempts: int = MAX_FAILED_ATTEMPTS,
        window_seconds: int = WINDOW_SECONDS,
    ):
        self._get_client = get_client
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds

    @staticmethod
    def _key(username: str) -> str:
        # casefold: "ANN", "Ann" and "ann" are one login. The key is a hash, so no login (personal data) is stored
        # in Redis and a very long login cannot make a long key.
        return "login_fail:" + hashlib.sha256(username.casefold().encode("utf-8")).hexdigest()

    def _client(self) -> redis.Redis | None:
        client = self._get_client()
        if client is None:
            LOGIN_GUARD_FAILURES.labels("not_configured").inc()
        return client

    @staticmethod
    def _failed(error: RedisError) -> None:
        LOGIN_GUARD_FAILURES.labels("redis_error").inc()
        # Never the login or the password in the log.
        logger.warning(
            "login guard unavailable, brute-force protection is off for this request: %s", error
        )

    def check(self, username: str) -> int | None:
        """Seconds the login must wait if it is locked, otherwise None."""
        client = self._client()
        if client is None:
            return None
        key = self._key(username)
        try:
            pipe = client.pipeline()
            pipe.get(key)
            pipe.ttl(key)
            count, ttl = pipe.execute()
            if count is None or int(count) < self.max_attempts:
                return None
            if ttl < 0:  # a counter without an expiry must never lock for ever
                client.expire(key, self.window_seconds)
                ttl = self.window_seconds
            return max(int(ttl), 1)
        except RedisError as error:
            self._failed(error)
            return None

    def record_failure(self, username: str) -> None:
        client = self._client()
        if client is None:
            return
        try:
            client.eval(
                _RECORD_FAILURE, 1, self._key(username), self.window_seconds, self.max_attempts
            )
        except RedisError as error:
            self._failed(error)

    def reset(self, username: str) -> None:
        """A successful login starts the count again."""
        client = self._client()
        if client is None:
            return
        try:
            client.delete(self._key(username))
        except RedisError as error:
            self._failed(error)


# The application's guard uses the same Redis connection as the cache (tests swap it with `cache.client`).
login_guard = LoginGuard(lambda: cache.client)
