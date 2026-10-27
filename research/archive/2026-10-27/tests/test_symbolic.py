"""Proof-obligation regression tests for the exact experimental Boolean/phase backends.

These do NOT prove quantum correctness outside supported operations and semantics.
"""
from __future__ import annotations

import random
from math import comb
import pytest

from src.corpus import parse_qasm_strict, read_corpus
from src.optimized import (
    DegreeOverflow, FastSetState, MixedState, ResourceLimit,
    Ring2, SetState, TruthState, set_mul,
)
from src.zdd import AutoZDDState, ZDD, ZDDState


def test_source_manifest_complete():
    all_ = list(read_corpus())
    assert len(all_) == 11
    assert len({x['name'] for x in all_}) == len(all_)
    assert all(len(x['sha']) == 40 for x in all_)
    for x in all_:
        assert x['ops']
        assert all(op in ('X', 'CX', 'CCX', 'MCX') for op, _, _, _ in x['ops'])


def test_parse_qasm_valid_and_reject_unsupported():
    text = '''OPENQASM 3.0;
include "stdgates.inc";
qubit[6] q;
x q[0];
cx q[0], q[1];
ccx q[0], q[1], q[2];
ctrl(3) @ x q[0], q[1], q[2], q[3];'''
    assert parse_qasm_strict(text) == (6, [
        ('X', (0,), None, None), ('CX', (0,1), None, None),
        ('CCX', (0,1,2), None, None), ('MCX', (0,1,2,3), None, None)])
    with pytest.raises(ValueError, match='unsupported'):
        parse_qasm_strict('OPENQASM 3.0;\nqubit[2] q;\nh q[0];')
    with pytest.raises(ValueError, match='alias'):
        parse_qasm_strict('OPENQASM 3.0;\nqubit[2] q;\ncx q[0], q[0];')


def test_ring2_exhaustive_affine_n3():
    ring = Ring2(3)
    assert ring.length == 1+3+comb(3,2)
    for a in range(1 << 4):
        for b in range(1 << 4):
            x, y = a, b
            aa={ring.masks[i] for i in range(4) if (x>>i)&1}
            bb={ring.masks[i] for i in range(4) if (y>>i)&1}
            expected = set_mul(aa,bb)
            assert ring.sparse(ring.mul(x,y)) == expected
    with pytest.raises(DegreeOverflow):
        ring.mul(ring.packed({(1<<0)|(1<<1)}),ring.var(2))


def test_zdd_ring_algebra_exact_n5():
    rng=random.Random(44)
    zdd=ZDD(5)
    for _ in range(80):
        a={mask for mask in range(1<<5) if rng.random()<.16}
        b={mask for mask in range(1<<5) if rng.random()<.16}
        c={mask for mask in range(1<<5) if rng.random()<.16}
        aa,bb,cc=[zdd.from_terms(s) for s in (a,b,c)]
        assert zdd.as_set(aa) == a
        assert zdd.as_set(zdd.xor(aa,bb)) == a.symmetric_difference(b)
        assert zdd.as_set(zdd.mul(aa,bb)) == set_mul(a,b)
        assert zdd.mul(aa,aa) == aa  # Boolean quotient: p^2 = p
        assert zdd.mul(aa,zdd.xor(bb,cc)) == zdd.xor(zdd.mul(aa,bb),zdd.mul(aa,cc))


def test_real_source_full_inputs_differential():
    # These are functions for all 2^n inputs, symbolically represented.
    for item in read_corpus():
        instances=[]
        for cl in (SetState, FastSetState, MixedState, ZDDState, AutoZDDState):
            instance=cl(item['n'], tuple(range(item['n'])))
            instance.run(item['ops'])
            instances.append(instance)
        gold=instances[0].digest()
        for instance in instances[1:]:
            assert instance.digest() == gold, (item['name'],instance.__class__.__name__)


def test_truth_independent_all_assignments_on_restricted_domains():
    # ~1000 assignments per case; every gate is checked by two independent models.
    for item in read_corpus():
        free = min(item['n'],10)
        ids=tuple(range(free))
        truth=TruthState(free,ids).run(item['ops'])
        exact=FastSetState(free,ids).run(item['ops'])
        assert truth.compare(exact,all_bits=10)


def test_inverse_reversible_gates_on_real_corpus():
    for item in read_corpus():
        ids=tuple(range(min(item['n'],7)))
        circuit=item['ops']+list(reversed(item['ops']))
        for cl in (FastSetState,AutoZDDState,ZDDState):
            result=cl(len(ids),ids).run(circuit)
            target=FastSetState(len(ids),ids).digest()
            assert result.digest() == target


