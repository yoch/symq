"""Reproduce the restricted GF24 99-term order search deterministically.

This is an explicit seeded research grid of term orders for one *fixed*
factorization and one *fixed* linear-frame emitter, NOT a globally
optimal CNOT search. A cheap pairwise transition heuristic proposes
2-opt reversals; every shortlisted path is scored by the exact
per-register pivot dynamic program, followed by exact short reversals.

Requires a checkout containing the pinned GF24 tensor and emits
a JSON receipt with a separate SHA-256. No user data or network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import sys
from pathlib import Path

from symq.generators.bilinear_optimization import _choose_order, _schedule_cost
from symq.labs.gf24_schedule import PINNED_ORDER, PINNED_ORDER_SHA256, pinned_gf24_emitted
from symq.labs.gf24_tower import gf24_tower_factors

SEARCH_SEEDS = 1000
MAX_FAST_REVERSALS = 120
MAX_FINAL_SWEEPS = 9
MAX_FINAL_SEGMENT = 9


def find_order() -> dict:
    factors = gf24_tower_factors()
    initial = _choose_order(factors)
    n = len(factors)
    if n != 99:
        raise ValueError("only a certified, exact 99-factor GF24 model is admitted")
    masks = [(t.left, t.right, t.into) for t in factors]
    endpoint = [sum(mask.bit_count() - 1 for mask in row) for row in masks]
    edges = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            cost = 0
            for axis in range(3):
                a, b = masks[i][axis], masks[j][axis]
                switching = a.bit_count() + b.bit_count() - 2
                staying = (a ^ b).bit_count() if a & b else 1_000_000
                cost += min(switching, staying)
            edges[i][j] = edges[j][i] = cost

    def _start(row: int | None) -> int:
        return endpoint[row] if row is not None else 0

    def fast_refine(source: tuple[int, ...]) -> tuple[int, ...]:
        order = list(source)
        for _ in range(MAX_FAST_REVERSALS):
            winning_delta = 0
            winning_pair = None
            for i in range(n):
                before = order[i - 1] if i else None
                first = order[i]
                for j in range(i + 1, n):
                    last = order[j]
                    after = order[j + 1] if j + 1 < n else None
                    added = ((edges[before][last] if before is not None else _start(last))
                             + (edges[first][after] if after is not None else _start(first)))
                    removed = ((edges[before][first] if before is not None else _start(first))
                               + (edges[last][after] if after is not None else _start(last)))
                    if added - removed < winning_delta:
                        winning_delta = added - removed
                        winning_pair = (i, j)
            if winning_pair is None:
                break
            i, j = winning_pair
            order[i:j + 1] = reversed(order[i:j + 1])
        return tuple(order)

    best: tuple[int, ...] | None = None
    best_cost = 1 << 30
    best_seed = -1
    for seed in range(SEARCH_SEEDS):
        if seed == 0:
            candidate = initial
        elif seed == 1:
            candidate = tuple(range(n))
        elif seed == 2:
            candidate = tuple(reversed(initial))
        else:
            rng = random.Random(seed)
            permuted = list(initial)
            for _ in range(seed % 12 + 1):
                left, right = sorted(rng.sample(range(n), 2))
                permuted[left:right + 1] = reversed(permuted[left:right + 1])
            candidate = tuple(permuted)
        order = fast_refine(candidate)
        score = _schedule_cost(factors, order)
        if score < best_cost:
            best, best_cost, best_seed = order, score, seed
    if best is None:
        raise RuntimeError("no GF24 term order evaluated")

    intermediate_cost = best_cost
    for _ in range(MAX_FINAL_SWEEPS):
        winning_cost = best_cost
        winning_order = best
        for i in range(n - 1):
            for j in range(i + 1, min(n, i + MAX_FINAL_SEGMENT)):
                trial = best[:i] + tuple(reversed(best[i:j + 1])) + best[j + 1:]
                score = _schedule_cost(factors, trial)
                if score < winning_cost:
                    winning_cost, winning_order = score, trial
        if winning_order == best:
            break
        best, best_cost = winning_order, winning_cost
    order_sha = hashlib.sha256(",".join(map(str, best)).encode("ascii")).hexdigest()
    if best != PINNED_ORDER or order_sha != PINNED_ORDER_SHA256 or best_cost != 2634:
        raise ValueError("independent pinned GF24 schedule search no longer reproduces")
    gate_cost = pinned_gf24_emitted()
    if gate_cost.cx != best_cost:
        raise ArithmeticError("exact pivot path cost and emitted gate count disagree")
    return {
        "schema": "symq-gf24-pinned-order-search-v1",
        "factor_count": n, "seeds": SEARCH_SEEDS, "best_seed": best_seed,
        "fast_two_opt_limit": MAX_FAST_REVERSALS,
        "exact_final_sweeps": MAX_FINAL_SWEEPS,
        "exact_final_segment": MAX_FINAL_SEGMENT,
        "base_default_scheduled_cx": _schedule_cost(factors, initial),
        "best_fast_sweep_exact_cx": intermediate_cost,
        "best_refined_exact_cx": best_cost,
        "ccx": gate_cost.ccx,
        "order": list(best), "order_sha256": order_sha,
        "not_global_cnot_optimality": True,
        "not_hardware_or_competition_cost": True,
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = (json.dumps(find_order(), sort_keys=True, indent=2) + "\n").encode("utf-8")
    args.output.write_bytes(payload)
    args.output.with_name(args.output.name + ".sha256").write_text(
        hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii"
    )
    print("GF24 fixed order independently reconstructed:", args.output)


if __name__ == "__main__":
    main()
