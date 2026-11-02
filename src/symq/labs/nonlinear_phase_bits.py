"""Source-bound sufficient certificates delta(x)=sum 2**j b_j(h(x)) mod 2**k.

Unlike predicatewise factoring, bit-sliced modular accumulation retains carries
and cancellation across all source phase predicates. Nonlinear h is permitted.
A bad supplied b_j is only a certificate failure, not channel inequivalence.
All outputs are retained; classical records are forgotten. No controlled use.
"""
from __future__ import annotations

import time

from symq.errors import InternalInconsistency, ResourceLimitExceeded, SatUnavailable
from symq.labs.anchored_kraus import Limit
from symq.labs.kraus_graph import Graph
from symq.resources import Budget, intersect_budgets


def _bool(poly, inputs, graph):
    value = graph.zero
    for mask in sorted(poly):
        value = graph.xor(value, graph.all(inputs[i] for i in range(len(inputs)) if mask >> i & 1))
    return value


def _phase_bits(phase, inputs, k, graph):
    """Exact ripple addition of c[p] modulo 2**k; no integer polynomial lift."""
    bits = [graph.zero] * k
    for predicate, coefficient in phase.items():
        p = _bool(predicate, inputs, graph)
        carry = graph.zero
        for j in range(k):
            a = bits[j]
            b = p if coefficient >> j & 1 else graph.zero
            parity = graph.xor(a, b)
            bits[j] = graph.xor(parity, carry)
            # The two carry terms cannot both be 1, so XOR equals OR.
            carry = graph.xor(graph.mul(a, b), graph.mul(parity, carry))
    return bits


def _certificate(value, k, signature_width, work):
    if type(value) is not tuple or len(value) != k:
        raise ValueError('one immutable Boolean ANF tuple per phase bit required')
    result = []
    work.check(sum(len(p) if type(p) is tuple else 1 for p in value))
    for poly in value:
        if type(poly) is not tuple:
            raise ValueError('bit polynomials must be tuples of sorted masks')
        previous = -1
        for mask in poly:
            work.check()
            if type(mask) is not int or mask <= previous or mask.bit_length() > signature_width:
                raise ValueError('masks must be exact, sorted, distinct and fit signature width')
            previous = mask
        result.append(tuple(poly))
    return tuple(result)


def _eval(poly, assignment):
    return sum(mask & assignment == mask for mask in poly) % 2


