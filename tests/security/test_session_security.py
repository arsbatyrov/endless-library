"""AUTH-017, criteria 4 and 6: refresh-token theft detection, the cookie's protection and cross-origin requests.

Criterion 4: a replaced refresh token that is presented again means a copy exists somewhere it should not: 401 and every
token of that user is revoked (the legitimate owner included: they sign in again).
Criterion 6: the refresh cookie is HttpOnly, SameSite and scoped to its path; refresh and logout requests that come
from another origin (a browser sends Origin / Sec-Fetch-Site) are refused and change nothing.
"""

import pytest

from app.auth.refresh_tokens import COOKIE_NAME, hash_refresh_token
from app.models import RefreshToken
from tests.factories import make_user
from tests.security.conftest import PASSWORD

EVIL_ORIGINS = [
    "https://evil.example",
    "http://evil.example",
    "http://testserver.evil.example",
    "http://evil.example/testserver",
    "http://testserver@evil.example",
    "http://evil.example:80",
    "https://evil.example:8443",
    "null",
    "file://",
    "chrome-extension://abcdef",
    "http://",
    "garbage",
]


@pytest.fixture
def user(db):
    return make_user(db, role="librarian", username="ann", password=PASSWORD)


def login(client, username="ann", **kwargs):
    response = client.post(
        "/auth/login", json={"username": username, "password": PASSWORD}, **kwargs
    )
    assert response.status_code == 200
    return response


def current(client) -> str:
    return client.cookies.get(COOKIE_NAME)


def put_cookie(client, value: str) -> None:
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, value, path="/auth")


def row(db, token: str) -> RefreshToken:
    db.expire_all()
    return db.query(RefreshToken).filter_by(token_hash=hash_refresh_token(token)).one()


# ---------- criterion 4: reuse of a replaced refresh token ----------


def test_a_replaced_token_is_refused_and_everything_of_that_user_is_revoked(client, db, user):
    login(client)
    stolen = current(client)
    client.post("/auth/refresh")
    legitimate = current(client)

    put_cookie(client, stolen)
    response = client.post("/auth/refresh")

    assert response.status_code == 401
    assert row(db, stolen).revoked_at is not None
    assert row(db, legitimate).revoked_at is not None
    put_cookie(client, legitimate)
    assert client.post("/auth/refresh").status_code == 401


def test_the_thief_gets_nothing_from_a_replayed_token_not_even_an_access_token(client, user):
    login(client)
    stolen = current(client)
    client.post("/auth/refresh")

    put_cookie(client, stolen)
    response = client.post("/auth/refresh")

    assert response.status_code == 401
    assert "access_token" not in response.text
    # at most a deletion of the cookie, never a new token
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert not set_cookie or "max-age=0" in set_cookie


def test_the_owner_can_sign_in_again_after_a_theft_is_detected(client, user):
    login(client)
    stolen = current(client)
    client.post("/auth/refresh")
    put_cookie(client, stolen)
    client.post("/auth/refresh")

    client.cookies.clear()

    assert (
        client.post("/auth/login", json={"username": "ann", "password": PASSWORD}).status_code
        == 200
    )


def test_a_theft_of_one_user_does_not_end_the_sessions_of_another(client, db, user):
    other = make_user(db, role="admin", username="bob", password=PASSWORD)
    login(client, "bob")
    bobs = current(client)
    client.cookies.clear()
    login(client)
    stolen = current(client)
    client.post("/auth/refresh")
    put_cookie(client, stolen)

    client.post("/auth/refresh")

    assert row(db, bobs).revoked_at is None
    assert row(db, bobs).user_id == other.id


def test_every_device_of_the_user_is_signed_out_when_a_theft_is_detected(client, db, user):
    login(client)
    laptop = current(client)
    client.cookies.clear()
    login(client)
    phone = current(client)
    client.post("/auth/refresh")  # the laptop's token is replaced by a new one
    put_cookie(client, laptop)

    client.post("/auth/refresh")  # the replaced laptop token is replayed

    assert row(db, phone).revoked_at is not None


def test_a_logged_out_token_cannot_be_used_again(client, db, user):
    login(client)
    token = current(client)
    client.post("/auth/logout")

    put_cookie(client, token)

    assert client.post("/auth/refresh").status_code == 401


