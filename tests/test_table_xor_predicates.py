"""Compact table domains, checked against independent finite word semantics.

All circuits and predicates are synthetic development fixtures authored here.
No private loader, benchmark result or external source is embedded.
"""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from symq.circuit import Circuit
from symq.experimental import (
    PredicateDomain,
    PredicateValues,
    ReceiptMismatch,
    TableXorContract,
    check_table_xor,
    replay_table_xor,
)
from symq.hashing import canonical_sha256
from symq.resources import Budget
from symq.sat.assumptions import And, Const, Eq, Not, Var


def contract(**changes):
    # Logical address and target bits are deliberately not physical wire IDs.
    values = {
        "width": 6, "address_wires": (3, 0), "target_wires": (4, 2),
        "clean_wires": (5,), "borrowed_wires": (1,), "table": (0, 1, 3, 2),
        "legal_addresses": PredicateValues.below(2, 3),
        "target_values": PredicateValues(PredicateDomain(2, Eq(Var("x.0"), Var("x.1"))), 0),
        "table_id": "synthetic-predicate-table", "slot_id": "synthetic-predicate-site",
        "theorem": "coherent",
    }
    values.update(changes)
    return TableXorContract(**values)


def source():
    return Circuit(6).cx(3, 4).cx(0, 4).cx(0, 2)


