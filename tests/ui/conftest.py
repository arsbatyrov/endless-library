"""Фикстуры UI-тестов.

Стенд: API (uvicorn) и фронтенд (Vite) запускаются отдельными процессами на отдельной базе
`<имя>_e2e_test`. Браузером управляет pytest-playwright (фикстура `page`).
"""

import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx2 as httpx
import pytest
from alembic import command
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from app import models  # noqa: F401  (регистрирует таблицы в Base)
from app.database import Base
from tests.db_utils import ROOT, alembic_config, ensure_database, reset_schema
from tests.ui.api_client import ApiClient
from tests.ui.pages import App

API_PORT = int(os.getenv("UI_API_PORT", "8100"))
WEB_PORT = int(os.getenv("UI_WEB_PORT", "5180"))
LOG_DIR = ROOT / "test-results" / "ui-servers"


@dataclass
class Stack:
    api_url: str
    web_url: str
    engine: Engine


def _port_is_busy(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _wait_until_ready(
    url: str, name: str, process: subprocess.Popen, log_path: Path, timeout: float = 40
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-1500:]
            pytest.exit(
                f"{name} exited during startup (code {process.returncode}). Log tail:\n{tail}",
                returncode=4,
            )
        try:
            if httpx.get(url, timeout=2).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    pytest.exit(
        f"{name} did not become ready at {url} within {timeout:.0f}s (see {log_path})", returncode=4
    )


def _stop(process: subprocess.Popen) -> None:
    """Останавливает процесс вместе с дочерними (на Windows нужен taskkill)."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture(scope="session")
def ui_stack():
    """Один раз за запуск: отдельная база, миграции, API и фронтенд в своих процессах."""
    node = shutil.which("node")
    if node is None:
        pytest.exit(
            "Node.js not found in PATH: it is required to run the frontend for UI tests",
            returncode=4,
        )
    if not (ROOT / "frontend" / "node_modules").exists():
        pytest.exit(
            "frontend/node_modules not found: run 'npm ci' in the frontend folder", returncode=4
        )
    for port in (API_PORT, WEB_PORT):
        if _port_is_busy(port):
            pytest.exit(
                f"Port {port} is busy. UI tests need ports {API_PORT} (API) and {WEB_PORT} (frontend); "
                "set UI_API_PORT / UI_WEB_PORT to use other ones",
                returncode=4,
            )

    # отдельная база для UI-тестов: <имя>_e2e_test (суффикс _test обязателен для защиты от стирания)
    test_url = make_url(os.environ["DATABASE_URL"])
    e2e_url = test_url.set(database=f"{test_url.database.removesuffix('_test')}_e2e_test")
    ensure_database(e2e_url)
    reset_schema(e2e_url)
    command.upgrade(alembic_config(e2e_url), "head")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    api_log_path, web_log_path = LOG_DIR / "api.log", LOG_DIR / "web.log"
    api_log, web_log = (
        open(api_log_path, "w", encoding="utf-8"),
        open(web_log_path, "w", encoding="utf-8"),
    )

    # AUTH_REQUIRED=false: the web UI has no sign-in page yet (AUTH-013); then the UI tests will log in instead.
    api_env = {
        **os.environ,
        "DATABASE_URL": e2e_url.render_as_string(hide_password=False),
        "AUTH_REQUIRED": "false",
    }
    web_env = {**os.environ, "API_TARGET": f"http://127.0.0.1:{API_PORT}"}
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(API_PORT),
        ],
        cwd=ROOT,
        env=api_env,
        stdout=api_log,
        stderr=subprocess.STDOUT,
    )
    web = subprocess.Popen(
        [
            node,
            "node_modules/vite/bin/vite.js",
            "--host",
            "127.0.0.1",
            "--port",
            str(WEB_PORT),
            "--strictPort",
        ],
        cwd=ROOT / "frontend",
        env=web_env,
        stdout=web_log,
        stderr=subprocess.STDOUT,
    )
    engine = create_engine(e2e_url)
    try:
        _wait_until_ready(f"http://127.0.0.1:{API_PORT}/health", "API", api, api_log_path)
        _wait_until_ready(f"http://127.0.0.1:{WEB_PORT}/", "Frontend", web, web_log_path)
        yield Stack(
            api_url=f"http://127.0.0.1:{API_PORT}",
            web_url=f"http://127.0.0.1:{WEB_PORT}",
            engine=engine,
        )
    finally:
        _stop(web)
        _stop(api)
        api_log.close()
        web_log.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(ui_stack):
    """Перед каждым UI-тестом база пуста, счётчики id сброшены: тесты не влияют друг на друга."""
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with ui_stack.engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def base_url(ui_stack):
    """Адрес фронтенда: pytest-playwright откроет относительные адреса (page.goto('/')) относительно него."""
    return ui_stack.web_url


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Одинаковая среда браузера у всех тестов: размер окна, язык и часовой пояс."""
    return {
        **browser_context_args,
        "viewport": {"width": 1000, "height": 700},
        "locale": "ru-RU",
        "timezone_id": "UTC",
    }


@pytest.fixture
def api(ui_stack):
    client = ApiClient(ui_stack.api_url)
    yield client
    client.close()


@pytest.fixture
def app(page):
    return App(page)
