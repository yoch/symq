"""Research: source-bound phases as weighted XORs of products of affine forms.

An affine form is an integer mask: bit0 is the constant, bit(j+1) selects h_j.
A certificate is an exact tuple of (coefficient, XOR-of-products) pairs, where
products are tuples of affine-form masks. Products are NEVER expanded into ANF.
The recognizer is sufficient only; its failure is not channel inequivalence.
"""
from __future__ import annotations

import time


def _span(generators, guard):
    """GF(2) row elimination on actual source ANFs, with affine-form provenance."""
    basis = {}
    stored = 0
    for i, polynomial in enumerate([frozenset((0,)), *generators]):
        guard.check_time()
        row, form = polynomial, 1 << i
        while row:
            guard.check_time()
            pivot = max(row)
            if pivot not in basis:
                basis[pivot] = (row, form)
                stored += len(row) + form.bit_count()
                guard.check_terms(stored)
                break
            previous, provenance = basis[pivot]
            guard.check_terms(stored + len(row) + len(previous))
            row, form = row ^ previous, form ^ provenance
    return basis


def _recover(polynomial, basis, guard):
    row, form = polynomial, 0
    while row:
        guard.check_time()
        pivot = max(row)
        if pivot not in basis:
            return None
        previous, provenance = basis[pivot]
        guard.check_terms(len(row) + len(previous))
        row, form = row ^ previous, form ^ provenance
    return form


def _linear_source(form, signature, guard):
    """Substitute a candidate affine form from REAL signature expressions."""
    polynomial = frozenset((0,)) if form & 1 else frozenset()
    todo = form >> 1
    while todo:
        guard.check_time()
        bit = todo & -todo
        item = signature[bit.bit_length() - 1]
        guard.check_terms(len(polynomial) + len(item))
        polynomial ^= item
        todo ^= bit
    return polynomial


def _propose(signature, delta, guard, max_items):
    """Recognize source atoms in span(1,h), then cover phase monomials exactly.

    Only monomials already present in the frozen source ANFs are considered.
    This bounded vocabulary can miss factorizations. The returned certificate
    has no authority until check_factored_phase checks the frozen sources afresh.
    """
    from symq.errors import InternalInconsistency
    from symq.labs.anchored_kraus import Limit

    basis = _span(signature, guard)
    atoms = set()
    for polynomial in (*signature, *delta):
        for monomial in polynomial:
            guard.check_time()
            if monomial:
                atoms.add(monomial)
            if len(atoms) > max_items:
                raise Limit('factored source atom cap')
    factors = {}
    for atom in sorted(atoms):
        guard.check_time()
        form = _recover(frozenset((atom,)), basis, guard)
        if form is not None:
            if _linear_source(form, signature, guard) != frozenset((atom,)):
                raise InternalInconsistency('affine factor provenance failed reconstruction')
            factors[atom] = form
    certificate = []
    items = 0
    for predicate, coefficient in sorted(delta.items(), key=lambda item: tuple(sorted(item[0]))):
        guard.check_time()
        direct = _recover(predicate, basis, guard)
        if direct is not None:
            products = ((direct,),)
        else:
            parity = set()
            for target in sorted(predicate):
                guard.check_time()
                remaining, selected, reconstructed = target, [], 0
                while remaining:
                    choice, best = None, 0
                    for atom, form in factors.items():
                        guard.check_time()
                        gain = (atom & remaining).bit_count()
                        if atom & ~target == 0 and gain > best:
                            choice, best = (atom, form), gain
                    if choice is None:
                        return None, {'uncovered_monomial': target,
                                      'recovered_factors': len(factors), 'span_rank': len(basis)}
                    atom, form = choice
                    selected.append(form)
                    remaining &= ~atom
                    reconstructed |= atom
                if reconstructed != target:
                    raise InternalInconsistency('monomial cover failed reconstruction')
                product = tuple(sorted(set(selected)))
                if product in parity:
                    parity.remove(product)
                else:
                    parity.add(product)
                items += 1 + len(product) + sum(mask.bit_count() for mask in product)
                guard.check_terms(items)
                if items > max_items:
                    raise Limit('factored certificate proposal cap')
            products = tuple(sorted(parity))
        items += 2 + sum(1 + len(p) + sum(mask.bit_count() for mask in p) for p in products)
        guard.check_terms(items)
        if items > max_items:
            raise Limit('factored certificate proposal cap')
        certificate.append((coefficient, products))
    guard.check_time()
    return tuple(certificate), {'recovered_factors': len(factors), 'span_rank': len(basis)}


