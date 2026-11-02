"""Portable, solver-independent checking of source-bound factored phase proofs.

This closes the UNSAT trust gap, not the semantic-encoder/Python trust gap.
All output/restoration obligations and CNF bytes are rebuilt from actual sources.
Candidate generation and DRUP elaboration are NEVER proof authority. Existing
factored/bitplane APIs and their default solver behavior remain unchanged.
"""
from __future__ import annotations

import hashlib
import time

from symq.labs import lrat_rup as kernel

_KIND = 'symq_factored_phase_lrat_rup'
_THEOREM = 'full_channels_after_source_dephaser'
_ENCODER = 'factored-dag-cnf-v1'
_KEYS = {'kind', 'schema_version', 'theorem', 'encoder', 'source_sha256',
         'certificate_sha256', 'cnf_sha256', 'lrat_sha256', 'cnf', 'lrat'}


class _NotApplicable(Exception):
    pass


def _bounds(limits):
    bounds = kernel.Limits() if limits is None else limits
    if type(bounds) is not kernel.Limits:
        raise TypeError('exact proof Limits required')
    bounds.validate()
    return bounds


def _guard(budget, bounds):
    from symq.labs.phase_factored import _new_guard
    from symq.resources import Budget, intersect_budgets

    if budget is not None and type(budget) is not Budget:
        raise TypeError('Budget or None required')
    return _new_guard(intersect_budgets(Budget(max_seconds=bounds.max_seconds),
                                        budget or Budget()))


def _pin(value):
    if type(value) is not str or kernel._PIN.fullmatch(value) is None:
        raise ValueError('independently pinned lowercase SHA-256 required')


def _encode_graph(graph, root, guard, limits):
    """Local explicit Tseitin templates; no calls to Graph._clauses_for/solver."""
    from symq.errors import InternalInconsistency

    nodes = graph.nodes
    if nodes[:2] != [None, ('one',)]:
        raise InternalInconsistency('graph constant prefix changed')
    size = len(nodes) - 1
    if size > limits.max_variables:
        raise kernel.ProofLimit('CNF variable limit')
    if type(root) is not int or not 0 < abs(root) <= size:
        raise InternalInconsistency('invalid obligation root')
    clauses = [(1,)]
    terms = 2
    for identifier, node in enumerate(nodes[2:], 2):
        guard.check_time()
        if type(node) is not tuple or type(node[0]) is not str:
            raise InternalInconsistency('invalid graph node')
        if node[0] == 'var':
            if len(node) != 2 or type(node[1]) is not int or node[1] < 0:
                raise InternalInconsistency('invalid graph input')
            continue
        if node[0] not in ('and', 'xor') or len(node) != 3:
            raise InternalInconsistency('unsupported graph node')
        a, b = node[1:]
        if any(type(v) is not int or not 0 < abs(v) < identifier for v in (a, b)):
            raise InternalInconsistency('graph is not topologically ordered')
        if node[0] == 'and':
            new = [(-identifier, a), (-identifier, b), (identifier, -a, -b)]
        else:
            new = [(-a, -b, -identifier), (a, b, -identifier),
                   (a, -b, identifier), (-a, b, identifier)]
        clauses.extend(new)
        terms += sum(len(c) + 1 for c in new)
        guard.check_terms(terms)
        if len(clauses) + 1 > limits.max_clauses:
            raise kernel.ProofLimit('CNF clause limit')
    clauses.append((root,))  # Query assumptions are authenticated INPUT clauses.
    text = f'p cnf {size} {len(clauses)}\n'
    chunks = [text]
    count = len(text)
    for clause in clauses:
        guard.check_time()
        row = ' '.join(map(str, clause)) + ' 0\n'
        count += len(row)
        if count > limits.max_bytes:
            raise kernel.ProofLimit('CNF byte limit')
        chunks.append(row)
    guard.check_time()
    return ''.join(chunks)


