"""FastAPI dependencies that identify the caller from the `Authorization: Bearer <access token>` header (AUTH-006)."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.tokens import TokenError, get_user_for_token
from app.database import get_db
from app.models import User

# auto_error=False: FastAPI's own answer for a missing header is 403; we want 401 with a Bearer challenge.
_bearer = HTTPBearer(auto_error=False)

# One text for every kind of token problem: the caller learns nothing about why a token was refused.
NOT_AUTHENTICATED = "Invalid or missing access token"


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """The signed-in user. Role and active flag come from the database, so a disabled user is refused at once."""
    if credentials is None:
        raise _unauthorized()
    try:
        return get_user_for_token(db, credentials.credentials)
    except TokenError:
        raise _unauthorized() from None


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=NOT_AUTHENTICATED,
        headers={"WWW-Authenticate": "Bearer"},
    )
