"""Paired cost of the two address-domain constructions of the affine table verifier.

``verify_affine_table(..., domain_style=...)`` builds the indicator of the admitted
addresses either as one selector per admitted word (``minterms``, the reference) or by
Shannon decomposition (``shannon``, the default since 0.3.0). Both decide the same
obligation; this benchmark measures what each costs on the synthetic loader family of
``tests/testkit/wide_loader_cases.py``, at a few address widths, on both backends.

Method:

- each (width, seed, mutant, backend) cell is run with both styles, ``repetitions`` times
  each, in an order shuffled from a declared seed, every run in a fresh worker process
  (``run_isolated``), so no cache or allocator state is shared between runs;
- the shared contract is converted to the version-2 contract once per run, timed apart
  (``conversion_seconds``), and the verifier is timed alone (``verify_seconds``);
- every run records status, products or graph nodes, peak terms and the worker's CPU time
  and peak RSS; a run whose status differs from the other style's, or from the expected
  status of its case, fails the qualification, and is kept in the record.

The record says nothing beyond the family measured: these are synthetic loaders with a
few product terms, not a sample of real loaders, and no external tool is compared.

    python -m benchmarks.table_domain --repetitions 15 --output evidence/table-domain.json
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

from benchmarks.environment import machine, receipt
from symq.experimental.execution import HardLimits, run_isolated

STYLES = ("shannon", "minterms")
BACKENDS = ("anf", "sat")
WIDTHS = (6, 8, 10, 12)
DEV_SEEDS = (0, 1)
"""Seeds of the measured family; the qualification tests use the same development seeds
and a disjoint holdout range (``tests/test_wide_address_tables.py``)."""
SCHEDULE_SEED = 20261112


def job(width: int, seed: int, mutant: str | None, backend: str, style: str) -> dict:
    """One run, in a worker: build the case, convert its contract, verify. JSON out."""
    from symq.labs.affine_table import verify_affine_table
    from symq.labs.shared_table import _normalize
    from symq.resources import Budget, Guard
    from tests.testkit.wide_loader_cases import case

    loader = case(width, seed, mutant)
    source, contract = loader.source(), loader.contract()
    started = time.perf_counter()
    _document, normalized, *_ = _normalize(contract, Guard(Budget(max_seconds=60)))
    converted = time.perf_counter()
    result = verify_affine_table(source, normalized, backend=backend, domain_style=style,
                                 max_seconds=60)
    finished = time.perf_counter()
    return {"status": result["status"], "expected": loader.expected,
            "obligation": result.get("obligation"), "resource": result.get("resource"),
            "products": result.get("products"), "peak_terms": result.get("peak_terms"),
            "graph_nodes": result.get("graph_nodes"), "cnf_clauses": result.get("cnf_clauses"),
            "conversion_seconds": converted - started, "verify_seconds": finished - converted}


def _limits() -> HardLimits:
    linux = sys.platform.startswith("linux")
    return HardLimits(wall_seconds=120, memory_bytes=4 * 1024**3 if linux else None)


def _cells(widths, seeds, mutants):
    return [(width, seed, mutant, backend)
            for width in widths for seed in seeds for mutant in mutants for backend in BACKENDS]


def _quantiles(values):
    ordered = sorted(values)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]
    return {"median": statistics.median(ordered), "p10": pick(0.1), "p90": pick(0.9),
            "min": ordered[0], "max": ordered[-1], "n": len(ordered)}


def run(*, repetitions: int = 15, widths=WIDTHS, seeds=DEV_SEEDS,
        mutants=(None, "missing_phase"), isolated: bool = True) -> dict:
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("positive repetitions required")
    schedule = [(cell, style, repetition) for cell in _cells(widths, seeds, mutants)
                for style in STYLES for repetition in range(repetitions)]
    random.Random(SCHEDULE_SEED).shuffle(schedule)
    runs = []
    started = time.perf_counter()
    for (width, seed, mutant, backend), style, repetition in schedule:
        if isolated:
            outcome = run_isolated(job, width, seed, mutant, backend, style, limits=_limits())
            value = outcome.value if outcome.status == "completed" else None
            execution = {"execution": outcome.status, "execution_reason": outcome.reason,
                         "worker_wall_seconds": outcome.wall_seconds,
                         "worker_cpu_seconds": outcome.cpu_seconds,
                         "worker_peak_rss_bytes": outcome.peak_rss_bytes}
        else:
            value, execution = job(width, seed, mutant, backend, style), {"execution": "in_process"}
        runs.append({"width": width, "seed": seed, "mutant": mutant, "backend": backend,
                     "style": style, "repetition": repetition, **execution,
                     **(value or {"status": "error"})})
    cells, failures = [], []
    for width, seed, mutant, backend in _cells(widths, seeds, mutants):
        mine = [r for r in runs if (r["width"], r["seed"], r["mutant"], r["backend"])
                == (width, seed, mutant, backend)]
        by_style = {style: [r for r in mine if r["style"] == style] for style in STYLES}
        statuses = {style: sorted({r["status"] for r in rows}) for style, rows in by_style.items()}
        expected = next((r["expected"] for r in mine if "expected" in r), None)
        cell = {"width": width, "seed": seed, "mutant": mutant, "backend": backend,
                "expected": expected, "statuses": statuses}
        for style, rows in by_style.items():
            done = [r for r in rows if r["status"] == expected]
            if done:
                cell[style] = {"verify_seconds": _quantiles([r["verify_seconds"] for r in done]),
                               "conversion_seconds": _quantiles(
                                   [r["conversion_seconds"] for r in done]),
                               "products": done[0]["products"],
                               "graph_nodes": done[0]["graph_nodes"],
                               "peak_terms": done[0]["peak_terms"]}
        if all(style in cell for style in STYLES):
            cell["median_ratio_minterms_over_shannon"] = (
                cell["minterms"]["verify_seconds"]["median"]
                / max(cell["shannon"]["verify_seconds"]["median"], 1e-9))
        # The reference may stop on a resource limit (inconclusive); the default style may not
        # disagree with the expected status, and no style may return a different verdict.
        wrong = [r for r in mine if r["status"] not in (expected, "inconclusive")
                 or (r["style"] == "shannon" and r["status"] != expected)]
        if wrong:
            failures.append({"cell": [width, seed, mutant, backend],
                             "runs": [{k: r.get(k) for k in ("style", "repetition", "status",
                                                             "execution", "execution_reason")}
                                      for r in wrong]})
        cells.append(cell)
    return {"schema_version": 1, "kind": "symq_table_domain_benchmark",
            "scope": "synthetic loader family of tests/testkit/wide_loader_cases.py only; "
                     "no external comparison; no claim beyond the measured cells",
            "machine": machine(), "code": receipt(),
            "settings": {"repetitions": repetitions, "widths": list(widths), "seeds": list(seeds),
                         "mutants": list(mutants), "backends": list(BACKENDS),
                         "styles": list(STYLES), "schedule_seed": SCHEDULE_SEED,
                         "isolated": isolated, "verifier_max_seconds": 60,
                         "hard_limits": {"wall_seconds": 120,
                                         "memory_bytes": _limits().memory_bytes}},
            "wall_seconds": time.perf_counter() - started,
            "cells": cells, "runs": runs, "failures": failures,
            "qualification_passed": not failures}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repetitions", type=int, default=15)
    parser.add_argument("--widths", type=int, nargs="+", default=list(WIDTHS))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(repetitions=args.repetitions, widths=tuple(args.widths))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    for cell in report["cells"]:
        print(cell["width"], cell["seed"], cell["mutant"], cell["backend"], cell["statuses"],
              cell.get("median_ratio_minterms_over_shannon"))
    return 0 if report["qualification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
