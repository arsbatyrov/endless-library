"""AUTH-017, criterion 5 and more: the sign-in endpoint reveals nothing and survives hostile input.

Criterion 5: a wrong login, a wrong password and a disabled account are indistinguishable by status, body, headers and
(within a tolerance) time. The rest: injection payloads, oversized and mistyped bodies, wrong verbs, CORS, and one
documented limitation of access tokens.
"""

import statistics
import time

import pytest

from app.models import RefreshToken, User
from tests.factories import make_user
from tests.security.conftest import PASSWORD, auth

WRONG = "wrong password"
VOLATILE_HEADERS = {"date", "x-request-id"}


def login(client, username="ann", password=PASSWORD, **kwargs):
    return client.post("/auth/login", json={"username": username, "password": password}, **kwargs)


@pytest.fixture
def user(db):
    return make_user(db, role="librarian", username="ann", password=PASSWORD)


def fingerprint(response) -> tuple:
    headers = {
        k.lower(): v for k, v in response.headers.items() if k.lower() not in VOLATILE_HEADERS
    }
    return response.status_code, response.text, tuple(sorted(headers.items()))


# ---------- criterion 5: indistinguishable ----------


def test_wrong_password_unknown_login_and_disabled_account_give_identical_answers(client, db, user):
    make_user(db, role="reader", username="rita", password=PASSWORD, active=False)

    wrong_password = login(client, "ann", WRONG)
    unknown_login = login(client, "no-such-person", WRONG)
    unknown_login_right_password = login(client, "no-such-person", PASSWORD)
    disabled = login(client, "rita", PASSWORD)
    disabled_wrong = login(client, "rita", WRONG)

    prints = {
        fingerprint(r)
        for r in (
            wrong_password,
            unknown_login,
            unknown_login_right_password,
            disabled,
            disabled_wrong,
        )
    }
    assert len(prints) == 1, prints
    assert next(iter(prints))[0] == 401


def test_the_answer_does_not_depend_on_the_role_or_the_card_of_the_account(client, db):
    make_user(db, role="admin", username="root", password=PASSWORD)
    make_user(db, role="reader", username="rita", password=PASSWORD)

    prints = {
        fingerprint(login(client, name, WRONG))
        for name in ("root", "rita", "ghost", "ROOT", "Rita")
    }

    assert len(prints) == 1


def test_no_cookie_or_token_is_issued_on_any_failure(client, db, user):
    make_user(db, role="reader", username="rita", password=PASSWORD, active=False)

    for name, password in (("ann", WRONG), ("ghost", WRONG), ("rita", PASSWORD)):
        response = login(client, name, password)
        assert "set-cookie" not in response.headers
        assert "access_token" not in response.text
    assert db.query(RefreshToken).count() == 0


def timing(client, name, password, rounds):
    started = time.perf_counter()
    login(client, name, password)
    rounds.append(time.perf_counter() - started)


def test_the_time_to_answer_does_not_reveal_which_logins_exist(client, db, user):
    """The password check (the slow part) runs in every case, also for a login that does not exist.

    The medians of interleaved samples are compared, so a slow moment of the machine hits all kinds equally. The
    tolerance is generous (the failure this guards against is a ~100x difference: skipping the hash).
    """
    make_user(db, role="reader", username="rita", password=PASSWORD, active=False)
    kinds = {
        "wrong password": ("ann", WRONG),
        "unknown login": ("no-such-person", WRONG),
        "disabled, right password": ("rita", PASSWORD),
    }
    samples = {kind: [] for kind in kinds}
    login(
        client, "ann", WRONG
    )  # warm-up: the first hash builds the dummy hash and loads the library

    for _ in range(9):
        for kind, (name, password) in kinds.items():
            timing(client, name, password, samples[kind])

    medians = {kind: statistics.median(values) for kind, values in samples.items()}
    slowest, fastest = max(medians.values()), min(medians.values())
    assert fastest > 0.005, (
        f"a failed login answered in {fastest * 1000:.1f} ms: the password is not being hashed"
    )
    assert slowest / fastest < 2.0, medians


def test_locked_answers_are_identical_for_existing_and_unknown_logins(
    client, db, user, redis_cache
):
    for _ in range(5):
        login(client, "ann", WRONG)
        login(client, "ghost", WRONG)

    real, ghost = login(client, "ann"), login(client, "ghost")

    assert (real.status_code, real.text) == (ghost.status_code, ghost.text) == (429, real.text)
    assert abs(int(real.headers["retry-after"]) - int(ghost.headers["retry-after"])) <= 2
    assert set(real.headers) == set(ghost.headers)


