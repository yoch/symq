"""Research: counterexample-guided discovery of source-bound phase certificates.

A fixed monomial dictionary is learned by one GF(2) system with k-bit labels.
Dictionary inconsistency is NOT channel inequivalence. A same-signature pair
with different source deltas is a separate, concretely replayed obstruction.
Positive candidates must pass the unchanged nonlinear_phase_bits checker afresh.
"""
from __future__ import annotations

import math
import time
from itertools import combinations


class _Basis:
    """Incremental exact row echelon form with XOR provenance and multiple RHS."""

    def __init__(self, size, tick):
        self.size, self.tick = size, tick
        self.rows = {}

    def add(self, row, label, index):
        provenance = 1 << index
        while row:
            self.tick()
            pivot = (row & -row).bit_length() - 1
            if pivot not in self.rows:
                self.rows[pivot] = (row, label, provenance)
                return None
            old_row, old_label, old_provenance = self.rows[pivot]
            row, label = row ^ old_row, label ^ old_label
            provenance ^= old_provenance
        return (provenance, label) if label else (0, 0)

    def solution(self):
        values = [0] * self.size
        for pivot, (row, label, _origin) in sorted(self.rows.items(), reverse=True):
            todo = row & ~(1 << pivot)
            while todo:
                self.tick()
                bit = (todo & -todo).bit_length() - 1
                label ^= values[bit]
                todo &= todo - 1
            values[pivot] = label
        return values


def _features(signature, dictionary):
    return sum((int(mask & signature == mask) << i) for i, mask in enumerate(dictionary))


def _evaluate(coefficients, feature_row):
    value = 0
    while feature_row:
        i = (feature_row & -feature_row).bit_length() - 1
        value ^= coefficients[i]
        feature_row &= feature_row - 1
    return value


def _dictionary(value, width, degree, cap, guard):
    from symq.labs.anchored_kraus import Limit

    if value is None:
        degree = min(degree, width)
        count = sum(math.comb(width, j) for j in range(degree + 1))
        if count > cap:
            raise Limit('monomial dictionary size')
        masks = []
        for j in range(degree + 1):
            for positions in combinations(range(width), j):
                guard.check_time()
                masks.append(sum(1 << i for i in positions))
        return tuple(sorted(masks))
    if type(value) is not tuple or not value:
        raise ValueError('dictionary must be a nonempty immutable tuple')
    if len(value) > cap:
        raise Limit('monomial dictionary size')
    previous = -1
    for mask in value:
        guard.check_time()
        if type(mask) is not int or mask <= previous or mask.bit_length() > width:
            raise ValueError('dictionary masks must be exact, sorted, distinct and in range')
        previous = mask
    return tuple(value)


def _prepare(core, left, right, dephaser, support, guard):
    work, limits = core._Work(guard), core._limits(None)
    a = core._freeze_dyadic(left, limits, work)
    b = core._freeze_dyadic(right, limits, work)
    d = core._freeze_dephaser(dephaser, limits, work)
    if a.width != b.width or a.width != d[0]:
        raise ValueError('source and dephaser widths differ')
    domain = core._freeze_support(support, a.width, work)
    initial = core._inputs(domain)
    restored, signature = core._dephasing_semantics(d, initial, work)
    k = max(a.k, b.k)
    identity = {'left': core._source_document(a), 'right': core._source_document(b),
                'dephaser': [d[0], d[1], [[op.kind, list(op.qubits), op.outcome] for op in d[2]]],
                'support': [domain.width, domain.offset, list(domain.columns)]}
    result = {'source_sha256': core._hash(identity), 'k': k,
              'signature_width': len(signature), 'parameter_dimension': len(domain.columns)}
    if restored != initial + [core._ZERO] * d[1]:
        result.update(status='not_proved', obligation='dephaser_restoration')
        return None, result
    out_a, pa = core._dyadic_semantics(a, initial, k, work, True)
    out_b, pb = core._dyadic_semantics(b, initial, k, work, True)
    for wire, (x, y) in enumerate(zip(out_a, out_b)):
        if x != y:
            z = min(x ^ y, key=lambda m: (m.bit_count(), m))
            ambient = core._ambient(domain, z)
            if _run_dyadic(a, ambient, k, core, guard)[0] == _run_dyadic(b, ambient, k, core, guard)[0]:
                from symq.errors import InternalInconsistency

                raise InternalInconsistency('output mismatch failed literal replay')
            result.update(status='different', obligation='outputs',
                          witness={'input': ambient, 'wire': wire})
            return None, result
    delta, modulus = dict(pa), 1 << k
    for predicate, coefficient in pb.items():
        value = (delta.get(predicate, 0) - coefficient) % modulus
        if value:
            delta[predicate] = value
        else:
            delta.pop(predicate, None)
        work.check(sum(map(len, delta)))
    return (a, b, d, domain, signature, delta, k), result


