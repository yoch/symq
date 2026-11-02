"""Bounded functional qualification of SAT cut-invariant discovery.

This is exposed development evidence, not a speed comparison or an untouched
compiler holdout. Trials run serially in randomized order in one process;
process-peak RSS includes imports and previous trials. The finite oracle is
outside both measured discovery/replay calls. Raw JSON belongs in CI artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import resource
import sys
import time
from collections import Counter
from pathlib import Path

from symq import Circuit, Gate
from symq.kickmix import parse_kmx
from symq.labs.cut_invariants import (
    InvariantLimits,
    discover_cut_invariants,
    replay_cut_invariants,
)
from symq.resources import Budget
from symq.sat.assumptions import Const, Eq, Var, evaluate

from .environment import machine, receipt

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = "benchmarks/corpus/kickmix/inc8.kmx"
PUBLIC_BLOB = "0604339b577f47d5cc63de0a89088863e1e8a935"
SEED = 20261101


def cases() -> list[dict]:
    raw = (ROOT / PUBLIC).read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if actual != PUBLIC_BLOB:
        raise ValueError("public fixture changed from the inspected source")
    program = parse_kmx(raw.decode()).to_phase_program(range(8))
    if program.width != 13 or not all(
            op.kind == "mcx" and len(op.qubits) == 3 for op in program.ops[:5]):
        raise ValueError("the selected public prefix no longer has the expected grammar")
    public = Circuit(13, [Gate("ccx", op.qubits) for op in program.ops[:5]])
    rng = random.Random(SEED)
    nonlinear = Circuit(6)
    for _ in range(24):
        a, b, c = rng.sample(range(6), 3)
        nonlinear.ccx(a, b, c).cx(c, a)
    return [
        {"id": "public-inc8-prefix", "prefix": public,
         "constants": tuple((q, 0) for q in range(8, 13)),
         "provenance": "existing-public-kickmix", "expected": "complete"},
        {"id": "synthetic-clean-product", "prefix": Circuit(3).ccx(0, 1, 2),
         "constants": ((2, 0),), "provenance": "synthetic", "expected": "complete"},
        {"id": "synthetic-dirty-product", "prefix": Circuit(3).ccx(0, 1, 2),
         "constants": (), "provenance": "synthetic", "expected": "complete"},
        {"id": "synthetic-relational-domain", "prefix": Circuit(4).cx(0, 2).ccx(1, 2, 3),
         "constants": (), "assumption": Eq(Var("x.0"), Var("x.1")),
         "provenance": "synthetic", "expected": "complete"},
        {"id": "synthetic-dense-six", "prefix": nonlinear,
         "constants": ((4, 0), (5, 0)), "provenance": "synthetic", "expected": "complete"},
        {"id": "synthetic-empty-domain", "prefix": Circuit(3), "constants": (),
         "assumption": Const(False), "provenance": "synthetic", "expected": "empty_domain"},
        {"id": "synthetic-refinement-stop", "prefix": Circuit(4), "constants": (),
         "limits": InvariantLimits(max_refinements=0),
         "provenance": "synthetic", "expected": "inconclusive"},
    ]


def _rank(rows: list[list[int]]) -> int:
    matrix = [row[:] for row in rows]
    rank = 0
    if not rows:
        return rank
    for column in range(len(rows[0])):
        pivot = next((i for i in range(rank, len(matrix)) if matrix[i][column]), None)
        if pivot is None:
            continue
        matrix[rank], matrix[pivot] = matrix[pivot], matrix[rank]
        for i in range(rank + 1, len(matrix)):
            if matrix[i][column]:
                matrix[i] = [a ^ b for a, b in zip(matrix[i], matrix[rank])]
        rank += 1
    return rank


def trial(case: dict, repetition: int) -> dict:
    prefix = case["prefix"]
    kwargs = {"initial_constants": case["constants"], "assumption": case.get("assumption"),
              "budget": Budget(max_seconds=5)}
    started = time.perf_counter()
    result = discover_cut_invariants(prefix, limits=case.get("limits", InvariantLimits()), **kwargs)
    discovery_seconds = time.perf_counter() - started
    replay_seconds = None
    reverified = None
    if result.proved:
        started = time.perf_counter()
        reverified = replay_cut_invariants(prefix, result.to_dict(), **kwargs).proved
        replay_seconds = time.perf_counter() - started
    rows = []
    for value in range(1 << prefix.width):
        if any(((value >> q) & 1) != bit for q, bit in case["constants"]):
            continue
        if case.get("assumption") is not None and not evaluate(
                case["assumption"], {f"x.{q}": (value >> q) & 1 for q in range(prefix.width)}):
            continue
        state = prefix.run(value)
        rows.append([int(state & mask == mask) for mask in result.dictionary])
    rank = _rank(rows)
    oracle_ok = (result.outcome == case["expected"] and (
        result.outcome == "inconclusive" and not result.invariants
        or result.outcome == "empty_domain" and not rows
        or result.proved and reverified and rank == result.rank
        and len(result.invariants) == len(result.dictionary) - rank
        and _rank([[(invariant >> j) & 1 for j in range(len(result.dictionary))]
                   for invariant in result.invariants]) == len(result.invariants)
        and all(sum(bit * ((invariant >> j) & 1) for j, bit in enumerate(row)) % 2 == 0
                for row in rows for invariant in result.invariants)
    ))
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "case": case["id"], "repetition": repetition, "provenance": case["provenance"],
        "width": prefix.width, "prefix_gates": len(prefix.gates), "legal_inputs": len(rows),
        "outcome": result.outcome, "reason": result.reason, "engine": result.engine,
        "dictionary_size": len(result.dictionary), "invariant_count": len(result.invariants),
        "rank": result.rank, "refinements": result.refinements, "sat_queries": result.sat_queries,
        "peak_query_clauses": result.max_clauses, "peak_query_variables": result.max_variables,
        "discovery_seconds": discovery_seconds, "replay_seconds": replay_seconds,
        "process_peak_rss_bytes": int(rss if sys.platform == "darwin" else rss * 1024),
        "oracle_ok": bool(oracle_ok), "reverified": reverified,
        "prefix_sha256": result.prefix_sha256, "problem_sha256": result.problem_sha256,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error("repetitions must be between 1 and 20")
    corpus = cases()
    order = [(case, repetition) for repetition in range(args.repetitions) for case in corpus]
    random.Random(SEED).shuffle(order)
    trials = [trial(case, repetition) for case, repetition in order]
    result = {
        "kind": "symq_cut_invariant_development_qualification", "schema_version": 1,
        "scope": "fixed-dictionary classical prefix invariants; not untouched holdout or speed claim",
        "timing": "serial randomized single process; warm library caches; independent oracle excluded",
        "memory": "cumulative process peak RSS including imports and earlier trials, not per-call RSS",
        "seed": SEED, "machine": machine(), "software": receipt(),
        "fixture": {"path": PUBLIC, "git_blob_sha1": PUBLIC_BLOB},
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256((ROOT / "src/symq/labs/cut_invariants.py").read_bytes()).hexdigest(),
        "outcomes": dict(Counter(row["outcome"] for row in trials)),
        "all_oracles_ok": all(row["oracle_ok"] for row in trials), "trials": trials,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"trials": len(trials), "outcomes": result["outcomes"],
                      "all_oracles_ok": result["all_oracles_ok"]}, sort_keys=True))
    if not result["all_oracles_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
