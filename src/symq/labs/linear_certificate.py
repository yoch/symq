"""Tiny independently checkable GF(2) affine inconsistency witnesses.

Only proves a finite *classical linear system* unsatisfiable, not a quantum
or SAT/CNF theorem.
"""
from __future__ import annotations


def verify_dual(columns: tuple[int, ...], rhs: int, rows: int, witness: int) -> bool:
    """y^T A = 0, y^T b = 1 with columns encoded as row-bitsets."""
    if (type(rows) is not int or rows < 1 or type(rhs) is not int or
            rhs < 0 or rhs >> rows or type(witness) is not int or
            witness < 0 or witness >> rows or type(columns) is not tuple or
            any(type(c) is not int or c < 0 or c >> rows for c in columns)):
        raise ValueError("all GF(2) columns/witnesses must fit declared rows")
    return bool((rhs & witness).bit_count() & 1) and all(
        (column & witness).bit_count() % 2 == 0 for column in columns
    )


def unsat_dual(columns: tuple[int, ...], rhs: int, rows: int) -> int | None:
    """Return a self-verifiable dual UNSAT certificate, or None if satisfiable."""
    verify_dual(columns, rhs, rows, 0)  # validate inputs, not a SAT assertion
    pivots: dict[int, tuple[int, int, int]] = {}
    for row in range(rows):
        vector = sum(1 << j for j, c in enumerate(columns) if c >> row & 1)
        target = rhs >> row & 1
        witness = 1 << row
        while vector:
            bit = vector.bit_length() - 1
            if bit not in pivots:
                pivots[bit] = (vector, target, witness)
                break
            old, old_target, old_witness = pivots[bit]
            vector ^= old
            target ^= old_target
            witness ^= old_witness
        if not vector and target:
            if not verify_dual(columns, rhs, rows, witness):
                raise RuntimeError("inconsistent GF(2) dual witness")
            return witness
    return None