def _run_dyadic(source, assignment, k, core, guard):
    state, phase = assignment, 0
    for gate in source.gates:
        guard.check_time()
        controls = gate.wires[:-1] if gate.name in core._PERMUTATIONS else gate.wires
        if all(state >> q & 1 for q in controls):
            if gate.name in core._PERMUTATIONS:
                state ^= 1 << gate.wires[-1]
            else:
                phase += core._exponent(gate, k)
    return state, phase % (1 << k)


def _sample(problem, z, core, guard):
    """Literal source execution, independent of polynomial/DAG evaluation."""
    a, b, d, domain, _signature, _delta, k = problem
    if type(z) is not int or not 0 <= z < 1 << len(domain.columns):
        from symq.errors import InternalInconsistency

        raise InternalInconsistency('counterexample parameter outside support')
    ambient = core._ambient(domain, z)
    state, events = ambient, []
    for op in d[2]:
        guard.check_time()
        if op.kind == 'mcx':
            if all(state >> q & 1 for q in op.qubits[:-1]):
                state ^= 1 << op.qubits[-1]
        elif op.kind == 'hmr':
            events.append(state >> op.qubits[0] & 1)
            state &= ~(1 << op.qubits[0])
        elif op.kind == 'mcz_if':
            events[op.outcome] ^= int(all(state >> q & 1 for q in op.qubits))
        elif op.kind != 'mcz':
            from symq.errors import InternalInconsistency

            raise InternalInconsistency('unexpected frozen dephaser operation')
    if state != ambient:
        from symq.errors import InternalInconsistency

        raise InternalInconsistency('dephaser restoration failed literal replay')
    oa, pa = _run_dyadic(a, ambient, k, core, guard)
    ob, pb = _run_dyadic(b, ambient, k, core, guard)
    if oa != ob:
        from symq.errors import InternalInconsistency

        raise InternalInconsistency('proved output equality failed literal replay')
    return {'parameter': z, 'input': ambient,
            'signature': sum(v << i for i, v in enumerate(events)), 'delta': (pa - pb) % (1 << k)}


def _fresh_check(problem, certificate, checker, guard, max_nodes, max_clauses):
    from symq.labs.dyadic_phase import DyadicPhaseProgram
    from symq.phase import PhaseProgram

    a, b, d, domain, _sig, _delta, _k = problem
    left = DyadicPhaseProgram(a.width, list(a.gates), a.k)
    right = DyadicPhaseProgram(b.width, list(b.gates), b.k)
    dephaser = PhaseProgram(d[0], d[1], list(d[2]))
    guard.check_time()
    return checker.check_nonlinear_phase(
        left, right, dephaser, certificate, support=domain,
        budget=guard.inherited_budget(), max_graph_nodes=max_nodes, max_clauses=max_clauses)


