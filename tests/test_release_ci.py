"""Release CI evidence is bound to one repository, workflow, commit and current attempt."""
from __future__ import annotations

import json
import os
import subprocess
from copy import deepcopy
from types import SimpleNamespace

import pytest
import yaml

from tests.conftest import ROOT
from tools import release_ci

SHA = "a" * 40
REPO = "yoch/symq"


@pytest.fixture
def run():
    return {"id": 12, "run_number": 2, "run_attempt": 1, "head_sha": SHA,
            "event": "push", "path": ".github/workflows/ci.yml", "check_suite_id": 42,
            "created_at": "2026-11-12T10:00:00Z", "updated_at": "2026-11-12T10:00:00Z",
            "repository": {"full_name": REPO}, "status": "completed", "conclusion": "success"}


@pytest.fixture
def check():
    return {"id": 123, "name": "ci-ok", "head_sha": SHA, "check_suite": {"id": 42},
            "app": {"slug": "github-actions"}, "status": "completed", "conclusion": "success"}


class API:
    def __init__(self, runs, checks, *, reread=None):
        self.runs, self.checks, self.reread = runs, checks, reread
        self.calls = []

    def __call__(self, endpoint):
        self.calls.append(endpoint)
        if "/actions/workflows/ci.yml/runs?" in endpoint:
            assert f"head_sha={SHA}&event=push&per_page=100&page=1" in endpoint
            runs = self.reread if len(self.calls) > 1 and self.reread is not None else self.runs
            return deepcopy({"total_count": len(runs), "workflow_runs": runs})
        suite = int(endpoint.split("/check-suites/", 1)[1].split("/", 1)[0])
        assert endpoint == (f"repos/{REPO}/check-suites/{suite}/check-runs"
                            "?check_name=ci-ok&filter=latest&per_page=100&page=1")
        checks = self.checks[suite] if isinstance(self.checks, dict) else self.checks
        return deepcopy({"total_count": len(checks), "check_runs": checks})


def test_success_names_the_exact_commit_current_run_attempt_and_check(run, check):
    api = API([run], [check])
    assert release_ci.require_ci(REPO, SHA, get=api) == {
        "sha": SHA, "runs": [{"run_id": 12, "run_attempt": 1, "check_run_id": 123}]}
    assert len(api.calls) == 3 and api.calls[0] == api.calls[2]


@pytest.mark.parametrize("status,conclusion", [
    ("queued", None), ("in_progress", None), ("waiting", None),
    ("completed", "failure"), ("completed", "cancelled"), ("completed", "skipped"),
    ("completed", "neutral"), ("completed", "timed_out"),
])
def test_newest_failed_or_pending_run_cannot_fall_back_to_old_success(run, check,
                                                                  status, conclusion):
    older = dict(run, id=11, run_number=1)
    run.update(status=status, conclusion=conclusion, run_attempt=2)
    api = API([older, run], [check])  # deliberately not sorted newest first
    with pytest.raises(release_ci.CIGateError, match="CI run 12 attempt 2"):
        release_ci.require_ci(REPO, SHA, get=api)
    assert len(api.calls) == 1


def test_a_recent_failed_rerun_of_an_older_run_cannot_hide_behind_a_newer_run_number(run, check):
    rerun = dict(run, id=11, run_number=1, run_attempt=2, conclusion="failure",
                 updated_at="2026-11-12T11:00:00Z")
    with pytest.raises(release_ci.CIGateError, match="CI run 11 attempt 2"):
        release_ci.require_ci(REPO, SHA, get=API([run, rerun], [check]))


@pytest.mark.parametrize("status,conclusion", [("queued", None), ("completed", "failure")])
def test_older_success_finishing_later_cannot_hide_a_newer_queued_or_failed_run(run, check,
                                                                          status, conclusion):
    older = dict(run, id=11, run_number=1, created_at="2026-11-12T09:00:00Z",
                 updated_at="2026-11-12T11:00:00Z")
    run.update(status=status, conclusion=conclusion)
    api = API([older, run], [check])
    with pytest.raises(release_ci.CIGateError, match="CI run 12 attempt 1"):
        release_ci.require_ci(REPO, SHA, get=api)
    assert len(api.calls) == 1  # no successful check from the old run can authorize publication


