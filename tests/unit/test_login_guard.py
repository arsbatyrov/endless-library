"""AUTH-010: the login guard itself (counter in Redis), including concurrent failures."""

import threading

import pytest
import redis

from app.auth.login_guard import LoginGuard

KEY_PREFIX = "login_fail:"


@pytest.fixture
def guard(redis_client):
    return LoginGuard(lambda: redis_client, max_attempts=3, window_seconds=60)


def test_not_locked_before_the_limit(guard):
    guard.record_failure("ann")
    guard.record_failure("ann")

    assert guard.check("ann") is None


def test_locked_at_the_limit_with_the_remaining_seconds(guard):
    for _ in range(3):
        guard.record_failure("ann")

    wait = guard.check("ann")

    assert wait is not None and 1 <= wait <= 60


def test_reset_clears_the_counter(guard):
    for _ in range(3):
        guard.record_failure("ann")

    guard.reset("ann")

    assert guard.check("ann") is None


def test_counters_are_separate_per_login(guard):
    for _ in range(3):
        guard.record_failure("ann")

    assert guard.check("bob") is None


def test_logins_are_compared_ignoring_case(guard):
    guard.record_failure("ANN")
    guard.record_failure("Ann")
    guard.record_failure("ann")

    assert guard.check("aNn") is not None


def test_unicode_case_variants_share_one_counter(guard):
    guard.record_failure("STRASSE")
    guard.record_failure("straße")
    guard.record_failure("Strasse")

    assert guard.check("strasse") is not None


def test_key_is_a_hash_not_the_login(guard, redis_client):
    guard.record_failure("some.person@example.com")

    (key,) = redis_client.keys("*")

    assert key.startswith(KEY_PREFIX)
    assert "person" not in key and "example" not in key
    assert len(key) == len(KEY_PREFIX) + 64


def test_very_long_logins_make_short_keys(guard, redis_client):
    guard.record_failure("x" * 5000)

    (key,) = redis_client.keys("*")

    assert len(key) < 100


def test_first_failure_starts_the_window(guard, redis_client):
    guard.record_failure("ann")

    (key,) = redis_client.keys("*")
    assert 55 <= redis_client.ttl(key) <= 60


def test_later_failures_do_not_restart_the_window_before_the_limit(guard, redis_client):
    guard.record_failure("ann")
    (key,) = redis_client.keys("*")
    redis_client.expire(key, 30)

    guard.record_failure("ann")

    assert redis_client.ttl(key) <= 30


def test_reaching_the_limit_restarts_the_window(guard, redis_client):
    guard.record_failure("ann")
    guard.record_failure("ann")
    (key,) = redis_client.keys("*")
    redis_client.expire(key, 10)

    guard.record_failure("ann")

    assert redis_client.ttl(key) >= 55


def test_concurrent_failures_are_all_counted(redis_client):
    guard = LoginGuard(lambda: redis_client, max_attempts=1000, window_seconds=60)
    errors = []

    def work():
        try:
            for _ in range(25):
                guard.record_failure("ann")
        except Exception as error:  # pragma: no cover - only on failure
            errors.append(error)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    (key,) = redis_client.keys("*")
    assert errors == []
    assert redis_client.get(key) == "200"


def test_the_counter_always_has_an_expiry_even_under_concurrency(redis_client):
    guard = LoginGuard(lambda: redis_client, max_attempts=1000, window_seconds=60)

    threads = [
        threading.Thread(target=lambda: [guard.record_failure("x") for _ in range(20)])
        for _ in range(6)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    (key,) = redis_client.keys("*")
    assert redis_client.ttl(key) > 0


def test_everything_is_a_noop_without_a_client():
    guard = LoginGuard(lambda: None, max_attempts=3, window_seconds=60)

    guard.record_failure("ann")
    guard.reset("ann")

    assert guard.check("ann") is None


def test_redis_errors_never_propagate():
    dead = redis.Redis.from_url(
        "redis://127.0.0.1:1/0", socket_connect_timeout=0.1, socket_timeout=0.1
    )
    guard = LoginGuard(lambda: dead, max_attempts=3, window_seconds=60)

    guard.record_failure("ann")
    guard.reset("ann")

    assert guard.check("ann") is None


def test_retry_after_is_at_least_one_second_even_when_the_lock_is_about_to_end(guard, redis_client):
    for _ in range(3):
        guard.record_failure("ann")
    (key,) = redis_client.keys("*")
    redis_client.pexpire(key, 400)  # TTL would round down to 0

    assert guard.check("ann") == 1