def discover_phase_certificate(left, right, dephaser, *, support=None, dictionary=None,
                               max_degree=2, max_features=256, max_rounds=257,
                               budget=None, max_graph_nodes=100000, max_clauses=500000):
    """CEGIS with exact multi-output interpolation; no enumeration of input states.

    proved requires fresh source checking; dictionary_exhausted has a finite GF(2)
    obstruction for that dictionary only. different needs a literal source/output
    witness or equal-signature pair with distinct deltas. Limits are inconclusive.
    This labs prototype is outside the audit scope of PRs #159--#162.
    """
    from symq.errors import InternalInconsistency, ResourceLimitExceeded, SatUnavailable
    from symq.labs import affine_phase as core
    from symq.labs import nonlinear_phase_bits as checker
    from symq.labs.anchored_kraus import Limit
    from symq.labs.kraus_graph import Graph
    from symq.resources import Budget, intersect_budgets

    for name, value in (('max_features', max_features), ('max_rounds', max_rounds),
                        ('max_graph_nodes', max_graph_nodes), ('max_clauses', max_clauses)):
        if type(value) is not int or value < 1:
            raise ValueError(f'{name} must be a positive plain integer')
    if max_features > 4096 or max_rounds > 4097:
        raise ValueError('research caps are 4096 features and 4097 rounds')
    if type(max_degree) is not int or not 0 <= max_degree <= 256:
        raise ValueError('max_degree must be an integer in 0..256')
    first = core._guard(budget)
    guard = core._guard(intersect_budgets(Budget(max_terms=100000, max_seconds=10),
                                         Budget(first.budget.max_terms, absolute_deadline=first.deadline)))
    started = time.perf_counter()
    graph = Graph(guard, max_graph_nodes, max_clauses)
    result = {'status': 'inconclusive', 'obligation': None, 'certificate': None,
              'witness': None, 'obstruction': None, 'fresh_verified': False,
              'portable_certificate': False, 'controlled_use_authorized': False,
              'rounds': 0, 'sample_count': 0, 'rank': 0}
    try:
        problem, identity = _prepare(core, left, right, dephaser, support, guard)
        result.update(identity)
        if problem is not None:
            _a, _b, _d, domain, signature, delta, k = problem
            masks = _dictionary(dictionary, len(signature), max_degree, max_features, guard)
            result.update(dictionary=list(masks), dictionary_sha256=core._hash(masks),
                          feature_count=len(masks), refinement_rank_bound=len(masks))
            inputs = [graph.var(i) for i in range(len(domain.columns))]
            h = [checker._bool(p, inputs, graph) for p in signature]
            actual = checker._phase_bits(delta, inputs, k, graph)
            features = [checker._bool((mask,), h, graph) for mask in masks]
            basis, samples, seen = _Basis(len(masks), guard.check_time), [], {}
            for iteration in range(max_rounds):
                guard.check_time()
                result['rounds'] = iteration + 1
                coefficients = basis.solution()
                candidate = tuple(tuple(mask for mask, coefficient in zip(masks, coefficients)
                                        if coefficient >> j & 1) for j in range(k))
                violation = graph.zero
                for j in range(k):
                    predicted = graph.zero
                    for feature, coefficient in zip(features, coefficients):
                        if coefficient >> j & 1:
                            predicted = graph.xor(predicted, feature)
                    bad = graph.xor(actual[j], predicted)
                    violation = -graph.mul(-violation, -bad)
                z = graph.witness(violation)
                if z is None:
                    graph.close()
                    before = time.perf_counter()
                    fresh = _fresh_check(problem, candidate, checker, guard, max_graph_nodes, max_clauses)
                    result['fresh_check_seconds'] = time.perf_counter() - before
                    if fresh['status'] in ('inconclusive', 'unsupported'):
                        result.update(status=fresh['status'], obligation='fresh_check',
                                      reason=fresh.get('reason', fresh['status']))
                        break
                    if fresh['status'] != 'proved' or fresh.get('source_sha256') != result['source_sha256']:
                        raise InternalInconsistency('discovered candidate failed the fresh source checker')
                    result.update(status='proved', certificate=[list(p) for p in candidate],
                                  certificate_sha256=fresh['certificate_sha256'], fresh_verified=True)
                    break
                sample = _sample(problem, z, core, guard)
                observed_h = sum(int(graph.evaluate(bit, z)) << i for i, bit in enumerate(h))
                observed_delta = sum(int(graph.evaluate(bit, z)) << i for i, bit in enumerate(actual))
                if sample['signature'] != observed_h or sample['delta'] != observed_delta:
                    raise InternalInconsistency('source and graph disagree on counterexample')
                row = _features(sample['signature'], masks)
                if _evaluate(coefficients, row) == sample['delta']:
                    raise InternalInconsistency('counterexample does not refute the candidate')
                previous = seen.get(sample['signature'])
                if previous is not None and previous['delta'] != sample['delta']:
                    again = _sample(problem, previous['parameter'], core, guard)
                    if again != previous:
                        raise InternalInconsistency('collision witness is not reproducible')
                    result.update(status='different', obligation='signature_collision',
                                  witness={'left': previous, 'right': sample})
                    break
                seen[sample['signature']] = sample
                index = len(samples)
                samples.append(sample)
                obstruction = basis.add(row, sample['delta'], index)
                result.update(sample_count=len(samples), rank=len(basis.rows))
                guard.check_terms(sum(r.bit_count() + p.bit_count() for r, _v, p in basis.rows.values())
                                  + len(samples) * 4 + len(masks))
                if obstruction is not None:
                    selected, _expected_label = obstruction
                    if not selected:
                        raise InternalInconsistency('refinement neither increases rank nor contradicts')
                    subset = [s for i, s in enumerate(samples) if selected >> i & 1]
                    row_xor, label_xor = 0, 0
                    for sample_again in subset:
                        verified = _sample(problem, sample_again['parameter'], core, guard)
                        if verified != sample_again:
                            raise InternalInconsistency('obstruction contains a stale sample')
                        row_xor ^= _features(verified['signature'], masks)
                        label_xor ^= verified['delta']
                    if row_xor or not label_xor:
                        raise InternalInconsistency('invalid finite dictionary obstruction')
                    result.update(status='dictionary_exhausted', obligation='specified_dictionary',
                                  obstruction={'samples': subset, 'xor_labels': label_xor})
                    break
            else:
                raise Limit('CEGIS round limit')
        graph.close()
        guard.check_time()
    except (Limit, ResourceLimitExceeded) as error:
        result.update(status='inconclusive', obligation='resources', certificate=None,
                      witness=None, obstruction=None, fresh_verified=False, reason=str(error))
    except SatUnavailable as error:
        result.update(status='unsupported', obligation='backend', certificate=None,
                      witness=None, obstruction=None, fresh_verified=False, reason=str(error))
    finally:
        graph.close()
    if result['status'] != 'proved':
        # A revoked or failed run must not keep any field of a positive answer.
        for key in ('certificate_sha256',):
            result.pop(key, None)
    result.update(graph.metrics(), seconds=time.perf_counter() - started)
    return result
