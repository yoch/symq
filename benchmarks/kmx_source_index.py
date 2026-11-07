"""Bounded synthetic qualification of reusable KMX indexing; no speedup claim."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import resource
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from symq.labs.kmx_source_index import IndexLimits, QueryLimits, build_kmx_index
from symq.resources import Budget

from .environment import machine, receipt

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261107


def _rss() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def trial(noise_ops: int, repetition: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="symq-index-benchmark-") as directory:
        source = Path(directory) / "synthetic.kmx"
        source_hash = hashlib.sha256()
        with source.open("wb") as stream:
            for index in range(noise_ops + 1):
                raw = b"CCX q0 q1 q2\n" if index == noise_ops // 2 else b"X q5 # unrelated\n"
                stream.write(raw)
                source_hash.update(raw)
        pin = source_hash.hexdigest()
        started, cpu = time.perf_counter(), time.process_time()
        with build_kmx_index(source, expected_source_sha256=pin,
                             limits=IndexLimits(), budget=Budget(max_seconds=60)) as index:
            build_wall, build_cpu = time.perf_counter() - started, time.process_time() - cpu
            # Benchmark-only disk observation; these private paths are never exported.
            index_bytes = (Path(index._directory.name) / "operations.sqlite").stat().st_size
            metadata = index.metadata()
            source.unlink()
            tasks = ["cone", "window", "cone", "window", "cone", "window"]
            random.Random(SEED + repetition).shuffle(tasks)
            queries = []
            for kind in tasks:
                started, cpu = time.perf_counter(), time.process_time()
                if kind == "cone":
                    query = {"stop_op": noise_ops + 1, "observed_wires": (0, 1, 2),
                             "expected_source_sha256": pin, "limits": QueryLimits()}
                    selected = index.cone(**query)
                else:
                    query = {"start_op": noise_ops // 2, "stop_op": noise_ops // 2 + 1,
                             "expected_source_sha256": pin, "limits": QueryLimits()}
                    selected = index.window(**query)
                query_wall, query_cpu = time.perf_counter() - started, time.process_time() - cpu
                started, cpu = time.perf_counter(), time.process_time()
                verified = (index.verify_cone(selected, **query) if kind == "cone"
                            else index.verify_window(selected, **query))
                replay_wall, replay_cpu = time.perf_counter() - started, time.process_time() - cpu
                # Fixed literal oracle for this original generator, independent of its index.
                oracle_ok = (selected["gate_indices"] == [noise_ops // 2]
                             and selected["global_wires"] == [0, 1, 2]
                             and verified.to_dict() == {"kind": "classical_reversible", "width": 3,
                                                       "gates": [["ccx", [0, 1, 2]]]})
                queries.append({"kind": kind, "outcome": selected["status"],
                                "work": selected["work"], "oracle_ok": oracle_ok,
                                "query_wall_seconds": query_wall, "query_cpu_seconds": query_cpu,
                                "replay_wall_seconds": replay_wall, "replay_cpu_seconds": replay_cpu})
            return {"repetition": repetition, "outcome": "complete", "source": metadata,
                    "build_wall_seconds": build_wall, "build_cpu_seconds": build_cpu,
                    "index_file_bytes": index_bytes, "snapshot_bytes": metadata["source_bytes"],
                    "process_peak_rss_bytes": _rss(), "queries": queries,
                    "oracle_ok": all(q["oracle_ok"] for q in queries)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--noise-ops", type=int, default=100_000)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20 or not 2 <= args.noise_ops <= 5_000_000:
        parser.error("repetitions must be 1..20 and noise-ops 2..5000000")
    trials = []
    for repetition in range(args.repetitions):
        try:
            trials.append(trial(args.noise_ops, repetition))
        except Exception as error:  # noqa: BLE001 - preserve every failed trial
            trials.append({"repetition": repetition, "outcome": "error", "oracle_ok": False,
                           "reason": f"{type(error).__name__}: {error}"})
    result = {
        "schema_version": 1, "kind": "symq_kmx_index_development_qualification",
        "scope": "synthetic functional and resource evidence; no speedup, holdout or 56M claim",
        "provenance": "original synthetic generator; repository MIT license; exposed development",
        "timing": "serial builds and randomized repeated queries; source generation excluded",
        "memory": "cumulative process peak RSS, including imports and previous repetitions",
        "sqlite_version": sqlite3.sqlite_version, "machine": machine(), "software": receipt(),
        "noise_ops": args.noise_ops, "seed": SEED,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "module_sha256": hashlib.sha256((ROOT / "src/symq/labs/kmx_source_index.py").read_bytes()).hexdigest(),
        "outcomes": dict(Counter(t["outcome"] for t in trials)),
        "all_oracles_ok": all(t["oracle_ok"] for t in trials), "trials": trials,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"trials": len(trials), "outcomes": result["outcomes"],
                      "all_oracles_ok": result["all_oracles_ok"]}, sort_keys=True))
    if not result["all_oracles_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
