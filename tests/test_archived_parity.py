"""Parity with independently written engines (the archived 27 Oct 2026 handoff).

The four archived engines were run at the archive commit and agree on every circuit; their output
ANFs are pinned by digest in ``tests/data/archived_engine_outputs.json``. Every in-tree backend
must reproduce them exactly, which keeps an oracle written outside SymQ in CI.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from symq import make_algebra, simulate
from symq.corpus import load_corpus

ROOT = Path(__file__).resolve().parents[1]
RECORD = json.loads((ROOT / "tests" / "data" / "archived_engine_outputs.json").read_text())
CORPUS = load_corpus(ROOT / "benchmarks" / "corpus" / "qcec" / "MANIFEST.json")


def _digest(algebra, circuit) -> tuple[str, int]:
    outputs = {str(wire): sorted(algebra.to_anf(value).terms)
               for wire, value in enumerate(simulate(circuit, algebra))
               if not algebra.is_zero(value)}
    blob = json.dumps(outputs, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest(), sum(len(t) for t in outputs.values())


def test_the_record_covers_the_dev_and_holdout_splits():
    names = {entry.name for entry in CORPUS.select(("dev", "holdout"))}
    assert names == set(RECORD["circuits"])
    assert sum(item["monomials"] for item in RECORD["circuits"].values()) == 13066


@pytest.mark.parametrize("backend", [
    "sparse", "zdd", "reference", "auto-zdd",
    pytest.param("zdd-native", marks=pytest.mark.native),
])
def test_backend_reproduces_the_archived_engines(backend):
    for entry in CORPUS.select(("dev", "holdout")):
        circuit = entry.load()
        expected = RECORD["circuits"][entry.name]
        assert _digest(make_algebra(backend, circuit.width), circuit) == (
            expected["sha256"], expected["monomials"]), (entry.name, backend)
