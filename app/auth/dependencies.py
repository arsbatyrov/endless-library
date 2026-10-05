"""FastAPI dependencies that identify the caller from the `Authorization: Bearer <access token>` header (AUTH-006)."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.tokens import TokenError, get_user_for_token
from app.database import get_db
from app.models import User
from app.schemas import PathId

# auto_error=False: FastAPI's own answer for a missing header is 403; we want 401 with a Bearer challenge.
_bearer = HTTPBearer(auto_error=False)

# One text for every kind of token problem: the caller learns nothing about why a token was refused.
NOT_AUTHENTICATED = "Invalid or missing access token"
FORBIDDEN = "Not enough permissions"


def _authenticate(credentials: HTTPAuthorizationCredentials | None, db: Session) -> User:
    if credentials is None:
        raise _unauthorized()
    try:
        return get_user_for_token(db, credentials.credentials)
    except TokenError:
        raise _unauthorized() from None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """The signed-in user. Role and active flag come from the database, so a disabled user is refused at once."""
    return _authenticate(credentials, db)


ALL_ROLES = ("reader", "librarian", "admin")
STAFF_ROLES = ("librarian", "admin")


def require_roles(*allowed: str):
    """Dependency factory: only the listed roles pass. No/bad token gives 401, another role gives 403."""

    def dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: Session = Depends(get_db),
    ) -> User | None:
        user = _authenticate(credentials, db)
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=FORBIDDEN)
        return user

    return dependency


# Librarians and admins (user management; what each may do with which account is decided in the service).
require_staff = require_roles(*STAFF_ROLES)


def require_staff_or_own_reader_card(
    reader_id: PathId,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """Staff may open any reader card's data; a reader only the card their account is linked to (AUTH-008).

    A reader asking for somebody else's card gets 403 whether or not that card exists, so card numbers cannot be probed.
    The link (`reader_id`) is read from the database, not from the token.
    """
    user = _authenticate(credentials, db)
    if user.role in STAFF_ROLES or (user.role == "reader" and user.reader_id == reader_id):
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=FORBIDDEN)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=NOT_AUTHENTICATED,
        headers={"WWW-Authenticate": "Bearer"},
    )
