"""AUTH-003, criterion 4: the application must not start without a strong JWT secret (there is no fallback value).

The secret signs every access token. A missing or weak secret would let anyone forge tokens, so a wrong configuration
must stop the application at startup with a message that tells how to fix it.
"""

import os
import subprocess
import sys

import pytest

from app.auth.config import MIN_SECRET_BYTES, AuthConfigError, load_jwt_secret

GOOD = "k" * MIN_SECRET_BYTES


# ---------- loading the secret ----------


def test_secret_of_the_minimum_size_is_accepted():
    assert load_jwt_secret({"JWT_SECRET": GOOD}) == GOOD


def test_minimum_secret_size_is_32_bytes():
    assert MIN_SECRET_BYTES == 32


@pytest.mark.parametrize("environ", [{}, {"JWT_SECRET": ""}], ids=["not set", "empty"])
def test_missing_secret_is_an_error_that_explains_how_to_fix_it(environ):
    with pytest.raises(AuthConfigError) as error:
        load_jwt_secret(environ)

    message = str(error.value)
    assert "JWT_SECRET" in message
    assert "secrets.token_hex(32)" in message  # a ready-to-run way to create a good value


@pytest.mark.parametrize("size", [1, 16, MIN_SECRET_BYTES - 1])
def test_secret_shorter_than_the_minimum_is_rejected(size):
    with pytest.raises(AuthConfigError) as error:
        load_jwt_secret({"JWT_SECRET": "k" * size})

    assert "32" in str(error.value)


def test_secret_size_is_counted_in_bytes_not_characters():
    """16 Cyrillic letters are 32 bytes (enough); 15 are 30 bytes (not enough)."""
    assert load_jwt_secret({"JWT_SECRET": "ж" * 16}) == "ж" * 16
    with pytest.raises(AuthConfigError):
        load_jwt_secret({"JWT_SECRET": "ж" * 15})


def test_error_message_never_contains_the_secret_itself():
    weak = "short-secret"

    with pytest.raises(AuthConfigError) as error:
        load_jwt_secret({"JWT_SECRET": weak})

    assert weak not in str(error.value)


# ---------- the application really refuses to start ----------


def start_application(jwt_secret: str | None) -> subprocess.CompletedProcess:
    """Import the application in a fresh process with the given secret (None = not set at all)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd()
    # "Not set" is an EMPTY value, not an absent one: python-dotenv (used by the app) fills in absent variables from a
    # local .env file, which could make this test pass or fail depending on the developer's machine.
    env["JWT_SECRET"] = "" if jwt_secret is None else jwt_secret
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_application_starts_with_a_good_secret():
    result = start_application(GOOD)

    assert result.returncode == 0, result.stderr


def test_application_does_not_start_without_a_secret():
    result = start_application(None)

    assert result.returncode != 0
    assert "JWT_SECRET" in result.stderr


def test_application_does_not_start_with_a_short_secret():
    result = start_application("too-short")

    assert result.returncode != 0
    assert "JWT_SECRET" in result.stderr
    assert "too-short" not in result.stderr
