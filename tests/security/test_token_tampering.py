"""AUTH-017, criterion 1: a forged, altered, unsigned or expired access token is always refused with 401.

Every variant is tried against EVERY protected operation (taken from the OpenAPI schema), so a new endpoint that forgets
the check is caught here as well. The answer must be exactly 401: never 200 (accepted), 403 (the token was believed) or
500 (the server crashed on it).
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.tokens import create_access_token
from tests.security.conftest import (
    PASSWORD,
    b64,
    b64decode,
    bearer,
    claims_for,
    manual_hs256,
    protected_operations,
    secret,
    send,
    token_for,
)

OTHER_KEY = "another-secret-that-is-long-enough-0123456789abcdef"


@pytest.fixture
def spec(client):
    return client.get("/openapi.json").json()


def forged_tokens(reader, admin) -> dict[str, str]:
    """name -> token. `reader` is a real reader account, `admin` a real administrator."""
    good = token_for(reader)
    header, payload, signature = good.split(".")
    claims = b64decode(payload)

    def with_payload(**changes) -> str:
        return f"{header}.{b64({**claims, **changes})}.{signature}"

    far = 4_000_000_000
    return {
        # the body was changed, the old signature kept
        "role raised to admin, signature kept": with_payload(role="admin"),
        "subject changed to the admin, signature kept": with_payload(sub=str(admin.id)),
        "expiry extended, signature kept": with_payload(exp=far),
        # signed with a key the server does not know
        "signed with another key": jwt.encode(claims_for(reader), OTHER_KEY, algorithm="HS256"),
        "admin claims signed with another key": jwt.encode(
            claims_for(admin), OTHER_KEY, algorithm="HS256"
        ),
        "empty key": manual_hs256(claims_for(admin), b""),
        "key of one zero byte": manual_hs256(claims_for(admin), b"\x00"),
        # unsigned: the `alg: none` attack, in the spellings parsers accept
        "alg none": jwt.encode(claims_for(admin), None, algorithm="none"),
        "alg None": f"{b64({'alg': 'None', 'typ': 'JWT'})}.{b64(claims_for(admin))}.",
        "alg NONE": f"{b64({'alg': 'NONE', 'typ': 'JWT'})}.{b64(claims_for(admin))}.",
        "alg none with a signature part": f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims_for(admin))}.AAAA",
        # algorithm confusion: other algorithms, even signed with the REAL key, are not accepted
        "HS384 signed with the real key": jwt.encode(
            claims_for(admin), secret(), algorithm="HS384"
        ),
        "HS512 signed with the real key": jwt.encode(
            claims_for(admin), secret(), algorithm="HS512"
        ),
        "RS256 header with a made-up signature": f"{b64({'alg': 'RS256', 'typ': 'JWT'})}.{b64(claims_for(admin))}.AAAA",
        "ES256 header with a made-up signature": f"{b64({'alg': 'ES256', 'typ': 'JWT'})}.{b64(claims_for(admin))}.AAAA",
        # headers that make some libraries fetch or trust a key from somewhere else
        "jku header": jwt.encode(
            claims_for(admin),
            OTHER_KEY,
            algorithm="HS256",
            headers={"jku": "https://evil.example/keys.json"},
        ),
        "x5u header": jwt.encode(
            claims_for(admin),
            OTHER_KEY,
            algorithm="HS256",
            headers={"x5u": "https://evil.example/cert.pem"},
        ),
        "kid path traversal": jwt.encode(
            claims_for(admin), OTHER_KEY, algorithm="HS256", headers={"kid": "../../../../dev/null"}
        ),
        # expired
        "expired seconds ago": create_access_token(
            reader.id, reader.role, now=datetime.now(UTC) - timedelta(minutes=15, seconds=5)
        ),
        "expired long ago": jwt.encode(
            claims_for(reader, exp=1_000_000_000, iat=999_999_000), secret(), algorithm="HS256"
        ),
        # claims the server requires are missing (so a token minted without them is useless)
        "no exp": jwt.encode(
            {k: v for k, v in claims_for(reader).items() if k != "exp"}, secret(), algorithm="HS256"
        ),
        "no iat": jwt.encode(
            {k: v for k, v in claims_for(reader).items() if k != "iat"}, secret(), algorithm="HS256"
        ),
        "no jti": jwt.encode(
            {k: v for k, v in claims_for(reader).items() if k != "jti"}, secret(), algorithm="HS256"
        ),
        "no sub": jwt.encode(
            {k: v for k, v in claims_for(reader).items() if k != "sub"}, secret(), algorithm="HS256"
        ),
        "no role": jwt.encode(
            {k: v for k, v in claims_for(reader).items() if k != "role"},
            secret(),
            algorithm="HS256",
        ),
        # the claims are there but make no sense
        "unknown role": jwt.encode(
            claims_for(reader, role="superuser"), secret(), algorithm="HS256"
        ),
        "subject is not a number": jwt.encode(
            claims_for(reader, sub="admin"), secret(), algorithm="HS256"
        ),
        "subject is zero": jwt.encode(claims_for(reader, sub="0"), secret(), algorithm="HS256"),
        "subject is negative": jwt.encode(
            claims_for(reader, sub="-1"), secret(), algorithm="HS256"
        ),
        "subject is huge": jwt.encode(
            claims_for(reader, sub="9" * 40), secret(), algorithm="HS256"
        ),
        "subject is a float": jwt.encode(
            claims_for(reader, sub="1.5"), secret(), algorithm="HS256"
        ),
        "subject of a user that does not exist": jwt.encode(
            claims_for(reader, sub="888888"), secret(), algorithm="HS256"
        ),
        "expiry is a string": jwt.encode(
            claims_for(reader, exp="never"), secret(), algorithm="HS256"
        ),
        # not a JWT at all, or damaged
        "truncated": good[:-3],
        "signature removed": f"{header}.{payload}.",
        "signature of a different token": f"{header}.{payload}.{token_for(admin).split('.')[2]}",
        "an extra segment": f"{good}.AAAA",
        "only two segments": f"{header}.{payload}",
        "empty segments": "..",
        "garbage": "not-a-token",
        "base64 noise": "A" * 300,
        "non-ASCII": "tökén.ünïcode.sïgnature",
        "very long": "a." * 20000 + "a",
    }


def test_the_variants_are_not_accidentally_valid(reader_account, admin):
    """Guards the test itself: the untouched token works, so a 401 below really comes from the alteration."""
    from app.auth.tokens import decode_access_token

    assert decode_access_token(token_for(reader_account)).user_id == reader_account.id


def test_a_well_formed_token_built_the_same_way_is_accepted(client, reader_account):
    """Guards the forged variants: their claims come from the same builder, so a 401 below is caused by the forgery."""
    good = jwt.encode(claims_for(reader_account), secret(), algorithm="HS256")

    assert client.get("/auth/me", headers=bearer(good)).status_code == 200


def test_every_forged_token_is_refused_on_every_protected_operation(
    client, spec, reader_account, admin
):
    operations = protected_operations(spec)
    assert len(operations) >= 20
    failures = []

    for name, token in forged_tokens(reader_account, admin).items():
        for method, path in operations:
            response = send(client, method, path, bearer(token))
            if response.status_code != 401:
                failures.append(f"{name}: {method} {path} -> {response.status_code}")

    assert failures == []


def test_a_forged_token_never_changes_data(client, db, spec, reader_account, admin):
    from app.models import Book, Reader, User

    before = (db.query(Book).count(), db.query(Reader).count(), db.query(User).count())

    for token in forged_tokens(reader_account, admin).values():
        for method, path in protected_operations(spec):
            send(client, method, path, bearer(token))

    db.expire_all()
    assert (db.query(Book).count(), db.query(Reader).count(), db.query(User).count()) == before


def test_a_refused_token_answers_look_the_same_whatever_the_reason(client, reader_account, admin):
    bodies = set()
    for token in forged_tokens(reader_account, admin).values():
        response = client.get("/auth/me", headers=bearer(token))
        bodies.add((response.status_code, response.text, response.headers.get("www-authenticate")))

    assert bodies == {(401, '{"detail":"Invalid or missing access token"}', "Bearer")}


# ---------- the header itself ----------


@pytest.mark.parametrize(
    "header",
    [
        "",
        "Bearer",
        "Bearer ",
        "bearer",
        "Basic dXNlcjpwYXNz",
        "Digest abc",
        "Token abc",
        "Bearer  ",
        "Bearer a b c",
        "Bearer\ttoken",
        "BearerXtoken",
        "Bearer: token",
    ],
)
def test_malformed_authorization_headers_are_refused(client, header):
    assert client.get("/books", headers={"Authorization": header}).status_code == 401


def test_the_token_is_not_accepted_from_a_query_string_cookie_or_body(client, admin):
    token = token_for(admin)

    assert client.get(f"/books?access_token={token}").status_code == 401
    assert client.get(f"/books?token={token}").status_code == 401
    assert client.get("/books", headers={"Cookie": f"access_token={token}"}).status_code == 401
    assert client.get("/books", headers={"X-Access-Token": token}).status_code == 401
    assert client.get("/books", headers={"X-Auth-Token": token}).status_code == 401


def test_the_refresh_cookie_is_not_an_access_token(client, librarian):
    client.post("/auth/login", json={"username": "lib", "password": PASSWORD})
    refresh_value = client.cookies.get("refresh_token")

    assert client.get("/books", headers=bearer(refresh_value)).status_code == 401


def test_an_access_token_is_not_a_refresh_token(client, librarian):
    client.cookies.set("refresh_token", token_for(librarian), path="/auth")

    assert client.post("/auth/refresh").status_code == 401