def _obligation(left, right, dephaser, candidate, support, guard, limits, max_items):
    from symq.labs import affine_phase as core
    from symq.labs import nonlinear_phase_bits as bits
    from symq.labs import phase_discovery as fixed
    from symq.labs import phase_factored as factored
    from symq.labs.kraus_graph import Graph

    factored._caps(max_items)
    problem, identity = fixed._prepare(core, left, right, dephaser, support, guard)
    if problem is None:
        raise _NotApplicable(identity.get('obligation', 'source preparation'))
    _a, _b, _d, domain, signature, delta, k = problem
    candidate, _items = factored._freeze_certificate(candidate, len(signature), k, guard, max_items)
    graph = Graph(guard, limits.max_variables, limits.max_clauses)
    try:
        inputs = [graph.var(i) for i in range(len(domain.columns))]
        actual = bits._phase_bits(delta, inputs, k, graph)
        claimed = factored._compile(candidate, signature, inputs, k, bits, graph, guard)
        violation = graph.zero
        for a, b in zip(actual, claimed):
            violation = -graph.mul(-violation, -graph.xor(a, b))
        cnf = _encode_graph(graph, violation, guard, limits)
        identity = {'source_sha256': identity['source_sha256'],
                    'certificate_sha256': core._hash(candidate),
                    'cnf_sha256': hashlib.sha256(cnf.encode('ascii')).hexdigest(),
                    'theorem': _THEOREM, 'encoder': _ENCODER}
        guard.check_time()
        return problem, candidate, cnf, identity
    finally:
        graph.close()


def describe_factored_obligation(left, right, dephaser, candidate, *, support=None,
                                 budget=None, limits=None, max_items=100000):
    """Obtain independent source/candidate/CNF pins without invoking a SAT solver.

    'ready' means an obligation was encoded, NOT that it is true. Trust this only
    when the supplied source objects, candidate and support are trusted inputs.
    """
    from symq.errors import ResourceLimitExceeded
    from symq.labs.anchored_kraus import Limit

    bounds = _bounds(limits)
    guard = _guard(budget, bounds)
    result = {'status': 'inconclusive', 'proved': False}
    try:
        _p, _c, cnf, identity = _obligation(left, right, dephaser, candidate, support,
                                          guard, bounds, max_items)
        guard.check_time()
        result.update(status='ready', cnf=cnf, **identity)
        guard.check_time()
    except (Limit, ResourceLimitExceeded, kernel.ProofLimit) as error:
        result = {'status': 'inconclusive', 'proved': False, 'reason': str(error)}
    except _NotApplicable as error:
        result = {'status': 'not_proved', 'proved': False, 'reason': str(error)}
    return result


def check_factored_proof(left, right, dephaser, candidate, bundle, *,
                         expected_source_sha256, expected_certificate_sha256,
                         support=None, budget=None, limits=None, max_items=100000):
    """Re-extract trusted inputs and check the proof, with NO SAT/search call.

    Bundle metadata is untrusted. It must match freshly rebuilt source semantics,
    the complete candidate, and byte-identical CNF including the query unit. The
    independent LRAT kernel then checks the explicit inference trace. The semantic
    reduction, Boolean graph simplifications and Python remain in the trusted base.
    """
    from symq.errors import ResourceLimitExceeded
    from symq.labs.anchored_kraus import Limit

    bounds = _bounds(limits)
    guard = _guard(budget, bounds)
    started = time.perf_counter()
    result = {'status': 'invalid', 'independent_unsat_checked': False,
              'semantic_kernel_formally_verified': False}
    try:
        guard.check_time()
        _pin(expected_source_sha256)
        _pin(expected_certificate_sha256)
        if type(bundle) is not dict or set(bundle) != _KEYS:
            raise kernel.InvalidProof('closed proof bundle fields required')
        if type(bundle['schema_version']) is not int or bundle['schema_version'] != 1:
            raise kernel.InvalidProof('unsupported bundle schema')
        if any(type(bundle[key]) is not str for key in _KEYS - {'schema_version'}):
            raise kernel.InvalidProof('bundle fields must be exact strings')
        bundle = dict(bundle)  # Strings are immutable, no nested mutable payloads.
        if sum(len(v) for v in bundle.values() if type(v) is str) > bounds.max_bytes:
            raise kernel.ProofLimit('bundle byte limit')
        if bundle['kind'] != _KIND or bundle['theorem'] != _THEOREM or bundle['encoder'] != _ENCODER:
            raise kernel.InvalidProof('bundle theorem or encoder mismatch')
        _p, _c, cnf, identity = _obligation(left, right, dephaser, candidate, support,
                                          guard, bounds, max_items)
        if (identity['source_sha256'] != expected_source_sha256
                or identity['certificate_sha256'] != expected_certificate_sha256
                or any(bundle[key] != value for key, value in identity.items())
                or bundle['cnf'] != cnf):
            raise kernel.InvalidProof('proof is not bound to the expected sources/candidate/formula')
        if not bundle['lrat'].isascii():
            raise kernel.InvalidProof('non-ASCII LRAT')
        proof_hash = hashlib.sha256(bundle['lrat'].encode('ascii')).hexdigest()
        if proof_hash != bundle['lrat_sha256']:
            raise kernel.InvalidProof('proof digest mismatch')
        checked = kernel.check_lrat(cnf, bundle['lrat'], expected_cnf_sha256=identity['cnf_sha256'],
                                    limits=bounds, absolute_deadline=guard.deadline)
        if checked['status'] == 'inconclusive':
            raise kernel.ProofLimit(checked.get('reason', 'incomplete proof check'))
        if checked['status'] != 'verified_unsat' or not checked['verified_unsat']:
            raise kernel.InvalidProof(checked.get('reason', 'invalid proof'))
        guard.check_time()
        result.update(status='proved', independent_unsat_checked=True,
                      controlled_use_authorized=False, **identity,
                      lrat_sha256=proof_hash, checked_steps=checked['steps'])
        guard.check_time()
    except (Limit, ResourceLimitExceeded, kernel.ProofLimit) as error:
        result = {'status': 'inconclusive', 'independent_unsat_checked': False, 'reason': str(error)}
    except (kernel.InvalidProof, _NotApplicable) as error:
        result = {'status': 'invalid', 'independent_unsat_checked': False, 'reason': str(error)}
    result['seconds'] = time.perf_counter() - started
    return result


