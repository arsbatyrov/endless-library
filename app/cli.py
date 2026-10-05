"""Command line for server administrators (AUTH-012).

    python -m app.cli create-user --username admin --role admin [--skip-if-exists]

The password is NEVER a command-line argument (it would be visible in the process list and in the shell history).
It is read from the environment variable LIBRARY_USER_PASSWORD, or typed at a hidden prompt (twice). The command never
prints the password or its hash. It talks to the database directly, so it needs DATABASE_URL, and it is meant for
whoever controls the server (the first admin is created this way at deploy time).
"""

import argparse
import contextlib
import getpass
import os
import sys
from collections.abc import Callable, Mapping

from pydantic import TypeAdapter, ValidationError

from app.schemas import UserCreate, Username
from app.services.errors import BusinessRuleError, NotFoundError, UnprocessableError
from app.services.users import create_account, username_exists

PASSWORD_VARIABLE = "LIBRARY_USER_PASSWORD"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli", description="Administration commands."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser(
        "create-user",
        help="create an account",
        description=(
            "Create an account. The password is read from the environment variable "
            f"{PASSWORD_VARIABLE}; if it is not set, it is asked for at a hidden prompt. "
            "It is never accepted as an argument."
        ),
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

    # The login is checked before it is used in a query (a NUL character would crash the database driver).
    try:
        TypeAdapter(Username).validate_python(args.username)
    except ValidationError as error:
        print(f"Error: username: {error.errors()[0]['msg']}", file=sys.stderr)
        return 1

    with session_factory() as db:
        if args.skip_if_exists and username_exists(db, args.username):
            print(f"User '{args.username}' already exists; left unchanged.")
            return 0
        if username_exists(db, args.username):
            print(
                f"Error: user '{args.username}' already exists. Nothing was changed.",
                file=sys.stderr,
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
            problems = "; ".join(
                f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()
            )
            print(f"Error: {problems}", file=sys.stderr)
            return 1
        try:
            user = create_account(db, data)
        except (UnprocessableError, NotFoundError, BusinessRuleError) as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
        print(f"Created {user.role} '{user.username}' (id {user.id}).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