def test_late_success_of_another_old_run_cannot_hide_a_recent_failed_rerun(run, check):
    latest = dict(run, id=13, run_number=3)
    failed = dict(run, id=12, run_number=2, run_attempt=2, conclusion="failure",
                  created_at="2026-11-12T09:30:00Z", updated_at="2026-11-12T10:30:00Z")
    older = dict(run, id=11, run_number=1, created_at="2026-11-12T09:00:00Z",
                 updated_at="2026-11-12T11:00:00Z")
    with pytest.raises(release_ci.CIGateError, match="CI run 12 attempt 2"):
        release_ci.require_ci(REPO, SHA, get=API([latest, older, failed], [check]))


@pytest.mark.parametrize("status", ["queued", "in_progress"])
def test_any_unfinished_old_run_blocks_even_if_it_was_last_updated_before_the_newest(run, check,
                                                                                 status):
    older = dict(run, id=11, run_number=1, status=status, conclusion=None,
                 created_at="2026-11-12T09:00:00Z", updated_at="2026-11-12T09:30:00Z")
    with pytest.raises(release_ci.CIGateError, match="CI run 11 attempt 1"):
        release_ci.require_ci(REPO, SHA, get=API([run, older], [check]))


def test_a_failure_completed_before_the_new_run_was_created_can_be_superseded(run, check):
    older = dict(run, id=11, run_number=1, conclusion="failure",
                 created_at="2026-11-12T09:00:00Z", updated_at="2026-11-12T09:59:59Z")
    accepted = release_ci.require_ci(REPO, SHA, get=API([older, run], [check]))
    assert [item["run_id"] for item in accepted["runs"]] == [12]


def test_failure_updated_at_the_creation_boundary_is_still_required(run, check):
    older = dict(run, id=11, run_number=1, conclusion="failure",
                 created_at="2026-11-12T09:00:00Z")  # updated_at equals the new run's created_at
    with pytest.raises(release_ci.CIGateError, match="CI run 11 attempt 1"):
        release_ci.require_ci(REPO, SHA, get=API([older, run], [check]))


def test_each_recent_successful_run_needs_its_own_ci_ok_check(run, check):
    older = dict(run, id=11, run_number=1, check_suite_id=43,
                 created_at="2026-11-12T09:00:00Z", updated_at="2026-11-12T10:30:00Z")
    api = API([older, run], {42: [check], 43: []})
    with pytest.raises(release_ci.CIGateError, match="exactly one current ci-ok"):
        release_ci.require_ci(REPO, SHA, get=api)
    older_check = dict(check, id=124, check_suite={"id": 43})
    api = API([older, run], {42: [check], 43: [older_check]})
    assert release_ci.require_ci(REPO, SHA, get=api)["runs"] == [
        {"run_id": 12, "run_attempt": 1, "check_run_id": 123},
        {"run_id": 11, "run_attempt": 1, "check_run_id": 124},
    ]
    assert len(api.calls) == 4


@pytest.mark.parametrize("was_relevant", [False, True])
def test_an_old_run_rerun_during_the_check_invalidates_the_required_evidence_set(run, check,
                                                                            was_relevant):
    older = dict(run, id=11, run_number=1, check_suite_id=43,
                 created_at="2026-11-12T09:00:00Z",
                 updated_at="2026-11-12T10:30:00Z" if was_relevant else "2026-11-12T09:30:00Z")
    reread = [run, dict(older, run_attempt=2, updated_at="2026-11-12T11:00:00Z")]
    older_check = dict(check, id=124, check_suite={"id": 43})
    api = API([run, older], {42: [check], 43: [older_check]}, reread=reread)
    with pytest.raises(release_ci.CIGateError, match="CI changed"):
        release_ci.require_ci(REPO, SHA, get=api)


@pytest.mark.parametrize("status,conclusion", [
    ("queued", None), ("in_progress", None), ("completed", "failure"),
    ("completed", "cancelled"), ("completed", "skipped"), ("completed", "neutral"),
])
def test_only_a_completed_successful_ci_ok_check_counts(run, check, status, conclusion):
    check.update(status=status, conclusion=conclusion)
    with pytest.raises(release_ci.CIGateError, match="ci-ok has not completed successfully"):
        release_ci.require_ci(REPO, SHA, get=API([run], [check]))


