"""AUTH-012: `python -m app.cli create-user` (acceptance criterion 1).

The password is never a command-line argument (it would show up in the process list and in shell history): it comes
from the environment variable LIBRARY_USER_PASSWORD or from a hidden prompt. The command never prints the password
or its hash. Repeating a login is refused with a clear message; `--skip-if-exists` makes it safe to run on every deploy.
"""

import contextlib
import os
import subprocess
import sys

import pytest

from app import cli
from app.auth.passwords import verify_password
from app.models import User
from tests.factories import make_reader, make_user

PASSWORD = "correct horse"
ENV = {"LIBRARY_USER_PASSWORD": PASSWORD}


@pytest.fixture
def run(db, capsys):
    """Run the CLI against the test database. Returns (exit code, stdout, stderr)."""

    def runner(*argv, environ=ENV, answers=()):
        replies = iter(answers)
        code = cli.main(
            list(argv),
            environ=environ,
            session_factory=lambda: contextlib.nullcontext(db),
            prompt=lambda _text: next(replies),
        )
        out, err = capsys.readouterr()
        return code, out, err

    return runner


def users(db):
    db.expire_all()
    return db.query(User).order_by(User.id).all()


# ---------- creating ----------


def test_creates_an_admin_with_a_hashed_password(run, db):
    code, out, err = run("create-user", "--username", "admin", "--role", "admin")

    assert code == 0, err
    (admin,) = users(db)
    assert (admin.username, admin.role, admin.reader_id, admin.is_active) == (
        "admin",
        "admin",
        None,
        True,
    )
    assert admin.password_hash.startswith("$argon2id$")
    assert verify_password(PASSWORD, admin.password_hash)
    assert "admin" in out and "Created" in out


def test_never_prints_the_password_or_the_hash(run, db):
    code, out, err = run("create-user", "--username", "admin", "--role", "admin")

    (admin,) = users(db)
    assert code == 0
    for text in (out, err):
        assert PASSWORD not in text
        assert admin.password_hash not in text
        assert "argon2" not in text


@pytest.mark.parametrize("role", ["admin", "librarian"])
def test_creates_staff_roles(run, db, role):
    code, _, err = run("create-user", "--username", "staff", "--role", role)

    assert code == 0, err
    assert users(db)[0].role == role


def test_creates_a_reader_linked_to_a_card(run, db):
    card = make_reader(db)

    code, _, err = run(
        "create-user", "--username", "rita", "--role", "reader", "--reader-id", str(card.id)
    )

    assert code == 0, err
    assert users(db)[0].reader_id == card.id


def test_the_created_account_can_sign_in(run, db, client):
    run("create-user", "--username", "admin", "--role", "admin")

    response = client.post("/auth/login", json={"username": "admin", "password": PASSWORD})

    assert response.status_code == 200


# ---------- where the password comes from ----------


def test_the_password_is_not_a_command_line_argument(run, db):
    with pytest.raises(SystemExit) as stopped:
        run("create-user", "--username", "admin", "--role", "admin", "--password", PASSWORD)

    assert stopped.value.code == 2
    assert users(db) == []


def test_without_the_variable_the_password_is_asked_twice(run, db):
    code, _, err = run(
        "create-user",
        "--username",
        "admin",
        "--role",
        "admin",
        environ={},
        answers=[PASSWORD, PASSWORD],
    )

    assert code == 0, err
    assert verify_password(PASSWORD, users(db)[0].password_hash)


def test_an_empty_variable_means_ask(run, db):
    code, _, err = run(
        "create-user",
        "--username",
        "admin",
        "--role",
        "admin",
        environ={"LIBRARY_USER_PASSWORD": ""},
        answers=[PASSWORD, PASSWORD],
    )

    assert code == 0, err


def test_prompts_that_do_not_match_are_refused(run, db):
    code, _, err = run(
        "create-user",
        "--username",
        "admin",
        "--role",
        "admin",
        environ={},
        answers=[PASSWORD, "another one"],
    )

    assert code == 1
    assert "match" in err.lower()
    assert users(db) == []


def test_the_variable_wins_over_the_prompt(run, db):
    code, _, _ = run(
        "create-user",
        "--username",
        "admin",
        "--role",
        "admin",
        answers=["never used", "never used"],
    )

    assert code == 0
    assert verify_password(PASSWORD, users(db)[0].password_hash)


# ---------- repeating a login ----------


def test_a_repeated_login_is_refused_with_a_clear_message(run, db):
    existing = make_user(db, role="admin", username="admin", password="the original one")
    original = existing.password_hash

    code, out, err = run("create-user", "--username", "admin", "--role", "admin")

    assert code == 1
    assert "already exists" in err
    assert "admin" in err
    db.expire_all()
    assert existing.password_hash == original
    assert len(users(db)) == 1


