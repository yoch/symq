"""Optional explicit paired microbenchmark; no performance or CI acceptance claim.

Run on pinned machines with full-call time, peak tracemalloc, repetitions,
data and source hashes recorded separately. Runtime RSS is not measured here.
"""
from __future__ import annotations

import json
import statistics
import time
import tracemalloc

from symq.phase import PhaseProgram, phase_semantics
from research.bitset_degree3.bitset import evaluate_phase


def case(n: int = 12, hmr: int = 30) -> PhaseProgram:
    p = PhaseProgram(n, 1)
    for i in range(n - 1):
        p.cx(i, i + 1)
    for j in range(hmr):
        p.cx(j % n, n)
        m = p.hmr(n)
        p.z_if(m, j % n)
    return p


def run(n: int = 12, hmr: int = 30, repetitions: int = 7) -> dict:
    p = case(n, hmr)
    results = {}
    for name, func in (
        ("baseline", lambda: phase_semantics(p)),
        ("bitset_k3", lambda: evaluate_phase(p, degree=3)),
    ):
        samples = []
        peaks = []
        for _ in range(repetitions):
            tracemalloc.start()
            start = time.perf_counter()
            try:
                result = func()
            except Exception as exc:
                results[name] = {"error": type(exc).__name__, "detail": str(exc)}
                tracemalloc.stop()
                break
            samples.append(time.perf_counter() - start)
            peaks.append(tracemalloc.get_traced_memory()[1])
            tracemalloc.stop()
        else:
            results[name] = {
                "median_seconds_full_call": statistics.median(samples),
                "max_tracemalloc_bytes": max(peaks),
                "repetitions": repetitions,
            }
    return results


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, indent=2))
