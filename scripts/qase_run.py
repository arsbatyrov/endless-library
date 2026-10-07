"""One Qase test run per CI run (TEST-004).

    python scripts/qase_run.py start     creates the run, writes `run_id=<number>` to $GITHUB_OUTPUT
    python scripts/qase_run.py finish    completes the run whose id is in QASE_TESTOPS_RUN_ID

The test jobs report their results into this run (`QASE_TESTOPS_RUN_ID`), so one run in Qase is one CI run.

Reporting is a convenience, never a gate: every problem (no token, a fork, Qase unreachable, a strange answer) ends in
an EMPTY run id and exit code 0, and the test jobs then simply do not report. Only the standard library is used. The
token is read from the environment and is never printed; of a failed request only the status code is shown.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import TextIO

API = "https://api.qase.io/v1"
TIMEOUT_SECONDS = 20
TITLE_LIMIT = 200
DESCRIPTION_LIMIT = 2000

Send = Callable[[str, str, str, dict | None], dict]


def send(method: str, url: str, token: str, payload: dict | None) -> dict:
    """One call to the Qase API; returns the decoded JSON answer or raises."""
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Token": token, "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read() or b"{}")


def _failure_reason(error: Exception) -> str:
    """A short, safe description: the status code or the kind of error, never a body or a header."""
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTP {error.code}"
    return type(error).__name__


def _clean(text: str, limit: int) -> str:
    """One line, no control characters, shortened: the text comes from a pull request title."""
    flat = "".join(ch if ch.isprintable() else " " for ch in text).strip()
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _write_output(run_id: str, path: str | None, out: TextIO) -> None:
    """The step output for the next jobs (GitHub's file), or the console when run by hand. Only a number is written."""
    line = f"run_id={run_id}\n"
    if path:
        with open(path, "a", encoding="utf-8") as output:
            output.write(line)
    else:
        out.write(line)


def start(environ: Mapping[str, str], *, call: Send = send, out: TextIO = sys.stdout) -> int:
    token = environ.get("QASE_TESTOPS_API_TOKEN", "")
    project = environ.get("QASE_TESTOPS_PROJECT", "")
    output_path = environ.get("GITHUB_OUTPUT")
    reason = None
    if environ.get("GITHUB_EVENT_NAME") != "pull_request":
        reason = "this run is not a pull request"
    elif environ.get("GITHUB_BASE_REF") != "main":
        reason = "the pull request does not target main"
    elif not token or not project:
        reason = "no token or project is available (a fork, Dependabot or not configured)"
    if reason:
        print(f"Qase reporting is off: {reason}.", file=out)
        _write_output("", output_path, out)
        return 0

    number = _clean(environ.get("PR_NUMBER", ""), 20)
    title = _clean(f"PR #{number}: {environ.get('PR_TITLE', '')}", TITLE_LIMIT)
    run_url = "{}/{}/actions/runs/{}".format(
        environ.get("GITHUB_SERVER_URL", "https://github.com"),
        environ.get("GITHUB_REPOSITORY", ""),
        environ.get("GITHUB_RUN_ID", ""),
    )
    description = _clean(
        f"Branch {environ.get('PR_BRANCH', '')}, commit {environ.get('PR_SHA', '')[:12]}. CI run: {run_url}",
        DESCRIPTION_LIMIT,
    )
    payload = {"title": title, "description": description, "is_autotest": True}
    try:
        answer = call("POST", f"{API}/run/{project}", token, payload)
        run_id = answer["result"]["id"]
        if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
            raise ValueError("unexpected run id")
    except Exception as error:  # reporting must never fail the build
        print(
            f"Qase reporting is off: could not create the run ({_failure_reason(error)}).", file=out
        )
        _write_output("", output_path, out)
        return 0
    print(f"Qase run {run_id} created.", file=out)
    _write_output(str(run_id), output_path, out)
    return 0


def finish(environ: Mapping[str, str], *, call: Send = send, out: TextIO = sys.stdout) -> int:
    token = environ.get("QASE_TESTOPS_API_TOKEN", "")
    project = environ.get("QASE_TESTOPS_PROJECT", "")
    run_id = environ.get("QASE_TESTOPS_RUN_ID", "")
    if not (token and project and run_id.isascii() and run_id.isdigit()):
        print("Qase: no run to complete.", file=out)
        return 0
    try:
        call("POST", f"{API}/run/{project}/{run_id}/complete", token, None)
    except Exception as error:
        print(f"Qase: could not complete the run ({_failure_reason(error)}).", file=out)
        return 0
    print(f"Qase run {run_id} completed.", file=out)
    return 0


def main(
    argv: list[str] | None = None, *, environ: Mapping[str, str] | None = None, call: Send = send
) -> int:
    args = sys.argv[1:] if argv is None else argv
    environ = os.environ if environ is None else environ
    if args == ["start"]:
        return start(environ, call=call)
    if args == ["finish"]:
        return finish(environ, call=call)
    print("usage: qase_run.py start|finish", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
