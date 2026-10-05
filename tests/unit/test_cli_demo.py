"""AUTH-021: `set-password` and `seed-demo` of the command line, and the demo account definitions.

Demo accounts have PUBLIC, known passwords: they exist only when the owner asks for them on a local machine
(`DEMO_ACCOUNTS=true`). The password policy forbids `admin/admin` (at least 8 characters, not equal to the login), so the
administrator's demo password is `admin12345`.
"""

import contextlib
import os
import subprocess
import sys

import pytest

from app import cli, demo
from app.auth.passwords import validate_password_policy, verify_password
from app.auth.refresh_tokens import issue_refresh_token
from app.models import Reader, RefreshToken, User
from tests.factories import make_user

ENABLED = {"DEMO_ACCOUNTS": "true"}


@pytest.fixture
def client(anonymous_client):
    return anonymous_client


@pytest.fixture
def run(db, capsys):
    def runner(*argv, environ=None, answers=()):
        replies = iter(answers)
        code = cli.main(
            list(argv),
            environ={} if environ is None else environ,
            session_factory=lambda: contextlib.nullcontext(db),
            prompt=lambda _text: next(replies),
        )
        out, err = capsys.readouterr()
        return code, out, err

    return runner


def users(db):
    db.expire_all()
    return {u.username: u for u in db.query(User).all()}


# ---------- the definitions ----------


def test_the_demo_accounts_are_the_three_roles_with_the_documented_logins():
    by_login = {a.username: a for a in demo.DEMO_ACCOUNTS}

    assert set(by_login) == {"admin", "librarian", "reader"}
    assert by_login["admin"].role == "admin" and by_login["admin"].password == "admin12345"
    assert (
        by_login["librarian"].role == "librarian"
        and by_login["librarian"].password == "librarian12345"
    )
    assert by_login["reader"].role == "reader" and by_login["reader"].password == "reader12345"


def test_every_demo_password_satisfies_the_password_policy():
    for account in demo.DEMO_ACCOUNTS:
        validate_password_policy(account.password, account.username)  # raises if it does not


def test_the_policy_really_forbids_admin_slash_admin():
    with pytest.raises(Exception):  # noqa: B017
        validate_password_policy("admin", "admin")


def test_the_readme_documents_every_demo_login():
    text = open("README.md", encoding="utf-8").read()

    for account in demo.DEMO_ACCOUNTS:
        assert f"{account.username} / {account.password}" in text, account.username
    assert "DEMO_ACCOUNTS" in text and "seed-demo" in text and "DEMO=1" in text


# ---------- set-password ----------


def test_set_password_changes_the_password_from_the_environment(run, db):
    make_user(db, role="librarian", username="lib", password="the old one")

    code, out, err = run(
        "set-password", "--username", "lib", environ={"LIBRARY_USER_PASSWORD": "a brand new one"}
    )

    assert code == 0, err
    assert verify_password("a brand new one", users(db)["lib"].password_hash)
    assert not verify_password("the old one", users(db)["lib"].password_hash)
    assert "lib" in out


def test_set_password_asks_twice_when_the_variable_is_not_set(run, db):
    make_user(db, role="librarian", username="lib", password="the old one")

    code, _, err = run(
        "set-password", "--username", "lib", answers=["a brand new one", "a brand new one"]
    )

    assert code == 0, err
    assert verify_password("a brand new one", users(db)["lib"].password_hash)


def test_set_password_refuses_prompts_that_do_not_match(run, db):
    user = make_user(db, role="librarian", username="lib", password="the old one")
    old = user.password_hash

    code, _, err = run("set-password", "--username", "lib", answers=["one", "another"])

    assert code == 1 and "match" in err.lower()
    assert users(db)["lib"].password_hash == old


def test_set_password_never_prints_the_password_or_the_hash(run, db):
    make_user(db, role="librarian", username="lib", password="the old one")

    _, out, err = run(
        "set-password", "--username", "lib", environ={"LIBRARY_USER_PASSWORD": "a brand new one"}
    )

    for text in (out, err):
        assert "a brand new one" not in text and "argon2" not in text


