"""Require the maintained CI's ci-ok check on the exact commit being released.

The Release preflight calls this with a read-only GitHub token. It deliberately does not wait
for CI: an absent, running or failed check blocks the release; rerun after CI succeeds. Only
push runs of .github/workflows/ci.yml count, never Release itself or a PR's synthetic merge.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime

API_VERSION = "2026-03-10"
WORKFLOW = ".github/workflows/ci.yml"


class CIGateError(Exception):
    """CI evidence is absent, unsuccessful, inconsistent or cannot be read."""


def github_json(endpoint: str) -> dict:
    """GitHub CLI supplies the runner's GH_TOKEN; never put it in arguments or logs."""
    try:
        done = subprocess.run(
            ["gh", "api", "--method", "GET", "-H", "Accept: application/vnd.github+json",
             "-H", f"X-GitHub-Api-Version: {API_VERSION}", endpoint],
            capture_output=True, text=True, check=True, timeout=30)
        value = json.loads(done.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise CIGateError(f"cannot read GitHub CI evidence ({type(error).__name__})") from error
    if not isinstance(value, dict):
        raise CIGateError("GitHub returned a non-object response")
    return value


def _records(endpoint: str, key: str, get: Callable[[str], dict]) -> list[dict]:
    """Bound pagination and fail closed on a truncated or changing result set."""
    items: list[dict] = []
    total = None
    for page in range(1, 11):
        value = get(f"{endpoint}&per_page=100&page={page}")
        count, batch = value.get("total_count"), value.get(key)
        if (type(count) is not int or not 0 <= count <= 1000 or not isinstance(batch, list)
                or any(not isinstance(item, dict) for item in batch)
                or (total is not None and count != total)):
            raise CIGateError("incomplete or changing GitHub CI evidence")
        total = count
        items.extend(batch)
        if len(items) == total:
            return items
        if len(items) > total or len(batch) != 100:
            break
    raise CIGateError("incomplete GitHub CI evidence")


def _timestamp(run: dict, field: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(run.get(field, ""))
    except (TypeError, ValueError) as error:
        raise CIGateError(f"CI run has no valid {field} timestamp") from error
    if timestamp.tzinfo is None:
        raise CIGateError(f"CI run has no timezone in its {field} timestamp")
    return timestamp


def _required_runs(repo: str, sha: str, get: Callable[[str], dict]) -> list[dict]:
    runs = _records(f"repos/{repo}/actions/workflows/ci.yml/runs?head_sha={sha}&event=push",
                    "workflow_runs", get)
    if not runs:
        raise CIGateError(f"no push run of {WORKFLOW} for {sha}")
    created, updated = {}, {}
    for run in runs:
        repository = run.get("repository")
        if (run.get("head_sha") != sha or run.get("event") != "push"
                or str(run.get("path", "")).split("@", 1)[0] != WORKFLOW
                or not isinstance(repository, dict)
                or str(repository.get("full_name", "")).lower() != repo.lower()
                or any(type(run.get(field)) is not int or run[field] < 1
                       for field in ("id", "run_number", "run_attempt", "check_suite_id"))):
            raise CIGateError("CI run identity does not match the release repository and commit")
        created[run["id"]] = _timestamp(run, "created_at")
        updated[run["id"]] = _timestamp(run, "updated_at")
        if updated[run["id"]] < created[run["id"]]:
            raise CIGateError("CI run update precedes its creation")
    if any(len({run[field] for run in runs}) != len(runs) for field in ("id", "run_number")):
        raise CIGateError("duplicate CI run identities")
    latest = max(runs, key=lambda run: run["run_number"])
    # updated_at is an activity/completion timestamp, not an ordering of starts. A long-running
    # older success must not hide a newer queued or failed run. Conversely, run_number alone
    # would hide a recent rerun of an older run. Require the newest run AND every older run
    # updated since its creation; reject all unfinished runs regardless of their timestamps.
    for run in runs:
        if run.get("status") != "completed":
            raise CIGateError(f"CI run {run['id']} attempt {run['run_attempt']} "
                              "has not completed successfully")
    required = sorted((run for run in runs if run["id"] == latest["id"]
                       or updated[run["id"]] >= created[latest["id"]]),
                      key=lambda run: run["run_number"], reverse=True)
    for run in required:
        # ci.yml groups push runs by commit and a newer queued run replaces a waiting one, so
        # pushing one commit to several branches can leave an older run cancelled after the
        # newest run was created. A cancelled run completed no test suite: it is evidence neither
        # for nor against the commit, and the newest run of the same commit must still succeed.
        # Failures, timeouts and skips block; so does a cancelled newest run.
        superseded = run["id"] != latest["id"] and run.get("conclusion") == "cancelled"
        if run.get("conclusion") != "success" and not superseded:
            raise CIGateError(f"CI run {run['id']} attempt {run['run_attempt']} "
                              "has not completed successfully")
    # A cancelled run has no ci-ok check to bind; only successful runs are evidence.
    return [run for run in required if run.get("conclusion") == "success"]


def require_ci(repo: str, sha: str, *, get: Callable[[str], dict] = github_json) -> dict:
    """Return the accepted run/check identities, or refuse publication.

    Bind every required check to its CI workflow's check suite and re-read the required runs
    after checking them. A successful old attempt cannot hide pending work or a recent failure.
    This is a point-in-time gate, not a replacement for branch/tag/environment protection.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo):
        raise CIGateError("repository must be owner/repo")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise CIGateError("commit must be an exact, dereferenced SHA")
    runs = _required_runs(repo, sha, get)
    evidence = []
    for run in runs:
        checks = _records(f"repos/{repo}/check-suites/{run['check_suite_id']}/check-runs"
                          "?check_name=ci-ok&filter=latest", "check_runs", get)
        if len(checks) != 1:
            raise CIGateError("expected exactly one current ci-ok check in the CI run")
        check = checks[0]
        app, suite = check.get("app"), check.get("check_suite")
        if (check.get("name") != "ci-ok" or check.get("head_sha") != sha
                or not isinstance(app, dict) or app.get("slug") != "github-actions"
                or not isinstance(suite, dict) or suite.get("id") != run["check_suite_id"]
                or type(check.get("id")) is not int or check["id"] < 1):
            raise CIGateError("ci-ok identity does not match the CI run and release commit")
        if check.get("status") != "completed" or check.get("conclusion") != "success":
            raise CIGateError("ci-ok has not completed successfully on the release commit")
        evidence.append({"run_id": run["id"], "run_attempt": run["run_attempt"],
                         "check_run_id": check["id"]})
    current = _required_runs(repo, sha, get)
    fields = ("id", "run_attempt", "check_suite_id")
    if ({tuple(run[field] for field in fields) for run in current}
            != {tuple(run[field] for field in fields) for run in runs}):
        raise CIGateError("CI changed while checking the release commit; retry preflight")
    return {"sha": sha, "runs": evidence}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args(argv)
    try:
        evidence = require_ci(args.repo, args.sha)
    except CIGateError as error:
        print(f"release_ci: {error}", file=sys.stderr)
        return 1
    for run in evidence["runs"]:
        print(f"ci-ok succeeded for {evidence['sha']} (CI run {run['run_id']}, "
              f"attempt {run['run_attempt']}, check {run['check_run_id']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
