"""Local CPTP substitution: coherent frame, classical liveness and hostile transcripts."""
from dataclasses import replace

import pytest

from symq import Budget, ResourceLimitExceeded
from symq.circuit import UnsupportedOperation
from symq.experimental.composition import (
    ChannelSlot,
    FrozenHybridProgram,
    HybridCommon,
    HybridFragment,
    TranscriptMismatch,
    UnprovedSubstitution,
    hybrid_digest,
    verify_channel_transcript,
)
from symq.experimental.hybrid import HOp, HybridProgram, same_channel


def fragment(width, *ops, inputs=()):
    return HybridFragment(width, tuple(ops), inputs)


def streams(data, ancillas, steps):
    from symq.experimental.composition import _map_ops
    left, right = [], []
    for step in steps:
        if isinstance(step, HybridCommon):
            left.extend(step.ops)
            right.extend(step.ops)
        else:
            left.extend(_map_ops(step.reference.ops, step.wires, dict(step.classical_map)))
            right.extend(_map_ops(step.candidate.ops, step.wires, dict(step.classical_map)))
    return HybridProgram(data, ancillas, left), HybridProgram(data, ancillas, right)


def check(data, ancillas, steps, **kwargs):
    left, right = streams(data, ancillas, steps)
    return verify_channel_transcript(
        left, right, steps, reference_sha256=hybrid_digest(left),
        candidate_sha256=hybrid_digest(right), **kwargs,
    )


def temporary_and():
    compute = (HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)))
    a = fragment(4, *compute, HOp("ccx", (0, 1, 3)))
    b = fragment(4, *compute, HOp("hmr", (3,), slot="b0"),
                 HOp("cz", (0, 1), condition="b0"))
    return ChannelSlot(a, b, (0, 1, 2, 3), (("b0", "b7"),), clean=(3,))


def test_temporary_and_full_coherent_channel_and_entangled_frame():
    slot = temporary_and()
    # An entangling common prefix/suffix connects all 71 wires. Only the 4-wire
    # lemma is enumerated; matrix-unit equality guarantees an arbitrary frame.
    steps = [HybridCommon(tuple(HOp("cx", (i, i+1)) for i in range(70))),
             HybridCommon((HOp("reset", (3,)),)), slot,
             HybridCommon((HOp("cx", (2, 70)),))]
    proof = check(70, 1, steps)
    assert proof.equivalent and proof.global_width == 71
    assert proof.checked_pairs == 64 and proof.unique_lemmas == 1
    a, b = streams(3, 1, [slot])
    assert same_channel(a, b).equivalent  # independent full-program oracle, small case


def test_temporary_and_mutants_clean_assumption_and_missing_correction():
    slot = temporary_and()
    with pytest.raises(UnprovedSubstitution, match="preparation"):
        check(4, 0, [slot])
    bad = replace(slot, candidate=replace(slot.candidate, ops=slot.candidate.ops[:-1]))
    with pytest.raises(UnprovedSubstitution, match="differs"):
        check(3, 1, [bad])
    # An initialized ancilla ceases to be clean after entangling with data.
    prefix = HybridCommon((HOp("cx", (0, 3)),))
    with pytest.raises(UnprovedSubstitution, match="preparation"):
        check(3, 1, [prefix, slot])


def test_immutable_stream_and_exact_transcript_coverage():
    slot = temporary_and()
    a, b = streams(3, 1, [slot])
    frozen = FrozenHybridProgram.freeze(a)
    a.ops.append(HOp("x", (0,)))
    assert frozen.ops != tuple(a.ops)
    with pytest.raises(TranscriptMismatch, match="hash"):
        verify_channel_transcript(a, b, [slot], reference_sha256=hybrid_digest(frozen),
                                  candidate_sha256=hybrid_digest(b))
    with pytest.raises(TranscriptMismatch, match="cover"):
        verify_channel_transcript(a, b, [slot], reference_sha256=hybrid_digest(a),
                                  candidate_sha256=hybrid_digest(b))
    with pytest.raises(ValueError, match="injective"):
        replace(slot, wires=(0, 1, 2, 2))
    with pytest.raises(ValueError, match="injective"):
        replace(slot, classical_map=(("b0", "b7"), ("b1", "b7")))


