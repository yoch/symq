"""The quick benchmark writes raw times and a receipt naming the exact code it measured."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks import quick
from benchmarks.environment import receipt
from symq import Circuit

ROOT = Path(__file__).resolve().parents[1]


def test_records_carry_raw_times_and_a_receipt(monkeypatch):
    # One small circuit is enough to check the record's shape; the corpus is not needed here.
    monkeypatch.setattr(quick, "circuits", lambda split: [("toffoli", Circuit(3).ccx(0, 1, 2))])
    result = quick.run("dev", ["sparse"], 2, 5.0, {})
    assert result["receipt"]["source_sha256"] and result["receipt"]["source_files"] > 0
    assert {row["workload"] for row in result["rows"]} == set(quick.WORKLOADS)
    for row in result["rows"]:
        assert row["status"] == "ok" and len(row["seconds"]) == 2
        assert min(row["seconds"]) <= row["median_seconds"] <= max(row["seconds"])


def test_the_receipt_names_the_loaded_native_binary_without_its_path():
    from symq.backends import has_native

    data = receipt()
    assert data["native"]["available"] == has_native()
    assert "/" not in json.dumps(data["native"]).replace("\\/", "")
    if has_native():
        from symq.backends import _zdd

        binary = Path(_zdd.__file__)
        assert data["native"]["file"] == binary.name
        assert data["native"]["sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
        assert data["native"]["abi"] == _zdd.ABI_VERSION


@pytest.mark.checkout
def test_the_receipt_names_the_checkout_commit():
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()
    data = receipt()
    assert data["git_commit"] == head and data["symq_location"] == "src/symq"


def _receipt_of(package_parent: Path) -> dict:
    """The receipt computed in a fresh interpreter that imports symq from ``package_parent``."""
    code = ("import json, sys; sys.path[:0] = [sys.argv[1], sys.argv[2]]; "
            "from benchmarks.environment import receipt; print(json.dumps(receipt()))")
    done = subprocess.run([sys.executable, "-I", "-c", code, str(package_parent), str(ROOT)],
                          capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def _git(directory: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True)


def _repository_with_a_copy(tmp_path: Path, *, track: bool) -> Path:
    import symq

    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / "README").write_text("x\n")
    target = tmp_path / "vendor" / "symq"
    shutil.copytree(Path(symq.__file__).parent, target,
                    ignore=shutil.ignore_patterns("__pycache__", "*.so"))
    _git(tmp_path, "add", "README", *(["vendor"] if track else []))
    _git(tmp_path, "commit", "-q", "-m", "init")
    return target


def test_an_untracked_copy_inside_a_checkout_claims_no_commit(tmp_path):
    target = _repository_with_a_copy(tmp_path, track=False)
    data = _receipt_of(target.parent)
    assert data["git_commit"] is None and data["git_dirty"] is None
    assert data["symq_location"] == "untracked"


def test_a_tracked_copy_reports_its_commit_and_untracked_files_make_it_dirty(tmp_path):
    target = _repository_with_a_copy(tmp_path, track=True)
    data = _receipt_of(target.parent)
    assert data["symq_location"] == "vendor/symq" and data["git_dirty"] is False
    assert len(data["git_commit"]) == 40
    (target / "leftover.py").write_text("x = 1\n")
    assert _receipt_of(target.parent)["git_dirty"] is True
