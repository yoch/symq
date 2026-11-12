"""Cost of the address-domain constructions of the table verifiers, on a synthetic family.

Two constructions changed in 0.3.0, and each is measured against the one it replaced, on
the synthetic loader family of ``tests/testkit/wide_loader_cases.py``:

1. **verification** (``verify_affine_table(..., domain_style=...)``): the indicator of the
   admitted addresses by Shannon decomposition (``shannon``) against one selector per
   admitted word (``minterms``, the reference). Paired: each repetition of a cell runs both
   styles back to back, in an order drawn per pair, and the record keeps the ratio of each
   pair. Widths 6 to 12; at 13 to 16 bits only ``shannon`` runs (the reference is the
   reason those widths were refused), and its cost is recorded alone;
2. **conversion** of a shared contract's predicate into the list of admitted words: the
   bit-set evaluation of ``shared_table._admitted`` against one
   ``PredicateDomain.contains`` call per word, the 0.2 construction. Paired the same way,
   widths 6 to 16.

Every run is a fresh worker process (``run_isolated``). A run records its status, its
deterministic counters (products or graph nodes, peak terms) and its times; a run that
stops on a limit is kept, with its time, under ``stopped``. A verdict that differs from
the case's known status, or from the other style's, fails the qualification and is kept.

Times below about 10 ms are of the order of scheduling noise; the counters are not. The
record says nothing beyond the measured family: synthetic loaders with a few product
terms, two seeds, no external tool.

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
PAIRED_WIDTHS = (6, 8, 10, 12)
WIDE_WIDTHS = (13, 14, 16)
SEEDS = (0, 1)
"""The development seeds of ``tests/test_wide_address_tables.py``."""
MUTANTS = (None, "missing_phase")
SCHEDULE_SEED = 20261112


def verify_job(width: int, seed: int, mutant: str | None, backend: str, style: str) -> dict:
    """One verification, in a worker: build, convert (timed apart), verify. JSON out."""
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


def domain_job(width: int, seed: int, method: str) -> dict:
    """One enumeration of a case's admitted addresses, in a worker."""
    from symq.experimental.table_xor import PredicateValues
    from symq.labs.shared_table import _admitted
    from symq.resources import Guard
    from tests.testkit.wide_loader_cases import case

    domain = PredicateValues.below(width, case(width, seed).upper).domain
    started = time.perf_counter()
    if method == "bitsets":
        words = _admitted(domain, Guard())
    else:
        words = [word for word in range(1 << width) if domain.contains(word)]
    return {"seconds": time.perf_counter() - started, "admitted": len(words),
            "checksum": sum(words) % (1 << 61)}


def _limits() -> HardLimits:
    linux = sys.platform.startswith("linux")
    return HardLimits(wall_seconds=120, memory_bytes=4 * 1024**3 if linux else None)


def _isolated(function, *args, isolated=True) -> dict:
    if not isolated:
        return {"execution": "in_process", **function(*args)}
    outcome = run_isolated(function, *args, limits=_limits())
    value = outcome.value if outcome.status == "completed" else {"status": "error"}
    return {"execution": outcome.status, "execution_reason": outcome.reason,
            "worker_wall_seconds": outcome.wall_seconds,
            "worker_cpu_seconds": outcome.cpu_seconds,
            "worker_peak_rss_bytes": outcome.peak_rss_bytes, **value}


def _quantiles(values):
    if not values:
        return None
    ordered = sorted(values)

    def pick(q):
        return ordered[min(len(ordered) - 1, int(q * len(ordered)))]

    return {"median": statistics.median(ordered), "p10": pick(0.1), "p90": pick(0.9),
            "min": ordered[0], "max": ordered[-1], "n": len(ordered)}


