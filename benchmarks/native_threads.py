"""Micro-benchmark of the native core: per-call overhead, simulate throughput and thread scaling.

Run it against two checkouts with the same interpreter and CPU affinity to compare them::

    PYTHONPATH=<checkout>/src taskset -c 0,1 python benchmarks/native_threads.py --label <name>

Only wall-clock medians of this script are reported; they say nothing about the external
comparisons of the paper (a separate, pinned harness).
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from symq import simulate
from symq.backends import zdd_native
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.generators import random_circuit


def median_seconds(function, repeat: int) -> float:
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        function()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


def per_call(repeat: int) -> dict[str, float]:
    alg = NativeZDDAlgebra(16)
    rng = random.Random(3)
    values = [alg.from_terms({rng.randrange(1 << 16) for _ in range(12)}) for _ in range(64)]
    manager = alg.manager
    calls = 20_000

    def xor_loop():
        for index in range(calls):
            manager.xor(values[index & 63], values[(index * 7 + 1) & 63])

    def product_loop():
        for index in range(calls):
            manager.product(values[index & 63], values[(index * 5 + 3) & 63])

    return {"xor_ns": median_seconds(xor_loop, repeat) / calls * 1e9,
            "product_ns": median_seconds(product_loop, repeat) / calls * 1e9}


def cheap_gates(repeat: int) -> float:
    circuit = random_circuit(8, 50_000, random.Random(2), max_controls=1)
    return median_seconds(lambda: simulate(circuit, NativeZDDAlgebra(8)), repeat)


def threads(repeat: int, gates: int) -> dict[str, float]:
    heavy = [random_circuit(12, gates, random.Random(seed), max_controls=3) for seed in range(4)]

    def run(circuit):
        simulate(circuit, NativeZDDAlgebra(12))

    def sequential():
        for circuit in heavy:
            run(circuit)

    def parallel():
        with ThreadPoolExecutor(4) as pool:
            list(pool.map(run, heavy))

    seq, par = median_seconds(sequential, repeat), median_seconds(parallel, repeat)
    return {"sequential_s": seq, "threads4_s": par, "speedup": seq / par}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--gates", type=int, default=70)
    args = parser.parse_args()
    result = {
        "label": args.label,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "module": zdd_native.__file__,
        "abi": zdd_native.ABI_VERSION,
        "repeat": args.repeat,
        "per_call": per_call(args.repeat),
        "cheap_50k_gates_s": cheap_gates(args.repeat),
        "threads": threads(max(3, args.repeat // 2), args.gates),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