def test_the_lock_cannot_be_dodged_by_changing_the_spelling_of_the_login(
    client, db, user, redis_cache
):
    for _ in range(5):
        login(client, "ann", WRONG)

    for variant in ("ANN", "Ann", "aNn"):
        assert login(client, variant).status_code == 429


def test_creating_an_account_does_not_reveal_logins_to_the_unauthenticated(client, user):
    response = client.post(
        "/users", json={"username": "ann", "password": PASSWORD, "role": "librarian"}
    )

    assert response.status_code == 401  # not 409: existence is shown only to staff


# ---------- hostile input ----------

INJECTION = [
    "' OR '1'='1",
    "' OR 1=1 --",
    "ann'--",
    "ann' #",
    "admin'/*",
    '" OR ""="',
    "ann'; DROP TABLE users; --",
    "'; UPDATE users SET role='admin'; --",
    "1; SELECT pg_sleep(5)",
    "ann' AND (SELECT 1 FROM pg_sleep(5))--",
    "%' OR '%'='",
    "\\' OR 1=1 --",
    "*)(uid=*))(|(uid=*",
    "../../../../etc/passwd",
    "..\\..\\windows\\win.ini",
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "{{7*7}}",
    "${7*7}",
    "${jndi:ldap://evil.example/a}",
    "%s%s%s%n",
    "ann\r\nSet-Cookie: injected=1",
    "ann\nX-Injected: 1",
    "ann‮gnp.exe",
    "аnn",  # a Cyrillic "а", a homoglyph of the Latin one
    "ann​",  # zero-width space
    "👾" * 20,
    "İ",  # a character whose lower-casing differs between systems
    " ",
    "ann ",
    " ann",
    "0",
    "-1",
    "null",
    "true",
    "undefined",
]


@pytest.mark.parametrize("payload", INJECTION)
def test_hostile_logins_never_sign_in_never_crash_and_are_never_echoed(client, db, user, payload):
    users_before = db.query(User).count()

    as_login = login(client, payload, PASSWORD)
    as_password = login(client, "ann", payload)
    in_both = login(client, payload, payload)

    for response in (as_login, as_password, in_both):
        assert response.status_code in (401, 422), (payload, response.status_code)
        assert "access_token" not in response.text
        assert "set-cookie" not in response.headers
        if len(payload) > 3:
            assert payload not in response.text
        assert "x-injected" not in response.headers and "injected" not in response.headers.get(
            "set-cookie", ""
        )
    db.expire_all()
    assert db.query(User).count() == users_before
    assert db.query(User).filter_by(username="ann").one().role == "librarian"


def test_a_comment_or_quote_trick_does_not_authenticate_as_the_real_user(client, user):
    for payload in ("ann'--", "ann' OR '1'='1", 'ann" --', "ann'/*"):
        assert login(client, payload, "anything at all").status_code in (401, 422)


@pytest.mark.parametrize(
    "body",
    [
        {"username": {"$ne": None}, "password": {"$ne": None}},
        {"username": {"$gt": ""}, "password": {"$gt": ""}},
        {"username": ["ann"], "password": [PASSWORD]},
        {"username": ["ann", "bob"], "password": PASSWORD},
        {"username": 1, "password": 1},
        {"username": True, "password": True},
        {"username": None, "password": None},
        {"username": "ann", "password": None},
        {"username": "ann"},
        {"password": PASSWORD},
        {},
        [],
        "ann",
        42,
        None,
        {"username": "ann", "password": PASSWORD, "admin": True, "role": "admin"},
    ],
)
def test_mistyped_or_structured_bodies_are_refused_cleanly(client, user, body):
    response = client.post("/auth/login", json=body)

    # the extra-fields body is a valid login: it signs in the real user as themselves and nothing more
    if body == {"username": "ann", "password": PASSWORD, "admin": True, "role": "admin"}:
        assert response.status_code == 200
        assert client.get("/auth/me", headers=auth_from(response)).json()["role"] == "librarian"
    else:
        assert response.status_code in (400, 422), response.text
        assert "access_token" not in response.text


