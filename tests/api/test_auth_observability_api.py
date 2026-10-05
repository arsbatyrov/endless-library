"""AUTH-016: metrics and the log of sign-ins (acceptance criteria 1-3).

Counters live in the memory of the whole process and are never reset between tests, so every test compares the value
BEFORE and AFTER an action (the increase), never absolute numbers.

The log never contains a password, a token, a hash or the login of a FAILED attempt (people often type a password
into the login field); a failure carries only a short hash of the login, which still lets an operator see that
many attempts hit the same login.
"""

import io
import json
import logging

import pytest
from prometheus_client import REGISTRY

from app.auth.passwords import hash_password  # noqa: F401  (documents what must never be logged)
from app.auth.refresh_tokens import COOKIE_NAME
from app.logging_config import JsonFormatter
from app.models import RefreshToken
from tests.factories import make_user

PASSWORD = "correct horse"
WRONG = "wrong password"
LOGINS = "endless_library_auth_logins_total"
REFRESHES = "endless_library_auth_refresh_total"


@pytest.fixture
def client(anonymous_client):
    return anonymous_client


@pytest.fixture
def user(db):
    return make_user(db, role="librarian", username="ann", password=PASSWORD)


def count(name: str, result: str) -> float:
    return REGISTRY.get_sample_value(name, {"result": result}) or 0.0


def login(client, username="ann", password=PASSWORD, **kwargs):
    return client.post("/auth/login", json={"username": username, "password": password}, **kwargs)


