"""The local qualification entry point is reproducible and non-overwriting."""

import json
import subprocess
import sys

from benchmarks import bilinear_phase_fusion


def test_benchmark_is_collected_only_in_labs_tier(request):
    assert request.node.get_closest_marker("labs") is not None
    assert request.node.get_closest_marker("core") is None


def test_quick_qualification_records_scope_and_refuses_overwrite(tmp_path):
    out = tmp_path / "new"
    command = [
        sys.executable,
        "-m",
        bilinear_phase_fusion.__name__,
        "--quick",
        "--out",
        str(out),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    original = (out / "qualification.json").read_bytes()
    report = json.loads(original)
    assert report["passed"]
    assert [r["outcomes_checked"] for r in report["rows"]] == [16, 512]
    assert report["limits"]["application_site_qualified"] is False
    assert report["provenance"]["sources"]
    assert all(len(r["compile_wall_seconds_3_trials"]) == 3 for r in report["rows"])
    assert all(c["status"] == "proved" for r in report["rows"] for c in r["checks"])
    rerun = subprocess.run(command, check=False, capture_output=True, text=True)
    assert rerun.returncode != 0
    assert (out / "qualification.json").read_bytes() == original
