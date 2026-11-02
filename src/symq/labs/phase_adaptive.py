"""Research: obstruction-guided enlargement of source-bound phase dictionaries.

The fixed learner remains unchanged. Every added monomial breaks a replayed
left-kernel obstruction and increases evaluation rank; no degree layer is
materialized. A fresh source check, not the learner, authorizes each positive.
"""
from __future__ import annotations

import time


def _separator(signatures, tick):
    """Find a positive monomial with odd incidence on distinct Boolean words.

    An inclusion-maximal word isolates itself among the words. Greedy deletion
    preserves odd incidence. This is not minimum-degree or minimum-size search.
    """
    if type(signatures) is not tuple or not signatures:
        raise ValueError('a nonempty tuple of distinct signature integers is required')
    seen = set()
    for word in signatures:
        tick()
        if type(word) is not int or word < 0 or word in seen:
            raise ValueError('signature words must be distinct nonnegative plain integers')
        seen.add(word)
    mask = max(signatures, key=lambda x: (x.bit_count(), x))

    def odd(candidate):
        parity = 0
        for word in signatures:
            tick()
            parity ^= int(word & candidate == candidate)
        return parity == 1

    # Maximal popcount excludes strict supersets, so this always starts odd.
    if not odd(mask):
        raise RuntimeError('maximal-word separator invariant failed')
    changed = True
    while changed:
        changed = False
        todo = mask
        while todo:
            tick()
            bit = todo & -todo
            todo ^= bit
            trial = mask ^ bit
            if odd(trial):
                mask, changed = trial, True
                break
    return mask


def _complete(samples, masks, features, signature_dag, problem, core, checker,
              graph, guard, max_features, result):
    """Refit the SAME accumulated samples; add columns only on inconsistency."""
    from symq.errors import InternalInconsistency
    from symq.labs import phase_discovery as fixed
    from symq.labs.anchored_kraus import Limit

    pending = None
    while True:
        guard.check_time()
        basis = fixed._Basis(len(masks), guard.check_time)
        result['basis_rebuilds'] += 1
        failed = None
        for index, sample in enumerate(samples):
            row = fixed._features(sample['signature'], masks)
            obstruction = basis.add(row, sample['delta'], index)
            if pending is not None and index == pending[0]:
                if obstruction is not None or len(basis.rows) < pending[1]:
                    raise InternalInconsistency('added feature did not increase the obstructed prefix rank')
                result['growth'][pending[2]]['rank_after'] = len(basis.rows)
                pending = None
            if obstruction is not None and obstruction[1]:
                failed = index, obstruction
                break
        guard.check_terms(sum(r.bit_count() + p.bit_count() for r, _v, p in basis.rows.values())
                          + len(samples) * 4 + len(masks)
                          + sum(len(g['sample_indices']) for g in result['growth']))
        if failed is None:
            result['rank'] = len(basis.rows)
            return basis
        index, (combination, label) = failed
        chosen = [i for i in range(index + 1) if combination >> i & 1]
        row_xor = label_xor = 0
        signatures = []
        for i in chosen:
            sample = samples[i]
            again = fixed._sample(problem, sample['parameter'], core, guard)
            if again != sample:
                raise InternalInconsistency('stale sample in refinement obstruction')
            row_xor ^= fixed._features(again['signature'], masks)
            label_xor ^= again['delta']
            signatures.append(again['signature'])
        if row_xor or label_xor != label or not label_xor:
            raise InternalInconsistency('invalid left-kernel obstruction')
        if len(masks) >= max_features:
            raise Limit('adaptive feature limit')
        added = _separator(tuple(signatures), guard.check_time)
        if added in masks or sum((h & added) == added for h in signatures) % 2 != 1:
            raise InternalInconsistency('separator does not escape the current feature span')
        entry = {'sample_indices': chosen, 'signature_words': signatures,
                 'xor_labels': label_xor, 'added_mask': added,
                 'rank_before': len(basis.rows), 'rank_after': None}
        result['growth'].append(entry)
        pending = (index, len(basis.rows) + 1, len(result['growth']) - 1)
        masks.append(added)
        features.append(checker._bool((added,), signature_dag, graph))
        result['feature_count'] = len(masks)


