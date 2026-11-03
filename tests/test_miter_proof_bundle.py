"""Adversarial source-bound classical-miter RUP proof and producer qualification."""
from __future__ import annotations

import copy
import hashlib
import sys

import pytest

from symq import Circuit
from symq.errors import ResourceLimitExceeded
from symq.labs import lrat_rup
from symq.labs.miter_cnf import export_classical_miter_cnf
from symq.labs.miter_proof_bundle import (
    check_classical_miter_proof,
    export_classical_miter_proof,
)
from symq.resources import Budget
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


def test_label_fields_must_be_exact_strings():
    class Liar:
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    left, source, bundle = _literal_witness()
    for field in ("kind", "theorem"):
        forged = dict(bundle, **{field: Liar()})
        result = check_classical_miter_proof(
            left, Circuit(1), Contract(), forged,
            expected_source_sha256=source.source_sha256,
        )
        assert result["status"] == "invalid", (field, result)
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



@pytest.mark.sat
def test_global_contextual_miter_under_declared_input_domain_with_suffix():
    # This proves a full global classical miter, *not* a local cut theorem:
    # a nontrivial prefix and suffix surround a CCX which is inert only when
    # the original input control q1 is zero.
    left = Circuit(4).cx(0, 2).ccx(0, 1, 2).cx(2, 3)
    right = Circuit(4).cx(0, 2).cx(2, 3)
    domain = Contract(input_constants={1: 0})
    source = export_classical_miter_cnf(left, right, domain)
    positive = export_classical_miter_proof(left, right, domain)
    assert positive["status"] == "proved", positive
    assert positive["independent_unsat_checked"]
    replay = check_classical_miter_proof(
        left, right, domain, positive["bundle"],
        expected_source_sha256=source.source_sha256,
    )
    assert replay["status"] == "proved"
    assert replay["source_recomputed"]
    assert replay["independent_unsat_checked"]
    assert not replay["controlled_use_authorized"]
    assert not replay["source_encoder_formally_verified"]

    for x in range(1 << 4):
        if x & 0b0010:
            continue
        assert left.run(x) == right.run(x)
    # Removing the legal input restriction makes the miter SAT. Importantly,
    # a context-dependent proof may not be reused as a total theorem.
    unqualified = export_classical_miter_proof(left, right, Contract())
    assert unqualified["status"] == "not_proved", unqualified
    assert not unqualified["independent_unsat_checked"]
    assert unqualified["bundle"] is None

    forged_contract = check_classical_miter_proof(
        left, right, Contract(), positive["bundle"],
        expected_source_sha256=source.source_sha256,
    )
    assert forged_contract["status"] == "invalid"
    assert not forged_contract["independent_unsat_checked"]

    # Mutate the *common* prefix on both sides so that q1 is toggled after the
    # declared input constraint: the CCX becomes active. This pair differs
    # from the proved (left, right) pair above only by the shared X(1), so
    # the negative is caused by CCX activation, not by a differing q1 output.
    prefix_left = Circuit(4).x(1).cx(0, 2).ccx(0, 1, 2).cx(2, 3)
    prefix_right = Circuit(4).x(1).cx(0, 2).cx(2, 3)
    altered = export_classical_miter_proof(prefix_left, prefix_right, domain)
    assert altered["status"] == "not_proved", altered
    assert not altered["independent_unsat_checked"]
    assert altered["bundle"] is None
    # A one-sided X(1) is refuted by the q1 output alone, even without a CCX,
    # so it cannot serve as evidence about the contextual CCX.
    one_sided = export_classical_miter_proof(
        Circuit(4).x(1).cx(0, 2).cx(2, 3), right, domain,
    )
    assert one_sided["status"] == "not_proved", one_sided


def test_expired_deadline_and_cap_edges_never_yield_a_positive(monkeypatch):
    # Owner review request on #184: within-cap and just-over-cap inputs under
    # an expired deadline. The deadline is polled before build_miter runs;
    # the size caps are checked only after encoding (a documented limit).
    import symq.labs.miter_cnf as module

    left, source, bundle = _literal_witness()
    right = Circuit(1)
    real_build = module.build_miter

    def trapped(*args, **kwargs):
        raise AssertionError("encoding ran after the deadline expired")

    monkeypatch.setattr(module, "build_miter", trapped)
    expired = Budget(absolute_deadline=0.0)
    with pytest.raises(ResourceLimitExceeded):
        export_classical_miter_cnf(left, right, Contract(), budget=expired)
    result = check_classical_miter_proof(
        left, right, Contract(), bundle,
        expected_source_sha256=source.source_sha256, budget=expired,
    )
    assert result["status"] == "inconclusive", result
    assert not result["independent_unsat_checked"]
    monkeypatch.setattr(module, "build_miter", real_build)

    # Exactly at the variable/clause caps the formula is exported; one below
    # is refused, and the consumer then reports inconclusive, never proved.
    at_cap = export_classical_miter_cnf(
        left, right, Contract(),
        max_variables=source.variables, max_clauses=source.clauses,
    )
    assert at_cap.dimacs == source.dimacs
    for caps in ({"max_variables": source.variables - 1},
                 {"max_clauses": source.clauses - 1}):
        with pytest.raises(ResourceLimitExceeded):
            export_classical_miter_cnf(left, right, Contract(), **caps)
    tight = lrat_rup.Limits(max_variables=source.variables - 1)
    result = check_classical_miter_proof(
        left, right, Contract(), bundle,
        expected_source_sha256=source.source_sha256, limits=tight,
    )
    assert result["status"] == "inconclusive", result
    assert not result["independent_unsat_checked"]