def export_factored_proof(left, right, dephaser, candidate, *, support=None,
                          budget=None, limits=None, max_items=100000):
    """Produce a portable proof and verify it through the solver-free consumer.

    The original APIs are untouched. A failed export does not fall back to an
    unchecked 'proved'. The bundle is returned only after source-bound proof
    checking and final cleanup/deadline checks have all succeeded.
    """
    from symq.errors import ResourceLimitExceeded
    from symq.labs.anchored_kraus import Limit
    from symq.labs.dyadic_phase import DyadicPhaseProgram
    from symq.labs.lrat_export import prove_cnf
    from symq.phase import PhaseProgram

    bounds = _bounds(limits)
    guard = _guard(budget, bounds)
    started = time.perf_counter()
    result = {'status': 'inconclusive', 'independent_unsat_checked': False, 'bundle': None}
    try:
        problem, frozen, cnf, identity = _obligation(left, right, dephaser, candidate, support,
                                                    guard, bounds, max_items)
        generated = prove_cnf(cnf, budget=guard.inherited_budget(), limits=bounds)
        if generated['status'] != 'proof_checked':
            result.update(status='not_proved' if generated['status'] == 'satisfiable'
                          else generated['status'], reason=generated.get('reason', generated['status']))
        else:
            # No trust in the producer's status or its purported successful check.
            proof = generated.get('lrat')
            if type(proof) is not str or not proof.isascii():
                raise kernel.InvalidProof('producer did not provide ASCII LRAT')
            bundle = {'kind': _KIND, 'schema_version': 1, **identity, 'cnf': cnf, 'lrat': proof,
                      'lrat_sha256': hashlib.sha256(proof.encode('ascii')).hexdigest()}
            a, b, d, domain, _h, _delta, _k = problem
            fresh = check_factored_proof(
                DyadicPhaseProgram(a.width, list(a.gates), a.k),
                DyadicPhaseProgram(b.width, list(b.gates), b.k),
                PhaseProgram(d[0], d[1], list(d[2])), frozen, bundle,
                expected_source_sha256=identity['source_sha256'],
                expected_certificate_sha256=identity['certificate_sha256'], support=domain,
                budget=guard.inherited_budget(), limits=bounds, max_items=max_items)
            if fresh['status'] != 'proved' or not fresh['independent_unsat_checked']:
                result.update(status=fresh['status'], reason=fresh.get('reason', 'fresh proof refused'))
            else:
                result.update(status='proved', independent_unsat_checked=True, bundle=bundle,
                              semantic_kernel_formally_verified=False,
                              controlled_use_authorized=False, **identity)
        guard.check_time()
    except (Limit, ResourceLimitExceeded, kernel.ProofLimit) as error:
        result = {'status': 'inconclusive', 'reason': str(error),
                  'bundle': None, 'independent_unsat_checked': False}
    except (kernel.InvalidProof, _NotApplicable) as error:
        result = {'status': 'not_proved', 'reason': str(error),
                  'bundle': None, 'independent_unsat_checked': False}
    result['seconds'] = time.perf_counter() - started
    return result
