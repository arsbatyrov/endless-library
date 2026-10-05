"""Access tokens: issuing and verifying JWT (AUTH-003).

A token is a signed statement "this is user N with role R, valid until time T". The server trusts it only because the
signature can be checked with the secret that only the server knows.

Rules in this module:
- only HS256 is accepted (the verifier is told the algorithm; the algorithm written inside a token is never trusted,
  which is what stops `alg: none` and algorithm-confusion attacks);
- every claim we rely on is required (sub, role, iat, exp, jti);
- the secret is read from the environment at the moment of use (no module-level copy);
- a token only says who the user was at login. What the user may do now is decided from the database
  (`get_user_for_token`): a disabled or demoted user loses access immediately, not when the token expires.

Time is injectable (`now=`) so tests need no sleeping.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy.orm import Session

from app.auth.config import load_jwt_secret
from app.models import User

ALGORITHM = "HS256"
MAX_USER_ID = 2**31 - 1  # the largest id the database stores (a 32-bit integer)
ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
ROLES = ("reader", "librarian", "admin")
REQUIRED_CLAIMS = ["sub", "role", "iat", "exp", "jti"]


class TokenError(Exception):
    """The token cannot be used. `code` is a stable reason: expired, invalid, user_not_found, user_inactive.

    The message deliberately never contains the token or the secret.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AccessClaims:
    user_id: int
    role: str
    issued_at: datetime
    expires_at: datetime
    token_id: str


def create_access_token(user_id: int, role: str, now: datetime | None = None) -> str:
    """Issue a signed access token valid for 15 minutes."""
    if role not in ROLES:
        raise ValueError(f"Unknown role: {role!r}")
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),  # JWT requires the subject to be a string
        "role": role,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + ACCESS_TOKEN_LIFETIME).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, load_jwt_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> AccessClaims:
    """Verify signature, algorithm, expiry and required claims; return the claims or raise TokenError."""
    try:
        payload = jwt.decode(
            token,
            load_jwt_secret(),
            algorithms=[ALGORITHM],
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.ExpiredSignatureError:
        raise TokenError("expired", "The token has expired") from None
    except jwt.PyJWTError:
        raise TokenError("invalid", "The token is not valid") from None

    try:
        user_id = int(payload["sub"])
        # An id outside the database's integer range can match no user, and asking the database for it would crash.
        if not 1 <= user_id <= MAX_USER_ID:
            raise ValueError("subject out of range")
        issued_at = datetime.fromtimestamp(payload["iat"], UTC)
        expires_at = datetime.fromtimestamp(payload["exp"], UTC)
    except (ValueError, TypeError, OverflowError, OSError):
        raise TokenError("invalid", "The token is not valid") from None
    if payload["role"] not in ROLES:
        raise TokenError("invalid", "The token is not valid")
    return AccessClaims(
        user_id=user_id,
        role=payload["role"],
        issued_at=issued_at,
        expires_at=expires_at,
        token_id=payload["jti"],
    )


def get_user_for_token(db: Session, token: str) -> User:
    """The user a valid token belongs to, **as the database knows them now**.

    The role and the active flag come from the database, not from the token: a user disabled or demoted after login
    loses the rights at once. Raises TokenError for a bad token, a deleted user or a disabled user.
    """
    claims = decode_access_token(token)
    user = db.get(User, claims.user_id)
    if user is None:
        raise TokenError("user_not_found", "The user of this token no longer exists")
    if not user.is_active:
        raise TokenError("user_inactive", "The user of this token is disabled")
    return user
