"""Constructive logarithmic-degree and source-monomial phase feature proposals.

Neither finite-set separators nor source factorization authorize channel proofs.
Every final learned certificate must be checked afresh against the real sources.
"""
from __future__ import annotations


def halving_separator(signatures, tick):
    """Separate a finite obstruction; every loop participates in caller budgeting.

    This private research helper proposes ONE feature. Its caller must still
    replay the obstruction, verify odd incidence and rank growth, and freshly
    check any resulting phase certificate against the actual source programs.
    """
    if type(signatures) is not tuple or not signatures:
        raise ValueError('a nonempty tuple of distinct signature integers is required')
    seen = set()
    for word in signatures:
        tick()
        if type(word) is not int or word < 0 or word in seen:
            raise ValueError('signature words must be distinct nonnegative plain integers')
        seen.add(word)
    if len(signatures) % 2:
        tick()
        return 0

    def odd(positive, negative=0):
        parity = 0
        for word in signatures:
            tick()
            parity ^= int(word & positive == positive and not word & negative)
        return parity == 1

    active = signatures
    positive = negative = 0
    while len(active) > 1:
        varying = 0
        first = active[0]
        for word in active[1:]:
            tick()
            varying |= first ^ word
        if not varying:
            raise RuntimeError('distinct-word partition invariant failed')
        bit = varying & -varying
        zero, one = [], []
        for word in active:
            tick()
            (one if word & bit else zero).append(word)
        if len(zero) <= len(one):
            negative |= bit
            active = tuple(zero)
        else:
            positive |= bit
            active = tuple(one)
    if not odd(positive, negative):
        raise RuntimeError('isolating-cube parity invariant failed')
    bound = len(signatures).bit_length() - 1
    if (positive | negative).bit_count() > bound:
        raise RuntimeError('minority splitting exceeded the logarithmic bound')

    # C*(1+x_i) = C + C*x_i over GF(2): at least one right-hand term is odd.
    while negative:
        tick()
        bit = negative & -negative
        remaining = negative ^ bit
        if not odd(positive, remaining):
            positive |= bit
        negative = remaining

    changed = True
    while changed:
        changed = False
        todo = positive
        while todo:
            tick()
            bit = todo & -todo
            todo ^= bit
            reduced = positive ^ bit
            if odd(reduced):
                positive, changed = reduced, True
                break
    if positive.bit_count() > bound or not odd(positive):
        raise RuntimeError('positive separator invariant failed')
    tick()
    return positive


def source_monomial_seeds(signature, delta, guard, max_features):
    """Propose factors from actual prepared source ANFs, never supplied formulas.

    For a single source monomial p, consider only signature coordinates that are
    themselves nonconstant monomials contained in p. Their product is p exactly
    iff the union of their variable masks is p. Greedy cover need not minimize
    the number of factors; it merely supplies a correctly reconstructed feature.
    Nonmonomial predicates are ignored, NOT declared independent or different.
    """
    from symq.errors import InternalInconsistency
    from symq.labs.anchored_kraus import Limit

    factors = []
    for index, polynomial in enumerate(signature):
        guard.check_time()
        if len(polynomial) == 1:
            monomial = next(iter(polynomial))
            if monomial:
                factors.append((index, monomial))
    records, seen = [], set()
    for predicate in sorted(delta, key=lambda p: tuple(sorted(p))):
        guard.check_time()
        if len(predicate) != 1:
            continue
        target = next(iter(predicate))
        if not target:
            continue
        eligible = []
        for index, mask in factors:
            guard.check_time()
            if mask & ~target == 0:
                eligible.append((index, mask))
        residual, feature = target, 0
        while residual:
            chosen, best = None, 0
            for index, mask in eligible:
                guard.check_time()
                gain = (mask & residual).bit_count()
                if gain > best:
                    best, chosen = gain, (index, mask)
            if chosen is None:
                break
            index, mask = chosen
            feature |= 1 << index
            residual &= ~mask
        if not residual and feature not in seen:
            reconstructed = 0
            for index, mask in factors:
                guard.check_time()
                if feature >> index & 1:
                    reconstructed |= mask
            if reconstructed != target:
                raise InternalInconsistency('source factor reconstruction failed')
            if len(records) >= max_features:
                raise Limit('source feature proposal limit')
            seen.add(feature)
            records.append({'feature': feature, 'source_monomial': target})
            guard.check_terms(sum(r['feature'].bit_count() + r['source_monomial'].bit_count()
                                  for r in records))
    guard.check_time()
    return records
