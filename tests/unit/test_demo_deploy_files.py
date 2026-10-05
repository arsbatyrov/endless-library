"""AUTH-021: the deployment files create demo accounts ONLY when asked (static checks; the cluster tests do the rest)."""

import re
from pathlib import Path

from app.demo import DEMO_ACCOUNTS

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


DEPLOY = read("k8s/deploy.sh")
JOB = read("k8s/seed-demo-job.yaml")
CI = read(".github/workflows/ci.yml")


def demo_block() -> str:
    start = DEPLOY.index('if [ "${DEMO:-}" = "1" ]; then')
    return DEPLOY[start : DEPLOY.index("\nfi\n", DEPLOY.index("else", start)) + 4]


# ---------- the job ----------


def test_the_job_runs_only_the_seed_demo_command_with_the_flag_it_demands():
    assert '["python", "-m", "app.cli", "seed-demo"]' in JOB
    assert re.search(r'name: DEMO_ACCOUNTS\s*\n\s*value: "true"', JOB)


def test_the_job_has_no_password_and_no_secret_other_than_the_database():
    assert "LIBRARY_USER_PASSWORD" not in JOB
    for account in DEMO_ACCOUNTS:
        assert account.password not in JOB
    assert JOB.count("secretKeyRef") == 1 and "endless-library-db" in JOB


def test_the_job_is_created_fresh_each_time_and_runs_unprivileged():
    assert "generateName: seed-demo-" in JOB and "ttlSecondsAfterFinished" in JOB
    assert "runAsNonRoot: true" in JOB and "allowPrivilegeEscalation: false" in JOB


# ---------- deploy.sh ----------


def test_the_demo_block_runs_only_with_demo_equal_to_1():
    assert 'if [ "${DEMO:-}" = "1" ]; then' in DEPLOY
    assert DEPLOY.count("seed-demo-job.yaml") == 1
    assert DEPLOY.index("seed-demo-job.yaml") > DEPLOY.index('if [ "${DEMO:-}" = "1" ]; then')


def test_no_demo_password_is_written_in_the_script():
    for account in DEMO_ACCOUNTS:
        assert account.password not in DEPLOY, (
            "the script must read the demo password from the command's output"
        )


def test_the_script_reads_the_demo_administrator_password_from_the_command_output():
    assert "demo-login:" in DEPLOY and '$2 == "admin"' in DEPLOY


def test_the_secret_is_patched_to_follow_the_demo_administrator_only_in_demo_mode():
    block = demo_block()

    assert re.search(r"^\s+k -n endless-library patch secret endless-library-admin", block, re.M)
    assert "patch secret" not in DEPLOY.replace(block, "")


def test_the_normal_path_removes_the_api_demo_flag_and_the_demo_path_sets_it():
    block = demo_block()
    demo_part, normal_part = block.split("else", 1)

    assert "DEMO_ACCOUNTS=true" in demo_part
    assert "DEMO_ACCOUNTS-" in normal_part


def test_the_first_admin_banner_is_not_shown_in_demo_mode():
    assert '[ "${DEMO:-}" != "1" ] && grep -q "^Created"' in DEPLOY


def test_the_demo_block_runs_before_the_api_restart_so_the_flag_takes_effect():
    assert DEPLOY.index('if [ "${DEMO:-}" = "1" ]; then') < DEPLOY.index(
        "rollout restart deployment/api"
    )


# ---------- compose, .env.example, CI ----------


def test_compose_defaults_the_flag_to_false():
    assert "DEMO_ACCOUNTS: ${DEMO_ACCOUNTS:-false}" in read("docker-compose.yml")


def test_the_env_template_has_the_flag_off():
    assert re.search(r"^DEMO_ACCOUNTS=false$", read(".env.example"), re.M)


def test_the_normal_ci_deploys_never_use_demo():
    normal = CI[
        CI.index("- name: Deploy the application") : CI.index("- name: Deploy with demo accounts")
    ]

    assert "DEMO=1" not in normal


def test_ci_runs_a_separate_demo_deploy_and_its_tests():
    assert "SKIP_BUILD=1 DEMO=1 bash k8s/deploy.sh" in CI
    assert "SMOKE_DEMO=1 pytest tests/smoke/test_demo_access.py" in CI


def test_the_demo_deploy_comes_after_the_checks_that_need_the_random_password():
    assert CI.index("Deploy again (nothing may change)") < CI.index(
        "Deploy with demo accounts (DEMO=1)"
    )
    assert CI.index("The admin still signs in after the second deploy") < CI.index(
        "Deploy with demo accounts (DEMO=1)"
    )


def test_the_published_images_and_manifests_do_not_enable_the_flag():
    for path in ("k8s/base/api.yaml", "Dockerfile", "docker-compose.yml"):
        text = read(path)
        assert not re.search(r"DEMO_ACCOUNTS[=:]\s*[\"']?true", text), path