def test_a_token_from_before_a_password_change_cannot_be_used(client, db, user):
    access = login(client).json()["access_token"]
    old = current(client)
    client.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": "battery staple"},
        headers={"Authorization": f"Bearer {access}"},
    )

    put_cookie(client, old)

    assert client.post("/auth/refresh").status_code == 401


def test_each_login_issues_a_new_unguessable_token(client, user):
    values = []
    for _ in range(5):
        client.cookies.clear()
        login(client)
        values.append(current(client))

    assert len(set(values)) == 5
    assert all(len(v) >= 43 for v in values)
    assert all(v.replace("-", "").replace("_", "").isalnum() for v in values)


def test_the_database_never_holds_the_token_itself(client, db, user):
    login(client)
    token = current(client)
    db.expire_all()

    hashes = [r.token_hash for r in db.query(RefreshToken).all()]

    assert token not in hashes
    assert hash_refresh_token(token) in hashes
    assert all(len(h) == 64 for h in hashes)


# ---------- criterion 6: the cookie ----------


def cookie_header(response) -> str:
    return response.headers["set-cookie"]


def test_the_cookie_has_the_protective_flags_after_login_and_refresh(client, user):
    first = login(client)
    second = client.post("/auth/refresh")

    for header in (cookie_header(first), cookie_header(second)):
        lowered = header.lower()
        assert "httponly" in lowered
        assert "samesite=lax" in lowered
        assert "path=/auth" in lowered
        assert "max-age=604800" in lowered
        assert "domain=" not in lowered  # host-only: never shared with subdomains


def test_the_cookie_is_secure_behind_a_https_proxy_and_only_then(client, user):
    plain = login(client)
    client.cookies.clear()
    proxied = client.post(
        "/auth/login",
        json={"username": "ann", "password": PASSWORD},
        headers={"X-Forwarded-Proto": "https"},
    )
    client.cookies.clear()
    chain = client.post(
        "/auth/login",
        json={"username": "ann", "password": PASSWORD},
        headers={"X-Forwarded-Proto": "https, http"},
    )

    assert "secure" not in cookie_header(plain).lower().replace("samesite", "")
    assert "secure" in cookie_header(proxied).lower()
    assert "secure" in cookie_header(chain).lower()


def test_the_cookie_path_follows_the_public_prefix_so_it_is_not_sent_elsewhere(db, user):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app, root_path="/api") as proxied:
            response = proxied.post("/auth/login", json={"username": "ann", "password": PASSWORD})
    finally:
        app.dependency_overrides.clear()

    assert "path=/api/auth" in response.headers["set-cookie"].lower()


def test_the_cookie_is_not_sent_to_the_data_endpoints(client, user):
    """Path=/auth: a request for data must not carry the refresh token (the browser enforces the path)."""
    login(client)
    token = current(client)

    # a data endpoint does not treat a cookie as a credential at all
    assert client.get("/books", headers={"Cookie": f"{COOKIE_NAME}={token}"}).status_code == 401


def test_the_refresh_token_is_never_in_a_response_body(client, user):
    bodies = [
        login(client).text,
        client.post("/auth/refresh").text,
        client.post("/auth/logout").text,
    ]
    token = None
    for text in bodies:
        assert "refresh" not in text.lower()
        assert token is None or token not in text


def test_logout_clears_the_cookie_with_the_same_protective_flags(client, user):
    login(client)

    header = cookie_header(client.post("/auth/logout")).lower()

    assert "max-age=0" in header
    assert "httponly" in header and "path=/auth" in header and "samesite=lax" in header


# ---------- criterion 6: requests from another origin ----------


@pytest.mark.parametrize("origin", EVIL_ORIGINS)
def test_refresh_from_another_origin_is_refused_and_changes_nothing(client, db, user, origin):
    login(client)
    token = current(client)

    response = client.post("/auth/refresh", headers={"Origin": origin})

    assert response.status_code == 403
    assert "access_token" not in response.text
    assert "set-cookie" not in response.headers  # not rotated, not even cleared
    assert row(db, token).revoked_at is None
    assert db.query(RefreshToken).count() == 1


