"""Checks 4 and 5 of the PR #96 checklist: mutation coverage.

Check 4 (HMR feedback and classical identity): for #90 and #94, mutate phase signs, event
identities, classical slots and borrowed-ancilla contracts; each mutant must be rejected.

Check 5 (transcript proofs): for #92, mutate the common prefix, the suffix, the local embedding,
the preserved-wire contract and the pinned source streams; each mutant must be rejected.

Every mutant is expected to be **rejected for a reason**, not merely to "not crash".
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PR90 = Path(os.environ.get("PR90", "/tmp/audit/pr90"))
PR92 = Path(os.environ.get("PR92", "/tmp/audit/pr92"))
PR94 = Path(os.environ.get("PR94", "/tmp/audit/pr94"))

sys.path.insert(0, str(PR90))
sys.path.insert(0, str(PR92))
sys.path.insert(0, str(PR94))

results: list[tuple[str, str, bool, str]] = []


def record(check: str, label: str, rejected: bool, detail: str = "") -> None:
    results.append((check, label, rejected, detail))


# ---------------------------------------------------------------- check 4: #90 semantics
from research.hybrid_channel.oracle import HybridProgram, same_channel, same_instrument


def probe90(label: str, left, right, *, expect_equal: bool, slots=None):
    """Record whether the oracle returns the *correct* verdict.

    ``expect_equal`` is the answer a sound checker ought to give; a mismatch is the finding.
    """
    if slots is None:
        got = same_channel(left, right, trace_ancillas=False, max_width=5).equivalent
    else:
        got = same_instrument(left, right, observed_slots=slots, max_width=5).equivalent
    correct = got == expect_equal
    record("4", label, correct, f"equivalent={got}, expected {expect_equal}")


# Baseline: identical programs must be equal (sanity, not a mutant).
a = HybridProgram(data=1)
a.hmr(0, "b0").x(0, condition="b0")
b = HybridProgram(data=1)
b.hmr(0, "b0").x(0, condition="b0")
probe90("baseline identical", a, b, expect_equal=True)

# M1: flip the conditioning (apply X when the outcome is 0).
c = HybridProgram(data=1)
c.hmr(0, "b0").x(0, condition="!b0")
probe90("M1 negated classical condition", a, c, expect_equal=False)

# M2: drop the conditional entirely.
d = HybridProgram(data=1)
d.hmr(0, "b0")
probe90("M2 dropped conditional X", a, d, expect_equal=False)

# M3: same unconditional channel, different observed record (instrument split).
e = HybridProgram(data=1)
e.measure_z(0, "b0").x(0, condition="b0")
f = HybridProgram(data=1)
f.measure_z(0, "b0").x(0, condition="b0").store("b0", 0)
probe90("M3 same channel", e, f, expect_equal=True)
probe90("M3 observed record differs", e, f, expect_equal=False, slots=("b0",))

# M4: stale classical bit reused after being overwritten.
g = HybridProgram(data=2)
g.measure_z(0, "b0").measure_z(1, "b0").x(0, condition="b0")
h = HybridProgram(data=2)
h.measure_z(0, "b0").x(0, condition="b0").measure_z(1, "b0")
probe90("M4 slot overwritten before use", g, h, expect_equal=False, slots=("b0",))

# M5: reset instead of HMR (same unconditional channel, different instrument availability).
i = HybridProgram(data=1)
i.reset(0)
j = HybridProgram(data=1)
j.hmr(0, "b0")
probe90("M5 reset vs HMR (channel)", i, j, expect_equal=True)

# ---------------------------------------------------------------- check 4: #94 phase debt
from research.hmr_feedback.repair import synthesize_feedback

from symq.phase import PhaseProgram, phase_semantics

p = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
p.hmr(3)
repaired, proof = synthesize_feedback(p, max_arity=2)
sem_before = phase_semantics(p)
sem_after = phase_semantics(repaired)

ok_debt_removed = not sem_after.phase.terms and bool(sem_before.phase.terms)
record("4", "#94 repair cancels the m-dependent phase", ok_debt_removed,
       f"before={sorted(bin(t) for t in sem_before.phase.terms)}, "
       f"after={sorted(bin(t) for t in sem_after.phase.terms)}")

# M6: removing the appended correction must reintroduce the debt.
uncorrected = PhaseProgram(3, 1, list(p.ops))
debt_back = bool(phase_semantics(uncorrected).phase.terms)
record("4", "M6 correction removed -> debt returns", debt_back)

# M7: a receipt must refuse a mutated program.
try:
    mutated = PhaseProgram(3, 1, list(repaired.ops))
    mutated.mcz(0, 1)
    proof.assert_fresh(p, mutated)
    record("4", "M7 receipt accepts a mutated repair", False)
except ValueError:
    record("4", "M7 receipt rejects a mutated repair", True)

# ---------------------------------------------------------------- check 5: #92 transcripts
from research.temporal_substitution.proof import (
    Common,
    Program,
    Slot,
    TranscriptMismatch,
    UnprovedSubstitution,
    digest,
    verify_transcript,
)

from symq import Circuit, Gate


def program(width, *gates):
    return Program.freeze(Circuit(width, list(gates)))


def stream(width, steps):
    reference, candidate = [], []
    for step in steps:
        if isinstance(step, Common):
            reference.extend(step.gates)
            candidate.extend(step.gates)
        else:
            reference.extend(
                Gate(g.name, tuple(step.wires[q] for q in g.qubits)) for g in step.reference.gates
            )
            candidate.extend(
                Gate(g.name, tuple(step.wires[q] for q in g.qubits)) for g in step.candidate.gates
            )
    return Circuit(width, reference), Circuit(width, candidate)


def check_transcript(steps, width, *, reference=None, candidate=None):
    """Verify ``steps`` against fixed circuits.

    The circuits must be built from the *original* steps and then held fixed, otherwise a mutated
    transcript simply regenerates matching circuits and the mutation is invisible. This is the
    mistake the first version of this harness made.
    """
    if reference is None or candidate is None:
        raise ValueError("pinned circuits and hashes are required")
    return verify_transcript(
        left_circuit, right_circuit, steps,
        reference_sha256=reference, candidate_sha256=candidate,
    )


loop = program(3, Gate("ccx", (0, 1, 2)), Gate("ccx", (0, 1, 2)))
empty = program(3)
good = [
    Common((Gate("cx", (0, 3)),)),
    Slot(loop, empty, (0, 1, 2)),
    Common((Gate("x", (3,)),)),
]
# Pin the circuits once, from the legitimate transcript.
left_circuit, right_circuit = stream(4, good)
ref_hash = digest(Program.freeze(left_circuit))
cand_hash = digest(Program.freeze(right_circuit))
verify_transcript(left_circuit, right_circuit, good,
                  reference_sha256=ref_hash, candidate_sha256=cand_hash)
record("5", "baseline transcript accepted", True, "control")

# M8: common prefix mutated, circuits held fixed.
bad_prefix = [Common((Gate("cx", (1, 3)),)), *good[1:]]
try:
    verify_transcript(left_circuit, right_circuit, bad_prefix,
                      reference_sha256=ref_hash, candidate_sha256=cand_hash)
    record("5", "M8 prefix mutated", False, "accepted")
except (TranscriptMismatch, UnprovedSubstitution):
    record("5", "M8 prefix mutated", True)

# M9: common suffix mutated.
bad_suffix = [*good[:-1], Common((Gate("x", (2,)),))]
try:
    verify_transcript(left_circuit, right_circuit, bad_suffix,
                      reference_sha256=ref_hash, candidate_sha256=cand_hash)
    record("5", "M9 suffix mutated", False, "accepted")
except (TranscriptMismatch, UnprovedSubstitution):
    record("5", "M9 suffix mutated", True)

# M10: local embedding remapped while the circuits keep the original mapping.
bad_embedding = [good[0], Slot(loop, empty, (0, 1, 3)), good[2]]
try:
    verify_transcript(left_circuit, right_circuit, bad_embedding,
                      reference_sha256=ref_hash, candidate_sha256=cand_hash)
    record("5", "M10 embedding remapped", False, "accepted")
except (TranscriptMismatch, UnprovedSubstitution):
    record("5", "M10 embedding remapped", True)

# M11: preserved-wire contract violated (the local program does not restore wire 2).
dirty = program(3, Gate("ccx", (0, 1, 2)))
dirty_slot = [Slot(dirty, dirty, (0, 1, 2), preserved=(2,))]
d_left, d_right = stream(3, dirty_slot)
try:
    verify_transcript(d_left, d_right, dirty_slot,
                      reference_sha256=digest(Program.freeze(d_left)),
                      candidate_sha256=digest(Program.freeze(d_right)))
    record("5", "M11 preserved wire not restored", False, "accepted")
except UnprovedSubstitution:
    record("5", "M11 preserved wire not restored", True)

# M12: pinned source hash wrong.
try:
    verify_transcript(left_circuit, right_circuit, good,
                      reference_sha256="0" * 64, candidate_sha256=cand_hash)
    record("5", "M12 wrong pinned hash", False, "accepted")
except TranscriptMismatch:
    record("5", "M12 wrong pinned hash", True)

# M13: candidate stream mutated in the circuit but transcript still the good one.
mutated_right = Circuit(4, [*right_circuit.gates, Gate("x", (0,))])
try:
    verify_transcript(left_circuit, mutated_right, good,
                      reference_sha256=ref_hash,
                      candidate_sha256=digest(Program.freeze(mutated_right)))
    record("5", "M13 candidate stream mutated", False, "accepted")
except (TranscriptMismatch, UnprovedSubstitution):
    record("5", "M13 candidate stream mutated", True)

# ---------------------------------------------------------------- report
print(f"{'chk':>3s} {'mutant':40s} {'caught':>7s}  detail")
failures = 0
for check, label, rejected, detail in results:
    flag = "yes" if rejected else "NO"
    if not rejected:
        failures += 1
    print(f"{check:>3s} {label:40s} {flag:>7s}  {detail}")
print()
print(f"{len(results) - failures}/{len(results)} mutations handled as expected")
raise SystemExit(0 if failures == 0 else 1)