def test_set_password_ends_every_session_of_the_account(run, db):
    user = make_user(db, role="librarian", username="lib", password="the old one")
    issue_refresh_token(db, user)
    db.commit()

    run("set-password", "--username", "lib", environ={"LIBRARY_USER_PASSWORD": "a brand new one"})

    db.expire_all()
    assert all(row.revoked_at is not None for row in db.query(RefreshToken).all())


def test_set_password_applies_the_policy(run, db):
    user = make_user(db, role="librarian", username="lib", password="the old one")
    old = user.password_hash

    for bad in ("short", "x" * 129, "LIB"):
        code, _, err = run(
            "set-password", "--username", "lib", environ={"LIBRARY_USER_PASSWORD": bad}
        )
        assert code == 1 and "Error" in err
        assert bad not in err

    assert users(db)["lib"].password_hash == old


def test_set_password_for_an_unknown_login_is_an_error(run, db):
    code, _, err = run(
        "set-password", "--username", "ghost", environ={"LIBRARY_USER_PASSWORD": "a brand new one"}
    )

    assert code == 1 and "does not exist" in err


def test_set_password_ignores_the_case_of_the_login(run, db):
    make_user(db, role="librarian", username="Lib", password="the old one")

    code, _, _ = run(
        "set-password", "--username", "LIB", environ={"LIBRARY_USER_PASSWORD": "a brand new one"}
    )

    assert code == 0


def test_set_password_does_not_reactivate_a_disabled_account(run, db):
    make_user(db, role="librarian", username="lib", password="the old one", active=False)

    run("set-password", "--username", "lib", environ={"LIBRARY_USER_PASSWORD": "a brand new one"})

    assert users(db)["lib"].is_active is False


def test_the_password_is_not_a_command_line_argument_of_set_password(run):
    with pytest.raises(SystemExit) as stopped:
        run("set-password", "--username", "lib", "--password", "x")

    assert stopped.value.code == 2


# ---------- seed-demo ----------


def test_seed_demo_refuses_without_the_flag_and_changes_nothing(run, db):
    code, _, err = run("seed-demo")

    assert code == 1
    assert "DEMO_ACCOUNTS=true" in err
    assert users(db) == {}


@pytest.mark.parametrize("value", ["", "false", "1", "yes", "True1", "tru"])
def test_only_the_word_true_enables_it(run, db, value):
    code, _, _ = run("seed-demo", environ={"DEMO_ACCOUNTS": value})

    assert code == 1 and users(db) == {}


@pytest.mark.parametrize("value", ["true", "TRUE", " True "])
def test_the_flag_is_not_case_sensitive(run, db, value):
    assert run("seed-demo", environ={"DEMO_ACCOUNTS": value})[0] == 0


def test_seed_demo_refuses_without_even_opening_the_database(capsys):
    """Refusing must not need a database at all (so a wrong DATABASE_URL cannot hide the real reason)."""

    def no_database():
        raise AssertionError("the database was touched")

    code = cli.main(["seed-demo"], environ={}, session_factory=no_database)

    assert code == 1
    assert "DEMO_ACCOUNTS=true" in capsys.readouterr().err


def test_the_service_rejects_an_unknown_login_by_itself(db):
    from app.services.errors import NotFoundError
    from app.services.users import set_password_by_login

    with pytest.raises(NotFoundError):
        set_password_by_login(db, "ghost", "a brand new one")


def test_seed_demo_creates_the_three_accounts_with_their_roles(run, db):
    code, out, err = run("seed-demo", environ=ENABLED)

    assert code == 0, err
    found = users(db)
    assert {name: u.role for name, u in found.items()} == {
        "admin": "admin",
        "librarian": "librarian",
        "reader": "reader",
    }
    assert all(u.is_active for u in found.values())
    for account in demo.DEMO_ACCOUNTS:
        assert verify_password(account.password, found[account.username].password_hash)


def test_the_demo_reader_is_linked_to_a_demo_card(run, db):
    run("seed-demo", environ=ENABLED)

    reader_user = users(db)["reader"]
    card = db.get(Reader, reader_user.reader_id)
    assert card is not None and card.email == "demo.reader@example.com"
    assert users(db)["admin"].reader_id is None and users(db)["librarian"].reader_id is None


