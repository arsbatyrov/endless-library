from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.events import (
    record_login,
    record_logout,
    record_password_changed,
    record_refresh,
)
from app.auth.login_guard import login_guard
from app.auth.passwords import (
    PasswordPolicyError,
    hash_password,
    validate_password_policy,
    verify_password,
)
from app.auth.refresh_tokens import (
    COOKIE_NAME,
    REFRESH_TOKEN_LIFETIME,
    issue_refresh_token,
    revoke_all_refresh_tokens,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.auth.tokens import ACCESS_TOKEN_LIFETIME, create_access_token
from app.database import get_db
from app.models import User
from app.openapi_responses import BAD_REQUEST, UNAUTHORIZED
from app.schemas import (
    ErrorResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    PasswordChangeRequest,
)
from app.services.auth import authenticate

router = APIRouter(prefix="/auth", tags=["auth"])

# One text for every kind of failure (wrong password, unknown login, disabled account): the answer must not reveal
# which logins exist.
INVALID_CREDENTIALS = "Invalid username or password"
TOO_MANY_ATTEMPTS = "Too many failed login attempts. Try again later."
INVALID_REFRESH_TOKEN = "Invalid or expired refresh token"
WRONG_CURRENT_PASSWORD = "Current password is incorrect"

_LOGIN_RESPONSES = {
    **BAD_REQUEST,
    **UNAUTHORIZED,
    429: {
        "model": ErrorResponse,
        "description": "Too many failed attempts for this login; wait for Retry-After seconds",
        "headers": {
            "Retry-After": {
                "description": "Seconds until the login can be tried again",
                "schema": {"type": "integer"},
            }
        },
    },
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
    # Locked logins are refused before the password is even looked at (it would cost a hash for nothing).
    wait = login_guard.check(data.username)
    if wait is not None:
        record_login("locked", data.username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=TOO_MANY_ATTEMPTS,
            headers={"Retry-After": str(wait)},
        )

    user = authenticate(db, data.username, data.password)
    if user is None:
        login_guard.record_failure(data.username)
        record_login("failure", data.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)
    login_guard.reset(data.username)

    refresh_token = issue_refresh_token(db, user)
    user.last_login_at = datetime.now(UTC)
    db.commit()
    record_login("success", data.username, user)

    _set_refresh_cookie(response, request, refresh_token)
    return LoginResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
    )


_CLEARS_COOKIE = {
    "Set-Cookie": {
        "description": "refresh_token cookie cleared (Max-Age=0), with the same path it was set with",
        "schema": {"type": "string"},
    }
}

_REFRESH_RESPONSES = {
    401: {**UNAUTHORIZED[401], "headers": _CLEARS_COOKIE},
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
        record_refresh("rejected")
        failure = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": INVALID_REFRESH_TOKEN}
        )
        _clear_refresh_cookie(failure, request)
        return failure

    user, new_token = rotated
    record_refresh("ok", user)
    _set_refresh_cookie(response, request, new_token)
    return LoginResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        204: {"description": "Signed out; the cookie is cleared.", "headers": _CLEARS_COOKIE}
    },
)
def logout(
    request: Request,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    """End this session: revoke the refresh token and clear the cookie. Safe to repeat."""
    if refresh_token:
        revoke_refresh_token(db, refresh_token)
    record_logout()
    done = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(done, request)
    return done


def _password_error(message: str) -> list[dict]:
    """A 422 in the same shape as request-validation errors, so clients handle one format."""
    return [{"type": "password_policy", "loc": ["body", "new_password"], "msg": message}]


@router.get("/me", response_model=MeResponse, responses=UNAUTHORIZED)
def me(user: User = Depends(get_current_user)):
    return MeResponse(id=user.id, username=user.username, role=user.role, reader_id=user.reader_id)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        **BAD_REQUEST,
        **UNAUTHORIZED,
        204: {
            "description": "Password changed; every session is ended and the cookie is cleared.",
            "headers": _CLEARS_COOKIE,
        },
    },
)
def change_password(
    data: PasswordChangeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the caller's own password. All refresh tokens are revoked, so every session must sign in again."""
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=WRONG_CURRENT_PASSWORD)
    try:
        validate_password_policy(data.new_password, user.username)
    except PasswordPolicyError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from None
    if verify_password(data.new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_password_error("New password must differ from the current one"),
        )

    user.password_hash = hash_password(data.new_password)
    revoke_all_refresh_tokens(db, user.id)  # commits together with the new hash
    record_password_changed(user)
    done = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(done, request)
    return done