def scalar_run(program, state):
    for gate in program.gates:
        if all((state // 2**q) % 2 for q in gate.qubits[:-1]):
            state ^= 2**gate.qubits[-1]
    return state


def expected(state):
    address = ((state >> 3) & 1) + 2 * (state & 1)
    word = (0, 1, 3, 2)[address]
    return state ^ ((word & 1) << 4) ^ ((word >> 1) << 2)


def admitted(state):
    address = ((state >> 3) & 1) + 2 * (state & 1)
    return address < 3 and ((state >> 4) & 1) == ((state >> 2) & 1) and state < 32


def test_predicate_exhaustive_matches_scalar_oracle_and_all_coherences():
    spec, program = contract(), source()
    initial = [x for x in range(64) if admitted(x)]
    assert len(initial) == 12
    result = check_table_xor(program, spec, backend="exhaustive")
    assert result.equivalent and result.checked_states == len(initial)
    images = [scalar_run(program, x) for x in initial]
    assert images == [expected(x) for x in initial]
    # A phase-free permutation preserves every matrix unit, not only diagonals.
    for x in initial:
        for y in initial:
            assert (scalar_run(program, x), scalar_run(program, y)) == (expected(x), expected(y))


@pytest.mark.parametrize("backend", ["exhaustive", pytest.param("sat", marks=pytest.mark.sat)])
def test_physical_mapping_witness_replay_and_dirty_target_boundary(backend):
    spec, program = contract(), source()
    assert check_table_xor(program, spec, backend=backend).equivalent
    # Corrupt a borrowed output iff original target bits differ. The declared
    # predicate excludes that case, whereas a full dirty target must detect it.
    restricted = Circuit(6).cx(4, 1).cx(2, 1)
    restricted.gates.extend(program.gates)
    assert check_table_xor(restricted, spec, backend=backend).equivalent
    bad = check_table_xor(restricted, replace(spec, target_values=None), backend=backend)
    assert bad.status == "different" and bad.witness is not None
    assert scalar_run(restricted, bad.witness) != expected(bad.witness)
    wrong = program.cx(3, 1)
    result = check_table_xor(wrong, spec, backend=backend)
    assert result.status == "different" and admitted(result.witness)
    assert scalar_run(wrong, result.witness) != expected(result.witness)


@pytest.mark.parametrize("width", range(1, 8))
def test_unsigned_below_is_exact_for_every_small_bound(width):
    for upper in range(1, 2**width + 1):
        values = PredicateValues.below(width, upper)
        assert values.witness == 0
        for word in range(2**width):
            assert values.domain.contains(word) == (word < upper)


@pytest.mark.sat
@pytest.mark.parametrize("compact", [False, True])
def test_1220_legal_addresses_on_sat_without_expanding_predicate(compact, monkeypatch):
    legal = PredicateValues.below(11, 1220) if compact else tuple(range(1220))
    spec = TableXorContract(
        width=12, address_wires=tuple(range(11)), target_wires=(11,),
        clean_wires=(), borrowed_wires=(), table=(0,) * 2048,
        legal_addresses=legal, target_values=None,
        table_id="synthetic-zero-table-11", slot_id="synthetic-large-domain",
        theorem="coherent",
    )
    import symq.experimental.table_xor as module

    def no_enumeration(*args):
        raise AssertionError("SAT must keep a predicate symbolic")

    monkeypatch.setattr(module, "_enumerated_values", no_enumeration)
    good = Circuit(12).cx(0, 11).cx(0, 11)
    proof = check_table_xor(good, spec, budget=Budget(max_seconds=10))
    assert proof.equivalent
    bad = Circuit(12).cx(0, 11)
    result = check_table_xor(bad, spec, budget=Budget(max_seconds=10))
    assert result.status == "different" and result.witness is not None
    assert result.witness & 2047 < 1220
    assert scalar_run(bad, result.witness) != result.witness


def test_predicates_roundtrip_and_v1_contract_identity_stays_unchanged():
    spec = contract()
    assert spec.to_dict()["schema_version"] == 2
    assert TableXorContract.from_dict(json.loads(json.dumps(spec.to_dict()))) == spec
    assert PredicateValues.from_dict(spec.legal_addresses.to_dict()) == spec.legal_addresses
    path = Path(__file__).resolve().parents[1] / "examples/table_xor/contract.json"
    original = json.loads(path.read_text())
    legacy = TableXorContract.from_dict(original)
    assert legacy.to_dict() == original
    assert legacy.sha256 == canonical_sha256(original)


def test_replay_binds_predicate_witness_and_domain_and_checks_fresh_source():
    program, spec = source(), contract()
    proof = check_table_xor(program, spec, backend="exhaustive")
    pins = {"expected_source_sha256": proof.source_sha256,
            "expected_contract_sha256": proof.contract_sha256}
    assert replay_table_xor(program, spec, proof.to_dict(), backend="exhaustive", **pins).equivalent
    for modified in (
        replace(spec, legal_addresses=PredicateValues.below(2, 4)),
        replace(spec, legal_addresses=PredicateValues(spec.legal_addresses.domain, 1)),
        replace(spec, target_values=None),
        replace(spec, address_wires=(0, 3)),
    ):
        with pytest.raises(ReceiptMismatch, match="changed"):
            replay_table_xor(program, modified, proof.to_dict(), backend="exhaustive", **pins)
    with pytest.raises(ReceiptMismatch, match="changed"):
        replay_table_xor(program.x(4), spec, proof.to_dict(), backend="exhaustive", **pins)


@pytest.mark.parametrize("bad", [-1, True, 4, 3])
def test_nonempty_witness_is_checked_and_not_an_assumption(bad):
    with pytest.raises(ValueError, match="witness"):
        PredicateValues(PredicateDomain(2, Not(And(Var("x.0"), Var("x.1")))), bad)
    with pytest.raises(ValueError, match="witness"):
        PredicateValues(PredicateDomain(2, Const(False)), 0)


def test_strict_predicate_schema_width_and_mutants():
    with pytest.raises(ValueError, match="width"):
        contract(legal_addresses=PredicateValues.below(3, 3))
    with pytest.raises(ValueError, match="undeclared"):
        PredicateValues(PredicateDomain(2, Var("x.2")), 0)
    for width, upper in ((True, 2), (0, 1), (17, 1), (2, True), (2, 0), (2, 5)):
        with pytest.raises(ValueError):
            PredicateValues.below(width, upper)
    for mutate in (
        lambda d: d["address_domain"].update(untrusted=True),
        lambda d: d["address_domain"].update(witness=True),
        lambda d: d["address_domain"]["domain"].update(kind="full_cube"),
        lambda d: d.update(schema_version=1),
        lambda d: d.update(legal_addresses=[0]),
    ):
        document = copy.deepcopy(contract().to_dict())
        mutate(document)
        with pytest.raises((ValueError, TypeError)):
            TableXorContract.from_dict(document)
    forged = object.__new__(PredicateValues)
    object.__setattr__(forged, "domain", PredicateDomain(2, Const(False)))
    object.__setattr__(forged, "witness", 0)
    with pytest.raises(ValueError, match="witness"):
        contract(legal_addresses=forged)


def test_predicate_enumeration_and_replay_respect_budget():
    spec, program = contract(), source()
    assert check_table_xor(program, spec, backend="exhaustive", max_states=11).status == "inconclusive"
    receipt = check_table_xor(program, spec, backend="exhaustive").to_dict()
    result = replay_table_xor(
        program, spec, receipt, backend="exhaustive", budget=Budget(max_seconds=1e-12),
        expected_source_sha256=receipt["source_sha256"],
        expected_contract_sha256=receipt["contract_sha256"],
    )
    assert result.status == "inconclusive" and not result.equivalent


@pytest.mark.sat
def test_combined_predicate_depth_refusal_is_explicit():
    # Each word predicate is legal by itself; their conjunction exceeds the
    # unchanged global grammar bound. A nonempty domain is not a proof bypass.
    expression = Var("x.0")
    for _ in range(23):
        expression = Not(expression)
    values = PredicateValues(PredicateDomain(2, expression), 0)
    result = check_table_xor(source(), contract(legal_addresses=values, target_values=values))
    assert result.status == "unsupported" and not result.equivalent
