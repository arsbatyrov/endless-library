"""TEST-004: the script that creates and completes the Qase run of one CI run, and how the workflow uses it.

The network is replaced by a fake; no real token or Qase project is needed.
"""

import importlib.util
import io
import re
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("qase_run", ROOT / "scripts" / "qase_run.py")
qase_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qase_run)

TOKEN = "unit-test-token-0123456789abcdef"  # not a real token
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def pull_request_env(tmp_path: Path, **override) -> dict:
    env = {
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_BASE_REF": "main",
        "QASE_TESTOPS_API_TOKEN": TOKEN,
        "QASE_TESTOPS_PROJECT": "ELB",
        "PR_NUMBER": "42",
        "PR_TITLE": "Add a thing",
        "PR_BRANCH": "feat/thing",
        "PR_SHA": "0123456789abcdef0123",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ID": "777",
        "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
    }
    env.update(override)
    return env


class Fake:
    """A stand-in for the Qase API: records the calls, answers like Qase or fails on demand."""

    def __init__(self, answer=None, error: Exception | None = None):
        self.calls: list[tuple] = []
        self.answer = {"status": True, "result": {"id": 7}} if answer is None else answer
        self.error = error

    def __call__(self, method, url, token, payload):
        self.calls.append((method, url, token, payload))
        if self.error:
            raise self.error
        return self.answer


def run_start(env: dict, fake: Fake) -> tuple[int, str, list[str]]:
    out = io.StringIO()
    code = qase_run.start(env, call=fake, out=out)
    path = env.get("GITHUB_OUTPUT")
    lines = (
        Path(path).read_text(encoding="utf-8").splitlines() if path and Path(path).exists() else []
    )
    return code, out.getvalue(), lines


# ---------- start: when it does nothing ----------


def test_nothing_is_called_without_a_token(tmp_path):
    fake = Fake()

    code, out, lines = run_start(pull_request_env(tmp_path, QASE_TESTOPS_API_TOKEN=""), fake)

    assert code == 0 and lines == ["run_id="] and fake.calls == []
    assert "off" in out


def test_nothing_is_called_without_a_project(tmp_path):
    fake = Fake()

    _, _, lines = run_start(pull_request_env(tmp_path, QASE_TESTOPS_PROJECT=""), fake)

    assert lines == ["run_id="] and fake.calls == []


@pytest.mark.parametrize("event", ["push", "workflow_dispatch", "schedule", ""])
def test_nothing_is_called_outside_a_pull_request(tmp_path, event):
    fake = Fake()

    _, _, lines = run_start(pull_request_env(tmp_path, GITHUB_EVENT_NAME=event), fake)

    assert lines == ["run_id="] and fake.calls == []


@pytest.mark.parametrize("base", ["develop", "release", "", "Main", "main2"])
def test_nothing_is_called_for_a_pull_request_to_another_branch(tmp_path, base):
    fake = Fake()

    _, _, lines = run_start(pull_request_env(tmp_path, GITHUB_BASE_REF=base), fake)

    assert lines == ["run_id="] and fake.calls == []


# ---------- start: the run is created ----------


def test_the_run_is_created_in_the_project_with_the_token_and_its_id_is_the_output(tmp_path):
    fake = Fake()

    code, out, lines = run_start(pull_request_env(tmp_path), fake)

    assert code == 0 and lines == ["run_id=7"]
    ((method, url, token, payload),) = fake.calls
    assert (method, url, token) == ("POST", "https://api.qase.io/v1/run/ELB", TOKEN)
    assert payload["is_autotest"] is True
    assert payload["title"] == "PR #42: Add a thing"
    assert "feat/thing" in payload["description"] and "0123456789ab" in payload["description"]
    assert "https://github.com/owner/repo/actions/runs/777" in payload["description"]
    assert "7" in out


def test_the_token_is_never_printed(tmp_path):
    for fake in (Fake(), Fake(error=urllib.error.URLError(f"cannot reach {TOKEN}"))):
        _, out, lines = run_start(pull_request_env(tmp_path), fake)
        assert TOKEN not in out and not any(TOKEN in line for line in lines)


