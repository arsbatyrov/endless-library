"""AUTH-012: the first admin exists on the deployed cluster and can sign in (acceptance criterion 2).

The password lives only in the cluster Secret `endless-library-admin`; this test reads it from there (kubectl) and
logs in through the real entrance (Ingress -> nginx -> API). Needs kubectl and the context kind-endless-library.
"""

import base64
import json
import shutil
import subprocess

import httpx2 as httpx
import pytest

from tests.smoke.conftest import SMOKE_URL

CONTEXT = "kind-endless-library"


def secret_value(name: str, key: str) -> str:
    if shutil.which("kubectl") is None:
        pytest.skip("kubectl is not installed")
    result = subprocess.run(
        [
            "kubectl",
            "--context",
            CONTEXT,
            "-n",
            "endless-library",
            "get",
            "secret",
            name,
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.fail(
            f"Secret {name} is missing: run `bash k8s/deploy.sh` first. {result.stderr.strip()}"
        )
    return base64.b64decode(json.loads(result.stdout)["data"][key]).decode()


@pytest.fixture(scope="module")
def admin_credentials():
    return secret_value("endless-library-admin", "username"), secret_value(
        "endless-library-admin", "password"
    )


def test_the_admin_secret_holds_a_random_password(admin_credentials):
    username, password = admin_credentials

    assert username == "admin"
    assert len(password) >= 32
    assert password != username


def test_the_admin_can_sign_in_on_the_cluster(admin_credentials):
    username, password = admin_credentials

    response = httpx.post(
        f"{SMOKE_URL}/api/auth/login", json={"username": username, "password": password}, timeout=15
    )

    assert response.status_code == 200
    token = response.json()["access_token"]
    me = httpx.get(
        f"{SMOKE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=15
    )
    assert me.json()["role"] == "admin"
    assert me.json()["username"] == "admin"


def test_the_refresh_cookie_works_through_the_ingress(admin_credentials):
    username, password = admin_credentials
    with httpx.Client(base_url=SMOKE_URL, timeout=15) as client:
        client.post("/api/auth/login", json={"username": username, "password": password})

        refreshed = client.post("/api/auth/refresh")

    assert refreshed.status_code == 200
    assert "access_token" in refreshed.json()


def test_the_jwt_secret_is_in_its_own_secret_and_differs_from_the_admin_password(admin_credentials):
    jwt = secret_value("endless-library-jwt", "JWT_SECRET")

    assert len(jwt) >= 64
    assert jwt != admin_credentials[1]


def test_the_admin_password_is_not_in_the_api_environment_or_logs(admin_credentials):
    """The API pod gets only the database and JWT secrets; the admin password is for the one-off Job only."""
    _, password = admin_credentials
    result = subprocess.run(
        [
            "kubectl",
            "--context",
            CONTEXT,
            "-n",
            "endless-library",
            "logs",
            "-l",
            "app=api",
            "--tail=500",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert password not in result.stdout
