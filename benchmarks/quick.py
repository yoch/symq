"""Quick in-process benchmark for regression checks (about a minute).

This is not the publication harness (``benchmarks/run.py`` isolates every cell in a fresh worker
and records memory). It runs the supported circuits of one corpus split through a few workloads
and backends in the current process, takes the median of a few repetitions, and writes a JSON
record that a later run can be compared against:

    python -m benchmarks.quick --output before.json
    python -m benchmarks.quick --output after.json --compare before.json

Workloads: ``simulate`` (symbolic outputs), ``equiv`` (against a variant built from sound
rewrites) and ``nonequiv`` (against the circuit with one inserted MCX gate). Every verdict is
checked against its expected value; a wrong verdict aborts the run.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
import zlib
from pathlib import Path

from symq import BACKENDS, Budget, ResourceLimitExceeded, check_equivalence, make_algebra, simulate
from symq.corpus import load_corpus
from symq.generators import equivalent_variant, mutate

try:  # ``python -m benchmarks.quick``
    from .environment import machine
except ImportError:  # executed as a script
    from environment import machine

MANIFEST = Path(__file__).resolve().parent / "corpus" / "qcec" / "MANIFEST.json"
WORKLOADS = ("simulate", "equiv", "nonequiv")
DEFAULT_BACKENDS = ("sparse", "zdd", "zdd-native", "sat")


def _pair(name, circuit, workload):
    rng = random.Random(zlib.crc32(name.encode()))
    if workload == "equiv":
        return equivalent_variant(circuit, rng, steps=len(circuit.gates)), True
    other, _ = mutate(circuit, rng, kind="insert")
    return other, False


def _run(circuit, other, workload, backend, budget, options):
    if workload == "simulate":
        algebra = make_algebra(backend, circuit.width, budget)
        simulate(circuit, algebra)
        return None
    if backend == "sat":
        from symq.sat import check_sat_equivalence

        verdict = check_sat_equivalence(circuit, other, budget=Budget(max_seconds=budget.max_seconds))
        if verdict.outcome == "inconclusive":
            raise ResourceLimitExceeded("seconds", budget.max_seconds or 0, budget.max_seconds or 0)
        return verdict.outcome == "equivalent"
    return check_equivalence(circuit, other, backend=backend, budget=budget,
                             backend_options=options or None).equivalent


def synthetic_family() -> list[tuple[str, object]]:
    """Harder, reproducible workloads than the QCEC corpus: adders and dense random circuits."""
    from symq.generators import random_circuit
    from symq.generators.arithmetic import cuccaro_adder

    cases = [(f"cuccaro_{n}", cuccaro_adder(n)) for n in (8, 16, 24)]
    cases += [(f"random_14x{gates}_{seed}",
               random_circuit(14, gates, random.Random(seed), max_controls=4))
              for gates in (60, 90) for seed in (1, 2)]
    return cases


def circuits(split: str) -> list[tuple[str, object]]:
    if split == "synthetic":
        return synthetic_family()
    corpus = load_corpus(MANIFEST)
    return [(entry.name, entry.load()) for entry in corpus.entries
            if entry.split == split and entry.status == "supported"]


def run(split: str, backends, repetitions: int, timeout: float, options: dict,
        progress: bool = False) -> dict:
    rows = []
    for name, circuit in circuits(split):
        entry_name = name
        for workload in WORKLOADS:
            other, expected = (None, None) if workload == "simulate" else _pair(
                entry_name, circuit, workload)
            for backend in backends:
                if workload == "simulate" and backend == "sat":
                    continue
                times, status = [], "ok"
                for _ in range(repetitions):
                    budget = Budget(max_seconds=timeout)
                    started = time.perf_counter()
                    try:
                        verdict = _run(circuit, other, workload, backend, budget,
                                       options if backend.startswith("zdd") else {})
                    except ResourceLimitExceeded as error:
                        status = f"limit:{error.resource}"
                        break
                    times.append(time.perf_counter() - started)
                    if verdict is not None and verdict != expected:
                        raise SystemExit(f"wrong verdict: {entry_name} {workload} {backend}")
                    if times[-1] > 1.0:
                        break  # one slow measurement is informative enough for a quick bench
                rows.append({"circuit": entry_name, "workload": workload, "backend": backend,
                             "status": status,
                             "median_seconds": statistics.median(times) if times else None})
                if progress:
                    print(report_row(rows[-1]), file=sys.stderr, flush=True)
    return {"schema_version": 1, "kind": "symq_quick_bench", "split": split,
            "repetitions": repetitions, "timeout_seconds": timeout,
            "backend_options": options, "environment": machine(), "rows": rows}


def _key(row):
    return row["circuit"], row["workload"], row["backend"]


def report_row(row: dict) -> str:
    median = row["median_seconds"]
    cell = f"{median * 1000:9.2f}ms" if median is not None else f"{row['status']:>11}"
    return f"{row['circuit']:<16} {row['workload']:<9} {row['backend']:<11} {cell:>10}"


def report(result: dict, baseline: dict | None) -> str:
    previous = {_key(row): row for row in (baseline or {}).get("rows", [])}
    lines = [f"{'circuit':<16} {'workload':<9} {'backend':<11} {'median':>10}"
             + (f" {'ratio':>7}" if baseline else "")]
    ratios = []
    for row in result["rows"]:
        median = row["median_seconds"]
        cell = f"{median * 1000:9.2f}ms" if median is not None else f"{row['status']:>11}"
        line = f"{row['circuit']:<16} {row['workload']:<9} {row['backend']:<11} {cell:>10}"
        old = previous.get(_key(row))
        if baseline and old and old["median_seconds"] and median:
            ratio = median / old["median_seconds"]
            ratios.append(ratio)
            line += f" {ratio:7.2f}"
        lines.append(line)
    if ratios:
        lines.append(f"geometric mean ratio (new/old) over {len(ratios)} cells: "
                     f"{statistics.geometric_mean(ratios):.3f}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="dev",
                        choices=("dev", "holdout", "extension", "synthetic"))
    parser.add_argument("--backends", nargs="+",
                        default=[b for b in DEFAULT_BACKENDS if b in BACKENDS or b == "sat"])
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--progress", action="store_true", help="print each cell as it finishes")
    parser.add_argument("--option", action="append", default=[],
                        help="backend option for the ZDD backends, e.g. collect_every=200")
    parser.add_argument("--output", help="write the JSON record here")
    parser.add_argument("--compare", help="a previous JSON record to compare against")
    args = parser.parse_args(argv)
    if "sat" in args.backends:
        from symq.sat import available

        if not available():
            args.backends = [b for b in args.backends if b != "sat"]
    options = {}
    for item in args.option:
        key, _, value = item.partition("=")
        options[key] = json.loads(value)
    result = run(args.split, args.backends, args.repetitions, args.timeout, options,
                 progress=args.progress)
    baseline = json.loads(Path(args.compare).read_text()) if args.compare else None
    print(report(result, baseline))
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