def test_phase_and_HMR_identity_and_fault_detection():
    # HMR contributes measurement-bit * measured Boolean value.
    ops=[('CX',(0,2),None,None),('CCX',(0,1,3),None,None),
         ('HMR',(3,),None,'h0'),('CZ',(0,1),'h0',None),
         ('CZ',(0,1),'h0',None),('HMR',(2,),None,'h1'),
         ('CZ',(0,1),None,None),('CZ',(0,1),None,None)]
    ref=FastSetState(2,(0,1));ref.new_classical_input('m0');ref.run(ops)
    for cl in (SetState,ZDDState,AutoZDDState,MixedState):
        x=cl(2,(0,1));x.new_classical_input('m0');x.run(ops)
        assert x.digest()==ref.digest()
    t=TruthState(2,(0,1));t.new_classical_input('m0');t.run(ops)
    assert t.compare(ref,all_bits=2)
    # Missing second HMR leaves a symbolic phase discrepancy and unclean wire.
    wrong=FastSetState(2,(0,1));wrong.new_classical_input('m0');wrong.run(ops[:5]+ops[6:])
    assert wrong.digest()!=ref.digest()
    assert ref.hmrs==2


def test_fail_closed_unsupported_and_degree_overflow():
    for cl in (FastSetState,ZDDState,AutoZDDState,MixedState,TruthState):
        e=cl(4,tuple(range(4)))
        with pytest.raises(ValueError):e.step('H',(0,))
        with pytest.raises(ValueError):e.step('CX',(0,0))
        with pytest.raises(ValueError):e.step('CCX',(0,1,2),condition='m')
        with pytest.raises(ValueError):e.step('CZ',(0,1),condition='missing')
    full=[('CCX',(0,1,4),None,None),('CCX',(2,4,5),None,None)]
    with pytest.raises(DegreeOverflow):
        MixedState(3,(0,1,2),mode='packed').run(full)
    x=MixedState(3,(0,1,2),mode='adaptive').run(full)
    y=FastSetState(3,(0,1,2)).run(full)
    assert x.digest()==y.digest()


def test_switch_threshold_selection():
    ops=[('CCX',(0,1,3),None,None),('CX',(3,4),None,None),
         ('CCX',(0,2,3),None,None)]
    x=AutoZDDState(3,(0,1,2),threshold=1)
    x.run(ops)
    assert x.switch_op == 1
    assert x.digest()==FastSetState(3,(0,1,2)).run(ops).digest()
    y=AutoZDDState(3,(0,1,2),threshold=1000).run(ops)
    assert y.switch_op is None


def test_mutations_detected_on_real_qcec():
    item=next(x for x in read_corpus() if x['name']=='mod5adder_306')
    ops=item['ops']; n=item['n'];ids=tuple(range(n))
    orig=FastSetState(n,ids).run(ops).digest()
    # Deleting a nontrivial CCX changes its truth function.
    for k,op in enumerate(ops):
        if op[0]=='CCX':
            alt=FastSetState(n,ids).run(ops[:k]+ops[k+1:]).digest()
            assert alt!=orig
            break
    else:raise AssertionError('no CCX found')


def test_auto_zdd_recovers_from_sparse_cap_without_loss():
    ops=[('CX',(0,3),None,None),('CX',(2,3),None,None),('CCX',(1,3,4),None,None)]
    fast=FastSetState(3,(0,1,2)).run(ops)
    adaptive=AutoZDDState(3,(0,1,2),threshold=10**6,cap=1).run(ops)
    assert adaptive.switch_op==3
    assert adaptive.switch_reason=='sparse resource cap'
    assert adaptive.digest()==fast.digest()


def test_seeded_random_phase_and_measurement_differential():
    """Fuzz exact Boolean/phase semantics, including live HMR outcome conditions."""
    rng=random.Random(20261027)
    n=5
    for case in range(35):
        ops=[];outcomes=[]
        for i in range(35):
            op=rng.choice(('X','CX','CCX','MCX','Z','CZ','CCZ','HMR','CZ'))
            if op=='X':args=(rng.randrange(9),)
            elif op=='CX':args=tuple(rng.sample(range(9),2))
            elif op in ('CCX','CCZ'):args=tuple(rng.sample(range(9),3))
            elif op=='MCX':args=tuple(rng.sample(range(9),4))
            elif op=='Z':args=(rng.randrange(9),)
            elif op=='CZ':args=tuple(rng.sample(range(9),2))
            elif op=='HMR':args=(rng.randrange(5,9),)
            cond=rng.choice(outcomes+['m0']) if op in ('Z','CZ','CCZ') and rng.random()<0.38 else None
            bit=f'h{case}_{i}' if op=='HMR' else None
            if bit:outcomes.append(bit)
            ops.append((op,args,cond,bit))
        ref=FastSetState(n,tuple(range(n)));ref.new_classical_input('m0');ref.run(ops)
        truth=TruthState(n,tuple(range(n)));truth.new_classical_input('m0');truth.run(ops)
        assert truth.compare(ref,all_bits=n)
        for cl in (ZDDState,AutoZDDState,MixedState):
            s=cl(n,tuple(range(n)));s.new_classical_input('m0');s.run(ops)
            assert s.digest()==ref.digest(),(case,cl.__name__)
