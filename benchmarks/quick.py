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

Ratios use complete, successful cells with the same inputs, backend options and measurement
configuration, measured on the same machine, interpreter and SAT library: the one rule of
``benchmarks.environment.machine_difference``, shared with ``benchmarks.paired`` (kernel build,
CPU count and memory size included). A cell is complete when it has every requested sample, or when it stopped early
because its last sample exceeded the slow-stop threshold: slow cells are the ones a regression
check needs most, so they are compared on the samples they have, never dropped. Older records without input identities remain readable, but are not aggregated.
The measured SymQ source may differ: comparing a change with its base is the point of this tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
import time
import zlib
from pathlib import Path

from symq import (
    BACKENDS,
    Budget,
    Circuit,
    ResourceLimitExceeded,
    check_equivalence,
    make_algebra,
    simulate,
)
from symq.corpus import load_corpus
from symq.generators import equivalent_variant, mutate

try:  # ``python -m benchmarks.quick``
    from .environment import cell_problem, machine, machine_difference, receipt
except ImportError:  # executed as a script
    from environment import cell_problem, machine, machine_difference, receipt

MANIFEST = Path(__file__).resolve().parent / "corpus" / "qcec" / "MANIFEST.json"
WORKLOADS = ("simulate", "equiv", "nonequiv")
DEFAULT_BACKENDS = ("sparse", "zdd", "zdd-native", "sat")
SLOW_STOP_SECONDS = 1.0


def _pair(name, circuit, workload):
    rng = random.Random(zlib.crc32(name.encode()))
    if workload == "equiv":
        return equivalent_variant(circuit, rng, steps=len(circuit.gates)), True
    other, _ = mutate(circuit, rng, kind="insert")
    return other, False


def _run(circuit, other, workload, backend, budget, options):
    if workload == "simulate":
        algebra = make_algebra(backend, circuit.width, budget, **options)
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


def synthetic_family() -> list[tuple[str, Circuit]]:
    """Harder, reproducible workloads than the QCEC corpus: adders and dense random circuits."""
    from symq.generators import random_circuit
    from symq.generators.arithmetic import cuccaro_adder

    cases = [(f"cuccaro_{n}", cuccaro_adder(n)) for n in (8, 16, 24)]
    cases += [(f"random_14x{gates}_{seed}",
               random_circuit(14, gates, random.Random(seed), max_controls=4))
              for gates in (60, 90) for seed in (1, 2)]
    return cases


def circuits(split: str) -> list[tuple[str, Circuit]]:
    if split == "synthetic":
        return synthetic_family()
    corpus = load_corpus(MANIFEST)
    return [(entry.name, entry.load()) for entry in corpus.entries
            if entry.split == split and entry.status == "supported"]


def run(split: str, backends, repetitions: int, timeout: float, options: dict,
        progress: bool = False) -> dict:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    rows = []
    for name, circuit in circuits(split):
        entry_name = name
        for workload in WORKLOADS:
            other, expected = (None, None) if workload == "simulate" else _pair(
                entry_name, circuit, workload)
            inputs = {"circuit": circuit.to_dict(),
                      "other": other.to_dict() if other is not None else None}
            input_sha256 = hashlib.sha256(json.dumps(
                inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            for backend in backends:
                if workload == "simulate" and backend == "sat":
                    continue
                times, status, stopped_slow = [], "ok", False
                backend_options = options if backend.startswith("zdd") else {}
                for _ in range(repetitions):
                    budget = Budget(max_seconds=timeout)
                    started = time.perf_counter()
                    try:
                        verdict = _run(circuit, other, workload, backend, budget, backend_options)
                    except ResourceLimitExceeded as error:
                        status = f"limit:{error.resource}"
                        break
                    times.append(time.perf_counter() - started)
                    if verdict is not None and verdict != expected:
                        raise SystemExit(f"wrong verdict: {entry_name} {workload} {backend}")
                    if times[-1] > SLOW_STOP_SECONDS and len(times) < repetitions:
                        stopped_slow = True
                        break  # one slow measurement is informative enough for a quick bench
                rows.append({"circuit": entry_name, "workload": workload, "backend": backend,
                             "status": status, "input_sha256": input_sha256,
                             "backend_options": dict(backend_options),
                             "repetitions_requested": repetitions,
                             "stopped_after_slow_sample": stopped_slow,
                             "median_seconds": statistics.median(times) if times else None,
                             "seconds": times})
                if progress:
                    print(report_row(rows[-1]), file=sys.stderr, flush=True)
    return {"schema_version": 2, "kind": "symq_quick_bench", "split": split,
            "repetitions": repetitions, "timeout_seconds": timeout,
            "slow_stop_seconds": SLOW_STOP_SECONDS,
            "backend_options": options, "environment": machine(), "receipt": receipt(),
            "rows": rows}


def _key(row):
    return row["circuit"], row["workload"], row["backend"]


def report_row(row: dict, repetitions: int | None = None) -> str:
    median = row["median_seconds"]
    cell = f"{median * 1000:9.2f}ms" if median is not None else "-"
    requested = row.get("repetitions_requested", repetitions)
    samples = f"{len(row.get('seconds', []))}/{requested if requested is not None else '?'}"
    if row.get("stopped_after_slow_sample"):
        samples += "*"  # stopped after one sample above the slow-stop threshold
    return (f"{row['circuit']:<16} {row['workload']:<9} {row['backend']:<11} {cell:>11} "
            f"{row['status']:<16} {samples:>7}")


def _comparison_problem(result, baseline, row, old) -> str | None:
    if old is None:
        return "no baseline cell"
    for label, record, cell in (("new", result, row), ("baseline", baseline, old)):
        problem = cell_problem(record, cell)
        if problem is not None:
            return f"{label}: {problem}"
    if any(record.get("schema_version") != 2 or record.get("kind") != "symq_quick_bench"
           for record in (result, baseline)):
        return "incompatible record schema"
    for field in ("split", "repetitions", "timeout_seconds", "slow_stop_seconds"):
        if field not in result or field not in baseline or result[field] != baseline[field]:
            return f"different or missing {field}"
    for field in ("input_sha256", "backend_options"):
        if field not in row or field not in old or row[field] != old[field]:
            return f"different or missing {field}"
    # SymQ's source receipt is the intended variable; the machine, interpreter and SAT library
    # must match (benchmarks.environment.machine_difference, shared with benchmarks.paired).
    difference = machine_difference(result, baseline)
    if difference is not None:
        return f"different or missing {difference}"
    return None


def report(result: dict, baseline: dict | None) -> str:
    previous = {_key(row): row for row in (baseline or {}).get("rows", [])}
    lines = [f"{'circuit':<16} {'workload':<9} {'backend':<11} {'median':>11} "
             f"{'status':<16} {'reps':>7}"
             + (f" {'ratio':>7}" if baseline else "")]
    ratios = []
    for row in result["rows"]:
        line = report_row(row, result.get("repetitions"))
        old = previous.get(_key(row))
        if baseline:
            problem = _comparison_problem(result, baseline, row, old)
            if problem is None:
                assert old is not None
                ratio = row["median_seconds"] / old["median_seconds"]
                ratios.append(ratio)
                line += f" {ratio:7.2f}"
            else:
                line += f" {'-':>7} ({problem})"
        lines.append(line)
    if ratios:
        lines.append(f"geometric mean ratio (new/old) over {len(ratios)} cells: "
                     f"{statistics.geometric_mean(ratios):.3f}")
    elif baseline:
        lines.append("no comparable cell: each row above gives the reason (a baseline needs "
                     "schema 2 and the same protocol, inputs and machine)")
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
