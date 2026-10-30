"""Independent exhaustive and adversarial checks for transcript-bound substitution."""
import random

import pytest

from research.temporal_substitution.proof import (
    Common,
    Program,
    Slot,
    TranscriptMismatch,
    UnprovedSubstitution,
    digest,
    verify_transcript,
)
from symq import Budget, Circuit, Gate, ResourceLimitExceeded
from symq.backends import has_native


def p(width, *gates):
    return Program.freeze(Circuit(width, list(gates)))


def stream(width, steps):
    reference, candidate = [], []
    for step in steps:
        if isinstance(step, Common):
            reference.extend(step.gates)
            candidate.extend(step.gates)
        else:
            reference.extend(Gate(g.name, tuple(step.wires[q] for q in g.qubits))
                             for g in step.reference.gates)
            candidate.extend(Gate(g.name, tuple(step.wires[q] for q in g.qubits))
                             for g in step.candidate.gates)
    return Circuit(width, reference), Circuit(width, candidate)


def check(steps, width, backend="sparse", **kwargs):
    a, b = stream(width, steps)
    return verify_transcript(
        a, b, steps, reference_sha256=digest(Program.freeze(a)),
        candidate_sha256=digest(Program.freeze(b)), backend=backend, **kwargs,
    )


def test_connected_71_wires_with_overlapping_slots_and_no_global_native_check():
    common = Common(tuple(Gate("cx", (i, i + 1)) for i in range(70)))
    left = p(3, Gate("ccx", (0, 1, 2)), Gate("ccx", (0, 1, 2)))
    right = p(3)
    pieces = [common, Slot(left, right, (10, 11, 12)),
              Common((Gate("cx", (12, 13)),)),
              Slot(left, right, (12, 13, 14)),
              Common((Gate("x", (70,)),))]
    a, b = stream(71, pieces)
    assert len(Circuit(71, a.gates + b.gates).wire_blocks()) == 1
    assert a.run(12345) == b.run(12345)
    result = check(pieces, 71)
    assert result.equivalent and result.slots == 2 and result.unique_lemmas == 1
    assert result.global_width == 71
    if has_native():
        native = check(pieces, 71, "zdd-native")
        assert native.equivalent and native.backend == "zdd-native"


def test_dirty_accumulator_is_arbitrary_not_zero():
    left = p(3, Gate("ccx", (0, 1, 2)))
    right = p(3)
    pieces = [Slot(left, right, (0, 1, 2))]
    with pytest.raises(UnprovedSubstitution) as exc:
        check(pieces, 3)
    assert exc.value.witness is not None
    a, b = stream(3, pieces)
    assert a.run(exc.value.witness) != b.run(exc.value.witness)


def test_same_dirty_wire_on_both_sides_does_not_meet_preserved_contract():
    dirty = p(3, Gate("ccx", (0, 1, 2)))
    with pytest.raises(UnprovedSubstitution, match="restore"):
        check([Slot(dirty, dirty, (0, 1, 2), preserved=(2,))], 3)
    check([Slot(dirty, dirty, (0, 1, 2), preserved=(0, 1))], 3)


def test_transcript_binds_full_stream_and_source_hashes():
    left = p(3, Gate("cx", (0, 1)), Gate("cx", (0, 1)))
    steps = [Common((Gate("x", (2,)),)),
             Slot(left, p(3), (0, 1, 2)),
             Common((Gate("cx", (1, 2)),))]
    a, b = stream(3, steps)
    digest_a, digest_b = digest(Program.freeze(a)), digest(Program.freeze(b))
    assert verify_transcript(a, b, steps, reference_sha256=digest_a,
                             candidate_sha256=digest_b).equivalent
    with pytest.raises(TranscriptMismatch, match="hash"):
        verify_transcript(a, b, steps, reference_sha256="0"*64,
                          candidate_sha256=digest_b)
    for mutated in (steps[:-1], [Common((Gate("x", (0,)),)), *steps[1:]],
                    [steps[1], steps[0], steps[2]]):
        with pytest.raises(TranscriptMismatch, match="transcript"):
            verify_transcript(a, b, mutated, reference_sha256=digest_a,
                              candidate_sha256=digest_b)


def test_invalid_mapping_or_unsupported_gate_fails_closed():
    a = p(2, Gate("cx", (0, 1)))
    with pytest.raises(ValueError, match="injective"):
        Slot(a, a, (0, 0))
    with pytest.raises(ValueError):
        check([Slot(a, a, (1, 3))], 3)
    with pytest.raises(ValueError):
        Gate("hmr", (0,))
    with pytest.raises(TypeError):
        check([Common(("x",))], 3)


def test_repeated_local_lemma_cache_and_resource_guards():
    identity = p(2, Gate("cx", (0, 1)), Gate("cx", (0, 1)))
    steps = [Slot(identity, p(2), (0, 1)),
             Slot(identity, p(2), (1, 2)),
             Slot(identity, p(2), (2, 3))]
    assert check(steps, 4).unique_lemmas == 1
    with pytest.raises(ResourceLimitExceeded):
        check(steps, 4, max_expanded_gates=2)
    with pytest.raises(ResourceLimitExceeded):
        check(steps, 4, budget=Budget(max_seconds=1e-12))


@pytest.mark.parametrize("seed", range(25))
def test_random_exhaustive_valid_replacements_and_mutants(seed):
    rng = random.Random(seed)
    width = rng.randint(3, 6)
    i, j, k = rng.sample(range(width), 3)
    orig = p(3, Gate("ccx", (0, 1, 2)), Gate("ccx", (0, 1, 2)))
    steps = [Common((Gate("cx", (i, j)),)),
             Slot(orig, p(3), (i, j, k)),
             Common((Gate("x", (k,)),))]
    a, b = stream(width, steps)
    proof = check(steps, width)
    assert proof.equivalent
    assert all(a.run(x) == b.run(x) for x in range(1 << width))
    bad = [steps[0], Slot(p(3, Gate("ccx", (0, 1, 2))), p(3), (i, j, k)), steps[2]]
    with pytest.raises(UnprovedSubstitution):
        check(bad, width)
