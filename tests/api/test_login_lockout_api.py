"""AUTH-010: brute-force protection of POST /auth/login (acceptance criteria 1-5).

Five failed logins in a row for one login (15-minute window) lock that login for 15 minutes: the sixth attempt is
answered with 429 and Retry-After, even with the right password. The counter lives in Redis and the protection fails
open: if Redis is unavailable, signing in keeps working (availability wins) and the failure is logged and counted.
"""

import hashlib
import logging
import time

import pytest
import redis
from prometheus_client import REGISTRY

from app.auth.login_guard import MAX_FAILED_ATTEMPTS, WINDOW_SECONDS
from app.cache import cache
from app.models import RefreshToken
from tests.factories import make_user

PASSWORD = "correct horse"
WRONG = "wrong password"
GUARD_FAILURES = "endless_library_login_guard_failures_total"


def login(client, username="ann", password=PASSWORD):
    return client.post("/auth/login", json={"username": username, "password": password})


def fail(client, times, username="ann"):
    for _ in range(times):
        assert login(client, username, WRONG).status_code == 401


def key_for(username: str) -> str:
    return "login_fail:" + hashlib.sha256(username.casefold().encode()).hexdigest()


def metric(reason: str) -> float:
    return REGISTRY.get_sample_value(GUARD_FAILURES, {"reason": reason}) or 0.0


@pytest.fixture
def user(db):
    return make_user(db, role="librarian", username="ann", password=PASSWORD)


@pytest.fixture
def guarded(redis_cache):
    """Redis is available: the protection is active."""
    return redis_cache


def test_limits_are_five_failures_and_fifteen_minutes():
    assert MAX_FAILED_ATTEMPTS == 5
    assert WINDOW_SECONDS == 15 * 60


# ---------- criterion 1: the sixth attempt ----------


def test_fifth_failure_is_still_401_and_the_sixth_attempt_is_429(client, guarded, user):
    fail(client, 5)

    response = login(client)  # right password, but the login is locked

    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= WINDOW_SECONDS


def test_four_failures_do_not_lock(client, guarded, user):
    fail(client, 4)

    assert login(client).status_code == 200


def test_a_locked_login_stays_locked_for_a_wrong_password_too(client, guarded, user):
    fail(client, 5)

    assert login(client, "ann", WRONG).status_code == 429


def test_no_session_is_created_while_locked(client, db, guarded, user):
    fail(client, 5)

    response = login(client)

    assert response.status_code == 429
    assert "set-cookie" not in response.headers
    assert "access_token" not in response.text
    db.expire_all()
    assert db.query(RefreshToken).count() == 0
    assert user.last_login_at is None


def test_the_lock_message_does_not_reveal_details(client, guarded, user):
    fail(client, 5)

    body = login(client).json()

    assert set(body) == {"detail"}
    assert "ann" not in body["detail"].lower()
    assert PASSWORD not in str(body)


def test_retry_after_matches_the_remaining_lock_time(client, guarded, user):
    fail(client, 5)
    guarded.client.expire(key_for("ann"), 120)

    response = login(client)

    assert 118 <= int(response.headers["retry-after"]) <= 120


def test_lock_lasts_fifteen_minutes_from_the_fifth_failure(client, guarded, user):
    fail(client, 3)
    guarded.client.expire(key_for("ann"), 100)  # the window of the first failures is nearly over
    fail(client, 2)

    ttl = guarded.client.ttl(key_for("ann"))

    assert WINDOW_SECONDS - 5 <= ttl <= WINDOW_SECONDS


def test_attempts_during_the_lock_do_not_extend_it(client, guarded, user):
    fail(client, 5)
    guarded.client.expire(key_for("ann"), 200)

    for _ in range(3):
        login(client)

    assert guarded.client.ttl(key_for("ann")) <= 200
    assert guarded.client.get(key_for("ann")) == "5"


def test_the_window_starts_at_the_first_failure(client, guarded, user):
    fail(client, 1)

    assert WINDOW_SECONDS - 5 <= guarded.client.ttl(key_for("ann")) <= WINDOW_SECONDS


def test_other_logins_are_not_affected(client, db, guarded, user):
    make_user(db, role="admin", username="bob", password=PASSWORD)
    fail(client, 5)

    assert login(client, "bob").status_code == 200


def test_the_counter_ignores_case_of_the_login(client, guarded, user):
    fail(client, 2, "ANN")
    fail(client, 2, "Ann")
    fail(client, 1, "ann")

    assert login(client, "aNN").status_code == 429


def test_a_disabled_account_is_locked_like_any_other(client, db, guarded, user):
    user.is_active = False
    db.commit()

    fail(client, 5)

    assert login(client).status_code == 429


# ---------- criterion 2: success resets the counter ----------


def test_success_resets_the_counter(client, guarded, user):
    fail(client, 4)
    assert login(client).status_code == 200
    assert guarded.client.get(key_for("ann")) is None

    fail(client, 4)  # would be 8 in total if the counter had not been reset

    assert login(client).status_code == 200


