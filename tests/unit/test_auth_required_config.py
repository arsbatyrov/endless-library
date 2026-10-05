"""AUTH-007: the temporary AUTH_REQUIRED switch. Secure by default; a typo must not silently turn security off."""

import os
import subprocess
import sys

import pytest

from app.auth.config import AuthConfigError, auth_required


def test_protection_is_required_when_the_variable_is_missing():
    assert auth_required({}) is True


@pytest.mark.parametrize("value", ["true", "TRUE", " True "])
def test_true_keeps_the_protection_on(value):
    assert auth_required({"AUTH_REQUIRED": value}) is True


@pytest.mark.parametrize("value", ["false", "FALSE", " False "])
def test_false_switches_it_off(value):
    assert auth_required({"AUTH_REQUIRED": value}) is False


def test_empty_value_means_the_default():
    assert auth_required({"AUTH_REQUIRED": ""}) is True


@pytest.mark.parametrize("value", ["flase", "0", "no", "off", "2", "disabled"])
def test_unknown_value_is_an_error_not_a_silent_off(value):
    with pytest.raises(AuthConfigError, match="AUTH_REQUIRED"):
        auth_required({"AUTH_REQUIRED": value})


def test_reads_the_real_environment_by_default(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "false")

    assert auth_required() is False


# ---------- the application at startup ----------


def start_application(auth_required: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd()
    env["AUTH_REQUIRED"] = auth_required
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_application_does_not_start_with_a_mistyped_switch():
    result = start_application("flase")

    assert result.returncode != 0
    assert "AUTH_REQUIRED" in result.stderr


def test_application_starts_silently_with_the_protection_on():
    result = start_application("true")

    assert result.returncode == 0, result.stderr
    assert "PROTECTION IS OFF" not in result.stdout + result.stderr


def test_application_warns_loudly_when_the_protection_is_off():
    result = start_application("false")

    assert result.returncode == 0, result.stderr
    assert "PROTECTION IS OFF" in result.stdout + result.stderr