def _freeze_certificate(candidate, width, k, guard, max_items):
    """Exact immutable depth-4 grammar; no user iteration or equality methods."""
    from symq.labs.anchored_kraus import Limit

    count = 0

    def charge(amount=1):
        nonlocal count
        guard.check_time()
        count += amount
        guard.check_terms(count)
        if count > max_items:
            raise Limit('factored certificate item cap')

    charge()
    if type(candidate) is not tuple:
        raise ValueError('certificate must be an exact tuple')
    frozen = []
    for term in candidate:
        charge()
        if type(term) is not tuple or len(term) != 2:
            raise ValueError('each term must be (integer coefficient, tuple of products)')
        coefficient, products = term
        if type(coefficient) is not int or not 0 <= coefficient < 1 << k:
            raise ValueError('coefficient must be canonical modulo 2**k')
        if type(products) is not tuple:
            raise ValueError('XOR-of-products must be an exact tuple')
        copied = []
        for product in products:
            charge()
            if type(product) is not tuple:
                raise ValueError('product must be an exact tuple of affine masks')
            masks = []
            for mask in product:
                charge()
                if type(mask) is not int or mask < 0 or mask.bit_length() > width + 1:
                    raise ValueError('affine masks must be exact, nonnegative and in range')
                charge(mask.bit_count())
                masks.append(mask)
            copied.append(tuple(masks))
        frozen.append((coefficient, tuple(copied)))
    return tuple(frozen), count


def _compile(candidate, signature, inputs, k, checker, graph, guard):
    weighted, predicates = {}, []
    for index, (coefficient, products) in enumerate(candidate):
        total = graph.zero
        for product in products:
            value = graph.one
            for form in product:
                polynomial = _linear_source(form, signature, guard)
                value = graph.mul(value, checker._bool(polynomial, inputs, graph))
            total = graph.xor(total, value)
        predicates.append(total)
        weighted[frozenset((1 << index,))] = coefficient
        guard.check_time()
    return checker._phase_bits(weighted, predicates, k, graph)


def _evaluate(candidate, signature_word, guard):
    """Literal certificate arithmetic independent of DAG/source polynomial evaluation."""
    word = 1 | signature_word << 1
    result = 0
    for coefficient, products in candidate:
        parity = 0
        for product in products:
            value = 1
            for form in product:
                guard.check_time()
                value &= (form & word).bit_count() & 1
            parity ^= value
        result += coefficient * parity
    guard.check_time()
    return result


def _new_guard(budget):
    from symq.labs import affine_phase as core
    from symq.resources import Budget, intersect_budgets

    first = core._guard(budget)
    return core._guard(intersect_budgets(Budget(max_terms=100000, max_seconds=10),
                                        Budget(first.budget.max_terms, absolute_deadline=first.deadline)))


def _caps(*values):
    for cap in values:
        if type(cap) is not int or cap < 1:
            raise ValueError('caps must be positive exact integers')


def check_factored_phase(left, right, dephaser, candidate, *, support=None,
                          budget=None, max_items=100000,
                          max_graph_nodes=100000, max_clauses=500000):
    """Check a supplied weighted factored expression against frozen real sources.

    not_proved(candidate_value) refutes ONLY the supplied expression, not equality.
    A different(outputs) result is the replayed independent source-output mismatch.
    No reusable SAT proof, controlled-use permission or support preparation proof.
    """
    from symq.errors import InternalInconsistency, ResourceLimitExceeded, SatUnavailable
    from symq.labs import affine_phase as core
    from symq.labs import nonlinear_phase_bits as checker
    from symq.labs import phase_discovery as fixed
    from symq.labs.anchored_kraus import Limit
    from symq.labs.kraus_graph import Graph

    _caps(max_items, max_graph_nodes, max_clauses)
    guard = _new_guard(budget)
    started = time.perf_counter()
    graph = Graph(guard, max_graph_nodes, max_clauses)
    result = {'status': 'inconclusive', 'obligation': None, 'witness': None,
              'certificate_kind': 'weighted_affine_products_v1',
              'portable_certificate': False, 'controlled_use_authorized': False}
    try:
        problem, identity = fixed._prepare(core, left, right, dephaser, support, guard)
        result.update(identity)
        if problem is not None:
            _a, _b, _d, domain, signature, delta, k = problem
            candidate, items = _freeze_certificate(candidate, len(signature), k, guard, max_items)
            result.update(certificate_sha256=core._hash(candidate), certificate_items=items)
            inputs = [graph.var(i) for i in range(len(domain.columns))]
            actual = checker._phase_bits(delta, inputs, k, graph)
            claimed = _compile(candidate, signature, inputs, k, checker, graph, guard)
            for j, (a, b) in enumerate(zip(actual, claimed)):
                parameter = graph.witness(graph.xor(a, b))
                if parameter is not None:
                    sample = fixed._sample(problem, parameter, core, guard)
                    expected = _evaluate(candidate, sample['signature'], guard) % (1 << k)
                    if ((sample['delta'] ^ expected) >> j & 1) == 0:
                        raise InternalInconsistency('factored counterexample failed literal replay')
                    result.update(status='not_proved', obligation='candidate_value',
                                  witness={**sample, 'candidate_delta': expected, 'bit': j})
                    break
            else:
                result.update(status='proved', checked_bits=k)
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
        result.pop('checked_bits', None)
    result.update(graph.metrics(), seconds=time.perf_counter() - started)
    return result