@pytest.mark.parametrize("field,value", [
    ("head_sha", "b" * 40), ("event", "pull_request"),
    ("path", ".github/workflows/release.yml"),
    ("repository", {"full_name": "other/symq"}), ("repository", None), ("run_attempt", None),
])
def test_a_green_run_for_another_identity_cannot_authorize_the_release(run, check, field, value):
    run[field] = value
    with pytest.raises(release_ci.CIGateError, match="CI run identity"):
        release_ci.require_ci(REPO, SHA, get=API([run], [check]))


@pytest.mark.parametrize("field,value", [
    ("head_sha", "b" * 40), ("name", "build"), ("app", {"slug": "another-app"}),
    ("check_suite", {"id": 43}), ("app", None), ("check_suite", None),
])
def test_ci_ok_must_belong_to_github_actions_and_the_exact_ci_suite(run, check, field, value):
    check[field] = value
    with pytest.raises(release_ci.CIGateError, match="ci-ok identity"):
        release_ci.require_ci(REPO, SHA, get=API([run], [check]))


def test_no_workflow_run_fails_closed(check):
    with pytest.raises(release_ci.CIGateError, match="no push run"):
        release_ci.require_ci(REPO, SHA, get=API([], [check]))


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_ambiguous_ci_ok_fails_closed(run, check, count):
    with pytest.raises(release_ci.CIGateError, match="exactly one current ci-ok"):
        release_ci.require_ci(REPO, SHA, get=API([run], [check] * count))


@pytest.mark.parametrize("changes", [
    {"run_attempt": 2}, {"id": 13, "run_number": 3},
    {"status": "in_progress", "conclusion": None, "run_attempt": 2},
])
def test_a_concurrent_rerun_or_new_run_invalidates_the_read(run, check, changes):
    api = API([run], [check], reread=[dict(run, **changes)])
    with pytest.raises(release_ci.CIGateError, match="CI changed|has not completed successfully"):
        release_ci.require_ci(REPO, SHA, get=api)


def test_paginated_runs_find_the_latest_even_when_it_is_on_another_page(run, check):
    many = [dict(run, id=index, run_number=index, created_at="2026-11-12T09:00:00Z",
                 updated_at="2026-11-12T09:30:00Z") for index in range(1, 101)]
    many.append(dict(run, id=101, run_number=101))
    calls = []

    def get(endpoint):
        calls.append(endpoint)
        if "check-suites" in endpoint:
            return {"total_count": 1, "check_runs": [check]}
        page = int(endpoint.rsplit("=", 1)[1])
        return {"total_count": len(many), "workflow_runs": many[(page - 1) * 100:page * 100]}

    assert release_ci.require_ci(REPO, SHA, get=get)["runs"][0]["run_id"] == 101
    assert len(calls) == 5


@pytest.mark.parametrize("response", [
    {"total_count": 2, "workflow_runs": []},
    {"total_count": 1001, "workflow_runs": []},
    {"total_count": 1, "workflow_runs": [None]}, {},
])
def test_truncated_or_malformed_api_results_fail_closed(response):
    with pytest.raises(release_ci.CIGateError, match="CI evidence"):
        release_ci.require_ci(REPO, SHA, get=lambda endpoint: response)


@pytest.mark.parametrize("sha", ["main", "refs/tags/v0.3.0", "a" * 7, "a" * 39, "a" * 41])
def test_floating_refs_or_abbreviated_commits_are_not_accepted(sha):
    with pytest.raises(release_ci.CIGateError, match="exact, dereferenced SHA"):
        release_ci.require_ci(REPO, sha, get=lambda endpoint: pytest.fail("API should not be read"))


@pytest.mark.parametrize("field", ["created_at", "updated_at"])
@pytest.mark.parametrize("value", [None, "not-a-time", "2026-11-12T10:00:00"])
def test_creation_and_update_timestamps_must_be_valid_and_have_a_timezone(run, check, field, value):
    run[field] = value
    with pytest.raises(release_ci.CIGateError, match="timestamp"):
        release_ci.require_ci(REPO, SHA, get=API([run], [check]))


