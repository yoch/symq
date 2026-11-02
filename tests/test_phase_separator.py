"""Finite-set separator degree theorem, tight bound, hostile inputs and non-optimality."""
from __future__ import annotations

import random
from itertools import combinations

import pytest

from symq.labs.phase_adaptive import _separator
from symq.labs.phase_separator import halving_separator


def parity(words, mask):
    positions = [i for i in range(mask.bit_length()) if mask >> i & 1]
    return sum(all(word >> i & 1 for i in positions) for word in words) % 2


def test_logarithmic_degree_bound_on_all_small_finite_sets():
    count = 0
    for width in range(1, 5):
        for membership in range(1, 1 << (1 << width)):
            words = tuple(word for word in range(1 << width) if membership >> word & 1)
            mask = halving_separator(words, lambda: None)
            assert parity(words, mask) == 1
            assert mask.bit_count() <= len(words).bit_length() - 1
            for bit in range(width):
                if mask >> bit & 1:
                    assert parity(words, mask ^ (1 << bit)) == 0
            count += 1
    assert count == 65808


def test_tight_bound_and_a_family_where_greedy_degree_is_unboundedly_worse():
    for width in range(1, 8):
        words = tuple(range(1 << width))
        assert halving_separator(words, lambda: None) == (1 << width) - 1
    for width in (5, 7, 15, 31, 63, 127, 255):
        full = (1 << width) - 1
        words = tuple(sorted({0, full, *(full ^ (1 << j) for j in range(width)),
                              *(1 << j for j in range(width))}))
        assert len(words) == 2 * width + 2
        assert _separator(words, lambda: None) == full
        small = halving_separator(words, lambda: None)
        assert small.bit_count() == 3 and parity(words, small) == 1
        if width <= 31:
            for degree in range(3):
                for variables in combinations(range(width), degree):
                    assert parity(words, sum(1 << j for j in variables)) == 0


def test_not_a_minimum_degree_or_dominance_claim():
    words = (0, 2, 3, 5)
    chosen = halving_separator(words, lambda: None)
    assert chosen == 3 and chosen.bit_count() == 2
    assert parity(words, 4) == 1
    assert _separator(words, lambda: None).bit_count() == 1


def test_wide_sets_permutation_invariance_and_budget_callback():
    rng = random.Random(16602)
    for width in (8, 24, 48, 128, 256):
        for _ in range(100):
            words = tuple(sorted({rng.getrandbits(width) for _ in range(rng.randrange(1, 100))}))
            chosen = halving_separator(words, lambda: None)
            assert parity(words, chosen) == 1
            assert chosen.bit_count() <= len(words).bit_length() - 1
            assert halving_separator(tuple(reversed(words)), lambda: None) == chosen
    for invalid in ((), [], (0, 0), (True,), (-1,), ('0',)):
        with pytest.raises(ValueError):
            halving_separator(invalid, lambda: None)
    calls = [0]

    def count():
        calls[0] += 1

    sample = tuple(range(8))
    halving_separator(sample, count)
    for point in range(calls[0]):
        remaining = [point]

        def expire():
            if remaining[0] == 0:
                raise TimeoutError('injected separator deadline')
            remaining[0] -= 1

        with pytest.raises(TimeoutError):
            halving_separator(sample, expire)