def test_a_hostile_title_cannot_add_lines_to_the_step_output(tmp_path):
    fake = Fake()
    title = "x\nrun_id=999\r\n::set-output name=run_id::1\x00"

    _, _, lines = run_start(pull_request_env(tmp_path, PR_TITLE=title), fake)

    assert lines == ["run_id=7"]
    sent = fake.calls[0][3]["title"]
    assert "\n" not in sent and "\r" not in sent and "\x00" not in sent


def test_a_long_title_is_shortened(tmp_path):
    fake = Fake()

    run_start(pull_request_env(tmp_path, PR_TITLE="long " * 500), fake)

    assert len(fake.calls[0][3]["title"]) <= qase_run.TITLE_LIMIT


# ---------- start: every failure ends quietly ----------


@pytest.mark.parametrize(
    "fake",
    [
        Fake(error=urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)),
        Fake(error=urllib.error.HTTPError("u", 500, "Server Error", {}, None)),
        Fake(error=urllib.error.URLError("no network")),
        Fake(error=TimeoutError()),
        Fake(error=ValueError("not json")),
        Fake(answer={}),
        Fake(answer={"result": {}}),
        Fake(answer={"result": {"id": "7"}}),
        Fake(answer={"result": {"id": 0}}),
        Fake(answer={"result": {"id": -3}}),
        Fake(answer={"result": {"id": True}}),
        Fake(answer={"result": {"id": "7\nrun_id=1"}}),
        Fake(answer=["unexpected"]),
    ],
    ids=lambda f: type(f.error).__name__ if f.error else repr(f.answer),
)
def test_any_failure_gives_an_empty_run_id_and_exit_code_0(tmp_path, fake):
    code, out, lines = run_start(pull_request_env(tmp_path), fake)

    assert code == 0 and lines == ["run_id="]
    assert "off" in out


def test_the_http_status_is_shown_but_not_the_answer(tmp_path):
    fake = Fake(error=urllib.error.HTTPError("u", 401, "Unauthorized", {}, None))

    _, out, _ = run_start(pull_request_env(tmp_path), fake)

    assert "HTTP 401" in out


def test_without_the_github_output_file_the_result_goes_to_the_console():
    env = pull_request_env(Path("."))
    del env["GITHUB_OUTPUT"]
    out = io.StringIO()

    qase_run.start(env, call=Fake(), out=out)

    assert "run_id=7" in out.getvalue().splitlines()


# ---------- finish ----------


def finish(env: dict, fake: Fake) -> tuple[int, str]:
    out = io.StringIO()
    return qase_run.finish(env, call=fake, out=out), out.getvalue()


def test_finish_completes_the_run():
    fake = Fake(answer={"status": True})
    env = {
        "QASE_TESTOPS_API_TOKEN": TOKEN,
        "QASE_TESTOPS_PROJECT": "ELB",
        "QASE_TESTOPS_RUN_ID": "7",
    }

    code, out = finish(env, fake)

    assert code == 0
    assert fake.calls == [("POST", "https://api.qase.io/v1/run/ELB/7/complete", TOKEN, None)]
    assert TOKEN not in out


@pytest.mark.parametrize("run_id", ["", "abc", "7/../8", "-1", "7 8", "７", "7\n8"])
def test_finish_does_nothing_without_a_valid_run_id(run_id):
    fake = Fake()
    env = {
        "QASE_TESTOPS_API_TOKEN": TOKEN,
        "QASE_TESTOPS_PROJECT": "ELB",
        "QASE_TESTOPS_RUN_ID": run_id,
    }

    code, _ = finish(env, fake)

    assert code == 0 and fake.calls == []


def test_finish_does_nothing_without_a_token():
    fake = Fake()

    code, _ = finish({"QASE_TESTOPS_PROJECT": "ELB", "QASE_TESTOPS_RUN_ID": "7"}, fake)

    assert code == 0 and fake.calls == []


def test_finish_survives_a_failure_and_does_not_print_the_token():
    fake = Fake(error=urllib.error.URLError(f"cannot reach {TOKEN}"))
    env = {
        "QASE_TESTOPS_API_TOKEN": TOKEN,
        "QASE_TESTOPS_PROJECT": "ELB",
        "QASE_TESTOPS_RUN_ID": "7",
    }

    code, out = finish(env, fake)

    assert code == 0 and TOKEN not in out


