"""AUTH-003, criteria 1-3: issuing and verifying access tokens (JWT, HS256).

Pure logic. Time is injected (`now=`), so nothing sleeps. The tests include the classic attacks on JWT:
tampered content, a foreign signature, `alg: none`, and algorithm confusion.
"""

import base64
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth import tokens
from app.auth.tokens import (
    ACCESS_TOKEN_LIFETIME,
    TokenError,
    create_access_token,
    decode_access_token,
)

SECRET = "test-only-secret-not-for-production-0123456789abcdef"
NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)


def issued_now(user_id=7, role="librarian"):
    """A token issued at the real current time (so that the library's own expiry check sees it as fresh)."""
    return create_access_token(user_id, role)


def raw_claims(token: str) -> dict:
    return jwt.decode(
        token, SECRET, algorithms=["HS256"], options={"verify_exp": False, "verify_iat": False}
    )


def forge(payload: dict, key=SECRET, algorithm="HS256") -> str:
    return jwt.encode(payload, key, algorithm=algorithm)


def base_payload(**overrides) -> dict:
    now = datetime.now(UTC)
    payload = {
        "sub": "7",
        "role": "admin",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "jti": "abc",
    }
    payload.update(overrides)
    return {key: value for key, value in payload.items() if value is not None}


# ---------- criterion 1: what a token contains ----------


def test_token_contains_the_agreed_claims():
    token = create_access_token(7, "librarian", now=NOW)

    claims = raw_claims(token)
    assert set(claims) == {"sub", "role", "iat", "exp", "jti"}
    assert claims["sub"] == "7"  # JWT requires the subject to be a string
    assert claims["role"] == "librarian"
    assert claims["iat"] == int(NOW.timestamp())
    assert claims["jti"]


def test_token_expires_after_15_minutes():
    claims = raw_claims(create_access_token(7, "admin", now=NOW))

    assert claims["exp"] - claims["iat"] == 15 * 60
    assert ACCESS_TOKEN_LIFETIME == timedelta(minutes=15)


def test_token_is_signed_with_hs256():
    header = jwt.get_unverified_header(issued_now())

    assert header["alg"] == "HS256"
    assert header["typ"] == "JWT"


def test_every_token_has_its_own_id():
    first, second = issued_now(), issued_now()

    assert raw_claims(first)["jti"] != raw_claims(second)["jti"]
    assert first != second


def test_token_is_signed_with_the_secret_from_the_environment(monkeypatch):
    token = issued_now()

    jwt.decode(token, SECRET, algorithms=["HS256"])  # the configured secret verifies it
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "another-secret-another-secret-123456", algorithms=["HS256"])


def test_unknown_role_cannot_be_issued():
    with pytest.raises(ValueError):
        create_access_token(7, "superuser")


# ---------- criterion 2: a correct token ----------


def test_correct_token_gives_the_user_id():
    claims = decode_access_token(issued_now(user_id=42, role="reader"))

    assert claims.user_id == 42
    assert claims.role == "reader"


def test_token_is_valid_just_before_it_expires():
    issued = datetime.now(UTC) - ACCESS_TOKEN_LIFETIME + timedelta(seconds=30)

    assert decode_access_token(create_access_token(7, "admin", now=issued)).user_id == 7


# ---------- criterion 3: rejected tokens ----------


def test_expired_token_is_rejected():
    issued = datetime.now(UTC) - ACCESS_TOKEN_LIFETIME - timedelta(seconds=30)

    with pytest.raises(TokenError) as error:
        decode_access_token(create_access_token(7, "admin", now=issued))

    assert error.value.code == "expired"


def test_token_with_changed_content_is_rejected():
    """The attacker edits the payload (role -> admin) and keeps the old signature."""
    header, payload, signature = issued_now(role="reader").split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["role"] = "admin"
    edited = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()

    with pytest.raises(TokenError) as error:
        decode_access_token(f"{header}.{edited}.{signature}")

    assert error.value.code == "invalid"


def test_token_signed_with_another_key_is_rejected():
    token = forge(base_payload(), key="attacker-key-attacker-key-attacker-key")

    with pytest.raises(TokenError) as error:
        decode_access_token(token)

    assert error.value.code == "invalid"


def test_token_with_alg_none_is_rejected():
    """A token without a signature must never be accepted, whatever it claims."""
    token = jwt.encode(base_payload(), key=None, algorithm="none")

    with pytest.raises(TokenError):
        decode_access_token(token)


def test_token_signed_with_another_hmac_algorithm_is_rejected():
    """Only HS256 is accepted, even if the secret is right (protects against algorithm confusion)."""
    token = forge(base_payload(), algorithm="HS384")

    with pytest.raises(TokenError):
        decode_access_token(token)


@pytest.mark.parametrize("missing", ["sub", "exp", "iat", "jti", "role"])
def test_token_without_a_required_claim_is_rejected(missing):
    token = forge(base_payload(**{missing: None}))

    with pytest.raises(TokenError):
        decode_access_token(token)


@pytest.mark.parametrize("subject", ["abc", "", "1.5", "-"])
def test_token_with_a_subject_that_is_not_an_id_is_rejected(subject):
    with pytest.raises(TokenError):
        decode_access_token(forge(base_payload(sub=subject)))


def test_token_with_an_unknown_role_is_rejected():
    with pytest.raises(TokenError):
        decode_access_token(forge(base_payload(role="superuser")))


def test_token_issued_in_the_future_is_rejected():
    future = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())

    with pytest.raises(TokenError):
        decode_access_token(forge(base_payload(iat=future, exp=future + 900)))


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "....", "Bearer x", "x" * 5000])
def test_garbage_is_rejected_with_a_token_error(garbage):
    with pytest.raises(TokenError):
        decode_access_token(garbage)


def test_changing_the_secret_invalidates_issued_tokens(monkeypatch):
    token = issued_now()
    monkeypatch.setenv("JWT_SECRET", "a-completely-new-secret-0123456789abcdefgh")

    with pytest.raises(TokenError):
        decode_access_token(token)


def test_token_error_never_exposes_the_token_or_the_secret():
    token = forge(base_payload(), key="attacker-key-attacker-key-attacker-key")

    with pytest.raises(TokenError) as error:
        decode_access_token(token)

    assert token not in str(error.value)
    assert SECRET not in str(error.value)


def test_module_does_not_keep_the_secret_in_a_constant():
    """The secret is read from the environment at use time: no module-level copy that could go stale or leak."""
    assert not any(isinstance(value, str) and value == SECRET for value in vars(tokens).values())
