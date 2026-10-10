"""TEST-007: the pytest settings that make a typo in a marker and a forgotten xfail visible must not be removed."""

import configparser
from pathlib import Path

PYTEST_INI = Path(__file__).resolve().parents[2] / "pytest.ini"


def pytest_section() -> configparser.SectionProxy:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(PYTEST_INI, encoding="utf-8")
    return parser["pytest"]


def test_unknown_markers_are_an_error():
    assert "--strict-markers" in pytest_section()["addopts"].split()


def test_an_unexpected_pass_of_an_xfail_test_is_a_failure():
    assert pytest_section()["xfail_strict"].strip().lower() == "true"
