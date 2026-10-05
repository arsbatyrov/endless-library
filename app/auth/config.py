"""Authentication settings (AUTH-003).

The JWT secret signs every access token. Whoever knows it can forge a token for any user, so there is **no fallback
value**: if the secret is missing or weak, the application refuses to start and says how to fix it.
"""

import os
from collections.abc import Mapping

MIN_SECRET_BYTES = 32


class AuthConfigError(RuntimeError):
    """The authentication configuration is missing or unsafe."""


_HOW_TO_FIX = (
    'Generate one with: python -c "import secrets; print(secrets.token_hex(32))" '
    "and set it as JWT_SECRET (in .env for local runs, in a Secret in Kubernetes)."
)


def load_jwt_secret(environ: Mapping[str, str] | None = None) -> str:
    """Return the JWT secret from the environment or raise AuthConfigError. The message never contains the secret itself."""
    environ = os.environ if environ is None else environ
    secret = environ.get("JWT_SECRET", "")
    if not secret:
        raise AuthConfigError(f"JWT_SECRET is not set. {_HOW_TO_FIX}")
    if len(secret.encode("utf-8")) < MIN_SECRET_BYTES:
        raise AuthConfigError(
            f"JWT_SECRET is too short: it must be at least {MIN_SECRET_BYTES} bytes. {_HOW_TO_FIX}"
        )
    return secret
