"""Exclusive accounting and public-profile evidence, without timing thresholds."""
from dataclasses import replace

import pytest

from symq.experimental.api import verify
from symq.experimental.contracts import VerificationContract
from symq.experimental.profiling import ExclusiveTimer, profile
from symq.phase import PhaseProgram
from symq.resources import Budget


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


def test_nested_timers_subtract_children_and_reconcile_orchestration():
    clock = Clock()
    timer = ExclusiveTimer(clock)
    with timer.stage("outer"):
        clock.value = 2
        with timer.stage("inner"):
            clock.value = 5
        clock.value = 9
    timer.finish(10)
    assert timer.seconds == {"inner": 3, "outer": 6, "orchestration": 1}
    assert sum(timer.seconds.values()) == 10


def test_recursive_stage_names_and_exceptions_do_not_double_count_or_leave_frames():
    clock = Clock()
    timer = ExclusiveTimer(clock)
    with pytest.raises(RuntimeError, match="fixture error"), timer.stage("same"):
        clock.value = 1
        with timer.stage("same"):
            clock.value = 4
            raise RuntimeError("fixture error")
    timer.finish(5)
    assert timer.seconds == {"same": 4, "orchestration": 1}
    with pytest.raises(RuntimeError, match="exceed"):
        timer.finish(2)


def test_legacy_timer_interface_uses_exclusive_accounting(monkeypatch):
    from research.hmr_native_channel.profile import StageTimes, _Timer
    clock = Clock()
    stages = StageTimes()
    timer = _Timer(stages)
    timer._timer.clock = clock
    with timer.stage("outputs_x"):
        clock.value = 2
        with timer.stage("phase0_x"):
            clock.value = 4
        clock.value = 6
    timer.reconcile(7)
    assert stages.outputs_x == 4
    assert stages.phase0_x == 2
    assert stages.orchestration == 1
    assert stages.total == 7


def test_legacy_serialised_stages_reconcile_with_total():
    from dataclasses import asdict

    from research.hmr_native_channel.profile import profile_channel
    report = profile_channel(PhaseProgram(2), PhaseProgram(2).mcz(0, 1), backend="zdd")
    fields = asdict(report.stages)
    total = fields.pop("total")
    assert sum(fields.values()) == pytest.approx(total)


@pytest.mark.parametrize("different", [False, True])
def test_profile_runs_public_verify_and_preserves_exact_result_and_witness(different):
    left, right = PhaseProgram(2, 1), PhaseProgram(2, 1)
    left.cx(0, 2)
    event = left.hmr(2)
    left.z_if(event, 0)
    if different:
        right.mcz(0, 1)
    contract = VerificationContract()
    expected = verify(left, right, contract)
    report = profile(left, right, contract, budget=Budget(max_seconds=10))
    # Backend timing statistics legitimately vary between the two real calls.
    assert replace(report.result, statistics=expected.statistics) == expected
    assert sum(dict(report.stage_seconds).values()) == pytest.approx(report.total_seconds)
    assert all(seconds >= 0 for _, seconds in report.stage_seconds)
    assert {"outputs_x", "outputs_y", "orchestration"} <= dict(report.stage_seconds).keys()
    assert report.result.witness_checked == different


def test_reduced_profile_and_standalone_exports_carry_contract_and_source_evidence(tmp_path):
    left, right = PhaseProgram(2, 1).cx(0, 2), PhaseProgram(2, 2).cx(0, 2)
    contract = VerificationContract("reduced_channel", "zdd",
                                    left_outputs=(1, 0), right_outputs=(1, 0))
    report = profile(left, right, contract)
    assert report.result.equivalent
    assert report.result.contract_sha256 == contract.sha256
    report.write_json(tmp_path / "profile.json")
    escaped = replace(report, result=replace(report.result, reason="<script>fixture</script>"))
    escaped.write_html(tmp_path / "profile.html")
    text = (tmp_path / "profile.html").read_text()
    assert "<script>fixture</script>" not in text
    assert "&lt;script&gt;fixture&lt;/script&gt;" in text
    assert report.result.left_sha256 in text
    assert contract.sha256 in text
    assert "https://" not in text


def test_profile_timeout_is_inconclusive_and_drops_witness():
    report = profile(PhaseProgram(2), PhaseProgram(2).x(0),
                     budget=Budget(max_seconds=1e-12))
    assert report.result.outcome == "inconclusive"
    assert report.result.witness is None
    assert report.result.witness_checked is False


def test_profile_normalises_deadline_expiring_during_session_exit(monkeypatch):
    from types import SimpleNamespace

    from symq import resources
    from symq.experimental import api
    from symq.experimental.contracts import VerificationResult

    ticks = iter((0.0, 0.0, 0.0, 2.0))
    monkeypatch.setattr(resources, "time", SimpleNamespace(perf_counter=lambda: next(ticks)))
    fake = VerificationResult("equivalent", "full_channel", "zdd", "fixture result", "", "", "")
    monkeypatch.setattr(api, "verify", lambda *args, **kwargs: fake)
    report = profile(PhaseProgram(1), PhaseProgram(1), budget=Budget(max_seconds=1))
    assert report.result.outcome == "inconclusive"
    assert "seconds limit exceeded" in report.result.reason
    assert report.result.witness_checked is False
    assert sum(dict(report.stage_seconds).values()) == pytest.approx(report.total_seconds)


def test_frozen_campaign_families_have_expected_public_verdicts_and_disjoint_sources():
    import json
    from pathlib import Path

    from benchmarks.roadmap_campaign import PINNED_MANIFEST_SHA256, _digest, _fixture
    from symq.experimental.contracts import VerificationContract
    from symq.experimental.serialization import program_from_dict

    manifest = json.loads((Path(__file__).parents[1] / "benchmarks/roadmap_manifest.json").read_text())
    assert _digest(manifest) == PINNED_MANIFEST_SHA256
    partitions = {"development": set(), "holdout": set()}
    for case in manifest["cases"]:
        left, right, document = _fixture(case)
        partitions[case["partition"]].update((_digest(left), _digest(right)))
        result = verify(program_from_dict(left), program_from_dict(right),
                        VerificationContract.from_dict(document))
        assert result.outcome == case["expected"], (case["id"], result)
    assert not partitions["development"] & partitions["holdout"]
