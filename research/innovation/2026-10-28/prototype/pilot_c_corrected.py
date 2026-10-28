"""Pilot C, corrected: continuous simulation, exact liveness, real rebuild, honest verification.

The first version had three defects (see ``PILOT_C_CORRECTIONS.md``): it restarted the simulation
on every fragment, it counted shared nodes once per root, and its "rebuild" continued in the old
manager. All three are fixed here.

**Verification protocol.** A run is correct if its outputs equal, monomial for monomial, the
outputs of the same circuit simulated monolithically by the same native engine. That property is
what a rebuild must preserve, and the native engine itself is checked against the Python ZDD
reference by ``tests/test_continuous_simulation.py`` on every split point of 30 random circuits,
so the chain is: Python reference == native monolithic (tested), and native monolithic ==
chunked/rebuild (measured here, and tested for small widths).

**What is measured.** Wall time of the strategy alone (the reference is computed once per circuit
and excluded), peak unique-table size reached *by the strategy*, number of rebuilds, the time
spent rebuilding, peak RSS, and whether the run completed under the node budget.

Strategies: ``plain`` (one manager), ``bounded`` (lossy fixed-size operation cache), ``rebuild``
(fresh manager when the table crosses a threshold, live roots transferred through explicit
monomials, simulation continues in the new manager).
"""
from __future__ import annotations

import json
import random
import resource
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE.parent))

import continuous

from symq import make_algebra, simulate
from symq.anf import ANF
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.generators import random_circuit
from symq.resources import Budget, ResourceLimitExceeded


@dataclass
class Result:
    strategy: str
    status: str = "ok"
    seconds: float = 0.0
    rebuild_seconds: float = 0.0
    rebuilds: int = 0
    peak_nodes: int = 0
    final_nodes: int = 0
    peak_rss_kib: int = 0
    correct: bool | None = None
    detail: str = ""
    nodes_history: list = field(default_factory=list)


def native_monolithic(circuit) -> tuple[tuple[ANF, ...], int, float]:
    algebra = make_algebra("zdd-native", circuit.width,
                           Budget(max_nodes=6_000_000, max_seconds=120.0))
    started = time.perf_counter()
    roots = simulate(circuit, algebra)
    seconds = time.perf_counter() - started
    return tuple(algebra.to_anf(value) for value in roots), algebra.node_count, seconds


def transfer_by_terms(source: NativeZDDAlgebra, roots, budget: Budget
                      ) -> tuple[NativeZDDAlgebra, tuple[int, ...]]:
    fresh = NativeZDDAlgebra(source.width, budget.start())
    moved = tuple(fresh.from_anf(ANF(frozenset(source.manager.anf(root)))) for root in roots)
    return fresh, moved


def run_plain(circuit, budget: Budget, *, cache_limit: int | None,
              expected: tuple[ANF, ...]) -> Result:
    result = Result("bounded" if cache_limit else "plain")
    started = time.perf_counter()
    algebra = NativeZDDAlgebra(circuit.width, budget.start(), cache_limit=cache_limit)
    roots = continuous.simulate_in_chunks(algebra, circuit, 1)
    result.seconds = time.perf_counter() - started
    result.final_nodes = algebra.node_count
    result.peak_nodes = algebra.node_count
    result.correct = tuple(algebra.to_anf(value) for value in roots) == expected
    result.peak_rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return result


def run_rebuild(circuit, budget: Budget, chunks: int, threshold: int,
                expected: tuple[ANF, ...]) -> Result:
    result = Result("rebuild")
    algebra = NativeZDDAlgebra(circuit.width, budget.start())
    parts = continuous.chunks(circuit, chunks)
    started = time.perf_counter()
    state = continuous.initial_state(algebra)
    for index, fragment in enumerate(parts):
        state = continuous.apply_fragment(algebra, state, fragment)
        result.peak_nodes = max(result.peak_nodes, algebra.node_count)
        result.nodes_history.append(algebra.node_count)
        remaining = parts[index + 1:]
        if not remaining or algebra.node_count < threshold:
            continue
        mark = time.perf_counter()
        algebra, moved = transfer_by_terms(algebra, state, budget)
        result.rebuild_seconds += time.perf_counter() - mark
        result.rebuilds += 1
        state = tuple(moved)
    result.seconds = time.perf_counter() - started
    result.final_nodes = algebra.node_count
    result.correct = tuple(algebra.to_anf(value) for value in state) == expected
    result.peak_rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return result


def one_cell(width: int, gates: int, seed: int, chunks: int, threshold: int) -> list[dict]:
    rng = random.Random(seed)
    circuit = random_circuit(width, gates, rng)
    budget = Budget(max_nodes=4_000_000, max_seconds=30.0)
    try:
        expected, reference_nodes, reference_seconds = native_monolithic(circuit)
    except ResourceLimitExceeded:
        return [{"width": width, "gates": gates, "strategy": "reference", "status": "budget"}]
    rows = []
    for label, function in (
            ("plain", lambda: run_plain(circuit, budget, cache_limit=None, expected=expected)),
            ("bounded", lambda: run_plain(circuit, budget, cache_limit=1 << 14,
                                          expected=expected)),
            ("rebuild", lambda: run_rebuild(circuit, budget, chunks, threshold, expected))):
        try:
            result = function()
        except ResourceLimitExceeded as error:
            result = Result(label, status="budget", detail=f"{error.resource} limit exceeded")
        except MemoryError:
            result = Result(label, status="memory")
        rows.append({"width": width, "gates": gates, "reference_nodes": reference_nodes,
                     "reference_seconds": reference_seconds, **result.__dict__})
    return rows


def main() -> int:
    rows = []
    for width, gates in ((10, 100), (12, 140), (13, 170), (14, 200)):
        for row in one_cell(width, gates, 7, 6, threshold=150_000):
            rows.append(row)
            if row.get("status") == "ok":
                print(f"w={width:2d} g={gates:3d} {row['strategy']:8s} "
                      f"{row['seconds']:7.3f}s peak={row['peak_nodes']:8d} "
                      f"(ref {row['reference_nodes']:8d}) correct={row['correct']} "
                      f"rebuilds={row['rebuilds']} gc={row['rebuild_seconds']:6.3f}s",
                      flush=True)
            else:
                print(f"w={width:2d} g={gates:3d} {row['strategy']:8s} {row['status']}",
                      flush=True)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "RESULTS_C_CORRECTED.json")
    out.write_text(json.dumps({"protocol": "corrected continuous pilot", "rows": rows},
                              indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