def _check(core, left, right, dephaser, bitplanes, support, guard, graph):
    work, limits = core._Work(guard), core._limits(None)
    a = core._freeze_dyadic(left, limits, work)
    b = core._freeze_dyadic(right, limits, work)
    source = core._freeze_dephaser(dephaser, limits, work)
    if a.width != b.width or a.width != source[0]:
        raise ValueError('program and dephaser widths differ')
    domain = core._freeze_support(support, a.width, work)
    k, dimension = max(a.k, b.k), len(domain.columns)
    initial = core._inputs(domain)
    restored, signature = core._dephasing_semantics(source, initial, work)
    certificate = _certificate(bitplanes, k, len(signature), work)
    identity = {'left': core._source_document(a), 'right': core._source_document(b),
                'dephaser': [source[0], source[1],
                             [[op.kind, list(op.qubits), op.outcome] for op in source[2]]],
                'support': [domain.width, domain.offset, list(domain.columns)]}
    result = {'status': 'not_proved', 'obligation': None, 'witness': None,
              'theorem': 'full_channels_after_source_dephaser',
              'delta_convention': 'left_minus_right', 'controlled_use_authorized': False,
              'source_sha256': core._hash(identity),
              'certificate_sha256': core._hash(certificate), 'k': k,
              'parameter_dimension': dimension, 'signature_width': len(signature),
              'portable_certificate': False}
    if restored != initial + [core._ZERO] * source[1]:
        result.update(obligation='dephaser_restoration')
        return result
    out_a, phase_a = core._dyadic_semantics(a, initial, k, work, True)
    out_b, phase_b = core._dyadic_semantics(b, initial, k, work, True)
    for i, (x, y) in enumerate(zip(out_a, out_b)):
        if x != y:
            z = min(x ^ y, key=lambda mask: (mask.bit_count(), mask))
            ambient = core._ambient(domain, z)
            if core._run(a, ambient, k)[0] == core._run(b, ambient, k)[0]:
                raise InternalInconsistency('output witness failed scalar replay')
            result.update(obligation='outputs', witness={'input': ambient, 'wire': i})
            return result
    delta, modulus = dict(phase_a), 1 << k
    for predicate, coefficient in phase_b.items():
        value = (delta.get(predicate, 0) - coefficient) % modulus
        if value:
            delta[predicate] = value
        else:
            delta.pop(predicate, None)
        work.check(sum(map(len, delta)))
    result.update(delta_sha256=core._hash(sorted((sorted(p), c) for p, c in delta.items())),
                  signature_sha256=core._hash([sorted(p) for p in signature]))
    inputs = [graph.var(i) for i in range(dimension)]
    h = [_bool(p, inputs, graph) for p in signature]
    actual = _phase_bits(delta, inputs, k, graph)
    for j, polynomial in enumerate(certificate):
        expected = _bool(polynomial, h, graph)
        z = graph.witness(graph.xor(actual[j], expected))
        if z is not None:
            ambient = core._ambient(domain, z)
            pa = core._run(a, ambient, k)[1]
            pb = core._run(b, ambient, k)[1]
            scalar_delta = (pa - pb) % modulus
            hv = sum(_eval(p, z) << i for i, p in enumerate(signature))
            claim = sum(_eval(p, hv) << i for i, p in enumerate(certificate))
            if (scalar_delta >> j & 1) == (claim >> j & 1):
                raise InternalInconsistency('phase-bit witness failed scalar source replay')
            result.update(obligation='candidate_phase_bit',
                          witness={'input': ambient, 'parameter': z, 'bit': j,
                                   'source_delta': scalar_delta, 'candidate_delta': claim})
            return result
    result.update(status='proved', checked_bits=k)
    return result


def check_nonlinear_phase(left, right, dephaser, bitplanes, *, support=None,
                          budget=None, max_graph_nodes=100000, max_clauses=500000):
    """Check a supplied aggregate signature certificate against real frozen sources.

    No witness discovery is claimed. Non-proof from a bad certificate is NOT an
    inequivalence verdict. Future two-copy discovery and independent proof logs
    are separate work. Existing exact source/support parsers remain the authority.
    """
    from symq.labs import affine_phase as core

    for cap in (max_graph_nodes, max_clauses):
        if type(cap) is not int or cap < 1:
            raise ValueError('positive exact graph/clauses caps required')
    # Preserve the original deadline, including any caller/session limit.
    initial_guard = core._guard(budget)
    guard = core._guard(intersect_budgets(
        Budget(max_terms=100000, max_seconds=10),
        Budget(initial_guard.budget.max_terms, absolute_deadline=initial_guard.deadline)))
    graph = Graph(guard, max_graph_nodes, max_clauses)
    started = time.perf_counter()
    result = {'status': 'inconclusive', 'obligation': None, 'witness': None,
              'portable_certificate': False}
    try:
        guard.check_time()
        result = _check(core, left, right, dephaser, bitplanes, support, guard, graph)
        graph.close()
        guard.check_time()
    except (Limit, ResourceLimitExceeded) as error:
        result.update(status='inconclusive', obligation='resources', witness=None, reason=str(error))
    except SatUnavailable as error:
        result.update(status='unsupported', obligation='backend', witness=None, reason=str(error))
    finally:
        graph.close()
    if result['status'] != 'proved':
        # A revoked or failed run must not keep any field of a positive answer.
        for key in ('checked_bits',):
            result.pop(key, None)
    result.update(graph.metrics(), seconds=time.perf_counter() - started)
    return result
