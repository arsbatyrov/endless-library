"""AUTH-012: the deployment files create the first admin safely (acceptance criteria 2-4).

These are static checks of the files; the real behaviour is checked by the Kubernetes job in CI
(tests/smoke/test_first_admin.py and the second deploy there).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


DEPLOY = read("k8s/deploy.sh")
JOB = read("k8s/create-admin-job.yaml")


# ---------- the Job ----------


def test_the_job_runs_the_cli_with_skip_if_exists():
    assert '"app.cli"' in JOB
    assert '"create-user"' in JOB
    assert '"--skip-if-exists"' in JOB
    assert '"admin"' in JOB


def test_the_job_takes_the_password_from_a_secret_never_from_the_command_line():
    assert "LIBRARY_USER_PASSWORD" in JOB
    assert re.search(
        r"LIBRARY_USER_PASSWORD\s*\n\s*valueFrom:\s*\{secretKeyRef:\s*\{name: endless-library-admin",
        JOB,
    )
    command = re.search(r"command:\s*(\[.*\])", JOB).group(1)
    assert "password" not in command.lower()


def test_the_job_has_no_literal_password():
    assert not re.search(r"value:\s*\S*pass", JOB, re.IGNORECASE)


def test_the_job_is_created_fresh_every_time_and_cleans_up():
    assert "generateName: create-admin-" in JOB
    assert "ttlSecondsAfterFinished" in JOB


def test_the_job_runs_as_the_same_unprivileged_user_as_the_api():
    assert "runAsNonRoot: true" in JOB
    assert "allowPrivilegeEscalation: false" in JOB


# ---------- deploy.sh ----------


def test_the_admin_secret_is_created_only_when_missing():
    block = DEPLOY[DEPLOY.index("endless-library-admin") - 200 :]

    assert re.search(r"if ! k -n endless-library get secret endless-library-admin", block)


def test_the_admin_password_is_random_and_comes_from_openssl():
    assert re.search(r'admin_password="\$\(openssl rand -hex 16\)"', DEPLOY)


def test_the_jwt_secret_is_still_created_only_when_missing_and_separately():
    assert re.search(r"if ! k -n endless-library get secret endless-library-jwt", DEPLOY)
    assert "endless-library-admin" != "endless-library-jwt"


def test_the_admin_job_runs_after_the_migrations_and_before_the_api_restart():
    migrate = DEPLOY.index("alembic") if "alembic" in DEPLOY else DEPLOY.index("migrate-job.yaml")
    admin = DEPLOY.index("create-admin-job.yaml")
    restart = DEPLOY.index("rollout restart deployment/api")

    assert migrate < admin < restart


def test_the_password_is_shown_only_when_the_admin_was_really_created_in_this_run():
    guard = DEPLOY.index('grep -q "^Created"')
    read_back = DEPLOY.index("shown_password=")
    printed = [m.start() for m in re.finditer(r"echo .*\$\{shown_password\}", DEPLOY)]

    assert printed, "the script must show the password once"
    assert guard < read_back < min(printed)
    # nothing else in the script prints a password variable
    assert not re.search(r"echo .*\$\{?admin_password", DEPLOY)


def test_the_script_never_passes_the_password_as_an_argument_to_the_job():
    assert "--password" not in DEPLOY
    assert not re.search(r"create-user[^\n]*\$\{?admin_password", DEPLOY)


def test_the_script_tells_where_the_password_is_kept():
    assert "get secret endless-library-admin" in DEPLOY


# ---------- Docker Compose and the CI job ----------

CI = read(".github/workflows/ci.yml")
DOCKER_JOB = CI[CI.index("  docker:") :]


def test_compose_passes_the_jwt_secret_and_the_switch():
    compose = read("docker-compose.yml")

    assert "JWT_SECRET: ${JWT_SECRET:-}" in compose
    assert "AUTH_REQUIRED" in compose


def test_the_docker_ci_job_generates_a_jwt_secret_and_turns_the_protection_on():
    assert 'sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env' in DOCKER_JOB
    assert re.search(r"AUTH_REQUIRED=true", DOCKER_JOB)


def test_the_docker_ci_job_expects_401_without_a_login_and_data_with_one():
    assert re.search(r"/api/books[^\n]*401|401[^\n]*/api/books", DOCKER_JOB)
    assert "/api/auth/login" in DOCKER_JOB
    assert "app.cli create-user" in DOCKER_JOB


def test_the_docker_ci_job_never_puts_the_password_on_a_command_line_of_the_cli():
    cli_lines = [line for line in DOCKER_JOB.splitlines() if "app.cli" in line]

    assert cli_lines
    assert all("--password" not in line for line in cli_lines)


def test_the_kubernetes_ci_job_deploys_twice_and_checks_that_nothing_changed():
    kube = CI[CI.index("  kubernetes:") : CI.index("  docker:")]

    assert kube.count("deploy.sh") >= 2
    assert "endless-library-admin" in kube
    assert "endless-library-jwt" in kube
