"""User management (AUTH-009): who may create, change and reset which accounts.

An admin manages everybody; a librarian manages only reader accounts; a reader manages nobody (the router refuses
readers before the service is reached).
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import PasswordPolicyError, hash_password, validate_password_policy
from app.auth.refresh_tokens import revoke_all_refresh_tokens
from app.models import Reader, User
from app.schemas import UserCreate, UserUpdate
from app.services.errors import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    UnprocessableError,
)

FORBIDDEN_FOR_ROLE = "Your role is not allowed to do this with this account"


def _may_manage(actor: User, target_role: str) -> bool:
    return actor.role == "admin" or (actor.role == "librarian" and target_role == "reader")


def _check_password(password: str, username: str, field: str) -> None:
    try:
        validate_password_policy(password, username)
    except PasswordPolicyError as error:
        raise UnprocessableError(field, str(error)) from None


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return user


def list_users(db: Session, actor: User) -> list[User]:
    stmt = select(User).order_by(User.id)
    if actor.role != "admin":
        stmt = stmt.where(User.role == "reader")
    return list(db.scalars(stmt))


def create_user(db: Session, actor: User, data: UserCreate) -> User:
    # The role check comes first so that a librarian cannot use the other answers to probe cards or logins.
    if not _may_manage(actor, data.role):
        raise PermissionDeniedError(FORBIDDEN_FOR_ROLE)
    return create_account(db, data)


def username_exists(db: Session, username: str) -> bool:
    return (
        db.scalar(select(User.id).where(func.lower(User.username) == username.lower())) is not None
    )


def create_account(db: Session, data: UserCreate) -> User:
    """Create an account, applying every rule of the account itself but NOT who is allowed to ask for it.

    The caller must have done that check: the API checks the role of the signed-in user, the command line is run by
    whoever controls the server. Order of answers: 422 (shape of the account), 404 (card), 409 (taken).
    """
    if data.role == "reader" and data.reader_id is None:
        raise UnprocessableError("reader_id", "A reader account must be linked to a reader card")
    if data.role != "reader" and data.reader_id is not None:
        raise UnprocessableError("reader_id", "Only reader accounts are linked to a reader card")
    _check_password(data.password, data.username, "password")

    if data.reader_id is not None:
        if db.get(Reader, data.reader_id) is None:
            raise NotFoundError("Reader not found")
        if db.scalar(select(User.id).where(User.reader_id == data.reader_id)) is not None:
            raise BusinessRuleError("This reader card already has an account")
    if username_exists(db, data.username):
        raise BusinessRuleError("This login is already taken")

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=data.role,
        reader_id=data.reader_id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Somebody created the same login or took the same card between our check and the insert.
        db.rollback()
        raise BusinessRuleError("This login or reader card is already taken") from None
    db.refresh(user)
    return user


def _card_has_account(db: Session, card_id: int) -> bool:
    return db.scalar(select(User.id).where(User.reader_id == card_id)) is not None


def update_user(db: Session, actor: User, user_id: int, data: UserUpdate) -> User:
    """Disable or enable an account and (admins only) change its role to any role.

    A reader account is tied to a reader card: becoming a reader needs a free card, leaving the reader role removes the
    link (the card itself stays). A librarian may only disable or enable reader accounts and may not send a role or a card.
    """
    target = _get_user(db, user_id)
    if actor.role != "admin" and (
        data.role is not None or data.reader_id is not None or not _may_manage(actor, target.role)
    ):
        raise PermissionDeniedError(FORBIDDEN_FOR_ROLE)

    new_role = data.role if data.role is not None else target.role
    new_active = data.is_active if data.is_active is not None else target.is_active
    new_card = target.reader_id
    if new_role == "reader":
        if target.role == "reader":
            if data.reader_id is not None and data.reader_id != target.reader_id:
                raise UnprocessableError(
                    "reader_id",
                    "A reader account stays linked to its card; create a new account for another card",
                )
        else:
            if data.reader_id is None:
                raise UnprocessableError(
                    "reader_id", "A reader account must be linked to a reader card"
                )
            if db.get(Reader, data.reader_id) is None:
                raise NotFoundError("Reader not found")
            if _card_has_account(db, data.reader_id):
                raise BusinessRuleError("This reader card already has an account")
            new_card = data.reader_id
    else:
        if data.reader_id is not None:
            raise UnprocessableError(
                "reader_id", "Only reader accounts are linked to a reader card"
            )
        new_card = None

    # The system must never be left without an active administrator. The rows are locked so that two admins
    # disabling each other at the same moment cannot both succeed.
    active_admins = list(
        db.scalars(
            select(User).where(User.role == "admin", User.is_active.is_(True)).with_for_update()
        )
    )
    stays_active_admin = new_role == "admin" and new_active
    if target in active_admins and not stays_active_admin and len(active_admins) <= 1:
        db.rollback()
        raise BusinessRuleError("The last active administrator cannot be disabled or demoted")

    was_active = target.is_active
    target.role = new_role
    target.reader_id = new_card
    target.is_active = new_active
    if was_active and not new_active:
        revoke_all_refresh_tokens(
            db, target.id, commit=False
        )  # a disabled account cannot keep sessions
    try:
        db.commit()
    except IntegrityError:
        # Somebody linked the same card between our check and the save: the database's unique index decided.
        db.rollback()
        raise BusinessRuleError("This reader card was just given to another account") from None
    db.refresh(target)
    return target


def reset_password(db: Session, actor: User, user_id: int, new_password: str) -> None:
    target = _get_user(db, user_id)
    if not _may_manage(actor, target.role):
        raise PermissionDeniedError(FORBIDDEN_FOR_ROLE)
    _check_password(new_password, target.username, "new_password")

    target.password_hash = hash_password(new_password)
    revoke_all_refresh_tokens(db, target.id, commit=False)  # same transaction as the new hash
    db.commit()
