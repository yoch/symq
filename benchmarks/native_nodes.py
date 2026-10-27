"""Time and peak memory of one heavy native simulation, in a fresh process per repetition.

Compare two checkouts with the same interpreter and CPU affinity::

    PYTHONPATH=<checkout>/src taskset -c 0 python benchmarks/native_nodes.py --label <name>

The parent process spawns the children; each child reports wall time of ``simulate`` and the
resident-set growth (``ru_maxrss``) caused by the manager. Micro-benchmark of this repository
only, not an external comparison.
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import resource
import statistics
import subprocess
import sys
import time

CASES = [(12, 80, 4, 1), (14, 80, 4, 1), (18, 80, 4, 2)]


def child(width: int, gates: int, controls: int, seed: int) -> None:
    from symq import simulate
    from symq.backends.zdd_native import NativeZDDAlgebra
    from symq.generators import random_circuit

    circuit = random_circuit(width, gates, random.Random(seed), max_controls=controls)
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    algebra = NativeZDDAlgebra(width)
    start = time.perf_counter()
    simulate(circuit, algebra)
    seconds = time.perf_counter() - start
    grown = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before
    print(json.dumps({"seconds": seconds, "rss_mib": grown / 1024, "nodes": algebra.node_count}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="run")
    parser.add_argument("--repeat", type=int, default=9)
    parser.add_argument("--child", nargs=4, type=int, metavar=("WIDTH", "GATES", "CONTROLS", "SEED"))
    args = parser.parse_args()
    if args.child:
        child(*args.child)
        return 0
    report = {"label": args.label, "python": sys.version.split()[0],
              "platform": platform.platform(), "repeat": args.repeat, "cases": []}
    for width, gates, controls, seed in CASES:
        runs = []
        for _ in range(args.repeat):
            out = subprocess.run(
                [sys.executable, __file__, "--child", str(width), str(gates), str(controls),
                 str(seed)], capture_output=True, text=True, check=True).stdout
            runs.append(json.loads(out))
        report["cases"].append({
            "width": width, "gates": gates, "controls": controls, "seed": seed,
            "nodes": runs[0]["nodes"],
            "seconds_median": statistics.median(r["seconds"] for r in runs),
            "seconds_min": min(r["seconds"] for r in runs),
            "rss_mib_median": statistics.median(r["rss_mib"] for r in runs)})
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
