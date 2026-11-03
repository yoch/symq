"""Miter CNF source provenance and independent small Boolean oracle."""
from __future__ import annotations

import hashlib
import random

import pytest

from symq import Circuit
from symq.errors import ResourceLimitExceeded
from symq.labs.lrat_rup import Limits, Meter, parse_dimacs
from symq.labs.miter_cnf import export_classical_miter_cnf
from symq.resources import Budget
from symq.sat.encoding import Contract


def _dpll(clauses: list[tuple[int, ...]], assumptions=()) -> bool:
    """Pure-Python exhaustive SAT oracle; no PySAT or SymQ encoder calls."""
    clauses = list(clauses) + [(v,) for v in assumptions]

    def solve(values: dict[int, bool]) -> bool:
        while True:
            changed = False
            for clause in clauses:
                open_lits = []
                satisfied = False
                for lit in clause:
                    value = values.get(abs(lit))
                    if value is None:
                        open_lits.append(lit)
                    elif value == (lit > 0):
                        satisfied = True
                        break
                if satisfied:
                    continue
                if not open_lits:
                    return False
                if len(open_lits) == 1:
                    lit = open_lits[0]
                    key, val = abs(lit), lit > 0
                    if key in values and values[key] != val:
                        return False
                    if key not in values:
                        values[key] = val
                        changed = True
            if not changed:
                break
        unresolved = []
        for clause in clauses:
            if not any(
                values.get(abs(lit)) == (lit > 0)
                for lit in clause if abs(lit) in values
            ):
                unresolved.append(clause)
        if not unresolved:
            return True
        variable = next(abs(lit) for lit in unresolved[0] if abs(lit) not in values)
        return solve({**values, variable: False}) or solve({**values, variable: True})

    return solve({})


def _check_against_truth(left: Circuit, right: Circuit, contract: Contract):
    bundle = export_classical_miter_cnf(left, right, contract)
    assert bundle.to_manifest()["proved"] is False
    assert bundle.cnf_sha256 == hashlib.sha256(bundle.dimacs.encode("ascii")).hexdigest()
    variables, clauses = parse_dimacs(bundle.dimacs, Meter(Limits()))
    assert variables == bundle.variables
    assert len(clauses) == bundle.clauses
    assert len(bundle.input_literals) == left.width
    sat = False
    for x in range(1 << left.width):
        left_out, right_out = left.run(x), right.run(x)
        legal = all(((x >> bit) & 1) == v for bit, v in contract.input_constants.items())
        pairs = (sorted(contract.output_map.items()) if contract.output_map else
                 [(q, q) for q in (
                     range(left.width) if contract.observed_outputs is None
                     else contract.observed_outputs
                 )])
        diff = any(((left_out >> a) & 1) != ((right_out >> b) & 1) for a, b in pairs)
        diff |= any(
            ((left_out >> w) & 1) != ((x >> w) & 1)
            or ((right_out >> w) & 1) != ((x >> w) & 1)
            for w in contract.restored_wires
        )
        expected = legal and diff
        assumptions = tuple(lit if x >> q & 1 else -lit
                            for q, lit in enumerate(bundle.input_literals))
        actual = _dpll(clauses, assumptions)
        assert actual == expected, (x, bundle.to_manifest())
        sat |= actual
    assert _dpll(clauses) == sat
    return bundle


def test_exact_miter_snapshot_agrees_with_independent_oracle():
    left = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
    right = Circuit(3)
    b = _check_against_truth(left, right, Contract())
    assert b.to_manifest()["portable_certificate"] is False
    assert export_classical_miter_cnf(left, right).dimacs == b.dimacs
    _check_against_truth(Circuit(3).ccx(0, 1, 2), right, Contract())
    _check_against_truth(Circuit(3).ccx(0, 1, 2), right, Contract(input_constants={0: 0}))
    _check_against_truth(Circuit(3).ccx(0, 1, 2), right,
                         Contract(observed_outputs=(0,), restored_wires=(2,)))
    _check_against_truth(Circuit(2), Circuit(2), Contract(output_map={0: 1, 1: 0}))


def test_tampered_source_changes_pin_and_unsupported_contract_refuses():
    left, right = Circuit(2).cx(0, 1), Circuit(2)
    original = export_classical_miter_cnf(left, right)
    left.x(1)
    changed = export_classical_miter_cnf(left, right)
    assert changed.source_sha256 != original.source_sha256
    assert changed.cnf_sha256 != original.cnf_sha256
    constrained = export_classical_miter_cnf(left, right, Contract(input_constants={0: 1}))
    assert constrained.source_sha256 != changed.source_sha256
    for args in ({"max_variables": 1}, {"max_clauses": 1}, {"max_bytes": 1}):
        with pytest.raises(ResourceLimitExceeded):
            export_classical_miter_cnf(left, right, **args)
    with pytest.raises(ValueError, match="term/node"):
        export_classical_miter_cnf(left, right, budget=Budget(max_terms=1))


def test_random_reversible_miter_matches_bruteforce():
    rng = random.Random(6133)
    for width in (2, 3):
        for _ in range(24):
            left, right = Circuit(width), Circuit(width)
            for circuit in (left, right):
                for _ in range(rng.randint(0, 4)):
                    t = rng.randrange(width)
                    if rng.randrange(2):
                        circuit.x(t)
                    else:
                        circuit.cx((t + 1) % width, t)
            contract = Contract()
            if rng.randrange(2):
                contract.input_constants[rng.randrange(width)] = rng.randrange(2)
            _check_against_truth(left, right, contract)
