"""Ancilla-free bilinear synthesis with reversible linear-frame reuse.

This is a general GF(2) bilinear-term *emitter*, not a low-rank finder or
an equivalence certificate for the supplied factorization. Given validated
terms (u, v, w), it emits a complete permutation on three dirty n-bit
registers: (a, b, z) -> (a, b, z XOR sum((u.a)*(v.b)*w)).

Each rank-one product uses exactly one CCX, regardless of output weight.
A temporary target-output CNOT fanout frame permits dirty output bits.
Optionally, the A, B and Z linear frames persist between products; exact
GF(2)-linear updates are undone before returning. A bounded deterministic
order heuristic improves CNOT count without changing the tensor.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..circuit import Circuit
from .gf2n import Term

MAX_SCHEDULE_TERMS = 1024
MAX_2OPT_TERMS = 32


def _check_terms(n: int, terms: Sequence[Term]) -> None:
    if type(n) is not int or not 1 <= n <= 64:
        raise ValueError("bilinear width must be an integer in 1..64")
    if not isinstance(terms, (list, tuple)) or not terms:
        raise ValueError("bilinear factors must be a nonempty list/tuple")
    limit = 1 << n
    for i, term in enumerate(terms):
        if type(term) is not Term or any(
            type(v) is not int or not 0 < v < limit
            for v in (term.left, term.right, term.into)
        ):
            raise ValueError(f"invalid bilinear factor {i}: expected nonzero n-bit masks")


def _pivot_bits(mask: int) -> tuple[int, ...]:
    return tuple(i for i in range(mask.bit_length()) if mask & (1 << i))


def _optimal_pivots(masks: list[int]) -> tuple[int, tuple[int, ...]]:
    """DP: exact minimum CNOT transitions for one register and fixed term order.

    State is one outstanding pivot frame; all other wires remain untouched
    (for input registers) or in the corresponding fanout frame (for outputs).
    Each mask is nonzero and the final frame must return to identity.
    """
    first = masks[0]
    previous = {p: first.bit_count() - 1 for p in _pivot_bits(first)}
    parents: list[dict[int, int]] = []
    for before, after in zip(masks, masks[1:]):
        next_costs: dict[int, int] = {}
        from_pivot: dict[int, int] = {}
        before_weight = before.bit_count() - 1
        after_weight = after.bit_count() - 1
        overlap_cost = (before ^ after).bit_count()
        for p in _pivot_bits(after):
            prev_p = min(
                previous,
                key=lambda old: (
                    previous[old] + (
                        overlap_cost if old == p else before_weight + after_weight
                    ),
                    old,
                ),
            )
            from_pivot[p] = prev_p
            next_costs[p] = previous[prev_p] + (
                overlap_cost if prev_p == p else before_weight + after_weight
            )
        parents.append(from_pivot)
        previous = next_costs
    final_p = min(previous, key=lambda p: (previous[p], p))
    total = previous[final_p] + masks[-1].bit_count() - 1
    path = [final_p]
    for predecessors in reversed(parents):
        path.append(predecessors[path[-1]])
    return total, tuple(reversed(path))


def _schedule_cost(terms: Sequence[Term], order: Sequence[int]) -> int:
    return sum(
        _optimal_pivots([getattr(terms[i], attribute) for i in order])[0]
        for attribute in ("left", "right", "into")
    )


def _greedy_order(terms: Sequence[Term]) -> tuple[int, ...]:
    """Deterministic nearest-frame heuristic, bounded by MAX_SCHEDULE_TERMS."""
    remaining = set(range(len(terms)))
    old: list[tuple[int, int] | None] = [None, None, None]
    order: list[int] = []

    def cost(state: tuple[int, int] | None, mask: int) -> tuple[int, int]:
        low_p = (mask & -mask).bit_length() - 1
        if state is None:
            return mask.bit_count() - 1, low_p
        p, previous = state
        switching = previous.bit_count() + mask.bit_count() - 2
        if mask & (1 << p):
            staying = (previous ^ mask).bit_count()
            if staying <= switching:
                return staying, p
        return switching, low_p

    while remaining:
        index = min(
            remaining,
            key=lambda i: (
                sum(
                    cost(old[k], (terms[i].left, terms[i].right, terms[i].into)[k])[0]
                    for k in range(3)
                ),
                i,
            ),
        )
        remaining.remove(index)
        term = terms[index]
        masks = (term.left, term.right, term.into)
        old = [(cost(old[k], masks[k])[1], masks[k]) for k in range(3)]
        order.append(index)
    return tuple(order)


def _choose_order(terms: Sequence[Term]) -> tuple[int, ...]:
    count = len(terms)
    if count > MAX_SCHEDULE_TERMS:
        raise ValueError(
            f"pivot-scheduled synthesis supports at most {MAX_SCHEDULE_TERMS} terms"
        )
    original = tuple(range(count))
    greedy = _greedy_order(terms)
    order = min((original, greedy), key=lambda o: (_schedule_cost(terms, o), o))
    if count > MAX_2OPT_TERMS:
        return order
    # Deterministic best-improvement segment reversal; no randomness, time limit or
    # dependence on hash iteration order. 12 sweeps bound the cubic exploration.
    for _ in range(12):
        current_cost = _schedule_cost(terms, order)
        candidate = order
        for i in range(count):
            for j in range(i + 1, count):
                revised = order[:i] + tuple(reversed(order[i:j + 1])) + order[j + 1:]
                new_cost = _schedule_cost(terms, revised)
                if new_cost < current_cost:
                    candidate, current_cost = revised, new_cost
        if candidate == order:
            break
        order = candidate
    return order


def emit_pivot(
    n: int, terms: Sequence[Term], *, schedule: bool = False
) -> tuple[Circuit, int]:
    """Emit 1 CCX per term; return circuit and input-fold CX count.

    Without scheduling, the factor order is unchanged but DP chooses pivots to
    minimize CNOT frame updates. With scheduling, a bounded deterministic greedy
    / 2-opt ordering is considered too. Both modes preserve all input wires and
    dirty output registers and restore all outstanding linear frames.
    """
    _check_terms(n, terms)
    order = _choose_order(terms) if schedule else tuple(range(len(terms)))
    all_masks = [
        [getattr(terms[i], field) for i in order]
        for field in ("left", "right", "into")
    ]
    pivots = [_optimal_pivots(masks)[1] for masks in all_masks]
    circuit = Circuit(3 * n)
    frames: list[tuple[int, int] | None] = [None, None, None]
    fold_cx = 0

    def toggle(axis: int, pivot: int, off: int) -> None:
        nonlocal fold_cx
        if axis == 2:
            circuit.cx(2 * n + pivot, 2 * n + off)
        else:
            circuit.cx(axis * n + off, axis * n + pivot)
            fold_cx += 1

    def update(axis: int, pivot: int, mask: int) -> None:
        previous = frames[axis]
        if previous is not None and previous[0] == pivot:
            old_mask = previous[1]
            for off in _pivot_bits(old_mask ^ mask):
                toggle(axis, pivot, off)
        else:
            if previous is not None:
                old_p, old_mask = previous
                for off in _pivot_bits(old_mask & ~(1 << old_p)):
                    toggle(axis, old_p, off)
            for off in _pivot_bits(mask & ~(1 << pivot)):
                toggle(axis, pivot, off)
        frames[axis] = (pivot, mask)

    for position, index in enumerate(order):
        term = terms[index]
        for axis, mask in enumerate((term.left, term.right, term.into)):
            update(axis, pivots[axis][position], mask)
        circuit.ccx(pivots[0][position], n + pivots[1][position], 2 * n + pivots[2][position])

    for axis, frame in enumerate(frames):
        if frame is not None:
            p, mask = frame
            for off in _pivot_bits(mask & ~(1 << p)):
                toggle(axis, p, off)
    return circuit, fold_cx


def _remainder(dividend: int, divisor: int) -> int:
    while dividend and dividend.bit_length() >= divisor.bit_length():
        dividend ^= divisor << (dividend.bit_length() - divisor.bit_length())
    return dividend


def _irreducible(modulus: int) -> bool:
    """Rabin's monic binary polynomial irreducibility test (no external deps)."""
    n = modulus.bit_length() - 1
    if n < 1 or modulus & 1 == 0:
        return False

    def gcd(a: int, b: int) -> int:
        while b:
            a, b = b, _remainder(a, b)
        return a

    divisors = [
        p for p in range(2, n + 1)
        if n % p == 0 and all(p % q for q in range(2, int(p ** 0.5) + 1))
    ]
    checkpoints = {n // p for p in divisors}
    x = _remainder(2, modulus)
    power = x
    for degree in range(1, n + 1):
        # In GF(2), squaring is a bit-index doubling map before reduction.
        square = sum(1 << (2 * i) for i in _pivot_bits(power))
        power = _remainder(square, modulus)
        if degree in checkpoints and gcd(power ^ x, modulus) != 1:
            return False
    return power == x


def certify_decomposition(n: int, terms: Sequence[Term], modulus: int) -> None:
    """Exact arithmetic certificate for arbitrary field basis polynomials.

    Verifies T[i,j,k] == coefficient k of x^(i+j) mod modulus for all
    i,j,k. Rejects reducible / malformed polynomials and malformed terms.
    This is distinct from circuit equivalence and contextual substitution.
    """
    _check_terms(n, terms)
    if (type(modulus) is not int or modulus.bit_length() != n + 1
            or not (modulus & 1) or not _irreducible(modulus)):
        raise ValueError("modulus must be a monic irreducible degree-n GF(2) polynomial")
    table = [[0] * n for _ in range(n)]
    for term in terms:
        for i in _pivot_bits(term.left):
            for j in _pivot_bits(term.right):
                table[i][j] ^= term.into
    for i in range(n):
        for j in range(n):
            expected = _remainder(1 << (i + j), modulus)
            if table[i][j] != expected:
                raise ValueError(
                    f"tensor mismatch at GF(2) basis ({i},{j}): "
                    f"actual={table[i][j]}, expected={expected}"
                )