def test_after_a_success_five_new_failures_are_needed(client, guarded, user):
    fail(client, 4)
    login(client)
    fail(client, 5)

    assert login(client).status_code == 429


# ---------- criterion 3: unknown logins ----------


def test_unknown_login_is_locked_in_the_same_way(client, guarded):
    fail(client, 5, "ghost")

    response = login(client, "ghost")

    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= WINDOW_SECONDS


def test_existing_and_unknown_logins_are_indistinguishable(client, guarded, user):
    fail(client, 5, "ann")
    fail(client, 5, "ghost")

    real = login(client, "ann", WRONG)
    ghost = login(client, "ghost", WRONG)

    assert real.status_code == ghost.status_code == 429
    assert real.json() == ghost.json()
    assert set(real.headers) == set(ghost.headers)


def test_the_sequence_of_answers_is_identical_for_existing_and_unknown_logins(
    client, guarded, user
):
    def sequence(username):
        return [login(client, username, WRONG).status_code for _ in range(7)]

    assert sequence("ann") == sequence("ghost") == [401] * 5 + [429] * 2


# ---------- criterion 4: the lock ends ----------


def test_login_works_again_when_the_lock_expires(client, guarded, user):
    fail(client, 5)
    assert login(client).status_code == 429

    guarded.client.pexpire(key_for("ann"), 50)
    time.sleep(0.2)

    assert login(client).status_code == 200


def test_after_the_lock_the_counter_starts_from_zero(client, guarded, user):
    fail(client, 5)
    guarded.client.pexpire(key_for("ann"), 50)
    time.sleep(0.2)

    fail(client, 4)

    assert login(client).status_code == 200


def test_a_counter_without_an_expiry_cannot_lock_forever(client, guarded, user):
    """If a process died between two Redis commands, the key must not stay locked for ever."""
    guarded.client.set(key_for("ann"), "5")  # no TTL

    response = login(client)

    assert response.status_code == 429
    assert 0 < guarded.client.ttl(key_for("ann")) <= WINDOW_SECONDS


# ---------- privacy ----------


def test_redis_keys_do_not_contain_the_login_or_the_password(client, guarded, user):
    fail(client, 2)

    keys = guarded.client.keys("*")

    assert keys == [key_for("ann")]
    assert all("ann" not in key.replace("login_fail", "") for key in keys)
    assert WRONG not in " ".join(keys)


# ---------- criterion 5: Redis is unavailable ----------


@pytest.fixture
def dead_redis(monkeypatch):
    dead = redis.Redis.from_url(
        "redis://127.0.0.1:1/0",
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
        decode_responses=True,
    )
    monkeypatch.setattr(cache, "client", dead)


def test_login_works_when_redis_is_unreachable(client, dead_redis, user):
    started = time.monotonic()
    response = login(client)
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert elapsed < 5


def test_a_wrong_password_is_still_401_when_redis_is_unreachable(client, dead_redis, user):
    assert login(client, "ann", WRONG).status_code == 401


def test_no_lock_without_redis_however_many_failures(client, dead_redis, user):
    fail(client, 8)

    assert login(client).status_code == 200


def test_the_failure_is_logged_and_counted(client, dead_redis, user, caplog):
    before = metric("redis_error")

    with caplog.at_level(logging.WARNING, logger="endless_library"):
        login(client)

    assert metric("redis_error") > before
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "login guard" in messages
    assert "ann" not in messages and PASSWORD not in messages


def test_an_error_in_the_middle_of_a_login_is_survived(client, guarded, user, monkeypatch):
    def broken(*args, **kwargs):
        raise redis.exceptions.ConnectionError("connection lost")

    monkeypatch.setattr(guarded.client, "pipeline", broken)
    monkeypatch.setattr(guarded.client, "eval", broken)
    monkeypatch.setattr(guarded.client, "delete", broken)

    assert login(client).status_code == 200
    assert login(client, "ann", WRONG).status_code == 401


def test_redis_not_configured_means_no_protection_and_a_counted_reason(client, user):
    assert cache.enabled is False
    before = metric("not_configured")

    fail(client, 6)

    assert login(client).status_code == 200
    assert metric("not_configured") > before


def test_a_working_redis_does_not_count_a_failure(client, guarded, user):
    before = (metric("redis_error"), metric("not_configured"))

    login(client)
    fail(client, 1)

    assert (metric("redis_error"), metric("not_configured")) == before


# ---------- the response contract ----------


def test_429_is_documented_with_retry_after(client):
    spec = client.get("/openapi.json").json()
    response = spec["paths"]["/auth/login"]["post"]["responses"]["429"]

    assert "Retry-After" in response["headers"]


def test_a_malformed_request_does_not_count_as_a_failed_attempt(client, guarded, user):
    for _ in range(6):
        client.post("/auth/login", json={"username": "ann"})  # 422: no password

    assert guarded.client.get(key_for("ann")) is None
    assert login(client).status_code == 200
