"""Command line for server administrators (AUTH-012, AUTH-021).

    python -m app.cli create-user  --username admin --role admin [--skip-if-exists]
    python -m app.cli set-password --username admin
    python -m app.cli seed-demo                      (needs DEMO_ACCOUNTS=true; local machines only)

The password is NEVER a command-line argument (it would be visible in the process list and in the shell history).
It is read from the environment variable LIBRARY_USER_PASSWORD, or typed at a hidden prompt (twice). The commands never
print a password or a hash (except `seed-demo`, whose demo passwords are public by design). They talk to the database
directly, so they need DATABASE_URL, and they are meant for whoever controls the server.
"""

import argparse
import contextlib
import getpass
import os
import sys
from collections.abc import Callable, Mapping

from pydantic import TypeAdapter, ValidationError

from app.demo import FLAG, DemoError, demo_enabled, seed_demo
from app.schemas import UserCreate, Username
from app.services.errors import BusinessRuleError, NotFoundError, UnprocessableError
from app.services.users import create_account, set_password_by_login, username_exists

PASSWORD_VARIABLE = "LIBRARY_USER_PASSWORD"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli", description="Administration commands."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    password_help = (
        f"The password is read from the environment variable {PASSWORD_VARIABLE}; if it is not set, "
        "it is asked for at a hidden prompt. It is never accepted as an argument."
    )
    create = commands.add_parser(
        "create-user", help="create an account", description=f"Create an account. {password_help}"
    )
    create.add_argument(
        "--username", required=True, help="the login (1 to 64 characters, unique ignoring case)"
    )
    create.add_argument("--role", required=True, choices=["admin", "librarian", "reader"])
    create.add_argument(
        "--reader-id", type=int, help="the reader card to link (required for role reader)"
    )
    create.add_argument(
        "--skip-if-exists",
        action="store_true",
        help="when the login already exists, change nothing and succeed (safe to run on every deploy)",
    )

    change = commands.add_parser(
        "set-password",
        help="set a new password for an account (also to regain access)",
        description=f"Set a new password for an account and end its sessions. {password_help}",
    )
    change.add_argument("--username", required=True, help="the login of the account")

    commands.add_parser(
        "seed-demo",
        help="create or reset the demo accounts (admin, librarian, reader) with PUBLIC passwords",
        description=(
            "Create the demo accounts admin / librarian / reader with known passwords, or reset them if they "
            f"exist. INSECURE: for a local machine only. Refuses to run unless {FLAG}=true."
        ),
    )
    return parser


def _password(environ: Mapping[str, str], prompt: Callable[[str], str]) -> str | None:
    value = environ.get(PASSWORD_VARIABLE, "")
    if value:
        return value
    first = prompt("Password: ")
    if prompt("Repeat the password: ") != first:
        return None
    return first


def _default_session_factory():
    from app.database import SessionLocal  # imported late: it needs DATABASE_URL, --help does not

    return SessionLocal()


def _create_user(args, db, environ, prompt) -> int:
    if args.skip_if_exists and username_exists(db, args.username):
        print(f"User '{args.username}' already exists; left unchanged.")
        return 0
    if username_exists(db, args.username):
        print(
            f"Error: user '{args.username}' already exists. Nothing was changed.", file=sys.stderr
        )
        return 1

    password = _password(environ, prompt)
    if password is None:
        print("Error: the two passwords do not match. Nothing was created.", file=sys.stderr)
        return 1
    try:
        data = UserCreate(
            username=args.username, password=password, role=args.role, reader_id=args.reader_id
        )
    except ValidationError as error:
        # Only the field and the rule, never the input (it contains the password).
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
        print(f"Error: {problems}", file=sys.stderr)
        return 1
    try:
        user = create_account(db, data)
    except (UnprocessableError, NotFoundError, BusinessRuleError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Created {user.role} '{user.username}' (id {user.id}).")
    return 0


def _set_password(args, db, environ, prompt) -> int:
    if not username_exists(db, args.username):
        print(f"Error: user '{args.username}' does not exist.", file=sys.stderr)
        return 1
    password = _password(environ, prompt)
    if password is None:
        print("Error: the two passwords do not match. Nothing was changed.", file=sys.stderr)
        return 1
    try:
        user = set_password_by_login(db, args.username, password)
    except (UnprocessableError, NotFoundError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"The password of '{user.username}' was changed; its sessions were ended.")
    return 0


def _seed_demo(db, environ) -> int:
    if not demo_enabled(environ):
        print(
            f"Error: demo accounts are disabled. They have PUBLIC passwords: set {FLAG}=true to create them, "
            "on a local machine only.",
            file=sys.stderr,
        )
        return 1
    try:
        accounts = seed_demo(db)
    except (DemoError, UnprocessableError, NotFoundError, BusinessRuleError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(
        "DEMO ACCOUNTS are ready. INSECURE: the passwords are public, use them on a local machine only."
    )
    for account in accounts:
        print(f"  {account.username} / {account.password}   ({account.role})")
    # one line per account for scripts (the deploy script reads the administrator's password from here)
    for account in accounts:
        print(f"demo-login: {account.username} {account.password} {account.role}")
    return 0


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    session_factory: Callable[[], contextlib.AbstractContextManager] | None = None,
    prompt: Callable[[str], str] = getpass.getpass,
) -> int:
    args = build_parser().parse_args(argv)
    environ = os.environ if environ is None else environ
    session_factory = session_factory or _default_session_factory

    if args.command in ("create-user", "set-password"):
        # The login is checked before it is used in a query (a NUL character would crash the database driver).
        try:
            TypeAdapter(Username).validate_python(args.username)
        except ValidationError as error:
            print(f"Error: username: {error.errors()[0]['msg']}", file=sys.stderr)
            return 1

    if args.command == "seed-demo" and not demo_enabled(environ):
        return _seed_demo(None, environ)  # refuses before touching the database
    with session_factory() as db:
        if args.command == "create-user":
            return _create_user(args, db, environ, prompt)
        if args.command == "set-password":
            return _set_password(args, db, environ, prompt)
        return _seed_demo(db, environ)


if __name__ == "__main__":
    sys.exit(main())
