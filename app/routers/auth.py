from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.refresh_tokens import (
    COOKIE_NAME,
    REFRESH_TOKEN_LIFETIME,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.auth.tokens import ACCESS_TOKEN_LIFETIME, create_access_token
from app.database import get_db
from app.openapi_responses import BAD_REQUEST, UNAUTHORIZED
from app.schemas import LoginRequest, LoginResponse
from app.services.auth import authenticate

router = APIRouter(prefix="/auth", tags=["auth"])

# One text for every kind of failure (wrong password, unknown login, disabled account): the answer must not reveal
# which logins exist.
INVALID_CREDENTIALS = "Invalid username or password"
INVALID_REFRESH_TOKEN = "Invalid or expired refresh token"

_LOGIN_RESPONSES = {
    **BAD_REQUEST,
    **UNAUTHORIZED,
    200: {
        "description": "Signed in. The access token is in the body; the refresh token is set as an httpOnly cookie.",
        "headers": {
            "Set-Cookie": {
                "description": "refresh_token cookie (HttpOnly, SameSite=Lax, 7 days)",
                "schema": {"type": "string"},
            }
        },
    },
}


def _is_https(request: Request) -> bool:
    """Behind a proxy that terminates TLS the original scheme arrives in X-Forwarded-Proto."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    return scheme.split(",")[0].strip().lower() == "https"


def _cookie_path(request: Request) -> str:
    """The cookie must be sent back to the PUBLIC address of the auth endpoints: behind nginx that is /api/auth."""
    return f"{request.scope.get('root_path', '').rstrip('/')}/auth"


def _set_refresh_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=int(REFRESH_TOKEN_LIFETIME.total_seconds()),
        path=_cookie_path(request),
        httponly=True,  # JavaScript on the page cannot read it
        samesite="lax",
        secure=_is_https(request),
    )


def _clear_refresh_cookie(response: Response, request: Request) -> None:
    # A cookie is removed only when path (and flags) match the ones it was set with.
    response.delete_cookie(
        key=COOKIE_NAME,
        path=_cookie_path(request),
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
    )


@router.post("/login", response_model=LoginResponse, responses=_LOGIN_RESPONSES)
def login(data: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = authenticate(db, data.username, data.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

    refresh_token = issue_refresh_token(db, user)
    user.last_login_at = datetime.now(UTC)
    db.commit()

    _set_refresh_cookie(response, request, refresh_token)
    return LoginResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
    )


_REFRESH_RESPONSES = {
    **UNAUTHORIZED,
    200: {
        "description": "New access token in the body; the refresh token is replaced (rotation) via Set-Cookie.",
        "headers": {
            "Set-Cookie": {"description": "new refresh_token cookie", "schema": {"type": "string"}}
        },
    },
}


@router.post("/refresh", response_model=LoginResponse, responses=_REFRESH_RESPONSES)
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    """Exchange the refresh cookie for a new access token. The old refresh token stops working."""
    rotated = rotate_refresh_token(db, refresh_token) if refresh_token else None
    if rotated is None:
        failure = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": INVALID_REFRESH_TOKEN}
        )
        _clear_refresh_cookie(failure, request)
        return failure

    user, new_token = rotated
    _set_refresh_cookie(response, request, new_token)
    return LoginResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def logout(
    request: Request,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    """End this session: revoke the refresh token and clear the cookie. Safe to repeat."""
    if refresh_token:
        revoke_refresh_token(db, refresh_token)
    done = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(done, request)
    return done