@pytest.fixture
def json_logs():
    """Captures what the application logs as the JSON lines it really writes (with the request id)."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("endless_library")
    logger.addHandler(handler)

    def lines(event: str | None = None) -> list[dict]:
        parsed = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
        return [p for p in parsed if event is None or p.get("event") == event]

    def raw() -> str:
        return stream.getvalue()

    lines.raw = raw
    yield lines
    logger.removeHandler(handler)


# ---------- criterion 1: the login counter ----------


def test_a_successful_login_is_counted(client, user):
    before = count(LOGINS, "success")

    login(client)

    assert count(LOGINS, "success") == before + 1


def test_a_wrong_password_is_counted_as_a_failure(client, user):
    before = (count(LOGINS, "failure"), count(LOGINS, "success"))

    login(client, password=WRONG)

    assert count(LOGINS, "failure") == before[0] + 1
    assert count(LOGINS, "success") == before[1]


def test_an_unknown_login_is_a_failure_just_like_a_wrong_password(client, user):
    before = count(LOGINS, "failure")

    login(client, username="ghost")
    login(client, password=WRONG)

    assert count(LOGINS, "failure") == before + 2


def test_a_disabled_account_is_a_failure(client, db, user):
    user.is_active = False
    db.commit()
    before = count(LOGINS, "failure")

    login(client)

    assert count(LOGINS, "failure") == before + 1


def test_a_locked_login_is_counted_as_locked_and_not_as_a_failure(client, user, redis_cache):
    for _ in range(5):
        login(client, password=WRONG)
    before = (count(LOGINS, "locked"), count(LOGINS, "failure"), count(LOGINS, "success"))

    response = login(client)  # right password, but locked

    assert response.status_code == 429
    assert count(LOGINS, "locked") == before[0] + 1
    assert count(LOGINS, "failure") == before[1]
    assert count(LOGINS, "success") == before[2]


def test_the_failures_before_the_lock_are_all_counted(client, user, redis_cache):
    before = count(LOGINS, "failure")

    for _ in range(5):
        login(client, password=WRONG)

    assert count(LOGINS, "failure") == before + 5


def test_exactly_one_result_is_counted_per_attempt(client, user):
    before = {r: count(LOGINS, r) for r in ("success", "failure", "locked")}

    login(client)
    login(client, password=WRONG)

    after = {r: count(LOGINS, r) for r in before}
    assert sum(after.values()) - sum(before.values()) == 2


def test_a_malformed_request_is_not_a_login_attempt(client, user):
    before = {r: count(LOGINS, r) for r in ("success", "failure", "locked")}

    client.post("/auth/login", json={"username": "ann"})  # 422: no password
    client.post(
        "/auth/login", content=b"{broken", headers={"Content-Type": "application/json"}
    )  # 400

    assert {r: count(LOGINS, r) for r in before} == before


def test_the_counter_has_only_the_result_label_so_no_login_becomes_a_label(client, user):
    login(client, username="some.person@example.com", password=WRONG)

    series = [
        sample
        for family in REGISTRY.collect()
        if family.name == LOGINS.removesuffix("_total")
        for sample in family.samples
        if sample.name == LOGINS
    ]

    assert series
    assert all(set(sample.labels) == {"result"} for sample in series)
    assert {s.labels["result"] for s in series} == {"success", "failure", "locked"}


def test_all_results_exist_from_the_start_so_graphs_never_have_gaps():
    """A fresh process already exposes every series at 0 (a `rate()` of a missing series would be empty)."""
    import os
    import subprocess
    import sys

    code = (
        "from prometheus_client import generate_latest;import app.metrics;"
        "print(generate_latest().decode())"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "PYTHONPATH": os.getcwd()},
        capture_output=True,
        text=True,
        timeout=60,
    )

    for series in (
        f'{LOGINS}{{result="success"}} 0.0',
        f'{LOGINS}{{result="failure"}} 0.0',
        f'{LOGINS}{{result="locked"}} 0.0',
        f'{REFRESHES}{{result="ok"}} 0.0',
        f'{REFRESHES}{{result="rejected"}} 0.0',
    ):
        assert series in result.stdout, series


def test_the_counters_are_exposed_on_the_metrics_endpoint(client, user):
    login(client)

    text = client.get("/metrics").text

    assert f"# TYPE {LOGINS} counter" in text
    assert f"# TYPE {REFRESHES} counter" in text
    assert f'{LOGINS}{{result="success"}}' in text


# ---------- criterion 2: the refresh counter ----------


def test_a_valid_refresh_is_counted_as_ok(client, user):
    login(client)
    before = count(REFRESHES, "ok")

    assert client.post("/auth/refresh").status_code == 200

    assert count(REFRESHES, "ok") == before + 1


def test_a_missing_cookie_is_rejected(client):
    before = count(REFRESHES, "rejected")

    assert client.post("/auth/refresh").status_code == 401

    assert count(REFRESHES, "rejected") == before + 1


def test_an_unknown_token_is_rejected(client):
    client.cookies.set(COOKIE_NAME, "not-a-token", path="/auth")
    before = count(REFRESHES, "rejected")

    client.post("/auth/refresh")

    assert count(REFRESHES, "rejected") == before + 1


def test_a_replaced_token_is_rejected_and_not_counted_as_ok(client, user):
    login(client)
    old = client.cookies.get(COOKIE_NAME)
    client.post("/auth/refresh")
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, old, path="/auth")
    before = (count(REFRESHES, "ok"), count(REFRESHES, "rejected"))

    client.post("/auth/refresh")

    assert count(REFRESHES, "ok") == before[0]
    assert count(REFRESHES, "rejected") == before[1] + 1


def test_a_disabled_user_is_rejected(client, db, user):
    login(client)
    user.is_active = False
    db.commit()
    before = count(REFRESHES, "rejected")

    client.post("/auth/refresh")

    assert count(REFRESHES, "rejected") == before + 1


def test_an_expired_token_is_rejected(client, db, user):
    from datetime import UTC, datetime, timedelta

    login(client)
    db.query(RefreshToken).update({"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    db.commit()
    before = count(REFRESHES, "rejected")

    client.post("/auth/refresh")

    assert count(REFRESHES, "rejected") == before + 1


def test_login_and_logout_do_not_touch_the_refresh_counter(client, user):
    before = (count(REFRESHES, "ok"), count(REFRESHES, "rejected"))

    login(client)
    client.post("/auth/logout")

    assert (count(REFRESHES, "ok"), count(REFRESHES, "rejected")) == before


# ---------- criterion 3: the log ----------


def test_a_successful_login_is_logged_with_the_request_id_and_the_result(client, user, json_logs):
    response = login(client, headers={"X-Request-ID": "req-ok-1"})

    (event,) = json_logs("login")
    assert response.headers["x-request-id"] == "req-ok-1"
    assert event["request_id"] == "req-ok-1"
    assert event["result"] == "success"
    assert event["user_id"] == user.id
    assert event["role"] == "librarian"


def test_a_failed_login_is_logged_without_the_login_itself(client, user, json_logs):
    login(
        client,
        username="some.person@example.com",
        password=WRONG,
        headers={"X-Request-ID": "req-bad-1"},
    )

    (event,) = json_logs("login")
    assert event["result"] == "failure"
    assert event["request_id"] == "req-bad-1"
    assert len(event["login_hash"]) == 12
    assert "some.person" not in json_logs.raw()
    assert "example.com" not in json_logs.raw()


def test_an_existing_and_an_unknown_login_leave_identical_log_entries(client, user, json_logs):
    login(client, username="ann", password=WRONG)
    login(client, username="ghost", password=WRONG)

    real, ghost = json_logs("login")
    assert set(real) == set(ghost)
    assert real["result"] == ghost["result"] == "failure"
    assert "user_id" not in real and "user_id" not in ghost


def test_the_login_hash_lets_an_operator_see_many_attempts_on_one_login(client, user, json_logs):
    login(client, username="ann", password=WRONG)
    login(client, username="ANN", password="another wrong one")
    login(client, username="bob", password=WRONG)

    first, second, third = json_logs("login")
    assert first["login_hash"] == second["login_hash"] != third["login_hash"]


def test_a_locked_login_is_logged_as_locked(client, user, redis_cache, json_logs):
    for _ in range(5):
        login(client, password=WRONG)

    login(client, headers={"X-Request-ID": "req-lock-1"})

    event = json_logs("login")[-1]
    assert event["result"] == "locked"
    assert event["request_id"] == "req-lock-1"
    assert event["level"] == "WARNING"


def test_a_refresh_is_logged_with_its_result(client, user, json_logs):
    login(client)
    client.post("/auth/refresh", headers={"X-Request-ID": "req-refresh-1"})
    client.cookies.clear()
    client.post("/auth/refresh", headers={"X-Request-ID": "req-refresh-2"})

    ok, rejected = json_logs("refresh")
    assert (ok["result"], ok["request_id"], ok["user_id"]) == ("ok", "req-refresh-1", user.id)
    assert (rejected["result"], rejected["request_id"]) == ("rejected", "req-refresh-2")
    assert "user_id" not in rejected
    assert (ok["level"], rejected["level"]) == ("INFO", "WARNING")


def test_the_reuse_of_a_replaced_token_is_logged_as_a_warning_with_the_user(
    client, user, json_logs
):
    login(client)
    old = client.cookies.get(COOKIE_NAME)
    client.post("/auth/refresh")
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, old, path="/auth")

    client.post("/auth/refresh", headers={"X-Request-ID": "req-theft-1"})

    (event,) = json_logs("refresh_token_reuse")
    assert event["level"] == "WARNING"
    assert event["user_id"] == user.id
    assert event["request_id"] == "req-theft-1"


def test_a_logout_is_logged(client, user, json_logs):
    login(client)

    client.post("/auth/logout", headers={"X-Request-ID": "req-logout-1"})

    (event,) = json_logs("logout")
    assert event["result"] == "ok"
    assert event["request_id"] == "req-logout-1"


def test_a_password_change_is_logged_without_any_password(client, user, json_logs):
    token = login(client).json()["access_token"]

    client.post(
        "/auth/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": PASSWORD, "new_password": "battery staple"},
    )

    (event,) = json_logs("password_changed")
    assert event["user_id"] == user.id
    assert "battery staple" not in json_logs.raw()


def test_no_secret_ever_reaches_the_log(client, db, user, json_logs):
    """Whatever the flow does, the log holds no password, token, cookie or hash."""
    response = login(client)
    access = response.json()["access_token"]
    refresh = client.cookies.get(COOKIE_NAME)
    login(client, password=WRONG)
    client.post("/auth/refresh")
    client.post("/auth/logout")
    client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    client.post("/auth/refresh")

    log = json_logs.raw()

    for secret in (PASSWORD, WRONG, access, refresh, user.password_hash, "set-cookie", "argon2"):
        assert secret.lower() not in log.lower(), secret


def test_every_auth_event_carries_the_request_id_and_a_timestamp(client, user, json_logs):
    login(client)
    login(client, password=WRONG)
    client.post("/auth/refresh")
    client.post("/auth/logout")

    events = [e for e in json_logs() if e.get("event") in {"login", "refresh", "logout"}]

    assert len(events) == 4
    assert all(e["request_id"] != "-" for e in events)
    assert all("ts" in e and "level" in e for e in events)


def test_the_guard_failure_is_still_logged_when_redis_is_down(client, user, json_logs, monkeypatch):
    import redis

    from app.cache import cache

    dead = redis.Redis.from_url(
        "redis://127.0.0.1:1/0",
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
        decode_responses=True,
    )
    monkeypatch.setattr(cache, "client", dead)

    response = login(client)

    assert response.status_code == 200
    assert any("login guard" in line["msg"] for line in json_logs())
    assert json_logs("login")[-1]["result"] == "success"
