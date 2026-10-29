"""Canonical hybrid oracle, immutable SSA and strict source subset qualification."""
import random
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction

import pytest

from symq.circuit import UnsupportedOperation
from symq.experimental.hybrid import (
    HybridProgram,
    coherence_image,
    coherence_image_shared,
    coherence_instrument,
    freeze_hybrid,
    same_channel,
)
from symq.experimental.importers import lower_phase_program, parse_phase_stream
from symq.experimental.qasm3 import parse_qasm3
from symq.phase import PhaseProgram, check_phase_equivalence
from symq.phase_oracle import run_program
from symq.resources import Budget, ResourceLimitExceeded


def test_ssa_slot_reuse_freezes_the_event_and_every_read_version():
    builder = HybridProgram(1, 1).hmr(1, "b0").z(0, condition="b0")
    builder.x(1).hmr(1, "b0").invert("b0").z(0, condition="!b0")
    ir = freeze_hybrid(builder)
    assert [e.index for e in ir.events] == [0, 1]
    assert ir.operations[1].condition.events == 1
    assert ir.operations[-1].condition.events == 2
    assert ir.operations[-1].condition.constant == 1
    assert ir.final_slots[0].version == 2
    before = ir.to_program()
    builder.x(0)
    assert ir.to_program().ops == before.ops
    with pytest.raises(FrozenInstanceError):
        ir.events[0].index = 9
    with pytest.raises(UnsupportedOperation, match="SSA"):
        replace(ir, events=tuple(reversed(ir.events))).to_program()
    bad = replace(ir.operations[1], condition=ir.operations[-1].condition)
    with pytest.raises(UnsupportedOperation, match="SSA"):
        replace(ir, operations=(ir.operations[0], bad, *ir.operations[2:])).validate()


def test_qasm_z_measurement_guarded_values_and_true_reset_preserve_cptp():
    source = """OPENQASM 3.0;
    include "stdgates.inc";
    qubit[2] q; bit[2] b;
    b[0] = measure q[0];
    b[1] = !b[0] ^ b[1];
    if (b[1] == 0) { x q[1]; z q[0]; }
    reset q[0];
    """
    parsed = parse_qasm3(source).to_program()
    manual = HybridProgram(2).store("b0", 0).store("b1", 0).measure_z(0, "b0")
    manual.store("b1", 1).oxor("b1", "b0").x(1, condition="!b1")
    manual.z(0, condition="!b1").reset(0)
    assert same_channel(parsed, manual).equivalent
    # A dirty reset loses coherence. It is never Boolean assignment/lowering.
    assert coherence_image(parsed, 0, 1) == {}
    with pytest.raises(UnsupportedOperation):
        lower_phase_program(parsed)


def test_qasm_assignment_reads_old_destination_and_slots_reuse_versions():
    p = parse_qasm3("""OPENQASM 3; qubit q; bit b;
                    b = measure q; b = b ^ b ^ 1; if (!b) x q;""").to_program()
    assert coherence_instrument(p, 0, 0, observed_slots=("b0",)) == {(1,): {(0, 0): 1}}
    assert coherence_instrument(p, 1, 1, observed_slots=("b0",)) == {(1,): {(1, 1): 1}}


@pytest.mark.parametrize("body", [
    "h q[0];", "rx(0.1) q[0];", "u(0,0,0) q[0];", "reset q;",
    "if (b[0]) { if (b[0]) x q[0]; }", "if (b[0]) reset q[0];",
    "if (b[0] & b[1]) x q[0];", "if (b[0]) { x q[0];",
    "if (b[0]) {}", "x q[0],q[1];", "x q[2];", "x missing;",
    "b[0] = b[0] & b[1];", "b[0] = measure q[0]; trailing",
    "qubit r;", "for int i in [0:1] { x q[0]; }", "pragma ignored;",
])
def test_qasm_rejects_every_unparsed_or_unsupported_operation(body):
    # An initial gate makes declarations inside the body invalid too.
    with pytest.raises(UnsupportedOperation):
        parse_qasm3("OPENQASM 3.0; qubit[2] q; bit[2] b; z q[0];" + body)