def test_an_update_before_creation_is_rejected(run, check):
    run["updated_at"] = "2026-11-12T09:00:00Z"
    with pytest.raises(release_ci.CIGateError, match="update precedes its creation"):
        release_ci.require_ci(REPO, SHA, get=API([run], [check]))


def test_github_transport_uses_read_only_requests_and_a_pinned_api_version(monkeypatch):
    def execute(arguments, **kwargs):
        assert arguments == ["gh", "api", "--method", "GET", "-H",
                             "Accept: application/vnd.github+json", "-H",
                             "X-GitHub-Api-Version: 2026-03-10", "repos/yoch/symq"]
        assert kwargs == {"capture_output": True, "text": True, "check": True, "timeout": 30}
        return SimpleNamespace(stdout=json.dumps({"id": 1}))

    monkeypatch.setattr(release_ci.subprocess, "run", execute)
    assert release_ci.github_json("repos/yoch/symq") == {"id": 1}


@pytest.mark.parametrize("error", [
    FileNotFoundError("gh unavailable"), subprocess.TimeoutExpired("gh", 30),
    subprocess.CalledProcessError(1, "gh", stderr="authentication or permission failure"),
])
def test_network_authentication_and_tool_failures_cannot_pass(monkeypatch, error):
    def execute(*args, **kwargs):
        raise error

    monkeypatch.setattr(release_ci.subprocess, "run", execute)
    with pytest.raises(release_ci.CIGateError, match="cannot read GitHub CI evidence"):
        release_ci.github_json("repos/yoch/symq")


@pytest.mark.parametrize("payload", ["not JSON", "[]", "null"])
def test_malformed_transport_response_cannot_pass(monkeypatch, payload):
    monkeypatch.setattr(release_ci.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=payload))
    with pytest.raises(release_ci.CIGateError):
        release_ci.github_json("repos/yoch/symq")


def test_command_returns_failure_until_exact_commit_evidence_passes(monkeypatch, capsys):
    def reject(*args):
        raise release_ci.CIGateError("no current CI")

    monkeypatch.setattr(release_ci, "require_ci", reject)
    assert release_ci.main(["--repo", REPO, "--sha", SHA]) == 1
    assert "no current CI" in capsys.readouterr().err
    monkeypatch.setattr(release_ci, "require_ci", lambda *a: {
        "sha": SHA, "runs": [{"run_id": 12, "run_attempt": 2, "check_run_id": 123}]})
    assert release_ci.main(["--repo", REPO, "--sha", SHA]) == 0
    assert f"ci-ok succeeded for {SHA}" in capsys.readouterr().out


@pytest.mark.checkout
@pytest.mark.parametrize("ref_kind", ["commit", "lightweight", "annotated", "wrong-commit"])
def test_workflow_checks_the_peeled_sha_and_refuses_a_different_checkout(tmp_path, ref_kind):
    def git(*args):
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "test")
    (tmp_path / "content").write_text("first\n")
    git("add", "content")
    git("commit", "-qm", "first")
    commit = git("rev-parse", "HEAD")
    if ref_kind == "annotated":
        git("tag", "-a", "v0.1.0", "-m", "annotated")
        event_sha = git("rev-parse", "v0.1.0")
        assert event_sha != commit
    elif ref_kind == "lightweight":
        git("tag", "v0.1.0")
        event_sha = git("rev-parse", "v0.1.0")
    else:
        event_sha = commit
    if ref_kind == "wrong-commit":
        (tmp_path / "content").write_text("second\n")
        git("commit", "-qam", "second")

    # Run the real workflow shell against a recording stand-in for the separately tested API
    # helper. No token or network is needed to exercise commit resolution and its refusal path.
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "release_ci.py").write_text(
        "import sys\nprint('checked ' + sys.argv[-1])\n")
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    script = next(step["run"] for step in workflow["jobs"]["preflight"]["steps"]
                  if "release_ci.py" in step.get("run", ""))
    done = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, capture_output=True, check=False,
                          text=True, env={**os.environ, "GITHUB_SHA": event_sha, "GH_REPO": REPO})
    if ref_kind == "wrong-commit":
        assert done.returncode != 0 and "checked " not in done.stdout
    else:
        assert done.returncode == 0 and done.stdout.strip() == f"checked {commit}"
