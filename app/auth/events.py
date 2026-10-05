"""Sign-in events (AUTH-016): every event is counted in Prometheus and written to the log, in one place.

What is deliberately NOT here: a password, an access or refresh token, a cookie, a password hash. And for a FAILED
sign-in not even the login: people often type their password into the login field, so the login of a failed attempt
would put passwords into the log. A failed or locked attempt carries `login_hash` instead, the first 12 hex characters
of a SHA-256 of the lower-cased login: enough to see that many attempts hit the same login, useless for anything else.
The id of the request (`request_id`) is added to every line by the log formatter.
"""

import hashlib
import logging

from app.metrics import AUTH_LOGINS, AUTH_REFRESH
from app.models import User

logger = logging.getLogger("endless_library.auth")


def login_hash(login: str) -> str:
    return hashlib.sha256(login.casefold().encode("utf-8")).hexdigest()[:12]


def record_login(result: str, login: str, user: User | None = None) -> None:
    """result: success, failure or locked."""
    AUTH_LOGINS.labels(result).inc()
    if user is not None:
        extra = {"event": "login", "result": result, "user_id": user.id, "role": user.role}
    else:
        extra = {"event": "login", "result": result, "login_hash": login_hash(login)}
    logger.log(
        logging.INFO if result == "success" else logging.WARNING, "login %s", result, extra=extra
    )


def record_refresh(result: str, user: User | None = None) -> None:
    """result: ok or rejected. A rejected refresh does not say who it was (the token may belong to nobody)."""
    AUTH_REFRESH.labels(result).inc()
    extra = {"event": "refresh", "result": result}
    if user is not None:
        extra["user_id"] = user.id
    logger.log(
        logging.INFO if result == "ok" else logging.WARNING, "refresh %s", result, extra=extra
    )


def record_logout() -> None:
    logger.info("logout", extra={"event": "logout", "result": "ok"})


def record_password_changed(user: User) -> None:
    logger.info(
        "password changed", extra={"event": "password_changed", "result": "ok", "user_id": user.id}
    )
