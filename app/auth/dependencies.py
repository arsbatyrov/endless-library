"""FastAPI dependencies that identify the caller from the `Authorization: Bearer <access token>` header (AUTH-006)."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.config import auth_required
from app.auth.tokens import TokenError, get_user_for_token
from app.database import get_db
from app.models import User

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
    """Dependency factory: only the listed roles pass. No/bad token gives 401, another role gives 403.

    While the temporary AUTH_REQUIRED switch is off (see app.auth.config.auth_required) everything passes.
    """

    def dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: Session = Depends(get_db),
    ) -> User | None:
        if not auth_required():
            return None
        user = _authenticate(credentials, db)
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=FORBIDDEN)
        return user

    return dependency


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=NOT_AUTHENTICATED,
        headers={"WWW-Authenticate": "Bearer"},
    )
