"""The density-matrix oracle itself, tested against independently known states.

The first version of ``channel.py`` had two defects that the cross-check against the ANF
criterion could not catch, because both sides were wrong in ways that agreed on the instances
run: the partial trace summed entries with *different* ancilla configurations, and basis pairs
were packed into shifted integers. These tests pin the oracle on cases whose answer is known by
hand, before it is used as a reference for anything else.
"""
from __future__ import annotations

import itertools
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "innovation" / "2026-10-28" / "prototype"))

import channel

from symq.phase import PhaseProgram


def bell(program: PhaseProgram) -> dict[tuple[int, int], Fraction]:
    """``(|00> + |11>)(<00| + <11|) / 2`` on ``data + 1`` wire, wire 0 the data wire."""
    half = Fraction(1, 2)
    states = [0, 0b11]
    matrix = {}
    for row, column in itertools.product(states, repeat=2):
        matrix[(row, column)] = half
    return matrix


def test_the_partial_trace_of_a_bell_pair_is_maximally_mixed():
    program = PhaseProgram(1, 1)
    reduced = channel.partial_trace(program, bell(program))
    assert reduced == {(0, 0): Fraction(1, 2), (1, 1): Fraction(1, 2)}


def test_the_partial_trace_drops_cross_ancilla_terms():
    """An entry whose row and column differ in the ancilla belongs to no reduced entry."""
    program = PhaseProgram(1, 1)
    matrix = {(0b00, 0b10): Fraction(1), (0b10, 0b00): Fraction(1)}
    assert channel.partial_trace(program, matrix) == {}


def test_the_partial_trace_keeps_the_trace_of_a_product_state():
    program = PhaseProgram(2, 1)  # data wires 0-1, ancilla wire 2
    # Row has ancilla 1, column has ancilla 0: the entry belongs to no reduced entry.
    assert channel.partial_trace(program, {(0b101, 0b001): Fraction(1)}) == {}
    # Same ancilla bit on both sides: the data parts survive.
    assert channel.partial_trace(program, {(0b101, 0b101): Fraction(1)}) == {
        (0b01, 0b01): Fraction(1)}
    assert channel.partial_trace(program, {(0b110, 0b100): Fraction(2)}) == {
        (0b10, 0b00): Fraction(2)}


def test_a_reduced_state_is_physical():
    program = PhaseProgram(1, 1)
    reduced = channel.partial_trace(program, bell(program))
    assert channel.trace(reduced) == 1
    assert channel.is_physical(program, reduced)


def test_pair_keys_are_tuples_and_cannot_collide():
    """The keys are ``(x, y, u, v)`` tuples: distinct pairs are distinct keys by construction.

    The old encoding packed ``(x, y)`` into ``x << 16 | y``, which collided as soon as either
    component needed 16 bits. The property is now structural, and this test pins the type so a
    future packing cannot creep back in.
    """
    program = PhaseProgram(2, 0)
    matrix = channel.channel_matrix(program)
    key = next(iter(matrix))
    assert len(key) == 4 and all(isinstance(part, int) for part in key)
    assert (3, 3, 3, 3) in matrix


def test_the_identity_program_has_the_identity_channel():
    program = PhaseProgram(2, 0)
    matrix = channel.channel_matrix(program)
    assert matrix == {(x, y, x, y): Fraction(1)
                      for x in range(4) for y in range(4)}


def test_a_bit_flip_maps_every_coherence_to_its_image():
    program = PhaseProgram(2, 0).x(1)
    matrix = channel.channel_matrix(program)
    for x in range(4):
        for y in range(4):
            assert matrix[(x, y, x ^ 2, y ^ 2)] == 1
    assert len(matrix) == 16


def test_a_phase_flips_the_sign_of_the_coherence():
    program = PhaseProgram(2, 0).mcz(0, 1)
    matrix = channel.channel_matrix(program)
    # Keys are (x, y, u, v): input row, input column, output row, output column.
    # The phase is (-1)^(x0 x1 + y0 y1), so a coherence picks it up only in its own coordinates.
    assert matrix[(0b11, 0b11, 0b11, 0b11)] == 1
    assert matrix[(0b00, 0b11, 0b00, 0b11)] == -1
    assert matrix[(0b11, 0b00, 0b11, 0b00)] == -1
    assert matrix[(0b01, 0b00, 0b01, 0b00)] == 1


def test_hmr_of_a_basis_state_gives_two_equal_branches():
    program = PhaseProgram(1, 1).x(1)
    program.hmr(1)
    for outcomes in (0, 1):
        operator = channel.kraus_operator(program, outcomes)
        sign = 1 if outcomes == 0 else -1
        assert operator == {(0, 0): Fraction(sign), (1, 1): Fraction(sign)}
    assert channel.is_trace_preserving(program)


def test_a_non_unitary_channel_is_recognised_as_such():
    """A program that measures a data wire and never restores it is trace preserving but the
    ancilla state is not clean; the data channel is not a unitary."""
    program = PhaseProgram(1, 1)
    program.mcx(0, 1)
    program.hmr(1)
    assert channel.is_trace_preserving(program)
    reduced = channel.coherence_image(program, 0, 1)
    assert reduced == {}


def test_trace_preserving_holds_for_random_programs():
    import random

    from test_factored import random_program

    rng = random.Random(3)
    for _ in range(40):
        program = random_program(rng, rng.randint(1, 2), rng.randint(0, 1),
                                 rng.randint(1, 7))
        assert channel.is_trace_preserving(program), program.ops
