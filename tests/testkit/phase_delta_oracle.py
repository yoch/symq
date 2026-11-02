"""Independent scalar oracle for two dyadic programs after a reversible prefix.

It reads only plain gate data (names, wires, angles) and never imports the
symbolic extraction, lifting or certificate code of ``symq.labs``. Phases are
exact ``Fraction`` turns reduced modulo one, so no ``2**k`` scaling is shared
with the checker; integer exponents are derived only when a modulus is asked for.
"""
from __future__ import annotations

from fractions import Fraction

_TURNS = {"t": Fraction(1, 8), "tdg": Fraction(-1, 8), "s": Fraction(1, 4),
          "sdg": Fraction(-1, 4), "z": Fraction(1, 2), "cz": Fraction(1, 2),
          "ccz": Fraction(1, 2)}
_FLIPS = {"x", "cx", "ccx", "mcx"}


def run_prefix(prefix, assignment: int) -> int:
    """Basis execution of an X/CX/CCX/MCX gate stream, controls first, target last."""
    for gate in prefix.gates:
        if gate.name not in _FLIPS:
            raise ValueError(f"oracle prefix gate {gate.name!r}")
        *controls, target = gate.qubits
        if all(assignment >> q & 1 for q in controls):
            assignment ^= 1 << target
    return assignment


def run_program(program, assignment: int) -> tuple[int, Fraction]:
    """(output basis state, accumulated phase in turns modulo one)."""
    turn = Fraction(0)
    for gate in program.gates:
        wires = gate.wires
        if gate.name in _FLIPS:
            *controls, target = wires
            if all(assignment >> q & 1 for q in controls):
                assignment ^= 1 << target
        elif all(assignment >> q & 1 for q in wires):
            turn += Fraction(gate.angle) if gate.name == "phase" else _TURNS[gate.name]
    return assignment, turn % 1


def legal_inputs(width: int, constants) -> list[int]:
    fixed = dict(constants)
    free = [q for q in range(width) if q not in fixed]
    ones = sum(1 << q for q, bit in fixed.items() if bit)
    return [ones | sum((index >> j & 1) << q for j, q in enumerate(free))
            for index in range(1 << len(free))]


def compare(prefix, left, right, constants) -> dict:
    """Exhaustive comparison of left∘prefix and right∘prefix on every legal input."""
    mismatches, turns, first_mismatch = 0, set(), None
    inputs = legal_inputs(prefix.width, constants)
    for x in inputs:
        cut = run_prefix(prefix, x)
        out_l, turn_l = run_program(left, cut)
        out_r, turn_r = run_program(right, cut)
        if out_l != out_r:
            mismatches += 1
            first_mismatch = x if first_mismatch is None else first_mismatch
        turns.add((turn_l - turn_r) % 1)
    ordered = sorted(turns)
    return {"inputs": len(inputs), "output_mismatches": mismatches,
            "first_output_mismatch": first_mismatch, "phase_turns": ordered,
            "global_turn": ordered[0] if not mismatches and len(ordered) == 1 else None}


def image(prefix, constants) -> set[int]:
    return {run_prefix(prefix, x) for x in legal_inputs(prefix.width, constants)}


def exponent(turn: Fraction, k: int) -> int:
    scaled = Fraction(turn) * (1 << k)
    if scaled.denominator != 1:
        raise ValueError("turn is not a multiple of 2**-k")
    return scaled.numerator % (1 << k)


def phase_table(left, right, k: int) -> list[int]:
    """delta(w) = phi_left(w) - phi_right(w) as integers mod 2**k for every program input."""
    return [exponent(run_program(left, w)[1] - run_program(right, w)[1], k)
            for w in range(1 << left.width)]


def interpolate(values, width: int, modulus: int) -> tuple[tuple[int, int], ...]:
    """Truth table -> multilinear coefficients by Moebius inversion over Z/modulus."""
    coefficients = list(values)
    for bit in range(width):
        for mask in range(1 << width):
            if mask >> bit & 1:
                coefficients[mask] -= coefficients[mask ^ (1 << bit)]
    return tuple((mask, c % modulus) for mask, c in enumerate(coefficients) if c % modulus)


def boolean_anf(values, width: int) -> frozenset[int]:
    return frozenset(mask for mask, c in interpolate(values, width, 2))


def universal_certificate(prefix, left, right, constants, k: int, constant: int):
    """(delta, invariant masks, multiplier) for delta - c = (delta - c) * [w not in image].

    The single invariant is the indicator of the complement of the prefix image;
    the identity holds as functions, hence as multilinear polynomials, exactly
    when delta equals the constant on the image.
    """
    modulus = 1 << k
    table = phase_table(left, right, k)
    reached = image(prefix, constants)
    outside = [int(w not in reached) for w in range(1 << prefix.width)]
    delta = interpolate(table, prefix.width, modulus)
    multiplier = interpolate([(value - constant) % modulus for value in table],
                             prefix.width, modulus)
    return delta, boolean_anf(outside, prefix.width), multiplier