def test_classical_live_cut_uses_instrument_before_guarded_suffix():
    # Measuring a reset-zero wire always emits 0. Invert changes only the live
    # record. The unconditional quantum channel is identical, the suffix differs.
    a = fragment(2, HOp("reset", (1,)), HOp("measure_z", (1,), slot="b0"))
    b = fragment(2, *a.ops, HOp("invert", slot="b0"))
    slot = ChannelSlot(a, b, (0, 1), (("b0", "b0"),))
    check(2, 0, [slot])  # dead record can legitimately be forgotten
    with pytest.raises(UnprovedSubstitution, match="instrument"):
        check(2, 0, [slot, HybridCommon((HOp("x", (0,), condition="b0"),))])
    with pytest.raises(UnprovedSubstitution, match="instrument"):
        check(2, 0, [slot], observed_slots=("b0",))


def test_arbitrary_classical_input_is_not_invented_zero():
    a = fragment(1, HOp("x", (0,), condition="b0"), inputs=("b0",))
    b = fragment(1, inputs=("b0",))
    slot = ChannelSlot(a, b, (0,), (("b0", "b3"),))
    with pytest.raises(UnprovedSubstitution, match="differs"):
        check(1, 0, [HybridCommon((HOp("store", slot="b3", value=0),)), slot])
    with pytest.raises(UnsupportedOperation):
        # The covered global program itself rejects a future/uninitialized bit.
        streams(1, 0, [slot])


def test_dirty_borrowed_identity_includes_correlations():
    # Both circuits leave the dirty *diagonal* value unchanged. A phase changes
    # its off-diagonals, so equality between sides is not a restoration proof.
    bad = fragment(2, HOp("cz", (0, 1)))
    slot = ChannelSlot(bad, bad, (0, 1), preserved=(1,))
    with pytest.raises(UnprovedSubstitution, match="identity correlation"):
        check(2, 0, [slot])
    good = fragment(2, HOp("cx", (1, 0)), HOp("cx", (1, 0)), HOp("z", (0,)))
    assert check(2, 0, [ChannelSlot(good, good, (0, 1), preserved=(1,))]).equivalent


def test_local_trace_requires_terminal_discard_and_preserves_reduced_channel():
    slot = ChannelSlot(fragment(2, HOp("x", (1,))), fragment(2), (0, 1), discarded=(1,))
    assert check(2, 0, [slot], discarded_global=(1,)).equivalent
    with pytest.raises(UnprovedSubstitution, match="terminal"):
        check(2, 0, [slot])
    with pytest.raises(UnprovedSubstitution, match="terminal"):
        check(2, 0, [slot, HybridCommon((HOp("cx", (1, 0)),))], discarded_global=(1,))


def test_leaf_deduplication_resource_limits_and_large_frame():
    a = fragment(2, HOp("cx", (0, 1)), HOp("cx", (0, 1)))
    b = fragment(2)
    steps = [ChannelSlot(a, b, (0, 1)), ChannelSlot(a, b, (1, 2))]
    proof = check(3, 0, steps)
    assert proof.unique_lemmas == 1 and proof.slots == 2
    with pytest.raises(ResourceLimitExceeded):
        check(3, 0, steps, max_local_width=1)
    with pytest.raises(ResourceLimitExceeded):
        check(3, 0, steps, max_expanded_ops=1)
    with pytest.raises(ResourceLimitExceeded):
        check(3, 0, steps, budget=Budget(max_seconds=1e-12))