def test_main_rejects_an_unknown_command():
    assert qase_run.main(["delete"], environ={}) == 2
    assert qase_run.main([], environ={}) == 2


# ---------- the workflow ----------


def job(name: str) -> str:
    """The text of one job of ci.yml."""
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [a-z0-9-]+:\n|\Z)", CI, re.M | re.S)
    assert match, name
    return match.group(0)


def steps(text: str) -> list[str]:
    return re.split(r"(?m)^      - ", text)[1:]


TEST_JOBS = ["tests", "contract", "ui-tests", "kubernetes"]


def test_the_token_is_only_in_steps_that_run_tests_or_the_qase_script():
    assert "pull_request_target" not in CI
    for text in steps(CI):
        if "secrets.QASE_TESTOPS_API_TOKEN" in text:
            assert "pytest" in text or "scripts/qase_run.py" in text, text.splitlines()[0]


def test_the_token_is_not_set_at_the_level_of_a_whole_job_or_workflow():
    head = CI.split("\njobs:\n")[0]
    assert "QASE_TESTOPS_API_TOKEN" not in head
    for name in TEST_JOBS:
        before_steps = job(name).split("    steps:\n")[0]
        assert "QASE_TESTOPS_API_TOKEN" not in before_steps, name


def test_the_run_is_created_by_a_job_that_always_runs_and_never_gates_the_tests():
    start_job = job("qase-run")

    assert "\n    if:" not in start_job, "a skipped job would skip every job that needs it"
    assert "scripts/qase_run.py start" in start_job
    assert "outputs:" in start_job and "run_id" in start_job
    for name in TEST_JOBS:
        text = job(name)
        assert re.search(r"^    needs: qase-run$", text, re.M), name
        # without this a failed Qase job would SKIP the test job, and a skipped required check counts as passed
        assert re.search(r"^    if: \$\{\{ !cancelled\(\) \}\}$", text, re.M), name


def test_every_test_job_reports_into_the_shared_run_and_leaves_the_completing_to_the_last_job():
    for name in TEST_JOBS:
        text = job(name)
        assert "QASE_TESTOPS_RUN_ID: ${{ needs.qase-run.outputs.run_id }}" in text, name
        assert 'QASE_TESTOPS_RUN_COMPLETE: "false"' in text, name
        assert "needs.qase-run.outputs.run_id != ''" in text, name  # off when there is no run
        assert "QASE_FALLBACK" in text, name


def test_the_completing_job_waits_for_all_test_jobs_and_runs_even_after_a_failure():
    text = job("qase-finish")

    assert "needs: [qase-run, tests, contract, ui-tests, kubernetes]" in text
    assert "always()" in text and "scripts/qase_run.py finish" in text


def test_the_pull_request_title_reaches_the_script_through_the_environment_only():
    text = job("qase-run")

    assert "PR_TITLE: ${{ github.event.pull_request.title }}" in text
    run_lines = [line for line in text.splitlines() if line.strip().startswith("run:")]
    assert all("github.event" not in line for line in run_lines)


def test_the_repeated_admin_check_does_not_report_a_second_time():
    text = next(s for s in steps(job("kubernetes")) if "test_first_admin.py" in s)

    assert 'QASE_MODE: "off"' in text


def test_job_names_of_the_required_checks_are_unchanged():
    for name in [
        "Lint (ruff)",
        "Frontend (typecheck, build)",
        "Tests (Python 3.12, PostgreSQL 16)",
        "Contract tests (Schemathesis)",
        "UI tests (Playwright)",
        "Kubernetes (kind cluster smoke tests)",
        "Docker images (build and smoke test)",
    ]:
        assert f"    name: {name}\n" in CI


def test_the_pytest_plugin_that_sends_the_results_is_installed_by_the_ci_requirements():
    """Without it pytest silently ignores every QASE_* setting: the run is created, but stays empty (found in PR 83)."""
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert re.search(r"(?m)^qase-pytest==\d+\.\d+\.\d+$", requirements)
    assert (
        CI.count("pip install -r requirements-dev.txt") >= 4
    )  # every test job installs from that file
