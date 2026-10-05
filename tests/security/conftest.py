"""AUTH-017: fixtures and helpers of the security suite (negative checks of sign-in, tokens and rights).

Every test here starts WITHOUT a login (the attacker's point of view) and builds the accounts and tokens it needs.
Run only this suite with: pytest -m security
"""

import base64
import hashlib
import hmac
import io
import json
import logging
import time

import jwt
import pytest

from app.auth.config import load_jwt_secret
from app.auth.tokens import create_access_token
from app.logging_config import JsonFormatter
from tests.factories import make_reader, make_user

PASSWORD = "correct horse"

# The only operations that need no bearer token (see tests/contract/test_security_contract.py).
OPEN_OPERATIONS = {
    ("GET", "/health"),
    ("GET", "/ready"),
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/logout"),
}
UNKNOWN_ID = "999999"


@pytest.fixture
def client(anonymous_client):
    """The attacker: no token, no cookie."""
    return anonymous_client


def bearer(token: str) -> dict:
    value = f"Bearer {token}"
    # the HTTP client cannot send a non-ASCII header as text; an attacker can send any bytes
    return {"Authorization": value if value.isascii() else value.encode("utf-8")}


def token_for(user) -> str:
    return create_access_token(user.id, user.role)


def auth(user) -> dict:
    return bearer(token_for(user))


@pytest.fixture
def admin(db):
    return make_user(db, role="admin", username="root", password=PASSWORD)


@pytest.fixture
def librarian(db):
    return make_user(db, role="librarian", username="lib", password=PASSWORD)


@pytest.fixture
def reader_account(db):
    return make_user(db, role="reader", username="rita", password=PASSWORD)


@pytest.fixture
def other_reader_card(db):
    return make_reader(db, name="Somebody else")


def b64(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def b64decode(part: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def manual_hs256(claims: dict, key: bytes) -> str:
    """An HS256 token built by hand: PyJWT refuses to sign with some keys (an empty one), an attacker would not."""
    head = f"{b64({'alg': 'HS256', 'typ': 'JWT'})}.{b64(claims)}"
    signature = hmac.new(key, head.encode(), hashlib.sha256).digest()
    return f"{head}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def secret() -> str:
    return load_jwt_secret()


def claims_for(user, **overrides) -> dict:
    now = int(
        time.time()
    )  # real time: claims with an `iat` in the future would be refused for THAT reason
    claims = {
        "sub": str(user.id),
        "role": user.role,
        "iat": now - 60,
        "exp": now + 900,
        "jti": "t1",
    }
    claims.update(overrides)
    return claims


def operations(spec: dict):
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            yield method.upper(), path, operation


def protected_operations(spec: dict) -> list[tuple[str, str]]:
    return [(m, p) for m, p, _ in operations(spec) if (m, p) not in OPEN_OPERATIONS]


def concrete_path(path: str) -> str:
    out = path
    while "{" in out:
        start, end = out.index("{"), out.index("}")
        out = out[:start] + UNKNOWN_ID + out[end + 1 :]
    return out


def send(client, method: str, path: str, headers: dict | None = None):
    body = {} if method in ("POST", "PUT", "PATCH") else None
    return client.request(method, concrete_path(path), json=body, headers=headers or {})


@pytest.fixture
def json_logs():
    """Captures everything the application logs, as the JSON lines it really writes (with the request id)."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("endless_library")
    logger.addHandler(handler)

    def lines() -> list[dict]:
        return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]

    lines.raw = stream.getvalue
    yield lines
    logger.removeHandler(handler)


__all__ = ["jwt"]
