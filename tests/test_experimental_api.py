"""Coherence-sensitive integration checks for the installed experimental API."""
from dataclasses import FrozenInstanceError, replace

import pytest

from symq.circuit import Circuit
from symq.experimental import (
    AffineDomain,
    PredicateDomain,
    PreparedDomain,
    VerificationContract,
    inspect,
    prepare_reference,
    replay,
    verify,
)
from symq.phase import PhaseProgram
from symq.resources import Budget
from symq.sat.assumptions import Const, Eq, Var


def test_relative_phase_requires_coherences_and_replays_pinned_sources():
    left, right = PhaseProgram(1), PhaseProgram(1).z(0)
    contract = VerificationContract()
    result = verify(left, right, contract)
    assert result.outcome == 'different' and result.witness[0] != result.witness[1]
    assert replay(result, left, right, contract).proof_kind == 'witness_replayed'
    with pytest.raises(ValueError, match='hash'):
        replay(result, left, PhaseProgram(1), contract)
    with pytest.raises(ValueError, match='replay'):
        replay(replace(result, witness=(0, 0)), left, right, contract)
    with pytest.raises(FrozenInstanceError):
        result.reason = 'changed'


def test_reduced_trace_keeps_garbage_dephasing_and_accepts_different_ancillas():
    left = PhaseProgram(1, 1)
    copy = PhaseProgram(1, 1).cx(0, 1)
    contract = VerificationContract('reduced_channel', 'zdd', left_outputs=(0,), right_outputs=(0,))
    result = verify(left, copy, contract)
    assert result.outcome == 'different' and result.witness[0] != result.witness[1]
    assert replay(result, left, copy, contract).witness_checked
    wider = PhaseProgram(1, 3).x(2)
    assert verify(left, wider, contract).equivalent
    # Both retain the same data map; discarded labels may differ by a bijection.
    copy_flipped = PhaseProgram(1, 2).cx(0, 1).x(1).x(2)
    assert verify(copy, copy_flipped, contract).equivalent


def test_reduced_output_mapping_and_empty_observation():
    left, right = PhaseProgram(2), PhaseProgram(2).cx(0, 1).cx(1, 0).cx(0, 1)
    contract = VerificationContract('reduced_channel', left_outputs=(0, 1), right_outputs=(1, 0))
    assert verify(left, right, contract).equivalent
    nothing = VerificationContract('reduced_channel', left_outputs=(), right_outputs=())
    assert verify(left, right, nothing).equivalent


def test_symbolic_domains_are_coherent_and_empty_predicate_fails():
    left, right = PhaseProgram(2), PhaseProgram(2).cz(0, 1)
    assert verify(left, right).outcome == 'different'
    affine = AffineDomain(2, 0, (1,))
    assert verify(left, right, domain=affine).equivalent
    diagonal = AffineDomain(2, 0, (3,))
    assert verify(left, right, domain=diagonal).outcome == 'different'
    predicate = PredicateDomain(2, Eq(Var('x.0'), Var('x.1')))
    assert verify(left, right, domain=predicate).outcome == 'different'
    prepared = PreparedDomain(Circuit(2).cx(0, 1), (0,))
    assert verify(left, right, domain=prepared).outcome == 'different'
    assert verify(left, right, domain=PredicateDomain(2, Const(False))).outcome == 'precondition_failed'


def test_outcome_coefficients_reduce_mod_constants_and_dependencies():
    left = PhaseProgram(1)
    left.hmr(0)
    right = PhaseProgram(1).x(0)
    right.hmr(0)
    assert verify(left, right).equivalent
    a = PhaseProgram(1, 1).cx(0, 1)
    a.hmr(1)
    b = PhaseProgram(1, 1).cx(0, 1)
    b.hmr(1)
    b.cx(0, 1)
    b.hmr(1)
    result = verify(a, b)
    assert result.equivalent
    stats = dict(result.statistics)
    assert stats['coefficients_after'] < stats['coefficients_before']
    assert stats['conversions'] == 0


