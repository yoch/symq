"""Adversarial source-bound classical-miter RUP proof and producer qualification."""
from __future__ import annotations

import copy
import hashlib
import sys

import pytest

from symq import Circuit
from symq.labs import lrat_rup
from symq.labs.miter_cnf import export_classical_miter_cnf
from symq.labs.miter_proof_bundle import (
    check_classical_miter_proof,
    export_classical_miter_proof,
)
from symq.sat.encoding import Contract


def _literal_witness():
    """Independently construct a standard empty-clause LRAT trace for x==x."""
    left = Circuit(1)
    source = export_classical_miter_cnf(left, Circuit(1), Contract())
    variables, clauses = lrat_rup.parse_dimacs(
        source.dimacs, lrat_rup.Meter(lrat_rup.Limits()),
    )
    assert variables == 2
    assert clauses == [(2,), (-2,)]
    proof = f"{len(clauses) + 1} 0 1 2 0\n"
    bundle = {
        "kind": "symq_classical_miter_positive_rup",
        "schema_version": 1,
        "theorem": "classical_sat_miter_nonidentity_v1",
        "source_sha256": source.source_sha256,
        "cnf_sha256": source.cnf_sha256,
        "cnf": source.dimacs,
        "lrat": proof,
        "lrat_sha256": hashlib.sha256(proof.encode("ascii")).hexdigest(),
    }
    return left, source, bundle


def test_checked_small_miter_proof_without_solver(monkeypatch):
    left, source, bundle = _literal_witness()
    # An installed SAT solver is not needed by the standalone consumer.
    monkeypatch.setitem(sys.modules, "pysat", None)
    monkeypatch.setitem(sys.modules, "pysat.solvers", None)
    result = check_classical_miter_proof(
        left, Circuit(1), Contract(), bundle,
        expected_source_sha256=source.source_sha256,
    )
    assert result["status"] == "proved", result
    assert result["source_recomputed"]
    assert result["independent_unsat_checked"]
    assert result["checked_steps"] == 1
    assert not result["source_encoder_formally_verified"]
    assert not result["controlled_use_authorized"]


@pytest.mark.parametrize("fault", [
    "source", "expected-pin", "formula", "formula-hash", "proof",
    "proof-hash", "trailing", "schema", "theorem", "extra",
])
def test_forged_bundle_never_accepted(fault):
    left, source, bundle = _literal_witness()
    manifest = copy.deepcopy(bundle)
    expected = source.source_sha256
    right = Circuit(1)
    if fault == "source":
        right = Circuit(1).x(0)
    elif fault == "expected-pin":
        expected = "0" * 64
    elif fault == "formula":
        manifest["cnf"] += "c forged\n"
    elif fault == "formula-hash":
        manifest["cnf_sha256"] = "0" * 64
    elif fault == "proof":
        manifest["lrat"] = "3 0 1 1 0\n"
        manifest["lrat_sha256"] = hashlib.sha256(
            manifest["lrat"].encode("ascii"),
        ).hexdigest()
    elif fault == "proof-hash":
        manifest["lrat_sha256"] = "0" * 64
    elif fault == "trailing":
        manifest["lrat"] += "4 0 1 2 0\n"
        manifest["lrat_sha256"] = hashlib.sha256(
            manifest["lrat"].encode("ascii"),
        ).hexdigest()
    elif fault == "schema":
        manifest["schema_version"] = 2
    elif fault == "theorem":
        manifest["theorem"] = "arbitrary_quantum_channel"
    else:
        manifest["sneaky"] = True
    result = check_classical_miter_proof(
        left, right, Contract(), manifest, expected_source_sha256=expected,
    )
    assert result["status"] != "proved", (fault, result)
    assert not result["independent_unsat_checked"]


def test_contract_and_support_changes_are_not_replayable():
    left, source, bundle = _literal_witness()
    legal = Contract(input_constants={0: 0})
    result = check_classical_miter_proof(
        left, left, legal, bundle,
        expected_source_sha256=source.source_sha256,
    )
    assert result["status"] == "invalid"
    assert not result["independent_unsat_checked"]


def test_zero_proof_budget_produces_no_false_positive():
    left, source, bundle = _literal_witness()
    result = check_classical_miter_proof(
        left, left, Contract(), bundle,
        expected_source_sha256=source.source_sha256,
        limits=lrat_rup.Limits(max_bytes=1),
    )
    assert result["status"] == "inconclusive"
    assert not result["independent_unsat_checked"]


@pytest.mark.sat
def test_producer_for_a_real_nonidentity_rewrite_and_negative_case():
    # Two CCXs cancel as a *function* but not as a source gate list.
    left = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
    right = Circuit(3)
    generated = export_classical_miter_proof(left, right)
    assert generated["status"] == "proved", generated
    assert generated["independent_unsat_checked"]
    assert generated["bundle"] is not None
    frozen = export_classical_miter_cnf(left, right, Contract())
    fresh = check_classical_miter_proof(
        left, right, Contract(), generated["bundle"],
        expected_source_sha256=frozen.source_sha256,
    )
    assert fresh["status"] == "proved"
    assert fresh["independent_unsat_checked"]
    assert not fresh["source_encoder_formally_verified"]
    assert not fresh["controlled_use_authorized"]

    wrong = export_classical_miter_proof(Circuit(3).ccx(0, 1, 2), right)
    assert wrong["status"] == "not_proved", wrong
    assert wrong["bundle"] is None
    assert not wrong["independent_unsat_checked"]
