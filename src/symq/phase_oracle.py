"""Independent state-vector oracle for :mod:`symq.phase` programs.

Amplitudes are integers: the Hadamard inside ``hmr`` is applied unnormalized as
``[[1, 1], [1, -1]]``, so each measurement contributes a factor ``1/√2`` that is left out.
This module deliberately shares no code with the ANF semantics.
"""
from __future__ import annotations

from .phase import PhaseProgram


def run_program(program: PhaseProgram, data_input: int, outcomes: int) -> dict[int, int]:
    """Unnormalized state after the outcome sequence ``outcomes`` (bit j is outcome j)."""
    if not 0 <= data_input < (1 << program.data):
        raise ValueError("data input outside the data wires")
    if not 0 <= outcomes < (1 << program.measurements):
        raise ValueError("outcome vector outside the measurement count")
    state = {data_input: 1}
    for op in program.ops:
        if op.kind == "mcx":
            *controls, target = op.qubits
            cmask = sum(1 << c for c in controls)
            state = {(s ^ (1 << target)) if s & cmask == cmask else s: a for s, a in state.items()}
        elif op.kind in ("mcz", "mcz_if"):
            if op.kind == "mcz_if" and not outcomes >> op.outcome & 1:
                continue
            qmask = sum(1 << q for q in op.qubits)
            state = {s: -a if s & qmask == qmask else a for s, a in state.items()}
        elif op.kind == "hmr":
            bit = 1 << op.qubits[0]
            superposed: dict[int, int] = {}
            for s, a in state.items():
                superposed[s & ~bit] = superposed.get(s & ~bit, 0) + a
                superposed[s | bit] = superposed.get(s | bit, 0) + (-a if s & bit else a)
            wanted = bit if outcomes >> op.outcome & 1 else 0
            state = {s & ~bit: a for s, a in superposed.items() if s & bit == wanted and a}
        else:
            raise ValueError(op.kind)
    return {s: a for s, a in state.items() if a}


def outcome_independent_unitary(program: PhaseProgram) -> dict[int, tuple[int, int]] | None:
    """``{x: (output basis state, sign)}`` if every outcome sequence yields the same single
    basis state with the same sign for every input and ancillas end in 0, else ``None``."""
    table = {}
    ancilla_mask = ((1 << program.ancillas) - 1) << program.data
    for x in range(1 << program.data):
        results = {tuple(run_program(program, x, m).items())
                   for m in range(1 << program.measurements)}
        if len(results) != 1:
            return None
        (items,) = results
        if len(items) != 1 or items[0][0] & ancilla_mask:
            return None
        (basis, amplitude), = items
        table[x] = (basis, 1 if amplitude > 0 else -1)
    return table
