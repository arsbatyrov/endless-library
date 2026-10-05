"""Фикстуры дымовых тестов развёрнутого стенда (кластер Kubernetes).

В отличие от tests/ui, здесь НЕ поднимаются свои серверы и базы: тесты ходят по HTTP в уже работающее
приложение (по умолчанию http://127.0.0.1:8080, вход в локальный кластер kind через Ingress).
Поэтому данные в стенде настоящие, и каждый тест убирает за собой то, что создал.

Запуск: pytest tests/smoke -m smoke --no-cov
Другой адрес стенда: SMOKE_BASE_URL=http://host:port
"""

import base64
import json
import os
import shutil
import subprocess
import uuid
from urllib.parse import urlparse

import httpx2 as httpx
import pytest

from tests.ui.pages import App

SMOKE_URL = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
CONTEXT = "kind-endless-library"


def cluster_secret(name: str, key: str) -> str:
    """Value of a key of a Secret in the cluster (read with kubectl). The first administrator's password lives only there."""
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


@pytest.fixture(scope="session")
def base_url():
    """Адрес стенда: pytest-playwright откроет относительные адреса (page.goto('/')) относительно него."""
    return SMOKE_URL


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1000, "height": 700},
        "locale": "ru-RU",
        "timezone_id": "UTC",
    }


@pytest.fixture(scope="session")
def admin_credentials():
    """Login and password of the first administrator, read from the cluster Secret."""
    return cluster_secret("endless-library-admin", "username"), cluster_secret(
        "endless-library-admin", "password"
    )


@pytest.fixture
def admin_login(admin_credentials):
    """Signs in through the real entrance (Ingress -> nginx -> API): the access token and the refresh cookie value."""
    username, password = admin_credentials
    response = httpx.post(
        f"{SMOKE_URL}/api/auth/login", json={"username": username, "password": password}, timeout=15
    )
    assert response.status_code == 200, (
        f"sign-in as the first admin failed: {response.status_code} {response.text}"
    )
    cookie = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    return response.json()["access_token"], cookie


@pytest.fixture
def api(admin_login):
    """HTTP client of the API through the same entrance as the user, signed in as the first administrator."""
    with httpx.Client(
        base_url=f"{SMOKE_URL}/api",
        timeout=10,
        headers={"Authorization": f"Bearer {admin_login[0]}"},
    ) as client:
        yield client


@pytest.fixture
def unique_title():
    """Уникальное название: в стенде могут лежать чужие данные, пересечений быть не должно."""
    return f"smoke-{uuid.uuid4().hex[:10]}"


@pytest.fixture
def created_books(api):
    """Список id книг, созданных тестом: после теста они удаляются, даже если тест упал."""
    ids: list[int] = []
    yield ids
    for book_id in ids:
        api.delete(f"/books/{book_id}")


@pytest.fixture
def app(page, context, admin_login):
    """The application in the browser, already signed in: the refresh cookie is put in as the server issued it."""
    context.add_cookies(
        [
            {
                "name": "refresh_token",
                "value": admin_login[1],
                # domain and path explicitly: a "url" would make Playwright derive the path "/api/" (default-path rule),
                # a second cookie next to the server's own (path /api/auth) that would be sent too and looks like token reuse
                "domain": urlparse(SMOKE_URL).hostname,
                "path": "/api/auth",
                "httpOnly": True,
                "sameSite": "Lax",
            }
        ]
    )
    return App(page)
