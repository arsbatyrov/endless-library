"""Demo accounts with PUBLIC, known passwords, for a local machine only (AUTH-021).

They exist so the owner of a local training installation can sign in at once. They are opt-in: nothing creates them
unless `python -m app.cli seed-demo` is run with `DEMO_ACCOUNTS=true` (or the cluster is deployed with `DEMO=1`). The
passwords are written in the README, so NEVER enable this anywhere that other people can reach.

The password policy forbids `admin/admin` (at least 8 characters, not equal to the login), hence `admin12345`.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.auth.refresh_tokens import revoke_all_refresh_tokens
from app.models import Reader, User
from app.schemas import UserCreate
from app.services.users import create_account

FLAG = "DEMO_ACCOUNTS"
DEMO_CARD_NAME = "Demo Reader"
DEMO_CARD_EMAIL = "demo.reader@example.com"


@dataclass(frozen=True)
class DemoAccount:
    username: str
    password: str
    role: str


DEMO_ACCOUNTS = (
    DemoAccount("admin", "admin12345", "admin"),
    DemoAccount("librarian", "librarian12345", "librarian"),
    DemoAccount("reader", "reader12345", "reader"),
)


class DemoError(Exception):
    """The demo accounts cannot be created or reset (the message says why)."""


def demo_enabled(environ: Mapping[str, str]) -> bool:
    """Only the word `true` (any case) enables it: a typo or `1` must never create accounts with public passwords."""
    return environ.get(FLAG, "").strip().lower() == "true"


def _find(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.username) == username.lower()))


def _demo_card(db: Session) -> Reader:
    card = db.scalar(select(Reader).where(Reader.email == DEMO_CARD_EMAIL))
    if card is None:
        card = Reader(name=DEMO_CARD_NAME, email=DEMO_CARD_EMAIL)
        db.add(card)
        db.flush()
    return card


def seed_demo(db: Session) -> tuple[DemoAccount, ...]:
    """Create the demo accounts, or reset them (password, active) when they exist.

    An existing account with the demo login but ANOTHER role is refused: silently changing a role could hand out
    rights, so the owner has to decide (rename or remove that account). Every such conflict is checked BEFORE anything
    is changed.
    """
    for account in DEMO_ACCOUNTS:
        existing = _find(db, account.username)
        if existing is not None and existing.role != account.role:
            raise DemoError(
                f"An account '{account.username}' already exists with the role '{existing.role}', "
                f"not '{account.role}'. Nothing was changed."
            )
    try:
        for account in DEMO_ACCOUNTS:
            existing = _find(db, account.username)
            if existing is None:
                card = _demo_card(db) if account.role == "reader" else None
                create_account(
                    db,
                    UserCreate(
                        username=account.username,
                        password=account.password,
                        role=account.role,
                        reader_id=card.id if card else None,
                    ),
                )
            else:
                existing.password_hash = hash_password(account.password)
                existing.is_active = True
                revoke_all_refresh_tokens(db, existing.id, commit=False)
                db.commit()
    except Exception:
        db.rollback()
        raise
    return DEMO_ACCOUNTS