@pytest.mark.parametrize("origin", EVIL_ORIGINS)
def test_logout_from_another_origin_is_refused_and_changes_nothing(client, db, user, origin):
    login(client)
    token = current(client)

    response = client.post("/auth/logout", headers={"Origin": origin})

    assert response.status_code == 403
    assert "set-cookie" not in response.headers
    assert row(db, token).revoked_at is None


@pytest.mark.parametrize("site", ["cross-site", "same-site", "Cross-Site", "unknown", ""])
def test_a_browser_that_says_the_request_is_not_same_origin_is_refused(client, db, user, site):
    login(client)
    token = current(client)

    refresh = client.post("/auth/refresh", headers={"Sec-Fetch-Site": site})
    logout = client.post("/auth/logout", headers={"Sec-Fetch-Site": site})

    assert (refresh.status_code, logout.status_code) == (403, 403)
    assert row(db, token).revoked_at is None


def test_sec_fetch_site_wins_over_a_matching_origin(client, db, user):
    login(client)

    response = client.post(
        "/auth/refresh", headers={"Sec-Fetch-Site": "cross-site", "Origin": "http://testserver"}
    )

    assert response.status_code == 403


@pytest.mark.parametrize("site", ["same-origin", "none", "SAME-ORIGIN"])
def test_a_same_origin_browser_request_works(client, user, site):
    login(client)

    assert client.post("/auth/refresh", headers={"Sec-Fetch-Site": site}).status_code == 200
    assert client.post("/auth/logout", headers={"Sec-Fetch-Site": site}).status_code == 204


def test_a_request_from_the_site_itself_works_by_its_origin_header(client, user):
    login(client)

    refresh = client.post("/auth/refresh", headers={"Origin": "http://testserver"})
    logout = client.post("/auth/logout", headers={"Origin": "http://testserver"})

    assert (refresh.status_code, logout.status_code) == (200, 204)


def test_behind_the_proxy_the_public_host_counts_not_the_internal_one(client, user):
    login(client)

    ok = client.post(
        "/auth/refresh",
        headers={"Origin": "https://library.example", "X-Forwarded-Host": "library.example"},
    )
    bad = client.post(
        "/auth/refresh",
        headers={"Origin": "https://evil.example", "X-Forwarded-Host": "library.example"},
    )

    assert (ok.status_code, bad.status_code) == (200, 403)


def test_clients_that_are_not_browsers_send_neither_header_and_still_work(client, user):
    """curl, the tests and the mobile app send no Origin: the cookie-riding attack needs a browser."""
    login(client)

    assert client.post("/auth/refresh").status_code == 200


def test_a_refused_cross_origin_request_is_documented_in_the_contract(client):
    spec = client.get("/openapi.json").json()

    for path in ("/auth/refresh", "/auth/logout"):
        assert "403" in spec["paths"][path]["post"]["responses"], path


def test_the_refusal_does_not_reveal_whether_the_cookie_was_valid(client, db, user):
    login(client)
    valid = client.post("/auth/refresh", headers={"Origin": "https://evil.example"})
    client.cookies.clear()
    missing = client.post("/auth/refresh", headers={"Origin": "https://evil.example"})
    client.cookies.set(COOKIE_NAME, "garbage", path="/auth")
    garbage = client.post("/auth/refresh", headers={"Origin": "https://evil.example"})

    assert {(r.status_code, r.text) for r in (valid, missing, garbage)} == {
        (403, '{"detail":"Cross-origin request refused"}')
    }


# ---------- tokens and caches ----------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/auth/login"),
        ("POST", "/auth/refresh"),
        ("POST", "/auth/logout"),
        ("GET", "/auth/me"),
    ],
)
def test_responses_with_tokens_or_identity_are_never_cached(client, user, method, path):
    access = login(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {access}"} if path == "/auth/me" else {}
    body = {"username": "ann", "password": PASSWORD} if path == "/auth/login" else None

    response = client.request(method, path, json=body, headers=headers)

    assert "no-store" in response.headers["cache-control"].lower()
    assert response.headers.get("pragma", "").lower() == "no-cache"


def test_failed_sign_ins_are_not_cached_either(client, user):
    response = client.post("/auth/login", json={"username": "ann", "password": "wrong password"})

    assert "no-store" in response.headers["cache-control"].lower()