def discover_adaptive_phase(left, right, dephaser, *, support=None,
                            initial_dictionary=None, initial_degree=1,
                            max_features=256, max_samples=1024, max_rounds=1025,
                            budget=None, max_graph_nodes=100000, max_clauses=500000):
    """Learn phase bitplanes with exact obstruction-guided feature generation.

    Feature exhaustion is inconclusive, NEVER inequivalence. Real differences
    require scalar-replayed output mismatch or a same-signature/different-delta
    pair. Every success is freshly checked on detached sources within one deadline.
    """
    from symq.errors import InternalInconsistency, ResourceLimitExceeded, SatUnavailable
    from symq.labs import affine_phase as core
    from symq.labs import nonlinear_phase_bits as checker
    from symq.labs import phase_discovery as fixed
    from symq.labs.anchored_kraus import Limit
    from symq.labs.kraus_graph import Graph
    from symq.resources import Budget, intersect_budgets

    for name, value, cap in (('max_features', max_features, 4096),
                             ('max_samples', max_samples, 4096),
                             ('max_rounds', max_rounds, 4097),
                             ('max_graph_nodes', max_graph_nodes, None),
                             ('max_clauses', max_clauses, None)):
        if type(value) is not int or value < 1 or (cap is not None and value > cap):
            raise ValueError(f'invalid positive plain integer for {name}')
    if type(initial_degree) is not int or not 0 <= initial_degree <= 256:
        raise ValueError('initial_degree must be in 0..256')
    first = core._guard(budget)
    guard = core._guard(intersect_budgets(Budget(max_terms=100000, max_seconds=10),
                                         Budget(first.budget.max_terms, absolute_deadline=first.deadline)))
    started = time.perf_counter()
    graph = Graph(guard, max_graph_nodes, max_clauses)
    result = {'status': 'inconclusive', 'obligation': None, 'certificate': None,
              'witness': None, 'fresh_verified': False, 'portable_certificate': False,
              'controlled_use_authorized': False, 'rounds': 0, 'rank': 0,
              'sample_count': 0, 'basis_rebuilds': 0, 'growth': [], 'samples': []}
    try:
        problem, identity = fixed._prepare(core, left, right, dephaser, support, guard)
        result.update(identity)
        if problem is not None:
            _a, _b, _d, domain, signature, delta, k = problem
            masks = list(fixed._dictionary(initial_dictionary, len(signature),
                                           initial_degree, max_features, guard))
            result.update(initial_dictionary=list(masks), feature_count=len(masks),
                          source_preparations=1)
            inputs = [graph.var(i) for i in range(len(domain.columns))]
            h = [checker._bool(p, inputs, graph) for p in signature]
            actual = checker._phase_bits(delta, inputs, k, graph)
            features = [checker._bool((mask,), h, graph) for mask in masks]
            samples, seen = [], {}
            basis = fixed._Basis(len(masks), guard.check_time)
            for iteration in range(max_rounds):
                guard.check_time()
                result['rounds'] = iteration + 1
                coefficients = basis.solution()
                candidate = tuple(tuple(sorted(mask for mask, value in zip(masks, coefficients)
                                                if value >> j & 1)) for j in range(k))
                violation = graph.zero
                for j in range(k):
                    predicted = graph.zero
                    for feature, value in zip(features, coefficients):
                        if value >> j & 1:
                            predicted = graph.xor(predicted, feature)
                    violation = -graph.mul(-violation, -graph.xor(actual[j], predicted))
                z = graph.witness(violation)
                if z is None:
                    graph.close()
                    before = time.perf_counter()
                    fresh = fixed._fresh_check(problem, candidate, checker, guard,
                                               max_graph_nodes, max_clauses)
                    result['fresh_check_seconds'] = time.perf_counter() - before
                    if fresh['status'] in ('inconclusive', 'unsupported'):
                        result.update(status=fresh['status'], obligation='fresh_check',
                                      reason=fresh.get('reason', fresh['status']))
                        break
                    if (fresh['status'] != 'proved'
                            or fresh.get('source_sha256') != result['source_sha256']
                            or fresh.get('certificate_sha256') != core._hash(candidate)):
                        raise InternalInconsistency('adaptive candidate failed fresh source-bound checking')
                    result.update(status='proved', certificate=[list(p) for p in candidate],
                                  certificate_sha256=fresh['certificate_sha256'], fresh_verified=True)
                    break
                sample = fixed._sample(problem, z, core, guard)
                actual_h = sum(int(graph.evaluate(bit, z)) << i for i, bit in enumerate(h))
                actual_delta = sum(int(graph.evaluate(bit, z)) << j for j, bit in enumerate(actual))
                if sample['signature'] != actual_h or sample['delta'] != actual_delta:
                    raise InternalInconsistency('adaptive graph and literal source disagree')
                if fixed._evaluate(coefficients, fixed._features(actual_h, masks)) == actual_delta:
                    raise InternalInconsistency('adaptive counterexample does not refute its candidate')
                previous = seen.get(actual_h)
                if previous is not None:
                    if previous['delta'] == sample['delta']:
                        raise InternalInconsistency('adaptive solver rediscovered an already fitted sample')
                    if fixed._sample(problem, previous['parameter'], core, guard) != previous:
                        raise InternalInconsistency('signature collision failed literal replay')
                    result.update(status='different', obligation='signature_collision',
                                  witness={'left': previous, 'right': sample})
                    break
                if len(samples) >= max_samples:
                    raise Limit('adaptive sample limit')
                seen[actual_h] = sample
                samples.append(sample)
                result.update(samples=list(samples), sample_count=len(samples))
                basis = _complete(samples, masks, features, h, problem, core, checker,
                                  graph, guard, max_features, result)
            else:
                raise Limit('adaptive CEGIS round limit')
            result.update(dictionary=sorted(masks), dictionary_sha256=core._hash(tuple(sorted(masks))),
                          max_feature_degree=max(mask.bit_count() for mask in masks),
                          added_features=len(result['growth']))
        graph.close()
        guard.check_time()
    except (Limit, ResourceLimitExceeded) as error:
        result.update(status='inconclusive', obligation='resources', certificate=None,
                      witness=None, fresh_verified=False, reason=str(error))
    except SatUnavailable as error:
        result.update(status='unsupported', obligation='backend', certificate=None,
                      witness=None, fresh_verified=False, reason=str(error))
    finally:
        graph.close()
    result.update(graph.metrics(), seconds=time.perf_counter() - started)
    return result
