"""Regressions for the code review of the #141-#146 labs assembly."""
from __future__ import annotations

import hashlib
import json
import random
import time
import tracemalloc

import pytest

import symq.labs.phase_quotient as pq
from symq import Circuit, Gate
from symq.anf import ANF
from symq.circuit import UnsupportedOperation
from symq.errors import ResourceLimitExceeded
from symq.labs import channel_certificate as cc
from symq.phase import Op, PhaseProgram
from symq.resources import Budget, Guard


def _quotient_case():
    # z - ab = (1 - 2ab) lift(z XOR ab) modulo 8, on a CCX prefix with a clean target.
    certificate = pq.PhaseQuotientCertificate(
        3, 3, ((3, 7), (4, 1)), (ANF(frozenset({3, 4})),), (((0, 1), (3, 6)),), 0)
    return Circuit(3).ccx(0, 1, 2), certificate, ((2, 0),)


# --- channel certificates: degree and incremental dictionary -----------------------

def test_degree_zero_keeps_constant_signature_proofs_and_explains_its_limit():
    # Provable on main at degree 0 and must stay provable (review of #208).
    empty = PhaseProgram(1)
    clean = PhaseProgram(1, 1)
    clean.hmr(1)
    for program in (empty, clean):
        assert cc.discover_certificate(program, program, degree=0).equivalent
    measured = PhaseProgram(1, 1).mcx(0, 1)
    measured.hmr(1)
    refused = cc.discover_certificate(measured, measured, degree=0)
    assert refused.outcome == "not_proved" and "degree >= 1" in refused.reason
    assert cc.discover_certificate(measured, measured, degree=1).equivalent
    with pytest.raises(ValueError, match="nonnegative"):
        cc.discover_certificate(empty, empty, degree=-1)


@pytest.mark.parametrize("degree", [1, 2, 3])
def test_growing_dictionary_spans_exactly_what_a_rebuild_spans(degree):
    rng = random.Random(degree)
    guard = Guard(Budget(max_terms=10**7))
    limits = cc.CertificateLimits(max_dictionary_terms=10**5)
    features = [frozenset(rng.sample(range(1, 64), rng.randint(1, 4))) for _ in range(7)]
    grown = cc._GrowingDictionary(degree, guard, limits)
    for count, feature in enumerate(features, 1):
        grown.add(feature)
        rebuilt = cc._dictionary(tuple(features[:count]), degree, guard, limits)
        probes = [frozenset(rng.sample(range(64), 3)) for _ in range(40)]
        probes += [cc._product(tuple(rng.sample(features[:count], min(degree, count))), guard)]
        for probe in probes:
            assert (grown.span.solve(probe) is None) == (rebuilt.solve(probe) is None)


# --- phase quotient: bounded default, receipt shape before proof work ---------------

def test_omitted_phase_quotient_budget_is_bounded_like_the_sibling_modules():
    budget = pq._guard(None).budget
    assert (budget.max_terms, budget.max_seconds) == (100_000, 10.0)


def test_malformed_receipts_are_refused_before_any_proof_work(monkeypatch):
    prefix, certificate, constants = _quotient_case()
    receipt = pq.check_prefix_phase(prefix, certificate,
                                    initial_constants=constants).to_dict()
    assert pq.replay_prefix_phase(prefix, certificate, receipt,
                                  initial_constants=constants).outcome == "proved"

    def no_proof(*_args, **_kwargs):
        raise AssertionError("proof ran before the receipt shape was checked")

    monkeypatch.setattr(pq, "check_prefix_phase", no_proof)
    huge_keys = {f"k{i}": i for i in range(1_000_000)}
    bad = [
        huge_keys,
        {"x": list(range(3_000_000))},
        {**receipt, "witness": 1 << 100_000},
        {**receipt, "width": 1 << 4096},
        {**receipt, "constant": -1},
        {**receipt, "initial_constants": {(2, 0)}},
        {**receipt, "initial_constants": [(2, 0)]},
        {**receipt, "witness": True},
        {**receipt, "reason": "r" * 5000},
        {**receipt, "initial_constants": [[0, 0]] * 300},
    ]
    for value in bad:
        started = time.perf_counter()
        with pytest.raises(ValueError):
            pq.replay_prefix_phase(prefix, certificate, value, Budget(max_seconds=0.01),
                                   initial_constants=constants)
        # The key-count check is O(1): even a million-key dict is refused at once.
        assert time.perf_counter() - started < 0.01


def test_witness_replay_polls_the_budget_inside_a_long_prefix(monkeypatch):
    # A false invariant on a long prefix forces the scalar witness replay; the budget
    # must be able to stop it between gates, not only before and after.
    width = 3
    prefix = Circuit(width).ccx(0, 1, 2)
    for _ in range(20_000):
        prefix.x(0)
    certificate = pq.PhaseQuotientCertificate(
        3, 3, ((3, 7), (4, 1)), (ANF(frozenset({3, 4})),), (((0, 1), (3, 6)),), 0)
    state = {"inside": False, "polls": 0}
    original_run = Circuit.run

    def tracking_run(self, assignment, *, check=None):
        assert check is not None, "witness replay must pass a per-gate check"
        state["inside"] = True
        try:
            return original_run(self, assignment, check=check)
        finally:
            state["inside"] = False

    original_check = Guard.check_time

    def exhausting_check(self):
        original_check(self)
        if state["inside"]:
            state["polls"] += 1
            if state["polls"] > 100:
                raise ResourceLimitExceeded("seconds", 0, 1)

    monkeypatch.setattr(Circuit, "run", tracking_run)
    monkeypatch.setattr(Guard, "check_time", exhausting_check)
    with pytest.raises(ResourceLimitExceeded):
        pq.check_prefix_phase(prefix, certificate, Budget(max_terms=10**6))
    assert state["polls"] == 101  # stopped mid-replay, after 100 completed gate checks