def test_the_repeat_check_ignores_case(run, db):
    make_user(db, role="admin", username="Admin", password="the original one")

    code, _, err = run("create-user", "--username", "ADMIN", "--role", "librarian")

    assert code == 1 and "already exists" in err


def test_skip_if_exists_leaves_the_account_untouched(run, db):
    existing = make_user(db, role="admin", username="admin", password="the original one")
    original = existing.password_hash

    code, out, err = run(
        "create-user", "--username", "admin", "--role", "admin", "--skip-if-exists"
    )

    assert code == 0, err
    assert "left unchanged" in out
    db.expire_all()
    assert existing.password_hash == original
    assert verify_password("the original one", existing.password_hash)
    assert not verify_password(PASSWORD, existing.password_hash)


def test_skip_if_exists_needs_no_password_when_the_user_exists(run, db):
    make_user(db, role="admin", username="admin", password="the original one")

    code, out, _ = run(
        "create-user", "--username", "admin", "--role", "admin", "--skip-if-exists", environ={}
    )

    assert code == 0 and "left unchanged" in out


def test_skip_if_exists_creates_when_missing(run, db):
    code, out, err = run(
        "create-user", "--username", "admin", "--role", "admin", "--skip-if-exists"
    )

    assert code == 0, err
    assert "Created" in out
    assert len(users(db)) == 1


def test_running_the_deploy_command_twice_creates_one_admin(run, db):
    first = run("create-user", "--username", "admin", "--role", "admin", "--skip-if-exists")
    second = run(
        "create-user",
        "--username",
        "admin",
        "--role",
        "admin",
        "--skip-if-exists",
        environ={"LIBRARY_USER_PASSWORD": "a different password"},
    )

    assert "Created" in first[1] and "left unchanged" in second[1]
    assert verify_password(PASSWORD, users(db)[0].password_hash)


# ---------- the same rules as the API ----------


@pytest.mark.parametrize("password", ["short", "1234567", "x" * 129])
def test_the_password_policy_applies(run, db, password):
    code, _, err = run(
        "create-user",
        "--username",
        "admin",
        "--role",
        "admin",
        environ={"LIBRARY_USER_PASSWORD": password},
    )

    assert code == 1
    assert "Error" in err
    assert password not in err
    assert users(db) == []


def test_a_password_equal_to_the_login_is_refused(run, db):
    code, _, err = run(
        "create-user",
        "--username",
        "administrator",
        "--role",
        "admin",
        environ={"LIBRARY_USER_PASSWORD": "ADMINISTRATOR"},
    )

    assert code == 1 and "login" in err.lower()


def test_a_reader_needs_a_card(run, db):
    code, _, err = run("create-user", "--username", "rita", "--role", "reader")

    assert code == 1 and "reader" in err.lower()
    assert users(db) == []


def test_a_missing_card_is_an_error(run, db):
    code, _, err = run(
        "create-user", "--username", "rita", "--role", "reader", "--reader-id", "999"
    )

    assert code == 1 and "not found" in err.lower()


def test_a_card_that_already_has_an_account_is_an_error(run, db):
    taken = make_user(db, role="reader", username="first")

    code, _, err = run(
        "create-user",
        "--username",
        "second",
        "--role",
        "reader",
        "--reader-id",
        str(taken.reader_id),
    )

    assert code == 1 and "already has an account" in err


def test_staff_must_not_have_a_card(run, db):
    card = make_reader(db)

    code, _, err = run(
        "create-user", "--username", "admin", "--role", "admin", "--reader-id", str(card.id)
    )

    assert code == 1
    assert users(db) == []


@pytest.mark.parametrize("username", ["", "x" * 65, "a\u0000b"])
def test_an_invalid_login_is_an_error(run, db, username):
    code, _, err = run("create-user", "--username", username, "--role", "admin")

    assert code == 1 and "Error" in err
    assert users(db) == []


def test_an_unknown_role_is_a_usage_error(run, db):
    with pytest.raises(SystemExit) as stopped:
        run("create-user", "--username", "admin", "--role", "superuser")

    assert stopped.value.code == 2


def test_a_missing_command_is_a_usage_error(run):
    with pytest.raises(SystemExit) as stopped:
        run()

    assert stopped.value.code == 2


def test_a_non_numeric_card_id_is_a_usage_error(run):
    with pytest.raises(SystemExit) as stopped:
        run("create-user", "--username", "rita", "--role", "reader", "--reader-id", "abc")

    assert stopped.value.code == 2


# ---------- the real command ----------


def test_the_module_can_be_started_with_python_dash_m():
    result = subprocess.run(
        [sys.executable, "-m", "app.cli", "create-user", "--help"],
        env={**os.environ, "PYTHONPATH": os.getcwd()},
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "--username" in result.stdout
    assert "LIBRARY_USER_PASSWORD" in result.stdout
    assert "--password" not in result.stdout.replace("LIBRARY_USER_PASSWORD", "")
