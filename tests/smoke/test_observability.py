"""Наблюдаемость в кластере: Prometheus собирает метрики API, а Grafana показывает готовый дашборд.

К Prometheus и Grafana обращаемся через прокси API-сервера Kubernetes (`kubectl get --raw`), поэтому
port-forward и свободные порты не нужны. Тесты пропускаются, если нет kubectl.
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

import pytest

from tests.db_utils import ROOT

KUBE_CONTEXT = os.getenv("SMOKE_KUBE_CONTEXT", "kind-endless-library")
DASHBOARD = ROOT / "k8s" / "monitoring" / "grafana" / "dashboards" / "endless-library.json"

pytestmark = pytest.mark.skipif(shutil.which("kubectl") is None, reason="kubectl is not installed")


def _raw(path: str) -> dict:
    out = subprocess.run(
        ["kubectl", "--context", KUBE_CONTEXT, "get", "--raw", path],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",  # the dashboard contains Cyrillic; on Windows the default would be cp1252
        timeout=30,
    ).stdout
    return json.loads(out)


def prometheus_query(expr: str) -> dict:
    return _raw(
        f"/api/v1/namespaces/monitoring/services/prometheus:9090/proxy/api/v1/query?query={quote(expr)}"
    )


def wait_for(check, timeout: float = 60, pause: float = 2):
    """Повторяет check(), пока он не вернёт истинное значение (его и возвращает) или не кончится время."""
    deadline = time.monotonic() + timeout
    result = check()
    while not result and time.monotonic() < deadline:
        time.sleep(pause)
        result = check()
    return result


def test_metrics_endpoint_is_not_reachable_from_outside(api):
    """/metrics открыт только внутри кластера (Prometheus ходит к подам напрямую); через вход его быть не должно."""
    assert api.get("/metrics").status_code == 404


def test_prometheus_scrapes_every_api_pod():
    def both_up():
        result = prometheus_query('up{job="api"}')["data"]["result"]
        return result if len(result) == 2 and all(r["value"][1] == "1" for r in result) else None

    assert wait_for(both_up), "Prometheus не видит оба пода API (или один из них недоступен)"


def test_prometheus_sees_user_traffic(api):
    for _ in range(5):
        api.get("/books")
        api.get("/books/999999999")  # 404: тоже должен попасть в метрики

    def seen():
        result = prometheus_query(
            'sum by (path, status) (endless_library_http_requests_total{path=~"/books.*"})'
        )["data"]["result"]
        found = {(r["metric"]["path"], r["metric"]["status"]) for r in result}
        return {("/books", "200"), ("/books/{book_id}", "404")} <= found

    assert wait_for(seen), "метрики запросов не появились в Prometheus"


def test_metric_labels_use_route_templates_so_cardinality_stays_low(api):
    api.get("/books/424242")
    api.get("/books/434343")

    paths = {
        r["metric"]["path"]
        for r in prometheus_query("endless_library_http_requests_total")["data"]["result"]
    }

    assert "/books/424242" not in paths
    assert "/books/434343" not in paths


def test_grafana_is_healthy_and_has_the_provisioned_dashboard():
    base = "/api/v1/namespaces/monitoring/services/grafana:3000/proxy"

    health = _raw(f"{base}/api/health")
    found = wait_for(lambda: _raw(f"{base}/api/search?query=Library"))

    assert health["database"] == "ok"
    assert [d["uid"] for d in found] == ["endless-library"]


def test_every_dashboard_query_is_valid_promql():
    """Опечатка в выражении дашборда не видна, пока не откроешь панель. Здесь каждое выражение выполняется в Prometheus."""
    dashboard = json.loads(Path(DASHBOARD).read_text(encoding="utf-8"))
    expressions = [t["expr"] for panel in dashboard["panels"] for t in panel["targets"]]

    assert len(expressions) >= 10
    for expr in expressions:
        assert prometheus_query(expr)["status"] == "success", expr


def test_grafana_is_reachable_by_its_host_name_through_the_ingress():
    """http://grafana.localhost:8080 открывает Grafana, а запросы к остальным именам по-прежнему идут в приложение.

    Имя подставляем заголовком Host: резолвер Windows и Python не всегда знают имена *.localhost (браузеры знают).
    """
    import httpx2 as httpx

    from tests.smoke.conftest import SMOKE_URL

    with httpx.Client(base_url=SMOKE_URL, timeout=10) as client:
        grafana = client.get("/api/health", headers={"Host": "grafana.localhost"})
        library = client.get("/api/health")  # путь тот же, имя обычное: должно отвечать приложение

    assert grafana.status_code == 200
    assert grafana.json()["database"] == "ok"
    assert library.json() == {"status": "ok"}


def test_prometheus_sees_the_sign_in_metrics(admin_credentials):
    """AUTH-016: a successful and a failed sign-in through the real entrance show up as counters in Prometheus."""
    import httpx2 as httpx

    from tests.smoke.conftest import SMOKE_URL

    username, password = admin_credentials
    with httpx.Client(base_url=f"{SMOKE_URL}/api", timeout=10) as client:
        assert (
            client.post(
                "/auth/login", json={"username": username, "password": password}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/auth/login", json={"username": username, "password": "wrong password"}
            ).status_code
            == 401
        )
        assert client.post("/auth/refresh").status_code == 200

    def seen():
        logins = prometheus_query("sum by (result) (endless_library_auth_logins_total)")["data"][
            "result"
        ]
        refreshes = prometheus_query("sum by (result) (endless_library_auth_refresh_total)")[
            "data"
        ]["result"]
        by_login = {r["metric"]["result"]: float(r["value"][1]) for r in logins}
        by_refresh = {r["metric"]["result"]: float(r["value"][1]) for r in refreshes}
        ok = (
            by_login.get("success", 0) >= 1
            and by_login.get("failure", 0) >= 1
            and by_refresh.get("ok", 0) >= 1
        )
        return (
            ok
            and {"success", "failure", "locked"} <= set(by_login)
            and {"ok", "rejected"} <= set(by_refresh)
        )

    assert wait_for(seen), "the sign-in counters did not reach Prometheus"


def test_the_dashboard_has_the_sign_in_panels_in_grafana():
    base = "/api/v1/namespaces/monitoring/services/grafana:3000/proxy"

    def titles():
        dashboard = _raw(f"{base}/api/dashboards/uid/endless-library")["dashboard"]
        found = {panel["title"] for panel in dashboard["panels"]}
        return found if {"Входы по результатам", "Заблокированные входы"} <= found else None

    assert wait_for(titles), "the sign-in panels are not in the provisioned dashboard"
