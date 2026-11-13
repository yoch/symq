"""Summarize paired quick-benchmark records (a baseline tree against a candidate tree).

Each round directory holds ``<split>-base.json`` and ``<split>-head.json`` written by
``python -m benchmarks.quick`` for the same split, repetitions and timeout. Rounds run the two
trees in opposite orders, so a warm-up or ordering effect shows up as disagreement between rounds
instead of as a speedup. A cell is one (circuit, workload, backend) triple. It is compared only
when every record measured it with status ``ok``. Every record of a split must come from the
same machine, interpreter and SAT library, or the summary refuses it. For each side the pooled time of a cell is the
minimum of its per-round medians, and the ratio is candidate / baseline, so smaller is faster.

    python -m benchmarks.paired docs/evidence/data/2026-10-31/round1 \
        docs/evidence/data/2026-10-31/round2 --backend sat

prints the receipts of both trees and a Markdown table; ``tests/test_evidence.py`` checks that the
tables in ``docs/evidence/performance-2026-10-31.md`` are exactly this output.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

SPLITS = ("dev", "holdout", "extension", "synthetic")
REGRESSION = 1.10
"""Cells slower than this ratio are flagged for inspection. It is not a noise bound: on
sub-millisecond cells, ordering and scheduling effects alone have exceeded it (see the 31 October
records), so a flagged cell is a regression only if it persists across rounds."""

try:  # ``python -m benchmarks.paired``
    from .environment import MACHINE_KEYS, cell_problem, machine_signature
except ImportError:  # executed as a script
    from environment import MACHINE_KEYS, cell_problem, machine_signature

__all__ = ["MACHINE_KEYS", "SPLITS", "exclusions", "load", "machine_signature", "ratios",
           "receipts", "table"]


def _schema(record: dict) -> int:
    """1 for the historical records (no per-cell identity), 2 for current quick-bench records."""
    version = record.get("schema_version")
    if version not in (1, 2) or record.get("kind", "symq_quick_bench") != "symq_quick_bench":
        raise ValueError(f"unsupported quick-bench record: schema {version!r}")
    return version


def load(directory: Path, split: str) -> tuple[dict, dict]:
    base = json.loads((directory / f"{split}-base.json").read_text(encoding="utf-8"))
    head = json.loads((directory / f"{split}-head.json").read_text(encoding="utf-8"))
    if _schema(base) != _schema(head):
        raise ValueError(f"{split}: base and head use different record schemas")
    keys = ["split", "repetitions", "timeout_seconds", "backend_options"]
    if _schema(base) == 2:
        keys.append("slow_stop_seconds")
    for key in keys:
        if base.get(key) != head.get(key):
            raise ValueError(f"{split}: records differ in {key}")
    if machine_signature(base) != machine_signature(head):
        raise ValueError(f"{split}: base and head were measured on different machines, "
                         "interpreters or SAT libraries; this is not a paired comparison")
    return base, head


def _same_machine(rounds: list[Path], split: str) -> None:
    signatures = {machine_signature(load(directory, split)[0]) for directory in rounds}
    if len(signatures) > 1:
        raise ValueError(f"{split}: rounds were measured on different machines")


def _cells(record: dict, backend: str) -> dict[tuple, float]:
    """Comparable cells of one record. Schema 2 cells must pass ``cell_problem`` and carry their
    input digest and backend options in the key, so a cell measured on different inputs or
    options never pairs. Schema 1 (historical) records keep their original rule."""
    if _schema(record) == 1:
        return {(row["circuit"], row["workload"]): row["median_seconds"]
                for row in record["rows"]
                if row["backend"] == backend and row["status"] == "ok" and row["median_seconds"]}
    return {(row["circuit"], row["workload"], row.get("input_sha256"),
             json.dumps(row.get("backend_options"), sort_keys=True)): row["median_seconds"]
            for row in record["rows"]
            if row["backend"] == backend and "input_sha256" in row and "backend_options" in row
            and cell_problem(record, row) is None}


def ratios(rounds: list[Path], split: str, backend: str
           ) -> dict[tuple[str, str], tuple[float, float]]:
    """``(circuit, workload) -> (baseline, candidate)`` pooled over rounds, for cells ok in every
    record of the split."""
    _same_machine(rounds, split)
    if len({_schema(load(directory, split)[0]) for directory in rounds}) > 1:
        raise ValueError(f"{split}: rounds use different record schemas")
    old: list[dict] = []
    new: list[dict] = []
    for directory in rounds:
        base, head = load(directory, split)
        old.append(_cells(base, backend))
        new.append(_cells(head, backend))
    keys = set.intersection(*(set(cells) for cells in old + new))
    return {key[:2]: (min(cells[key] for cells in old), min(cells[key] for cells in new))
            for key in sorted(keys, key=str)}


def exclusions(rounds: Path | list[Path], split: str, backend: str) -> list[str]:
    """Why each schema-2 cell of ``backend`` is left out of the ratios (empty for schema 1)."""
    rounds = [rounds] if isinstance(rounds, Path) else list(rounds)
    reasons = []
    for directory in rounds:
        base, head = load(directory, split)
        if _schema(base) == 1:
            continue
        cells = {side: {(row["circuit"], row["workload"]): row for row in record["rows"]
                        if row["backend"] == backend}
                 for side, record in (("base", base), ("head", head))}
        for key in sorted(set(cells["base"]) | set(cells["head"])):
            where = f"{directory.name} {key[0]} {key[1]}"
            for side, record in (("base", base), ("head", head)):
                row = cells[side].get(key)
                problem = "missing cell" if row is None else cell_problem(record, row)
                if problem is not None:
                    reasons.append(f"{where}: {side} {problem}")
            if key in cells["base"] and key in cells["head"]:
                for field in ("input_sha256", "backend_options"):
                    if (field not in cells["base"][key] or field not in cells["head"][key]
                            or cells["base"][key][field] != cells["head"][key][field]):
                        reasons.append(f"{where}: different or missing {field}")
    return reasons


def table(rounds: Path | list[Path], backend: str, splits=SPLITS) -> str:
    rounds = [rounds] if isinstance(rounds, Path) else list(rounds)
    header = ("| Split | Cells | Geometric mean ratio (head/base) | Best | Worst | "
              f"Cells above {REGRESSION:.2f} |")
    lines = [header, "| --- | --- | --- | --- | --- | --- |"]
    for split in splits:
        pairs = ratios(rounds, split, backend)
        if not pairs:
            lines.append(f"| {split} | 0 | — | — | — | — |")
            continue
        values = [new / old for old, new in pairs.values()]
        slower = sum(value > REGRESSION for value in values)
        lines.append(f"| {split} | {len(values)} | {statistics.geometric_mean(values):.2f} | "
                     f"{min(values):.2f} | {max(values):.2f} | {slower} |")
    return "\n".join(lines)


def receipts(rounds: Path | list[Path], splits=SPLITS) -> dict[str, set[tuple]]:
    """The distinct (commit, dirty, source digest, native SHA-256, ABI) of each side."""
    rounds = [rounds] if isinstance(rounds, Path) else list(rounds)
    seen: dict[str, set[tuple]] = {"base": set(), "head": set()}
    for split in splits:
        for side, record in (pair for directory in rounds
                             for pair in zip(("base", "head"), load(directory, split))):
            r = record["receipt"]
            seen[side].add((r["git_commit"], r["git_dirty"], r["source_sha256"],
                            r["native"].get("sha256"), r["native"].get("abi")))
    return seen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rounds", type=Path, nargs="+", help="round directories")
    parser.add_argument("--backend", action="append",
                        help="backend to summarize (repeatable; default: every backend)")
    args = parser.parse_args(argv)
    if any(_schema(load(directory, split)[0]) == 1 for directory in args.rounds
           for split in SPLITS):
        print("legacy schema 1 records: cells are not checked for completeness, inputs or "
              "options (re-measure with benchmarks.quick for schema 2)")
    for side, values in receipts(args.rounds).items():
        for commit, dirty, source, native, abi in sorted(values, key=str):
            print(f"{side}: commit {commit} dirty={dirty} source {source[:16]} "
                  f"native ABI {abi} {str(native)[:16]}")
    base, _ = load(args.rounds[0], SPLITS[0])
    backends = args.backend or sorted({row["backend"] for row in base["rows"]})
    for backend in backends:
        print(f"\n{backend}, pooled over {len(args.rounds)} round(s)\n")
        print(table(args.rounds, backend))
        for split in SPLITS:
            for reason in exclusions(args.rounds, split, backend):
                print(f"excluded ({split}): {reason}")
        if len(args.rounds) > 1:
            for directory in args.rounds:
                print(f"\n{backend}, {directory.name} only\n\n{table(directory, backend)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
