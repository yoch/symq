"""Strict hybrid sign/HMR text import is independently checked on small branches."""

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "hybrid_phase_stream"))

from importer import parse_phase_stream

from symq.circuit import UnsupportedOperation
from symq.phase import PhaseProgram, check_phase_equivalence, phase_semantics
from symq.phase_oracle import run_program


def oracle_check(result):
    p = result.program
    semantics = phase_semantics(p)
    for x in range(1 << p.data):
        for m in range(1 << p.measurements):
            assignment = x | (m << p.data)
            output = sum(bit.evaluate(assignment) << i
                         for i, bit in enumerate(semantics.outputs))
            sign = -1 if semantics.phase.evaluate(assignment) else 1
            assert run_program(p, x, m) == {output: sign}, (p.ops, x, m)


def test_temporary_and_release_and_negative_correction():
    source = """CCX q0 q1 q3
CX q3 q2
HMR q3 b7
R q3
CZ q0 q1 if b7
"""
    good = parse_phase_stream(source, data=3, ancillas=1)
    assert good.measurement_events == 1 and good.resets_proved_zero == 1
    oracle_check(good)
    target = PhaseProgram(3, 1).ccx(0, 1, 2)
    assert check_phase_equivalence(good.program, target).equivalent
    bad = parse_phase_stream(source.replace("CZ q0 q1 if b7", ""), data=3, ancillas=1)
    oracle_check(bad)
    verdict = check_phase_equivalence(bad.program, target)
    assert not verdict.equivalent and any("O2:" in msg for msg in verdict.violations)


def test_xor_of_measurement_events_is_exact_and_versioned():
    source = """X q2
HMR q2 b0
CX q0 q2
HMR q2 b1
BIT_INVERT b0 if b1
Z q1 if b0
"""
    p = parse_phase_stream(source, data=2, ancillas=1)
    assert p.final_classical["b0"].events == 3
    oracle_check(p)
    manual = PhaseProgram(2, 1).x(2)
    a = manual.hmr(2)
    manual.cx(0, 2)
    b = manual.hmr(2)
    manual.z_if(a, 1).z_if(b, 1)
    assert phase_semantics(p.program) == phase_semantics(manual)


def test_classical_storage_reuse_does_not_reuse_measurement_event():
    p = parse_phase_stream("HMR q1 b0\nX q1\nHMR q1 b0\nZ q0 if b0",
                           data=1, ancillas=1)
    assert p.measurement_events == 2 and p.final_classical["b0"].events == 2
    oracle_check(p)


def test_global_and_negated_signs_and_oxor():
    p = parse_phase_stream(
        "HMR q1 b0\nBIT_STORE1 b2\nOXOR b2 b0\nNEG if b2\nZ q0 if !b2",
        data=1, ancillas=1)
    assert p.final_classical["b2"].constant == 1
    assert p.final_classical["b2"].events == 1
    oracle_check(p)


def test_swap_and_cswap_are_exact_permutations():
    for op, width in [("SWAP q0 q1", 2), ("CSWAP q0 q1 q2", 3)]:
        p = parse_phase_stream(op, data=width)
        oracle_check(p)
        sem = phase_semantics(p.program)
        for x in range(1 << width):
            actual = sum(f.evaluate(x) << i for i, f in enumerate(sem.outputs))
            expected = x
            if op.startswith("SWAP"):
                if (x & 1) != ((x >> 1) & 1):
                    expected ^= 3
            elif x & 1 and (((x >> 1) & 1) != ((x >> 2) & 1)):
                expected ^= 6
            assert actual == expected


@pytest.mark.parametrize("source", [
    "R q0",
    "CX q0 q1\nR q1",
    "X q1\nR q1",
    "H q0",
    "Z_POW q0 0.25",
    "CX q0 q1 if b0",
    "HMR q1 b0\nX q0 if b0",
    "CZ q0 q1 if b0",
    "BIT_INVERT b1",
    "BIT_STORE0 b0\nOXOR b0 b1",
    "HMR q1 b0\nZ q0 if b2",
    "PUSH_CONDITION if b0",
    "POP_CONDITION",
    "MEASURE q0 b0",
    "R q0 if b0",
])
def test_unsupported_or_entangled_reset_refuses(source):
    with pytest.raises(UnsupportedOperation):
        parse_phase_stream(source, data=1, ancillas=2)


def test_clean_reset_and_instruction_budget():
    ok = parse_phase_stream("R q1", data=1, ancillas=1)
    assert ok.resets_proved_zero == 1 and not ok.program.ops
    with pytest.raises(UnsupportedOperation, match="budget"):
        parse_phase_stream("X q0\nX q0", data=1, max_instructions=1)


@pytest.mark.parametrize("seed", range(24))
def test_random_small_streams_match_independent_state_oracle(seed):
    rng = random.Random(2026102900 + seed)
    lines = []
    latest = []
    for _ in range(12):
        op = rng.choice(["X", "CX", "CCX", "Z", "CZ", "CCZ", "HMR"])
        if op == "HMR":
            bit = f"b{rng.randrange(3)}"
            latest.append(bit)
            lines.append(f"HMR q{rng.randrange(4)} {bit}")
        else:
            arity = {"X": 1, "CX": 2, "CCX": 3, "Z": 1, "CZ": 2, "CCZ": 3}[op]
            wires = rng.sample(range(4), arity)
            line = op + " " + " ".join(f"q{x}" for x in wires)
            if op in {"Z", "CZ", "CCZ"} and latest and rng.randrange(3) == 0:
                line += " if " + rng.choice(latest)
            lines.append(line)
    oracle_check(parse_phase_stream("\n".join(lines), data=2, ancillas=2))
