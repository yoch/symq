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

MACHINE_KEYS = ("python_version", "implementation", "platform", "machine", "cpu_model",
                "cpu_count", "cpu_affinity", "mem_total_kib")
"""Environment fields that must agree for two records to form a paired comparison."""


def machine_signature(record: dict) -> tuple:
    """What makes two records comparable: the machine, the interpreter and the SAT library."""
    environment = record["environment"]
    return (*(environment.get(key) for key in MACHINE_KEYS),
            record.get("receipt", {}).get("python_sat"))


def load(directory: Path, split: str) -> tuple[dict, dict]:
    base = json.loads((directory / f"{split}-base.json").read_text(encoding="utf-8"))
    head = json.loads((directory / f"{split}-head.json").read_text(encoding="utf-8"))
    for key in ("split", "repetitions", "timeout_seconds", "backend_options"):
        if base[key] != head[key]:
            raise ValueError(f"{split}: records differ in {key}")
    if machine_signature(base) != machine_signature(head):
        raise ValueError(f"{split}: base and head were measured on different machines, "
                         "interpreters or SAT libraries; this is not a paired comparison")
    return base, head


def _same_machine(rounds: list[Path], split: str) -> None:
    signatures = {machine_signature(load(directory, split)[0]) for directory in rounds}
    if len(signatures) > 1:
        raise ValueError(f"{split}: rounds were measured on different machines")


def _cells(record: dict, backend: str) -> dict[tuple[str, str], float]:
    return {(row["circuit"], row["workload"]): row["median_seconds"]
            for row in record["rows"]
            if row["backend"] == backend and row["status"] == "ok" and row["median_seconds"]}


def ratios(rounds: list[Path], split: str, backend: str
           ) -> dict[tuple[str, str], tuple[float, float]]:
    """``(circuit, workload) -> (baseline, candidate)`` pooled over rounds, for cells ok in every
    record of the split."""
    _same_machine(rounds, split)
    old: list[dict] = []
    new: list[dict] = []
    for directory in rounds:
        base, head = load(directory, split)
        old.append(_cells(base, backend))
        new.append(_cells(head, backend))
    keys = set.intersection(*(set(cells) for cells in old + new))
    return {key: (min(cells[key] for cells in old), min(cells[key] for cells in new))
            for key in sorted(keys)}


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
    for side, values in receipts(args.rounds).items():
        for commit, dirty, source, native, abi in sorted(values, key=str):
            print(f"{side}: commit {commit} dirty={dirty} source {source[:16]} "
                  f"native ABI {abi} {str(native)[:16]}")
    base, _ = load(args.rounds[0], SPLITS[0])
    backends = args.backend or sorted({row["backend"] for row in base["rows"]})
    for backend in backends:
        print(f"\n{backend}, pooled over {len(args.rounds)} round(s)\n")
        print(table(args.rounds, backend))
        if len(args.rounds) > 1:
            for directory in args.rounds:
                print(f"\n{backend}, {directory.name} only\n\n{table(directory, backend)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
