"""AUTH-016: the Grafana dashboard shows the sign-in metrics (acceptance criterion 4).

Static checks of the dashboard file; the cluster smoke test asks Prometheus whether every query is valid.
"""

import json
import re
from pathlib import Path

from prometheus_client import REGISTRY

import app.metrics  # noqa: F401  (registers the metrics)

DASHBOARD = (
    Path(__file__).resolve().parents[2]
    / "k8s"
    / "monitoring"
    / "grafana"
    / "dashboards"
    / "endless-library.json"
)
DATA = json.loads(DASHBOARD.read_text(encoding="utf-8"))
PANELS = {panel["title"]: panel for panel in DATA["panels"]}


def expressions(panel) -> list[str]:
    return [target["expr"] for target in panel["targets"]]


def test_the_sign_in_panels_exist():
    assert "Входы по результатам" in PANELS
    assert "Заблокированные входы" in PANELS


def test_logins_by_result_is_a_graph_split_by_the_result_label():
    panel = PANELS["Входы по результатам"]

    assert panel["type"] == "timeseries"
    assert any(
        "endless_library_auth_logins_total" in e and "by (result)" in e for e in expressions(panel)
    )
    assert any(t["legendFormat"] == "{{result}}" for t in panel["targets"])


def test_locked_logins_looks_at_the_locked_result_only():
    panel = PANELS["Заблокированные входы"]

    assert any(
        'endless_library_auth_logins_total{result="locked"}' in e for e in expressions(panel)
    )


def test_there_is_a_panel_for_token_refreshes_too():
    panel = next(
        p
        for t, p in PANELS.items()
        if "endless_library_auth_refresh_total" in " ".join(expressions(p))
    )

    assert any("by (result)" in e for e in expressions(panel))


def test_every_panel_has_a_unique_id_and_a_position_that_does_not_overlap():
    ids = [p["id"] for p in DATA["panels"]]
    assert len(ids) == len(set(ids))

    cells = set()
    for panel in DATA["panels"]:
        grid = panel["gridPos"]
        for x in range(grid["x"], grid["x"] + grid["w"]):
            for y in range(grid["y"], grid["y"] + grid["h"]):
                assert (x, y) not in cells, f"panel {panel['title']!r} overlaps another one"
                cells.add((x, y))
        assert grid["x"] + grid["w"] <= 24


def test_every_endless_library_metric_in_the_dashboard_exists_in_the_code():
    registered = {family.name for family in REGISTRY.collect()}
    # counters are registered as <name> and exposed as <name>_total; histograms add _bucket, _sum, _count
    names = set()
    for panel in DATA["panels"]:
        for expr in expressions(panel):
            names.update(re.findall(r"endless_library_[a-z_]+", expr))
    for name in names:
        base = re.sub(r"_(total|bucket|sum|count)$", "", name)
        assert base in registered or name in registered, (
            f"{name} is used in the dashboard but not defined"
        )


def test_the_panels_use_the_prometheus_data_source_like_the_others():
    for panel in DATA["panels"]:
        assert panel["datasource"] == {"type": "prometheus", "uid": "prometheus"}
        assert all(
            t["datasource"] == {"type": "prometheus", "uid": "prometheus"} for t in panel["targets"]
        )
