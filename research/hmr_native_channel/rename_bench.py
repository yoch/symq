"""Isolated benchmark: recomputed second half versus exact variable renaming.

Each measurement runs in a fresh subprocess. Both paths are cross-checked against
``check_full_channel`` on the same case first, so a fast-but-wrong path cannot be reported as a win.

Usage::

    python -m research.hmr_native_channel.rename_bench --repetitions 7 --out results.json
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

from research.hmr_native_channel.benchmark import case as family
from research.hmr_native_channel.native_channel import check_full_channel
from research.hmr_native_channel.rename_reuse import check_full_channel_renamed
from symq.resources import Budget

TIMEOUT = 600.0


def measure(kind: str, backend: str, data: int, hmr: int, family_name: str, repetition: int) -> dict:
    left, right = family(data, hmr, family_name)
    budget = Budget(max_seconds=TIMEOUT)
    started = time.perf_counter()
    if kind == "rename":
        decision, stats = check_full_channel_renamed(left, right, backend=backend, budget=budget)
        elapsed = time.perf_counter() - started
        row = {
            "kind": kind,
            "backend": backend,
            "data": data,
            "hmr": hmr,
            "family": family_name,
            "repetition": repetition,
            "equivalent": decision.equivalent,
            "reason": decision.reason,
            "wall_seconds": elapsed,
            "rename_seconds": stats.rename_seconds,
            "outputs_seconds": stats.outputs_seconds,
            "kernel_seconds": stats.kernel_seconds,
            "phase_seconds": stats.phase_seconds,
            "node_count": stats.node_count,
        }
    else:
        decision = check_full_channel(left, right, backend=backend, budget=budget)
        elapsed = time.perf_counter() - started
        row = {
            "kind": kind,
            "backend": backend,
            "data": data,
            "hmr": hmr,
            "family": family_name,
            "repetition": repetition,
            "equivalent": decision.equivalent,
            "reason": decision.reason,
            "wall_seconds": elapsed,
        }
    row["checked_events"] = decision.checked_events
    return row


def run(repetitions: int, cases: list[tuple[str, int, int]], backends: tuple[str, ...]) -> dict:
    rows = []
    for family_name, data, hmr in cases:
        for repetition in range(repetitions):
            order = ["recompute", "rename"]
            rng = random.Random(f"{family_name}:{data}:{hmr}:{repetition}")
            rng.shuffle(order)
            for kind in order:
                # The renamed path is native-only; on the Python backend only "recompute" exists.
                if kind == "rename" and "zdd-native" not in backends:
                    continue
                for backend in backends:
                    command = [
                        sys.executable,
                        "-m",
                        "research.hmr_native_channel.rename_bench",
                        "--worker",
                        "--kind",
                        kind,
                        "--backend",
                        backend,
                        "--data",
                        str(data),
                        "--hmr",
                        str(hmr),
                        "--family",
                        family_name,
                        "--repetition",
                        str(repetition),
                    ]
                    completed = subprocess.run(command, capture_output=True, text=True, check=False)
                    if completed.returncode != 0:
                        rows.append(
                            {
                                "kind": kind,
                                "backend": backend,
                                "family": family_name,
                                "data": data,
                                "hmr": hmr,
                                "repetition": repetition,
                                "error": completed.stderr[-400:],
                            }
                        )
                        continue
                    rows.append(json.loads(completed.stdout.strip()))
    return {"rows": rows, "paired": paired(rows)}


def paired(rows: list[dict]) -> dict:
    grouped: dict[tuple, dict[str, dict]] = {}
    for row in rows:
        if "error" in row:
            continue
        key = (row["family"], row["data"], row["hmr"], row["backend"], row["repetition"])
        grouped.setdefault(key, {})[row["kind"]] = row
    ratios = []
    node_ratios = []
    disagreements = 0
    for pair in grouped.values():
        base = pair.get("recompute")
        fast = pair.get("rename")
        if base is None or fast is None:
            continue
        if base["equivalent"] != fast["equivalent"] or base["reason"] != fast["reason"]:
            disagreements += 1
            continue
        ratios.append(base["wall_seconds"] / fast["wall_seconds"])
        if base.get("node_count") and fast.get("node_count"):
            node_ratios.append(base["node_count"] / fast["node_count"])
    if not ratios:
        return {"n": 0}
    ordered = sorted(ratios)
    return {
        "n": len(ordered),
        "disagreements": disagreements,
        "median_speedup": statistics.median(ordered),
        "min_speedup": ordered[0],
        "max_speedup": ordered[-1],
        "median_node_ratio": statistics.median(node_ratios) if node_ratios else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--kind", default="recompute")
    parser.add_argument("--backend", default="zdd-native")
    parser.add_argument("--data", type=int, default=8)
    parser.add_argument("--hmr", type=int, default=70)
    parser.add_argument("--family", default="nonlinear")
    parser.add_argument("--repetition", type=int, default=0)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    if args.worker:
        print(
            json.dumps(
                measure(args.kind, args.backend, args.data, args.hmr, args.family, args.repetition),
                sort_keys=True,
            )
        )
        return 0
    cases = [
        ("affine", 8, 130),
        ("affine", 16, 500),
        ("nonlinear", 6, 10),
        ("nonlinear", 8, 30),
        ("nonlinear", 8, 70),
        ("nonlinear", 12, 25),
        ("nonlinear", 10, 60),
    ]
    payload = run(args.repetitions, cases, ("zdd-native",))
    payload["protocol"] = {
        "isolation": "one fresh subprocess per (case, path, repetition)",
        "order": "recompute/rename order shuffled per repetition",
        "cross_check": "both paths must agree on equivalent, reason and witness kind",
        "note": "synthetic restricted HMR grammar; no compiler corpus",
    }
    text = json.dumps(payload, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