def run(*, repetitions: int = 15, paired_widths=PAIRED_WIDTHS, wide_widths=WIDE_WIDTHS,
        seeds=SEEDS, mutants=MUTANTS, isolated: bool = True) -> dict:
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("positive repetitions required")
    rng = random.Random(SCHEDULE_SEED)
    cells = [(w, s, m, b) for w in (*paired_widths, *wide_widths) for s in seeds
             for m in mutants for b in BACKENDS]
    schedule = []
    for cell in cells:
        styles = STYLES if cell[0] in paired_widths else ("shannon",)
        for repetition in range(repetitions):
            schedule.append(("verify", cell, styles, repetition))
    for width in (*paired_widths, *wide_widths):
        for seed in seeds:
            for repetition in range(repetitions):
                schedule.append(("domain", (width, seed), ("bitsets", "per_word"), repetition))
    rng.shuffle(schedule)
    started = time.perf_counter()
    runs = []
    for kind, cell, methods, repetition in schedule:
        order = list(methods)
        rng.shuffle(order)  # which member of the pair runs first
        for position, method in enumerate(order):
            if kind == "verify":
                record = _isolated(verify_job, *cell, method, isolated=isolated)
                key = dict(zip(("width", "seed", "mutant", "backend"), cell))
            else:
                record = _isolated(domain_job, *cell, method, isolated=isolated)
                key = dict(zip(("width", "seed"), cell))
            runs.append({"kind": kind, **key, "method": method, "repetition": repetition,
                         "position": position, **record})
    verification, failures = [], []
    for cell in cells:
        width, seed, mutant, backend = cell
        mine = [r for r in runs if r["kind"] == "verify"
                and (r["width"], r["seed"], r["mutant"], r["backend"]) == cell]
        expected = next((r["expected"] for r in mine if "expected" in r), None)
        summary = {"width": width, "seed": seed, "mutant": mutant, "backend": backend,
                   "expected": expected, "paired": width in paired_widths}
        for style in {r["method"] for r in mine}:
            rows = [r for r in mine if r["method"] == style]
            done = [r for r in rows if r["status"] == expected]
            stopped = [r for r in rows if r["status"] == "inconclusive"]
            summary[style] = {
                "statuses": sorted({r["status"] for r in rows}),
                "verify_seconds": _quantiles([r["verify_seconds"] for r in done]),
                "stopped": {"n": len(stopped), "resources": sorted({str(r.get("resource"))
                                                                    for r in stopped}),
                            "verify_seconds": _quantiles([r["verify_seconds"] for r in stopped])},
                "conversion_seconds": _quantiles([r["conversion_seconds"] for r in rows
                                                  if "conversion_seconds" in r]),
                "products": sorted({r.get("products") for r in done} - {None}),
                "graph_nodes": sorted({r.get("graph_nodes") for r in done} - {None}),
                "peak_terms": sorted({r.get("peak_terms") for r in done} - {None})}
        if summary["paired"]:
            ratios = []
            for repetition in range(repetitions):
                pair = {r["method"]: r for r in mine if r["repetition"] == repetition}
                if all(pair.get(s, {}).get("status") == expected for s in STYLES):
                    ratios.append(pair["minterms"]["verify_seconds"]
                                  / max(pair["shannon"]["verify_seconds"], 1e-9))
            summary["paired_ratio_minterms_over_shannon"] = _quantiles(ratios)
        # The reference may stop on a limit; nothing may return another verdict, and the
        # default construction may not stop at all on this family.
        wrong = [r for r in mine if r["status"] not in (expected, "inconclusive")
                 or (r["method"] == "shannon" and r["status"] != expected)]
        if wrong:
            failures.append({"cell": list(cell), "runs": [
                {k: r.get(k) for k in ("method", "repetition", "status", "execution",
                                       "execution_reason")} for r in wrong]})
        verification.append(summary)
    conversion = []
    for width in (*paired_widths, *wide_widths):
        for seed in seeds:
            mine = [r for r in runs if r["kind"] == "domain"
                    and (r["width"], r["seed"]) == (width, seed)]
            results = {(r.get("admitted"), r.get("checksum")) for r in mine}
            if len(results) != 1 or any(r.get("status") == "error" for r in mine):
                failures.append({"conversion": [width, seed], "results": sorted(map(str, results))})
            ratios = []
            for repetition in range(repetitions):
                pair = {r["method"]: r for r in mine if r["repetition"] == repetition}
                if all("seconds" in pair.get(m, {}) for m in ("bitsets", "per_word")):
                    ratios.append(pair["per_word"]["seconds"]
                                  / max(pair["bitsets"]["seconds"], 1e-9))
            conversion.append({
                "width": width, "seed": seed, "admitted": mine[0].get("admitted") if mine else None,
                **{m: _quantiles([r["seconds"] for r in mine if r["method"] == m and "seconds" in r])
                   for m in ("bitsets", "per_word")},
                "paired_ratio_per_word_over_bitsets": _quantiles(ratios)})
    return {"schema_version": 2, "kind": "symq_table_domain_benchmark",
            "scope": "synthetic loader family of tests/testkit/wide_loader_cases.py, seeds "
                     f"{list(seeds)}; no external comparison; no claim beyond the measured cells",
            "machine": machine(), "code": receipt(),
            "settings": {"repetitions": repetitions, "paired_widths": list(paired_widths),
                         "wide_widths": list(wide_widths), "seeds": list(seeds),
                         "mutants": list(mutants), "backends": list(BACKENDS),
                         "schedule_seed": SCHEDULE_SEED, "isolated": isolated,
                         "verifier_max_seconds": 60,
                         "hard_limits": {"wall_seconds": 120,
                                         "memory_bytes": _limits().memory_bytes}},
            "wall_seconds": time.perf_counter() - started,
            "verification": verification, "conversion": conversion, "runs": runs,
            "failures": failures, "qualification_passed": not failures}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repetitions", type=int, default=15)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(repetitions=args.repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    for cell in report["verification"]:
        print(cell["width"], cell["seed"], cell["mutant"], cell["backend"],
              {s: cell[s]["statuses"] for s in STYLES if s in cell},
              cell.get("paired_ratio_minterms_over_shannon"))
    for cell in report["conversion"]:
        print("conversion", cell["width"], cell["seed"], cell["paired_ratio_per_word_over_bitsets"])
    return 0 if report["qualification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