def test_phase_ledger_reconstructs_event_and_exact_discharge_point():
    from symq.experimental.ledger import PhaseDischarge, UnresolvedPhaseDebt, verify_phase_ledger
    _, program = streams(3, 1, [temporary_and()])
    proof = verify_phase_ledger(program, (PhaseDischarge(0, 3),))
    assert proof.events[0].operation_index == 2
    assert proof.events[0].identity == 0
    assert proof.events[0].measured_value.terms == frozenset({0b11})
    assert not proof.final_phase.terms
    with pytest.raises(UnresolvedPhaseDebt, match="nonzero"):
        verify_phase_ledger(program, (PhaseDischarge(0, 2),))
    with pytest.raises(UnresolvedPhaseDebt, match="precede"):
        verify_phase_ledger(program, (PhaseDischarge(0, 1),))
    with pytest.raises(ValueError, match="unknown"):
        verify_phase_ledger(program, (PhaseDischarge(1, 3),))
    with pytest.raises(UnresolvedPhaseDebt, match="every"):
        verify_phase_ledger(program, ())
    program.x(0)
    with pytest.raises(ValueError, match="changed"):
        proof.assert_fresh(program)


def test_reused_classical_slot_cannot_impersonate_old_measurement_event():
    from symq.experimental.ledger import PhaseDischarge, UnresolvedPhaseDebt, verify_phase_ledger
    program = (HybridProgram(2, 1).ccx(0, 1, 2).hmr(2, "b0")
               .hmr(2, "b0").cz(0, 1, condition="b0"))
    with pytest.raises(UnresolvedPhaseDebt, match="nonzero"):
        verify_phase_ledger(program, (PhaseDischarge(0, 3), PhaseDischarge(1, 3)))
    # Replaying the first event through a separate slot discharges the real debt.
    good = (HybridProgram(2, 1).ccx(0, 1, 2).hmr(2, "b0")
            .store("b1", 0).oxor("b1", "b0").hmr(2, "b0")
            .cz(0, 1, condition="b1"))
    proof = verify_phase_ledger(good, (PhaseDischarge(0, 5), PhaseDischarge(1, 5)))
    assert [event.identity for event in proof.events] == [0, 1]
    assert [event.destination for event in proof.events] == ["b0", "b0"]


def test_ledger_refuses_reset_of_unproved_value_and_reintroduced_debt():
    from symq.experimental.ledger import PhaseDischarge, UnresolvedPhaseDebt, verify_phase_ledger
    with pytest.raises(UnsupportedOperation, match="channel semantics"):
        verify_phase_ledger(HybridProgram(1).reset(0), ())
    _, program = streams(3, 1, [temporary_and()])
    program.cz(0, 1, condition="b7")
    with pytest.raises(UnresolvedPhaseDebt, match="reintroduced"):
        verify_phase_ledger(program, (PhaseDischarge(0, 3),))
    with pytest.raises(ResourceLimitExceeded):
        verify_phase_ledger(program, (PhaseDischarge(0, 3),), max_variables=2)


def classical_graph(mutant=False):
    from symq import Circuit
    from symq.experimental.classical_transcript import Program
    from symq.experimental.proof_graph import ClassicalObligation, ProofGraph, ProofNode
    reference = Program.freeze(Circuit(2).cx(0, 1).cx(0, 1))
    candidate = Program.freeze(Circuit(2).x(1) if mutant else Circuit(2))
    leaf = ProofNode("lemma", ClassicalObligation(reference, candidate))
    middle = ProofNode("local", dependencies=("lemma",))
    root = ProofNode("root", dependencies=("local",))
    return ProofGraph((root, leaf, middle), "root")