def test_prepared_cache_owns_snapshot_and_renews_each_budget():
    reference = PhaseProgram(2)
    with prepare_reference(reference, max_cache_entries=1) as prepared:
        reference.x(0)
        candidate = PhaseProgram(2)
        assert prepared.compare(candidate).equivalent
        assert dict(prepared.compare(candidate).statistics)['cache_hit'] == 1
        assert prepared.compare(candidate, budget=Budget(max_seconds=1e-12)).outcome == 'inconclusive'
        assert prepared.compare(candidate, budget=Budget(max_seconds=2)).equivalent
        changed = PhaseProgram(2).z(0)
        assert prepared.compare(changed).outcome == 'different'
        prepared.clear_cache()
        assert prepared.compare(candidate).equivalent
    with pytest.raises(RuntimeError, match='closed'):
        prepared.compare(candidate)


def test_explicit_capabilities_no_backend_fallback_or_record_authentication():
    assert inspect(PhaseProgram(1), engine='zdd').supported
    with pytest.raises(ValueError):
        verify(PhaseProgram(1), PhaseProgram(1), engine='zdd', backend='zdd')
    result = verify(PhaseProgram(1), PhaseProgram(1), budget=Budget(max_seconds=1e-12))
    assert result.outcome == 'inconclusive' and not result.certified
    with pytest.raises(ValueError, match='concrete difference'):
        replay(verify(PhaseProgram(1), PhaseProgram(1)), PhaseProgram(1), PhaseProgram(1),
               VerificationContract())


def test_hybrid_channel_instrument_and_immutable_ir_capabilities():
    from symq.experimental.hybrid import HybridProgram, freeze_hybrid
    left = HybridProgram(1).measure_z(0, 'b0')
    right = HybridProgram(1).measure_z(0, 'b0').store('b0', 0)
    channel = VerificationContract('full_channel', 'hybrid-exact')
    instrument = VerificationContract('instrument', 'hybrid-exact', observed_slots=('b0',))
    assert verify(left, right, channel).equivalent
    result = verify(left, right, instrument)
    assert result.outcome == 'different' and replay(result, left, right, instrument).witness_checked
    assert inspect(freeze_hybrid(left), contract=channel).supported
    reduced = VerificationContract('reduced_channel', 'hybrid-exact',
                                   left_outputs=(0,), right_outputs=(0,))
    assert verify(HybridProgram(1), HybridProgram(1, 1), reduced).equivalent


def test_reduction_reconstruction_relations_hold_in_both_parameter_halves():
    from symq.backends import make_algebra
    from symq.experimental.channel import _reduction
    from symq.resources import Guard
    algebra = make_algebra('zdd', 4)
    x0, x1, y0, y1 = (algebra.variable(i) for i in range(4))
    xs = (x0, algebra.xor(x0, algebra.one()), x1, algebra.xor(x0, x1), algebra.one())
    ys = (y0, algebra.xor(y0, algebra.one()), y1, algebra.xor(y0, y1), algebra.one())
    reduced = _reduction(algebra, xs, ys, Guard())
    assert reduced.record.rank == 2
    for half, originals in enumerate((xs, ys)):
        for i, (combination, constant) in enumerate(zip(
                reduced.record.basis_combinations, reduced.record.basis_constants)):
            value = algebra.one() if constant else algebra.zero()
            for j, root in enumerate(originals):
                if combination >> j & 1:
                    value = algebra.xor(value, root)
            assert algebra.equal(value, reduced.basis[i][half])
        for i, root in enumerate(originals):
            value = algebra.one() if reduced.constants[i] else algebra.zero()
            for j, pair in enumerate(reduced.basis):
                if reduced.reconstruction[i] >> j & 1:
                    value = algebra.xor(value, pair[half])
            assert algebra.equal(value, root)


