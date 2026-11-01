"""Reconstruct a bounded GF24 99-term CNOT-order search, not a global optimum.

The order is optimized using a deterministic symmetric-edge surrogate
for reversible parity-frame transitions. Every survivor is re-scored
with SymQ's exact dynamic-programmed pivot counts. The best sequence
is checked against the separately pinned, SHA-guarded production order.
Only the published GF24 factors are used; no Kaggle score is computed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import sys
from itertools import pairwise
from pathlib import Path

from symq.generators.bilinear_optimization import _choose_order, _schedule_cost
from symq.labs.gf24_order import FACTOR_SHA256, PINNED_ORDER, reordered_gf24
from symq.labs.gf24_tower import gf24_tower_factors

SEEDS = 504
MAX_MOVES = 120


def _edges(terms):
    values = [(t.left, t.right, t.into) for t in terms]
    n = len(terms)
    weights = [sum(x.bit_count() - 1 for x in row) for row in values]
    adjacency = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            result = 0
            for left, right in zip(values[i], values[j]):
                changing_pivot = left.bit_count() + right.bit_count() - 2
                same_pivot = (left ^ right).bit_count() if left & right else 999
                result += min(changing_pivot, same_pivot)
            adjacency[i][j] = adjacency[j][i] = result
    return weights, adjacency


def _two_opt(order, weights, edges):
    current = list(order)
    n = len(current)
    cost = (weights[current[0]] + weights[current[-1]]
            + sum(edges[a][b] for a, b in pairwise(current)))
    for _ in range(MAX_MOVES):
        best_delta = 0
        best_pair = None
        for i in range(n):
            before = current[i - 1] if i else None
            first = current[i]
            for j in range(i + 1, n):
                last = current[j]
                after = current[j + 1] if j + 1 < n else None
                old = (edges[before][first] if before is not None else weights[first])
                old += edges[last][after] if after is not None else weights[last]
                new = (edges[before][last] if before is not None else weights[last])
                new += edges[first][after] if after is not None else weights[first]
                if new - old < best_delta:
                    best_delta, best_pair = new - old, (i, j)
        if best_pair is None:
            break
        start, stop = best_pair
        current[start:stop + 1] = reversed(current[start:stop + 1])
        cost += best_delta
    return tuple(current), cost


def campaign():
    terms = gf24_tower_factors()
    if tuple(terms[i] for i in PINNED_ORDER) != reordered_gf24():
        raise ValueError("pinned GF24 factor order and source disagree")
    begin = _choose_order(terms)
    weights, edges = _edges(terms)
    best = (10**9, ())
    improved = 0
    for seed in range(SEEDS):
        if seed == 0:
            start = begin
        elif seed == 1:
            start = tuple(range(len(terms)))
        elif seed == 2:
            start = tuple(reversed(begin))
        else:
            rng = random.Random(seed)
            mutated = list(begin)
            for _ in range(seed % 12 + 1):
                i, j = sorted(rng.sample(range(len(terms)), 2))
                mutated[i:j + 1] = reversed(mutated[i:j + 1])
            start = tuple(mutated)
        chosen, _heuristic = _two_opt(start, weights, edges)
        exact = _schedule_cost(terms, chosen)
        if exact < best[0]:
            best = (exact, chosen)
            improved += 1
    if best != (2646, PINNED_ORDER):
        raise RuntimeError("GF24 exact-CX order search is no longer reproducible")
    return {
        "schema": "symq-gf24-504-seed-order-v1",
        "source_factor_sha256": FACTOR_SHA256,
        "seeds": SEEDS,
        "surrogate": "symmetric nearest-frame edges with 2-opt segment reversal",
        "max_moves_per_seed": MAX_MOVES,
        "baseline_exact_cx": _schedule_cost(terms, begin),
        "best_exact_cx": best[0],
        "ccx": len(terms),
        "best_order": list(best[1]),
        "new_best_records": improved,
        "not_global_optimality_claim": True,
        "not_official_kaggle_score": True,
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = (json.dumps(campaign(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    args.output.write_bytes(payload)
    args.output.with_name(args.output.name + ".sha256").write_text(
        hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii"
    )


if __name__ == "__main__":
    main()
