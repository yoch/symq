"""Enforce research CNF resource limits during encoding, not only after it."""
from __future__ import annotations

import pytest

from symq import Circuit
from symq.circuit import Gate
from symq.errors import ResourceLimitExceeded
from symq.labs import miter_cnf, miter_proof_bundle
from symq.resources import Budget, Guard, VerificationSession
from symq.sat import encoding, miter
from symq.sat.encoding import Contract


def _long_ccx(count: int = 400) -> Circuit:
    return Circuit(3, [Gate("ccx", (0, 1, 2))] * count)


def test_variable_cap_trips_inside_builder_before_it_returns(monkeypatch):
    original = miter_cnf.build_miter
    observed = []

    def must_not_complete(*args, **kwargs):
        try:
            original(*args, **kwargs)
        except ResourceLimitExceeded as exc:
            observed.append(exc.resource)
            raise
        raise AssertionError("entire miter was built before the variable ceiling")

    monkeypatch.setattr(miter_cnf, "build_miter", must_not_complete)
    with pytest.raises(ResourceLimitExceeded, match="variables"):
        miter_cnf.export_classical_miter_cnf(
            _long_ccx(), Circuit(3), max_variables=5, max_source_gates=1000,
        )
    assert observed == ["variables"]


def test_clause_cap_trips_inside_builder_before_it_returns(monkeypatch):
    original = miter_cnf.build_miter
    observed = []

    def must_not_complete(*args, **kwargs):
        try:
            original(*args, **kwargs)
        except ResourceLimitExceeded as exc:
            observed.append(exc.resource)
            raise
        raise AssertionError("entire miter was built before the clause ceiling")

    monkeypatch.setattr(miter_cnf, "build_miter", must_not_complete)
    with pytest.raises(ResourceLimitExceeded, match="clauses"):
        miter_cnf.export_classical_miter_cnf(
            _long_ccx(), Circuit(3), max_clauses=2, max_source_gates=1000,
        )
    assert observed == ["clauses"]


def test_source_gate_cap_rejects_before_any_snapshot_validation(monkeypatch):
    left, right = _long_ccx(50), Circuit(3)

    def must_not_validate(*_args, **_kwargs):
        raise AssertionError("oversized input should not be snapshotted")

    monkeypatch.setattr(Circuit, "validate", must_not_validate)
    with pytest.raises(ResourceLimitExceeded, match="operations"):
        miter_cnf.export_classical_miter_cnf(
            left, right, max_source_gates=10,
        )


def test_budget_is_polled_inside_simplification_only_gate_stream(monkeypatch):
    # X-X-X... can simplify without allocating new Tseitin variables for
    # most gates. A check only in Encoder.new/add would not bound this loop.
    source = Circuit(1, [Gate("x", (0,))] * 512)
    visited = []
    original = encoding._poll_gates

    def fail_during_iteration(gates, checkpoint):
        for index, gate in enumerate(original(gates, checkpoint)):
            visited.append(index)
            if index == 128:
                raise ResourceLimitExceeded("seconds", 0.01, 0.02)
            yield gate

    monkeypatch.setattr(encoding, "_poll_gates", fail_during_iteration)
    with pytest.raises(ResourceLimitExceeded, match="seconds"):
        miter_cnf.export_classical_miter_cnf(source, Circuit(1))
    assert visited[-1] == 128


def test_inherited_byte_ceiling_is_enforced_and_unsupported_limits_refuse():
    left, right = Circuit(3).ccx(0, 1, 2), Circuit(3)
    with VerificationSession(Budget(max_bytes=16)):
        with pytest.raises(ResourceLimitExceeded, match="bytes"):
            miter_cnf.export_classical_miter_cnf(left, right)
    for budget in (Budget(max_terms=5), Budget(max_nodes=1)):
        with VerificationSession(budget):
            with pytest.raises(ValueError, match="node/term"):
                miter_cnf.export_classical_miter_cnf(left, right)


def test_normalized_tautologies_and_duplicates_consume_only_actual_cnf_bytes():
    guard = Guard()
    # Tight budget is exact for the normalized formula "p cnf 1 1\n1 0\n".
    expected = "p cnf 1 1\n1 0\n"
    bounded = miter_cnf._BoundedEncoder(
        guard, max_variables=1, max_clauses=4, cnf_bytes=len(expected),
    )
    assert bounded.new() == 1
    bounded.add(1, -1)  # tautology: no normalized output clause
    bounded.add(1, 1)   # duplicate literal: one normalized output clause
    assert bounded._normalized_clauses == 1
    assert bounded._normalized_bytes == len("1 0\n")
    assert bounded.clauses == [[1, -1], [1, 1]]
    with pytest.raises(ResourceLimitExceeded, match="bytes"):
        bounded.add(1)

    clause_limited = miter_cnf._BoundedEncoder(
        guard, max_variables=1, max_clauses=2, cnf_bytes=1024,
    )
    assert clause_limited.new() == 1
    clause_limited.add(1)
    clause_limited.add(-1)
    with pytest.raises(ResourceLimitExceeded, match="clauses"):
        clause_limited.add(1)


def test_legacy_default_miter_still_uses_unbounded_encoder():
    left, right = Circuit(2).cx(0, 1), Circuit(2)
    direct = miter.build_miter(left, right)
    assert type(direct.encoder) is encoding.Encoder
    direct.encoder.add(*direct.difference)
    bound = miter_cnf.export_classical_miter_cnf(left, right)
    assert bound.variables == direct.encoder.next_variable - 1


@pytest.mark.sat
def test_proof_consumer_never_issues_success_on_in_encoding_limit():
    left, right = _long_ccx(200), Circuit(3)
    # The caller only opts into this research checker, not the default SAT engine.
    result = miter_proof_bundle.export_classical_miter_proof(
        left, right, limits=miter_proof_bundle.lrat_rup.Limits(max_variables=5),
    )
    assert result["status"] == "inconclusive"
    assert result["bundle"] is None
    assert not result["independent_unsat_checked"]
