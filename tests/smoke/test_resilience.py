"""Проверки устойчивости: приложение переживает перезапуски компонентов в кластере.

Это уже не «работает ли», а «что будет, когда под перезапустится или обновится».
Тесты управляют кластером командой kubectl, поэтому нужны kubectl и доступ к кластеру;
без них тесты пропускаются. Контекст: SMOKE_KUBE_CONTEXT (по умолчанию kind-endless-library), namespace endless-library.
"""

import os
import shutil
import subprocess
import time

import httpx2 as httpx
import pytest

from tests.smoke.conftest import SMOKE_URL

KUBE_CONTEXT = os.getenv("SMOKE_KUBE_CONTEXT", "kind-endless-library")
NAMESPACE = os.getenv("SMOKE_KUBE_NAMESPACE", "endless-library")

pytestmark = pytest.mark.skipif(shutil.which("kubectl") is None, reason="kubectl is not installed")


def _kubectl(*args: str) -> list[str]:
    return ["kubectl", "--context", KUBE_CONTEXT, "-n", NAMESPACE, *args]


def _run_kubectl(*args: str, timeout: float = 240) -> None:
    subprocess.run(_kubectl(*args), check=True, capture_output=True, text=True, timeout=timeout)


def test_rolling_restart_of_api_loses_no_requests(api):
    """Во время плавного обновления API ни один запрос пользователя не должен завершиться ошибкой.

    Это проверка настроек Deployment: maxUnavailable=0 и readiness-пробы. Если новый под
    начнёт получать запросы раньше времени, а старый исчезнет мгновенно, часть запросов упадёт (502/503).
    """
    _run_kubectl("rollout", "restart", "deployment/api")
    rollout = subprocess.Popen(
        _kubectl("rollout", "status", "deployment/api", "--timeout=240s"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    failures: list[str] = []
    total = 0
    while rollout.poll() is None:
        total += 1
        try:
            status = api.get("/books").status_code
            if status != 200:
                failures.append(f"HTTP {status}")
        except httpx.HTTPError as exc:
            failures.append(type(exc).__name__)
        time.sleep(0.05)

    assert rollout.returncode == 0, "обновление не завершилось"
    assert total >= 20, f"слишком мало запросов за время обновления: {total}"
    assert not failures, f"{len(failures)} из {total} запросов упали: {sorted(set(failures))}"


def test_data_survives_database_restart(api, unique_title, created_books):
    """Данные лежат на постоянном томе (PVC): после перезапуска пода базы они на месте."""
    created = api.post(
        "/books",
        json={"title": unique_title, "author": "Persist", "year": 2024, "copies_available": 1},
    )
    assert created.status_code == 201
    book_id = created.json()["id"]
    created_books.append(book_id)

    _run_kubectl("rollout", "restart", "statefulset/db")
    _run_kubectl("rollout", "status", "statefulset/db", "--timeout=240s", timeout=260)

    # Пока база поднимается, readiness API красная (503); ждём, пока API снова увидит базу.
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if api.get("/ready").status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        pytest.fail("API не вернулся в готовность после перезапуска базы")

    after = api.get(f"/books/{book_id}")
    assert after.status_code == 200
    assert after.json()["title"] == unique_title


def _api_restart_total() -> int:
    """Сколько раз Kubernetes перезапускал контейнеры подов API (сумма: число подов может меняться при обновлении)."""
    out = subprocess.run(
        _kubectl(
            "get",
            "pods",
            "-l",
            "app=api",
            "-o",
            "jsonpath={.items[*].status.containerStatuses[*].restartCount}",
        ),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return sum(int(x) for x in out.split())


def test_api_reports_not_ready_while_database_is_down():
    """Когда базы нет, readiness API красная, а liveness зелёная: поды выводятся из балансировки, но не перезапускаются."""
    restarts_before = _api_restart_total()
    _run_kubectl("scale", "statefulset/db", "--replicas=0")
    try:
        _run_kubectl("wait", "--for=delete", "pod/db-0", "--timeout=120s", timeout=140)
        with httpx.Client(base_url=f"{SMOKE_URL}/api", timeout=10) as client:
            deadline = time.monotonic() + 60
            api_is_ready = True
            while time.monotonic() < deadline:
                try:
                    api_is_ready = client.get("/ready").status_code == 200
                except httpx.HTTPError:
                    # Готовых подов нет: в зависимости от окружения запрос получает 502/503 или зависает
                    # до таймаута. Оба исхода значат «не готов».
                    api_is_ready = False
                if not api_is_ready:
                    break
                time.sleep(1)
            assert not api_is_ready, "API остался «готовым» при недоступной базе"
            # Даём liveness-пробе время сработать несколько раз (период 10 с): перезапусков быть не должно.
            time.sleep(25)
            assert _api_restart_total() == restarts_before
    finally:
        _run_kubectl("scale", "statefulset/db", "--replicas=1")
        _run_kubectl("rollout", "status", "statefulset/db", "--timeout=240s", timeout=260)
        with httpx.Client(base_url=f"{SMOKE_URL}/api", timeout=10) as client:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                try:
                    if client.get("/ready").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)


def test_api_keeps_working_when_redis_is_down(api, unique_title, created_books):
    """Redis это ускоритель, а не источник правды: без него API отвечает (из Postgres), остаётся готовым
    (readiness от Redis не зависит), а после возвращения Redis кэш снова работает."""
    created = api.post(
        "/books",
        json={"title": unique_title, "author": "No cache", "year": 2024, "copies_available": 1},
    )
    created_books.append(created.json()["id"])

    _run_kubectl("scale", "deployment/redis", "--replicas=0")
    try:
        _run_kubectl(
            "wait", "--for=delete", "pod", "-l", "app=redis", "--timeout=120s", timeout=140
        )

        listing = api.get("/books")
        ready = api.get("/ready")

        assert listing.status_code == 200
        assert any(book["title"] == unique_title for book in listing.json())
        assert ready.status_code == 200
    finally:
        _run_kubectl("scale", "deployment/redis", "--replicas=1")
        _run_kubectl("rollout", "status", "deployment/redis", "--timeout=120s", timeout=140)

    # Redis вернулся пустым: первое чтение MISS, второе HIT.
    deadline = time.monotonic() + 30
    headers = []
    while time.monotonic() < deadline:
        api.get("/books")
        headers.append(api.get("/books").headers.get("X-Cache"))
        if headers[-1] == "HIT":
            break
        time.sleep(1)
    assert headers[-1] == "HIT", f"кэш не восстановился после возвращения Redis: {headers}"