def test_the_demo_accounts_can_really_sign_in(run, db, client):
    run("seed-demo", environ=ENABLED)

    for account in demo.DEMO_ACCOUNTS:
        response = client.post(
            "/auth/login", json={"username": account.username, "password": account.password}
        )
        assert response.status_code == 200, account.username
        me = client.get(
            "/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}
        ).json()
        assert me["role"] == account.role


def test_running_it_again_creates_nothing_twice(run, db):
    run("seed-demo", environ=ENABLED)
    run("seed-demo", environ=ENABLED)

    assert db.query(User).count() == 3
    assert db.query(Reader).count() == 1


def test_running_it_again_resets_the_demo_passwords_and_reactivates(run, db):
    run("seed-demo", environ=ENABLED)
    users(db)["admin"].password_hash = "not-a-hash"
    users(db)["librarian"].is_active = False
    db.commit()

    code, _, _ = run("seed-demo", environ=ENABLED)

    assert code == 0
    assert verify_password("admin12345", users(db)["admin"].password_hash)
    assert users(db)["librarian"].is_active is True


def test_it_resets_an_existing_admin_with_a_random_password_and_ends_its_sessions(run, db):
    existing = make_user(db, role="admin", username="admin", password="a random generated password")
    issue_refresh_token(db, existing)
    db.commit()

    code, _, _ = run("seed-demo", environ=ENABLED)

    assert code == 0
    assert verify_password("admin12345", users(db)["admin"].password_hash)
    db.expire_all()
    assert all(row.revoked_at is not None for row in db.query(RefreshToken).all())


def test_an_existing_account_with_another_role_is_refused_not_silently_changed(run, db):
    make_user(db, role="reader", username="admin", password="whatever it is")

    code, _, err = run("seed-demo", environ=ENABLED)

    assert code == 1 and "admin" in err and "role" in err.lower()
    assert users(db)["admin"].role == "reader"
    assert len(users(db)) == 1  # nothing else was created either (all or nothing)


def test_the_output_lists_the_public_logins_and_warns(run, db):
    _, out, _ = run("seed-demo", environ=ENABLED)

    assert "INSECURE" in out and "local" in out.lower()
    for account in demo.DEMO_ACCOUNTS:
        assert f"{account.username} / {account.password}" in out


def test_the_output_has_a_machine_readable_line_for_the_deploy_script(run, db):
    _, out, _ = run("seed-demo", environ=ENABLED)

    assert "demo-login: admin admin12345 admin" in out.splitlines()


def test_the_output_never_contains_a_hash(run, db):
    _, out, err = run("seed-demo", environ=ENABLED)

    assert "argon2" not in out + err


# ---------- the application warns at startup ----------


def start_application(demo_value: str | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd()
    if demo_value is None:
        env.pop("DEMO_ACCOUNTS", None)
    else:
        env["DEMO_ACCOUNTS"] = demo_value
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_the_application_warns_loudly_once_when_demo_accounts_are_enabled():
    result = start_application("true")

    assert result.returncode == 0, result.stderr
    assert (result.stdout + result.stderr).count("DEMO_ACCOUNTS=true") == 1
    assert "PUBLIC" in result.stdout + result.stderr


@pytest.mark.parametrize("value", [None, "false", ""])
def test_the_application_is_silent_about_demo_when_it_is_not_enabled(value):
    result = start_application(value)

    assert result.returncode == 0, result.stderr
    assert "DEMO_ACCOUNTS" not in result.stdout + result.stderr


def test_nothing_about_the_demo_logins_is_in_the_application_code_that_serves_pages():
    """The demo passwords are documented in the README only: not in the web app, the API responses or the OpenAPI."""
    import pathlib

    for path in list(pathlib.Path("frontend/src").glob("*")) + list(
        pathlib.Path("app/routers").glob("*.py")
    ):
        text = path.read_text(encoding="utf-8")
        for account in demo.DEMO_ACCOUNTS:
            assert account.password not in text, f"{path}: {account.password}"