def test_graph_json_is_proposal_and_mutated_leaf_invalidates_every_ancestor(tmp_path):
    from symq.experimental.proof_graph import ProofGraph, ProofKernel
    graph = classical_graph()
    kernel = ProofKernel(cache_directory=tmp_path)
    assert kernel.verify(graph).accepted
    assert all(e.cached for e in kernel.verify(graph).evidence)
    bad = classical_graph(mutant=True)
    old, new = graph.addresses(), bad.addresses()
    assert all(old[name] != new[name] for name in old)
    verdict = kernel.verify(bad)
    assert not verdict.accepted
    assert all(not e.cached for e in verdict.evidence)
    roundtrip = ProofGraph.from_json(graph.to_json())
    assert roundtrip == graph
    assert ProofKernel().verify(roundtrip).accepted
    # Even an affirmative content-addressed disk receipt never certifies a leaf.
    for path in tmp_path.glob("*.json"):
        path.write_text('{"accepted":true,"verdict":"equivalent"}')
    assert not ProofKernel(cache_directory=tmp_path).verify(bad).accepted
    with pytest.raises(ValueError, match="verdicts"):
        ProofGraph.from_json('{"accepted":true,"verdict":"equivalent"}')


def test_graph_fails_closed_on_version_missing_dependency_and_cycle():
    from symq.experimental.proof_graph import ProofGraph, ProofNode
    graph = classical_graph()
    with pytest.raises(ValueError, match="version"):
        replace(graph, version="future-v500")
    with pytest.raises(ValueError, match="missing"):
        replace(graph, nodes=(ProofNode("root", dependencies=("absent",)),))
    with pytest.raises(ValueError, match="cycle"):
        ProofGraph((ProofNode("a", dependencies=("b",)),
                    ProofNode("b", dependencies=("a",))), "a")
    with pytest.raises(TypeError, match="recognizes"):
        ProofNode("leaf", obligation=True)


def test_graph_replays_full_composition_transcript_and_ignores_claimed_receipt():
    from symq.experimental.proof_graph import (
        ProofGraph,
        ProofKernel,
        ProofNode,
        TranscriptObligation,
    )
    slot = temporary_and()
    a, b = streams(3, 1, [slot])
    obligation = TranscriptObligation(FrozenHybridProgram.freeze(a),
                                     FrozenHybridProgram.freeze(b), (slot,))
    graph = ProofGraph((ProofNode("composition", obligation),), "composition")
    assert ProofKernel().verify(ProofGraph.from_json(graph.to_json())).accepted
    malformed = replace(obligation, steps=(HybridCommon(tuple(a.ops)),))
    with pytest.raises(TranscriptMismatch, match="cover"):
        ProofKernel().verify(ProofGraph((ProofNode("composition", malformed),), "composition"))


def test_independent_graph_checks_spawn_distinct_processes_and_backends():
    from symq.experimental.execution import HardLimits
    from symq.experimental.proof_graph import ProofKernel
    result = ProofKernel().verify(classical_graph(), independent=True,
                                  limits=HardLimits(wall_seconds=10, memory_bytes=512*1024**2))
    assert result.accepted
    leaf = next(e for e in result.evidence if e.name == "lemma")
    assert len(leaf.independent_runs) == 2
    assert all(run.status == "completed" and run.value is True for run in leaf.independent_runs)
    assert all(run.peak_rss_bytes is not None for run in leaf.independent_runs)


def test_public_dirty_bridge_gadget_restores_entangled_borrowed_wire():
    # Public four-CNOT bridge identity; the middle borrowed wire may be entangled
    # with an external reference and must return with every correlation intact.
    bridge = fragment(3, HOp("cx", (0, 1)), HOp("cx", (1, 2)),
                      HOp("cx", (0, 1)), HOp("cx", (1, 2)))
    direct = fragment(3, HOp("cx", (0, 2)))
    slot = ChannelSlot(bridge, direct, (0, 1, 2), preserved=(1,))
    proof = check(4, 0, [HybridCommon((HOp("cx", (3, 1)),)), slot,
                         HybridCommon((HOp("cx", (1, 3)),))])
    assert proof.equivalent
    mutant = replace(slot, reference=replace(bridge, ops=bridge.ops[:-1]))
    with pytest.raises(UnprovedSubstitution):
        check(4, 0, [mutant])


def test_clean_preparation_flows_from_a_previous_verified_local_lemma():
    first = temporary_and()
    # Full output equality proves the clean wire returns zero, even when the
    # conservative prefix value propagation cannot simplify CCX twice.
    assert check(3, 1, [first, first]).equivalent