def test_qasm_limits_and_explicit_initial_frame():
    with pytest.raises(UnsupportedOperation):
        parse_qasm3("OPENQASM 3; qubit[2] q;", data=1, ancillas=0)
    with pytest.raises(UnsupportedOperation):
        parse_qasm3("OPENQASM 3; qubit[100] q;", max_register_bits=4)
    with pytest.raises(UnsupportedOperation):
        parse_qasm3("OPENQASM 3; qubit q; x q; x q;", max_instructions=1)
    with pytest.raises(UnsupportedOperation):
        parse_qasm3("OPENQASM 3; qubit q; bit b; if(b){x q;z q;}", max_condition_ops=1)


def test_pr88_strict_stream_lowering_checked_by_independent_branch_oracle():
    source = "CCX q0 q1 q3\nCX q3 q2\nHMR q3 b7\nR q3\nCZ q0 q1 if b7"
    imported = parse_phase_stream(source, data=3, ancillas=1)
    assert imported.measurement_events == 1 and imported.resets_proved_zero == 1
    target = PhaseProgram(3, 1).ccx(0, 1, 2)
    assert check_phase_equivalence(imported.program, target).equivalent
    for x in range(8):
        for m in range(2):
            expected = x ^ (4 if x & 3 == 3 else 0)
            assert run_program(imported.program, x, m) == {expected: 1}
    builder = HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b7")
    builder.reset(3).cz(0, 1, condition="b7")
    assert lower_phase_program(freeze_hybrid(builder)) == imported.program
    assert lower_phase_program(HybridProgram(5).mcx(0, 1, 2, 3, 4)) == (
        PhaseProgram(5).mcx(0, 1, 2, 3, 4))
    for bad in (HybridProgram(1).reset(0), HybridProgram(1).measure_z(0, "b0"),
                HybridProgram(1, 1).hmr(1, "b0").x(0, condition="b0")):
        with pytest.raises(UnsupportedOperation):
            lower_phase_program(bad)


def test_branch_sharing_matches_unshared_oracle_all_coherences_and_observations():
    rng = random.Random(81073)
    programs = []
    for _ in range(16):
        p = HybridProgram(2, 1).store("b0", 0).store("b1", 1)
        for _ in range(8):
            choice = rng.randrange(8)
            q = rng.randrange(3)
            slot = f"b{rng.randrange(2)}"
            if choice == 0:
                p.hmr(q, slot)
            elif choice == 1:
                p.measure_z(q, slot)
            elif choice == 2:
                p.reset(q)
            elif choice == 3:
                p.oxor("b0", "b1")
            elif choice == 4:
                p.invert(slot, condition="!b1")
            elif choice == 5:
                p.x(q, condition=slot)
            elif choice == 6:
                p.cz(0, 1, condition="!b0")
            else:
                p.store(slot, rng.randrange(2))
        programs.append(p)
    for p in programs:
        for x in range(4):
            for y in range(4):
                for trace in (False, True):
                    shared = coherence_image_shared(p, x, y, trace_ancillas=trace)
                    assert shared.get((), {}) == coherence_image(p, x, y, trace_ancillas=trace)
                    observed = coherence_image_shared(p, x, y, trace_ancillas=trace,
                                                     observed_slots=("b0", "b1"))
                    assert observed == coherence_instrument(p, x, y, trace_ancillas=trace,
                                                           observed_slots=("b0", "b1"))


def test_sharing_discards_dead_histories_but_keeps_exponential_live_records():
    dead = HybridProgram(1, 1)
    for _ in range(40):
        dead.hmr(1, "b0")
    assert coherence_image_shared(dead, 0, 1, max_branches=1) == {(): {(0, 1): Fraction(1)}}
    with pytest.raises(ResourceLimitExceeded):
        coherence_image(dead, 0, 1, max_events=64, max_branches=256)
    live = HybridProgram(1, 1)
    for event in range(8):
        live.hmr(1, f"b{event}")
    for event in range(8):
        live.x(0, condition=f"b{event}")
    with pytest.raises(ResourceLimitExceeded, match="branches"):
        coherence_image_shared(live, 0, 0, max_branches=128)
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        coherence_image_shared(live, 0, 0, budget=Budget(max_terms=1))
