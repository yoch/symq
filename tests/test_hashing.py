"""Digests recorded in artifacts must not change when the hashing code is refactored."""
from __future__ import annotations

import hashlib
import json

import pytest

from symq import Circuit, PhaseProgram
from symq.hashing import canonical_sha256


def _legacy(body, *, sort_keys=True):
    """The formula every module used before ``symq.hashing`` existed."""
    return hashlib.sha256(json.dumps(body, sort_keys=sort_keys,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _phase_program():
    program = PhaseProgram(2, 1).ccx(0, 1, 2)
    event = program.hmr(2)
    return program.cz_if(event, 0, 1)


def test_canonical_digest_equals_the_legacy_formula():
    body = {"b": [1, 2, {"z": None, "a": True}], "a": "x"}
    assert canonical_sha256(body) == _legacy(body)
    assert canonical_sha256([3, {"k": 1}], sort_keys=False) == _legacy([3, {"k": 1}], sort_keys=False)


def test_non_finite_numbers_are_refused():
    with pytest.raises(ValueError):
        canonical_sha256({"x": float("nan")})


def test_program_digests_keep_their_recorded_values():
    from symq.experimental.api import program_hash
    from symq.experimental.channel import _sha
    from symq.experimental.serialization import program_to_dict
    from symq.verification import _program_hash

    circuit = Circuit(3).ccx(0, 1, 2).x(0)
    assert _program_hash(circuit) == _legacy({
        "kind": "classical_reversible", "width": 3,
        "gates": [["ccx", [0, 1, 2]], ["x", [0]]]})
    program = _phase_program()
    ops = [[op.kind, list(op.qubits), op.outcome] for op in program.ops]
    assert _program_hash(program) == _legacy(
        {"kind": "sign_phase_hmr", "data": 2, "ancillas": 1, "ops": ops})
    assert _sha(program) == _legacy({"grammar": "sign-hmr/affine-outcomes/full-channel/v1",
                                     "data": 2, "ancillas": 1, "ops": ops})
    assert program_hash(program) == _legacy(program_to_dict(program))