def test_diagonal_failure_does_not_construct_y_halves(monkeypatch):
    from symq.experimental import channel
    def forbidden(*args):
        raise AssertionError('unnecessary y construction')
    monkeypatch.setattr(channel, '_other_half', forbidden)
    assert verify(PhaseProgram(2), PhaseProgram(2).x(0)).outcome == 'different'


def test_explicit_blocks_and_native_prepared_budget_rebinding():
    from symq.backends import BACKENDS
    if 'zdd-native' not in BACKENDS:
        pytest.skip('optional native backend unavailable')
    left, right = PhaseProgram(36), PhaseProgram(36)
    for first in range(0, 36, 9):
        for q in range(first, first + 8):
            left.cx(q, q + 1)
        for q in reversed(range(first, first + 8)):
            left.cx(q, q + 1)
    report = inspect(left, right, engine='zdd-native-blocks')
    assert report.supported and len(report.common_blocks) == 4
    assert report.widest_data_component == 9 and not report.monolithic_supported
    contract = VerificationContract(backend='zdd-native-blocks')
    assert verify(left, right, contract, theorem='full_channel', engine='zdd-native-blocks').equivalent
    assert verify(left, right, engine='zdd-native').outcome == 'unsupported'
    with prepare_reference(PhaseProgram(3), engine='zdd-native', max_cache_entries=1) as prepared:
        assert prepared.compare(PhaseProgram(3), budget=Budget(max_seconds=2)).equivalent
        assert prepared.compare(PhaseProgram(3).z(0), budget=Budget(max_seconds=2)).outcome == 'different'
        prepared.clear_cache(budget=Budget(max_seconds=2))
        assert prepared.compare(PhaseProgram(3), budget=Budget(max_seconds=2)).equivalent


def test_random_reduced_kernel_matches_independent_density_oracle():
    import random

    from symq.experimental.api import _project
    from symq.experimental.hybrid import HOp, HybridProgram, coherence_image
    def hybrid(program):
        ops = []
        for op in program.ops:
            if op.kind == 'hmr':
                ops.append(HOp('hmr', op.qubits, slot=f'b{op.outcome}'))
            elif op.kind == 'mcx':
                ops.append(HOp('x' if len(op.qubits) == 1 else 'mcx', op.qubits))
            else:
                name = {1: 'z', 2: 'cz', 3: 'ccz'}[len(op.qubits)]
                condition = f'b{op.outcome}' if op.kind == 'mcz_if' else None
                ops.append(HOp(name, op.qubits, condition=condition))
        return HybridProgram(program.data, program.ancillas, ops)
    for seed in range(24):
        rng = random.Random(seed)
        programs = []
        for _ in range(2):
            p = PhaseProgram(2, rng.randrange(3))
            for _ in range(7):
                q = rng.randrange(p.width)
                choice = rng.randrange(5)
                if choice == 0:
                    p.x(q)
                elif choice == 1:
                    a, b = rng.sample(range(p.width), 2)
                    p.cx(a, b)
                elif choice == 2:
                    p.z(q)
                elif choice == 3:
                    p.hmr(q)
                elif p.measurements:
                    p.z_if(rng.randrange(p.measurements), q)
            programs.append(p)
        a, b = programs
        left, right = hybrid(a), hybrid(b)
        contract = VerificationContract('reduced_channel', left_outputs=(0,), right_outputs=(0,))
        expected = all(_project(coherence_image(left, x, y), (0,), left.width) ==
                       _project(coherence_image(right, x, y), (0,), right.width)
                       for x in range(4) for y in range(4))
        result = verify(a, b, contract)
        assert result.equivalent == expected
        if not expected:
            assert replay(result, a, b, contract).witness_checked


def test_replay_rejects_relabelled_theorem_metadata():
    left, right = PhaseProgram(1), PhaseProgram(1).z(0)
    contract = VerificationContract()
    result = verify(left, right, contract)
    with pytest.raises(ValueError, match='metadata'):
        replay(replace(result, theorem='reduced_channel'), left, right, contract)
