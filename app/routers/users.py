from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_staff
from app.database import get_db
from app.models import User
from app.openapi_responses import BAD_REQUEST, CONFLICT, FORBIDDEN, NOT_FOUND, UNAUTHORIZED
from app.schemas import PasswordReset, PathId, UserCreate, UserRead, UserUpdate
from app.services import users as user_service

# Staff only (librarian, admin). Unlike the books/readers/loans routers this one ignores the temporary AUTH_REQUIRED
# switch: it needs to know who is calling. What each staff role may do with which account is decided in the service.
router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_staff)],
    responses={**UNAUTHORIZED, **FORBIDDEN},
)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST, **NOT_FOUND, **CONFLICT},
)
def create_user(
    data: UserCreate, actor: User = Depends(require_staff), db: Session = Depends(get_db)
):
    return user_service.create_user(db, actor, data)


@router.get("", response_model=list[UserRead])
def list_users(actor: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Admins see every account, librarians only reader accounts."""
    return user_service.list_users(db, actor)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    responses={**BAD_REQUEST, **NOT_FOUND, **CONFLICT},
)
def update_user(
    user_id: PathId,
    data: UserUpdate,
    actor: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """Disable or enable an account, or change an admin/librarian role. The last active admin is protected."""
    return user_service.update_user(db, actor, user_id, data)


@router.post(
    "/{user_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**BAD_REQUEST, **NOT_FOUND},
)
def reset_password(
    user_id: PathId,
    data: PasswordReset,
    actor: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """Set a new password for the account and end all its sessions."""
    user_service.reset_password(db, actor, user_id, data.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
