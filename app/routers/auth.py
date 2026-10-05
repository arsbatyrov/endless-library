from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.refresh_tokens import COOKIE_NAME, REFRESH_TOKEN_LIFETIME, issue_refresh_token
from app.auth.tokens import ACCESS_TOKEN_LIFETIME, create_access_token
from app.database import get_db
from app.openapi_responses import BAD_REQUEST, UNAUTHORIZED
from app.schemas import LoginRequest, LoginResponse
from app.services.auth import authenticate

router = APIRouter(prefix="/auth", tags=["auth"])

# One text for every kind of failure (wrong password, unknown login, disabled account): the answer must not reveal
# which logins exist.
INVALID_CREDENTIALS = "Invalid username or password"

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


@router.post("/login", response_model=LoginResponse, responses=_LOGIN_RESPONSES)
def login(data: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = authenticate(db, data.username, data.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

    refresh_token = issue_refresh_token(db, user)
    user.last_login_at = datetime.now(UTC)
    db.commit()

    # The cookie must be sent back to the PUBLIC address of the auth endpoints: behind nginx that is /api/auth.
    root_path = request.scope.get("root_path", "").rstrip("/")
    response.set_cookie(
        key=COOKIE_NAME,
        value=refresh_token,
        max_age=int(REFRESH_TOKEN_LIFETIME.total_seconds()),
        path=f"{root_path}/auth",
        httponly=True,  # JavaScript on the page cannot read it
        samesite="lax",
        secure=_is_https(request),
    )
    return LoginResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
    )