def parallel_graph():
    from symq.experimental.proof_graph import ProofGraph, ProofNode
    first = classical_graph().nodes[1]
    second_query = replace(first.obligation, preserved=(0,))
    second = ProofNode("second", second_query)
    return ProofGraph((first, second, ProofNode("all", dependencies=("lemma", "second"))), "all")


def test_parallel_leaf_admission_shares_parent_deadline_and_memory(monkeypatch):
    import threading

    from symq.experimental import proof_graph
    from symq.experimental.execution import HardLimits, IsolatedResult
    barrier = threading.Barrier(2)
    admissions = []
    lock = threading.Lock()

    def isolated(function, obligation, backend, budget, *, limits, session):
        with lock:
            admissions.append((session, limits.memory_bytes, backend))
        # Both distinct leaf tasks must be admitted concurrently, for both runs.
        barrier.wait(timeout=3)
        return IsolatedResult("completed", "test subprocess orchestration", True)

    monkeypatch.setattr(proof_graph, "run_isolated", isolated)
    result = proof_graph.ProofKernel().verify(
        parallel_graph(), independent=True, parallel_workers=2,
        budget=Budget(max_seconds=5), limits=HardLimits(wall_seconds=5, memory_bytes=1024),
    )
    assert result.accepted and len(admissions) == 4
    assert len({id(session) for session, _, _ in admissions}) == 1
    assert {memory for _, memory, _ in admissions} == {512}
    assert [backend for _, _, backend in admissions].count("truthtable") == 2


def test_late_parallel_results_never_become_certified_or_cached(monkeypatch):
    import time

    from symq.experimental import proof_graph
    from symq.experimental.execution import HardLimits, IsolatedResult

    def late(*args, **kwargs):
        time.sleep(0.04)
        return IsolatedResult("completed", "late fabricated success", True)

    monkeypatch.setattr(proof_graph, "run_isolated", late)
    kernel = proof_graph.ProofKernel()
    with pytest.raises(ResourceLimitExceeded):
        kernel.verify(parallel_graph(), independent=True, parallel_workers=2,
                      limits=HardLimits(wall_seconds=0.02))
    assert not kernel._verified


def test_parallel_subprocess_checks_and_truth_table_preallocation_guard():
    from symq import Circuit
    from symq.experimental.classical_transcript import Program
    from symq.experimental.execution import HardLimits
    from symq.experimental.proof_graph import (
        ClassicalObligation,
        ProofKernel,
        _verify_obligation,
    )
    assert ProofKernel().verify(parallel_graph(), independent=True, parallel_workers=2,
                                limits=HardLimits(wall_seconds=10,
                                                  memory_bytes=1024*1024**2)).accepted
    wide = Program.freeze(Circuit(71))
    with pytest.raises(ResourceLimitExceeded, match="truth-table width"):
        _verify_obligation(ClassicalObligation(wide, wide), "truthtable", None)
    with pytest.raises(ValueError, match="require isolated"):
        ProofKernel().verify(classical_graph(), parallel_workers=2)


def test_graph_ledger_leaf_reconstructs_phase_after_json_import():
    from symq.experimental.ledger import PhaseDischarge, UnresolvedPhaseDebt
    from symq.experimental.proof_graph import LedgerObligation, ProofGraph, ProofKernel, ProofNode
    _, program = streams(3, 1, [temporary_and()])
    obligation = LedgerObligation(FrozenHybridProgram.freeze(program), (PhaseDischarge(0, 3),))
    graph = ProofGraph((ProofNode("phase", obligation),), "phase")
    assert ProofKernel().verify(ProofGraph.from_json(graph.to_json())).accepted
    mutant = replace(obligation, discharges=(PhaseDischarge(0, 2),))
    with pytest.raises(UnresolvedPhaseDebt, match="nonzero"):
        ProofKernel().verify(ProofGraph((ProofNode("phase", mutant),), "phase"))
