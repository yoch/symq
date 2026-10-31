"""The quick benchmark writes raw times and a receipt naming the exact code it measured."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from benchmarks import quick
from benchmarks.environment import receipt


def test_records_carry_raw_times_and_a_receipt():
    result = quick.run("dev", ["sparse"], 2, 5.0, {})
    assert result["receipt"]["source_sha256"] and result["receipt"]["source_files"] > 0
    rows = [row for row in result["rows"] if row["status"] == "ok"]
    assert rows
    for row in rows:
        assert 1 <= len(row["seconds"]) <= 2
        assert min(row["seconds"]) <= row["median_seconds"] <= max(row["seconds"])


def test_the_receipt_names_the_loaded_native_binary():
    from symq.backends import has_native

    data = receipt()
    assert data["native"]["available"] == has_native()
    if has_native():
        from symq.backends import _zdd

        binary = Path(_zdd.__file__)
        assert data["native"]["sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
        assert data["native"]["abi"] == _zdd.ABI_VERSION


@pytest.mark.checkout
def test_the_receipt_names_the_checkout_commit():
    import subprocess

    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()
    assert receipt()["git_commit"] == head