def _fresh(problem, candidate, guard, max_items, max_graph_nodes, max_clauses):
    from symq.labs.dyadic_phase import DyadicPhaseProgram
    from symq.phase import PhaseProgram

    a, b, d, domain, _h, _delta, _k = problem
    left = DyadicPhaseProgram(a.width, list(a.gates), a.k)
    right = DyadicPhaseProgram(b.width, list(b.gates), b.k)
    source = PhaseProgram(d[0], d[1], list(d[2]))
    return check_factored_phase(left, right, source, candidate, support=domain,
                                budget=guard.inherited_budget(), max_items=max_items,
                                max_graph_nodes=max_graph_nodes, max_clauses=max_clauses)


def discover_factored_phase(left, right, dephaser, *, support=None, budget=None,
                             max_items=100000, max_graph_nodes=100000, max_clauses=500000):
    """Sufficient structural discovery; missing factors are never inequivalence.

    Learn affine combinations of effective-signature ANFs, then recognize actual
    source monomial products. No complete degree layer or signature cube is built.
    Positive output requires NEW source preparation/checking under the same deadline.
    """
    from symq.errors import InternalInconsistency, ResourceLimitExceeded, SatUnavailable
    from symq.labs import affine_phase as core
    from symq.labs import phase_discovery as fixed
    from symq.labs.anchored_kraus import Limit

    _caps(max_items, max_graph_nodes, max_clauses)
    guard = _new_guard(budget)
    started = time.perf_counter()
    result = {'status': 'inconclusive', 'obligation': None, 'witness': None,
              'certificate': None, 'fresh_verified': False, 'portable_certificate': False,
              'certificate_kind': 'weighted_affine_products_v1', 'controlled_use_authorized': False}
    try:
        problem, identity = fixed._prepare(core, left, right, dephaser, support, guard)
        result.update(identity)
        if problem is not None:
            _a, _b, _d, _domain, signature, delta, _k = problem
            candidate, details = _propose(signature, delta, guard, max_items)
            result.update(details)
            if candidate is None:
                result.update(status='not_proved', obligation='structural_factorization')
            else:
                before = time.perf_counter()
                fresh = _fresh(problem, candidate, guard, max_items, max_graph_nodes, max_clauses)
                result['fresh_check_seconds'] = time.perf_counter() - before
                if fresh['status'] in ('inconclusive', 'unsupported'):
                    result.update(status=fresh['status'], obligation='fresh_check',
                                  reason=fresh.get('reason', fresh['status']))
                elif (fresh['status'] != 'proved'
                      or fresh.get('source_sha256') != result['source_sha256']
                      or fresh.get('certificate_sha256') != core._hash(candidate)):
                    raise InternalInconsistency('proposed factored certificate failed fresh checking')
                else:
                    result.update(status='proved', certificate=candidate, fresh_verified=True,
                                  certificate_sha256=fresh['certificate_sha256'],
                                  certificate_items=fresh['certificate_items'], fresh_metrics=fresh)
        guard.check_time()
    except (Limit, ResourceLimitExceeded) as error:
        result.update(status='inconclusive', obligation='resources', certificate=None,
                      witness=None, fresh_verified=False, reason=str(error))
    except SatUnavailable as error:
        result.update(status='unsupported', obligation='backend', certificate=None,
                      witness=None, fresh_verified=False, reason=str(error))
    if result['status'] != 'proved':
        # A revoked or failed run must not keep any field of a positive answer.
        for key in ('fresh_metrics', 'certificate_sha256', 'certificate_items'):
            result.pop(key, None)
    result['seconds'] = time.perf_counter() - started
    return result