def auth_from(response) -> dict:
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{",
        b"{broken",
        b"null",
        b"\xff\xfe\x00\x00",
        b'{"username":"ann","password":"x"}\x00',
        b'{"username":"ann\x00","password":"x"}',
        b"[" * 20000 + b"]" * 20000,
        b'{"a":' * 5000 + b"1" + b"}" * 5000,
        b"A" * 100_000,
    ],
    ids=[
        "empty",
        "open-brace",
        "broken-object",
        "null",
        "invalid-utf8",
        "trailing-nul",
        "nul-in-login",
        "array-nesting-20000",
        "object-nesting-5000",
        "100k-bytes",
    ],
)
def test_malformed_bodies_get_a_client_error_never_a_server_error(client, user, raw):
    response = client.post("/auth/login", content=raw, headers={"Content-Type": "application/json"})

    assert 400 <= response.status_code < 500, response.status_code
    assert "Traceback" not in response.text and 'File "' not in response.text


@pytest.mark.parametrize(
    "content_type", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data", ""]
)
def test_other_content_types_do_not_sign_anybody_in(client, user, content_type):
    headers = {"Content-Type": content_type} if content_type else {}

    response = client.post(
        "/auth/login", content=f"username=ann&password={PASSWORD}", headers=headers
    )

    assert response.status_code in (400, 415, 422)
    assert "access_token" not in response.text


def test_a_credential_in_the_query_string_is_ignored(client, user):
    response = client.post(f"/auth/login?username=ann&password={PASSWORD}")

    assert response.status_code in (400, 422)
    assert (
        client.post(
            f"/auth/login?password={PASSWORD}", json={"username": "ann", "password": WRONG}
        ).status_code
        == 401
    )


def test_a_huge_password_is_refused_before_it_is_hashed(client, user):
    started = time.perf_counter()
    response = login(client, "ann", "x" * 1_000_000)
    elapsed = time.perf_counter() - started

    assert response.status_code == 422
    assert elapsed < 2.0
    assert "x" * 50 not in response.text


def test_a_huge_login_is_refused_without_a_query(client, user):
    started = time.perf_counter()
    response = login(client, "a" * 1_000_000, PASSWORD)

    assert response.status_code == 422
    assert time.perf_counter() - started < 2.0


def test_the_password_boundary_is_exactly_128_characters(client, user):
    assert login(client, "ann", "x" * 128).status_code == 401
    assert login(client, "ann", "x" * 129).status_code == 422


# ---------- verbs, CORS, headers ----------


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "PATCH", "HEAD", "TRACE"])
def test_the_login_endpoint_accepts_only_post(client, user, method):
    response = client.request(method, "/auth/login", json={"username": "ann", "password": PASSWORD})

    assert response.status_code in (405, 404)
    assert "access_token" not in response.text


def test_a_method_override_header_cannot_turn_a_post_into_something_else(client, user):
    response = client.post(
        "/auth/login",
        json={"username": "ann", "password": PASSWORD},
        headers={"X-HTTP-Method-Override": "DELETE", "X-Method-Override": "GET"},
    )

    assert response.status_code == 200


def test_no_cors_permission_is_granted_to_other_sites(client, user):
    preflight = client.options(
        "/auth/login",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    actual = client.post(
        "/auth/login",
        json={"username": "ann", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )

    for response in (preflight, actual):
        assert "access-control-allow-origin" not in response.headers
        assert "access-control-allow-credentials" not in response.headers


def test_error_pages_do_not_reveal_the_stack_or_the_server_internals(client, user):
    for response in (
        client.post("/auth/login", content=b"{", headers={"Content-Type": "application/json"}),
        client.get("/no/such/page"),
        client.get("/books/abc", headers=auth_headers(user)),
    ):
        text = response.text
        assert (
            "Traceback" not in text
            and "sqlalchemy" not in text.lower()
            and "psycopg" not in text.lower()
        )
        assert "argon2" not in text.lower() and "jwt" not in text.lower()


def auth_headers(user) -> dict:
    return auth(user)


# ---------- a documented limitation ----------


def test_known_limitation_an_access_token_stays_valid_after_logout_until_it_expires(client, user):
    """Characterisation, not an endorsement. Access tokens are stateless and live 15 minutes; logout revokes the
    REFRESH token (no new access token can be obtained) but cannot recall one already issued. If this test starts
    failing because the limitation was removed (a token deny-list), delete or invert it on purpose."""
    access = login(client).json()["access_token"]
    client.post("/auth/logout")

    still_valid = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    cannot_renew = client.post("/auth/refresh")

    assert still_valid.status_code == 200
    assert cannot_renew.status_code == 401


def test_a_disabled_user_is_cut_off_at_once_despite_that_limitation(client, db, user):
    """The limitation above does not apply to disabling or demoting: the user is looked up on every request."""
    access = login(client).json()["access_token"]
    user.is_active = False
    db.commit()

    assert client.get("/auth/me", headers={"Authorization": f"Bearer {access}"}).status_code == 401