def test_circuit_run_check_is_called_per_gate_and_optional():
    circuit = Circuit(2).cx(0, 1).x(0).cx(0, 1)
    calls = []
    assert circuit.run(1, check=lambda: calls.append(1)) == circuit.run(1)
    assert len(calls) == 2 * len(circuit.gates)  # validation and execution


def test_prefix_digest_bytes_are_unchanged_by_the_shared_hasher():
    _, certificate, _ = _quotient_case()
    document = pq._certificate_dict(certificate)
    legacy = hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()
    assert pq._digest(document, Guard(None)) == legacy


# --- core snapshots ----------------------------------------------------------------

def test_circuit_snapshot_rebuilds_and_detaches_every_gate():
    circuit = Circuit(3).ccx(0, 1, 2).x(0)
    copy = circuit.snapshot()
    assert copy == circuit and copy.gates is not circuit.gates
    assert all(a is not b for a, b in zip(copy.gates, circuit.gates))
    tampered = Gate("cx", (0, 1))
    object.__setattr__(tampered, "qubits", [0, 1])
    with pytest.raises(TypeError, match="tuple of plain integers"):
        Circuit(3, [tampered]).snapshot()

    class Name(str):
        pass

    masked = Gate("x", (0,))
    object.__setattr__(masked, "name", Name("x"))
    with pytest.raises(TypeError, match="plain string name"):
        Circuit(1, [masked]).snapshot()
    object.__setattr__(tampered, "qubits", (0, 0))
    with pytest.raises(ValueError):
        Circuit(3, [tampered]).snapshot()  # rebuilding reruns the gate's own checks


def test_phase_program_snapshot_requires_exact_op_fields():
    program = PhaseProgram(2, 1).mcx(0, 2)
    program.mcz_if(program.hmr(2), 1)
    copy = program.snapshot()
    assert copy.ops == program.ops and all(a is not b for a, b in zip(copy.ops, program.ops))
    forged = Op("hmr", (2,), 0)
    object.__setattr__(forged, "outcome", True)
    with pytest.raises(UnsupportedOperation, match="exact"):
        PhaseProgram(2, 1, [Op("mcx", (0, 2)), forged]).snapshot()


# --- evidence harness ---------------------------------------------------------------

def test_affine_phase_harness_writes_evidence_when_case_construction_fails(monkeypatch, tmp_path):
    from benchmarks import affine_phase as bench

    def broken(case):
        raise RuntimeError(f"cannot build {case[0]}")

    monkeypatch.setattr(bench, "build_case", broken)
    output = tmp_path / "affine-phase.json"
    assert bench.main(["--repetitions", "1", "--output", str(output)]) == 1
    document = json.loads(output.read_text())
    assert document["qualification_passed"] is False
    assert document["trials"] and all(t["status"] == "error" for t in document["trials"])
    assert all(not oracle["passed"] for oracle in document["exhaustive_oracles"])
    assert not tracemalloc.is_tracing()


# --- second independent review (acfaba2) -----------------------------------------

def test_receipt_initial_constants_are_bounded_before_any_proof(monkeypatch):
    prefix, certificate, constants = _quotient_case()
    receipt = pq.check_prefix_phase(prefix, certificate,
                                    initial_constants=constants).to_dict()

    def no_proof(*_args, **_kwargs):
        raise AssertionError("proof ran before the receipt shape was checked")

    monkeypatch.setattr(pq, "check_prefix_phase", no_proof)
    for pair in ([1 << 100_000, 0], [-1, 0], [2, 2], [300, 1]):
        with pytest.raises(ValueError, match="bounded"):
            pq.replay_prefix_phase(prefix, certificate, {**receipt, "initial_constants": [pair]},
                                   initial_constants=constants)


def test_snapshot_refuses_an_oversized_qubit_tuple_in_constant_time():
    tampered = Gate("cx", (0, 1))
    object.__setattr__(tampered, "qubits", tuple(range(5_000_000)))
    circuit = Circuit(3)
    circuit.gates.append(tampered)  # appended after construction, as a caller could
    started = time.perf_counter()
    with pytest.raises(ValueError, match="more qubits than width"):
        circuit.snapshot()
    assert time.perf_counter() - started < 0.01


def test_sibling_parsers_check_the_key_count_before_copying_keys():
    import symq.labs.phase_delta_binding as pdb

    huge = {f"k{i}": i for i in range(1_000_000)}
    for call in (lambda: pq.certificate_from_dict(huge, Budget(max_seconds=0.01)),
                 lambda: pdb._validate_receipt(huge, Guard(Budget(max_seconds=0.01)))):
        started = time.perf_counter()
        with pytest.raises(ValueError):
            call()
        assert time.perf_counter() - started < 0.01
