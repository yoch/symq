"""Constructive logarithmic-degree separators for adaptive GF(2) interpolation.

For N distinct Boolean signature words, return a positive monomial with odd
incidence and degree <= floor(log2(N)). No minimum-degree claim. The general
existence bound follows from Reed--Muller dual distance; this implementation
uses a direct minority-cube construction and parity-preserving literal removal.
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

    # Choose the smaller nonempty half at each split. After at most floor(log2 N)
    # splits one word remains. The resulting mixed-literal cube isolates it.
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

    # C*(1+x_i) = C + C*x_i over GF(2): odd incidence of the left side
    # ensures at least one right-side term is odd. Never expand 2^k terms.
    while negative:
        tick()
        bit = negative & -negative
        remaining = negative ^ bit
        if not odd(positive, remaining):
            positive |= bit
        negative = remaining

    # Optional reduction to deletion-minimality. This cannot increase degree,
    # but still does NOT prove that the answer has globally minimum degree.
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
